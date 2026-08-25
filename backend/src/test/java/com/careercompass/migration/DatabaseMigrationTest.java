package com.careercompass.migration;

import org.flywaydb.core.Flyway;
import org.flywaydb.core.api.MigrationVersion;
import org.junit.jupiter.api.Test;
import org.springframework.core.io.ClassPathResource;
import org.springframework.jdbc.datasource.init.ScriptUtils;

import java.sql.Connection;
import java.sql.DatabaseMetaData;
import java.sql.DriverManager;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;
import java.sql.Types;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

/**
 * Release-gate tests for the Java-owned schema lifecycle. These run the same packaged Flyway
 * migrations used by the application, not Hibernate-generated DDL.
 */
class DatabaseMigrationTest {

    @Test
    void cleanDatabaseMigratesToLatestAndEnforcesQuizIntegrity() throws Exception {
        String url = newDatabaseUrl();
        Flyway flyway = flyway(url);

        assertThat(flyway.migrate().migrationsExecuted).isEqualTo(5);
        flyway.validate();
        assertLatestShapeAndConstraints(url);
        assertThat(flyway.migrate().migrationsExecuted).isZero();
    }

    @Test
    void operatorBaselinedSchemaWithoutLegacyQuizMigrationUpgrades() throws Exception {
        String url = newDatabaseUrl();
        installUnmanagedV1(url);
        installLegacyLearningOutcome(url);

        Flyway flyway = flyway(url);
        flyway.baseline();

        assertThat(flyway.migrate().migrationsExecuted).isEqualTo(4);
        flyway.validate();
        assertLatestShapeAndConstraints(url);
        assertLegacyLearningOutcomeBackfill(url);
    }

    @Test
    void operatorBaselinedSchemaWithLegacyQuizMigrationUpgradesWithoutDuplicateColumn() throws Exception {
        String url = newDatabaseUrl();
        installUnmanagedV1(url);
        installLegacyLearningOutcome(url);
        try (Connection connection = DriverManager.getConnection(url, "sa", "");
             Statement statement = connection.createStatement()) {
            statement.execute("ALTER TABLE quizzes ADD COLUMN skill_id VARCHAR(120) NULL");
            statement.execute(
                    "CREATE INDEX idx_quizzes_jobseeker_skill ON quizzes (jobseeker_id, skill_id)");
        }

        Flyway flyway = flyway(url);
        flyway.baseline();

        assertThat(flyway.migrate().migrationsExecuted).isEqualTo(4);
        flyway.validate();
        assertLatestShapeAndConstraints(url);
        assertLegacyLearningOutcomeBackfill(url);
    }

    private static Flyway flyway(String url) {
        return Flyway.configure()
                .dataSource(url, "sa", "")
                .locations("classpath:db/migration")
                .baselineVersion(MigrationVersion.fromVersion("1"))
                .load();
    }

    private static void installUnmanagedV1(String url) throws SQLException {
        try (Connection connection = DriverManager.getConnection(url, "sa", "")) {
            ScriptUtils.executeSqlScript(
                    connection, new ClassPathResource("db/migration/V1__baseline.sql"));
        }
    }

    private static void installLegacyLearningOutcome(String url) throws SQLException {
        try (Connection connection = DriverManager.getConnection(url, "sa", "");
             Statement statement = connection.createStatement()) {
            statement.execute("""
                    INSERT INTO universities (university_id, university_name)
                    VALUES (91, 'Legacy University')
                    """);
            statement.execute("""
                    INSERT INTO study_fields (study_field_id, field_name)
                    VALUES (91, 'Legacy Computing')
                    """);
            statement.execute("""
                    INSERT INTO university_study_fields
                        (university_field_id, university_id, study_field_id)
                    VALUES (91, 91, 91)
                    """);
            statement.execute("""
                    INSERT INTO learning_outcomes
                        (outcome_id, university_field_id, course_name, file_path,
                         original_filename, uploaded_at)
                    VALUES
                        (91, 91, 'Legacy Databases', '/legacy/databases.pdf',
                         'databases.pdf', TIMESTAMP '2025-01-02 03:04:05')
                    """);
        }
    }

    private static void assertLegacyLearningOutcomeBackfill(String url) throws SQLException {
        try (Connection connection = DriverManager.getConnection(url, "sa", "");
             Statement statement = connection.createStatement();
             ResultSet row = statement.executeQuery("""
                     SELECT institution_code, catalog_version, course_code, content_sha256,
                            extraction_status, draft_revision, course_map_version, updated_at
                       FROM learning_outcomes
                      WHERE outcome_id = 91
                     """)) {
            assertThat(row.next()).isTrue();
            assertThat(row.getString("institution_code")).isEqualTo("legacy:university-field:91");
            assertThat(row.getString("catalog_version")).isEqualTo("legacy");
            assertThat(row.getString("course_code")).isEqualTo("legacy:outcome:91");
            assertThat(row.getString("content_sha256")).isNull();
            assertThat(row.getString("extraction_status")).isEqualTo("UPLOADED");
            assertThat(row.getLong("draft_revision")).isZero();
            assertThat(row.getLong("course_map_version")).isZero();
            assertThat(row.getTimestamp("updated_at")).isNotNull();
        }
    }

