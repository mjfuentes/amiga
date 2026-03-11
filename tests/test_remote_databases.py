"""Tests for remote database detection in projects/scanner.py."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from projects.scanner import (
    _detect_remote_databases,
    _extract_columns_from_create,
    _find_env_var_names,
    _parse_sql_migrations,
    _split_respecting_parens,
    scan_project,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write(path: Path, content: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


# ---------------------------------------------------------------------------
# SQL migration parsing tests
# ---------------------------------------------------------------------------


class TestParseSqlMigrations:
    def test_basic_create_table(self, tmp_path: Path) -> None:
        migrations = tmp_path / "migrations"
        migrations.mkdir()
        _write(
            migrations / "001_initial.sql",
            """
            CREATE TABLE users (
                id UUID PRIMARY KEY,
                name TEXT NOT NULL,
                email TEXT,
                created_at TIMESTAMPTZ DEFAULT NOW()
            );
            """,
        )
        tables = _parse_sql_migrations(migrations)
        assert len(tables) == 1
        assert tables[0]["name"] == "users"
        cols = {c["name"]: c["type"] for c in tables[0]["columns"]}
        assert cols["id"] == "UUID"
        assert cols["name"] == "TEXT"
        assert cols["email"] == "TEXT"
        assert cols["created_at"] == "TIMESTAMPTZ"

    def test_create_table_if_not_exists(self, tmp_path: Path) -> None:
        migrations = tmp_path / "migrations"
        migrations.mkdir()
        _write(
            migrations / "001.sql",
            """
            CREATE TABLE IF NOT EXISTS events (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                name TEXT NOT NULL,
                date TIMESTAMPTZ NOT NULL,
                venue TEXT NOT NULL
            );
            """,
        )
        tables = _parse_sql_migrations(migrations)
        assert len(tables) == 1
        assert tables[0]["name"] == "events"
        assert len(tables[0]["columns"]) == 4

    def test_multiple_tables_single_file(self, tmp_path: Path) -> None:
        migrations = tmp_path / "migrations"
        migrations.mkdir()
        _write(
            migrations / "001.sql",
            """
            CREATE TABLE users (
                id INTEGER PRIMARY KEY,
                name TEXT
            );

            CREATE TABLE orders (
                id INTEGER PRIMARY KEY,
                user_id INTEGER,
                total REAL
            );
            """,
        )
        tables = _parse_sql_migrations(migrations)
        assert len(tables) == 2
        table_names = {t["name"] for t in tables}
        assert table_names == {"users", "orders"}

    def test_multiple_migration_files(self, tmp_path: Path) -> None:
        migrations = tmp_path / "migrations"
        migrations.mkdir()
        _write(
            migrations / "001_users.sql",
            "CREATE TABLE users (id UUID PRIMARY KEY, name TEXT);",
        )
        _write(
            migrations / "002_posts.sql",
            "CREATE TABLE posts (id UUID PRIMARY KEY, title TEXT, user_id UUID);",
        )
        tables = _parse_sql_migrations(migrations)
        assert len(tables) == 2

    def test_alter_table_add_column(self, tmp_path: Path) -> None:
        migrations = tmp_path / "migrations"
        migrations.mkdir()
        _write(
            migrations / "001.sql",
            "CREATE TABLE releases (id UUID PRIMARY KEY, title TEXT);",
        )
        _write(
            migrations / "002.sql",
            """
            ALTER TABLE releases ADD COLUMN IF NOT EXISTS artist_name TEXT;
            ALTER TABLE releases ADD COLUMN status TEXT;
            """,
        )
        tables = _parse_sql_migrations(migrations)
        assert len(tables) == 1
        cols = {c["name"] for c in tables[0]["columns"]}
        assert "artist_name" in cols
        assert "status" in cols
        assert "id" in cols
        assert "title" in cols

    def test_alter_table_no_duplicate_columns(self, tmp_path: Path) -> None:
        migrations = tmp_path / "migrations"
        migrations.mkdir()
        _write(
            migrations / "001.sql",
            "CREATE TABLE t (id UUID PRIMARY KEY, name TEXT);",
        )
        _write(
            migrations / "002.sql",
            "ALTER TABLE t ADD COLUMN name TEXT;",
        )
        tables = _parse_sql_migrations(migrations)
        name_cols = [c for c in tables[0]["columns"] if c["name"] == "name"]
        assert len(name_cols) == 1

    def test_skips_constraints(self, tmp_path: Path) -> None:
        migrations = tmp_path / "migrations"
        migrations.mkdir()
        _write(
            migrations / "001.sql",
            """
            CREATE TABLE items (
                id UUID PRIMARY KEY,
                name TEXT NOT NULL,
                price INTEGER CHECK (price > 0),
                UNIQUE(name),
                CONSTRAINT fk_cat FOREIGN KEY (cat_id) REFERENCES cats(id)
            );
            """,
        )
        tables = _parse_sql_migrations(migrations)
        col_names = {c["name"] for c in tables[0]["columns"]}
        assert "id" in col_names
        assert "name" in col_names
        assert "price" in col_names
        # Constraints should not appear as columns
        assert "UNIQUE" not in col_names
        assert "CONSTRAINT" not in col_names

    def test_handles_check_constraints_in_columns(self, tmp_path: Path) -> None:
        """Column with CHECK (status IN ('a', 'b')) should parse correctly."""
        migrations = tmp_path / "migrations"
        migrations.mkdir()
        _write(
            migrations / "001.sql",
            """
            CREATE TABLE submissions (
                id UUID PRIMARY KEY,
                status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected')),
                genre TEXT NOT NULL CHECK (genre IN ('house', 'techno'))
            );
            """,
        )
        tables = _parse_sql_migrations(migrations)
        assert len(tables) == 1
        col_names = {c["name"] for c in tables[0]["columns"]}
        assert "id" in col_names
        assert "status" in col_names
        assert "genre" in col_names

    def test_handles_sql_comments(self, tmp_path: Path) -> None:
        migrations = tmp_path / "migrations"
        migrations.mkdir()
        _write(
            migrations / "001.sql",
            """
            -- This is a comment
            CREATE TABLE data (
                id INTEGER PRIMARY KEY, -- inline comment
                value TEXT
            );
            """,
        )
        tables = _parse_sql_migrations(migrations)
        assert len(tables) == 1
        assert tables[0]["name"] == "data"

    def test_nonexistent_dir(self) -> None:
        tables = _parse_sql_migrations(Path("/nonexistent/migrations"))
        assert tables == []

    def test_empty_dir(self, tmp_path: Path) -> None:
        migrations = tmp_path / "migrations"
        migrations.mkdir()
        tables = _parse_sql_migrations(migrations)
        assert tables == []

    def test_non_sql_files_ignored(self, tmp_path: Path) -> None:
        migrations = tmp_path / "migrations"
        migrations.mkdir()
        _write(migrations / "README.md", "# Migrations")
        _write(migrations / "001.sql", "CREATE TABLE t (id INTEGER);")
        tables = _parse_sql_migrations(migrations)
        assert len(tables) == 1


class TestSplitRespectingParens:
    def test_simple(self) -> None:
        parts = _split_respecting_parens("a, b, c")
        assert len(parts) == 3
        assert parts[0].strip() == "a"

    def test_nested_parens(self) -> None:
        parts = _split_respecting_parens("id UUID, status TEXT CHECK (status IN ('a', 'b'))")
        assert len(parts) == 2

    def test_empty(self) -> None:
        parts = _split_respecting_parens("")
        # Empty string produces empty list or single empty string
        assert len(parts) <= 1


class TestExtractColumnsFromCreate:
    def test_basic(self) -> None:
        sql = "(id UUID PRIMARY KEY, name TEXT NOT NULL, age INTEGER)"
        cols = _extract_columns_from_create(sql, 1)
        assert len(cols) == 3
        assert cols[0]["name"] == "id"
        assert cols[0]["type"] == "UUID"

    def test_unmatched_parens(self) -> None:
        sql = "(id UUID PRIMARY KEY, name TEXT"
        cols = _extract_columns_from_create(sql, 1)
        assert cols == []


# ---------------------------------------------------------------------------
# Env var parsing tests
# ---------------------------------------------------------------------------


class TestFindEnvVarNames:
    def test_basic(self, tmp_path: Path) -> None:
        _write(
            tmp_path / ".env",
            "SUPABASE_URL=https://example.supabase.co\nSUPABASE_KEY=secret\n",
        )
        names = _find_env_var_names(tmp_path / ".env")
        assert "SUPABASE_URL" in names
        assert "SUPABASE_KEY" in names

    def test_skips_comments_and_empty(self, tmp_path: Path) -> None:
        _write(
            tmp_path / ".env",
            "# comment\n\nAPI_KEY=abc\n  \n# another comment\n",
        )
        names = _find_env_var_names(tmp_path / ".env")
        assert names == {"API_KEY"}

    def test_nonexistent_file(self, tmp_path: Path) -> None:
        names = _find_env_var_names(tmp_path / ".env.missing")
        assert names == set()


# ---------------------------------------------------------------------------
# Remote database detection tests
# ---------------------------------------------------------------------------


class TestDetectRemoteDatabases:
    def test_no_remote_dbs(self, tmp_path: Path) -> None:
        _write(tmp_path / "app.py", "print('hello')")
        result = _detect_remote_databases(tmp_path)
        assert result == []

    def test_supabase_from_directory(self, tmp_path: Path) -> None:
        """Detect Supabase from supabase/ directory with migrations."""
        migrations = tmp_path / "supabase" / "migrations"
        migrations.mkdir(parents=True)
        _write(
            migrations / "001.sql",
            "CREATE TABLE users (id UUID PRIMARY KEY, name TEXT, email TEXT);",
        )
        _write(tmp_path / ".env", "NEXT_PUBLIC_SUPABASE_URL=https://x.supabase.co\n")

        result = _detect_remote_databases(tmp_path)
        assert len(result) == 1
        assert result[0]["type"] == "supabase"
        assert result[0]["config_path"] == "supabase/"
        assert result[0]["migrations_path"] == "supabase/migrations/"
        assert len(result[0]["tables"]) == 1
        assert result[0]["tables"][0]["name"] == "users"
        assert "NEXT_PUBLIC_SUPABASE_URL" in result[0]["env_vars"]

    def test_supabase_in_subdirectory(self, tmp_path: Path) -> None:
        """Detect Supabase in a nested subdirectory like website/."""
        website = tmp_path / "website"
        migrations = website / "supabase" / "migrations"
        migrations.mkdir(parents=True)
        _write(
            migrations / "001.sql",
            "CREATE TABLE posts (id UUID PRIMARY KEY, title TEXT);",
        )
        _write(website / ".env.local", "NEXT_PUBLIC_SUPABASE_URL=https://x.supabase.co\nSUPABASE_SERVICE_ROLE_KEY=secret\n")
        pkg = {"dependencies": {"@supabase/supabase-js": "^2.0.0"}}
        _write(website / "package.json", json.dumps(pkg))

        result = _detect_remote_databases(tmp_path)
        assert len(result) == 1
        assert result[0]["type"] == "supabase"
        assert "website/supabase/" in result[0]["config_path"]
        assert len(result[0]["tables"]) == 1

    def test_supabase_from_package_json_only(self, tmp_path: Path) -> None:
        """Detect Supabase from package.json dependency alone."""
        pkg = {"dependencies": {"@supabase/supabase-js": "^2.0.0"}}
        _write(tmp_path / "package.json", json.dumps(pkg))

        result = _detect_remote_databases(tmp_path)
        assert len(result) == 1
        assert result[0]["type"] == "supabase"
        assert "tables" not in result[0]  # No migrations dir

    def test_firebase_detection(self, tmp_path: Path) -> None:
        _write(tmp_path / "firebase.json", '{"hosting": {}}')
        _write(tmp_path / ".env", "FIREBASE_API_KEY=abc\nFIREBASE_PROJECT_ID=my-project\n")

        result = _detect_remote_databases(tmp_path)
        assert len(result) == 1
        assert result[0]["type"] == "firebase"
        assert "FIREBASE_API_KEY" in result[0]["env_vars"]
        assert "note" in result[0]

    def test_firebase_from_package_json(self, tmp_path: Path) -> None:
        pkg = {"dependencies": {"firebase": "^10.0.0"}}
        _write(tmp_path / "package.json", json.dumps(pkg))

        result = _detect_remote_databases(tmp_path)
        assert len(result) == 1
        assert result[0]["type"] == "firebase"

    def test_postgresql_detection(self, tmp_path: Path) -> None:
        _write(tmp_path / ".env", "DATABASE_URL=postgresql://localhost/mydb\n")
        _write(tmp_path / "requirements.txt", "psycopg2-binary==2.9\n")

        result = _detect_remote_databases(tmp_path)
        assert len(result) == 1
        assert result[0]["type"] == "postgresql"
        assert "DATABASE_URL" in result[0]["env_vars"]

    def test_postgresql_from_js_deps(self, tmp_path: Path) -> None:
        pkg = {"dependencies": {"pg": "^8.0.0"}}
        _write(tmp_path / "package.json", json.dumps(pkg))

        result = _detect_remote_databases(tmp_path)
        assert len(result) == 1
        assert result[0]["type"] == "postgresql"

    def test_mongodb_detection(self, tmp_path: Path) -> None:
        _write(tmp_path / ".env", "MONGODB_URI=mongodb://localhost/mydb\n")

        result = _detect_remote_databases(tmp_path)
        assert len(result) == 1
        assert result[0]["type"] == "mongodb"

    def test_mongodb_from_python_deps(self, tmp_path: Path) -> None:
        _write(tmp_path / "requirements.txt", "pymongo==4.6\nmotor==3.3\n")

        result = _detect_remote_databases(tmp_path)
        assert len(result) == 1
        assert result[0]["type"] == "mongodb"

    def test_mongodb_from_js_deps(self, tmp_path: Path) -> None:
        pkg = {"dependencies": {"mongoose": "^8.0.0"}}
        _write(tmp_path / "package.json", json.dumps(pkg))

        result = _detect_remote_databases(tmp_path)
        assert len(result) == 1
        assert result[0]["type"] == "mongodb"

    def test_mysql_detection(self, tmp_path: Path) -> None:
        _write(tmp_path / ".env", "MYSQL_HOST=localhost\nMYSQL_DATABASE=myapp\n")

        result = _detect_remote_databases(tmp_path)
        assert len(result) == 1
        assert result[0]["type"] == "mysql"

    def test_mysql_from_python_deps(self, tmp_path: Path) -> None:
        _write(tmp_path / "requirements.txt", "mysqlclient==2.2\n")

        result = _detect_remote_databases(tmp_path)
        assert len(result) == 1
        assert result[0]["type"] == "mysql"

    def test_mysql_from_js_deps(self, tmp_path: Path) -> None:
        pkg = {"dependencies": {"mysql2": "^3.0.0"}}
        _write(tmp_path / "package.json", json.dumps(pkg))

        result = _detect_remote_databases(tmp_path)
        assert len(result) == 1
        assert result[0]["type"] == "mysql"

    def test_supabase_suppresses_postgresql(self, tmp_path: Path) -> None:
        """When Supabase is detected, don't also report PostgreSQL."""
        pkg = {"dependencies": {"@supabase/supabase-js": "^2.0.0"}}
        _write(tmp_path / "package.json", json.dumps(pkg))
        _write(tmp_path / ".env", "DATABASE_URL=postgresql://localhost/mydb\n")

        result = _detect_remote_databases(tmp_path)
        types = [r["type"] for r in result]
        assert "supabase" in types
        assert "postgresql" not in types

    def test_multiple_databases(self, tmp_path: Path) -> None:
        """Project with both Supabase and MongoDB."""
        pkg = {"dependencies": {"@supabase/supabase-js": "^2.0.0", "mongoose": "^8.0.0"}}
        _write(tmp_path / "package.json", json.dumps(pkg))
        _write(tmp_path / ".env", "MONGODB_URI=mongodb://localhost/mydb\n")

        result = _detect_remote_databases(tmp_path)
        types = {r["type"] for r in result}
        assert "supabase" in types
        assert "mongodb" in types

    def test_env_vars_never_leak_values(self, tmp_path: Path) -> None:
        """Verify that actual secret values never appear in results."""
        _write(
            tmp_path / ".env",
            "NEXT_PUBLIC_SUPABASE_URL=https://secret.supabase.co\nSUPABASE_SERVICE_ROLE_KEY=eyJhbGciOiJSUzI1NiJ9.secret\n",
        )
        pkg = {"dependencies": {"@supabase/supabase-js": "^2.0.0"}}
        _write(tmp_path / "package.json", json.dumps(pkg))

        result = _detect_remote_databases(tmp_path)
        result_str = json.dumps(result)
        assert "secret.supabase.co" not in result_str
        assert "eyJhbGciOiJSUzI1NiJ9" not in result_str

    def test_stable_ordering(self, tmp_path: Path) -> None:
        """Result order should be: supabase, firebase, postgresql, mongodb, mysql."""
        _write(tmp_path / ".env", "MYSQL_HOST=x\nMONGODB_URI=y\nDATABASE_URL=z\n")
        _write(tmp_path / "firebase.json", "{}")
        # No supabase, so order should be: firebase, postgresql, mongodb, mysql
        result = _detect_remote_databases(tmp_path)
        types = [r["type"] for r in result]
        # firebase before postgresql before mongodb before mysql
        assert types.index("firebase") < types.index("postgresql")
        assert types.index("postgresql") < types.index("mongodb")
        assert types.index("mongodb") < types.index("mysql")


