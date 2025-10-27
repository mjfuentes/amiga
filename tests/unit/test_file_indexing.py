#!/usr/bin/env python3
"""
Validation test for file indexing system implementation
Tests all critical functionality against requirements
"""

import asyncio
import json
import sqlite3
import tempfile
from pathlib import Path

# Add parent directory to path for imports
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from tasks.database import Database
from tasks.tracker import ToolUsageTracker


def print_section(title: str):
    """Print section header"""
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def print_result(test_name: str, passed: bool, details: str = ""):
    """Print test result"""
    status = "PASS" if passed else "FAIL"
    symbol = "✓" if passed else "✗"
    print(f"{symbol} {test_name:50s} [{status}]")
    if details:
        print(f"  {details}")


async def test_schema_migration():
    """Test 1: Verify schema migration creates files table correctly"""
    print_section("TEST 1: Schema Migration")

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        db = Database(str(db_path))

        # Check table exists
        cursor = db.conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='files'")
        table_exists = cursor.fetchone() is not None
        print_result("Files table created", table_exists)

        # Check columns
        cursor.execute("PRAGMA table_info(files)")
        columns = {col[1]: col[2] for col in cursor.fetchall()}

        expected_columns = {
            "file_path": "TEXT",
            "first_seen": "TEXT",
            "last_accessed": "TEXT",
            "access_count": "INTEGER",
            "task_ids": "TEXT",
            "operations": "TEXT",
            "file_size": "INTEGER",
            "file_hash": "TEXT",
        }

        all_columns_present = all(col in columns for col in expected_columns.keys())
        print_result("All required columns present", all_columns_present)

        # Check primary key
        cursor.execute("PRAGMA table_info(files)")
        pk_column = None
        for col in cursor.fetchall():
            if col[5] == 1:  # pk field
                pk_column = col[1]
        print_result("Primary key on file_path", pk_column == "file_path")

        return table_exists and all_columns_present and pk_column == "file_path"


async def test_indices():
    """Test 2: Verify indices are created for performance"""
    print_section("TEST 2: Index Creation")

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        db = Database(str(db_path))

        cursor = db.conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='index'")
        indices = [row[0] for row in cursor.fetchall()]

        last_accessed_idx = any("idx_files_last_accessed" in idx for idx in indices)
        access_count_idx = any("idx_files_access_count" in idx for idx in indices)

        print_result("Last accessed index created", last_accessed_idx)
        print_result("Access count index created", access_count_idx)

        return last_accessed_idx and access_count_idx


async def test_record_file_access():
    """Test 3: Verify record_file_access() updates file index properly"""
    print_section("TEST 3: Record File Access")

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        db = Database(str(db_path))

        test_file = "/tmp/test_file.py"
        task_id = "test_task_123"

        # Record first access
        await db.record_file_access(test_file, task_id, "read")

        # Verify record created
        file_info = db.get_file_info(test_file)
        print_result("File record created", file_info is not None)
        print_result("Access count is 1", file_info["access_count"] == 1, f"Got: {file_info['access_count']}")
        print_result("Task ID recorded", task_id in file_info["task_ids"], f"Got: {file_info['task_ids']}")
        print_result(
            "Read operation recorded",
            file_info["operations"]["read"] == 1,
            f"Got: {file_info['operations']}",
        )

        # Record second access (different operation)
        await db.record_file_access(test_file, task_id, "write")

        file_info = db.get_file_info(test_file)
        print_result("Access count incremented to 2", file_info["access_count"] == 2, f"Got: {file_info['access_count']}")
        print_result(
            "Write operation recorded",
            file_info["operations"]["write"] == 1,
            f"Got: {file_info['operations']}",
        )

        # Record access from different task
        task_id2 = "test_task_456"
        await db.record_file_access(test_file, task_id2, "edit")

        file_info = db.get_file_info(test_file)
        print_result("Access count incremented to 3", file_info["access_count"] == 3, f"Got: {file_info['access_count']}")
        print_result(
            "Both task IDs recorded",
            task_id in file_info["task_ids"] and task_id2 in file_info["task_ids"],
            f"Got: {file_info['task_ids']}",
        )
        print_result(
            "Edit operation recorded",
            file_info["operations"]["edit"] == 1,
            f"Got: {file_info['operations']}",
        )

        return file_info["access_count"] == 3 and len(file_info["task_ids"]) == 2


