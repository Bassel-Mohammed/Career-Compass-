CREATE TABLE administrators (
    admin_id        INT AUTO_INCREMENT PRIMARY KEY,
    first_name      VARCHAR(100) NOT NULL,
    last_name       VARCHAR(100) NOT NULL,
    email           VARCHAR(255) NOT NULL UNIQUE,
    password_hash   VARCHAR(255) NOT NULL,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE study_fields (
    study_field_id       INT AUTO_INCREMENT PRIMARY KEY,
    field_name           VARCHAR(150) NOT NULL UNIQUE,
    created_by_admin_id  INT NULL,
    CONSTRAINT fk_studyfield_admin
        FOREIGN KEY (created_by_admin_id) REFERENCES administrators(admin_id)
        ON DELETE SET NULL
);

CREATE TABLE career_paths (
    career_path_id      INT AUTO_INCREMENT PRIMARY KEY,
    title                VARCHAR(150) NOT NULL,
    description          TEXT,
    created_by_admin_id  INT NULL,
    created_at           TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_careerpath_admin
        FOREIGN KEY (created_by_admin_id) REFERENCES administrators(admin_id)
        ON DELETE SET NULL
);

CREATE TABLE career_path_study_fields (
    career_path_id  INT NOT NULL,
    study_field_id  INT NOT NULL,
    PRIMARY KEY (career_path_id, study_field_id),
    CONSTRAINT fk_cpsf_careerpath
        FOREIGN KEY (career_path_id) REFERENCES career_paths(career_path_id)
        ON DELETE CASCADE,
    CONSTRAINT fk_cpsf_studyfield
        FOREIGN KEY (study_field_id) REFERENCES study_fields(study_field_id)
        ON DELETE CASCADE
);

CREATE TABLE universities (
    university_id     INT AUTO_INCREMENT PRIMARY KEY,
    university_name   VARCHAR(200) NOT NULL,
    created_by_admin_id INT NULL,
    created_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_university_admin
        FOREIGN KEY (created_by_admin_id) REFERENCES administrators(admin_id)
        ON DELETE SET NULL
);

CREATE TABLE content_managers (
    content_manager_id  INT AUTO_INCREMENT PRIMARY KEY,
    first_name           VARCHAR(100) NOT NULL,
    last_name             VARCHAR(100) NOT NULL,
    email                 VARCHAR(255) NOT NULL UNIQUE,
    password_hash         VARCHAR(255) NOT NULL,
    university_id         INT NOT NULL,
    study_field_id         INT NULL,
    is_active              BOOLEAN NOT NULL DEFAULT TRUE,
    created_by_admin_id    INT NULL,
    created_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_cm_university
        FOREIGN KEY (university_id) REFERENCES universities(university_id)
        ON DELETE CASCADE,
    CONSTRAINT fk_cm_studyfield
        FOREIGN KEY (study_field_id) REFERENCES study_fields(study_field_id)
        ON DELETE SET NULL,
    CONSTRAINT fk_cm_admin
        FOREIGN KEY (created_by_admin_id) REFERENCES administrators(admin_id)
        ON DELETE SET NULL
);

CREATE TABLE university_study_fields (
    university_field_id  INT AUTO_INCREMENT PRIMARY KEY,
    university_id          INT NOT NULL,
    study_field_id          INT NOT NULL,
    degree_level             VARCHAR(50),
    duration_years            DECIMAL(3,1),
    CONSTRAINT uq_university_field UNIQUE (university_id, study_field_id),
    CONSTRAINT fk_usf_university
        FOREIGN KEY (university_id) REFERENCES universities(university_id)
        ON DELETE CASCADE,
    CONSTRAINT fk_usf_studyfield
        FOREIGN KEY (study_field_id) REFERENCES study_fields(study_field_id)
        ON DELETE CASCADE
);

CREATE TABLE learning_outcomes (
    outcome_id             INT AUTO_INCREMENT PRIMARY KEY,
    university_field_id     INT NOT NULL,
    course_name               VARCHAR(200) NOT NULL,
    description                 TEXT,
    file_path                     VARCHAR(500) NOT NULL,
    original_filename                VARCHAR(255) NOT NULL,
    is_deleted_from_disk                BOOLEAN NOT NULL DEFAULT FALSE,
    uploaded_by_content_manager_id INT NULL,
    uploaded_at                       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_lo_usf
        FOREIGN KEY (university_field_id) REFERENCES university_study_fields(university_field_id)
        ON DELETE CASCADE,
    CONSTRAINT fk_lo_cm
        FOREIGN KEY (uploaded_by_content_manager_id) REFERENCES content_managers(content_manager_id)
        ON DELETE SET NULL
);

CREATE TABLE job_seekers (
    jobseeker_id     INT AUTO_INCREMENT PRIMARY KEY,
    first_name         VARCHAR(100) NOT NULL,
    last_name            VARCHAR(100) NOT NULL,
    email                 VARCHAR(255) NOT NULL UNIQUE,
    password_hash         VARCHAR(255) NOT NULL,
    university_id          INT NULL,
    study_field_id          INT NULL,
    career_path_id          INT NULL,
    created_at               TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_login_at             TIMESTAMP NULL,
    CONSTRAINT fk_js_university
        FOREIGN KEY (university_id) REFERENCES universities(university_id)
        ON DELETE SET NULL,
    CONSTRAINT fk_js_studyfield
        FOREIGN KEY (study_field_id) REFERENCES study_fields(study_field_id)
        ON DELETE SET NULL,
    CONSTRAINT fk_js_careerpath
        FOREIGN KEY (career_path_id) REFERENCES career_paths(career_path_id)
        ON DELETE SET NULL
);

CREATE TABLE academic_records (
    record_id      INT AUTO_INCREMENT PRIMARY KEY,
    jobseeker_id     INT NOT NULL,
    course_name        VARCHAR(200) NOT NULL,
    grade                VARCHAR(10) NOT NULL,
    extracted_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_ar_jobseeker
        FOREIGN KEY (jobseeker_id) REFERENCES job_seekers(jobseeker_id)
        ON DELETE CASCADE
);

CREATE TABLE courses_recommendations (
    recommendation_id  INT AUTO_INCREMENT PRIMARY KEY,
    jobseeker_id          INT NOT NULL,
    course_name             VARCHAR(200) NOT NULL,
    source_link               VARCHAR(500),
    recommended_at             TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_cr_jobseeker
        FOREIGN KEY (jobseeker_id) REFERENCES job_seekers(jobseeker_id)
        ON DELETE CASCADE
);

CREATE TABLE quizzes (
    quiz_id       INT AUTO_INCREMENT PRIMARY KEY,
    jobseeker_id    INT NOT NULL,
    course_name       VARCHAR(200) NOT NULL,
    generated_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    score                 DECIMAL(5,2),
    taken_at                TIMESTAMP NULL,
    CONSTRAINT fk_quiz_jobseeker
        FOREIGN KEY (jobseeker_id) REFERENCES job_seekers(jobseeker_id)
        ON DELETE CASCADE
);

CREATE TABLE quiz_questions (
    question_id     INT AUTO_INCREMENT PRIMARY KEY,
    quiz_id           INT NOT NULL,
    question_text       TEXT NOT NULL,
    option_a               VARCHAR(300) NOT NULL,
    option_b               VARCHAR(300) NOT NULL,
    option_c               VARCHAR(300) NOT NULL,
    option_d               VARCHAR(300) NOT NULL,
    correct_option           CHAR(1) NOT NULL,
    CONSTRAINT chk_correct_option CHECK (correct_option IN ('A','B','C','D')),
    CONSTRAINT fk_qq_quiz
        FOREIGN KEY (quiz_id) REFERENCES quizzes(quiz_id)
        ON DELETE CASCADE
);

CREATE TABLE quiz_responses (
    response_id       INT AUTO_INCREMENT PRIMARY KEY,
    question_id         INT NOT NULL,
    selected_option        CHAR(1) NOT NULL,
    is_correct               BOOLEAN NOT NULL,
    answered_at                TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_selected_option CHECK (selected_option IN ('A','B','C','D')),
    CONSTRAINT fk_qr_question
        FOREIGN KEY (question_id) REFERENCES quiz_questions(question_id)
        ON DELETE CASCADE
);

CREATE TABLE skills (
    skill_id     INT AUTO_INCREMENT PRIMARY KEY,
    skill_name     VARCHAR(150) NOT NULL UNIQUE
);

CREATE TABLE levels (
    level_id    INT AUTO_INCREMENT PRIMARY KEY,
    level_name    VARCHAR(50) NOT NULL UNIQUE
);

CREATE TABLE jobseeker_skills (
    jobseeker_id   INT NOT NULL,
    skill_id         INT NOT NULL,
    level_id           INT NOT NULL,
    score                 DECIMAL(5,2),
    updated_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (jobseeker_id, skill_id),
    CONSTRAINT fk_js_skill_jobseeker
        FOREIGN KEY (jobseeker_id) REFERENCES job_seekers(jobseeker_id)
        ON DELETE CASCADE,
    CONSTRAINT fk_js_skill_skill
        FOREIGN KEY (skill_id) REFERENCES skills(skill_id)
        ON DELETE CASCADE,
    CONSTRAINT fk_js_skill_level
        FOREIGN KEY (level_id) REFERENCES levels(level_id)
        ON DELETE RESTRICT
);

CREATE TABLE employers (
    employer_id           INT AUTO_INCREMENT PRIMARY KEY,
    company_name             VARCHAR(200) NOT NULL,
    industry                   VARCHAR(150),
    email                         VARCHAR(255) NOT NULL UNIQUE,
    password_hash                   VARCHAR(255) NOT NULL,
    company_description                TEXT,
    created_at                            TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE jobs (
    job_id            INT AUTO_INCREMENT PRIMARY KEY,
    employer_id          INT NOT NULL,
    study_field_id          INT NULL,
    title                       VARCHAR(200) NOT NULL,
    description                    TEXT,
    required_skills                    TEXT,
    posted_at                              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_active                                  BOOLEAN NOT NULL DEFAULT TRUE,
    CONSTRAINT fk_job_employer
        FOREIGN KEY (employer_id) REFERENCES employers(employer_id)
        ON DELETE CASCADE,
    CONSTRAINT fk_job_studyfield
        FOREIGN KEY (study_field_id) REFERENCES study_fields(study_field_id)
        ON DELETE SET NULL
);

CREATE TABLE job_skills (
    job_id     INT NOT NULL,
    skill_id     INT NOT NULL,
    PRIMARY KEY (job_id, skill_id),
    CONSTRAINT fk_jobskill_job
        FOREIGN KEY (job_id) REFERENCES jobs(job_id)
        ON DELETE CASCADE,
    CONSTRAINT fk_jobskill_skill
        FOREIGN KEY (skill_id) REFERENCES skills(skill_id)
        ON DELETE CASCADE
);

CREATE TABLE job_matches (
    job_id         INT NOT NULL,
    jobseeker_id     INT NOT NULL,
    match_score        DECIMAL(5,2) NOT NULL,
    matched_at            TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (job_id, jobseeker_id),
    CONSTRAINT fk_match_job
        FOREIGN KEY (job_id) REFERENCES jobs(job_id)
        ON DELETE CASCADE,
    CONSTRAINT fk_match_jobseeker
        FOREIGN KEY (jobseeker_id) REFERENCES job_seekers(jobseeker_id)
        ON DELETE CASCADE
);

CREATE TABLE expert_statuses (
    status_id     INT AUTO_INCREMENT PRIMARY KEY,
    status_name     VARCHAR(50) NOT NULL UNIQUE
);

CREATE TABLE experts (
    expert_id             INT AUTO_INCREMENT PRIMARY KEY,
    first_name               VARCHAR(100) NOT NULL,
    last_name                   VARCHAR(100) NOT NULL,
    email                         VARCHAR(255) NOT NULL UNIQUE,
    password_hash                   VARCHAR(255) NOT NULL,
    study_field_id                     INT NULL,
    field_starting_year                   SMALLINT NOT NULL,
    status_id                                     INT NOT NULL,
    created_by_admin_id                              INT NULL,
    CONSTRAINT fk_expert_studyfield
        FOREIGN KEY (study_field_id) REFERENCES study_fields(study_field_id)
        ON DELETE SET NULL,
    CONSTRAINT fk_expert_status
        FOREIGN KEY (status_id) REFERENCES expert_statuses(status_id)
        ON DELETE RESTRICT,
    CONSTRAINT fk_expert_admin
        FOREIGN KEY (created_by_admin_id) REFERENCES administrators(admin_id)
        ON DELETE SET NULL
);

CREATE TABLE expert_availability (
    availability_id   INT AUTO_INCREMENT PRIMARY KEY,
    expert_id           INT NOT NULL,
    day_of_week            TINYINT NOT NULL,
    start_time                TIME NOT NULL,
    end_time                    TIME NOT NULL,
    CONSTRAINT chk_day_of_week CHECK (day_of_week BETWEEN 1 AND 7),
    CONSTRAINT chk_time_range CHECK (start_time < end_time),
    CONSTRAINT fk_avail_expert
        FOREIGN KEY (expert_id) REFERENCES experts(expert_id)
        ON DELETE CASCADE
);

CREATE TABLE appointment_statuses (
    status_id     INT AUTO_INCREMENT PRIMARY KEY,
    status_name     VARCHAR(50) NOT NULL UNIQUE
);

CREATE TABLE appointments (
    appointment_id     INT AUTO_INCREMENT PRIMARY KEY,
    expert_id             INT NOT NULL,
    jobseeker_id             INT NOT NULL,
    appointment_date            TIMESTAMP NOT NULL,
    status_id                       INT NOT NULL,
    session_notes                       TEXT,
    feedback                                TEXT,
    created_at                                  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_appt_expert
        FOREIGN KEY (expert_id) REFERENCES experts(expert_id)
        ON DELETE CASCADE,
    CONSTRAINT fk_appt_jobseeker
        FOREIGN KEY (jobseeker_id) REFERENCES job_seekers(jobseeker_id)
        ON DELETE CASCADE,
    CONSTRAINT fk_appt_status
        FOREIGN KEY (status_id) REFERENCES appointment_statuses(status_id)
        ON DELETE RESTRICT
);