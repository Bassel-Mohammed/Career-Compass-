-- LinkedIn Jobs Table — Scraped job data from LinkedIn
CREATE TABLE IF NOT EXISTS linkedin_jobs (
    id                SERIAL PRIMARY KEY,

    -- Search context
    career_path       VARCHAR(150)  NOT NULL,
    search_query      VARCHAR(200)  NOT NULL,

    -- Core job info
    title             VARCHAR(300)  NOT NULL,
    company_name      VARCHAR(200),
    location          VARCHAR(200),
    url               VARCHAR(500)  NOT NULL UNIQUE,

    -- Full description (used later for skill extraction + embeddings)
    description       TEXT,

    -- Structured metadata from LinkedIn detail page
    seniority_level   VARCHAR(100),
    employment_type   VARCHAR(100),
    job_function      VARCHAR(200),
    industries        VARCHAR(300),

    -- Timing
    posted_date       VARCHAR(100),
    scraped_at        TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- Quality flags
    is_relevant       BOOLEAN       NOT NULL DEFAULT TRUE
);

-- Index for fast lookups by career path (used by Module 5: Job Matching)
CREATE INDEX IF NOT EXISTS idx_linkedin_jobs_career_path
    ON linkedin_jobs (career_path);

-- Index for deduplication checks
CREATE INDEX IF NOT EXISTS idx_linkedin_jobs_url
    ON linkedin_jobs (url);

-- LinkedIn Job Skills — Extracted skills per job
-- (Populated later by LLM / regex enrichment pipeline)

CREATE TABLE IF NOT EXISTS linkedin_job_skills (
    id                SERIAL PRIMARY KEY,
    linkedin_job_id   INT           NOT NULL,
    skill_name        VARCHAR(150)  NOT NULL,

    CONSTRAINT fk_ljs_linkedin_job
        FOREIGN KEY (linkedin_job_id) REFERENCES linkedin_jobs (id)
        ON DELETE CASCADE,

    CONSTRAINT uq_job_skill UNIQUE (linkedin_job_id, skill_name)
);

CREATE INDEX IF NOT EXISTS idx_linkedin_job_skills_job_id
    ON linkedin_job_skills (linkedin_job_id);
