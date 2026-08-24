"""Command-line entry point for applying the AI PostgreSQL schema."""

from careercompass.db.connection import apply_migrations, discover_migrations


def main() -> None:
    migrations = discover_migrations()
    applied = apply_migrations()
    if applied:
        print("Applied: " + ", ".join(migration.filename for migration in applied))
    else:
        print(f"Schema is current at {migrations[-1].filename}")


if __name__ == "__main__":
    main()
