-- Job Skills and the Career-Path Ontology
--
-- The right half of the gap analysis. Migration 002 built the course
-- side; this builds the market side, and both reference
-- taxonomy_skills.skill_id, so "Developing ROS 2 Nodes" in a syllabus and
-- "ROS 2 node development" in a posting resolve to one row and the gap is
-- a subtraction rather than a string comparison.

-- ── Per posting ───────────────────────────────────────────────
-- One row per term a posting asked for, whether or not it resolved.
-- Unresolved terms are kept for the same reason course_skills keeps
-- them: they are the review queue, and the record of what the taxonomy
-- is missing. Dropping them would hide the gap in the vocabulary itself.
CREATE TABLE IF NOT EXISTS job_skills (
    id                SERIAL        PRIMARY KEY,
    job_id            INTEGER       NOT NULL,
    term              VARCHAR(300)  NOT NULL,      -- as the posting wrote it

    -- Extraction output
    sources           VARCHAR(120)  NOT NULL DEFAULT '',  -- requirements+qualifications+...
    level             VARCHAR(20)   NOT NULL,      -- beginner | intermediate | advanced
    weight            NUMERIC(4,2)  NOT NULL,

    -- Match output. NULL skill_id means the term did not resolve.
    skill_id          VARCHAR(120),
    match_method      VARCHAR(40),
    match_score       NUMERIC(5,3),
    review_status     VARCHAR(20)   NOT NULL,      -- accepted | needs_review | no_match
    taxonomy_version  VARCHAR(20),

    created_at        TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_job_skill_job
        FOREIGN KEY (job_id) REFERENCES linkedin_jobs (id)
        ON DELETE CASCADE,
    CONSTRAINT fk_job_skill_taxonomy
        FOREIGN KEY (skill_id) REFERENCES taxonomy_skills (skill_id)
        ON DELETE SET NULL,

    CONSTRAINT uq_job_skill_term UNIQUE (job_id, term)
);

CREATE INDEX IF NOT EXISTS idx_job_skills_skill
    ON job_skills (skill_id);
CREATE INDEX IF NOT EXISTS idx_job_skills_status
    ON job_skills (review_status);

-- ── Per career path ───────────────────────────────────────────
-- The ontology: what a path requires, derived from the postings above.
--
-- Keyed on the career path's *name*, not on the Java backend's numeric
-- id. The two services do not share a database, and the integration
-- contract passes skills and paths by name for exactly that reason; a
-- foreign key here would couple this table to a schema it cannot see.
CREATE TABLE IF NOT EXISTS career_path_skills (
    id                SERIAL        PRIMARY KEY,
    career_path       VARCHAR(120)  NOT NULL,
    skill_id          VARCHAR(120)  NOT NULL,

    posting_count     INTEGER       NOT NULL,      -- postings asking for it
    sample_size       INTEGER       NOT NULL,      -- postings in the path
    coverage          NUMERIC(6,4)  NOT NULL,      -- posting_count / sample_size
    required_score    NUMERIC(5,1)  NOT NULL,      -- coverage on a 0-100 scale
    required_level    VARCHAR(20)   NOT NULL,

    derived_from      VARCHAR(20)   NOT NULL DEFAULT 'job_postings',
    taxonomy_version  VARCHAR(20)   NOT NULL,
    updated_at        TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_path_skill_taxonomy
        FOREIGN KEY (skill_id) REFERENCES taxonomy_skills (skill_id)
        ON DELETE CASCADE,

    CONSTRAINT uq_path_skill UNIQUE (career_path, skill_id)
);

CREATE INDEX IF NOT EXISTS idx_career_path_skills_path
    ON career_path_skills (career_path);
CREATE INDEX IF NOT EXISTS idx_career_path_skills_score
    ON career_path_skills (career_path, required_score DESC);
