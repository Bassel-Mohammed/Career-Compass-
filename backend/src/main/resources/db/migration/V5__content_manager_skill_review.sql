-- Content-manager syllabus review and immutable publication history.
--
-- The upload row is the aggregate root.  Existing rows predate qualified course identities,
-- checksums, and extraction state, so the three required identity columns receive deterministic
-- legacy values.  Operators can replace those values during normal review; fabricating a PDF
-- checksum for an old row would be unsafe, therefore content_sha256 intentionally remains NULL.

ALTER TABLE learning_outcomes
    ADD COLUMN institution_code VARCHAR(120) NOT NULL DEFAULT 'legacy:unknown';

ALTER TABLE learning_outcomes
    ADD COLUMN catalog_version VARCHAR(120) NOT NULL DEFAULT 'legacy';

ALTER TABLE learning_outcomes
    ADD COLUMN course_code VARCHAR(80) NOT NULL DEFAULT 'legacy:unassigned';

ALTER TABLE learning_outcomes
    ADD COLUMN content_sha256 CHAR(64) NULL;

ALTER TABLE learning_outcomes
    ADD COLUMN ai_extraction_id VARCHAR(120) NULL;

ALTER TABLE learning_outcomes
    ADD COLUMN extraction_status VARCHAR(32) NOT NULL DEFAULT 'UPLOADED';

ALTER TABLE learning_outcomes
    ADD COLUMN extraction_error TEXT NULL;

ALTER TABLE learning_outcomes
    ADD COLUMN extraction_warnings_json TEXT NULL;

ALTER TABLE learning_outcomes
    ADD COLUMN taxonomy_version VARCHAR(120) NULL;

ALTER TABLE learning_outcomes
    ADD COLUMN draft_revision BIGINT NOT NULL DEFAULT 0;

ALTER TABLE learning_outcomes
    ADD COLUMN course_map_version BIGINT NOT NULL DEFAULT 0;

ALTER TABLE learning_outcomes
    ADD COLUMN updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP;

ALTER TABLE learning_outcomes
    ADD COLUMN published_at TIMESTAMP NULL;

-- A qualified but explicitly legacy identity is safer than guessing an institution code or
-- silently merging historical uploads that happened to use the same display name.
UPDATE learning_outcomes
SET institution_code = CONCAT('legacy:university-field:', university_field_id),
    course_code = CONCAT('legacy:outcome:', outcome_id),
    updated_at = COALESCE(uploaded_at, CURRENT_TIMESTAMP);

ALTER TABLE learning_outcomes
    ADD CONSTRAINT uq_learning_outcomes_ai_extraction UNIQUE (ai_extraction_id);

ALTER TABLE learning_outcomes
    ADD CONSTRAINT chk_learning_outcomes_extraction_status CHECK (
        extraction_status IN (
            'UPLOADED', 'QUEUED', 'EXTRACTING', 'READY_FOR_REVIEW',
            'PUBLISHING', 'PUBLISHED', 'FAILED', 'CANCELLED'
        )
    );

CREATE INDEX idx_learning_outcomes_owner_status
    ON learning_outcomes (uploaded_by_content_manager_id, extraction_status, updated_at);

CREATE INDEX idx_learning_outcomes_course_scope
    ON learning_outcomes (institution_code, catalog_version, course_code);

CREATE TABLE learning_outcome_skill_drafts (
    draft_skill_id BIGINT AUTO_INCREMENT PRIMARY KEY,
    outcome_id INT NOT NULL,
    term VARCHAR(200) NOT NULL,
    canonical_skill_id VARCHAR(120) NULL,
    canonical_label VARCHAR(200) NULL,
    original_canonical_skill_id VARCHAR(120) NULL,
    original_canonical_label VARCHAR(200) NULL,
    level VARCHAR(30) NOT NULL,
    weight DECIMAL(5,4) NOT NULL DEFAULT 0.0000,
    evidence_count INT NOT NULL DEFAULT 0,
    evidence_json TEXT NULL,
    sources_json TEXT NULL,
    candidates_json TEXT NULL,
    match_method VARCHAR(40) NULL,
    match_score DECIMAL(5,4) NULL,
    match_reason TEXT NULL,
    ai_review_status VARCHAR(30) NOT NULL DEFAULT 'no_match',
    decision VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    note VARCHAR(500) NULL,
    row_version BIGINT NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_draft_skill_outcome FOREIGN KEY (outcome_id)
        REFERENCES learning_outcomes(outcome_id) ON DELETE CASCADE,
    CONSTRAINT uq_draft_skill_term UNIQUE (outcome_id, term),
    CONSTRAINT chk_draft_skill_weight CHECK (weight BETWEEN 0.0000 AND 1.0000),
    CONSTRAINT chk_draft_skill_match_score CHECK (
        match_score IS NULL OR match_score BETWEEN 0.0000 AND 1.0000
    ),
    CONSTRAINT chk_draft_skill_evidence_count CHECK (evidence_count >= 0),
    CONSTRAINT chk_draft_skill_decision CHECK (
        decision IN ('PENDING', 'ACCEPTED', 'REPLACED', 'REMOVED', 'ADDED')
    )
);

