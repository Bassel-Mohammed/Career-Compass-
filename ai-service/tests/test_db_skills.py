"""Persistence semantics tested with an in-memory DB-API fake.

These tests verify SQL intent and transaction behaviour without connecting to
the PostgreSQL configured in a developer's ``.env``.
"""

import pytest

from careercompass.db import skills as skills_db
from careercompass.skills.matcher import ACCEPTED, NEEDS_REVIEW, UNMATCHED


class FakeCursor:
    def __init__(self, conn):
        self.conn = conn
        self.rows = []
        self.rowcount = 0

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def __iter__(self):
        return iter(self.rows)

    def execute(self, sql, params=None):
        self.conn.statements.append((sql, params))
        self.rows = []
        for marker, rows in self.conn.responses:
            if marker in sql:
                self.rows = list(rows)
                break
        self.rowcount = len(self.rows)

    def fetchall(self):
        return list(self.rows)


class FakeConnection:
    def __init__(self, responses=()):
        self.responses = list(responses)
        self.statements = []
        self.batches = []
        self.commits = 0
        self.rollbacks = 0
        self.closed = False

    def cursor(self, *_args, **_kwargs):
        return FakeCursor(self)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        self.closed = True


@pytest.fixture
def fake_execute_batch(monkeypatch):
    def execute_batch(cur, sql, rows, page_size=None):
        cur.conn.batches.append((sql, list(rows), page_size))

    monkeypatch.setattr(skills_db.psycopg2.extras, "execute_batch", execute_batch)


def find_statement(conn, marker):
    return next((sql, params) for sql, params in conn.statements if marker in sql)


def matched_skill(term="Docker"):
    return {
        "term": term,
        "level": "intermediate",
        "weight": 0.8,
        "evidence_count": 2,
        "sources": ["topics"],
        "evidence": [],
        "match": {
            "canonical_id": "custom:docker",
            "match_method": "exact_alias",
            "match_score": 1.0,
            "review_status": "accepted",
            "candidates": [],
        },
    }


def test_review_correction_updates_every_normalised_course_term():
    conn = FakeConnection([
        ("SELECT id, term FROM course_skills", [(7, "Action servers"), (8, "Other")]),
    ])

    updated = skills_db.record_review(
        "ACTION-SERVERS",
        "custom:ros2",
        "corrected",
        reviewer="reviewer-1",
        conn=conn,
    )

    assert updated == 1
    _, params = find_statement(conn, "UPDATE course_skills")
    assert params[0] == "custom:ros2"
    assert params[1] == 1.0
    assert params[2] == "accepted"
    assert params[-1] == [7]
    assert conn.commits == 1
    assert conn.rollbacks == 0


def test_review_rejection_marks_no_match_and_clears_proposed_skill():
    conn = FakeConnection([
        ("SELECT id, term FROM course_skills", [(4, "generic noise")]),
    ])

    skills_db.record_review("generic noise", None, "rejected", conn=conn)

    _, params = find_statement(conn, "UPDATE course_skills")
    assert params[:3] == (None, None, "no_match")


@pytest.mark.parametrize(
    ("skill_id", "decision", "message"),
    [
        (None, "confirmed", "require a skill_id"),
        (None, "corrected", "require a skill_id"),
        ("custom:docker", "rejected", "must not include"),
    ],
)
def test_review_decision_shape_is_validated_before_connecting(skill_id, decision, message):
    with pytest.raises(ValueError, match=message):
        skills_db.record_review("term", skill_id, decision, conn=FakeConnection())


def test_review_queue_excludes_terms_with_completed_human_decisions():
    conn = FakeConnection([
        (
            "SELECT course_code, term, review_status",
            [
                ("CS1", "Action servers", "needs_review", 0.2, []),
                ("CS2", "Unresolved term", "no_match", None, []),
            ],
        ),
        (
            "SELECT term_normalized, skill_id, decision FROM skill_match_reviews",
            [("action servers", "custom:ros2", "corrected")],
        ),
    ])

    queue = skills_db.get_review_queue(limit=10, conn=conn)

    assert [item["term"] for item in queue] == ["Unresolved term"]


def test_review_queue_restores_a_correction_whose_taxonomy_id_was_retired():
    conn = FakeConnection([
        (
            "SELECT course_code, term, review_status",
            [("CS1", "Old mapped term", "needs_review", 0.2, [])],
        ),
        (
            "SELECT term_normalized, skill_id, decision FROM skill_match_reviews",
            [("old mapped term", None, "corrected")],
        ),
    ])

    queue = skills_db.get_review_queue(limit=10, conn=conn)

    assert [item["term"] for item in queue] == ["Old mapped term"]


