"""Tests for projects/scanner.py and projects/registry.py."""

import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from projects.scanner import (
    _count_files,
    _detect_build_tools,
    _detect_databases,
    _detect_docs,
    _detect_frameworks,
    _detect_languages,
    _detect_package_manager,
    _detect_structure,
    _detect_test_framework,
    _find_database_files,
    _read_db_schema,
    scan_project,
)


# ---------------------------------------------------------------------------
# Helpers to build mock project trees
# ---------------------------------------------------------------------------


def _write(path: Path, content: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _make_python_project(root: Path) -> None:
    """Create a minimal Python/Flask project."""
    _write(root / "app.py", "from flask import Flask\napp = Flask(__name__)\n")
    _write(root / "utils.py", "def helper(): pass\n")
    _write(root / "requirements.txt", "flask==3.0.0\npytest==8.0.0\n")
    _write(root / "README.md", "# My Python App\nA simple flask app.\n")
    (root / "tests").mkdir(exist_ok=True)
    _write(root / "tests" / "test_app.py", "def test_one(): pass\n")
    _write(root / "Makefile", "test:\n\tpytest\nbuild:\n\techo build\n")


def _make_typescript_react_project(root: Path) -> None:
    """Create a minimal TypeScript/React project."""
    pkg = {
        "name": "my-react-app",
        "scripts": {"dev": "vite", "build": "vite build", "test": "vitest"},
        "dependencies": {"react": "^18.0.0", "react-dom": "^18.0.0"},
        "devDependencies": {
            "typescript": "^5.0.0",
            "vitest": "^1.0.0",
            "tailwindcss": "^3.0.0",
            "vite": "^5.0.0",
        },
    }
    _write(root / "package.json", json.dumps(pkg))
    _write(root / "pnpm-lock.yaml", "lockfileVersion: '9.0'\n")
    _write(root / "tsconfig.json", '{"compilerOptions": {}}')
    _write(root / "vite.config.ts", "export default {}")
    (root / "src").mkdir(exist_ok=True)
    _write(root / "src" / "App.tsx", "export default function App() { return <div/>; }")
    _write(root / "src" / "index.ts", "import App from './App';")
    _write(root / "src" / "style.css", "body { margin: 0; }")
    (root / "src" / "components").mkdir(exist_ok=True)
    _write(root / "src" / "components" / "Button.tsx", "export function Button() {}")
    _write(root / "README.md", "# React App\nBuilt with Vite.\n")


def _make_go_project(root: Path) -> None:
    """Create a minimal Go/Gin project."""
    _write(
        root / "go.mod",
        "module example.com/myapp\n\ngo 1.21\n\nrequire github.com/gin-gonic/gin v1.9.1\n",
    )
    _write(root / "go.sum", "github.com/gin-gonic/gin v1.9.1 h1:abc=\n")
    _write(root / "main.go", 'package main\n\nfunc main() { fmt.Println("hello") }\n')
    (root / "handlers").mkdir(exist_ok=True)
    _write(root / "handlers" / "user.go", "package handlers\n")
    _write(root / "Dockerfile", "FROM golang:1.21\n")
    (root / ".github" / "workflows").mkdir(parents=True, exist_ok=True)
    _write(root / ".github" / "workflows" / "ci.yml", "name: CI\n")


def _make_rust_project(root: Path) -> None:
    """Create a minimal Rust/Axum project."""
    _write(
        root / "Cargo.toml",
        '[package]\nname = "myapp"\n\n[dependencies]\naxum = "0.7"\ntokio = { version = "1", features = ["full"] }\n',
    )
    _write(root / "Cargo.lock", "# lock file\n")
    (root / "src").mkdir(exist_ok=True)
    _write(root / "src" / "main.rs", "fn main() {}")
    _write(root / "src" / "lib.rs", "pub fn add(a: i32, b: i32) -> i32 { a + b }")


# ---------------------------------------------------------------------------
# scan_project tests
# ---------------------------------------------------------------------------


class TestScanProject:
    def test_raises_on_nonexistent(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="Not a directory"):
            scan_project(tmp_path / "nope")

    def test_empty_directory(self, tmp_path: Path) -> None:
        result = scan_project(tmp_path)
        assert result["name"] == tmp_path.name
        assert result["languages"] == []
        assert result["primary_language"] is None
        assert result["frameworks"] == []
        assert result["package_manager"] is None
        assert result["file_count"] == 0
        assert result["total_lines"] is None
        assert "scanned_at" in result

    def test_python_project(self, tmp_path: Path) -> None:
        _make_python_project(tmp_path)
        result = scan_project(tmp_path)

        assert result["primary_language"] == "python"
        assert "python" in result["languages"]
        assert "flask" in result["frameworks"]
        assert result["package_manager"] == "pip"
        assert result["test_framework"] == "pytest"
        assert result["docs"]["has_readme"] is True
        assert "My Python App" in result["docs"]["readme_summary"]
        assert "tests" in result["structure"]["key_dirs"].get("tests", "")
        assert result["structure"]["entry_points"].get("main") == "python app.py"
        assert result["structure"]["entry_points"].get("make_test") == "make test"
        assert result["structure"]["entry_points"].get("make_build") == "make build"

    def test_typescript_react_project(self, tmp_path: Path) -> None:
        _make_typescript_react_project(tmp_path)
        result = scan_project(tmp_path)

        assert result["primary_language"] == "typescript"
        assert "typescript" in result["languages"]
        assert "css" in result["languages"]
        assert "react" in result["frameworks"]
        assert "tailwind" in result["frameworks"]
        assert result["package_manager"] == "pnpm"
        assert result["test_framework"] == "vitest"
        assert "typescript" in result["build_tools"]
        assert "vite" in result["build_tools"]
        # pnpm uses bare commands, not "pnpm run"
        assert result["structure"]["entry_points"].get("dev") == "pnpm dev"
        assert result["structure"]["entry_points"].get("build") == "pnpm build"
        assert "source" in result["structure"]["key_dirs"]
        assert result["structure"]["key_dirs"]["source"] == "src"

    def test_go_project(self, tmp_path: Path) -> None:
        _make_go_project(tmp_path)
        result = scan_project(tmp_path)

        assert result["primary_language"] == "go"
        assert "go" in result["languages"]
        assert "gin" in result["frameworks"]
        assert result["package_manager"] == "go modules"
        assert "docker" in result["build_tools"]
        assert "github-actions" in result["build_tools"]
        assert result["structure"]["entry_points"].get("main") == "go run main.go"

    def test_rust_project(self, tmp_path: Path) -> None:
        _make_rust_project(tmp_path)
        result = scan_project(tmp_path)

        assert result["primary_language"] == "rust"
        assert "axum" in result["frameworks"]
        assert "tokio" in result["frameworks"]
        assert result["package_manager"] == "cargo"

    def test_skips_node_modules(self, tmp_path: Path) -> None:
        (tmp_path / "node_modules" / "react").mkdir(parents=True)
        _write(tmp_path / "node_modules" / "react" / "index.js", "module.exports = {};")
        _write(tmp_path / "src.js", "console.log('hi');")

        result = scan_project(tmp_path)
        assert result["file_count"] == 1
        assert result["languages"] == ["javascript"]


# ---------------------------------------------------------------------------
# Individual detector tests
# ---------------------------------------------------------------------------


class TestDetectLanguages:
    def test_counts_correctly(self, tmp_path: Path) -> None:
        _write(tmp_path / "a.py")
        _write(tmp_path / "b.py")
        _write(tmp_path / "c.py")
        _write(tmp_path / "d.ts")
        langs = _detect_languages(tmp_path)
        assert langs[0] == "python"
        assert "typescript" in langs

    def test_empty_dir(self, tmp_path: Path) -> None:
        assert _detect_languages(tmp_path) == []


class TestDetectFrameworks:
    def test_js_frameworks(self, tmp_path: Path) -> None:
        pkg = {"dependencies": {"express": "^4.0.0", "hono": "^3.0.0"}}
        _write(tmp_path / "package.json", json.dumps(pkg))
        fws = _detect_frameworks(tmp_path)
        assert "express" in fws
        assert "hono" in fws

    def test_python_frameworks_from_requirements(self, tmp_path: Path) -> None:
        _write(tmp_path / "requirements.txt", "fastapi==0.100.0\nsqlalchemy==2.0\n")
        fws = _detect_frameworks(tmp_path)
        assert "fastapi" in fws
        assert "sqlalchemy" in fws

    def test_go_frameworks(self, tmp_path: Path) -> None:
        _write(tmp_path / "go.mod", "require github.com/gofiber/fiber/v2 v2.50.0\n")
        fws = _detect_frameworks(tmp_path)
        assert "fiber" in fws

    def test_ruby_frameworks(self, tmp_path: Path) -> None:
        _write(tmp_path / "Gemfile", "gem 'rails', '~> 7.0'\ngem 'sinatra'\n")
        fws = _detect_frameworks(tmp_path)
        assert "rails" in fws
        assert "sinatra" in fws

    def test_deduplication(self, tmp_path: Path) -> None:
        # Flask in both requirements.txt and pyproject.toml
        _write(tmp_path / "requirements.txt", "flask\n")
        _write(tmp_path / "pyproject.toml", "[project]\ndependencies = ['flask']\n")
        fws = _detect_frameworks(tmp_path)
        assert fws.count("flask") == 1


class TestDetectPackageManager:
    def test_pnpm(self, tmp_path: Path) -> None:
        _write(tmp_path / "pnpm-lock.yaml", "")
        assert _detect_package_manager(tmp_path) == "pnpm"

    def test_yarn(self, tmp_path: Path) -> None:
        _write(tmp_path / "yarn.lock", "")
        assert _detect_package_manager(tmp_path) == "yarn"

    def test_npm(self, tmp_path: Path) -> None:
        _write(tmp_path / "package-lock.json", "{}")
        assert _detect_package_manager(tmp_path) == "npm"

    def test_pip(self, tmp_path: Path) -> None:
        _write(tmp_path / "requirements.txt", "flask\n")
        assert _detect_package_manager(tmp_path) == "pip"

    def test_poetry_from_pyproject(self, tmp_path: Path) -> None:
        _write(tmp_path / "pyproject.toml", "[tool.poetry]\nname='x'\n")
        assert _detect_package_manager(tmp_path) == "poetry"

    def test_pip_fallback_pyproject(self, tmp_path: Path) -> None:
        _write(tmp_path / "pyproject.toml", "[project]\nname='x'\n")
        assert _detect_package_manager(tmp_path) == "pip"

    def test_none_for_empty(self, tmp_path: Path) -> None:
        assert _detect_package_manager(tmp_path) is None


class TestDetectTestFramework:
    def test_vitest_from_package_json(self, tmp_path: Path) -> None:
        pkg = {"devDependencies": {"vitest": "^1.0.0"}}
        _write(tmp_path / "package.json", json.dumps(pkg))
        assert _detect_test_framework(tmp_path) == "vitest"

    def test_jest_from_config(self, tmp_path: Path) -> None:
        _write(tmp_path / "jest.config.js", "module.exports = {};")
        assert _detect_test_framework(tmp_path) == "jest"

    def test_pytest_from_conftest(self, tmp_path: Path) -> None:
        _write(tmp_path / "conftest.py", "import pytest\n")
        assert _detect_test_framework(tmp_path) == "pytest"

    def test_pytest_from_requirements(self, tmp_path: Path) -> None:
        _write(tmp_path / "requirements.txt", "pytest>=8.0\n")
        assert _detect_test_framework(tmp_path) == "pytest"

    def test_heuristic_from_test_dir(self, tmp_path: Path) -> None:
        (tmp_path / "tests").mkdir()
        _write(tmp_path / "main.go", "package main")
        assert _detect_test_framework(tmp_path) == "go test"


class TestDetectBuildTools:
    def test_docker_and_make(self, tmp_path: Path) -> None:
        _write(tmp_path / "Dockerfile", "FROM python:3.12")
        _write(tmp_path / "Makefile", "all:\n\techo hi")
        tools = _detect_build_tools(tmp_path)
        assert "docker" in tools
        assert "make" in tools

    def test_github_actions(self, tmp_path: Path) -> None:
        (tmp_path / ".github" / "workflows").mkdir(parents=True)
        _write(tmp_path / ".github" / "workflows" / "ci.yml", "name: CI")
        tools = _detect_build_tools(tmp_path)
        assert "github-actions" in tools

    def test_vite_glob(self, tmp_path: Path) -> None:
        _write(tmp_path / "vite.config.ts", "export default {}")
        tools = _detect_build_tools(tmp_path)
        assert "vite" in tools


class TestDetectStructure:
    def test_key_dirs(self, tmp_path: Path) -> None:
        (tmp_path / "src").mkdir()
        (tmp_path / "tests").mkdir()
        (tmp_path / "docs").mkdir()
        structure = _detect_structure(tmp_path)
        assert structure["key_dirs"]["source"] == "src"
        assert structure["key_dirs"]["tests"] == "tests"
        assert structure["key_dirs"]["docs"] == "docs"
        assert "src" in structure["directories"]

    def test_entry_points_from_package_json(self, tmp_path: Path) -> None:
        pkg = {"scripts": {"dev": "next dev", "build": "next build"}}
        _write(tmp_path / "package.json", json.dumps(pkg))
        _write(tmp_path / "package-lock.json", "{}")
        structure = _detect_structure(tmp_path)
        assert structure["entry_points"]["dev"] == "npm run dev"
        assert structure["entry_points"]["build"] == "npm run build"


class TestDetectDocs:
    def test_with_readme(self, tmp_path: Path) -> None:
        _write(tmp_path / "README.md", "# Title\nDescription here.\n")
        docs = _detect_docs(tmp_path)
        assert docs["has_readme"] is True
        assert "Title" in docs["readme_summary"]

    def test_with_claude_md(self, tmp_path: Path) -> None:
        _write(tmp_path / "CLAUDE.md", "# Claude\n")
        docs = _detect_docs(tmp_path)
        assert docs["has_claude_md"] is True

    def test_with_claude_dir(self, tmp_path: Path) -> None:
        (tmp_path / ".claude").mkdir()
        docs = _detect_docs(tmp_path)
        assert docs["has_claude_dir"] is True

    def test_no_docs(self, tmp_path: Path) -> None:
        docs = _detect_docs(tmp_path)
        assert docs["has_readme"] is False
        assert docs["has_claude_md"] is False
        assert docs["has_claude_dir"] is False
        assert docs["readme_summary"] is None


class TestCountFiles:
    def test_counts_only_files(self, tmp_path: Path) -> None:
        _write(tmp_path / "a.txt")
        _write(tmp_path / "b.txt")
        (tmp_path / "subdir").mkdir()
        _write(tmp_path / "subdir" / "c.txt")
        assert _count_files(tmp_path) == 3

    def test_skips_hidden(self, tmp_path: Path) -> None:
        (tmp_path / ".hidden").mkdir()
        _write(tmp_path / ".hidden" / "secret.txt")
        _write(tmp_path / "visible.txt")
        assert _count_files(tmp_path) == 1


# ---------------------------------------------------------------------------
# Database detection tests
# ---------------------------------------------------------------------------


def _create_test_db(db_path: Path, tables: dict[str, list[tuple[str, str]]] | None = None) -> None:
    """Create a test SQLite database with optional table definitions.

    Args:
        db_path: Path to create the database file.
        tables: Dict mapping table name to list of (column_name, column_type) tuples.
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    if tables:
        for table_name, columns in tables.items():
            cols = ", ".join(f"{name} {typ}" for name, typ in columns)
            conn.execute(f"CREATE TABLE {table_name} ({cols})")
    conn.commit()
    conn.close()


class TestFindDatabaseFiles:
    def test_finds_db_in_root(self, tmp_path: Path) -> None:
        _create_test_db(tmp_path / "app.db")
        found = _find_database_files(tmp_path)
        assert len(found) == 1
        assert found[0].name == "app.db"

    def test_finds_db_in_data_subdir(self, tmp_path: Path) -> None:
        _create_test_db(tmp_path / "data" / "store.sqlite")
        found = _find_database_files(tmp_path)
        assert len(found) == 1
        assert found[0].name == "store.sqlite"

    def test_finds_sqlite3_extension(self, tmp_path: Path) -> None:
        _create_test_db(tmp_path / "db" / "main.sqlite3")
        found = _find_database_files(tmp_path)
        assert len(found) == 1
        assert found[0].name == "main.sqlite3"

    def test_skips_non_db_extensions(self, tmp_path: Path) -> None:
        _write(tmp_path / "data.json", "{}")
        _write(tmp_path / "app.txt", "hello")
        found = _find_database_files(tmp_path)
        assert len(found) == 0

    def test_deduplicates_root_and_subdir(self, tmp_path: Path) -> None:
        """If data/ is both in root scan and _DB_SEARCH_DIRS, no duplicates."""
        _create_test_db(tmp_path / "data" / "app.db")
        found = _find_database_files(tmp_path)
        assert len(found) == 1

    def test_finds_multiple_databases(self, tmp_path: Path) -> None:
        _create_test_db(tmp_path / "app.db")
        _create_test_db(tmp_path / "data" / "store.sqlite")
        _create_test_db(tmp_path / "database" / "archive.sqlite3")
        found = _find_database_files(tmp_path)
        assert len(found) == 3

    def test_empty_directory(self, tmp_path: Path) -> None:
        found = _find_database_files(tmp_path)
        assert found == []


class TestReadDbSchema:
    def test_reads_table_and_columns(self, tmp_path: Path) -> None:
        db_path = tmp_path / "test.db"
        _create_test_db(db_path, {
            "users": [("id", "INTEGER"), ("name", "TEXT"), ("email", "TEXT")],
        })
        result = _read_db_schema(db_path, tmp_path)
        assert result is not None
        assert result["path"] == "test.db"
        assert result["size_mb"] >= 0
        assert len(result["tables"]) == 1

        table = result["tables"][0]
        assert table["name"] == "users"
        assert len(table["columns"]) == 3
        col_names = [c["name"] for c in table["columns"]]
        assert "id" in col_names
        assert "name" in col_names
        assert "email" in col_names
        col_types = {c["name"]: c["type"] for c in table["columns"]}
        assert col_types["id"] == "INTEGER"
        assert col_types["name"] == "TEXT"

    def test_reads_row_count(self, tmp_path: Path) -> None:
        db_path = tmp_path / "test.db"
        _create_test_db(db_path, {
            "items": [("id", "INTEGER"), ("value", "TEXT")],
        })
        conn = sqlite3.connect(str(db_path))
        for i in range(50):
            conn.execute("INSERT INTO items (id, value) VALUES (?, ?)", (i, f"val_{i}"))
        conn.commit()
        conn.close()

        result = _read_db_schema(db_path, tmp_path)
        assert result is not None
        assert result["tables"][0]["row_count"] == 50

    def test_multiple_tables(self, tmp_path: Path) -> None:
        db_path = tmp_path / "multi.db"
        _create_test_db(db_path, {
            "users": [("id", "INTEGER"), ("name", "TEXT")],
            "orders": [("id", "INTEGER"), ("user_id", "INTEGER"), ("total", "REAL")],
        })
        result = _read_db_schema(db_path, tmp_path)
        assert result is not None
        assert len(result["tables"]) == 2
        table_names = {t["name"] for t in result["tables"]}
        assert table_names == {"users", "orders"}

    def test_relative_path_in_subdir(self, tmp_path: Path) -> None:
        db_path = tmp_path / "data" / "nested" / "app.db"
        _create_test_db(db_path, {"t": [("id", "INTEGER")]})
        result = _read_db_schema(db_path, tmp_path)
        assert result is not None
        assert result["path"] == "data/nested/app.db"

    def test_skips_corrupted_file(self, tmp_path: Path) -> None:
        bad_path = tmp_path / "bad.db"
        bad_path.write_bytes(b"this is not a sqlite database at all")
        result = _read_db_schema(bad_path, tmp_path)
        assert result is None

    def test_skips_nonexistent_file(self, tmp_path: Path) -> None:
        result = _read_db_schema(tmp_path / "nope.db", tmp_path)
        assert result is None

    def test_empty_database(self, tmp_path: Path) -> None:
        db_path = tmp_path / "empty.db"
        _create_test_db(db_path)
        result = _read_db_schema(db_path, tmp_path)
        assert result is not None
        assert result["tables"] == []


class TestDetectDatabases:
    def test_full_detection(self, tmp_path: Path) -> None:
        db_path = tmp_path / "data" / "app.db"
        _create_test_db(db_path, {
            "emails": [
                ("id", "INTEGER"),
                ("sender", "TEXT"),
                ("subject", "TEXT"),
                ("body", "TEXT"),
                ("received_at", "TEXT"),
            ],
        })
        conn = sqlite3.connect(str(db_path))
        for i in range(10):
            conn.execute(
                "INSERT INTO emails (id, sender, subject, body, received_at) VALUES (?, ?, ?, ?, ?)",
                (i, f"user{i}@test.com", f"Subject {i}", f"Body {i}", "2026-01-01"),
            )
        conn.commit()
        conn.close()

        databases = _detect_databases(tmp_path)
        assert len(databases) == 1

        db = databases[0]
        assert db["path"] == "data/app.db"
        assert db["size_mb"] >= 0
        assert len(db["tables"]) == 1

        table = db["tables"][0]
        assert table["name"] == "emails"
        assert table["row_count"] == 10
        assert len(table["columns"]) == 5
        col_names = [c["name"] for c in table["columns"]]
        assert col_names == ["id", "sender", "subject", "body", "received_at"]

    def test_no_databases(self, tmp_path: Path) -> None:
        _write(tmp_path / "app.py", "print('hello')")
        databases = _detect_databases(tmp_path)
        assert databases == []

    def test_skips_corrupted_gracefully(self, tmp_path: Path) -> None:
        (tmp_path / "bad.db").write_bytes(b"not sqlite")
        _create_test_db(tmp_path / "good.db", {"t": [("id", "INTEGER")]})
        databases = _detect_databases(tmp_path)
        assert len(databases) == 1
        assert databases[0]["tables"][0]["name"] == "t"


class TestScanProjectDatabases:
    def test_databases_in_scan_result(self, tmp_path: Path) -> None:
        _create_test_db(tmp_path / "data" / "store.db", {
            "products": [("id", "INTEGER"), ("name", "TEXT"), ("price", "REAL")],
        })
        result = scan_project(tmp_path)
        assert "databases" in result
        assert len(result["databases"]) == 1
        assert result["databases"][0]["tables"][0]["name"] == "products"

    def test_empty_project_has_empty_databases(self, tmp_path: Path) -> None:
        result = scan_project(tmp_path)
        assert result["databases"] == []


# ---------------------------------------------------------------------------
# Registry tests
# ---------------------------------------------------------------------------


class TestRegistry:
    @pytest.fixture(autouse=True)
    def _use_tmp_registry(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Redirect the registry file to a temp location."""
        import projects.registry as reg

        self.registry_path = tmp_path / "registry" / "projects.json"
        monkeypatch.setattr(reg, "REGISTRY_PATH", self.registry_path)

    def test_register_and_list(self) -> None:
        from projects.registry import list_projects, register_project

        profile = {
            "name": "my-app",
            "path": "/tmp/my-app",
            "primary_language": "python",
            "frameworks": ["flask"],
            "scanned_at": "2026-03-11T00:00:00+00:00",
        }
        register_project(profile)
        projects = list_projects()
        assert len(projects) == 1
        assert projects[0]["name"] == "my-app"
        assert projects[0]["path"] == "/tmp/my-app"
        assert "added_at" in projects[0]

    def test_register_updates_existing(self) -> None:
        from projects.registry import list_projects, register_project

        profile1 = {
            "name": "app",
            "path": "/tmp/app",
            "primary_language": "python",
            "frameworks": [],
            "scanned_at": "2026-03-01T00:00:00+00:00",
        }
        register_project(profile1)

        profile2 = {
            "name": "app",
            "path": "/tmp/app",
            "primary_language": "python",
            "frameworks": ["flask"],
            "scanned_at": "2026-03-11T00:00:00+00:00",
        }
        register_project(profile2)

        projects = list_projects()
        assert len(projects) == 1
        assert projects[0]["frameworks"] == ["flask"]
        assert projects[0]["last_scanned"] == "2026-03-11T00:00:00+00:00"

    def test_unregister(self) -> None:
        from projects.registry import list_projects, register_project, unregister_project

        register_project({"name": "a", "path": "/a", "primary_language": "python", "frameworks": []})
        assert unregister_project("/a") is True
        assert list_projects() == []
        assert unregister_project("/nonexistent") is False

    def test_active_project(self) -> None:
        from projects.registry import (
            get_active_project,
            register_project,
            set_active_project,
        )

        assert get_active_project() is None

        register_project({"name": "x", "path": "/x", "primary_language": "go", "frameworks": []})
        assert set_active_project("/x") is True
        active = get_active_project()
        assert active is not None
        assert active["path"] == "/x"

    def test_set_active_nonexistent(self) -> None:
        from projects.registry import set_active_project

        assert set_active_project("/nope") is False

    def test_unregister_clears_active(self) -> None:
        from projects.registry import (
            get_active_project,
            register_project,
            set_active_project,
            unregister_project,
        )

        register_project({"name": "z", "path": "/z", "primary_language": "rust", "frameworks": []})
        set_active_project("/z")
        unregister_project("/z")
        assert get_active_project() is None

    def test_register_missing_path_raises(self) -> None:
        from projects.registry import register_project

        with pytest.raises(ValueError, match="path"):
            register_project({"name": "bad"})
