"""
Tests for database path consolidation to core.config

This module tests that database paths are centralized in core.config
and used consistently across migration scripts.

Note: telegram_bot/migrate_to_sqlite.py is a legacy migration script
that references an old database.py location. It's tested for path
consolidation only, not full import functionality.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def test_config_provides_database_paths():
    """Test that core.config provides centralized database paths"""
    from core.config import DATABASE_PATH_STR, DATA_DIR_STR, SESSIONS_FILE_STR

    # Verify paths are defined
    assert DATABASE_PATH_STR is not None
    assert DATA_DIR_STR is not None
    assert SESSIONS_FILE_STR is not None

    # Verify they are absolute paths
    assert Path(DATABASE_PATH_STR).is_absolute()
    assert Path(DATA_DIR_STR).is_absolute()
    assert Path(SESSIONS_FILE_STR).is_absolute()


def test_scripts_import_from_config():
    """Test that migration scripts import paths from core.config"""
    # Check scripts/migrate_to_sqlite.py uses config
    with open("scripts/migrate_to_sqlite.py") as f:
        content = f.read()
        assert "from core.config import DATABASE_PATH_STR" in content
        assert "from core.config import" in content and "SESSIONS_FILE_STR" in content

    # Check scripts/migrate_tasks_to_messages.py uses config
    with open("scripts/migrate_tasks_to_messages.py") as f:
        content = f.read()
        assert "from core.config import DATABASE_PATH_STR" in content

    # Check scripts/merge_databases.py uses config
    with open("scripts/merge_databases.py") as f:
        content = f.read()
        assert "from core.config import DATABASE_PATH_STR" in content


def test_no_hardcoded_database_paths():
    """Test that no hardcoded database path strings remain in code"""
    import subprocess

    # Search for hardcoded paths (excluding core/config.py and this test file)
    result = subprocess.run(
        [
            "grep",
            "-rE",
            '(data/agentlab\\.db|"agentlab\\.db")',
            "--include=*.py",
            ".",
        ],
        capture_output=True,
        text=True,
    )

    # Filter out core/config.py (only allowed location) and this test file
    lines = [
        line
        for line in result.stdout.split("\n")
        if line and "core/config.py" not in line and "test_migrate_to_sqlite.py" not in line
    ]

    # Should be empty - no hardcoded paths outside config
    assert len(lines) == 0, f"Found hardcoded database paths: {lines}"
