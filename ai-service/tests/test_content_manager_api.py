"""API and worker tests for the content-manager review boundary."""

from __future__ import annotations

import hashlib
from types import SimpleNamespace
from unittest.mock import patch

import httpx
import pytest

import careercompass.api.app as app_module
from careercompass.api import jobs
from careercompass.db.course_maps import PublicationRecord
from careercompass.skills.course_maps import PublishedCourseMap
from careercompass.skills.taxonomy import Taxonomy, make_skill


def _taxonomy() -> Taxonomy:
    return Taxonomy(
        [
            make_skill(
                "custom:docker",
                "Docker",
                "custom",
                aliases=["container engine"],
                description="Build and run software containers.",
                skill_type="tool",
            ),
            make_skill(
                "custom:python",
                "Python",
                "custom",
                aliases=["Python programming"],
                description="Programming language.",
                skill_type="skill",
            ),
        ],
        version="1.0",
    )


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def api_client(monkeypatch):
    monkeypatch.delenv("CC_SERVICE_TOKEN", raising=False)
    client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app_module.app),
        base_url="http://testserver",
    )
    try:
        yield client
    finally:
        await client.aclose()


@pytest.mark.anyio
async def test_taxonomy_search_returns_only_canonical_contract_fields(
    api_client, monkeypatch
):
    taxonomy = _taxonomy()
    monkeypatch.setattr(
        app_module.runtime, "require", lambda: SimpleNamespace(taxonomy=taxonomy)
    )

    response = await api_client.get("/api/v1/taxonomy/skills?q=container&limit=1")

    assert response.status_code == 200, response.text
    assert response.json() == {
        "total": 1,
        "items": [
            {
                "skill_id": "custom:docker",
                "label": "Docker",
                "skill_type": "tool",
                "source": "custom",
                "description": "Build and run software containers.",
                "taxonomy_version": "1.0",
            }
        ],
    }


@pytest.mark.anyio
async def test_taxonomy_search_requires_a_nonblank_query(api_client):
    response = await api_client.get("/api/v1/taxonomy/skills?q=")

    assert response.status_code == 422
    assert response.json()["type"] == "invalid-request"


def _publication_payload(**overrides):
    payload = {
        "institution_code": "MEU",
        "catalog_version": "2026",
        "course_code": "CS101",
        "source_outcome_id": "outcome-41",
        "taxonomy_version": "1.0",
        "skills": [
            {
                "skill_id": "custom:docker",
                "skill_label": "possibly stale browser label",
                "term": "Container deployment",
                "level": "intermediate",
                "weight": 0.8,
                "evidence_count": 2,
                "sources": ["clo", "topic"],
                "evidence": [{"source": "clo", "text": "Deploy containers"}],
            }
        ],
    }
    payload.update(overrides)
    return payload


@pytest.mark.anyio
async def test_publish_accepts_backend_institution_codes_with_colon(
    api_client, monkeypatch
):
    """The Java backend derives institution codes as ``uni:<id>`` — a colon the
    publication schema must accept (contract declares no character restriction)."""
    taxonomy = _taxonomy()
    monkeypatch.setattr(
        app_module.runtime, "require", lambda: SimpleNamespace(taxonomy=taxonomy)
    )
    captured = {}

    def fake_publish(document, directory):
        captured["document"] = document
        return PublishedCourseMap(
            record=PublicationRecord(
                course_map_version="map-1",
                published_at="2026-08-25T10:00:00Z",
                idempotent=False,
                active=True,
            ),
            qualified_course_key="uni:41|2026|CS101",
            payload_sha256="a" * 64,
            artifact_filename="course_map_hash.json",
        )

    monkeypatch.setattr(app_module.course_maps, "publish_course_map", fake_publish)

    payload = _publication_payload(institution_code="uni:41")
    response = await api_client.put("/api/v1/course-maps/map-1", json=payload)

    assert response.status_code == 200, response.text
    assert response.json()["course_key"] == "uni:41|2026|CS101"
    assert captured["document"]["institution_code"] == "UNI:41"


@pytest.mark.anyio
async def test_publish_endpoint_builds_accepted_only_map_and_matches_contract(
    api_client, monkeypatch
):
    taxonomy = _taxonomy()
    monkeypatch.setattr(
        app_module.runtime, "require", lambda: SimpleNamespace(taxonomy=taxonomy)
    )
    captured = {}

    def fake_publish(document, directory):
        captured["document"] = document
        captured["directory"] = directory
        return PublishedCourseMap(
            record=PublicationRecord(
                course_map_version="map-1",
                published_at="2026-08-25T10:00:00Z",
                idempotent=False,
                active=True,
            ),
            qualified_course_key="MEU|2026|CS101",
            payload_sha256="a" * 64,
            artifact_filename="course_map_hash.json",
        )

    monkeypatch.setattr(app_module.course_maps, "publish_course_map", fake_publish)

    response = await api_client.put(
        "/api/v1/course-maps/map-1", json=_publication_payload()
    )

    assert response.status_code == 200, response.text
    assert response.json() == {
        "course_map_version": "map-1",
        "course_key": "MEU|2026|CS101",
        "course_code": "CS101",
        "taxonomy_version": "1.0",
        "total_skills": 1,
        "content_sha256": "a" * 64,
        "published_at": "2026-08-25T10:00:00Z",
        "idempotent": False,
    }
    row = captured["document"]["skills"][0]
    assert row["canonical"]["label"] == "Docker"
    assert row["match"]["review_status"] == "accepted"
    assert row["match"]["match_method"] == "human_review"
    assert captured["document"]["publication_status"] == "published"


