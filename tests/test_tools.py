"""
Tests for Claude API tool calling functionality
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import json
import sqlite3
import tempfile
from unittest.mock import Mock, patch

import pytest

from claude.tools import (
    AVAILABLE_TOOLS,
    SQLITE_TOOL,
    _validate_select_query,
    execute_sqlite_query,
    execute_tool,
)


class TestToolDefinitions:
    """Test tool definition structures."""

    def test_sqlite_tool_structure(self):
        """Test SQLite tool has required fields."""
        assert "name" in SQLITE_TOOL
        assert "description" in SQLITE_TOOL
        assert "input_schema" in SQLITE_TOOL
        assert SQLITE_TOOL["name"] == "query_database"

    def test_sqlite_tool_schema(self):
        """Test SQLite tool input schema."""
        schema = SQLITE_TOOL["input_schema"]
        assert schema["type"] == "object"
        assert "query" in schema["properties"]
        assert "database" in schema["properties"]
        assert "parameters" in schema["properties"]
        assert set(schema["required"]) == {"query", "database"}

    def test_available_tools_list(self):
        """Test AVAILABLE_TOOLS contains expected tools."""
        assert len(AVAILABLE_TOOLS) == 1
        assert AVAILABLE_TOOLS[0] == SQLITE_TOOL


class TestQueryValidation:
    """Test SQL query validation."""

    def test_valid_select_query(self):
        """Test valid SELECT query passes validation."""
        query = "SELECT * FROM tasks WHERE status='running'"
        is_valid, error = _validate_select_query(query)
        assert is_valid
        assert error is None

    def test_empty_query(self):
        """Test empty query fails validation."""
        is_valid, error = _validate_select_query("")
        assert not is_valid
        assert "empty" in error.lower()

    def test_non_select_query(self):
        """Test non-SELECT query fails validation."""
        queries = [
            "DELETE FROM tasks WHERE id=1",
            "UPDATE tasks SET status='failed'",
            "INSERT INTO tasks VALUES (1, 'test')",
            "DROP TABLE tasks",
        ]
        for query in queries:
            is_valid, error = _validate_select_query(query)
            assert not is_valid, f"Query should fail: {query}"
            assert error is not None

    def test_dangerous_patterns(self):
        """Test dangerous SQL patterns are rejected."""
        dangerous_queries = [
            "SELECT * FROM tasks; DROP TABLE tasks;",
            "SELECT * FROM tasks; DELETE FROM tasks",
            "SELECT PRAGMA table_info(tasks)",
            "SELECT * FROM tasks ATTACH DATABASE 'evil.db'",
        ]
        for query in dangerous_queries:
            is_valid, error = _validate_select_query(query)
            assert not is_valid, f"Dangerous query should fail: {query}"
            assert error is not None

    def test_query_with_comments(self):
        """Test query with comments is still validated correctly."""
        query = "SELECT * FROM tasks -- this is a comment"
        is_valid, error = _validate_select_query(query)
        assert is_valid
        assert error is None


class TestSQLiteExecution:
    """Test SQLite query execution."""

    @pytest.fixture
    def temp_db(self):
        """Create a temporary SQLite database for testing."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        # Create test database
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE tasks (
                task_id TEXT PRIMARY KEY,
                status TEXT,
                description TEXT
            )
        """
        )
        cursor.execute("INSERT INTO tasks VALUES ('task1', 'running', 'Test task 1')")
        cursor.execute("INSERT INTO tasks VALUES ('task2', 'completed', 'Test task 2')")
        cursor.execute("INSERT INTO tasks VALUES ('task3', 'failed', 'Test task 3')")
        conn.commit()
        conn.close()

        yield db_path

        # Cleanup
        Path(db_path).unlink()

    @pytest.mark.asyncio
    async def test_valid_query_execution(self, temp_db):
        """Test executing a valid SELECT query."""
        with patch("core.config.get_data_dir_for_cwd") as mock_get_data_dir:
            mock_get_data_dir.return_value = Path(temp_db).parent

            # Mock the database name to match temp file
            db_name = Path(temp_db).stem
            result = await execute_sqlite_query(
                query="SELECT task_id, status FROM tasks WHERE status='running'", database=db_name, parameters=None
            )

            result_data = json.loads(result)
            assert result_data["success"] is True
            assert result_data["row_count"] == 1
            assert len(result_data["results"]) == 1
            assert result_data["results"][0]["task_id"] == "task1"
            assert result_data["results"][0]["status"] == "running"

    @pytest.mark.asyncio
    async def test_invalid_query_rejected(self):
        """Test invalid query is rejected before execution."""
        result = await execute_sqlite_query(query="DELETE FROM tasks", database="agentlab", parameters=None)

        result_data = json.loads(result)
        assert result_data["success"] is False
        assert "error" in result_data
        assert "forbidden" in result_data["error"].lower() or "only select" in result_data["error"].lower()

    @pytest.mark.asyncio
    async def test_database_not_found(self):
        """Test handling of non-existent database."""
        with patch("core.config.get_data_dir_for_cwd") as mock_get_data_dir:
            mock_get_data_dir.return_value = Path("/nonexistent/path")

            result = await execute_sqlite_query(
                query="SELECT * FROM tasks", database="nonexistent", parameters=None
            )

            result_data = json.loads(result)
            assert result_data["success"] is False
            assert "not found" in result_data["error"].lower()

    @pytest.mark.asyncio
    async def test_row_limit_enforced(self, temp_db):
        """Test that row limit is enforced."""
        with patch("core.config.get_data_dir_for_cwd") as mock_get_data_dir:
            mock_get_data_dir.return_value = Path(temp_db).parent

            db_name = Path(temp_db).stem
            result = await execute_sqlite_query(
                query="SELECT * FROM tasks",  # Would return 3 rows without limit
                database=db_name,
                parameters=None,
            )

            result_data = json.loads(result)
            assert result_data["success"] is True
            # Should return all 3 since we're under the 100 row limit
            assert result_data["row_count"] == 3

    @pytest.mark.asyncio
    async def test_parameterized_query(self, temp_db):
        """Test executing a parameterized query."""
        with patch("core.config.get_data_dir_for_cwd") as mock_get_data_dir:
            mock_get_data_dir.return_value = Path(temp_db).parent

            db_name = Path(temp_db).stem
            result = await execute_sqlite_query(
                query="SELECT * FROM tasks WHERE status=?", database=db_name, parameters=["running"]
            )

            result_data = json.loads(result)
            assert result_data["success"] is True
            assert result_data["row_count"] == 1
            assert result_data["results"][0]["status"] == "running"


class TestToolDispatcher:
    """Test tool execution dispatcher."""

    @pytest.mark.asyncio
    async def test_execute_known_tool(self):
        """Test executing a known tool."""
        with patch("claude.tools.execute_sqlite_query") as mock_exec:
            mock_exec.return_value = json.dumps({"success": True, "row_count": 1, "results": []})

            result = await execute_tool(
                tool_name="query_database", tool_input={"query": "SELECT * FROM tasks", "database": "agentlab"}
            )

            mock_exec.assert_called_once()
            result_data = json.loads(result)
            assert result_data["success"] is True

    @pytest.mark.asyncio
    async def test_execute_unknown_tool(self):
        """Test executing an unknown tool returns error."""
        result = await execute_tool(tool_name="nonexistent_tool", tool_input={})

        result_data = json.loads(result)
        assert result_data["success"] is False
        assert "unknown tool" in result_data["error"].lower()


class TestErrorHandling:
    """Test error handling in tool execution."""

    @pytest.mark.asyncio
    async def test_sql_error_handling(self):
        """Test SQL errors are caught and returned."""
        with patch("core.config.get_data_dir_for_cwd") as mock_get_data_dir:
            mock_get_data_dir.return_value = Path("/tmp")

            # Create a temp db with no tables
            with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
                db_path = f.name
            conn = sqlite3.connect(db_path)
            conn.close()

            db_name = Path(db_path).stem
            result = await execute_sqlite_query(
                query="SELECT * FROM nonexistent_table",  # Table doesn't exist
                database=db_name,
                parameters=None,
            )

            result_data = json.loads(result)
            assert result_data["success"] is False
            assert "error" in result_data

            # Cleanup
            Path(db_path).unlink()