def test_reviewed_matches_include_corrections_and_rejections():
    conn = FakeConnection([
        (
            "SELECT term_normalized, skill_id, decision",
            [
                ("action servers", "custom:ros2", "corrected"),
                ("generic noise", None, "rejected"),
            ],
        ),
    ])

    assert skills_db.load_reviewed_matches(conn) == {
        "action servers": {"skill_id": "custom:ros2", "decision": "corrected"},
        "generic noise": {"skill_id": None, "decision": "rejected"},
    }


def test_matcher_treats_human_correction_as_authoritative(matcher):
    reviewed = matcher.with_thresholds()
    skill = matcher.taxonomy.skills[0]
    reviewed.set_reviewed_decision("manually mapped phrase", skill["id"], "corrected")

    result = reviewed.match("Manually-mapped phrase")

    assert result["canonical_id"] == skill["id"]
    assert result["match_method"] == "human_review"
    assert result["review_status"] == ACCEPTED


def test_matcher_treats_human_rejection_as_authoritative(matcher):
    reviewed = matcher.with_thresholds()
    reviewed.set_reviewed_decision("Docker", None, "rejected")

    result = reviewed.match("docker")

    assert result["canonical_id"] is None
    assert result["match_method"] == "human_review"
    assert result["review_status"] == UNMATCHED


def test_matcher_does_not_accept_a_review_whose_taxonomy_id_was_retired(matcher):
    reviewed = matcher.with_thresholds()
    reviewed.set_reviewed_decision("old mapping", "custom:retired-id", "confirmed")

    result = reviewed.match("old mapping")

    assert result["review_status"] == NEEDS_REVIEW
    assert "no longer available" in result["reason"]


def test_review_overlay_changes_the_student_vector_without_reextracting(matcher):
    from careercompass.skills.vector import build_skill_vector

    reviewed = matcher.with_thresholds()
    skill = matcher.taxonomy.skills[0]
    reviewed.set_reviewed_decision("ambiguous stored term", skill["id"], "corrected")
    stored_json_rows = [{
        "term": "Ambiguous stored term",
        "level": "intermediate",
        "weight": 0.8,
        "canonical": None,
        "match": {
            "canonical_id": "custom:wrong-proposal",
            "review_status": "needs_review",
        },
    }]

    assert reviewed.overlay_reviewed_matches(stored_json_rows) == 1
    vector = build_skill_vector(
        [{"course_code": "CS101", "grade": "A"}],
        {"CS101": stored_json_rows},
    )

    assert [row["skill_id"] for row in vector["skills"]] == [skill["id"]]
    assert stored_json_rows[0]["match"]["match_method"] == "human_review"


def test_course_sync_deletes_terms_missing_from_the_new_extraction(fake_execute_batch):
    conn = FakeConnection()

    skills_db.store_course_skills("CS101", [matched_skill()], conn=conn)

    _, params = find_statement(conn, "DELETE FROM course_skills")
    assert params == ("CS101", ["Docker"])
    assert conn.commits == 1


def test_empty_course_sync_clears_the_course(fake_execute_batch):
    conn = FakeConnection()

    assert skills_db.store_course_skills("CS101", [], conn=conn) == 0

    _, params = find_statement(conn, "DELETE FROM course_skills WHERE course_code")
    assert params == ("CS101",)


def test_job_sync_deletes_terms_missing_from_the_new_extraction(fake_execute_batch):
    conn = FakeConnection()

    skills_db.store_job_skills(42, [matched_skill()], conn=conn)

    _, params = find_statement(conn, "DELETE FROM job_skills")
    assert params == (42, ["Docker"])


def test_empty_ontology_derivation_clears_paths_present_in_totals(fake_execute_batch):
    conn = FakeConnection()

    written = skills_db.store_career_path_skills(
        [], {"Backend Development": 12}, conn=conn,
    )

    assert written == 0
    _, params = find_statement(conn, "DELETE FROM career_path_skills")
    assert params == (["Backend Development"],)
    assert conn.commits == 1


def test_empty_catalog_can_explicitly_clear_a_platform(fake_execute_batch):
    conn = FakeConnection([
        ("SELECT skill_id FROM taxonomy_skills", []),
    ])

    written = skills_db.store_catalog_courses({}, conn=conn, platforms=["coursera"])

    assert written == 0
    _, params = find_statement(conn, "DELETE FROM catalog_courses")
    assert params == (["coursera"],)
    assert conn.commits == 1


def test_career_path_read_returns_skill_type():
    conn = FakeConnection([
        (
            "SELECT c.skill_id",
            [{"skill_id": "custom:docker", "skill_type": "tool"}],
        ),
    ])

    rows = skills_db.get_career_path_skills("DevOps & Cloud", conn=conn)

    assert rows[0]["skill_type"] == "tool"
    sql, _ = find_statement(conn, "SELECT c.skill_id")
    assert "c.skill_type" in sql
