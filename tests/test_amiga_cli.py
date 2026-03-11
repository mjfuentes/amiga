"""Tests for the ./amiga CLI script."""
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

PROJECT_ROOT = Path(__file__).parent.parent
AMIGA_CLI = PROJECT_ROOT / "amiga"


def run_cli(*args, input_text=None, env_override=None):
    """Run the amiga CLI and return result."""
    env = os.environ.copy()
    if env_override:
        env.update(env_override)
    result = subprocess.run(
        [str(AMIGA_CLI)] + list(args),
        capture_output=True,
        text=True,
        cwd=str(PROJECT_ROOT),
        env=env,
        input=input_text,
        timeout=30,
    )
    return result


class TestAmigaCLIHelp:
    """Tests for the help command and argument parsing."""

    def test_help_command(self):
        result = run_cli("help")
        assert result.returncode == 0
        assert "AMIGA" in result.stdout
        assert "setup" in result.stdout
        assert "start" in result.stdout
        assert "stop" in result.stdout
        assert "status" in result.stdout
        assert "logs" in result.stdout
        assert "db" in result.stdout

    def test_help_flag(self):
        result = run_cli("--help")
        assert result.returncode == 0
        assert "AMIGA" in result.stdout

    def test_h_flag(self):
        result = run_cli("-h")
        assert result.returncode == 0
        assert "AMIGA" in result.stdout

    def test_no_args_shows_help(self):
        result = run_cli()
        assert result.returncode == 0
        assert "AMIGA" in result.stdout

    def test_unknown_command_fails(self):
        result = run_cli("nonexistent")
        assert result.returncode == 1
        assert "Unknown command" in result.stderr


class TestAmigaCLIExecutable:
    """Tests that the script is properly configured."""

    def test_script_exists(self):
        assert AMIGA_CLI.exists()

    def test_script_is_executable(self):
        assert os.access(AMIGA_CLI, os.X_OK)

    def test_shebang_line(self):
        content = AMIGA_CLI.read_text()
        assert content.startswith("#!/usr/bin/env bash")


class TestAmigaCLIStatus:
    """Tests for the status command."""

    def test_status_runs(self):
        result = run_cli("status")
        assert result.returncode == 0
        assert "AMIGA Status" in result.stdout
        assert "Server:" in result.stdout

    def test_status_shows_server_state(self):
        result = run_cli("status")
        # Should show either "running" or "stopped"
        assert "running" in result.stdout or "stopped" in result.stdout


class TestAmigaCLIDb:
    """Tests for the db command."""

    def test_db_no_query_fails(self):
        result = run_cli("db")
        assert result.returncode == 1
        assert "Usage" in result.stderr or "SQL query" in result.stderr

    def test_db_with_query(self):
        if not (PROJECT_ROOT / "data" / "agentlab.db").exists():
            pytest.skip("No database file present")
        result = run_cli("db", "SELECT 1 as test;")
        assert result.returncode == 0
        assert "test" in result.stdout


class TestAmigaCLILogs:
    """Tests for the logs command behavior when no log file exists."""

    def test_logs_missing_file_errors(self):
        # If logs don't exist, should error gracefully
        log_path = PROJECT_ROOT / "logs" / "monitoring.log"
        if log_path.exists():
            pytest.skip("Log file exists, can't test missing-file path")
        result = run_cli("logs")
        assert result.returncode == 1
        assert "No log file" in result.stderr or "ERROR" in result.stderr


class TestAmigaCLIStop:
    """Tests for the stop command."""

    def test_stop_when_not_running(self):
        # Stop should be safe to call even when nothing is running
        result = run_cli("stop")
        assert result.returncode == 0
        assert "not running" in result.stdout or "Stopped" in result.stdout


class TestAmigaCLIScriptStructure:
    """Tests that validate the script content and structure."""

    def test_script_detects_own_directory(self):
        content = AMIGA_CLI.read_text()
        assert 'SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"' in content

    def test_all_commands_have_functions(self):
        content = AMIGA_CLI.read_text()
        for cmd in ["setup", "start", "stop", "status", "logs", "db", "help"]:
            assert f"cmd_{cmd}" in content, f"Missing function cmd_{cmd}"

    def test_set_flags(self):
        content = AMIGA_CLI.read_text()
        assert "set -euo pipefail" in content

    def test_color_graceful_degradation(self):
        content = AMIGA_CLI.read_text()
        # Should check for tput availability
        assert "tput" in content
        # Should have fallback empty strings
        assert 'BOLD=""' in content