async def test_query_methods():
    """Test 4: Test query methods return expected data"""
    print_section("TEST 4: Query Methods")

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        db = Database(str(db_path))

        # Create test data
        files = [
            ("/tmp/file1.py", "task1", "read", 10),
            ("/tmp/file2.py", "task1", "write", 5),
            ("/tmp/file3.py", "task2", "edit", 20),
            ("/tmp/file1.py", "task2", "read", None),  # Second access to file1
        ]

        for file_path, task_id, operation, count in files:
            for _ in range(count) if count else [None]:
                await db.record_file_access(file_path, task_id, operation)

        # Test get_file_info
        file1_info = db.get_file_info("/tmp/file1.py")
        print_result(
            "get_file_info returns correct data",
            file1_info is not None and file1_info["access_count"] == 10,
            f"Got access_count: {file1_info['access_count'] if file1_info else 'None'}",
        )

        # Test get_frequently_accessed_files
        frequent_files = db.get_frequently_accessed_files(limit=10)
        print_result("get_frequently_accessed_files returns data", len(frequent_files) == 3)

        # Should be sorted by access_count DESC
        is_sorted = all(
            frequent_files[i]["access_count"] >= frequent_files[i + 1]["access_count"]
            for i in range(len(frequent_files) - 1)
        )
        print_result("Results sorted by access count", is_sorted, f"Got order: {[f['access_count'] for f in frequent_files]}")

        # Top file should be file3 (20 accesses)
        top_file_correct = frequent_files[0]["file_path"] == "/tmp/file3.py"
        print_result("Top file is correct", top_file_correct, f"Got: {frequent_files[0]['file_path']}")

        # Test get_task_files
        task1_files = db.get_task_files("task1")
        print_result(
            "get_task_files returns correct count",
            len(task1_files) == 2,
            f"Got {len(task1_files)} files: {[f['file_path'] for f in task1_files]}",
        )

        # Test get_file_statistics
        stats = db.get_file_statistics()
        print_result("get_file_statistics returns total_files", stats["total_files"] == 3, f"Got: {stats['total_files']}")
        print_result(
            "get_file_statistics returns total_accesses",
            stats["total_accesses"] == 35,
            f"Got: {stats['total_accesses']}",
        )
        print_result(
            "get_file_statistics returns operations_by_type",
            stats["operations_by_type"]["read"] == 10
            and stats["operations_by_type"]["write"] == 5
            and stats["operations_by_type"]["edit"] == 20,
            f"Got: {stats['operations_by_type']}",
        )

        return len(frequent_files) == 3 and is_sorted and len(task1_files) == 2


async def test_tool_usage_tracker_integration():
    """Test 5: Confirm integration with tool_usage_tracker works"""
    print_section("TEST 5: Tool Usage Tracker Integration")

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        db = Database(str(db_path))
        tracker = ToolUsageTracker(db=db, data_dir=tmpdir)

        task_id = "integration_test_task"
        test_file = "/tmp/integration_test.py"

        # Test Read tool
        tracker.record_tool_complete(
            task_id=task_id,
            tool_name="Read",
            duration_ms=100.0,
            success=True,
            parameters={"file_path": test_file},
        )

        # Give async operation time to complete
        await asyncio.sleep(0.1)

        # Check file was indexed
        file_info = db.get_file_info(test_file)
        read_recorded = file_info is not None and file_info["operations"]["read"] == 1
        print_result("Read tool triggers file indexing", read_recorded, f"Got: {file_info}")

        # Test Write tool
        tracker.record_tool_complete(
            task_id=task_id,
            tool_name="Write",
            duration_ms=150.0,
            success=True,
            parameters={"file_path": test_file},
        )

        await asyncio.sleep(0.1)

        file_info = db.get_file_info(test_file)
        write_recorded = file_info is not None and file_info["operations"]["write"] == 1
        print_result("Write tool triggers file indexing", write_recorded, f"Got: {file_info}")

        # Test Edit tool
        tracker.record_tool_complete(
            task_id=task_id,
            tool_name="Edit",
            duration_ms=200.0,
            success=True,
            parameters={"file_path": test_file},
        )

        await asyncio.sleep(0.1)

        file_info = db.get_file_info(test_file)
        edit_recorded = file_info is not None and file_info["operations"]["edit"] == 1
        print_result("Edit tool triggers file indexing", edit_recorded, f"Got: {file_info}")

        # Test non-file tool (should not trigger indexing)
        initial_file_count = db.get_file_statistics()["total_files"]
        tracker.record_tool_complete(
            task_id=task_id,
            tool_name="Bash",
            duration_ms=50.0,
            success=True,
            parameters={"command": "ls -la"},
        )

        await asyncio.sleep(0.1)

        final_file_count = db.get_file_statistics()["total_files"]
        print_result("Non-file tools don't trigger indexing", initial_file_count == final_file_count)

        # Test failed tool (should not trigger indexing)
        tracker.record_tool_complete(
            task_id=task_id,
            tool_name="Read",
            duration_ms=10.0,
            success=False,
            error="File not found",
            parameters={"file_path": "/tmp/nonexistent.py"},
        )

        await asyncio.sleep(0.1)

        nonexistent_info = db.get_file_info("/tmp/nonexistent.py")
        print_result("Failed tools don't trigger indexing", nonexistent_info is None)

        return read_recorded and write_recorded and edit_recorded and initial_file_count == final_file_count


async def main():
    """Run all validation tests"""
    print("\n" + "=" * 60)
    print("  FILE INDEXING SYSTEM VALIDATION")
    print("=" * 60)

    results = {
        "Schema Migration": await test_schema_migration(),
        "Index Creation": await test_indices(),
        "Record File Access": await test_record_file_access(),
        "Query Methods": await test_query_methods(),
        "Tool Usage Tracker Integration": await test_tool_usage_tracker_integration(),
    }

    print_section("VALIDATION SUMMARY")

    all_passed = all(results.values())
    for test_name, passed in results.items():
        status = "PASS" if passed else "FAIL"
        symbol = "✓" if passed else "✗"
        print(f"{symbol} {test_name:40s} [{status}]")

    print("\n" + "=" * 60)
    if all_passed:
        print("  VALIDATION STATUS: APPROVED")
        print("  All requirements met and working correctly")
    else:
        print("  VALIDATION STATUS: REJECTED")
        print("  Critical issues found - see failures above")
    print("=" * 60 + "\n")

    return 0 if all_passed else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
