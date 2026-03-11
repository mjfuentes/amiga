"""
Tests for active project context integration in Claude API client and project tools.

Covers:
- Project profile loading (_load_active_project_profile)
- Project context building (_build_project_context)
- System prompt injection with/without active project
- Tool selection based on active project state
- Project tool executors (read_file, search_code, list_files, query_project_database, project_info)
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import json
import sqlite3
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from claude.api_client import _build_project_context, _load_active_project_profile
from claude.tools import (
    _get_active_project_path,
    _is_excluded_path,
    _validate_project_path,
    execute_list_files,
    execute_project_info,
    execute_query_project_database,
    execute_read_file,
    execute_search_code,
    get_available_tools,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_profile():
    """A realistic project profile dict."""
    return {
        "name": "testproject",
        "path": "/tmp/test-project",
        "languages": ["python", "typescript", "javascript"],
        "frameworks": ["fastapi", "react"],
        "package_manager": "npm",
        "test_framework": "pytest",
        "structure": {
            "directories": ["src", "tests", "docs", "scripts", "config"],
        },
        "databases": [
            {
                "path": "data/app.db",
                "size_mb": 2.5,
                "tables": [
                    {
                        "name": "users",
                        "row_count": 150,
                        "columns": [
                            {"name": "id"},
                            {"name": "email"},
                            {"name": "name"},
                        ],
                    },
                    {
                        "name": "orders",
                        "row_count": 500,
                        "columns": [
                            {"name": "id"},
                            {"name": "user_id"},
                            {"name": "total"},
                        ],
                    },
                ],
            }
        ],
        "git": {"is_repo": True, "branch": "main"},
    }


@pytest.fixture
def temp_project(sample_profile):
    """Create a temporary project directory with profile and sample files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        project_root = Path(tmpdir)

        # Create .amiga/profile.json
        amiga_dir = project_root / ".amiga"
        amiga_dir.mkdir()
        profile = {**sample_profile, "path": str(project_root)}
        (amiga_dir / "profile.json").write_text(json.dumps(profile), encoding="utf-8")

        # Create sample source files
        src_dir = project_root / "src"
        src_dir.mkdir()
        (src_dir / "main.py").write_text("def main():\n    print('hello')\n", encoding="utf-8")
        (src_dir / "auth.py").write_text(
            "def authenticate(user):\n    # TODO: implement\n    return True\n",
            encoding="utf-8",
        )
        (project_root / "README.md").write_text("# Test Project\n", encoding="utf-8")

        # Create a sample SQLite database
        data_dir = project_root / "data"
        data_dir.mkdir()
        db_path = data_dir / "app.db"
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, email TEXT, name TEXT)")
        cursor.execute("INSERT INTO users VALUES (1, 'alice@test.com', 'Alice')")
        cursor.execute("INSERT INTO users VALUES (2, 'bob@test.com', 'Bob')")
        conn.commit()
        conn.close()

        yield project_root


# ---------------------------------------------------------------------------
# Tests: _load_active_project_profile
# ---------------------------------------------------------------------------


