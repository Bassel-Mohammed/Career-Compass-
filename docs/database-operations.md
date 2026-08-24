# Database ownership and migration operations

CareerCompass deliberately uses two databases. They are not two migration
systems for the same schema and their migrations must never be pointed at the
same database.

| Owner | Engine | Authoritative data |
| --- | --- | --- |
| Java backend | MySQL (H2 in local development/tests) | Users, transcripts, jobs, quizzes, approved course mappings, and business records |
| Python AI service | PostgreSQL | Taxonomy/catalog indexes, extraction results, review work queues, and other rebuildable computation state |

Both databases contain a table named `job_skills`, but with intentionally
different meanings and incompatible columns. Separate database names and
credentials are a deployment requirement, not merely a convention.

## PostgreSQL backup procedure

Backups may contain sensitive data. Keep them outside source control, create
them with owner-only permissions, and record a checksum before any migration.
The repository ignores `backups/` for this reason.

```bash
install -d -m 700 backups/postgresql
umask 077
pg_dump --format=custom --compress=9 \
  --host="$CC_DB_HOST" --port="$CC_DB_PORT" \
  --username="$CC_DB_USER" --dbname="$CC_DB_NAME" \
  --file="backups/postgresql/${CC_DB_NAME}_YYYYMMDDTHHMMSSZ.dump"
pg_restore --list "backups/postgresql/${CC_DB_NAME}_YYYYMMDDTHHMMSSZ.dump" >/dev/null
sha256sum "backups/postgresql/${CC_DB_NAME}_YYYYMMDDTHHMMSSZ.dump"
```

`PGPASSWORD` or a protected PostgreSQL password file may supply credentials;
never put a password in a command, script, log, or tracked environment file.

## Safe AI upgrade rehearsal

Never use the source database as the rehearsal target.

1. Confirm an explicitly named disposable database does not already exist.
2. Create that database and restore the custom-format backup with
   `pg_restore --no-owner --no-privileges --exit-on-error`.
3. Point only the AI migration command at the disposable database.
4. Run `cc-db-migrate` twice: the first run applies pending migrations and the
   second must report that the schema is current.
5. Verify the migration-history rows, expected columns/tables, foreign keys,
   and representative row counts before scheduling a live change.

The AI migration runner applies the complete packaged chain in numeric order,
uses a PostgreSQL advisory lock, and rejects changed checksums. Never invoke an
individual migration out of sequence.

## Backend migration policy

Flyway owns Java schema changes; Hibernate validates them. Hibernate
`ddl-auto=update` is not an accepted schema-management path. A populated
database that predates Flyway must be inspected and explicitly baselined at V1
by an operator before the application starts. An empty database runs the V1
baseline and every later migration normally.

Release checks must cover both an empty installation and an upgrade from the
supported legacy shape. Production should run migrations using a credential
that can alter the Java schema, then run the application with its normal
least-privilege credential where practical.
