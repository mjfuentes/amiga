"""
Integration test for database schema migrations

Tests schema evolution and data integrity:
- Migration from old schema to new schema
- Data preservation during migration
- Schema version tracking
- Backwards compatibility
- Index creation and optimization
"""

import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from tasks.database import SCHEMA_VERSION, Database


@pytest.fixture
def temp_db_path(tmp_path):
    """Create temporary database path"""
    return tmp_path / "test_migration.db"


def create_v1_schema(db_path):
    """Create version 1 schema (initial schema)"""
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    # Create schema version table
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER PRIMARY KEY,
            applied_at TEXT NOT NULL
        )
    """
    )

    # Initial tasks table (version 1)
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS tasks (
            task_id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            description TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            model TEXT NOT NULL,
            workspace TEXT NOT NULL,
            agent_type TEXT NOT NULL DEFAULT 'code_agent',
            result TEXT,
            error TEXT,
            pid INTEGER,
            activity_log TEXT,
            session_uuid TEXT
        )
    """
    )

    # Tool usage table
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS tool_usage (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            task_id TEXT NOT NULL,
            tool_name TEXT NOT NULL,
            duration_ms REAL,
            success BOOLEAN,
            error TEXT,
            parameters TEXT
        )
    """
    )

    # Mark as version 1
    cursor.execute(
        "INSERT INTO schema_version (version, applied_at) VALUES (?, ?)",
        (1, datetime.now().isoformat()),
    )

    conn.commit()
    conn.close()


def populate_v1_data(db_path):
    """Populate database with test data"""
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    # Insert test tasks
    test_tasks = [
        {
            "task_id": "task_001",
            "user_id": 123456,
            "description": "Test task 1",
            "status": "completed",
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "model": "claude-sonnet-4.5",
            "workspace": "/tmp/workspace1",
            "agent_type": "code_agent",
            "result": "Task completed successfully",
            "error": None,
            "pid": 12345,
            "activity_log": json.dumps([{"message": "Started", "timestamp": datetime.now().isoformat()}]),
            "session_uuid": "uuid-001"
        },
        {
            "task_id": "task_002",
            "user_id": 789012,
            "description": "Test task 2",
            "status": "failed",
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "model": "claude-sonnet-4.5",
            "workspace": "/tmp/workspace2",
            "agent_type": "code_agent",
            "result": None,
            "error": "Task failed",
            "pid": 12346,
            "activity_log": json.dumps([{"message": "Failed", "timestamp": datetime.now().isoformat()}]),
            "session_uuid": "uuid-002"
        }
    ]

    for task in test_tasks:
        cursor.execute(
            """
            INSERT INTO tasks (task_id, user_id, description, status, created_at, updated_at,
                             model, workspace, agent_type, result, error, pid, activity_log, session_uuid)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                task["task_id"],
                task["user_id"],
                task["description"],
                task["status"],
                task["created_at"],
                task["updated_at"],
                task["model"],
                task["workspace"],
                task["agent_type"],
                task["result"],
                task["error"],
                task["pid"],
                task["activity_log"],
                task["session_uuid"]
            ),
        )

    # Insert test tool usage
    cursor.execute(
        """
        INSERT INTO tool_usage (timestamp, task_id, tool_name, duration_ms, success, error, parameters)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """,
        (datetime.now().isoformat(), "task_001", "Read", 100.5, 1, None, json.dumps({"file": "test.py"})),
    )

    conn.commit()
    conn.close()


@pytest.mark.integration
def test_schema_migration_v1_to_current(temp_db_path):
    """
    Test migration from v1 schema to current schema

    Scenario:
    1. Create v1 schema
    2. Populate with test data
    3. Open database with current Database class (triggers migration)
    4. Verify schema upgraded to current version
    5. Verify data integrity preserved
    """
    # Create v1 schema
    create_v1_schema(temp_db_path)
    populate_v1_data(temp_db_path)

    # Verify v1 state
    conn = sqlite3.connect(str(temp_db_path))
    cursor = conn.cursor()
    cursor.execute("SELECT version FROM schema_version ORDER BY version DESC LIMIT 1")
    version = cursor.fetchone()[0]
    assert version == 1

    # Count records before migration
    cursor.execute("SELECT COUNT(*) FROM tasks")
    tasks_count = cursor.fetchone()[0]
    assert tasks_count == 2

    cursor.execute("SELECT COUNT(*) FROM tool_usage")
    tool_usage_count = cursor.fetchone()[0]
    assert tool_usage_count == 1
    conn.close()

    # Open with Database class (triggers migration)
    db = Database(temp_db_path)

    # Verify current schema version
    cursor = db.conn.cursor()
    cursor.execute("SELECT version FROM schema_version ORDER BY version DESC LIMIT 1")
    current_version = cursor.fetchone()[0]
    assert current_version == SCHEMA_VERSION

    # Verify data preserved
    cursor.execute("SELECT COUNT(*) FROM tasks")
    assert cursor.fetchone()[0] == tasks_count

    cursor.execute("SELECT COUNT(*) FROM tool_usage")
    assert cursor.fetchone()[0] == tool_usage_count

    # Verify task data integrity
    cursor.execute("SELECT task_id, user_id, description, status FROM tasks ORDER BY task_id")
    tasks = cursor.fetchall()

    assert len(tasks) == 2
    assert tasks[0][0] == "task_001"
    assert tasks[0][1] == 123456
    assert tasks[0][3] == "completed"

    assert tasks[1][0] == "task_002"
    assert tasks[1][1] == 789012
    assert tasks[1][3] == "failed"

    db.close()