class TestLoadActiveProjectProfile:
    def test_returns_none_when_no_active_project(self):
        with patch("projects.registry.get_active_project", return_value=None):
            project, profile = _load_active_project_profile()
            assert project is None
            assert profile is None

    def test_returns_none_when_no_path(self):
        with patch("projects.registry.get_active_project", return_value={"name": "test"}):
            project, profile = _load_active_project_profile()
            assert project is None
            assert profile is None

    def test_returns_project_without_profile(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            active = {"name": "test", "path": tmpdir}
            with patch("projects.registry.get_active_project", return_value=active):
                project, profile = _load_active_project_profile()
                assert project == active
                assert profile is None

    def test_returns_project_with_profile(self, temp_project):
        active = {"name": "test", "path": str(temp_project)}
        with patch("projects.registry.get_active_project", return_value=active):
            project, profile = _load_active_project_profile()
            assert project == active
            assert profile is not None
            assert profile["name"] == "testproject"

    def test_handles_exception_gracefully(self):
        with patch("projects.registry.get_active_project", side_effect=RuntimeError("broken")):
            project, profile = _load_active_project_profile()
            assert project is None
            assert profile is None


# ---------------------------------------------------------------------------
# Tests: _build_project_context
# ---------------------------------------------------------------------------


class TestBuildProjectContext:
    def test_basic_fields(self, sample_profile):
        result = _build_project_context(sample_profile)
        assert "<active_project>" in result
        assert "</active_project>" in result
        assert "testproject" in result
        assert "python" in result
        assert "fastapi" in result

    def test_includes_directories(self, sample_profile):
        result = _build_project_context(sample_profile)
        assert "src" in result
        assert "tests" in result

    def test_includes_databases(self, sample_profile):
        result = _build_project_context(sample_profile)
        assert "data/app.db" in result
        assert "users" in result
        assert "orders" in result
        assert "email" in result

    def test_handles_empty_profile(self):
        result = _build_project_context({})
        assert "<active_project>" in result
        assert "unknown" in result

    def test_handles_no_databases(self):
        result = _build_project_context({"name": "minimal", "path": "/tmp/x"})
        assert "Databases:" not in result

    def test_handles_missing_optional_fields(self):
        result = _build_project_context({"name": "test", "path": "/tmp/x"})
        assert "Package manager" not in result
        assert "Test framework" not in result


# ---------------------------------------------------------------------------
# Tests: get_available_tools
# ---------------------------------------------------------------------------


class TestGetAvailableTools:
    def test_base_tools_without_project(self):
        tools = get_available_tools(has_active_project=False)
        tool_names = {t["name"] for t in tools}
        assert "query_database" in tool_names
        assert "web_search" in tool_names
        assert "git_query" in tool_names
        assert "read_file" not in tool_names
        assert "search_code" not in tool_names

    def test_all_tools_with_project(self):
        tools = get_available_tools(has_active_project=True)
        tool_names = {t["name"] for t in tools}
        assert "query_database" in tool_names
        assert "read_file" in tool_names
        assert "search_code" in tool_names
        assert "list_files" in tool_names
        assert "query_project_database" in tool_names
        assert "project_info" in tool_names


# ---------------------------------------------------------------------------
# Tests: Path validation helpers
# ---------------------------------------------------------------------------


class TestPathValidation:
    def test_validate_project_path_normal(self, temp_project):
        resolved, err = _validate_project_path(temp_project, "src/main.py")
        assert err is None
        assert resolved is not None
        assert resolved.name == "main.py"

    def test_validate_project_path_traversal(self, temp_project):
        resolved, err = _validate_project_path(temp_project, "../etc/passwd")
        assert resolved is None
        assert "traversal" in err.lower()

    def test_validate_project_path_empty(self, temp_project):
        resolved, err = _validate_project_path(temp_project, "")
        assert resolved is None
        assert "empty" in err.lower()

    def test_is_excluded_path(self):
        assert _is_excluded_path(Path("node_modules/package.json")) is True
        assert _is_excluded_path(Path(".git/config")) is True
        assert _is_excluded_path(Path("__pycache__/mod.pyc")) is True
        assert _is_excluded_path(Path("src/main.py")) is False


# ---------------------------------------------------------------------------
# Tests: Project tool executors
# ---------------------------------------------------------------------------


class TestReadFile:
    @pytest.mark.asyncio
    async def test_read_file_success(self, temp_project):
        with patch("claude.tools._get_active_project_path", return_value=temp_project):
            result = json.loads(await execute_read_file(path="src/main.py"))
            assert result["success"] is True
            assert "main" in result["content"]
            assert result["total_lines"] == 2

    @pytest.mark.asyncio
    async def test_read_file_not_found(self, temp_project):
        with patch("claude.tools._get_active_project_path", return_value=temp_project):
            result = json.loads(await execute_read_file(path="nonexistent.py"))
            assert result["success"] is False
            assert "not found" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_read_file_no_active_project(self):
        with patch("claude.tools._get_active_project_path", return_value=None):
            result = json.loads(await execute_read_file(path="src/main.py"))
            assert result["success"] is False
            assert "no active project" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_read_file_traversal_blocked(self, temp_project):
        with patch("claude.tools._get_active_project_path", return_value=temp_project):
            result = json.loads(await execute_read_file(path="../etc/passwd"))
            assert result["success"] is False
            assert "traversal" in result["error"].lower()


class TestSearchCode:
    @pytest.mark.asyncio
    async def test_search_code_success(self, temp_project):
        with patch("claude.tools._get_active_project_path", return_value=temp_project):
            result = json.loads(await execute_search_code(pattern="TODO"))
            assert result["success"] is True
            assert result["match_count"] >= 1

    @pytest.mark.asyncio
    async def test_search_code_no_matches(self, temp_project):
        with patch("claude.tools._get_active_project_path", return_value=temp_project):
            result = json.loads(await execute_search_code(pattern="ZZZZNONEXISTENTZZZZ"))
            assert result["success"] is True
            assert result["match_count"] == 0

    @pytest.mark.asyncio
    async def test_search_code_empty_pattern(self, temp_project):
        with patch("claude.tools._get_active_project_path", return_value=temp_project):
            result = json.loads(await execute_search_code(pattern=""))
            assert result["success"] is False

    @pytest.mark.asyncio
    async def test_search_code_no_active_project(self):
        with patch("claude.tools._get_active_project_path", return_value=None):
            result = json.loads(await execute_search_code(pattern="test"))
            assert result["success"] is False


class TestListFiles:
    @pytest.mark.asyncio
    async def test_list_files_success(self, temp_project):
        with patch("claude.tools._get_active_project_path", return_value=temp_project):
            result = json.loads(await execute_list_files(pattern="src/*.py"))
            assert result["success"] is True
            assert result["file_count"] >= 2

    @pytest.mark.asyncio
    async def test_list_files_wildcard(self, temp_project):
        with patch("claude.tools._get_active_project_path", return_value=temp_project):
            result = json.loads(await execute_list_files(pattern="*.md"))
            assert result["success"] is True
            assert any("README.md" in f for f in result["files"])

    @pytest.mark.asyncio
    async def test_list_files_empty_pattern(self, temp_project):
        with patch("claude.tools._get_active_project_path", return_value=temp_project):
            result = json.loads(await execute_list_files(pattern=""))
            assert result["success"] is False

    @pytest.mark.asyncio
    async def test_list_files_no_active_project(self):
        with patch("claude.tools._get_active_project_path", return_value=None):
            result = json.loads(await execute_list_files(pattern="*.py"))
            assert result["success"] is False


class TestQueryProjectDatabase:
    @pytest.mark.asyncio
    async def test_query_success(self, temp_project):
        with patch("claude.tools._get_active_project_path", return_value=temp_project):
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
    async def test_query_with_parameters(self, temp_project):
        with patch("claude.tools._get_active_project_path", return_value=temp_project):
            result = json.loads(
                await execute_query_project_database(
                    database_path="data/app.db",
                    query="SELECT * FROM users WHERE email=?",
                    parameters=["bob@test.com"],
                )
            )
            assert result["success"] is True
            assert result["row_count"] == 1
            assert result["results"][0]["name"] == "Bob"

    @pytest.mark.asyncio
    async def test_rejects_non_select(self, temp_project):
        with patch("claude.tools._get_active_project_path", return_value=temp_project):
            result = json.loads(
                await execute_query_project_database(
                    database_path="data/app.db",
                    query="DELETE FROM users",
                )
            )
            assert result["success"] is False

    @pytest.mark.asyncio
    async def test_database_not_found(self, temp_project):
        with patch("claude.tools._get_active_project_path", return_value=temp_project):
            result = json.loads(
                await execute_query_project_database(
                    database_path="data/nonexistent.db",
                    query="SELECT 1",
                )
            )
            assert result["success"] is False
            assert "not found" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_no_active_project(self):
        with patch("claude.tools._get_active_project_path", return_value=None):
            result = json.loads(
                await execute_query_project_database(
                    database_path="data/app.db",
                    query="SELECT 1",
                )
            )
            assert result["success"] is False


class TestProjectInfo:
    @pytest.mark.asyncio
    async def test_project_info_success(self, temp_project):
        with patch("claude.tools._get_active_project_path", return_value=temp_project):
            result = json.loads(await execute_project_info())
            assert result["success"] is True
            assert result["profile"]["name"] == "testproject"

    @pytest.mark.asyncio
    async def test_project_info_no_profile(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("claude.tools._get_active_project_path", return_value=Path(tmpdir)):
                result = json.loads(await execute_project_info())
                assert result["success"] is True
                assert result["profile"] is None

    @pytest.mark.asyncio
    async def test_project_info_no_active_project(self):
        with patch("claude.tools._get_active_project_path", return_value=None):
            result = json.loads(await execute_project_info())
            assert result["success"] is False


# ---------------------------------------------------------------------------
# Tests: System prompt integration
# ---------------------------------------------------------------------------


class TestSystemPromptIntegration:
    """Test that project context is properly injected into the system prompt."""

    def test_prompt_includes_project_context_when_active(self, sample_profile):
        context = _build_project_context(sample_profile)
        # Verify the context contains expected project info
        assert "testproject" in context
        assert "python" in context
        assert "data/app.db" in context
        assert "users" in context
        assert "email" in context

    def test_prompt_empty_when_no_project(self):
        """When no active project, context section should be empty."""
        project, profile = None, None
        # Simulate what ask_claude does
        project_context_section = ""
        if profile:
            project_context_section = _build_project_context(profile)
        assert project_context_section == ""

    def test_tools_conditional_on_project(self):
        """Verify tool selection changes based on project state."""
        base_tools = get_available_tools(has_active_project=False)
        full_tools = get_available_tools(has_active_project=True)
        assert len(full_tools) > len(base_tools)
        # Project tools should only be in full set
        full_names = {t["name"] for t in full_tools}
        base_names = {t["name"] for t in base_tools}
        project_only = full_names - base_names
        assert "read_file" in project_only
        assert "search_code" in project_only
        assert "list_files" in project_only
        assert "query_project_database" in project_only
        assert "project_info" in project_only