CREATE INDEX idx_draft_skills_outcome_decision
    ON learning_outcome_skill_drafts (outcome_id, decision, draft_skill_id);

CREATE INDEX idx_draft_skills_canonical
    ON learning_outcome_skill_drafts (outcome_id, canonical_skill_id);

-- A published course map is append-only.  A new review creates a new map_version rather than
-- updating the last published rows, so vectors can always be traced to the exact approved map.
CREATE TABLE course_skill_map_versions (
    map_id BIGINT AUTO_INCREMENT PRIMARY KEY,
    institution_code VARCHAR(120) NOT NULL,
    catalog_version VARCHAR(120) NOT NULL,
    course_code VARCHAR(80) NOT NULL,
    map_version BIGINT NOT NULL,
    state VARCHAR(20) NOT NULL DEFAULT 'PUBLISHING',
    taxonomy_version VARCHAR(120) NULL,
    approved_by_content_manager_id INT NULL,
    source_outcome_id INT NOT NULL,
    checksum CHAR(64) NOT NULL,
    error TEXT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    published_at TIMESTAMP NULL,
    failed_at TIMESTAMP NULL,
    CONSTRAINT fk_course_map_approver FOREIGN KEY (approved_by_content_manager_id)
        REFERENCES content_managers(content_manager_id) ON DELETE SET NULL,
    CONSTRAINT fk_course_map_source_outcome FOREIGN KEY (source_outcome_id)
        REFERENCES learning_outcomes(outcome_id) ON DELETE RESTRICT,
    CONSTRAINT uq_course_map_scope_version UNIQUE (
        institution_code, catalog_version, course_code, map_version
    ),
    CONSTRAINT chk_course_map_version CHECK (map_version > 0),
    CONSTRAINT chk_course_map_state CHECK (state IN ('PUBLISHING', 'PUBLISHED', 'FAILED'))
);

CREATE INDEX idx_course_map_scope_state
    ON course_skill_map_versions (
        institution_code, catalog_version, course_code, state, map_version
    );

CREATE INDEX idx_course_map_source
    ON course_skill_map_versions (source_outcome_id, map_version);

CREATE TABLE course_skill_map_items (
    map_item_id BIGINT AUTO_INCREMENT PRIMARY KEY,
    map_id BIGINT NOT NULL,
    source_draft_skill_id BIGINT NULL,
    term VARCHAR(200) NOT NULL,
    canonical_skill_id VARCHAR(120) NOT NULL,
    canonical_label VARCHAR(200) NOT NULL,
    level VARCHAR(30) NOT NULL,
    weight DECIMAL(5,4) NOT NULL,
    evidence_count INT NOT NULL DEFAULT 0,
    sources_json TEXT NULL,
    evidence_json TEXT NULL,
    decision_note VARCHAR(500) NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_course_map_item_map FOREIGN KEY (map_id)
        REFERENCES course_skill_map_versions(map_id) ON DELETE CASCADE,
    CONSTRAINT fk_course_map_item_draft FOREIGN KEY (source_draft_skill_id)
        REFERENCES learning_outcome_skill_drafts(draft_skill_id) ON DELETE SET NULL,
    CONSTRAINT uq_course_map_canonical_skill UNIQUE (map_id, canonical_skill_id),
    CONSTRAINT chk_course_map_item_weight CHECK (weight BETWEEN 0.0000 AND 1.0000),
    CONSTRAINT chk_course_map_item_evidence_count CHECK (evidence_count >= 0)
);

CREATE INDEX idx_course_map_items_canonical
    ON course_skill_map_items (canonical_skill_id);
