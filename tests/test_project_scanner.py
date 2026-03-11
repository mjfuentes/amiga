"""Tests for projects.scanner module."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from projects.scanner import scan_project


class TestScanProject:
    """Tests for the project scanner."""

    def test_scan_empty_directory(self, tmp_path):
        profile = scan_project(tmp_path)
        assert profile["name"] == tmp_path.name
        assert profile["path"] == str(tmp_path)
        assert profile["languages"] == []
        assert profile["primary_language"] is None
        assert profile["file_count"] == 0
        assert profile["git"]["is_repo"] is False

    def test_scan_python_project(self, tmp_path):
        (tmp_path / "main.py").write_text("print('hello')")
        (tmp_path / "utils.py").write_text("def helper(): pass")
        (tmp_path / "requirements.txt").write_text("flask==3.0")
        profile = scan_project(tmp_path)
        assert "python" in profile["languages"]
        assert profile["primary_language"] == "python"
        assert profile["file_count"] == 3
        assert "flask" in profile["frameworks"]

    def test_scan_javascript_project(self, tmp_path):
        (tmp_path / "index.js").write_text("console.log('hi')")
        (tmp_path / "package.json").write_text(json.dumps({
            "dependencies": {"react": "^18.0.0", "express": "^4.0.0"}
        }))
        (tmp_path / "package-lock.json").write_text("{}")
        profile = scan_project(tmp_path)
        assert "javascript" in profile["languages"]
        assert profile["package_manager"] == "npm"
        assert "react" in profile["frameworks"]
        assert "express" in profile["frameworks"]

    def test_scan_typescript_project(self, tmp_path):
        (tmp_path / "app.ts").write_text("const x: number = 1")
        (tmp_path / "app.tsx").write_text("export default function() {}")
        profile = scan_project(tmp_path)
        assert "typescript" in profile["languages"]

    def test_scan_with_git(self, tmp_path):
        (tmp_path / ".git").mkdir()
        (tmp_path / "main.py").write_text("")
        profile = scan_project(tmp_path)
        assert profile["git"]["is_repo"] is True

    def test_scan_skips_node_modules(self, tmp_path):
        nm = tmp_path / "node_modules" / "lodash"
        nm.mkdir(parents=True)
        (nm / "index.js").write_text("module.exports = {}")
        (tmp_path / "app.js").write_text("")
        profile = scan_project(tmp_path)
        assert profile["file_count"] == 1

    def test_scan_skips_pycache(self, tmp_path):
        cache = tmp_path / "__pycache__"
        cache.mkdir()
        (cache / "main.cpython-312.pyc").write_text("")
        (tmp_path / "main.py").write_text("")
        profile = scan_project(tmp_path)
        assert profile["file_count"] == 1

    def test_scan_detects_pytest(self, tmp_path):
        (tmp_path / "conftest.py").write_text("")
        (tmp_path / "test_main.py").write_text("")
        profile = scan_project(tmp_path)
        assert profile["test_framework"] == "pytest"

    def test_scan_detects_jest(self, tmp_path):
        (tmp_path / "jest.config.js").write_text("module.exports = {}")
        profile = scan_project(tmp_path)
        assert profile["test_framework"] == "jest"

    def test_scan_detects_vitest(self, tmp_path):
        (tmp_path / "vitest.config.ts").write_text("")
        profile = scan_project(tmp_path)
        assert profile["test_framework"] == "vitest"

    def test_scan_detects_package_managers(self, tmp_path):
        (tmp_path / "yarn.lock").write_text("")
        profile = scan_project(tmp_path)
        assert profile["package_manager"] == "yarn"

    def test_scan_detects_pnpm(self, tmp_path):
        (tmp_path / "pnpm-lock.yaml").write_text("")
        profile = scan_project(tmp_path)
        assert profile["package_manager"] == "pnpm"

    def test_scan_detects_cargo(self, tmp_path):
        (tmp_path / "main.rs").write_text("fn main() {}")
        (tmp_path / "Cargo.toml").write_text("[package]")
        (tmp_path / "Cargo.lock").write_text("")
        profile = scan_project(tmp_path)
        assert "rust" in profile["languages"]
        assert profile["package_manager"] == "cargo"

    def test_scan_detects_go(self, tmp_path):
        (tmp_path / "main.go").write_text("package main")
        (tmp_path / "go.mod").write_text("module example.com/app")
        (tmp_path / "go.sum").write_text("")
        profile = scan_project(tmp_path)
        assert "go" in profile["languages"]
        assert profile["package_manager"] == "go modules"

    def test_scan_detects_docker(self, tmp_path):
        (tmp_path / "Dockerfile").write_text("FROM python:3.12")
        profile = scan_project(tmp_path)
        assert "docker" in profile["build_tools"]

    def test_scan_detects_github_actions(self, tmp_path):
        wf = tmp_path / ".github" / "workflows"
        wf.mkdir(parents=True)
        (wf / "ci.yml").write_text("on: push")
        profile = scan_project(tmp_path)
        assert "github-actions" in profile["build_tools"]

    def test_scan_multiple_languages_sorted_by_count(self, tmp_path):
        for i in range(5):
            (tmp_path / f"module{i}.py").write_text("")
        for i in range(2):
            (tmp_path / f"script{i}.js").write_text("")
        profile = scan_project(tmp_path)
        assert profile["languages"][0] == "python"
        assert profile["languages"][1] == "javascript"

    def test_scan_invalid_path_raises(self, tmp_path):
        with pytest.raises(ValueError, match="Not a directory"):
            scan_project(tmp_path / "nonexistent")

    def test_scan_malformed_package_json(self, tmp_path):
        (tmp_path / "package.json").write_text("not json{{{")
        profile = scan_project(tmp_path)
        # Should not crash, just skip framework detection
        assert isinstance(profile["frameworks"], list)

    def test_scan_pyproject_toml_frameworks(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text(
            '[project]\ndependencies = ["fastapi", "sqlalchemy"]\n'
            "[tool.pytest.ini_options]\n"
        )
        (tmp_path / "app.py").write_text("")
        profile = scan_project(tmp_path)
        assert "fastapi" in profile["frameworks"]
        assert "sqlalchemy" in profile["frameworks"]
        assert profile["test_framework"] == "pytest"

    def test_scan_nextjs_project(self, tmp_path):
        (tmp_path / "package.json").write_text(json.dumps({
            "dependencies": {"next": "^14.0.0", "react": "^18.0.0"},
            "devDependencies": {"tailwindcss": "^3.0.0"},
        }))
        profile = scan_project(tmp_path)
        assert "next.js" in profile["frameworks"]
        assert "react" in profile["frameworks"]
        assert "tailwind" in profile["frameworks"]


class TestScanProjectProfile:
    """Tests for profile structure and completeness."""

    def test_profile_has_required_keys(self, tmp_path):
        (tmp_path / "app.py").write_text("")
        profile = scan_project(tmp_path)
        required_keys = {
            "name", "path", "languages", "primary_language",
            "frameworks", "package_manager", "test_framework",
            "file_count", "git", "build_tools", "structure", "docs",
        }
        assert required_keys.issubset(profile.keys())

    def test_profile_path_is_absolute(self, tmp_path):
        profile = scan_project(tmp_path)
        assert Path(profile["path"]).is_absolute()

    def test_profile_serializable_to_json(self, tmp_path):
        (tmp_path / "main.py").write_text("")
        (tmp_path / "package.json").write_text(json.dumps({"dependencies": {"react": "^18"}}))
        profile = scan_project(tmp_path)
        serialized = json.dumps(profile)
        deserialized = json.loads(serialized)
        assert deserialized["name"] == profile["name"]

    def test_profile_has_scanned_at(self, tmp_path):
        profile = scan_project(tmp_path)
        assert "scanned_at" in profile
        assert isinstance(profile["scanned_at"], str)

    def test_profile_structure_has_directories(self, tmp_path):
        (tmp_path / "src").mkdir()
        (tmp_path / "tests").mkdir()
        profile = scan_project(tmp_path)
        assert "directories" in profile["structure"]
        assert "src" in profile["structure"]["directories"]

    def test_profile_docs_detection(self, tmp_path):
        (tmp_path / "README.md").write_text("# My Project\nDescription here")
        profile = scan_project(tmp_path)
        assert profile["docs"]["has_readme"] is True
        assert profile["docs"]["readme_summary"] is not None
