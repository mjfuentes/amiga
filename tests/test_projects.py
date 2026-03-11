"""Tests for projects.registry and projects.scanner modules."""

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from projects.registry import (
    _read_registry,
    _write_registry,
    get_active_project,
    list_projects,
    register_project,
    set_active_project,
    unregister_project,
)
from projects.scanner import scan_project


class TestRegistry:
    """Tests for project registry CRUD operations."""

    def test_list_projects_empty(self, tmp_path):
        """Empty registry returns empty list."""
        registry_file = tmp_path / "projects.json"
        with patch("projects.registry.REGISTRY_PATH", registry_file):
            result = list_projects()
            assert result == []

    def test_register_and_list_project(self, tmp_path):
        """Registering a project makes it visible in list."""
        registry_file = tmp_path / "projects.json"
        profile = {
            "name": "test-project",
            "path": "/tmp/test-project",
            "primary_language": "Python",
            "frameworks": ["Flask"],
        }
        with patch("projects.registry.REGISTRY_PATH", registry_file):
            register_project(profile)
            projects = list_projects()
            assert len(projects) == 1
            assert projects[0]["name"] == "test-project"
            assert projects[0]["path"] == "/tmp/test-project"
            assert projects[0]["primary_language"] == "Python"

    def test_register_project_replaces_existing(self, tmp_path):
        """Re-registering same path updates the entry."""
        registry_file = tmp_path / "projects.json"
        profile_v1 = {
            "name": "my-app",
            "path": "/tmp/my-app",
            "primary_language": "JavaScript",
            "frameworks": [],
        }
        profile_v2 = {
            "name": "my-app",
            "path": "/tmp/my-app",
            "primary_language": "TypeScript",
            "frameworks": ["React"],
        }
        with patch("projects.registry.REGISTRY_PATH", registry_file):
            register_project(profile_v1)
            register_project(profile_v2)
            projects = list_projects()
            assert len(projects) == 1
            assert projects[0]["primary_language"] == "TypeScript"

    def test_register_project_missing_path_raises(self, tmp_path):
        """Profile without path field raises ValueError."""
        registry_file = tmp_path / "projects.json"
        with patch("projects.registry.REGISTRY_PATH", registry_file):
            with pytest.raises(ValueError, match="path"):
                register_project({"name": "no-path"})

    def test_set_and_get_active_project(self, tmp_path):
        """Setting active project makes it retrievable."""
        registry_file = tmp_path / "projects.json"
        profile = {
            "name": "active-test",
            "path": "/tmp/active-test",
            "primary_language": "Go",
            "frameworks": [],
        }
        with patch("projects.registry.REGISTRY_PATH", registry_file):
            register_project(profile)
            result = set_active_project("/tmp/active-test")
            assert result is True

            active = get_active_project()
            assert active is not None
            assert active["path"] == "/tmp/active-test"

    def test_set_active_unknown_path_returns_false(self, tmp_path):
        """Setting active to unregistered path returns False."""
        registry_file = tmp_path / "projects.json"
        with patch("projects.registry.REGISTRY_PATH", registry_file):
            result = set_active_project("/nonexistent")
            assert result is False

    def test_get_active_project_none_when_empty(self, tmp_path):
        """No active project returns None."""
        registry_file = tmp_path / "projects.json"
        with patch("projects.registry.REGISTRY_PATH", registry_file):
            assert get_active_project() is None

    def test_unregister_project(self, tmp_path):
        """Unregistering removes the project from the list."""
        registry_file = tmp_path / "projects.json"
        profile = {
            "name": "removable",
            "path": "/tmp/removable",
            "primary_language": "Rust",
            "frameworks": [],
        }
        with patch("projects.registry.REGISTRY_PATH", registry_file):
            register_project(profile)
            assert len(list_projects()) == 1

            removed = unregister_project("/tmp/removable")
            assert removed is True
            assert len(list_projects()) == 0

    def test_unregister_nonexistent_returns_false(self, tmp_path):
        """Unregistering non-existent project returns False."""
        registry_file = tmp_path / "projects.json"
        with patch("projects.registry.REGISTRY_PATH", registry_file):
            assert unregister_project("/nope") is False

    def test_unregister_clears_active(self, tmp_path):
        """Unregistering the active project clears active."""
        registry_file = tmp_path / "projects.json"
        profile = {
            "name": "active-remove",
            "path": "/tmp/active-remove",
            "primary_language": "Python",
            "frameworks": [],
        }
        with patch("projects.registry.REGISTRY_PATH", registry_file):
            register_project(profile)
            set_active_project("/tmp/active-remove")
            assert get_active_project() is not None

            unregister_project("/tmp/active-remove")
            assert get_active_project() is None

    def test_corrupted_registry_file(self, tmp_path):
        """Corrupted JSON file returns empty state."""
        registry_file = tmp_path / "projects.json"
        registry_file.write_text("not json {{{")
        with patch("projects.registry.REGISTRY_PATH", registry_file):
            result = list_projects()
            assert result == []

    def test_multiple_projects(self, tmp_path):
        """Multiple projects can be registered and listed."""
        registry_file = tmp_path / "projects.json"
        with patch("projects.registry.REGISTRY_PATH", registry_file):
            for i in range(3):
                register_project({
                    "name": f"proj-{i}",
                    "path": f"/tmp/proj-{i}",
                    "primary_language": "Python",
                    "frameworks": [],
                })
            projects = list_projects()
            assert len(projects) == 3