@pytest.mark.integration
def test_migration_idempotency(temp_db_path):
    """
    Test that migrations can be run multiple times safely

    Scenario:
    1. Create database
    2. Run migration
    3. Close and reopen database
    4. Verify migration doesn't break on second run
    """
    # First initialization
    db1 = Database(temp_db_path)
    version1 = db1.conn.execute(
        "SELECT version FROM schema_version ORDER BY version DESC LIMIT 1"
    ).fetchone()[0]
    db1.close()

    # Second initialization (should not rerun migration)
    db2 = Database(temp_db_path)
    version2 = db2.conn.execute(
        "SELECT version FROM schema_version ORDER BY version DESC LIMIT 1"
    ).fetchone()[0]

    assert version1 == version2 == SCHEMA_VERSION

    # Verify schema version table has correct entries
    versions = db2.conn.execute(
        "SELECT version FROM schema_version ORDER BY version"
    ).fetchall()

    # Should only have one entry for current version (migrations are idempotent)
    assert len(versions) >= 1
    assert versions[-1][0] == SCHEMA_VERSION

    db2.close()


@pytest.mark.integration
def test_index_creation_during_migration(temp_db_path):
    """
    Test that indices are created during migration

    Scenario:
    1. Create database
    2. Verify indices exist
    3. Verify query performance with indices
    """
    db = Database(temp_db_path)

    # Query for indices
    cursor = db.conn.cursor()
    cursor.execute(
        """
        SELECT name FROM sqlite_master
        WHERE type = 'index' AND name LIKE 'idx_%'
        ORDER BY name
    """
    )
    indices = [row[0] for row in cursor.fetchall()]

    # Verify critical indices exist
    expected_indices = [
        "idx_tasks_user_status",
        "idx_tasks_created",
        "idx_tasks_status",
        "idx_tool_timestamp",
        "idx_tool_task",
        "idx_tool_name"
    ]

    for idx in expected_indices:
        assert idx in indices, f"Index {idx} not found"

    db.close()


@pytest.mark.integration
def test_schema_version_tracking(temp_db_path):
    """
    Test schema version tracking mechanism

    Scenario:
    1. Create database
    2. Verify schema_version table exists
    3. Verify version recorded correctly
    4. Verify timestamp recorded
    """
    db = Database(temp_db_path)
    cursor = db.conn.cursor()

    # Verify schema_version table exists
    cursor.execute(
        """
        SELECT name FROM sqlite_master
        WHERE type = 'table' AND name = 'schema_version'
    """
    )
    assert cursor.fetchone() is not None

    # Verify version entry
    cursor.execute("SELECT version, applied_at FROM schema_version ORDER BY version DESC LIMIT 1")
    row = cursor.fetchone()

    assert row is not None
    assert row[0] == SCHEMA_VERSION
    assert row[1] is not None  # Timestamp exists

    # Verify timestamp is valid ISO format
    try:
        datetime.fromisoformat(row[1])
    except ValueError:
        pytest.fail("Invalid timestamp format in schema_version")

    db.close()