    private static void assertLatestShapeAndConstraints(String url) throws Exception {
        try (Connection connection = DriverManager.getConnection(url, "sa", "")) {
            assertThat(columnType(connection, "QUIZZES", "SKILL_ID")).isEqualTo(Types.VARCHAR);
            assertThat(columnType(connection, "QUIZ_QUESTIONS", "CORRECT_OPTION")).isEqualTo(Types.VARCHAR);
            assertThat(columnType(connection, "QUIZ_RESPONSES", "SELECTED_OPTION")).isEqualTo(Types.VARCHAR);
            assertThat(columnType(connection, "SKILLS", "CANONICAL_SKILL_ID")).isEqualTo(Types.VARCHAR);
            assertThat(columnType(connection, "CAREER_PATHS", "CAREER_PATH_CODE")).isEqualTo(Types.VARCHAR);
            assertThat(columnType(connection, "JOBSEEKER_SKILLS", "VECTOR_VERSION")).isEqualTo(Types.VARCHAR);
            assertThat(columnType(connection, "LEARNING_OUTCOMES", "INSTITUTION_CODE"))
                    .isEqualTo(Types.VARCHAR);
            assertThat(columnType(connection, "LEARNING_OUTCOMES", "CONTENT_SHA256"))
                    .isEqualTo(Types.CHAR);
            assertThat(columnType(connection, "LEARNING_OUTCOME_SKILL_DRAFTS", "ROW_VERSION"))
                    .isEqualTo(Types.BIGINT);
            assertThat(columnType(connection, "COURSE_SKILL_MAP_VERSIONS", "MAP_VERSION"))
                    .isEqualTo(Types.BIGINT);
            assertThat(columnType(connection, "COURSE_SKILL_MAP_ITEMS", "CANONICAL_SKILL_ID"))
                    .isEqualTo(Types.VARCHAR);
            assertThat(columnType(connection, "COURSE_SKILL_MAP_ITEMS", "EVIDENCE_COUNT"))
                    .isEqualTo(Types.INTEGER);

            try (Statement statement = connection.createStatement()) {
                statement.execute("""
                        INSERT INTO job_seekers
                            (jobseeker_id, first_name, last_name, email, password_hash)
                        VALUES (1, 'Test', 'Student', 'migration@test.local', 'not-a-real-hash')
                        """);
                statement.execute("""
                        INSERT INTO quizzes
                            (quiz_id, jobseeker_id, course_name, skill_id, score)
                        VALUES (1, 1, 'Databases', 'custom:databases', 50.00)
                        """);
                statement.execute("""
                        INSERT INTO quiz_questions
                            (question_id, quiz_id, question_text, option_a, option_b, option_c,
                             option_d, correct_option)
                        VALUES (1, 1, 'Question?', 'A', 'B', 'C', 'D', 'A')
                        """);
                statement.execute("""
                        INSERT INTO quiz_responses
                            (response_id, question_id, selected_option, is_correct)
                        VALUES (1, 1, 'A', TRUE)
                        """);

                assertThatThrownBy(() -> statement.execute("""
                        INSERT INTO quiz_responses
                            (response_id, question_id, selected_option, is_correct)
                        VALUES (2, 1, 'B', FALSE)
                        """))
                        .isInstanceOf(SQLException.class);

                assertThatThrownBy(() -> statement.execute(
                        "UPDATE quizzes SET score = 101.00 WHERE quiz_id = 1"))
                        .isInstanceOf(SQLException.class);

                statement.execute("INSERT INTO levels (level_id, level_name) VALUES (1, 'Test')");
                statement.execute("""
                        INSERT INTO skills
                            (skill_id, skill_name, canonical_skill_id, taxonomy_version)
                        VALUES (1, 'Databases', 'custom:databases', 'taxonomy-test-v1')
                        """);
                assertThatThrownBy(() -> statement.execute("""
                        INSERT INTO jobseeker_skills
                            (jobseeker_id, skill_id, level_id, score)
                        VALUES (1, 1, 1, -0.01)
                        """))
                        .isInstanceOf(SQLException.class);
                assertThatThrownBy(() -> statement.execute("""
                        INSERT INTO skills
                            (skill_id, skill_name, canonical_skill_id)
                        VALUES (2, 'Relational Databases', 'custom:databases')
                        """))
                        .isInstanceOf(SQLException.class);

                statement.execute("""
                        INSERT INTO career_paths
                            (career_path_id, title, career_path_code)
                        VALUES (1, 'Backend', 'career:backend')
                        """);
                assertThatThrownBy(() -> statement.execute("""
                        INSERT INTO career_paths
                            (career_path_id, title, career_path_code)
                        VALUES (2, 'Backend renamed', 'career:backend')
                        """))
                        .isInstanceOf(SQLException.class);

                statement.execute("""
                        INSERT INTO employers
                            (employer_id, company_name, email, password_hash)
                        VALUES (1, 'Test Company', 'employer@test.local', 'not-a-real-hash')
                        """);
                statement.execute("""
                        INSERT INTO jobs (job_id, employer_id, title)
                        VALUES (1, 1, 'Database Engineer')
                        """);
                assertThatThrownBy(() -> statement.execute("""
                        INSERT INTO job_matches (job_id, jobseeker_id, match_score)
                        VALUES (1, 1, 100.01)
                        """))
                        .isInstanceOf(SQLException.class);

                statement.execute("""
                        INSERT INTO universities (university_id, university_name)
                        VALUES (1, 'Migration University')
                        """);
                statement.execute("""
                        INSERT INTO study_fields (study_field_id, field_name)
                        VALUES (1, 'Migration Computing')
                        """);
                statement.execute("""
                        INSERT INTO content_managers
                            (content_manager_id, first_name, last_name, email, password_hash,
                             university_id)
                        VALUES
                            (1, 'Content', 'Manager', 'content@test.local', 'not-a-real-hash', 1)
                        """);
                statement.execute("""
                        INSERT INTO university_study_fields
                            (university_field_id, university_id, study_field_id)
                        VALUES (1, 1, 1)
                        """);
                statement.execute("""
                        INSERT INTO learning_outcomes
                            (outcome_id, university_field_id, course_name, file_path,
                             original_filename, uploaded_by_content_manager_id,
                             institution_code, catalog_version, course_code, content_sha256,
                             extraction_status)
                        VALUES
                            (1, 1, 'Database Systems', '/test/database.pdf', 'database.pdf', 1,
                             'meu', '2026', 'CS301',
                             'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
                             'READY_FOR_REVIEW')
                        """);
                statement.execute("""
                        INSERT INTO learning_outcome_skill_drafts
                            (draft_skill_id, outcome_id, term, canonical_skill_id,
                             canonical_label, level, weight, evidence_count,
                             ai_review_status, decision)
                        VALUES
                            (1, 1, 'relational databases', 'custom:relational-databases',
                             'Relational databases', 'advanced', 0.7500, 3,
                             'accepted', 'ACCEPTED')
                        """);

                assertThatThrownBy(() -> statement.execute("""
                        INSERT INTO learning_outcome_skill_drafts
                            (draft_skill_id, outcome_id, term, level, weight)
                        VALUES (2, 1, 'invalid weight', 'beginner', 1.0001)
                        """))
                        .isInstanceOf(SQLException.class);

                statement.execute("""
                        INSERT INTO course_skill_map_versions
                            (map_id, institution_code, catalog_version, course_code, map_version,
                             state, approved_by_content_manager_id, source_outcome_id, checksum)
                        VALUES
                            (1, 'meu', '2026', 'CS301', 1, 'PUBLISHED', 1, 1,
                             'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb')
                        """);
                statement.execute("""
                        INSERT INTO course_skill_map_items
                            (map_item_id, map_id, source_draft_skill_id, term,
                             canonical_skill_id, canonical_label, level, weight)
                        VALUES
                            (1, 1, 1, 'relational databases', 'custom:relational-databases',
                             'Relational databases', 'advanced', 0.7500)
                        """);

                assertThatThrownBy(() -> statement.execute("""
                        INSERT INTO course_skill_map_items
                            (map_item_id, map_id, term, canonical_skill_id,
                             canonical_label, level, weight)
                        VALUES
                            (2, 1, 'duplicate label', 'custom:relational-databases',
                             'Renamed databases', 'advanced', 0.5000)
                        """))
                        .isInstanceOf(SQLException.class);

                assertThatThrownBy(() -> statement.execute("""
                        INSERT INTO course_skill_map_versions
                            (map_id, institution_code, catalog_version, course_code, map_version,
                             state, source_outcome_id, checksum)
                        VALUES
                            (2, 'meu', '2026', 'CS301', 1, 'PUBLISHING', 1,
                             'cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc')
                        """))
                        .isInstanceOf(SQLException.class);
            }
        }
    }

    private static int columnType(Connection connection, String table, String column) throws SQLException {
        DatabaseMetaData metadata = connection.getMetaData();
        try (ResultSet columns = metadata.getColumns(connection.getCatalog(), null, table, column)) {
            assertThat(columns.next())
                    .as("column %s.%s exists", table, column)
                    .isTrue();
            return columns.getInt("DATA_TYPE");
        }
    }

    private static String newDatabaseUrl() {
        return "jdbc:h2:mem:migration_" + UUID.randomUUID()
                + ";DB_CLOSE_DELAY=-1;MODE=MySQL";
    }
}
