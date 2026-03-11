"""Project scanner — detects tech stack, structure, and conventions by reading files."""

from __future__ import annotations

import json
import sqlite3
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Maximum database file size to scan (100 MB)
_MAX_DB_SIZE_BYTES = 100 * 1024 * 1024

# Row count threshold — above this we report as approximate
_ROW_COUNT_LIMIT = 1_000_000

# Database file extensions to look for
_DB_EXTENSIONS = frozenset({".db", ".sqlite", ".sqlite3"})

# Subdirectories to search for databases (in addition to project root)
_DB_SEARCH_DIRS = ("data", "db", "database")

# Directories to skip during scanning
SKIP_DIRS = frozenset(
    {
        "node_modules",
        "venv",
        ".venv",
        "env",
        ".git",
        "__pycache__",
        "dist",
        "build",
        ".next",
        ".nuxt",
        "target",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".tox",
        "vendor",
        "coverage",
        ".turbo",
        "htmlcov",
        ".eggs",
        ".cargo",
        ".idea",
        ".vscode",
        ".amiga",
    }
)

# Extension to language name mapping
EXTENSION_MAP: dict[str, str] = {
    ".py": "python",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".rb": "ruby",
    ".swift": "swift",
    ".kt": "kotlin",
    ".css": "css",
    ".scss": "scss",
    ".html": "html",
    ".vue": "vue",
    ".svelte": "svelte",
}

# Framework detection patterns per manifest
_JS_FRAMEWORK_PATTERNS: dict[str, str] = {
    "react": "react",
    "next": "next.js",
    "nuxt": "nuxt",
    "vue": "vue",
    "@angular/core": "angular",
    "express": "express",
    "fastify": "fastify",
    "koa": "koa",
    "hono": "hono",
    "svelte": "svelte",
    "solid-js": "solid",
    "remix": "remix",
    "gatsby": "gatsby",
    "@nestjs/core": "nestjs",
    "electron": "electron",
    "tailwindcss": "tailwind",
}

_PY_FRAMEWORK_PATTERNS: dict[str, str] = {
    "django": "django",
    "flask": "flask",
    "fastapi": "fastapi",
    "starlette": "starlette",
    "tornado": "tornado",
    "aiohttp": "aiohttp",
    "sanic": "sanic",
    "celery": "celery",
    "sqlalchemy": "sqlalchemy",
    "pydantic": "pydantic",
}

_GO_FRAMEWORK_PATTERNS: dict[str, str] = {
    "gin-gonic/gin": "gin",
    "labstack/echo": "echo",
    "gofiber/fiber": "fiber",
    "gorilla/mux": "gorilla",
    "chi": "chi",
}

_RUST_FRAMEWORK_PATTERNS: dict[str, str] = {
    "actix": "actix",
    "axum": "axum",
    "rocket": "rocket",
    "warp": "warp",
    "tokio": "tokio",
}

_RUBY_FRAMEWORK_PATTERNS: dict[str, str] = {
    "rails": "rails",
    "sinatra": "sinatra",
    "hanami": "hanami",
}


def scan_project(path: Path) -> dict[str, Any]:
    """Scan a project directory and return a profile dict."""
    path = path.resolve()
    if not path.is_dir():
        raise ValueError(f"Not a directory: {path}")

    languages = _detect_languages(path)
    frameworks = _detect_frameworks(path)
    package_manager = _detect_package_manager(path)
    test_framework = _detect_test_framework(path)
    build_tools = _detect_build_tools(path)
    structure = _detect_structure(path)
    docs = _detect_docs(path)
    git_info = _detect_git_info(path)
    file_count = _count_files(path)
    databases = _detect_databases(path)

    primary_language = languages[0] if languages else None

    return {
        "name": path.name,
        "path": str(path),
        "scanned_at": datetime.now(timezone.utc).isoformat(),
        "languages": languages,
        "primary_language": primary_language,
        "frameworks": frameworks,
        "package_manager": package_manager,
        "test_framework": test_framework,
        "build_tools": build_tools,
        "structure": structure,
        "docs": docs,
        "git": git_info,
        "file_count": file_count,
        "databases": databases,
        "total_lines": None,
    }


