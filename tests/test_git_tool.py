"""
Tests for Git Tool

Tests the git_query tool for read-only git operations.
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import json
import pytest
from unittest.mock import patch, MagicMock
from claude.tools import execute_git_query, GIT_TOOL


class TestGitToolDefinition:
    """Test git tool schema definition"""

    def test_git_tool_schema(self):
        """Verify git tool has correct schema structure"""
        assert GIT_TOOL["name"] == "git_query"
        assert "description" in GIT_TOOL
        assert "input_schema" in GIT_TOOL
        
        schema = GIT_TOOL["input_schema"]
        assert schema["type"] == "object"
        assert "operation" in schema["properties"]
        assert schema["required"] == ["operation"]
        
    def test_git_operations_enum(self):
        """Verify allowed operations are defined"""
        operations = GIT_TOOL["input_schema"]["properties"]["operation"]["enum"]
        expected_ops = ["status", "log", "diff", "branch", "show"]
        assert set(operations) == set(expected_ops)


class TestGitQueryExecution:
    """Test git query execution"""

    @pytest.mark.asyncio
    async def test_git_status_success(self):
        """Test successful git status query"""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "## main...origin/main\n"
        mock_result.stderr = ""
        
        with patch("subprocess.run", return_value=mock_result):
            result = await execute_git_query("status")
            
        data = json.loads(result)
        assert data["success"] is True
        assert data["operation"] == "status"
        assert "main" in data["output"]

    @pytest.mark.asyncio
    async def test_git_log_with_limit(self):
        """Test git log with custom limit"""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "abc123 Recent commit\ndef456 Previous commit\n"
        mock_result.stderr = ""
        
        with patch("subprocess.run", return_value=mock_result) as mock_run:
            result = await execute_git_query("log", {"limit": 2})
            
        data = json.loads(result)
        assert data["success"] is True
        assert data["operation"] == "log"
        
        # Verify limit was applied
        call_args = mock_run.call_args
        assert "-2" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_git_log_max_limit(self):
        """Test git log respects maximum limit of 50"""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "commits...\n"
        mock_result.stderr = ""
        
        with patch("subprocess.run", return_value=mock_result) as mock_run:
            result = await execute_git_query("log", {"limit": 100})
            
        # Should cap at 50
        call_args = mock_run.call_args
        assert "-50" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_git_diff_with_file(self):
        """Test git diff for specific file"""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "claude/tools.py | 10 +++++++---\n"
        mock_result.stderr = ""
        
        with patch("subprocess.run", return_value=mock_result) as mock_run:
            result = await execute_git_query("diff", {"file_path": "claude/tools.py"})
            
        data = json.loads(result)
        assert data["success"] is True
        
        # Verify file path was passed
        call_args = mock_run.call_args
        assert "claude/tools.py" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_git_branch_list(self):
        """Test git branch listing"""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "* main\n  feature/test\n"
        mock_result.stderr = ""
        
        with patch("subprocess.run", return_value=mock_result):
            result = await execute_git_query("branch")
            
        data = json.loads(result)
        assert data["success"] is True
        assert "main" in data["output"]

    @pytest.mark.asyncio
    async def test_git_show_commit(self):
        """Test git show for specific commit"""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "abc123 Commit message\nfile.py | 5 ++---\n"
        mock_result.stderr = ""
        
        with patch("subprocess.run", return_value=mock_result) as mock_run:
            result = await execute_git_query("show", {"commit_hash": "abc123"})
            
        data = json.loads(result)
        assert data["success"] is True
        
        # Verify commit hash was passed
        call_args = mock_run.call_args
        assert "abc123" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_invalid_operation(self):
        """Test error handling for invalid operation"""
        result = await execute_git_query("invalid_op")
        
        data = json.loads(result)
        assert data["success"] is False
        assert "Invalid operation" in data["error"]

    @pytest.mark.asyncio
    async def test_git_command_failure(self):
        """Test handling of failed git command"""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "fatal: not a git repository"
        
        with patch("subprocess.run", return_value=mock_result):
            result = await execute_git_query("status")
            
        data = json.loads(result)
        assert data["success"] is False
        assert "git repository" in data["error"].lower()

    @pytest.mark.asyncio
    async def test_git_timeout(self):
        """Test handling of git command timeout"""
        from subprocess import TimeoutExpired
        
        with patch("subprocess.run", side_effect=TimeoutExpired("git", 10)):
            result = await execute_git_query("status")
            
        data = json.loads(result)
        assert data["success"] is False
        assert "timeout" in data["error"].lower() or "timed out" in data["error"].lower()

    @pytest.mark.asyncio
    async def test_git_unexpected_error(self):
        """Test handling of unexpected errors"""
        with patch("subprocess.run", side_effect=Exception("Unexpected error")):
            result = await execute_git_query("status")
            
        data = json.loads(result)
        assert data["success"] is False
        assert "Unexpected error" in data["error"]


class TestGitSecurityValidation:
    """Test security aspects of git tool"""

    @pytest.mark.asyncio
    async def test_only_read_operations(self):
        """Verify only read-only operations are supported"""
        allowed_ops = ["status", "log", "diff", "branch", "show"]
        dangerous_ops = ["commit", "push", "reset", "rebase", "merge"]
        
        tool_ops = GIT_TOOL["input_schema"]["properties"]["operation"]["enum"]
        
        # All allowed ops should be present
        for op in allowed_ops:
            assert op in tool_ops
            
        # Dangerous ops should not be present
        for op in dangerous_ops:
            assert op not in tool_ops

    @pytest.mark.asyncio
    async def test_command_injection_prevention(self):
        """Test that command injection is prevented"""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "output"
        mock_result.stderr = ""
        
        with patch("subprocess.run", return_value=mock_result) as mock_run:
            # Try to inject commands via file_path
            await execute_git_query("diff", {"file_path": "file.py; rm -rf /"})
            
        # Verify subprocess.run was called with list (not shell=True)
        call_args = mock_run.call_args
        assert call_args[1].get("shell", False) is False
        assert isinstance(call_args[0][0], list)
