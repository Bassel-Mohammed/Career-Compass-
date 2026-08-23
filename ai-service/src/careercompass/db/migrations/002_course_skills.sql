-- Canonical Skill Taxonomy and Course Skills
--
-- The join that makes the gap analysis possible: course skills and job
-- skills both resolve to taxonomy_skills.skill_id, so "GazeboSim
-- Harmonic" in a syllabus and "Gazebo simulator" in a posting are the
-- same row.
--
-- Embeddings live in the file-backed index (src/data/taxonomy/
-- vector_index.npz), not here: this PostgreSQL server has no pgvector
-- extension available. To move retrieval into the database, install
-- postgresql-18-pgvector, then add:
--     CREATE EXTENSION IF NOT EXISTS vector;
--     ALTER TABLE taxonomy_skills ADD COLUMN embedding vector(1024);
--     CREATE INDEX ON taxonomy_skills USING hnsw (embedding vector_cosine_ops);

-- ── Canonical vocabulary ──────────────────────────────────────
CREATE TABLE IF NOT EXISTS taxonomy_skills (
    skill_id          VARCHAR(120)  PRIMARY KEY,   -- esco:<uuid> | onet:<id> | custom:<slug>
    label             VARCHAR(300)  NOT NULL,
    source            VARCHAR(20)   NOT NULL,      -- esco | onet | custom
    skill_type        VARCHAR(20)   NOT NULL,      -- knowledge | skill | tool | soft
    description       TEXT,
    uri               VARCHAR(500),
    label_ar          VARCHAR(300),
    taxonomy_version  VARCHAR(20)   NOT NULL,
    updated_at        TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_taxonomy_skills_source
    ON taxonomy_skills (source);

-- Alternative wordings. The matcher's exact stage reads this, so it
-- carries the normalised form rather than the display form.
CREATE TABLE IF NOT EXISTS taxonomy_skill_aliases (
    id                SERIAL        PRIMARY KEY,
    skill_id          VARCHAR(120)  NOT NULL,
    alias             VARCHAR(300)  NOT NULL,
    alias_normalized  VARCHAR(300)  NOT NULL,
    language          VARCHAR(10)   NOT NULL DEFAULT 'en',

    CONSTRAINT fk_alias_skill
        FOREIGN KEY (skill_id) REFERENCES taxonomy_skills (skill_id)
        ON DELETE CASCADE,

    CONSTRAINT uq_skill_alias UNIQUE (skill_id, alias_normalized)
);

CREATE INDEX IF NOT EXISTS idx_taxonomy_alias_normalized
    ON taxonomy_skill_aliases (alias_normalized);

-- ── Course side ───────────────────────────────────────────────
-- One row per term a syllabus taught, whether or not it resolved. The
-- unresolved ones are the review queue and the signal for what the
-- taxonomy is missing, so they are kept rather than dropped.
CREATE TABLE IF NOT EXISTS course_skills (
    id                SERIAL        PRIMARY KEY,
    course_code       VARCHAR(30)   NOT NULL,
    term              VARCHAR(300)  NOT NULL,      -- as the syllabus wrote it

    -- Extraction output
    level             VARCHAR(20)   NOT NULL,      -- beginner | intermediate | advanced
    weight            NUMERIC(3,2)  NOT NULL,
    evidence_count    INT           NOT NULL DEFAULT 0,
    sources           VARCHAR(120)  NOT NULL DEFAULT '',
    evidence          JSONB,

    -- Taxonomy match output.
    -- A needs_review row still carries the skill_id the matcher proposed,
    -- so every consumer must filter on review_status = 'accepted' before
    -- treating skill_id as fact. skills_db.get_course_skills does.
    skill_id          VARCHAR(120),
    match_method      VARCHAR(30),                 -- exact_alias | embedding_reranker | llm | none
    match_score       NUMERIC(4,3),
    review_status     VARCHAR(20)   NOT NULL DEFAULT 'no_match',
    match_reason      TEXT,
    candidates        JSONB,                       -- runner-ups, for the reviewer
    taxonomy_version  VARCHAR(20),

    matched_at        TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_course_skill_taxonomy
        FOREIGN KEY (skill_id) REFERENCES taxonomy_skills (skill_id)
        ON DELETE SET NULL,

    CONSTRAINT uq_course_term UNIQUE (course_code, term)
);

CREATE INDEX IF NOT EXISTS idx_course_skills_course
    ON course_skills (course_code);

CREATE INDEX IF NOT EXISTS idx_course_skills_skill
    ON course_skills (skill_id);

-- The review queue is read far more often than it is written.
CREATE INDEX IF NOT EXISTS idx_course_skills_review
    ON course_skills (review_status)
    WHERE review_status <> 'accepted';

-- ── Reviewer decisions ────────────────────────────────────────
-- Kept separate from course_skills so a re-run of the matcher never
-- overwrites a human's judgement, and so the same correction applies to
-- every course that uses the term. This table is also the training and
-- evaluation set the design calls for: 300-500 reviewed mappings, used
-- to tune the accept thresholds.
CREATE TABLE IF NOT EXISTS skill_match_reviews (
    id                SERIAL        PRIMARY KEY,
    term_normalized   VARCHAR(300)  NOT NULL,
    skill_id          VARCHAR(120),                -- NULL means "nothing in the taxonomy fits"
    decision          VARCHAR(20)   NOT NULL,      -- confirmed | corrected | rejected
    reviewer          VARCHAR(100),
    note              TEXT,
    reviewed_at       TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_review_skill
        FOREIGN KEY (skill_id) REFERENCES taxonomy_skills (skill_id)
        ON DELETE SET NULL,

    CONSTRAINT uq_review_term UNIQUE (term_normalized)
);