def _should_skip(dir_path: Path) -> bool:
    """Check if a directory should be skipped."""
    return dir_path.name in SKIP_DIRS or dir_path.name.startswith(".")


def _iter_files(path: Path) -> list[Path]:
    """Iterate over all files, skipping excluded directories."""
    files: list[Path] = []
    stack: list[Path] = [path]
    while stack:
        current = stack.pop()
        try:
            for entry in current.iterdir():
                if entry.is_dir():
                    if not _should_skip(entry):
                        stack.append(entry)
                elif entry.is_file():
                    files.append(entry)
        except PermissionError:
            continue
    return files


def _detect_languages(path: Path) -> list[str]:
    """Detect languages by counting file extensions, sorted by frequency."""
    counts: dict[str, int] = {}
    for file in _iter_files(path):
        suffix = file.suffix.lower()
        lang = EXTENSION_MAP.get(suffix)
        if lang:
            counts[lang] = counts.get(lang, 0) + 1

    sorted_langs = sorted(counts.keys(), key=lambda k: counts[k], reverse=True)
    return sorted_langs


def _read_file_safe(file_path: Path, max_bytes: int = 1_000_000) -> str | None:
    """Read a file safely, returning None on any error."""
    try:
        if not file_path.is_file():
            return None
        if file_path.stat().st_size > max_bytes:
            return None
        return file_path.read_text(encoding="utf-8", errors="replace")
    except (OSError, PermissionError, UnicodeDecodeError):
        return None


def _parse_json_safe(file_path: Path) -> dict[str, Any] | None:
    """Parse a JSON file safely."""
    content = _read_file_safe(file_path)
    if content is None:
        return None
    try:
        data = json.loads(content)
        if isinstance(data, dict):
            return data
        return None
    except (json.JSONDecodeError, ValueError):
        return None


def _detect_frameworks(path: Path) -> list[str]:
    """Detect frameworks from manifest files."""
    frameworks: list[str] = []

    # JavaScript/TypeScript: package.json
    pkg = _parse_json_safe(path / "package.json")
    if pkg is not None:
        all_deps: dict[str, str] = {}
        for key in ("dependencies", "devDependencies", "peerDependencies"):
            deps = pkg.get(key)
            if isinstance(deps, dict):
                all_deps.update(deps)
        dep_names = set(all_deps.keys())
        for pattern, name in _JS_FRAMEWORK_PATTERNS.items():
            if pattern in dep_names:
                frameworks.append(name)

    # Python: requirements.txt
    req_content = _read_file_safe(path / "requirements.txt")
    if req_content is not None:
        _match_python_deps(req_content, frameworks)

    # Python: pyproject.toml
    pyproject_content = _read_file_safe(path / "pyproject.toml")
    if pyproject_content is not None:
        _match_python_deps(pyproject_content, frameworks)

    # Python: Pipfile
    pipfile_content = _read_file_safe(path / "Pipfile")
    if pipfile_content is not None:
        _match_python_deps(pipfile_content, frameworks)

    # Go: go.mod
    gomod_content = _read_file_safe(path / "go.mod")
    if gomod_content is not None:
        lower = gomod_content.lower()
        for pattern, name in _GO_FRAMEWORK_PATTERNS.items():
            if pattern.lower() in lower:
                frameworks.append(name)

    # Rust: Cargo.toml
    cargo_content = _read_file_safe(path / "Cargo.toml")
    if cargo_content is not None:
        lower = cargo_content.lower()
        for pattern, name in _RUST_FRAMEWORK_PATTERNS.items():
            if pattern.lower() in lower:
                frameworks.append(name)

    # Ruby: Gemfile
    gemfile_content = _read_file_safe(path / "Gemfile")
    if gemfile_content is not None:
        lower = gemfile_content.lower()
        for pattern, name in _RUBY_FRAMEWORK_PATTERNS.items():
            if pattern.lower() in lower:
                frameworks.append(name)

    # Deduplicate while preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for fw in frameworks:
        if fw not in seen:
            seen.add(fw)
            unique.append(fw)
    return unique


def _match_python_deps(content: str, frameworks: list[str]) -> None:
    """Match Python framework patterns against file content."""
    lower = content.lower()
    for pattern, name in _PY_FRAMEWORK_PATTERNS.items():
        if pattern in lower and name not in frameworks:
            frameworks.append(name)


