"""PostgreSQL metadata for reviewed course-map publications.

The JSON artifact remains the vector builder's read model.  PostgreSQL owns
the publication ledger: version immutability, the active head for each
qualified course, and enough payload metadata to audit or repair an artifact.
Extraction proposals never call this module.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from careercompass.db.connection import get_connection


class CourseMapVersionConflict(RuntimeError):
    """A caller reused an immutable course-map version for different content."""


@dataclass(frozen=True)
class PublicationRecord:
    course_map_version: str
    published_at: str
    idempotent: bool
    active: bool


def _timestamp(value) -> str:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace(
            "+00:00", "Z"
        )
    return str(value)


def register_course_map_publication(
    *,
    course_map_version: str,
    institution_code: str,
    catalog_version: str,
    course_code: str,
    qualified_course_key: str,
    source_outcome_id: str,
    taxonomy_version: str,
    payload_sha256: str,
    artifact_filename: str,
    skill_count: int,
    payload_json: str,
    conn=None,
) -> PublicationRecord:
    """Register one immutable publication and advance its qualified-course head.

    Repeating the exact version and canonical payload succeeds without moving
    the active head.  This detail matters after a newer version has already
    been published: retrying an old HTTP request must not reactivate it.
    """
    owned = conn is None
    conn = conn or get_connection()

    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT institution_code, catalog_version, course_code,
                       payload_sha256, published_at
                  FROM course_map_publications
                 WHERE course_map_version = %s
                 FOR UPDATE
                """,
                (course_map_version,),
            )
            existing = cur.fetchone()

            if existing is not None:
                existing_identity = tuple(existing[:3])
                requested_identity = (institution_code, catalog_version, course_code)
                existing_digest = str(existing[3]).strip()
                if existing_identity != requested_identity or existing_digest != payload_sha256:
                    raise CourseMapVersionConflict(
                        f"Course-map version {course_map_version!r} is already bound "
                        "to different content."
                    )

                cur.execute(
                    """
                    SELECT course_map_version
                      FROM course_map_heads
                     WHERE institution_code = %s
                       AND catalog_version = %s
                       AND course_code = %s
                    """,
                    requested_identity,
                )
                head = cur.fetchone()
                conn.commit()
                return PublicationRecord(
                    course_map_version=course_map_version,
                    published_at=_timestamp(existing[4]),
                    idempotent=True,
                    active=head is not None and head[0] == course_map_version,
                )

            cur.execute(
                """
                INSERT INTO course_map_publications (
                    course_map_version, institution_code, catalog_version,
                    course_code, qualified_course_key, source_outcome_id,
                    taxonomy_version, payload_sha256, artifact_filename,
                    skill_count, payload
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb
                )
                RETURNING published_at
                """,
                (
                    course_map_version,
                    institution_code,
                    catalog_version,
                    course_code,
                    qualified_course_key,
                    source_outcome_id,
                    taxonomy_version,
                    payload_sha256,
                    artifact_filename,
                    skill_count,
                    payload_json,
                ),
            )
            published_at = cur.fetchone()[0]
            cur.execute(
                """
                INSERT INTO course_map_heads (
                    institution_code, catalog_version, course_code,
                    course_map_version
                ) VALUES (%s, %s, %s, %s)
                ON CONFLICT (institution_code, catalog_version, course_code)
                DO UPDATE SET
                    course_map_version = EXCLUDED.course_map_version,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (institution_code, catalog_version, course_code, course_map_version),
            )

        conn.commit()
        return PublicationRecord(
            course_map_version=course_map_version,
            published_at=_timestamp(published_at),
            idempotent=False,
            active=True,
        )
    except Exception:
        conn.rollback()
        raise
    finally:
        if owned:
            conn.close()
