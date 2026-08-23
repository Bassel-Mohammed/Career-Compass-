"""
CareerCompass — Job Posting Extractor Tests

Checks the three things that separate a posting from a syllabus: that
sections route a term to the right weight and drop the ones that carry no
skills, that the boilerplate a scraper drags in produces nothing, and that
recruiting padding collapses onto the skill underneath it.

The hardest case is real: some scraped rows are an entire web page, and
their navigation menu looks exactly like a list of one-word topics.

Usage:
    python -m tests.test_job_extractor
"""

import sys

from careercompass.skills.job_extractor import (
    extract_job_skills, job_level, refine, sections,
)

_failures = []
_checks = 0


def check(label: str, actual, expected):
    """Assert equality without stopping the run, so every failure is visible."""
    global _checks
    _checks += 1
    if actual != expected:
        _failures.append(f"{label}\n      expected: {expected!r}\n      actual:   {actual!r}")


def check_in(label: str, needle, haystack):
    global _checks
    _checks += 1
    if needle not in haystack:
        _failures.append(f"{label}\n      {needle!r} missing from {sorted(haystack)[:12]}")


def check_not_in(label: str, needle, haystack):
    global _checks
    _checks += 1
    if needle in haystack:
        _failures.append(f"{label}\n      {needle!r} should not be present")


def terms(skills: list) -> dict:
    """Index skills by lowercased term."""
    return {s["term"].lower(): s for s in skills}


# ── Section routing ────────────────────────────────────────────
POSTING = {
    "title": "Senior Backend Engineer",
    "seniority_level": "Mid-Senior level",
    "description": """
About Us
We are a fast-growing company that loves ping pong and free snacks.

Key Responsibilities
Build and maintain RESTful APIs.
Collaborate with product managers on delivery.

Requirements
Strong experience with Kubernetes and Docker.
Proficiency in PostgreSQL.

Nice to have
Familiarity with Terraform.

Benefits
Dental and medical insurance.
Generous stock options and a gym membership.
""",
}


def test_section_routing():
    found = terms(extract_job_skills(POSTING))

    # A requirement outranks a responsibility, which outranks loose prose.
    check_in("section.requirements", "kubernetes", found)
    check("section.requirements.weight", found["kubernetes"]["weight"], 1.0)
    check("section.requirements.zone", found["kubernetes"]["sources"], ["requirements"])

    check_in("section.responsibilities", "restful apis", found)
    check("section.responsibilities.weight",
          found["restful apis"]["weight"], 0.7)
    # "Build and maintain RESTful APIs" — both chained verbs are stripped.
    check_not_in("section.chained_verb", "maintain restful apis", found)

    check_in("section.qualifications", "terraform", found)
    check("section.qualifications.weight", found["terraform"]["weight"], 0.9)

    # The title is the strongest single statement of what the role is.
    check_in("section.title", "backend engineer", found)
    check("section.title.weight", found["backend engineer"]["weight"], 1.0)

    # Dropped sections contribute nothing at all.
    for junk in ("dental", "medical insurance", "stock options", "gym",
                 "ping pong", "free snacks"):
        check_not_in(f"section.dropped.{junk}", junk, found)

    # Headings are structure and never become terms themselves.
    for heading in ("requirements", "key responsibilities", "benefits",
                    "about us", "nice to have"):
        check_not_in(f"section.heading.{heading}", heading, found)


def test_dropped_sections_excluded_from_zones():
    zones = {zone for zone, _ in sections(POSTING["description"])}
    check("sections.zones", zones,
          {"responsibilities", "requirements", "qualifications"})


# ── Boilerplate ────────────────────────────────────────────────
def test_eeo_yields_nothing():
    eeo = {
        "title": "",
        "description": (
            "Acme is an equal opportunity employer. All qualified applicants "
            "will receive consideration for employment without regard to race, "
            "color, religion, sex, sexual orientation, gender identity, "
            "national origin, disability or protected veteran status."
        ),
    }
    check("eeo.empty", extract_job_skills(eeo), [])

    # The same statement broken across lines by the scrape.
    split = {
        "title": "",
        "description": (
            "We are an equal opportunity employer.\n"
            "race, color, religion, sex, national origin,\n"
            "age, disability, veteran status\n"
        ),
    }
    check("eeo.split.empty", extract_job_skills(split), [])


def test_navigation_menu_yields_nothing():
    scraped = {
        "title": "",
        "description": (
            "Home\nAbout Us\nServices\nProducts\nBlog\nCareers\nContact Us\n"
        ),
    }
    check("menu.empty", extract_job_skills(scraped), [])


def test_short_line_survives_outside_a_run():
    """One short line is a topic; three in a row are a menu."""
    posting = {
        "title": "",
        "description": "Requirements\nKubernetes\nWe need someone who ships.\n",
    }
    check_in("menu.single_line_kept", "kubernetes",
             terms(extract_job_skills(posting)))