def _detect_package_manager(path: Path) -> str | None:
    """Detect the package manager from lock files."""
    checks: list[tuple[str, str]] = [
        ("pnpm-lock.yaml", "pnpm"),
        ("yarn.lock", "yarn"),
        ("bun.lockb", "bun"),
        ("package-lock.json", "npm"),
        ("Pipfile.lock", "pipenv"),
        ("poetry.lock", "poetry"),
        ("requirements.txt", "pip"),
        ("go.sum", "go modules"),
        ("Cargo.lock", "cargo"),
        ("Gemfile.lock", "bundler"),
    ]
    for filename, manager in checks:
        if (path / filename).exists():
            return manager

    # Fallback: pyproject.toml with poetry or pip
    if (path / "pyproject.toml").exists():
        content = _read_file_safe(path / "pyproject.toml")
        if content and "poetry" in content.lower():
            return "poetry"
        return "pip"

    return None


def _detect_test_framework(path: Path) -> str | None:
    """Detect the test framework from config files and manifests."""
    # JS test frameworks from package.json
    pkg = _parse_json_safe(path / "package.json")
    if pkg is not None:
        all_deps: set[str] = set()
        for key in ("dependencies", "devDependencies"):
            deps = pkg.get(key)
            if isinstance(deps, dict):
                all_deps.update(deps.keys())

        js_test_fws: list[tuple[str, str]] = [
            ("vitest", "vitest"),
            ("jest", "jest"),
            ("mocha", "mocha"),
            ("@playwright/test", "playwright"),
            ("playwright", "playwright"),
            ("cypress", "cypress"),
        ]
        for dep, name in js_test_fws:
            if dep in all_deps:
                return name

    # Config file checks
    config_checks: list[tuple[str, str]] = [
        ("vitest.config.ts", "vitest"),
        ("vitest.config.js", "vitest"),
        ("jest.config.ts", "jest"),
        ("jest.config.js", "jest"),
        ("jest.config.json", "jest"),
        ("pytest.ini", "pytest"),
        ("conftest.py", "pytest"),
        ("setup.cfg", "pytest"),
    ]
    for filename, fw in config_checks:
        if (path / filename).exists():
            if filename == "setup.cfg":
                content = _read_file_safe(path / filename)
                if content and "pytest" in content.lower():
                    return "pytest"
            else:
                return fw

    # Python: check requirements for pytest
    for manifest in ("requirements.txt", "pyproject.toml", "Pipfile"):
        content = _read_file_safe(path / manifest)
        if content and "pytest" in content.lower():
            return "pytest"

    # Test directory heuristic
    test_dirs = ("tests", "test", "__tests__", "spec")
    for d in test_dirs:
        if (path / d).is_dir():
            languages = _detect_languages(path)
            if languages:
                primary = languages[0]
                lang_to_test: dict[str, str] = {
                    "typescript": "jest",
                    "javascript": "jest",
                    "python": "pytest",
                    "go": "go test",
                    "rust": "cargo test",
                }
                result = lang_to_test.get(primary)
                if result:
                    return result

    return None


def _detect_build_tools(path: Path) -> list[str]:
    """Detect build tools and CI/CD configurations."""
    tools: list[str] = []

    file_checks: list[tuple[str, str]] = [
        ("Makefile", "make"),
        ("Dockerfile", "docker"),
        ("docker-compose.yml", "docker-compose"),
        ("docker-compose.yaml", "docker-compose"),
        ("tsconfig.json", "typescript"),
        ("Procfile", "procfile"),
        ("vercel.json", "vercel"),
        ("netlify.toml", "netlify"),
        ("fly.toml", "fly.io"),
        ("render.yaml", "render"),
        ("turbo.json", "turborepo"),
        ("nx.json", "nx"),
        (".eslintrc.json", "eslint"),
        (".eslintrc.js", "eslint"),
        (".prettierrc", "prettier"),
        ("biome.json", "biome"),
    ]
    for filename, tool in file_checks:
        if (path / filename).exists():
            tools.append(tool)

    # Glob-style config checks
    glob_checks: list[tuple[str, str]] = [
        ("webpack.config.*", "webpack"),
        ("vite.config.*", "vite"),
        ("rollup.config.*", "rollup"),
        ("esbuild.*", "esbuild"),
    ]
    for pattern, tool in glob_checks:
        if list(path.glob(pattern)):
            tools.append(tool)

    # CI/CD directories
    if (path / ".github" / "workflows").is_dir():
        tools.append("github-actions")
    if (path / ".gitlab-ci.yml").exists():
        tools.append("gitlab-ci")
    if (path / ".circleci").is_dir():
        tools.append("circleci")
    if (path / "Jenkinsfile").exists():
        tools.append("jenkins")

    # Deduplicate preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for t in tools:
        if t not in seen:
            seen.add(t)
            unique.append(t)
    return unique


