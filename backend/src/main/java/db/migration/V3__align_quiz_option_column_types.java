package db.migration;

import org.flywaydb.core.api.FlywayException;
import org.flywaydb.core.api.migration.BaseJavaMigration;
import org.flywaydb.core.api.migration.Context;

import java.sql.Connection;
import java.sql.Statement;
import java.util.Locale;

/**
 * Aligns the old CHAR(1) columns with Hibernate's VARCHAR(1) String mapping.
 *
 * <p>MySQL and H2 deliberately use different ALTER COLUMN grammar. Keeping that small dialect
 * branch here lets every other migration remain ordinary portable SQL and lets @DataJpaTest use
 * a plain H2 replacement datasource, not only H2's MySQL compatibility mode.
 */
public class V3__align_quiz_option_column_types extends BaseJavaMigration {

    @Override
    public void migrate(Context context) throws Exception {
        Connection connection = context.getConnection();
        String product = connection.getMetaData().getDatabaseProductName().toLowerCase(Locale.ROOT);

        try (Statement statement = connection.createStatement()) {
            if (product.contains("mysql")) {
                statement.execute(
                        "ALTER TABLE quiz_questions MODIFY COLUMN correct_option VARCHAR(1) NOT NULL");
                statement.execute(
                        "ALTER TABLE quiz_responses MODIFY COLUMN selected_option VARCHAR(1) NOT NULL");
            } else if (product.contains("h2")) {
                statement.execute(
                        "ALTER TABLE quiz_questions ALTER COLUMN correct_option VARCHAR(1) NOT NULL");
                statement.execute(
                        "ALTER TABLE quiz_responses ALTER COLUMN selected_option VARCHAR(1) NOT NULL");
            } else {
                throw new FlywayException("Unsupported Java-owned database: " + product);
            }
        }
    }

    @Override
    public boolean canExecuteInTransaction() {
        return false;
    }
}
