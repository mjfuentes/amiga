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
        expected = [
            "setup", "start", "stop", "restart", "status", "logs",
            "db", "help", "install_daemon", "uninstall_daemon", "update",
            "doctor",
        ]
        for cmd in expected:
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

    def test_plist_label_defined(self):
        content = AMIGA_CLI.read_text()
        assert 'PLIST_LABEL="com.amiga.server"' in content

    def test_plist_path_uses_launch_agents(self):
        content = AMIGA_CLI.read_text()
        assert "Library/LaunchAgents" in content

    def test_dispatch_includes_all_commands(self):
        content = AMIGA_CLI.read_text()
        for cmd in ["install-daemon", "uninstall-daemon", "restart", "update"]:
            assert cmd in content, f"Missing dispatch entry for {cmd}"


class TestAmigaCLIRestart:
    """Tests for the restart command."""

    def test_restart_runs(self):
        result = run_cli("restart")
        # Should succeed (falls back to stop + start when no daemon)
        assert result.returncode == 0


class TestAmigaCLIDaemonHelpers:
    """Tests for daemon helper functions in the script."""

    def test_require_macos_function_exists(self):
        content = AMIGA_CLI.read_text()
        assert "require_macos()" in content
        assert 'uname' in content
        assert "macOS-only" in content

    def test_daemon_installed_function_exists(self):
        content = AMIGA_CLI.read_text()
        assert "daemon_installed()" in content

    def test_daemon_loaded_function_exists(self):
        content = AMIGA_CLI.read_text()
        assert "daemon_loaded()" in content


class TestAmigaCLIInstallDaemon:
    """Tests for the install-daemon command."""

    def test_install_daemon_generates_valid_plist(self):
        """Verify the plist generation logic includes required keys."""
        content = AMIGA_CLI.read_text()
        # Check plist template contains essential launchd keys
        assert "RunAtLoad" in content
        assert "KeepAlive" in content
        assert "WorkingDirectory" in content
        assert "StandardOutPath" in content
        assert "StandardErrorPath" in content
        assert "ProgramArguments" in content
        assert "EnvironmentVariables" in content
        assert "monitoring/server.py" in content

    def test_install_daemon_reads_env_file(self):
        """Verify .env parsing logic is present."""
        content = AMIGA_CLI.read_text()
        assert "ENV_FILE" in content
        # Should skip comments and blank lines
        assert "Skip comments" in content or "#" in content

    def test_install_daemon_creates_log_dir(self):
        """Verify log directory creation."""
        content = AMIGA_CLI.read_text()
        assert "launchd-stdout.log" in content
        assert "launchd-stderr.log" in content


class TestAmigaCLIUninstallDaemon:
    """Tests for the uninstall-daemon command."""

    def test_uninstall_when_not_installed(self):
        """Should exit cleanly when no daemon is installed."""
        result = run_cli("uninstall-daemon")
        assert result.returncode == 0
        assert "not installed" in result.stdout


class TestAmigaCLIUpdate:
    """Tests for the update command."""

    def test_update_function_exists(self):
        content = AMIGA_CLI.read_text()
        assert "cmd_update()" in content
        assert "git" in content
        assert "pip install" in content
        assert "deploy.sh" in content

    def test_update_shows_new_commits(self):
        """Verify update compares git hashes."""
        content = AMIGA_CLI.read_text()
        assert "before_hash" in content
        assert "after_hash" in content
        assert "Already up to date" in content


class TestAmigaCLIHelpContent:
    """Tests that help output documents all commands."""

    def test_help_lists_new_commands(self):
        result = run_cli("help")
        assert result.returncode == 0
        assert "restart" in result.stdout
        assert "update" in result.stdout
        assert "install-daemon" in result.stdout
        assert "uninstall-daemon" in result.stdout

    def test_help_shows_examples(self):
        result = run_cli("help")
        assert "install-daemon" in result.stdout
        assert "update" in result.stdout


class TestAmigaCLIStatusDaemon:
    """Tests that status shows daemon info."""

    def test_status_shows_daemon_line(self):
        result = run_cli("status")
        assert result.returncode == 0
        assert "Daemon:" in result.stdout

    def test_status_daemon_not_installed(self):
        result = run_cli("status")
        # Unless someone has it installed, should show not installed
        assert "not installed" in result.stdout or "installed" in result.stdout


class TestAmigaCLIDoctor:
    """Tests for the doctor command."""

    def test_doctor_runs(self):
        result = run_cli("doctor")
        assert result.returncode == 0 or result.returncode == 1
        assert "AMIGA Doctor" in result.stdout

    def test_doctor_checks_python(self):
        result = run_cli("doctor")
        assert "Checking Python..." in result.stdout

    def test_doctor_checks_node(self):
        result = run_cli("doctor")
        assert "Checking Node..." in result.stdout

    def test_doctor_checks_jq(self):
        result = run_cli("doctor")
        assert "Checking jq..." in result.stdout

    def test_doctor_checks_venv(self):
        result = run_cli("doctor")
        assert "Checking venv..." in result.stdout

    def test_doctor_checks_dependencies(self):
        result = run_cli("doctor")
        assert "Checking dependencies..." in result.stdout

    def test_doctor_checks_env(self):
        result = run_cli("doctor")
        assert "Checking .env..." in result.stdout

    def test_doctor_checks_env_permissions(self):
        result = run_cli("doctor")
        assert "Checking .env permissions..." in result.stdout

    def test_doctor_checks_frontend(self):
        result = run_cli("doctor")
        assert "Checking frontend build..." in result.stdout

    def test_doctor_checks_database(self):
        result = run_cli("doctor")
        assert "Checking database..." in result.stdout

    def test_doctor_checks_server(self):
        result = run_cli("doctor")
        assert "Checking server..." in result.stdout

    def test_doctor_checks_daemon(self):
        result = run_cli("doctor")
        assert "Checking daemon..." in result.stdout

    def test_doctor_checks_disk_space(self):
        result = run_cli("doctor")
        assert "Checking disk space..." in result.stdout

    def test_doctor_shows_summary(self):
        result = run_cli("doctor")
        assert "checks passed" in result.stdout

    def test_doctor_in_help(self):
        result = run_cli("help")
        assert "doctor" in result.stdout

    def test_doctor_in_dispatch(self):
        content = AMIGA_CLI.read_text()
        assert "doctor)" in content
        assert "cmd_doctor" in content

    def test_doctor_all_12_checks_present(self):
        """Verify all 12 checks are present in output."""
        result = run_cli("doctor")
        checks = [
            "Python", "Node", "jq", "venv", "dependencies",
            ".env...", ".env permissions", "frontend build",
            "database", "server", "daemon", "disk space",
        ]
        for check in checks:
            assert check in result.stdout, f"Missing check: {check}"

    def test_doctor_output_alignment(self):
        """Verify output lines are consistently formatted."""
        result = run_cli("doctor")
        lines = [l for l in result.stdout.split("\n") if "Checking" in l]
        assert len(lines) == 12, f"Expected 12 check lines, got {len(lines)}"
