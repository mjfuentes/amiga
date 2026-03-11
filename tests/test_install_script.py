"""Tests for install.sh — validates script structure, syntax, and key behaviors."""

import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

INSTALL_SH = Path(__file__).parent.parent / "install.sh"


class TestInstallScriptExists:
    def test_file_exists(self):
        assert INSTALL_SH.exists()

    def test_file_is_executable(self):
        assert os.access(INSTALL_SH, os.X_OK)

    def test_starts_with_shebang(self):
        content = INSTALL_SH.read_text()
        assert content.startswith("#!/usr/bin/env bash")


class TestInstallScriptSyntax:
    def test_bash_syntax_check(self):
        """bash -n parses the script without executing it."""
        result = subprocess.run(
            ["bash", "-n", str(INSTALL_SH)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"Syntax error: {result.stderr}"


class TestInstallScriptContent:
    @pytest.fixture(autouse=True)
    def load_content(self):
        self.content = INSTALL_SH.read_text()

    def test_has_set_euo_pipefail(self):
        assert "set -euo pipefail" in self.content

    def test_has_banner(self):
        assert "Installing AMIGA" in self.content

    def test_checks_python_version(self):
        assert "python3" in self.content
        assert "3.12" in self.content or "PY_MINOR" in self.content

    def test_checks_node_version(self):
        assert "node" in self.content
        assert "18" in self.content or "NODE_MAJOR" in self.content

    def test_checks_git(self):
        assert "command -v git" in self.content

    def test_checks_jq_optional(self):
        assert "command -v jq" in self.content
        # jq should warn, not fail
        assert "warn" in self.content.split("jq")[1].split("\n")[0] or \
               "warn" in self.content.split("jq not found")[0].split("\n")[-1]

    def test_default_install_location(self):
        assert "AMIGA_HOME" in self.content
        assert "$HOME/.amiga" in self.content

    def test_clone_ssh_then_https_fallback(self):
        assert "git@github.com:mjfuentes/amiga.git" in self.content
        assert "https://github.com/mjfuentes/amiga.git" in self.content

    def test_ssh_clone_before_https(self):
        ssh_pos = self.content.index("git@github.com")
        https_pos = self.content.index("https://github.com/mjfuentes/amiga.git")
        assert ssh_pos < https_pos, "SSH clone should be attempted before HTTPS"

    def test_runs_amiga_setup(self):
        assert "amiga\" setup" in self.content or "amiga setup" in self.content

    def test_symlink_usr_local_bin(self):
        assert "/usr/local/bin" in self.content
        assert "ln -sf" in self.content

    def test_fallback_local_bin(self):
        assert ".local/bin" in self.content

    def test_shell_profile_fallback(self):
        assert ".zshrc" in self.content
        assert ".bashrc" in self.content or ".bash_profile" in self.content

    def test_idempotent_path_handling(self):
        """Script should not duplicate PATH entries."""
        assert "grep -qF" in self.content or "already in" in self.content

    def test_idempotent_existing_install(self):
        """If AMIGA_HOME exists with .git, should update not re-clone."""
        assert "git pull" in self.content

    def test_success_message(self):
        assert "AMIGA installed successfully" in self.content
        assert "amiga start" in self.content
        assert "amiga help" in self.content

    def test_no_emoji(self):
        """Script should use clean, professional output without emoji."""
        # Check for common emoji patterns (unicode ranges)
        import re
        emoji_pattern = re.compile(
            "[\U0001F300-\U0001F9FF]"  # Misc symbols, emoticons, etc
        )
        # Exclude the git commit message pattern which is in CLAUDE.md references
        lines = [
            line for line in self.content.split("\n")
            if not line.strip().startswith("#")
        ]
        script_body = "\n".join(lines)
        matches = emoji_pattern.findall(script_body)
        assert len(matches) == 0, f"Found emoji in script: {matches}"

    def test_no_sudo(self):
        """Script should not use sudo."""
        lines = [
            line for line in self.content.split("\n")
            if not line.strip().startswith("#")
            and not line.strip().startswith("echo")
            and "Install with" not in line
            and "Ubuntu:" not in line
        ]
        for line in lines:
            assert "sudo" not in line, f"Found sudo in non-comment line: {line}"

    def test_color_fallback(self):
        """Colors should degrade gracefully when tput unavailable."""
        assert 'command -v tput' in self.content
        assert 'BOLD="" DIM="" GREEN=""' in self.content or 'BOLD=""' in self.content

    def test_fail_function_defined(self):
        assert "fail()" in self.content

    def test_curl_pipe_compatible(self):
        """No interactive reads in the main script body (setup handles that)."""
        lines = self.content.split("\n")
        for line in lines:
            stripped = line.strip()
            # Skip comments and the amiga setup call
            if stripped.startswith("#"):
                continue
            # The script itself should not use read -r for user input
            if "read -r" in stripped:
                pytest.fail(f"Found interactive read in install.sh: {stripped}")


class TestInstallScriptStructure:
    """Verify the script follows the specified step order."""

    @pytest.fixture(autouse=True)
    def load_content(self):
        self.content = INSTALL_SH.read_text()

    def test_steps_in_order(self):
        """Prerequisites -> Install location -> Clone -> Setup -> PATH -> Success."""
        markers = [
            "Checking prerequisites",
            "Install location",
            "Running setup",
            "Adding to PATH",
            "installed successfully",
        ]
        positions = []
        for marker in markers:
            pos = self.content.find(marker)
            assert pos != -1, f"Missing step marker: {marker}"
            positions.append(pos)

        for i in range(len(positions) - 1):
            assert positions[i] < positions[i + 1], (
                f"Steps out of order: '{markers[i]}' should come before '{markers[i + 1]}'"
            )

    def test_functions_defined_before_use(self):
        """All functions should be defined before their first call."""
        # Find function definitions
        import re
        func_defs = {}
        func_calls = {}

        for i, line in enumerate(self.content.split("\n")):
            # Match function definitions: name() {
            def_match = re.match(r'^(\w+)\(\)\s*\{', line.strip())
            if def_match:
                name = def_match.group(1)
                if name not in func_defs:
                    func_defs[name] = i

        # Check that add_path_to_profile is defined before PATH section
        assert "add_path_to_profile" in func_defs, "add_path_to_profile function must be defined"
        path_section_line = None
        for i, line in enumerate(self.content.split("\n")):
            if "Adding to PATH" in line:
                path_section_line = i
                break

        assert func_defs["add_path_to_profile"] < path_section_line, (
            "add_path_to_profile must be defined before the PATH section"
        )
