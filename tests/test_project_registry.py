"""Tests for projects.registry module."""

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from projects import registry


@pytest.fixture
def mock_registry_path(tmp_path):
    """Redirect registry to a temp directory."""
    reg_path = tmp_path / "projects.json"
    with patch.object(registry, "REGISTRY_PATH", reg_path):
        yield reg_path


@pytest.fixture
def sample_profile():
    return {
        "name": "my-app",
        "path": "/home/user/projects/my-app",
        "primary_language": "Python",
        "languages": ["Python", "JavaScript"],
        "frameworks": ["Flask"],
        "package_manager": "pip",
        "test_framework": "pytest",
        "file_count": 42,
        "has_git": True,
    }


class TestRegisterProject:
    def test_register_new_project(self, mock_registry_path, sample_profile):
        registry.register_project(sample_profile)
        data = json.loads(mock_registry_path.read_text())
        assert sample_profile["path"] in data["projects"]
        entry = data["projects"][sample_profile["path"]]
        assert entry["name"] == "my-app"
        assert entry["primary_language"] == "Python"

    def test_register_overwrites_existing(self, mock_registry_path, sample_profile):
        registry.register_project(sample_profile)

        updated = {**sample_profile, "primary_language": "TypeScript", "frameworks": ["Next.js"]}
        registry.register_project(updated)

        data = json.loads(mock_registry_path.read_text())
        entry = data["projects"][sample_profile["path"]]
        assert entry["primary_language"] == "TypeScript"
        assert entry["frameworks"] == ["Next.js"]

    def test_register_preserves_added_at(self, mock_registry_path, sample_profile):
        registry.register_project(sample_profile)
        data = json.loads(mock_registry_path.read_text())
        first_added = data["projects"][sample_profile["path"]]["added_at"]

        registry.register_project(sample_profile)
        data = json.loads(mock_registry_path.read_text())
        assert data["projects"][sample_profile["path"]]["added_at"] == first_added

    def test_register_missing_path_raises(self, mock_registry_path):
        with pytest.raises(ValueError, match="path"):
            registry.register_project({"name": "broken"})


class TestListProjects:
    def test_empty_registry(self, mock_registry_path):
        assert registry.list_projects() == []

    def test_list_returns_all(self, mock_registry_path, sample_profile):
        registry.register_project(sample_profile)
        second = {**sample_profile, "name": "other", "path": "/other"}
        registry.register_project(second)

        projects = registry.list_projects()
        assert len(projects) == 2
        names = {p["name"] for p in projects}
        assert names == {"my-app", "other"}


class TestActiveProject:
    def test_no_active_initially(self, mock_registry_path):
        assert registry.get_active_project() is None

    def test_set_and_get_active(self, mock_registry_path, sample_profile):
        registry.register_project(sample_profile)
        result = registry.set_active_project(sample_profile["path"])
        assert result is True

        active = registry.get_active_project()
        assert active is not None
        assert active["name"] == "my-app"

    def test_set_active_unknown_path_returns_false(self, mock_registry_path):
        result = registry.set_active_project("/nonexistent")
        assert result is False

    def test_get_active_returns_none_when_path_not_in_registry(self, mock_registry_path):
        # Write a registry with active pointing to non-existent project
        mock_registry_path.write_text(json.dumps({
            "active": "/gone",
            "projects": {},
        }))
        assert registry.get_active_project() is None


class TestUnregisterProject:
    def test_unregister_existing(self, mock_registry_path, sample_profile):
        registry.register_project(sample_profile)
        result = registry.unregister_project(sample_profile["path"])
        assert result is True
        assert registry.list_projects() == []

    def test_unregister_nonexistent(self, mock_registry_path):
        result = registry.unregister_project("/not/here")
        assert result is False

    def test_unregister_clears_active(self, mock_registry_path, sample_profile):
        registry.register_project(sample_profile)
        registry.set_active_project(sample_profile["path"])
        registry.unregister_project(sample_profile["path"])
        assert registry.get_active_project() is None


class TestCorruptedRegistry:
    def test_malformed_json_returns_empty(self, mock_registry_path):
        mock_registry_path.write_text("not json{{{")
        projects = registry.list_projects()
        assert projects == []

    def test_missing_projects_key(self, mock_registry_path):
        mock_registry_path.write_text(json.dumps({"active": None}))
        projects = registry.list_projects()
        assert projects == []
