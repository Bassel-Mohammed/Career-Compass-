-- 004: skill_type on career_path_skills
--
-- Soft skills dominate every career path. `communication skills`, `problem
-- solving` and `teamwork` rank top-3 in nearly all nine, which is an accurate
-- reading of job postings but useless for guidance: a gap dashboard that ranks
-- them first gives every student the same advice regardless of what they
-- studied or where they are headed.
--
-- The taxonomy already carries skill_type — knowledge, skill, tool, soft — but
-- the derived ontology did not surface it, so M3 had no way to rank technical
-- and soft requirements separately. This adds the column and backfills it from
-- the taxonomy.
--
-- Nullable rather than NOT NULL: a career_path_skills row can predate the
-- taxonomy entry it points at, and failing the migration over a missing type
-- would be worse than a null the gap query can treat as 'knowledge'.

ALTER TABLE career_path_skills
    ADD COLUMN IF NOT EXISTS skill_type VARCHAR(20);

UPDATE career_path_skills c
   SET skill_type = t.skill_type
  FROM taxonomy_skills t
 WHERE t.skill_id = c.skill_id
   AND c.skill_type IS DISTINCT FROM t.skill_type;

-- The gap query filters by path and ranks by score within a type, so the type
-- belongs in the existing ranking index rather than one of its own.
CREATE INDEX IF NOT EXISTS idx_career_path_skills_type
    ON career_path_skills (career_path, skill_type, required_score DESC);
