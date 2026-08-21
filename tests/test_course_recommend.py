"""
CareerCompass — M4 Course Recommendation Tests

The invariant the design states outright is that the system cannot invent a
course: every item is retrieved from the catalog and carries a real URL. That
is what these tests protect hardest, along with the two quality rules that
were added after watching real output go wrong — a course must not be
recommended for a skill it merely mentions, and it must be at a level the
student can actually use.

Offline: a fake catalog, no network, no model.

Usage:
    python -m tests.test_course_recommend
"""

import json
import sys

from careercompass.skills.course_index import (
    build_index, build_surface_map, skills_in_text,
)
from careercompass.skills.recommend import recommend_courses

_failures = []
_checks = 0


def check(label: str, actual, expected):
    """Assert equality without stopping the run, so every failure is visible."""
    global _checks
    _checks += 1
    if actual != expected:
        _failures.append(f"{label}\n      expected: {expected!r}\n      actual:   {actual!r}")


class FakeTaxonomy:
    def __init__(self, skills):
        self.skills = skills


def skill(skill_id, label, aliases=None):
    return {"id": skill_id, "label": label, "aliases": aliases or [],
            "skill_type": "tool", "labels": {}}


class FakeCourse:
    """Enough of catalog.base.Course for the index to consume."""

    def __init__(self, course_id, title, description="", level=None,
                 platform="coursera", language="en", rating=None, url=None):
        self.course_id = course_id
        self.title = title
        self.url = url or f"https://example.test/{course_id.replace(':', '-')}"
        self.description = description
        self.level = level
        self.platform = platform
        self.language = language
        self.duration_hours = None
        self.rating = rating

    def matchable_text(self):
        return f"{self.title}. {self.description}"


def gap_row(skill_id, label, classification="weak", priority=0.3, gap=0.85,
            importance=0.4, skill_type="tool"):
    return {"skill_id": skill_id, "label": label, "classification": classification,
            "priority": priority, "gap": gap, "importance": importance,
            "skill_type": skill_type}


def gap_of(*rows, career_path="Cybersecurity"):
    return {"career_path": career_path, "skills": list(rows)}


# ── surface map ────────────────────────────────────────────────
def test_head_noun_aliases_are_rejected():
    """ESCO lists aliases far broader than the skill they name.

    "Microsoft Access" claims "Access", so every course mentioning access
    control was tagged as a Microsoft Access course.
    """
    skills = [skill("s:access", "Microsoft Access", ["Access", "MS Access"]),
              skill("s:packaging", "packaging engineering", ["engineering"]),
              skill("s:docker", "Docker", ["containerisation"])]
    surfaces = build_surface_map(skills)

    check("bare head noun dropped", surfaces.get("access"), None)
    check("second head noun dropped", surfaces.get("engineering"), None)
    check("multi-word alias kept", surfaces.get("ms access"), "s:access")
    check("full label kept", surfaces.get("microsoft access"), "s:access")
    # A single-word label is the label, not a head noun lifted out of one.
    check("single-word label kept", surfaces.get("docker"), "s:docker")
    check("distinctive alias kept", surfaces.get("containerisation"), "s:docker")


def test_ambiguous_surfaces_are_dropped():
    """A surface two skills both claim identifies neither."""
    skills = [skill("s:a", "alpha", ["shared term"]),
              skill("s:b", "bravo", ["shared term"])]
    surfaces = build_surface_map(skills)
    check("ambiguous dropped", surfaces.get("shared term"), None)
    check("labels survive", (surfaces.get("alpha"), surfaces.get("bravo")),
          ("s:a", "s:b"))


def test_a_label_outranks_another_skills_alias():
    """The bug that hid CSS from a 14,941-course catalog.

    "css" is the label of CSS and merely an alias of "style sheet languages".
    Treating both claims as equal dropped the surface as ambiguous, so CSS —
    asked for by 14% of Backend postings — matched no course at all. The same
    silence hid NoSQL, Ansible, Metasploit and Xcode.
    """
    skills = [skill("s:css", "CSS", ["Cascading Style Sheets"]),
              skill("s:sheets", "style sheet languages", ["CSS", "SASS"])]
    surfaces = build_surface_map(skills)
    check("label wins over alias", surfaces.get("css"), "s:css")
    check("the alias-only surface survives", surfaces.get("sass"), "s:sheets")

    # Two *labels* colliding is still genuinely ambiguous.
    both = build_surface_map([skill("s:a", "Overlap"), skill("s:b", "Overlap")])
    check("colliding labels dropped", both.get("overlap"), None)


