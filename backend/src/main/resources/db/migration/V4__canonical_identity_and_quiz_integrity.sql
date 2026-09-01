-- A question belongs to exactly one quiz/job seeker and can therefore have at most one answer.
-- Historical duplicates must be reviewed before baselining a populated database at V1.
ALTER TABLE quiz_responses
    ADD CONSTRAINT uq_quiz_response_question UNIQUE (question_id);

ALTER TABLE quizzes
    ADD CONSTRAINT chk_quiz_score CHECK (score IS NULL OR score BETWEEN 0 AND 100);

ALTER TABLE jobseeker_skills
    ADD CONSTRAINT chk_jobseeker_skill_score CHECK (score IS NULL OR score BETWEEN 0 AND 100);

ALTER TABLE job_matches
    ADD CONSTRAINT chk_job_match_score CHECK (match_score BETWEEN 0 AND 100);

-- Safe, nullable identity/provenance foundation. Existing name-keyed rows remain valid and can be
-- backfilled from an operator-reviewed mapping; new real-AI writes populate these columns.
ALTER TABLE skills
    ADD COLUMN canonical_skill_id VARCHAR(120) NULL;

ALTER TABLE skills
    ADD COLUMN taxonomy_version VARCHAR(120) NULL;

ALTER TABLE skills
    ADD CONSTRAINT uq_skills_canonical_skill_id UNIQUE (canonical_skill_id);

ALTER TABLE career_paths
    ADD COLUMN career_path_code VARCHAR(120) NULL;

ALTER TABLE career_paths
    ADD COLUMN ontology_version VARCHAR(120) NULL;

ALTER TABLE career_paths
    ADD CONSTRAINT uq_career_paths_code UNIQUE (career_path_code);

ALTER TABLE jobseeker_skills
    ADD COLUMN vector_version VARCHAR(120) NULL;

ALTER TABLE jobseeker_skills
    ADD COLUMN taxonomy_version VARCHAR(120) NULL;

CREATE INDEX idx_jobseeker_skills_vector_version
    ON jobseeker_skills (jobseeker_id, vector_version);
