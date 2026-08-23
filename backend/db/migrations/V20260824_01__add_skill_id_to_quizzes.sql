-- Canonical skill identity for quizzes (ADR-003).
--
-- FR-JS-20/21's write-back previously matched a quiz to a skill by comparing the quiz's course
-- name to the skill's name. That only held while one course mapped to exactly one
-- identically-named skill; against the real ontology it matched nothing, so quiz results
-- silently stopped refining the dashboard.
--
-- Additive and nullable: quizzes taken before this column existed have no id, and inferring one
-- from a label is exactly the guess this column removes. Those rows stay readable but cannot
-- update a skill until the quiz is re-taken.
ALTER TABLE quizzes
    ADD COLUMN skill_id VARCHAR(120) NULL AFTER course_name;

-- The write-back reads every completed quiz for one job seeker and groups by skill.
CREATE INDEX idx_quizzes_jobseeker_skill
    ON quizzes (jobseeker_id, skill_id);
