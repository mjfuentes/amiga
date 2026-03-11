"""Tests for the AMIGA CLI script (amiga) and uninstall.sh."""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent
CLI_PATH = PROJECT_ROOT / "amiga"
UNINSTALL_PATH = PROJECT_ROOT / "uninstall.sh"


class TestCLISyntax:
    """Verify both scripts parse without syntax errors."""

    def test_amiga_cli_syntax(self):
        result = subprocess.run(
            ["bash", "-n", str(CLI_PATH)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"Syntax error in amiga: {result.stderr}"

    def test_uninstall_sh_syntax(self):
        result = subprocess.run(
            ["bash", "-n", str(UNINSTALL_PATH)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"Syntax error in uninstall.sh: {result.stderr}"

    def test_uninstall_sh_is_executable(self):
        assert os.access(str(UNINSTALL_PATH), os.X_OK), "uninstall.sh is not executable"


class TestCLIHelp:
    """Verify help output includes all expected commands."""

    @pytest.fixture
    def help_output(self):
        result = subprocess.run(
            ["bash", str(CLI_PATH), "help"],
            capture_output=True,
            text=True,
        )
        return result.stdout

    def test_help_exits_zero(self):
        result = subprocess.run(
            ["bash", str(CLI_PATH), "help"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0

    def test_help_includes_setup(self, help_output):
        assert "setup" in help_output

    def test_help_includes_uninstall(self, help_output):
        assert "uninstall" in help_output
        assert "Remove AMIGA from your system" in help_output

    def test_help_includes_doctor(self, help_output):
        assert "doctor" in help_output

    def test_help_includes_all_commands(self, help_output):
        expected_commands = [
            "setup",
            "start",
            "stop",
            "restart",
            "status",
            "logs",
            "update",
            "doctor",
            "db",
            "install-daemon",
            "uninstall-daemon",
            "uninstall",
            "help",
        ]
        for cmd in expected_commands:
            assert cmd in help_output, f"Command '{cmd}' missing from help output"


class TestCLIDispatch:
    """Verify unknown commands fail with error."""

    def test_unknown_command_exits_nonzero(self):
        result = subprocess.run(
            ["bash", str(CLI_PATH), "nonexistent-command"],
            capture_output=True,
            text=True,
        )
        assert result.returncode != 0

    def test_unknown_command_shows_error(self):
        result = subprocess.run(
            ["bash", str(CLI_PATH), "nonexistent-command"],
            capture_output=True,
            text=True,
        )
        assert "Unknown command" in result.stderr


class TestSetupNodeCheck:
    """Verify cmd_setup includes Node.js version check."""

    def test_setup_script_contains_node_check(self):
        content = CLI_PATH.read_text()
        assert "Checking Node.js" in content
        assert "node --version" in content
        assert "NODE_MAJOR" in content
        assert "Node 18+" in content
        assert "nodejs.org" in content


class TestEnvPermissions:
    """Verify configure_env_interactive sets chmod 600."""

    def test_configure_env_sets_permissions(self):
        content = CLI_PATH.read_text()
        # Find the configure_env_interactive function and check for chmod
        func_start = content.index("configure_env_interactive()")
        func_end = content.index("\ncmd_start()", func_start)
        func_body = content[func_start:func_end]
        assert 'chmod 600 "$ENV_FILE"' in func_body


class TestUninstallCommand:
    """Verify cmd_uninstall function content."""

    def test_uninstall_function_exists(self):
        content = CLI_PATH.read_text()
        assert "cmd_uninstall()" in content

    def test_uninstall_asks_confirmation(self):
        content = CLI_PATH.read_text()
        func_start = content.index("cmd_uninstall()")
        func_end = content.index("\ncmd_update()", func_start)
        func_body = content[func_start:func_end]
        assert "Type 'yes' to confirm" in func_body

    def test_uninstall_removes_symlink(self):
        content = CLI_PATH.read_text()
        func_start = content.index("cmd_uninstall()")
        func_end = content.index("\ncmd_update()", func_start)
        func_body = content[func_start:func_end]
        assert "/usr/local/bin/amiga" in func_body

    def test_uninstall_cleans_shell_profiles(self):
        content = CLI_PATH.read_text()
        func_start = content.index("cmd_uninstall()")
        func_end = content.index("\ncmd_update()", func_start)
        func_body = content[func_start:func_end]
        assert ".zshrc" in func_body
        assert ".bashrc" in func_body
        assert "/.amiga" in func_body
        assert "# AMIGA" in func_body

    def test_uninstall_does_not_auto_delete_directory(self):
        content = CLI_PATH.read_text()
        func_start = content.index("cmd_uninstall()")
        func_end = content.index("\ncmd_update()", func_start)
        func_body = content[func_start:func_end]
        # Should suggest rm -rf but not execute it
        assert "rm -rf $SCRIPT_DIR" in func_body
        # The rm -rf should be in a dim() message, not a direct command
        assert 'dim "To remove all files: rm -rf $SCRIPT_DIR"' in func_body

    def test_uninstall_stops_server(self):
        content = CLI_PATH.read_text()
        func_start = content.index("cmd_uninstall()")
        func_end = content.index("\ncmd_update()", func_start)
        func_body = content[func_start:func_end]
        assert "is_running" in func_body
        assert "server_pid" in func_body

    def test_uninstall_unloads_daemon(self):
        content = CLI_PATH.read_text()
        func_start = content.index("cmd_uninstall()")
        func_end = content.index("\ncmd_update()", func_start)
        func_body = content[func_start:func_end]
        assert "daemon_installed" in func_body
        assert "launchctl unload" in func_body

    def test_uninstall_in_dispatch(self):
        content = CLI_PATH.read_text()
        assert 'uninstall)' in content
        assert 'cmd_uninstall' in content


class TestUninstallScript:
    """Verify standalone uninstall.sh content."""

    def test_script_exists(self):
        assert UNINSTALL_PATH.exists()

    def test_script_detects_amiga_home(self):
        content = UNINSTALL_PATH.read_text()
        assert "AMIGA_HOME" in content
        assert "$HOME/.amiga" in content

    def test_script_stops_server(self):
        content = UNINSTALL_PATH.read_text()
        assert f"lsof -ti:" in content

    def test_script_unloads_daemon(self):
        content = UNINSTALL_PATH.read_text()
        assert "launchctl unload" in content
        assert "PLIST_PATH" in content

    def test_script_removes_symlink(self):
        content = UNINSTALL_PATH.read_text()
        assert "/usr/local/bin/amiga" in content

    def test_script_cleans_shell_profiles(self):
        content = UNINSTALL_PATH.read_text()
        assert ".zshrc" in content
        assert ".bashrc" in content

    def test_script_asks_before_deleting_directory(self):
        content = UNINSTALL_PATH.read_text()
        assert "Delete $AMIGA_HOME" in content
        assert "rm -rf" in content

    def test_script_has_shebang(self):
        content = UNINSTALL_PATH.read_text()
        assert content.startswith("#!/usr/bin/env bash")

    def test_script_uses_strict_mode(self):
        content = UNINSTALL_PATH.read_text()
        assert "set -euo pipefail" in content
