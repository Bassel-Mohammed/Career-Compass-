-- Additive, backward-compatible migration for the canonical Java/Python course identity.
-- Historical rows remain NULL because guessing a code from a display name is unsafe.
ALTER TABLE academic_records
    ADD COLUMN course_code VARCHAR(50) NULL AFTER jobseeker_id;

CREATE INDEX idx_academic_records_jobseeker_course
    ON academic_records (jobseeker_id, course_code);
