-- 006: immutable content-manager course-map publications
--
-- Extraction proposals are intentionally transient and never enter these
-- tables.  A row is created only after a content manager submits a complete,
-- canonical, accepted-only map through PUT /api/v1/course-maps/{version}.
-- The immutable publication history makes retries safe and makes reusing a
-- version for different content a detectable conflict.

CREATE TABLE IF NOT EXISTS course_map_publications (
    course_map_version   VARCHAR(120) PRIMARY KEY,
    institution_code    VARCHAR(120) NOT NULL,
    catalog_version     VARCHAR(80)  NOT NULL,
    course_code         VARCHAR(64)  NOT NULL,
    qualified_course_key VARCHAR(266) NOT NULL,
    source_outcome_id   VARCHAR(120) NOT NULL,
    taxonomy_version    VARCHAR(20)  NOT NULL,
    payload_sha256      CHAR(64)     NOT NULL,
    artifact_filename   VARCHAR(255) NOT NULL,
    skill_count         INTEGER      NOT NULL,
    payload             JSONB        NOT NULL,
    published_at        TIMESTAMPTZ  NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT ck_course_map_skill_count
        CHECK (skill_count >= 0),
    CONSTRAINT ck_course_map_payload_sha256
        CHECK (payload_sha256 ~ '^[0-9a-f]{64}$'),
    CONSTRAINT uq_course_map_identity_version
        UNIQUE (institution_code, catalog_version, course_code, course_map_version)
);

-- One active publication per fully-qualified course.  History remains in
-- course_map_publications; this small head table is what prevents an
-- idempotent retry of a superseded version from becoming active again.
CREATE TABLE IF NOT EXISTS course_map_heads (
    institution_code    VARCHAR(120) NOT NULL,
    catalog_version     VARCHAR(80)  NOT NULL,
    course_code         VARCHAR(64)  NOT NULL,
    course_map_version  VARCHAR(120) NOT NULL,
    updated_at          TIMESTAMPTZ  NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT pk_course_map_heads
        PRIMARY KEY (institution_code, catalog_version, course_code),
    CONSTRAINT fk_course_map_head_publication
        FOREIGN KEY (course_map_version)
        REFERENCES course_map_publications (course_map_version)
        ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_course_map_publications_course
    ON course_map_publications (institution_code, catalog_version, course_code,
                                published_at DESC);
CREATE INDEX IF NOT EXISTS idx_course_map_publications_source_outcome
    ON course_map_publications (source_outcome_id);
