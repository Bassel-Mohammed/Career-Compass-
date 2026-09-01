package db.migration;

import org.flywaydb.core.api.migration.BaseJavaMigration;
import org.flywaydb.core.api.migration.Context;

import java.sql.Connection;
import java.sql.DatabaseMetaData;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;

/**
 * Adds canonical quiz skill identity without failing databases that already received the former
 * hand-run {@code V20260824_01} script.
 *
 * <p>MySQL does not provide a portable {@code ADD COLUMN IF NOT EXISTS} form, while H2 does. A
 * Java migration using JDBC metadata is therefore the one deterministic implementation shared by
 * both supported databases. It is deliberately limited to this legacy bridge; ordinary future
 * migrations should remain SQL.
 */
public class V2__add_quiz_skill_identity extends BaseJavaMigration {

    private static final String TABLE = "quizzes";
    private static final String COLUMN = "skill_id";
    private static final String INDEX = "idx_quizzes_jobseeker_skill";

    @Override
    public void migrate(Context context) throws Exception {
        Connection connection = context.getConnection();
        String actualTableName = findTable(connection, TABLE);

        if (!columnExists(connection, actualTableName, COLUMN)) {
            try (Statement statement = connection.createStatement()) {
                statement.execute("ALTER TABLE quizzes ADD COLUMN skill_id VARCHAR(120) NULL");
            }
        }

        if (!indexExists(connection, actualTableName, INDEX)) {
            try (Statement statement = connection.createStatement()) {
                statement.execute(
                        "CREATE INDEX idx_quizzes_jobseeker_skill ON quizzes (jobseeker_id, skill_id)");
            }
        }
    }

    /** MySQL DDL commits implicitly; Flyway must not wrap this bridge migration in a transaction. */
    @Override
    public boolean canExecuteInTransaction() {
        return false;
    }

    private static String findTable(Connection connection, String wanted) throws SQLException {
        DatabaseMetaData metadata = connection.getMetaData();
        try (ResultSet tables = metadata.getTables(connection.getCatalog(), null, null, new String[]{"TABLE"})) {
            while (tables.next()) {
                String tableName = tables.getString("TABLE_NAME");
                if (wanted.equalsIgnoreCase(tableName)) {
                    return tableName;
                }
            }
        }
        throw new SQLException("Required baseline table '" + wanted + "' does not exist");
    }

    private static boolean columnExists(Connection connection, String table, String wanted)
            throws SQLException {
        DatabaseMetaData metadata = connection.getMetaData();
        try (ResultSet columns = metadata.getColumns(connection.getCatalog(), null, table, null)) {
            while (columns.next()) {
                if (wanted.equalsIgnoreCase(columns.getString("COLUMN_NAME"))) {
                    return true;
                }
            }
        }
        return false;
    }

    private static boolean indexExists(Connection connection, String table, String wanted)
            throws SQLException {
        DatabaseMetaData metadata = connection.getMetaData();
        try (ResultSet indexes = metadata.getIndexInfo(connection.getCatalog(), null, table, false, false)) {
            while (indexes.next()) {
                String indexName = indexes.getString("INDEX_NAME");
                if (indexName != null && wanted.equalsIgnoreCase(indexName)) {
                    return true;
                }
            }
        }
        return false;
    }
}
