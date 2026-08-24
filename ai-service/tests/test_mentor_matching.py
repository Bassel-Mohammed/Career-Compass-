"""
Tests for mentor matching (M6).

Uses plain ``assert`` rather than the ``check()`` helper the older suites share — new tests
should fail on the assertion that broke, at the line that broke.

The gap is synthetic throughout. Building a real one would drag in the taxonomy, the course
map and the career-path ontology, none of which these tests are about, and would make the
expected ranking depend on data that changes as syllabi are collected.

Usage:
    pytest tests/test_mentor_matching.py
"""

from datetime import date

import pytest

from careercompass.skills import mentor_matching as mm

TODAY = date(2026, 8, 24)


def gap(**overrides) -> dict:
    """A student weak in SQL and Docker, moderate on Kafka, already strong on Git."""
    base = {
        "career_path": "Backend Development",
        "taxonomy_version": "1.0",
        "skills": [
            {"skill_id": "sql", "label": "SQL", "classification": "weak", "priority": 0.90},
            {"skill_id": "docker", "label": "Docker", "classification": "weak", "priority": 0.50},
            {"skill_id": "kafka", "label": "Kafka", "classification": "moderate", "priority": 0.30},
            {"skill_id": "git", "label": "Git", "classification": "strong", "priority": 0.00},
        ],
    }
    base.update(overrides)
    return base


class FakeMatcher:
    """Resolves only the terms it is given, so tests never touch the real index."""

    def __init__(self, resolutions: dict):
        self.resolutions = resolutions

    def match(self, term: str, evidence: str = "") -> dict:
        skill_id = self.resolutions.get(term)
        if skill_id is None:
            return {"review_status": "no_match", "canonical_id": None}
        return {"review_status": "accepted", "canonical_id": skill_id}


def mentor(mentor_id: str, **kwargs) -> dict:
    return {"mentor_id": mentor_id, **kwargs}


def run(mentors, matcher=None, **kwargs) -> dict:
    return mm.build_mentor_matches(gap(), mentors, matcher=matcher, today=TODAY, **kwargs)


def by_id(result: dict) -> dict:
    return {item["mentor_id"]: item for item in result["items"]}


# ── What a mentor is matched against ───────────────────────────


def test_only_unmet_gaps_are_considered():
    """A mentor is useful for what the student lacks, not for what they already have."""
    matcher = FakeMatcher({"Git": "git"})
    result = run([mentor("m1", expertise_terms=["Git"])], matcher)

    item = by_id(result)["m1"]
    # Git is classified strong, so it is not a gap and must not count as alignment.
    assert item["aligned_skills"] == []
    assert item["gaps_addressed"] == 0


def test_moderate_gaps_count_as_unmet():
    matcher = FakeMatcher({"Kafka": "kafka"})
    item = by_id(run([mentor("m1", expertise_terms=["Kafka"])], matcher))["m1"]
    assert [skill["skill_id"] for skill in item["aligned_skills"]] == ["kafka"]


def test_higher_priority_gaps_are_listed_first():
    matcher = FakeMatcher({"SQL": "sql", "Docker": "docker"})
    item = by_id(run([mentor("m1", expertise_terms=["Docker", "SQL"])], matcher))["m1"]
    # SQL carries the higher priority, so it leads the explanation regardless of input order.
    assert [skill["skill_id"] for skill in item["aligned_skills"]] == ["sql", "docker"]


# ── Evidence quality ───────────────────────────────────────────


def test_stated_expertise_outranks_a_study_field_guess(monkeypatch):
    """
    The regression this exists to prevent.

    A study field is mapped to a whole career path, so an inferred mentor covers nearly every
    gap by construction. Before the coverage cap, that let a mentor nobody had asked about
    outrank one who explicitly listed the skills the student is missing.
    """
    monkeypatch.setattr(mm, "_inferred_skill_ids",
                        lambda field: frozenset({"sql", "docker", "kafka"}))

    matcher = FakeMatcher({"SQL": "sql"})
    result = run(
        [
            mentor("guessed", study_field="Computer Science", field_starting_year=2018),
            mentor("stated", study_field="Computer Science", field_starting_year=2018,
                   expertise_terms=["SQL"]),
        ],
        matcher,
    )

    assert [item["mentor_id"] for item in result["items"]] == ["stated", "guessed"]
    assert by_id(result)["stated"]["signal"] == "stated"
    assert by_id(result)["guessed"]["signal"] == "inferred"


def test_inferred_coverage_is_capped(monkeypatch):
    """Covering every gap by inference must not score as a perfect match."""
    monkeypatch.setattr(mm, "_inferred_skill_ids",
                        lambda field: frozenset({"sql", "docker", "kafka"}))

    item = by_id(run([mentor("m1", study_field="Computer Science")]))["m1"]

    ceiling = mm.COVERAGE_WEIGHT * mm.INFERRED_COVERAGE_CAP * mm.INFERRED_CONFIDENCE
    assert item["score"] <= ceiling + 1e-9


