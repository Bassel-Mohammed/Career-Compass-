"""Unit tests for immutable publication metadata and vector artifacts."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from careercompass.db import course_maps as publication_db
from careercompass.skills.course_maps import (
    artifact_filename,
    build_course_map_document,
    canonical_document_bytes,
    publish_course_map,
)
from careercompass.skills.taxonomy import Taxonomy, make_skill
from careercompass.skills.vector import load_course_skills


def taxonomy() -> Taxonomy:
    return Taxonomy(
        [
            make_skill(
                "custom:docker",
                "Docker",
                "custom",
                skill_type="tool",
                description="Container engine",
            ),
            make_skill(
                "custom:python", "Python", "custom", skill_type="skill"
            ),
        ],
        version="1.0",
    )


def approved(skill_id="custom:docker", term="Containers"):
    return {
        "skill_id": skill_id,
        "skill_label": "caller label is not authoritative",
        "term": term,
        "level": "intermediate",
        "weight": 0.8,
        "evidence_count": 1,
        "sources": ["clo"],
        "evidence": [{"source": "clo", "text": "Deploy containers"}],
    }


def document(version="map-1", institution="MEU", catalog="2026", course="CS101"):
    return build_course_map_document(
        course_map_version=version,
        institution_code=institution,
        catalog_version=catalog,
        course_code=course,
        source_outcome_id="outcome-1",
        taxonomy_version="1.0",
        approved_skills=[approved()],
        taxonomy=taxonomy(),
    )


def test_document_contains_only_accepted_canonical_rows():
    result = document()

    assert result["qualified_course_key"] == "MEU|2026|CS101"
    assert result["publication_status"] == "published"
    assert result["match_summary"]["by_status"] == {"accepted": 1}
    assert result["skills"][0]["canonical"] == {
        "id": "custom:docker",
        "label": "Docker",
        "taxonomy": "custom",
    }
    assert result["skills"][0]["match"]["review_status"] == "accepted"
    assert "needs_review" not in canonical_document_bytes(result).decode("utf-8")


@pytest.mark.parametrize(
    ("version", "skills", "message"),
    [
        ("0.9", [approved()], "stale"),
        ("1.0", [approved("custom:missing")], "unknown canonical"),
        ("1.0", [approved(), approved()], "duplicate canonical"),
    ],
)
def test_document_rejects_stale_unknown_and_duplicate_skills(version, skills, message):
    with pytest.raises(ValueError, match=message):
        build_course_map_document(
            course_map_version="map-x",
            institution_code="MEU",
            catalog_version="2026",
            course_code="CS101",
            source_outcome_id="outcome-1",
            taxonomy_version=version,
            approved_skills=skills,
            taxonomy=taxonomy(),
        )


def test_publication_writes_collision_safe_artifact_atomically(tmp_path):
    calls = []

    def registrar(**kwargs):
        calls.append(kwargs)
        return publication_db.PublicationRecord(
            course_map_version="map-1",
            published_at="2026-08-25T10:00:00Z",
            idempotent=False,
            active=True,
        )

    result = publish_course_map(document(), tmp_path, registrar=registrar)
    path = tmp_path / result.artifact_filename

    assert result.artifact_filename == artifact_filename("MEU|2026|CS101")
    assert path.exists()
    assert json.loads(path.read_text(encoding="utf-8"))["course_map_version"] == "map-1"
    assert calls[0]["payload_sha256"] == result.payload_sha256
    assert calls[0]["payload_json"] == path.read_text(encoding="utf-8")
    assert not list(tmp_path.glob("*.tmp"))


def test_retry_of_superseded_version_does_not_rewrite_active_artifact(tmp_path):
    old = document(version="map-old")
    filename = artifact_filename(old["qualified_course_key"])
    path = tmp_path / filename
    path.write_text('{"course_map_version":"map-new"}', encoding="utf-8")

    def registrar(**_kwargs):
        return publication_db.PublicationRecord(
            course_map_version="map-old",
            published_at="2026-08-25T09:00:00Z",
            idempotent=True,
            active=False,
        )

    result = publish_course_map(old, tmp_path, registrar=registrar)

    assert result.record.idempotent is True
    assert result.record.active is False
    assert json.loads(path.read_text(encoding="utf-8"))["course_map_version"] == "map-new"


def _write_map(path, *, institution, catalog, course):
    payload = document(
        version=f"map-{institution}-{catalog}",
        institution=institution,
        catalog=catalog,
        course=course,
    )
    path.write_bytes(canonical_document_bytes(payload))
    return payload


def test_bare_course_lookup_is_removed_when_qualified_maps_are_ambiguous(tmp_path):
    first = _write_map(
        tmp_path / "first.json", institution="MEU", catalog="2025", course="CS101"
    )
    second = _write_map(
        tmp_path / "second.json", institution="OTHER", catalog="2026", course="CS101"
    )

    mapping = load_course_skills([tmp_path / "first.json", tmp_path / "second.json"])

    assert "CS101" not in mapping
    assert first["qualified_course_key"] in mapping
    assert second["qualified_course_key"] in mapping


def test_single_qualified_map_keeps_backwards_compatible_bare_lookup(tmp_path):
    payload = _write_map(
        tmp_path / "only.json", institution="MEU", catalog="2026", course="CS101"
    )

    mapping = load_course_skills([tmp_path / "only.json"])

    assert mapping["CS101"] is mapping[payload["qualified_course_key"]]


class FakeCursor:
    def __init__(self, conn):
        self.conn = conn
        self.row = None

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, params=None):
        self.conn.statements.append((sql, params))
        compact = " ".join(sql.split())
        if compact.startswith("SELECT institution_code"):
            self.row = self.conn.existing
        elif compact.startswith("SELECT course_map_version"):
            self.row = self.conn.head
        elif compact.startswith("INSERT INTO course_map_publications"):
            self.row = (self.conn.published_at,)
        else:
            self.row = None

    def fetchone(self):
        return self.row


class FakeConnection:
    def __init__(self, *, existing=None, head=None):
        self.existing = existing
        self.head = head
        self.published_at = datetime(2026, 8, 25, 10, 0, tzinfo=timezone.utc)
        self.statements = []
        self.commits = 0
        self.rollbacks = 0
        self.closed = False

    def cursor(self):
        return FakeCursor(self)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        self.closed = True


def registration_args(**overrides):
    args = {
        "course_map_version": "map-1",
        "institution_code": "MEU",
        "catalog_version": "2026",
        "course_code": "CS101",
        "qualified_course_key": "MEU|2026|CS101",
        "source_outcome_id": "outcome-1",
        "taxonomy_version": "1.0",
        "payload_sha256": "a" * 64,
        "artifact_filename": "course_map_hash.json",
        "skill_count": 1,
        "payload_json": "{}",
    }
    args.update(overrides)
    return args


def test_new_publication_is_registered_and_becomes_active():
    conn = FakeConnection()

    result = publication_db.register_course_map_publication(
        **registration_args(), conn=conn
    )

    assert result.idempotent is False
    assert result.active is True
    assert result.published_at == "2026-08-25T10:00:00Z"
    assert conn.commits == 1
    assert conn.rollbacks == 0
    assert any("INSERT INTO course_map_heads" in sql for sql, _ in conn.statements)


def test_same_version_and_digest_is_idempotent_without_moving_head():
    published_at = datetime(2026, 8, 25, 9, 0, tzinfo=timezone.utc)
    conn = FakeConnection(
        existing=("MEU", "2026", "CS101", "a" * 64, published_at),
        head=("map-newer",),
    )

    result = publication_db.register_course_map_publication(
        **registration_args(), conn=conn
    )

    assert result.idempotent is True
    assert result.active is False
    assert not any("INSERT INTO course_map_heads" in sql for sql, _ in conn.statements)
    assert conn.commits == 1


def test_same_version_with_different_payload_is_a_conflict_and_rolls_back():
    conn = FakeConnection(
        existing=(
            "MEU",
            "2026",
            "CS101",
            "b" * 64,
            datetime(2026, 8, 25, tzinfo=timezone.utc),
        )
    )

    with pytest.raises(publication_db.CourseMapVersionConflict):
        publication_db.register_course_map_publication(
            **registration_args(), conn=conn
        )

    assert conn.commits == 0
    assert conn.rollbacks == 1