def _detect_structure(path: Path) -> dict[str, Any]:
    """Detect directory structure and entry points."""
    # Top-level directories (exclude hidden and skip dirs)
    directories: list[str] = []
    try:
        for entry in sorted(path.iterdir()):
            if entry.is_dir() and not _should_skip(entry):
                directories.append(entry.name)
    except PermissionError:
        pass

    # Key directories
    key_dir_mapping: dict[str, list[str]] = {
        "source": ["src", "lib", "app"],
        "components": ["components"],
        "pages": ["pages"],
        "api": ["api"],
        "tests": ["tests", "test", "__tests__", "spec"],
        "docs": ["docs", "documentation"],
        "scripts": ["scripts"],
        "public": ["public", "static"],
        "config": ["config", "configs"],
    }
    key_dirs: dict[str, str] = {}
    for role, candidates in key_dir_mapping.items():
        for candidate in candidates:
            if (path / candidate).is_dir():
                key_dirs[role] = candidate
                break

    # Entry points
    entry_points: dict[str, str] = {}

    # From package.json scripts
    pkg = _parse_json_safe(path / "package.json")
    if pkg is not None:
        scripts = pkg.get("scripts")
        if isinstance(scripts, dict):
            interesting = ("start", "dev", "build", "test", "lint", "serve", "preview")
            for key in interesting:
                if key in scripts:
                    manager = _detect_package_manager(path) or "npm"
                    prefix = {"pnpm": "pnpm", "yarn": "yarn", "bun": "bun"}.get(manager, "npm")
                    run_cmd = "" if prefix in ("pnpm", "yarn", "bun") else " run"
                    entry_points[key] = f"{prefix}{run_cmd} {key}"

    # Common entry point files
    entry_files: list[tuple[str, str]] = [
        ("main.py", "python main.py"),
        ("app.py", "python app.py"),
        ("manage.py", "python manage.py"),
        ("main.go", "go run main.go"),
        ("main.rs", "cargo run"),
        ("index.ts", "ts-node index.ts"),
        ("index.js", "node index.js"),
    ]
    for filename, cmd in entry_files:
        if (path / filename).exists() and "start" not in entry_points:
            entry_points["main"] = cmd

    # Makefile targets
    makefile_content = _read_file_safe(path / "Makefile")
    if makefile_content is not None:
        for line in makefile_content.splitlines():
            if line and not line.startswith(("\t", " ", "#")) and ":" in line:
                target = line.split(":")[0].strip()
                if target and not target.startswith(".") and target in (
                    "run",
                    "dev",
                    "build",
                    "test",
                    "deploy",
                ):
                    entry_points[f"make_{target}"] = f"make {target}"

    return {
        "directories": directories,
        "key_dirs": key_dirs,
        "entry_points": entry_points,
    }


def _detect_docs(path: Path) -> dict[str, Any]:
    """Detect documentation files."""
    has_readme = (path / "README.md").is_file()
    readme_summary: str | None = None
    if has_readme:
        content = _read_file_safe(path / "README.md")
        if content:
            lines = content.splitlines()[:20]
            readme_summary = "\n".join(lines)

    return {
        "has_readme": has_readme,
        "has_claude_md": (path / "CLAUDE.md").is_file(),
        "has_claude_dir": (path / ".claude").is_dir(),
        "readme_summary": readme_summary,
    }