def test_parenthetical_qualifiers_are_stripped():
    """ESCO disambiguates in brackets; no course title does.

    "Ruby (computer programming)" is called Ruby, and matching only the full
    label meant it never matched anything.
    """
    skills = [skill("s:ruby", "Ruby (computer programming)", ["Ruby lang"]),
              skill("s:android", "Android (mobile operating systems)")]
    surfaces = build_surface_map(skills)
    check("bare name matches", surfaces.get("ruby"), "s:ruby")
    check("full label still matches", surfaces.get("ruby computer programming"), "s:ruby")
    check("second case", surfaces.get("android"), "s:android")


def test_restricting_to_ontology_skills():
    """A skill no career path asks for can never appear in a gap."""
    skills = [skill("s:wanted", "Docker"), skill("s:unwanted", "manufacturing dies")]
    surfaces = build_surface_map(skills, skill_ids={"s:wanted"})
    check("wanted kept", surfaces.get("docker"), "s:wanted")
    check("unwanted absent", surfaces.get("manufacturing dies"), None)


def test_tokeniser_handles_sentence_punctuation():
    """Internal punctuation is part of a name; trailing punctuation is not."""
    surfaces = build_surface_map([skill("s:py", "Python"), skill("s:node", "Node.js")])
    check("trailing full stop", skills_in_text("We use Python.", surfaces), {"s:py"})
    check("internal dot kept", skills_in_text("Built on Node.js today", surfaces),
          {"s:node"})


# ── index ──────────────────────────────────────────────────────
def index_of(*courses, ids=None):
    skills = [skill("s:linux", "Linux"), skill("s:docker", "Docker"),
              skill("s:python", "Python")]
    return build_index(list(courses), FakeTaxonomy(skills), skill_ids=ids)


def test_index_records_where_the_match_came_from():
    index = index_of(
        FakeCourse("c:1", "The Linux Essentials", "Learn the shell."),
        FakeCourse("c:2", "HTML5 Authoring", "Runs on Windows, macOS and Linux."))
    by_id = {c["course_id"]: c for c in index["s:linux"]}
    check("both tagged", sorted(by_id), ["c:1", "c:2"])
    check("title match flagged", by_id["c:1"]["in_title"], True)
    check("passing mention not flagged", by_id["c:2"]["in_title"], False)


def test_index_never_carries_a_description():
    """The licence boundary: descriptions are read, then dropped."""
    index = index_of(FakeCourse("c:1", "Docker Deep Dive", "Long partner-owned text."))
    for courses in index.values():
        for course in courses:
            check("no description stored", "description" in course, False)


def test_untagged_courses_are_excluded():
    index = index_of(FakeCourse("c:1", "Basket Weaving", "Reeds and willow."))
    check("nothing indexed", index, {})


# ── recommendation ─────────────────────────────────────────────
def test_every_item_carries_a_real_url():
    """The invariant API_DESIGN states outright."""
    index = index_of(FakeCourse("c:1", "The Linux Essentials", level="beginner"))
    result = recommend_courses(gap_of(gap_row("s:linux", "Linux")), index)
    check("returned something", result["total"] > 0, True)
    for item in result["items"]:
        check("url present", bool(item["course"]["url"].strip()), True)


def test_title_match_outranks_a_passing_mention():
    index = index_of(
        FakeCourse("c:mention", "HTML5 Authoring", "Also runs on Linux.", level="beginner"),
        FakeCourse("c:real", "The Linux Essentials", "The shell.", level="beginner"))
    result = recommend_courses(gap_of(gap_row("s:linux", "Linux")), index)
    check("the real course first", result["items"][0]["course"]["course_id"], "c:real")
    check("flagged", result["items"][0]["matched_in_title"], True)


def test_level_fits_the_size_of_the_gap():
    """A student who has never touched a skill needs the introduction."""
    index = index_of(
        FakeCourse("c:adv", "Advanced Linux", "x", level="advanced"),
        FakeCourse("c:beg", "Linux Basics", "x", level="beginner"))

    weak = recommend_courses(gap_of(gap_row("s:linux", "Linux", "weak")), index)
    check("beginner for a weak skill", weak["items"][0]["course"]["course_id"], "c:beg")

    moderate = recommend_courses(
        gap_of(gap_row("s:linux", "Linux", "moderate", gap=0.2)), index)
    check("advanced for a moderate skill",
          moderate["items"][0]["course"]["course_id"], "c:adv")


def test_met_requirements_are_not_recommended_for():
    index = index_of(FakeCourse("c:1", "The Linux Essentials", level="beginner"))
    result = recommend_courses(
        gap_of(gap_row("s:linux", "Linux", classification="strong")), index)
    check("nothing to close", result["total"], 0)