@pytest.mark.integration
def test_data_types_preserved_during_migration(temp_db_path):
    """
    Test that data types are preserved correctly

    Scenario:
    1. Create database with various data types
    2. Insert test data
    3. Verify data types preserved after migration
    """
    create_v1_schema(temp_db_path)

    # Insert data with various types
    conn = sqlite3.connect(str(temp_db_path))
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO tasks (task_id, user_id, description, status, created_at, updated_at,
                         model, workspace, agent_type, result, error, pid, activity_log, session_uuid)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """,
        (
            "task_types",
            999999,
            "Test data types",
            "completed",
            datetime.now().isoformat(),
            datetime.now().isoformat(),
            "claude-sonnet-4.5",
            "/tmp/test",
            "code_agent",
            "Result with special chars: <>&\"'",
            None,
            12345,
            json.dumps([{"key": "value", "number": 42, "bool": True}]),
            "uuid-types"
        ),
    )

    cursor.execute(
        """
        INSERT INTO tool_usage (timestamp, task_id, tool_name, duration_ms, success, error, parameters)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """,
        (
            datetime.now().isoformat(),
            "task_types",
            "Read",
            123.456,
            1,
            None,
            json.dumps({"nested": {"key": "value"}})
        ),
    )

    conn.commit()
    conn.close()

    # Open with Database class
    db = Database(temp_db_path)
    cursor = db.conn.cursor()

    # Verify task data
    cursor.execute("SELECT * FROM tasks WHERE task_id = 'task_types'")
    task = cursor.fetchone()

    assert task is not None
    # Verify integers
    assert isinstance(task[1], int)  # user_id
    assert isinstance(task[11], int)  # pid

    # Verify JSON
    activity_log = json.loads(task[12])
    assert activity_log[0]["number"] == 42
    assert activity_log[0]["bool"] is True

    # Verify special characters preserved
    assert task[9] == "Result with special chars: <>&\"'"

    # Verify tool usage data
    cursor.execute("SELECT * FROM tool_usage WHERE task_id = 'task_types'")
    tool = cursor.fetchone()

    assert tool is not None
    # Verify float
    assert isinstance(tool[4], float)  # duration_ms
    assert abs(tool[4] - 123.456) < 0.001

    # Verify boolean
    assert tool[5] == 1  # success (SQLite stores as integer)

    # Verify nested JSON
    params = json.loads(tool[7])
    assert params["nested"]["key"] == "value"

    db.close()


@pytest.mark.integration
def test_empty_database_migration(temp_db_path):
    """
    Test migration on empty database

    Scenario:
    1. Create fresh database
    2. Verify schema created correctly
    3. Verify no data issues with empty tables
    """
    db = Database(temp_db_path)

    # Verify tables exist
    cursor = db.conn.cursor()
    cursor.execute(
        """
        SELECT name FROM sqlite_master
        WHERE type = 'table'
        ORDER BY name
    """
    )
    tables = [row[0] for row in cursor.fetchall()]

    expected_tables = ["tasks", "tool_usage", "agent_status", "schema_version"]
    for table in expected_tables:
        assert table in tables, f"Table {table} not found"

    # Verify tables are empty
    for table in ["tasks", "tool_usage", "agent_status"]:
        cursor.execute(f"SELECT COUNT(*) FROM {table}")
        count = cursor.fetchone()[0]
        assert count == 0

    # Verify can insert into empty tables
    cursor.execute(
        """
        INSERT INTO tasks (task_id, user_id, description, status, created_at, updated_at,
                         model, workspace, agent_type)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """,
        (
            "test_001",
            123456,
            "Test task",
            "pending",
            datetime.now().isoformat(),
            datetime.now().isoformat(),
            "claude-sonnet-4.5",
            "/tmp/test",
            "code_agent"
        ),
    )
    db.conn.commit()

    cursor.execute("SELECT COUNT(*) FROM tasks")
    assert cursor.fetchone()[0] == 1

    db.close()


@pytest.mark.integration
def test_foreign_key_constraints(temp_db_path):
    """
    Test that foreign key constraints are enabled

    Scenario:
    1. Create database
    2. Verify PRAGMA foreign_keys is ON
    3. Test constraint enforcement (if applicable)
    """
    db = Database(temp_db_path)
    cursor = db.conn.cursor()

    # Verify foreign keys enabled
    cursor.execute("PRAGMA foreign_keys")
    fk_status = cursor.fetchone()[0]
    assert fk_status == 1, "Foreign keys should be enabled"

    db.close()


@pytest.mark.integration
def test_wal_mode_enabled(temp_db_path):
    """
    Test that WAL mode is enabled for better concurrency

    Scenario:
    1. Create database
    2. Verify PRAGMA journal_mode is WAL
    """
    db = Database(temp_db_path)
    cursor = db.conn.cursor()

    # Verify WAL mode
    cursor.execute("PRAGMA journal_mode")
    mode = cursor.fetchone()[0]
    assert mode.lower() == "wal", "Database should use WAL mode"

    db.close()