def test_chrome_stripped():
    posting = {
        "title": "",
        "description": "Requirements\nApply now\nFollow us\nRust\n",
    }
    found = terms(extract_job_skills(posting))
    check_in("chrome.skill_kept", "rust", found)
    check_not_in("chrome.apply", "apply now", found)
    check_not_in("chrome.follow", "follow us", found)


# ── Refinement ─────────────────────────────────────────────────
def test_refine_collapses_padding():
    cases = [
        ("strong communication skills", "communication"),
        ("Excellent problem-solving abilities", "problem-solving"),
        ("5+ years of experience in Kubernetes", "Kubernetes"),
        ("3-5 years of hands-on experience with Docker", "Docker"),
        ("Proficiency in Python", "Python"),
        ("deep knowledge of distributed systems", "distributed systems"),
        ("Kubernetes", "Kubernetes"),
    ]
    for raw, expected in cases:
        check(f"refine.{raw[:28]}", refine(raw), expected)


def test_variants_merge_into_one_term():
    posting = {
        "title": "",
        "description": (
            "Requirements\n"
            "Strong Python skills.\n"
            "5 years of experience in Python.\n"
            "Proficiency in Python.\n"
        ),
    }
    found = terms(extract_job_skills(posting))
    check_in("merge.python", "python", found)
    # Three phrasings, one term, three pieces of evidence behind it.
    check("merge.evidence_count", found["python"]["evidence_count"], 3)


def test_degree_requirements_dropped():
    posting = {
        "title": "",
        "description": (
            "Requirements\n"
            "Bachelor's degree in Computer Science or a related field.\n"
            "Experience with Rust.\n"
        ),
    }
    found = terms(extract_job_skills(posting))
    check_in("degree.skill_kept", "rust", found)
    for junk in ("bachelor's degree in computer science", "related field",
                 "bachelor's degree"):
        check_not_in(f"degree.{junk}", junk, found)


# ── Levels ─────────────────────────────────────────────────────
def test_two_letter_names_are_dropped():
    """
    A known limitation, pinned so it is visible rather than surprising.

    MIN_TERM_LENGTH is 3, so "Go", "R" and "C" never reach the matcher.
    Raising the bound to catch them would admit far more noise than the
    three languages it recovers, and the matcher's own one-word alias
    guard would send them to review regardless.
    """
    posting = {"title": "", "description": "Requirements\nExperience with Go.\n"}
    check("short_name.dropped", extract_job_skills(posting), [])


def test_level_from_seniority_field():
    check("level.entry", job_level({"seniority_level": "Entry level"}), "beginner")
    check("level.associate", job_level({"seniority_level": "Associate"}),
          "intermediate")
    check("level.mid_senior", job_level({"seniority_level": "Mid-Senior level"}),
          "advanced")


def test_level_falls_back_to_title():
    """57% of the corpus has no seniority_level, so the title carries it."""
    check("level.title.senior",
          job_level({"seniority_level": None, "title": "Senior Data Engineer"}),
          "advanced")
    check("level.title.junior",
          job_level({"seniority_level": None, "title": "Junior QA Tester"}),
          "beginner")
    check("level.title.intern",
          job_level({"seniority_level": "", "title": "Software Engineering Intern"}),
          "beginner")
    check("level.title.plain",
          job_level({"seniority_level": None, "title": "Backend Developer"}),
          "intermediate")
    # "Not Applicable" is in the data but not in the mapping; the title wins.
    check("level.unknown_seniority",
          job_level({"seniority_level": "Not Applicable", "title": "Lead SRE"}),
          "advanced")


# ── Shape ──────────────────────────────────────────────────────
def test_shape_matches_the_matcher_contract():
    """SkillMatcher.match_skills reads these keys and no others."""
    skill = extract_job_skills(POSTING)[0]
    check("shape.keys", set(skill),
          {"term", "canonical", "level", "weight", "evidence_count",
           "sources", "evidence"})
    check("shape.canonical_unresolved", skill["canonical"], None)
    check("shape.evidence_text", "text" in skill["evidence"][0], True)


def test_empty_posting():
    check("empty.no_description", extract_job_skills({"title": ""}), [])
    check("empty.blank", extract_job_skills({"title": "", "description": ""}), [])


def main():
    test_section_routing()
    test_dropped_sections_excluded_from_zones()
    test_eeo_yields_nothing()
    test_navigation_menu_yields_nothing()
    test_short_line_survives_outside_a_run()
    test_chrome_stripped()
    test_refine_collapses_padding()
    test_variants_merge_into_one_term()
    test_degree_requirements_dropped()
    test_two_letter_names_are_dropped()
    test_level_from_seniority_field()
    test_level_falls_back_to_title()
    test_shape_matches_the_matcher_contract()
    test_empty_posting()

    print(f"Ran {_checks} checks")
    if _failures:
        print(f"\n❌ {len(_failures)} failed\n")
        for failure in _failures:
            print(f"   - {failure}")
        sys.exit(1)
    print("✅ All checks passed")


if __name__ == "__main__":
    main()
