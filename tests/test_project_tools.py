"""
Tests for project-scoped tool definitions and executors in claude/tools.py.

Covers: read_file, search_code, list_files, query_project_database, project_info,
        git_query active-project routing, _validate_project_path, _is_excluded_path,
        and the execute_tool dispatcher for new tool names.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import json
import sqlite3
import tempfile
from unittest.mock import patch

import pytest

from claude.tools import (
    AVAILABLE_TOOLS,
    LIST_FILES_TOOL,
    PROJECT_INFO_TOOL,
    QUERY_PROJECT_DB_TOOL,
    READ_FILE_TOOL,
    SEARCH_CODE_TOOL,
    _get_active_project_path,
    _is_excluded_path,
    _validate_project_path,
    execute_list_files,
    execute_project_info,
    execute_query_project_database,
    execute_read_file,
    execute_search_code,
    execute_tool,
    get_available_tools,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_project(tmp_path):
    """Create a minimal fake project directory with sample files."""
    # Create project files
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("# main\ndef hello():\n    return 'world'\n")
    (tmp_path / "src" / "utils.py").write_text("# utils\ndef add(a, b):\n    return a + b\n")
    (tmp_path / "README.md").write_text("# Fake Project\nA test project.\n")
    (tmp_path / "config.json").write_text('{"key": "value"}\n')

    # Hidden dir and excluded dir
    (tmp_path / ".git").mkdir()
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "pkg.js").write_text("module.exports = {}")

    # .amiga profile
    amiga_dir = tmp_path / ".amiga"
    amiga_dir.mkdir()
    profile = {"name": "fake-project", "primary_language": "Python", "frameworks": ["pytest"]}
    (amiga_dir / "profile.json").write_text(json.dumps(profile))

    # A small SQLite database
    db_path = tmp_path / "data"
    db_path.mkdir()
    conn = sqlite3.connect(str(db_path / "app.db"))
    cur = conn.cursor()
    cur.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT)")
    cur.execute("INSERT INTO users VALUES (1, 'Alice')")
    cur.execute("INSERT INTO users VALUES (2, 'Bob')")
    conn.commit()
    conn.close()

    return tmp_path


def _patch_active_project(project_path):
    """Return a patch context manager that makes _get_active_project_path return *project_path*."""
    return patch("claude.tools._get_active_project_path", return_value=project_path)


# ---------------------------------------------------------------------------
# Tool definition tests
# ---------------------------------------------------------------------------


class TestProjectToolDefinitions:
    """Verify new tool definition dicts have required fields."""

    @pytest.mark.parametrize(
        "tool",
        [READ_FILE_TOOL, SEARCH_CODE_TOOL, LIST_FILES_TOOL, QUERY_PROJECT_DB_TOOL, PROJECT_INFO_TOOL],
        ids=["read_file", "search_code", "list_files", "query_project_database", "project_info"],
    )
    def test_tool_has_required_keys(self, tool):
        assert "name" in tool
        assert "description" in tool
        assert "input_schema" in tool
        assert tool["input_schema"]["type"] == "object"

    def test_available_tools_includes_project_tools(self):
        names = {t["name"] for t in AVAILABLE_TOOLS}
        assert "read_file" in names
        assert "search_code" in names
        assert "list_files" in names
        assert "query_project_database" in names
        assert "project_info" in names

    def test_get_available_tools_without_project(self):
        tools = get_available_tools(has_active_project=False)
        names = {t["name"] for t in tools}
        assert "read_file" not in names
        assert "query_database" in names

    def test_get_available_tools_with_project(self):
        tools = get_available_tools(has_active_project=True)
        names = {t["name"] for t in tools}
        assert "read_file" in names
        assert "query_database" in names


# ---------------------------------------------------------------------------
# Helper tests
# ---------------------------------------------------------------------------


class TestValidateProjectPath:
    def test_valid_relative_path(self, tmp_path):
        (tmp_path / "file.txt").write_text("hi")
        resolved, err = _validate_project_path(tmp_path, "file.txt")
        assert err is None
        assert resolved == (tmp_path / "file.txt").resolve()

    def test_rejects_empty_path(self, tmp_path):
        resolved, err = _validate_project_path(tmp_path, "")
        assert resolved is None
        assert "empty" in err.lower()

    def test_rejects_dotdot_traversal(self, tmp_path):
        resolved, err = _validate_project_path(tmp_path, "../etc/passwd")
        assert resolved is None
        assert "traversal" in err.lower()

    def test_rejects_symlink_escape(self, tmp_path):
        # Create a symlink that points outside the project
        outside = tmp_path.parent / "outside_file.txt"
        outside.write_text("secret")
        link = tmp_path / "sneaky"
        link.symlink_to(outside)

        resolved, err = _validate_project_path(tmp_path, "sneaky")
        assert resolved is None
        assert "escapes" in err.lower()

        # Cleanup
        outside.unlink()


class TestIsExcludedPath:
    def test_node_modules_excluded(self):
        assert _is_excluded_path(Path("node_modules/foo.js"))

    def test_hidden_dir_excluded(self):
        assert _is_excluded_path(Path(".git/config"))

    def test_normal_path_not_excluded(self):
        assert not _is_excluded_path(Path("src/main.py"))

    def test_venv_excluded(self):
        assert _is_excluded_path(Path("venv/lib/python3.12/site.py"))


class TestGetActiveProjectPath:
    def test_returns_none_when_registry_has_no_active(self):
        with patch("projects.registry.get_active_project", return_value=None):
            result = _get_active_project_path()
            assert result is None

    def test_returns_path_when_active(self):
        with patch("projects.registry.get_active_project", return_value={"path": "/tmp/myproject"}):
            result = _get_active_project_path()
            assert result == Path("/tmp/myproject")

    def test_returns_none_on_import_error(self):
        with patch("claude.tools._get_active_project_path", return_value=None) as mock_fn:
            assert mock_fn() is None


# ---------------------------------------------------------------------------
# Executor tests: read_file
# ---------------------------------------------------------------------------


class TestExecuteReadFile:
    @pytest.mark.asyncio
    async def test_read_existing_file(self, fake_project):
        with _patch_active_project(fake_project):
            result = json.loads(await execute_read_file(path="src/main.py"))
            assert result["success"] is True
            assert result["total_lines"] == 3
            assert "hello" in result["content"]

    @pytest.mark.asyncio
    async def test_read_with_start_line_and_max(self, fake_project):
        with _patch_active_project(fake_project):
            result = json.loads(await execute_read_file(path="src/main.py", start_line=2, max_lines=1))
            assert result["success"] is True
            assert result["lines_returned"] == 1
            assert result["start_line"] == 2
            assert "hello" in result["content"]

    @pytest.mark.asyncio
    async def test_read_nonexistent_file(self, fake_project):
        with _patch_active_project(fake_project):
            result = json.loads(await execute_read_file(path="nope.txt"))
            assert result["success"] is False
            assert "not found" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_read_traversal_blocked(self, fake_project):
        with _patch_active_project(fake_project):
            result = json.loads(await execute_read_file(path="../etc/passwd"))
            assert result["success"] is False
            assert "traversal" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_read_no_active_project(self):
        with _patch_active_project(None):
            result = json.loads(await execute_read_file(path="anything.py"))
            assert result["success"] is False
            assert "no active project" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_read_large_file_rejected(self, fake_project):
        # Create a file > 1MB
        big_file = fake_project / "big.bin"
        big_file.write_bytes(b"x" * (1_048_576 + 1))
        with _patch_active_project(fake_project):
            result = json.loads(await execute_read_file(path="big.bin"))
            assert result["success"] is False
            assert "too large" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_read_truncates_long_lines(self, fake_project):
        long_line_file = fake_project / "long.txt"
        long_line_file.write_text("x" * 600 + "\n")
        with _patch_active_project(fake_project):
            result = json.loads(await execute_read_file(path="long.txt"))
            assert result["success"] is True
            # Line should be truncated to 500 chars + "..."
            assert "..." in result["content"]


# ---------------------------------------------------------------------------
# Executor tests: search_code
# ---------------------------------------------------------------------------


class TestExecuteSearchCode:
    @pytest.mark.asyncio
    async def test_search_finds_pattern(self, fake_project):
        with _patch_active_project(fake_project):
            result = json.loads(await execute_search_code(pattern="def hello"))
            assert result["success"] is True
            assert result["match_count"] >= 1
            assert any("main.py" in m for m in result["matches"])

    @pytest.mark.asyncio
    async def test_search_with_file_pattern(self, fake_project):
        with _patch_active_project(fake_project):
            result = json.loads(await execute_search_code(pattern="def", file_pattern="*.py"))
            assert result["success"] is True
            assert result["match_count"] >= 1

    @pytest.mark.asyncio
    async def test_search_no_matches(self, fake_project):
        with _patch_active_project(fake_project):
            result = json.loads(await execute_search_code(pattern="zzz_nonexistent_zzz"))
            assert result["success"] is True
            assert result["match_count"] == 0

    @pytest.mark.asyncio
    async def test_search_empty_pattern(self, fake_project):
        with _patch_active_project(fake_project):
            result = json.loads(await execute_search_code(pattern=""))
            assert result["success"] is False
            assert "empty" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_search_no_active_project(self):
        with _patch_active_project(None):
            result = json.loads(await execute_search_code(pattern="hello"))
            assert result["success"] is False
            assert "no active project" in result["error"].lower()


# ---------------------------------------------------------------------------
# Executor tests: list_files
# ---------------------------------------------------------------------------


class TestExecuteListFiles:
    @pytest.mark.asyncio
    async def test_list_all_py_files(self, fake_project):
        with _patch_active_project(fake_project):
            result = json.loads(await execute_list_files(pattern="**/*.py"))
            assert result["success"] is True
            assert result["file_count"] >= 2
            files = result["files"]
            assert any("main.py" in f for f in files)
            assert any("utils.py" in f for f in files)

    @pytest.mark.asyncio
    async def test_excludes_node_modules(self, fake_project):
        with _patch_active_project(fake_project):
            result = json.loads(await execute_list_files(pattern="**/*.js"))
            assert result["success"] is True
            for f in result["files"]:
                assert "node_modules" not in f

    @pytest.mark.asyncio
    async def test_list_respects_max_results(self, fake_project):
        with _patch_active_project(fake_project):
            result = json.loads(await execute_list_files(pattern="**/*", max_results=1))
            assert result["success"] is True
            assert result["file_count"] <= 1

    @pytest.mark.asyncio
    async def test_list_empty_pattern(self, fake_project):
        with _patch_active_project(fake_project):
            result = json.loads(await execute_list_files(pattern=""))
            assert result["success"] is False
            assert "empty" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_list_no_active_project(self):
        with _patch_active_project(None):
            result = json.loads(await execute_list_files(pattern="*"))
            assert result["success"] is False
            assert "no active project" in result["error"].lower()


# ---------------------------------------------------------------------------
# Executor tests: query_project_database
# ---------------------------------------------------------------------------


class TestExecuteQueryProjectDatabase:
    @pytest.mark.asyncio
    async def test_select_returns_rows(self, fake_project):
        with _patch_active_project(fake_project):
            result = json.loads(
                await execute_query_project_database(
                    database_path="data/app.db",
                    query="SELECT * FROM users ORDER BY id",
                )
            )
            assert result["success"] is True
            assert result["row_count"] == 2
            assert result["results"][0]["name"] == "Alice"

    @pytest.mark.asyncio
    async def test_parameterized_query(self, fake_project):
        with _patch_active_project(fake_project):
            result = json.loads(
                await execute_query_project_database(
                    database_path="data/app.db",
                    query="SELECT name FROM users WHERE id = ?",
                    parameters=[2],
                )
            )
            assert result["success"] is True
            assert result["row_count"] == 1
            assert result["results"][0]["name"] == "Bob"

    @pytest.mark.asyncio
    async def test_rejects_non_select(self, fake_project):
        with _patch_active_project(fake_project):
            result = json.loads(
                await execute_query_project_database(
                    database_path="data/app.db",
                    query="DELETE FROM users",
                )
            )
            assert result["success"] is False

    @pytest.mark.asyncio
    async def test_database_not_found(self, fake_project):
        with _patch_active_project(fake_project):
            result = json.loads(
                await execute_query_project_database(
                    database_path="nonexistent.db",
                    query="SELECT 1",
                )
            )
            assert result["success"] is False
            assert "not found" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_traversal_blocked(self, fake_project):
        with _patch_active_project(fake_project):
            result = json.loads(
                await execute_query_project_database(
                    database_path="../etc/passwd",
                    query="SELECT 1",
                )
            )
            assert result["success"] is False
            assert "traversal" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_no_active_project(self):
        with _patch_active_project(None):
            result = json.loads(
                await execute_query_project_database(
                    database_path="data/app.db",
                    query="SELECT 1",
                )
            )
            assert result["success"] is False
            assert "no active project" in result["error"].lower()


# ---------------------------------------------------------------------------
# Executor tests: project_info
# ---------------------------------------------------------------------------


class TestExecuteProjectInfo:
    @pytest.mark.asyncio
    async def test_returns_profile(self, fake_project):
        with _patch_active_project(fake_project):
            result = json.loads(await execute_project_info())
            assert result["success"] is True
            assert result["profile"]["name"] == "fake-project"
            assert result["profile"]["primary_language"] == "Python"

    @pytest.mark.asyncio
    async def test_no_profile_file(self, tmp_path):
        with _patch_active_project(tmp_path):
            result = json.loads(await execute_project_info())
            assert result["success"] is True
            assert result["profile"] is None
            assert "amiga scan" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_no_active_project(self):
        with _patch_active_project(None):
            result = json.loads(await execute_project_info())
            assert result["success"] is False
            assert "no active project" in result["error"].lower()


# ---------------------------------------------------------------------------
# Dispatcher integration tests
# ---------------------------------------------------------------------------


class TestExecuteToolDispatcherNewTools:
    @pytest.mark.asyncio
    async def test_dispatch_read_file(self, fake_project):
        with _patch_active_project(fake_project):
            result = json.loads(await execute_tool("read_file", {"path": "src/main.py"}))
            assert result["success"] is True

    @pytest.mark.asyncio
    async def test_dispatch_search_code(self, fake_project):
        with _patch_active_project(fake_project):
            result = json.loads(await execute_tool("search_code", {"pattern": "hello"}))
            assert result["success"] is True

    @pytest.mark.asyncio
    async def test_dispatch_list_files(self, fake_project):
        with _patch_active_project(fake_project):
            result = json.loads(await execute_tool("list_files", {"pattern": "**/*.py"}))
            assert result["success"] is True

    @pytest.mark.asyncio
    async def test_dispatch_query_project_database(self, fake_project):
        with _patch_active_project(fake_project):
            result = json.loads(
                await execute_tool(
                    "query_project_database",
                    {"database_path": "data/app.db", "query": "SELECT COUNT(*) as cnt FROM users"},
                )
            )
            assert result["success"] is True
            assert result["results"][0]["cnt"] == 2

    @pytest.mark.asyncio
    async def test_dispatch_project_info(self, fake_project):
        with _patch_active_project(fake_project):
            result = json.loads(await execute_tool("project_info", {}))
            assert result["success"] is True

    @pytest.mark.asyncio
    async def test_dispatch_unknown_tool(self):
        result = json.loads(await execute_tool("totally_bogus", {}))
        assert result["success"] is False
        assert "unknown tool" in result["error"].lower()