class TestScanner:
    """Tests for project scanner."""

    def test_scan_empty_directory(self, tmp_path):
        """Scanning an empty directory returns minimal profile."""
        profile = scan_project(tmp_path)
        assert profile["name"] == tmp_path.name
        assert profile["path"] == str(tmp_path)
        assert profile["primary_language"] is None or profile["primary_language"] == "Unknown"
        assert profile["git"]["is_repo"] is False
        assert profile["file_count"] == 0

    def test_scan_python_project(self, tmp_path):
        """Scanning a Python project detects language."""
        (tmp_path / "main.py").write_text("print('hello')")
        (tmp_path / "utils.py").write_text("def helper(): pass")
        (tmp_path / "requirements.txt").write_text("flask\nrequests\n")

        profile = scan_project(tmp_path)
        assert profile["primary_language"] == "python"
        assert profile["file_count"] >= 2

    def test_scan_javascript_project(self, tmp_path):
        """Scanning a JS project with package.json detects React."""
        (tmp_path / "index.js").write_text("console.log('hi')")
        pkg = {"dependencies": {"react": "^18.0.0"}, "devDependencies": {"typescript": "^5.0.0"}}
        (tmp_path / "package.json").write_text(json.dumps(pkg))

        profile = scan_project(tmp_path)
        assert profile["primary_language"] == "javascript"

    def test_scan_detects_git(self, tmp_path):
        """Scanner detects .git directory."""
        (tmp_path / ".git").mkdir()
        (tmp_path / "main.py").write_text("")
        profile = scan_project(tmp_path)
        assert profile["git"]["is_repo"] is True

    def test_scan_basic_structure(self, tmp_path):
        """Scanner returns expected top-level keys."""
        (tmp_path / "app.py").write_text("")
        profile = scan_project(tmp_path)
        assert "name" in profile
        assert "path" in profile
        assert "primary_language" in profile
        assert "frameworks" in profile
        assert "file_count" in profile
        assert "git" in profile

    def test_scan_nonexistent_raises(self):
        """Scanning a non-existent path raises."""
        with pytest.raises((ValueError, FileNotFoundError)):
            scan_project(Path("/tmp/definitely-does-not-exist-abc123"))

    def test_scan_detects_package_manager(self, tmp_path):
        """Scanner detects package manager from lock files."""
        (tmp_path / "package.json").write_text("{}")
        (tmp_path / "pnpm-lock.yaml").write_text("")
        (tmp_path / "index.js").write_text("")
        profile = scan_project(tmp_path)
        assert profile["package_manager"] == "pnpm"

    def test_scan_multiple_languages(self, tmp_path):
        """Scanner handles projects with multiple languages."""
        (tmp_path / "app.py").write_text("")
        (tmp_path / "utils.py").write_text("")
        (tmp_path / "script.js").write_text("")
        profile = scan_project(tmp_path)
        assert "python" in profile["languages"]
        assert profile["primary_language"] == "python"