def test_soft_skills_are_excluded_by_default():
    index = index_of(FakeCourse("c:1", "Linux for Teams", level="beginner"))
    rows = gap_of(gap_row("s:linux", "Linux", skill_type="soft"))
    check("excluded", recommend_courses(rows, index)["total"], 0)
    check("on request", recommend_courses(rows, index, include_soft=True)["total"], 1)


def test_foreign_language_is_penalised_not_dropped():
    """Something a student cannot follow is not advice — but nothing is worse."""
    index = index_of(
        FakeCourse("c:fr", "Linux Essentials", "x", level="beginner", language="fr"),
        FakeCourse("c:en", "Linux Essentials Course", "x", level="beginner", language="en"))
    result = recommend_courses(gap_of(gap_row("s:linux", "Linux")), index)
    check("english first", result["items"][0]["course"]["course_id"], "c:en")
    check("french still offered", len(result["items"]), 2)


def test_platform_filter_and_limits():
    index = index_of(
        FakeCourse("c:1", "Linux One", level="beginner", platform="coursera"),
        FakeCourse("c:2", "Linux Two", level="beginner", platform="ocw"),
        FakeCourse("c:3", "Linux Three", level="beginner", platform="ocw"))
    rows = gap_of(gap_row("s:linux", "Linux"))

    only_ocw = recommend_courses(rows, index, platform="ocw")
    check("filtered", {i["course"]["platform"] for i in only_ocw["items"]}, {"ocw"})
    check("limit honoured", recommend_courses(rows, index, limit=1)["total"], 1)
    check("per-skill cap", len(recommend_courses(rows, index, per_skill=2)["items"]), 2)


def test_uncovered_gaps_are_reported_not_hidden():
    """The honest answer to 'why is there nothing here', and what to fix.

    Carries the label, not just the id. As bare ESCO UUIDs
    (`esco:1d86f05e-e9cc-40ce-99d8-2b21cc71b16b`) this list could not be shown
    to anyone, and the calling service has no taxonomy to resolve them against.
    """
    index = index_of(FakeCourse("c:1", "The Linux Essentials", level="beginner"))
    result = recommend_courses(
        gap_of(gap_row("s:linux", "Linux"), gap_row("s:docker", "Docker")), index)
    check("reported", result["skills_without_courses"],
          [{"skill_id": "s:docker", "skill_label": "Docker"}])

    # One entry per skill, however many platforms failed to serve it.
    twice = recommend_courses(
        gap_of(gap_row("s:docker", "Docker"), gap_row("s:docker", "Docker")), index)
    check("deduplicated", twice["skills_without_courses"],
          [{"skill_id": "s:docker", "skill_label": "Docker"}])


def test_explanation_comes_from_the_gap():
    """Never from the course description — a licence rule and better advice."""
    index = index_of(FakeCourse("c:1", "The Linux Essentials",
                                "Partner-owned marketing copy.", level="beginner"))
    item = recommend_courses(gap_of(gap_row("s:linux", "Linux")), index)["items"][0]
    check("names the skill", "Linux" in item["explanation"], True)
    check("cites demand", "40%" in item["explanation"], True)
    check("no course copy", "marketing copy" in item["explanation"], False)


def test_deterministic():
    index = index_of(
        FakeCourse("c:a", "Linux One", level="beginner"),
        FakeCourse("c:b", "Linux Two", level="beginner"),
        FakeCourse("c:c", "Docker One", level="beginner"))
    rows = gap_of(gap_row("s:linux", "Linux"), gap_row("s:docker", "Docker"))
    first = json.dumps(recommend_courses(rows, index), sort_keys=True)
    for _ in range(3):
        check("stable", json.dumps(recommend_courses(rows, index), sort_keys=True), first)


def main():
    test_head_noun_aliases_are_rejected()
    test_a_label_outranks_another_skills_alias()
    test_parenthetical_qualifiers_are_stripped()
    test_ambiguous_surfaces_are_dropped()
    test_restricting_to_ontology_skills()
    test_tokeniser_handles_sentence_punctuation()
    test_index_records_where_the_match_came_from()
    test_index_never_carries_a_description()
    test_untagged_courses_are_excluded()
    test_every_item_carries_a_real_url()
    test_title_match_outranks_a_passing_mention()
    test_level_fits_the_size_of_the_gap()
    test_met_requirements_are_not_recommended_for()
    test_soft_skills_are_excluded_by_default()
    test_foreign_language_is_penalised_not_dropped()
    test_platform_filter_and_limits()
    test_uncovered_gaps_are_reported_not_hidden()
    test_explanation_comes_from_the_gap()
    test_deterministic()

    print(f"Ran {_checks} checks")
    if _failures:
        print(f"\n❌ {len(_failures)} failed\n")
        for failure in _failures:
            print(f"   - {failure}")
        sys.exit(1)
    print("✅ All checks passed")


if __name__ == "__main__":
    main()
