-- Keep the reasoning that came with each course recommendation.
--
-- The AI service returns three things per recommendation: the course, the skill it targets, and
-- a market-grounded explanation of why it was picked ("29% of postings on this path ask for
-- CI/CD, and your coursework shows no evidence of it").  Only the course survived a save, so a
-- student who came back to /courses saw a bare list of links and the page had to apologise:
-- "Which skill each one targets is not stored with them — regenerate to see that again."
--
-- Regenerating to re-read a sentence the system already produced is wasted LLM work and loses
-- the original context, since the gaps it was reasoned against have since moved.
--
-- Both columns are nullable: rows written before this migration genuinely have no reasoning,
-- and inventing one would be worse than showing none.

ALTER TABLE courses_recommendations
    ADD COLUMN targeted_skill_name VARCHAR(200) NULL;

ALTER TABLE courses_recommendations
    ADD COLUMN explanation VARCHAR(1000) NULL;
