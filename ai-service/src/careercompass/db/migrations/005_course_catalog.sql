-- 005: catalog courses and their skills (M4)
--
-- Two tables holding the courses M4 recommends. They store deliberately
-- little.
--
-- There is NO description column, and one must not be added. Coursera states
-- the catalog copyright belongs to its university partners and the API grants
-- no licence to republish descriptions; MIT Learn mixes CC-licensed OCW
-- material with xPRO and MITx courses that are not CC. Descriptions are read
-- once to derive skill tags and dropped. The product links out, and the
-- explanation a student sees is generated from their own skill gap, not from
-- the course page.

CREATE TABLE IF NOT EXISTS catalog_courses (
    course_id         VARCHAR(200)  PRIMARY KEY,   -- "coursera:abc123"
    platform          VARCHAR(20)   NOT NULL,      -- coursera | ocw | youtube
    title             VARCHAR(400)  NOT NULL,
    url               TEXT          NOT NULL,      -- must resolve; the design
                                                   -- requires a real link
    level             VARCHAR(20),                 -- beginner|intermediate|advanced
    language          VARCHAR(20),
    duration_hours    NUMERIC(6,1),
    rating            NUMERIC(3,2),                -- absent for most sources
    fetched_at        TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS catalog_course_skills (
    id                SERIAL        PRIMARY KEY,
    course_id         VARCHAR(200)  NOT NULL,
    skill_id          VARCHAR(120)  NOT NULL,

    -- Whether the skill was named in the course TITLE rather than only in its
    -- description. A course that mentions a skill in passing is not a course
    -- about it: "HTML5: Content Authoring Fundamentals" was being offered as a
    -- way to learn Linux because its description said it runs on Linux.
    in_title          BOOLEAN       NOT NULL DEFAULT FALSE,

    CONSTRAINT fk_catalog_skill_course
        FOREIGN KEY (course_id) REFERENCES catalog_courses (course_id)
        ON DELETE CASCADE,
    CONSTRAINT fk_catalog_skill_taxonomy
        FOREIGN KEY (skill_id) REFERENCES taxonomy_skills (skill_id)
        ON DELETE CASCADE,
    CONSTRAINT uq_catalog_course_skill UNIQUE (course_id, skill_id)
);

CREATE INDEX IF NOT EXISTS idx_catalog_courses_platform
    ON catalog_courses (platform);
-- The recommender's only read path: every course for one skill, best first.
CREATE INDEX IF NOT EXISTS idx_catalog_course_skills_skill
    ON catalog_course_skills (skill_id, in_title DESC);
