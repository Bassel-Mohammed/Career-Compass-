"""Build and atomically publish content-manager-approved course maps."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from careercompass.db.course_maps import (
    PublicationRecord,
    register_course_map_publication,
)


def qualified_course_key(
    institution_code: str, catalog_version: str, course_code: str
) -> str:
    """Stable identity shared by the artifact and vector loader."""
    return f"{institution_code}|{catalog_version}|{course_code}"


def artifact_filename(qualified_key: str) -> str:
    """A path-safe, collision-resistant filename for one qualified course."""
    digest = hashlib.sha256(qualified_key.encode("utf-8")).hexdigest()
    return f"course_map_{digest}.json"


def build_course_map_document(
    *,
    course_map_version: str,
    institution_code: str,
    catalog_version: str,
    course_code: str,
    source_outcome_id: str,
    taxonomy_version: str,
    approved_skills: list[dict],
    taxonomy,
) -> dict:
    """Create the accepted-only artifact consumed by student vectors.

    Labels, sources and skill types come from the loaded taxonomy rather than
    the request.  A stale display label in a browser therefore cannot alter
    canonical data during publication.
    """
    if taxonomy_version != taxonomy.version:
        raise ValueError(
            f"taxonomy version {taxonomy_version!r} is stale; current version "
            f"is {taxonomy.version!r}"
        )

    seen = set()
    rows = []
    for approved in approved_skills:
        skill_id = approved["skill_id"]
        if skill_id in seen:
            raise ValueError(f"duplicate canonical skill_id: {skill_id}")
        seen.add(skill_id)

        canonical = taxonomy.index.get(skill_id)
        if canonical is None:
            raise ValueError(f"unknown canonical skill_id: {skill_id}")

        canonical_projection = {
            "id": canonical["id"],
            "label": canonical["label"],
            "taxonomy": canonical["source"],
        }
        rows.append(
            {
                "term": approved["term"],
                "level": approved["level"],
                "weight": approved["weight"],
                "evidence_count": approved["evidence_count"],
                "sources": approved.get("sources") or [],
                "evidence": approved.get("evidence") or [],
                "skill_type": canonical["skill_type"],
                "canonical": canonical_projection,
                "match": {
                    "canonical_id": canonical["id"],
                    "canonical_label": canonical["label"],
                    "taxonomy": canonical["source"],
                    "taxonomy_version": taxonomy.version,
                    "match_method": "human_review",
                    "match_score": 1.0,
                    "review_status": "accepted",
                    "reason": "Approved by the content manager.",
                    "candidates": [],
                },
            }
        )

    qualified_key = qualified_course_key(
        institution_code, catalog_version, course_code
    )
    total = len(rows)
    return {
        "schema_version": "course-map-v1",
        "publication_status": "published",
        "course_map_version": course_map_version,
        "qualified_course_key": qualified_key,
        "institution_code": institution_code,
        "catalog_version": catalog_version,
        "course_code": course_code,
        "source_outcome_id": source_outcome_id,
        "taxonomy_version": taxonomy.version,
        "total_skills": total,
        "match_summary": {
            "total": total,
            "by_status": {"accepted": total},
            "by_method": {"human_review": total},
        },
        "skills": rows,
    }


def canonical_document_bytes(document: dict) -> bytes:
    """Deterministic bytes used for both idempotency and the artifact."""
    return json.dumps(
        document,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _atomic_write(path: Path, payload: bytes) -> None:
    """Replace a JSON artifact without exposing a partially written file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.parent / f".{path.name}.{uuid.uuid4().hex}.tmp"
    fd = None
    try:
        fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as stream:
            fd = None
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
        # Persist the rename itself where the filesystem supports directory
        # fsync.  The artifact contents were already synced above.
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if fd is not None:
            os.close(fd)
        try:
            temp.unlink()
        except FileNotFoundError:
            pass


@contextmanager
def _publication_lock(directory: Path, filename: str):
    """Serialise publishers sharing the same artifact volume."""
    directory.mkdir(parents=True, exist_ok=True)
    lock_path = directory / f".{filename}.lock"
    with lock_path.open("a+b") as stream:
        os.chmod(lock_path, 0o600)
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


@dataclass(frozen=True)
class PublishedCourseMap:
    record: PublicationRecord
    qualified_course_key: str
    payload_sha256: str
    artifact_filename: str


def publish_course_map(
    document: dict,
    directory: Path,
    *,
    registrar: Callable | None = None,
) -> PublishedCourseMap:
    """Register and expose one complete reviewed map.

    The per-artifact file lock spans database registration and replacement, so
    concurrent workers sharing the volume cannot let an older completion write
    over a newer head.  If the database commit succeeds but the filesystem
    replacement fails, retrying the same version is safe and repairs the file.
    """
    registrar = registrar or register_course_map_publication
    directory = Path(directory)
    qualified_key = document["qualified_course_key"]
    filename = artifact_filename(qualified_key)
    payload = canonical_document_bytes(document)
    payload_sha256 = hashlib.sha256(payload).hexdigest()

    with _publication_lock(directory, filename):
        record = registrar(
            course_map_version=document["course_map_version"],
            institution_code=document["institution_code"],
            catalog_version=document["catalog_version"],
            course_code=document["course_code"],
            qualified_course_key=qualified_key,
            source_outcome_id=document["source_outcome_id"],
            taxonomy_version=document["taxonomy_version"],
            payload_sha256=payload_sha256,
            artifact_filename=filename,
            skill_count=document["total_skills"],
            payload_json=payload.decode("utf-8"),
        )
        # An exact retry of an old, superseded version is successful but must
        # not reactivate or rewrite it.  An active retry does rewrite the same
        # deterministic bytes, which repairs a missing/corrupt artifact.
        if record.active:
            _atomic_write(directory / filename, payload)

    return PublishedCourseMap(
        record=record,
        qualified_course_key=qualified_key,
        payload_sha256=payload_sha256,
        artifact_filename=filename,
    )
