"""Project registry — manages a global list of scanned projects."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REGISTRY_PATH = Path.home() / ".amiga" / "data" / "projects.json"


def _read_registry() -> dict[str, Any]:
    """Read the registry file, returning empty structure if missing."""
    try:
        if REGISTRY_PATH.is_file():
            content = REGISTRY_PATH.read_text(encoding="utf-8")
            data = json.loads(content)
            if isinstance(data, dict) and "projects" in data:
                return data
    except (json.JSONDecodeError, OSError, PermissionError):
        pass
    return {"active": None, "projects": {}}


def _write_registry(data: dict[str, Any]) -> None:
    """Write the registry file, creating parent directories."""
    REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    REGISTRY_PATH.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def register_project(profile: dict[str, Any]) -> None:
    """Add or update a project in the global registry."""
    registry = _read_registry()
    project_path = profile.get("path")
    if not project_path:
        raise ValueError("Profile must contain a 'path' field")

    now = datetime.now(timezone.utc).isoformat()

    # Build a compact summary for the registry
    entry: dict[str, Any] = {
        "name": profile.get("name", Path(project_path).name),
        "path": project_path,
        "primary_language": profile.get("primary_language"),
        "frameworks": profile.get("frameworks", []),
        "last_scanned": profile.get("scanned_at", now),
    }

    existing = registry["projects"].get(project_path)
    if existing and isinstance(existing, dict):
        entry["added_at"] = existing.get("added_at", now)
    else:
        entry["added_at"] = now

    registry["projects"][project_path] = entry
    _write_registry(registry)


def unregister_project(path: str) -> bool:
    """Remove a project from the registry. Returns True if found and removed."""
    registry = _read_registry()
    if path not in registry["projects"]:
        return False

    del registry["projects"][path]

    # Clear active if it was the removed project
    if registry.get("active") == path:
        registry["active"] = None

    _write_registry(registry)
    return True


def list_projects() -> list[dict[str, Any]]:
    """Return all registered projects with their profiles."""
    registry = _read_registry()
    projects = registry.get("projects", {})
    return list(projects.values())


def get_active_project() -> dict[str, Any] | None:
    """Return the currently active project, or None."""
    registry = _read_registry()
    active_path = registry.get("active")
    if active_path is None:
        return None
    projects = registry.get("projects", {})
    return projects.get(active_path)


def set_active_project(path: str) -> bool:
    """Set a project as the active workspace. Returns True if the project exists in registry."""
    registry = _read_registry()
    if path not in registry["projects"]:
        return False
    registry["active"] = path
    _write_registry(registry)
    return True
