"""CLI entry points for project management."""

import json
import sys
from pathlib import Path

from projects.registry import get_active_project, list_projects, register_project, set_active_project
from projects.scanner import scan_project


def cmd_init(project_path: str) -> None:
    """Scan a project directory and register it globally."""
    path = Path(project_path).resolve()

    if not path.is_dir():
        print(f"Error: not a directory: {path}", file=sys.stderr)
        sys.exit(1)

    print(f"Scanning {path.name}...")
    profile = scan_project(path)

    # Write .amiga/profile.json in the project
    amiga_dir = path / ".amiga"
    amiga_dir.mkdir(exist_ok=True)
    (amiga_dir / "profile.json").write_text(json.dumps(profile, indent=2) + "\n")

    # Register globally
    register_project(profile)
    set_active_project(str(path))

    # Print summary
    print(f"\nProject: {profile['name']}")
    print(f"Languages: {', '.join(profile['languages'][:5])}")
    if profile["frameworks"]:
        print(f"Frameworks: {', '.join(profile['frameworks'])}")
    if profile["package_manager"]:
        print(f"Package manager: {profile['package_manager']}")
    if profile["test_framework"]:
        print(f"Tests: {profile['test_framework']}")
    print(f"Files: {profile['file_count']}")
    print(f"\nProfile saved to .amiga/profile.json")
    print(f"Set as active project.")


def cmd_list() -> None:
    """List all registered projects."""
    projects = list_projects()
    active = get_active_project()
    active_path = active["path"] if active else None

    if not projects:
        print("No projects registered. Run 'amiga init' in a project directory.")
        return

    for p in projects:
        marker = " *" if p["path"] == active_path else ""
        lang = p.get("primary_language", "Unknown")
        print(f"  {p['name']}{marker}  ({lang})  {p['path']}")


def cmd_switch(project_name_or_path: str) -> None:
    """Switch active project by name or path."""
    if not project_name_or_path:
        print("Error: provide a project name or path.", file=sys.stderr)
        cmd_list()
        sys.exit(1)

    projects = list_projects()

    # Match by name or path
    for p in projects:
        if p["name"] == project_name_or_path or p["path"] == project_name_or_path:
            set_active_project(p["path"])
            print(f"Switched to: {p['name']} ({p['path']})")
            return

    print(f"Project not found: {project_name_or_path}")
    print("Registered projects:")
    cmd_list()
    sys.exit(1)


if __name__ == "__main__":
    action = sys.argv[1] if len(sys.argv) > 1 else "help"

    if action == "init":
        cmd_init(sys.argv[2] if len(sys.argv) > 2 else ".")
    elif action == "list":
        cmd_list()
    elif action == "switch":
        cmd_switch(sys.argv[2] if len(sys.argv) > 2 else "")
    else:
        print("Usage: python -m projects.cli {init|list|switch} [args]")