def _run_git_command(path: Path, args: list[str]) -> str | None:
    """Run a git command safely, returning stdout or None."""
    try:
        result = subprocess.run(
            ["git"] + args,
            cwd=str(path),
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
        return None
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return None


def _detect_git_info(path: Path) -> dict[str, Any]:
    """Detect git repository information."""
    is_repo = (path / ".git").exists() or (path / ".git").is_file()
    if not is_repo:
        check = _run_git_command(path, ["rev-parse", "--is-inside-work-tree"])
        is_repo = check == "true"

    if not is_repo:
        return {
            "is_repo": False,
            "remote": None,
            "branch": None,
            "commit_count": None,
        }

    remote = _run_git_command(path, ["remote", "get-url", "origin"])
    branch = _run_git_command(path, ["branch", "--show-current"])
    commit_count_str = _run_git_command(path, ["rev-list", "--count", "HEAD"])

    commit_count: int | None = None
    if commit_count_str is not None:
        try:
            commit_count = int(commit_count_str)
        except ValueError:
            pass

    return {
        "is_repo": True,
        "remote": remote,
        "branch": branch,
        "commit_count": commit_count,
    }


def _count_files(path: Path) -> int:
    """Count all non-hidden files, excluding skip directories."""
    return len(_iter_files(path))


def _find_database_files(path: Path) -> list[Path]:
    """Find SQLite database files in the project root and common subdirectories."""
    db_files: list[Path] = []
    search_dirs = [path] + [path / d for d in _DB_SEARCH_DIRS]

    for search_dir in search_dirs:
        if not search_dir.is_dir():
            continue
        try:
            for entry in search_dir.iterdir():
                if not entry.is_file():
                    continue
                if entry.suffix.lower() not in _DB_EXTENSIONS:
                    continue
                try:
                    size = entry.stat().st_size
                    if size > _MAX_DB_SIZE_BYTES:
                        continue
                    db_files.append(entry)
                except OSError:
                    continue
        except PermissionError:
            continue

    # Deduplicate (root scan might overlap with subdir scan)
    seen: set[Path] = set()
    unique: list[Path] = []
    for db_path in db_files:
        resolved = db_path.resolve()
        if resolved not in seen:
            seen.add(resolved)
            unique.append(db_path)
    return unique


def _read_db_schema(db_path: Path, project_root: Path) -> dict[str, Any] | None:
    """Read schema information from a SQLite database file.

    Returns a dict with path, size_mb, and tables info, or None on error.
    """
    try:
        size_mb = round(db_path.stat().st_size / (1024 * 1024), 2)
    except OSError:
        return None

    try:
        conn = sqlite3.connect(str(db_path), timeout=5)
        conn.execute("PRAGMA journal_mode=WAL")
    except (sqlite3.Error, OSError):
        return None

    try:
        # Verify it's a valid SQLite database
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
        table_names = [row[0] for row in cursor.fetchall()]

        tables: list[dict[str, Any]] = []
        for table_name in table_names:
            columns_info: list[dict[str, str]] = []
            try:
                col_cursor = conn.execute(f"PRAGMA table_info([{table_name}])")
                for col_row in col_cursor.fetchall():
                    columns_info.append({
                        "name": col_row[1],
                        "type": col_row[2] or "UNKNOWN",
                    })
            except sqlite3.Error:
                continue

            # Row count with safety limit
            row_count: int | str
            try:
                count_cursor = conn.execute(f"SELECT COUNT(*) FROM [{table_name}]")
                count = count_cursor.fetchone()[0]
                row_count = f"{_ROW_COUNT_LIMIT}+" if count > _ROW_COUNT_LIMIT else count
            except sqlite3.Error:
                row_count = "unknown"

            tables.append({
                "name": table_name,
                "columns": columns_info,
                "row_count": row_count,
            })

        conn.close()

        # Build relative path from project root
        try:
            rel_path = str(db_path.resolve().relative_to(project_root.resolve()))
        except ValueError:
            rel_path = str(db_path)

        return {
            "path": rel_path,
            "size_mb": size_mb,
            "tables": tables,
        }
    except sqlite3.Error:
        try:
            conn.close()
        except sqlite3.Error:
            pass
        return None


def _detect_databases(path: Path) -> list[dict[str, Any]]:
    """Detect SQLite databases and read their schemas."""
    db_files = _find_database_files(path)
    databases: list[dict[str, Any]] = []
    for db_path in db_files:
        schema = _read_db_schema(db_path, path)
        if schema is not None:
            databases.append(schema)
    return databases