class TestScanProjectRemoteDatabases:
    def test_remote_databases_in_scan_result(self, tmp_path: Path) -> None:
        migrations = tmp_path / "supabase" / "migrations"
        migrations.mkdir(parents=True)
        _write(
            migrations / "001.sql",
            "CREATE TABLE items (id UUID PRIMARY KEY, name TEXT);",
        )
        _write(tmp_path / ".env", "NEXT_PUBLIC_SUPABASE_URL=https://x.supabase.co\n")

        result = scan_project(tmp_path)
        assert "remote_databases" in result
        assert len(result["remote_databases"]) == 1
        assert result["remote_databases"][0]["type"] == "supabase"

    def test_empty_project_has_empty_remote_databases(self, tmp_path: Path) -> None:
        result = scan_project(tmp_path)
        assert result["remote_databases"] == []


# ---------------------------------------------------------------------------
# Real-world Supabase migration parsing (groovetherapy-style)
# ---------------------------------------------------------------------------


class TestRealWorldMigrations:
    def test_groovetherapy_style(self, tmp_path: Path) -> None:
        """Parse migrations similar to the groovetherapy project."""
        migrations = tmp_path / "migrations"
        migrations.mkdir()
        _write(
            migrations / "20260205000001_initial_schema.sql",
            """
            CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

            CREATE TABLE IF NOT EXISTS submissions (
                id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                artist_name TEXT NOT NULL,
                email TEXT NOT NULL,
                track_title TEXT NOT NULL,
                genre TEXT NOT NULL CHECK (genre IN ('house', 'techno', 'other')),
                bpm INTEGER CHECK (bpm > 0 AND bpm < 300),
                status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected'))
            );

            CREATE TABLE IF NOT EXISTS releases (
                id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                catalog_number TEXT NOT NULL UNIQUE,
                title TEXT NOT NULL,
                release_date DATE NOT NULL,
                is_published BOOLEAN NOT NULL DEFAULT FALSE
            );

            CREATE TABLE IF NOT EXISTS events (
                id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                name TEXT NOT NULL,
                date TIMESTAMPTZ NOT NULL,
                venue TEXT NOT NULL,
                city TEXT NOT NULL DEFAULT 'Berlin'
            );
            """,
        )
        _write(
            migrations / "20260205000002_admin_dashboard.sql",
            """
            ALTER TABLE releases
            ADD COLUMN IF NOT EXISTS artist_name text,
            ADD COLUMN IF NOT EXISTS release_type text;

            CREATE TABLE IF NOT EXISTS release_tracks (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                release_id uuid NOT NULL,
                track_number integer NOT NULL,
                title text NOT NULL,
                artist_name text NOT NULL,
                UNIQUE(release_id, track_number)
            );
            """,
        )

        tables = _parse_sql_migrations(migrations)
        table_names = {t["name"] for t in tables}
        assert "submissions" in table_names
        assert "releases" in table_names
        assert "events" in table_names
        assert "release_tracks" in table_names

        # Check submissions columns
        submissions = next(t for t in tables if t["name"] == "submissions")
        col_names = {c["name"] for c in submissions["columns"]}
        assert "artist_name" in col_names
        assert "email" in col_names
        assert "genre" in col_names
        assert "status" in col_names

        # Check releases got ALTER TABLE columns
        releases = next(t for t in tables if t["name"] == "releases")
        rel_col_names = {c["name"] for c in releases["columns"]}
        assert "artist_name" in rel_col_names
        assert "release_type" in rel_col_names
        assert "title" in rel_col_names
