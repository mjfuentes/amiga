"""Tests for projects.cli module."""

import json
import sys
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from projects import registry
from projects.cli import cmd_init, cmd_list, cmd_switch


@pytest.fixture
def mock_registry_path(tmp_path):
    """Redirect registry to a temp directory."""
    reg_path = tmp_path / "data" / "projects.json"
    with patch.object(registry, "REGISTRY_PATH", reg_path):
        yield reg_path


@pytest.fixture
def project_dir(tmp_path):
    """Create a minimal project directory."""
    proj = tmp_path / "my-project"
    proj.mkdir()
    (proj / ".git").mkdir()
    (proj / "main.py").write_text("print('hello')")
    (proj / "utils.py").write_text("def helper(): pass")
    (proj / "requirements.txt").write_text("flask")
    return proj


class TestCmdInit:
    def test_init_creates_profile(self, mock_registry_path, project_dir, capsys):
        cmd_init(str(project_dir))
        profile_path = project_dir / ".amiga" / "profile.json"
        assert profile_path.exists()
        profile = json.loads(profile_path.read_text())
        assert profile["name"] == "my-project"
        assert "python" in profile["languages"]

    def test_init_registers_globally(self, mock_registry_path, project_dir, capsys):
        cmd_init(str(project_dir))
        projects = registry.list_projects()
        assert len(projects) == 1
        assert projects[0]["name"] == "my-project"

    def test_init_sets_active(self, mock_registry_path, project_dir, capsys):
        cmd_init(str(project_dir))
        active = registry.get_active_project()
        assert active is not None
        assert active["name"] == "my-project"

    def test_init_prints_summary(self, mock_registry_path, project_dir, capsys):
        cmd_init(str(project_dir))
        output = capsys.readouterr().out
        assert "my-project" in output
        assert "python" in output
        assert "profile.json" in output

    def test_init_invalid_path_exits(self, mock_registry_path, tmp_path):
        with pytest.raises(SystemExit):
            cmd_init(str(tmp_path / "nonexistent"))


class TestCmdList:
    def test_list_empty(self, mock_registry_path, capsys):
        cmd_list()
        output = capsys.readouterr().out
        assert "No projects registered" in output

    def test_list_shows_projects(self, mock_registry_path, project_dir, capsys):
        cmd_init(str(project_dir))
        capsys.readouterr()  # clear init output

        cmd_list()
        output = capsys.readouterr().out
        assert "my-project" in output
        assert "*" in output  # active marker

    def test_list_shows_active_marker(self, mock_registry_path, tmp_path, capsys):
        # Create two projects
        proj1 = tmp_path / "proj1"
        proj1.mkdir()
        (proj1 / "app.py").write_text("")

        proj2 = tmp_path / "proj2"
        proj2.mkdir()
        (proj2 / "index.js").write_text("")

        cmd_init(str(proj1))
        cmd_init(str(proj2))
        capsys.readouterr()  # clear

        cmd_list()
        output = capsys.readouterr().out
        # proj2 was init'd last, so it's active
        lines = output.strip().split("\n")
        for line in lines:
            if "proj2" in line:
                assert "*" in line
            elif "proj1" in line:
                assert "*" not in line


class TestCmdSwitch:
    def test_switch_by_name(self, mock_registry_path, tmp_path, capsys):
        proj1 = tmp_path / "alpha"
        proj1.mkdir()
        (proj1 / "main.py").write_text("")

        proj2 = tmp_path / "beta"
        proj2.mkdir()
        (proj2 / "app.js").write_text("")

        cmd_init(str(proj1))
        cmd_init(str(proj2))
        capsys.readouterr()

        cmd_switch("alpha")
        active = registry.get_active_project()
        assert active["name"] == "alpha"

        output = capsys.readouterr().out
        assert "Switched to: alpha" in output

    def test_switch_by_path(self, mock_registry_path, project_dir, capsys):
        cmd_init(str(project_dir))
        capsys.readouterr()

        cmd_switch(str(project_dir))
        output = capsys.readouterr().out
        assert "Switched to:" in output

    def test_switch_unknown_exits(self, mock_registry_path, capsys):
        with pytest.raises(SystemExit):
            cmd_switch("nonexistent-project")

    def test_switch_empty_name_exits(self, mock_registry_path, capsys):
        with pytest.raises(SystemExit):
            cmd_switch("")