def test_unmapped_study_field_yields_no_attributed_skills(monkeypatch):
    """
    A field the reviewed mapping does not know produces no skills at all.

    Guessing would be worse than admitting ignorance: a fuzzy match would confidently send a
    student to a mentor in an unrelated discipline.
    """
    monkeypatch.setattr(mm, "_inferred_skill_ids", lambda field: frozenset())

    item = by_id(run([mentor("m1", study_field="Fine Art", field_starting_year=2000)]))["m1"]
    assert item["signal"] == "none"
    assert item["aligned_skills"] == []
    assert "experience" in item["explanation"]


def test_unresolvable_expertise_terms_fall_back_rather_than_claiming_a_skill():
    """A term the matcher would not accept must not become a claim the mentor knows it."""
    matcher = FakeMatcher({})  # resolves nothing
    item = by_id(run([mentor("m1", expertise_terms=["Underwater Basket Weaving"])],
                     matcher))["m1"]
    assert item["aligned_skills"] == []
    assert item["signal"] in ("inferred", "none")


def test_a_failing_matcher_does_not_fail_the_request():
    """One bad term is not a reason to refuse to rank anybody."""

    class Exploding:
        def match(self, term, evidence=""):
            raise RuntimeError("index unavailable")

    item = by_id(run([mentor("m1", expertise_terms=["SQL"])], Exploding()))["m1"]
    assert item["mentor_id"] == "m1"


# ── Seniority ──────────────────────────────────────────────────


def test_experience_raises_the_score_when_coverage_is_equal():
    matcher = FakeMatcher({"SQL": "sql"})
    result = run(
        [
            mentor("junior", field_starting_year=2025, expertise_terms=["SQL"]),
            mentor("senior", field_starting_year=2010, expertise_terms=["SQL"]),
        ],
        matcher,
    )
    assert [item["mentor_id"] for item in result["items"]] == ["senior", "junior"]


def test_experience_is_capped_so_it_cannot_outweigh_relevance():
    matcher = FakeMatcher({"SQL": "sql"})
    result = run(
        [
            mentor("ancient", field_starting_year=1970),
            mentor("relevant", field_starting_year=2020, expertise_terms=["SQL"]),
        ],
        matcher,
    )
    assert result["items"][0]["mentor_id"] == "relevant"


def test_missing_starting_year_is_zero_experience_not_an_error():
    item = by_id(run([mentor("m1")]))["m1"]
    assert item["years_experience"] == 0


# ── Contract guarantees ────────────────────────────────────────


def test_no_mentor_id_is_invented():
    matcher = FakeMatcher({"SQL": "sql"})
    supplied = {"a", "b", "c"}
    result = run([mentor(i, expertise_terms=["SQL"]) for i in supplied], matcher)
    assert {item["mentor_id"] for item in result["items"]} <= supplied


def test_ranking_is_deterministic_for_tied_mentors():
    """
    Two mentors with identical evidence must not swap places between requests.

    Without the id tie-break the order would depend on dict iteration, which reads to a
    student as the ranking being arbitrary.
    """
    mentors = [mentor("zeta"), mentor("alpha")]
    first = run(mentors)
    second = run(list(reversed(mentors)))
    assert [i["mentor_id"] for i in first["items"]] == [i["mentor_id"] for i in second["items"]]


def test_limit_truncates_but_total_reports_everyone_scored():
    result = run([mentor(f"m{i}") for i in range(8)], limit=3)
    assert len(result["items"]) == 3
    assert result["total"] == 8


def test_scores_stay_within_range():
    matcher = FakeMatcher({"SQL": "sql", "Docker": "docker", "Kafka": "kafka"})
    result = run([mentor("m1", field_starting_year=1980,
                         expertise_terms=["SQL", "Docker", "Kafka"])], matcher)
    assert 0.0 <= result["items"][0]["score"] <= 1.0


def test_a_student_with_no_gaps_still_returns_a_ranking():
    """Nothing to close is a good outcome, not an error."""
    no_gaps = gap(skills=[
        {"skill_id": "git", "label": "Git", "classification": "strong", "priority": 0.0},
    ])
    result = mm.build_mentor_matches(no_gaps, [mentor("m1", field_starting_year=2015)],
                                     today=TODAY)
    assert result["gaps_considered"] == 0
    assert result["items"][0]["mentor_id"] == "m1"


@pytest.mark.parametrize("field", ["Computer Science", "COMPUTER  science", " computer science "])
def test_study_field_lookup_ignores_case_and_spacing(field):
    """Administrators type study fields by hand; matching must not hinge on their spacing."""
    assert mm._normalize_field(field) == "computer science"