@pytest.mark.anyio
async def test_publish_rejects_stale_taxonomy_before_storage(api_client, monkeypatch):
    taxonomy = _taxonomy()
    monkeypatch.setattr(
        app_module.runtime, "require", lambda: SimpleNamespace(taxonomy=taxonomy)
    )
    publisher = patch.object(app_module.course_maps, "publish_course_map")
    with publisher as publish:
        response = await api_client.put(
            "/api/v1/course-maps/map-1",
            json=_publication_payload(taxonomy_version="0.9"),
        )

    assert response.status_code == 409
    assert response.json()["type"] == "taxonomy-version-conflict"
    publish.assert_not_called()


@pytest.mark.anyio
async def test_publish_rejects_unknown_and_duplicate_canonical_ids(
    api_client, monkeypatch
):
    taxonomy = _taxonomy()
    monkeypatch.setattr(
        app_module.runtime, "require", lambda: SimpleNamespace(taxonomy=taxonomy)
    )

    unknown = _publication_payload()
    unknown["skills"][0]["skill_id"] = "custom:not-real"
    response = await api_client.put("/api/v1/course-maps/map-2", json=unknown)
    assert response.status_code == 422
    assert response.json()["type"] == "invalid-course-map"

    duplicate = _publication_payload()
    duplicate["skills"].append(dict(duplicate["skills"][0]))
    response = await api_client.put("/api/v1/course-maps/map-3", json=duplicate)
    assert response.status_code == 422
    assert response.json()["type"] == "invalid-request"


class _Decider:
    enabled = False
    available = False
    reason_unavailable = "disabled"


class _Matcher:
    decider = _Decider()

    def match_skills(self, skills):
        return [
            {
                "canonical_id": "custom:docker",
                "canonical_label": "Docker",
                "review_status": "accepted",
                "match_method": "exact_alias",
            }
            for _ in skills
        ]

    def attach(self, skills, matches):
        for skill, match in zip(skills, matches):
            skill["match"] = match

    def summary(self, matches):
        return {
            "by_status": {"accepted": len(matches)},
            "by_method": {"exact_alias": len(matches)},
        }


def _extraction_job(*, store: bool) -> jobs.ExtractionJob:
    digest = hashlib.sha256(b"pdf").hexdigest()
    return jobs.ExtractionJob(
        extraction_id="ext_test",
        content_sha256=digest,
        cache_key="cache",
        filename="course.pdf",
        syllabus={"course_code": "CS101"},
        use_llm=False,
        store=store,
    )


def _candidate_skill():
    return {
        "term": "Docker",
        "level": "intermediate",
        "weight": 0.8,
        "evidence_count": 1,
        "sources": ["clo"],
        "evidence": [],
    }


def test_proposal_only_extraction_writes_neither_json_nor_postgres(monkeypatch):
    monkeypatch.setattr(jobs, "extract_skills", lambda _syllabus: [_candidate_skill()])
    monkeypatch.setattr(jobs.runtime, "matcher_for", lambda _use_llm: _Matcher())

    with patch.object(jobs, "save_skills") as save_json, patch(
        "careercompass.db.skills.store_course_skills"
    ) as save_database:
        job = _extraction_job(store=False)
        jobs._run_job(job)

    save_json.assert_not_called()
    save_database.assert_not_called()
    assert job.result["skills"][0]["match"]["review_status"] == "accepted"
    assert job.stage == "done"


def test_stored_extraction_preserves_existing_json_and_database_writes(monkeypatch):
    monkeypatch.setattr(jobs, "extract_skills", lambda _syllabus: [_candidate_skill()])
    monkeypatch.setattr(jobs.runtime, "matcher_for", lambda _use_llm: _Matcher())

    with patch.object(jobs, "save_skills") as save_json, patch(
        "careercompass.db.skills.store_course_skills"
    ) as save_database:
        jobs._run_job(_extraction_job(store=True))

    save_json.assert_called_once()
    save_database.assert_called_once()


def test_extraction_cache_separates_storage_and_llm_semantics(monkeypatch):
    monkeypatch.setattr(
        jobs.runtime,
        "require",
        lambda: SimpleNamespace(taxonomy=SimpleNamespace(fingerprint="tax-fingerprint")),
    )
    digest = "f" * 64

    keys = {
        jobs.cache_key_for(digest, store=False, use_llm=None),
        jobs.cache_key_for(digest, store=True, use_llm=None),
        jobs.cache_key_for(digest, store=False, use_llm=False),
        jobs.cache_key_for(digest, store=False, use_llm=True),
    }

    assert len(keys) == 4
