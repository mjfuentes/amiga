"""
Migration script to convert JSON storage to SQLite
Safely migrates existing data from JSON files to SQLite database
"""

import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

# Add parent directory to path for config imports
sys.path.insert(0, str(Path(__file__).parent.parent))
from database import Database

from core.config import DATA_DIR_STR, DATABASE_PATH_STR
from utils.logging_setup import setup_logging

logger = setup_logging(__name__, console=True)


class MigrationError(Exception):
    """Migration error"""

    pass


def backup_json_files(data_dir: Path, backup_dir: Path):
    """Backup existing JSON files before migration"""
    backup_dir.mkdir(exist_ok=True, parents=True)

    files_to_backup = [
        "tasks.json",
        "tool_usage.json",
        "agent_status.json",
    ]

    backed_up = []
    for filename in files_to_backup:
        src = data_dir / filename
        if src.exists():
            dst = backup_dir / filename
            shutil.copy2(src, dst)
            backed_up.append(filename)
            logger.info(f"Backed up {filename} to {backup_dir}")

    return backed_up


def load_json_data(data_dir: Path) -> dict:
    """Load all JSON data files"""
    data = {
        "tasks": {},
        "tool_usage": [],
        "agent_status": [],
    }

    # Load tasks
    tasks_file = data_dir / "tasks.json"
    if tasks_file.exists():
        try:
            with open(tasks_file) as f:
                data["tasks"] = json.load(f)
            logger.info(f"Loaded {len(data['tasks'])} tasks from {tasks_file}")
        except Exception as e:
            logger.error(f"Error loading tasks: {e}")
            raise MigrationError(f"Failed to load tasks.json: {e}") from e

    # Load tool usage
    tool_usage_file = data_dir / "tool_usage.json"
    if tool_usage_file.exists():
        try:
            with open(tool_usage_file) as f:
                data["tool_usage"] = json.load(f)
            logger.info(f"Loaded {len(data['tool_usage'])} tool usage records from {tool_usage_file}")
        except Exception as e:
            logger.error(f"Error loading tool usage: {e}")
            raise MigrationError(f"Failed to load tool_usage.json: {e}") from e

    # Load agent status
    agent_status_file = data_dir / "agent_status.json"
    if agent_status_file.exists():
        try:
            with open(agent_status_file) as f:
                data["agent_status"] = json.load(f)
            logger.info(f"Loaded {len(data['agent_status'])} agent status records from {agent_status_file}")
        except Exception as e:
            logger.error(f"Error loading agent status: {e}")
            raise MigrationError(f"Failed to load agent_status.json: {e}") from e

    return data


def migrate_tasks(db: Database, tasks_data: dict) -> int:
    """Migrate tasks to SQLite"""
    migrated = 0
    errors = 0

    for task_id, task in tasks_data.items():
        try:
            # Ensure activity_log is a list
            activity_log = task.get("activity_log", [])
            if not isinstance(activity_log, list):
                activity_log = []

            # Convert activity_log to JSON string
            activity_log_json = json.dumps(activity_log)

            cursor = db.conn.cursor()
            cursor.execute(
                """
                INSERT INTO tasks (
                    task_id, user_id, description, status, created_at, updated_at,
                    model, workspace, agent_type, result, error, pid, activity_log
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    task.get("task_id", task_id),
                    task["user_id"],
                    task["description"],
                    task["status"],
                    task["created_at"],
                    task["updated_at"],
                    task["model"],
                    task["workspace"],
                    task.get("agent_type", "code_agent"),
                    task.get("result"),
                    task.get("error"),
                    task.get("pid"),
                    activity_log_json,
                ),
            )
            migrated += 1

        except Exception as e:
            logger.error(f"Error migrating task {task_id}: {e}")
            errors += 1

    db.conn.commit()
    logger.info(f"Migrated {migrated} tasks ({errors} errors)")
    return migrated


def migrate_tool_usage(db: Database, tool_usage_data: list) -> int:
    """Migrate tool usage records to SQLite"""
    migrated = 0
    errors = 0

    for record in tool_usage_data:
        try:
            # Convert parameters to JSON string if present
            parameters = record.get("parameters")
            parameters_json = json.dumps(parameters) if parameters else None

            cursor = db.conn.cursor()
            cursor.execute(
                """
                INSERT INTO tool_usage (
                    timestamp, task_id, tool_name, duration_ms, success, error, parameters
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    record["timestamp"],
                    record["task_id"],
                    record["tool_name"],
                    record.get("duration_ms"),
                    record.get("success"),
                    record.get("error"),
                    parameters_json,
                ),
            )
            migrated += 1

        except Exception as e:
            logger.error(f"Error migrating tool usage record: {e}")
            logger.error(f"Record: {record}")
            errors += 1

    db.conn.commit()
    logger.info(f"Migrated {migrated} tool usage records ({errors} errors)")
    return migrated


def migrate_agent_status(db: Database, agent_status_data: list) -> int:
    """Migrate agent status records to SQLite"""
    migrated = 0
    errors = 0

    for record in agent_status_data:
        try:
            # Convert metadata to JSON string if present
            metadata = record.get("metadata")
            metadata_json = json.dumps(metadata) if metadata else None

            cursor = db.conn.cursor()
            cursor.execute(
                """
                INSERT INTO agent_status (
                    timestamp, task_id, status, message, metadata
                )
                VALUES (?, ?, ?, ?, ?)
            """,
                (
                    record["timestamp"],
                    record["task_id"],
                    record["status"],
                    record.get("message"),
                    metadata_json,
                ),
            )
            migrated += 1

        except Exception as e:
            logger.error(f"Error migrating agent status record: {e}")
            logger.error(f"Record: {record}")
            errors += 1

    db.conn.commit()
    logger.info(f"Migrated {migrated} agent status records ({errors} errors)")
    return migrated


def verify_migration(db: Database, original_data: dict) -> bool:
    """Verify migration was successful"""
    logger.info("Verifying migration...")

    cursor = db.conn.cursor()

    # Verify task count
    cursor.execute("SELECT COUNT(*) FROM tasks")
    task_count = cursor.fetchone()[0]
    expected_tasks = len(original_data["tasks"])

    if task_count != expected_tasks:
        logger.error(f"Task count mismatch: expected {expected_tasks}, got {task_count}")
        return False
    logger.info(f"✓ Task count matches: {task_count}")

    # Verify tool usage count
    cursor.execute("SELECT COUNT(*) FROM tool_usage")
    tool_usage_count = cursor.fetchone()[0]
    expected_tool_usage = len(original_data["tool_usage"])

    if tool_usage_count != expected_tool_usage:
        logger.error(f"Tool usage count mismatch: expected {expected_tool_usage}, got {tool_usage_count}")
        return False
    logger.info(f"✓ Tool usage count matches: {tool_usage_count}")

    # Verify agent status count
    cursor.execute("SELECT COUNT(*) FROM agent_status")
    agent_status_count = cursor.fetchone()[0]
    expected_agent_status = len(original_data["agent_status"])

    if agent_status_count != expected_agent_status:
        logger.error(f"Agent status count mismatch: expected {expected_agent_status}, got {agent_status_count}")
        return False
    logger.info(f"✓ Agent status count matches: {agent_status_count}")

    # Verify sample task data
    if original_data["tasks"]:
        sample_task_id = list(original_data["tasks"].keys())[0]
        sample_task = original_data["tasks"][sample_task_id]

        cursor.execute("SELECT * FROM tasks WHERE task_id = ?", (sample_task_id,))
        row = cursor.fetchone()

        if not row:
            logger.error(f"Sample task {sample_task_id} not found in database")
            return False

        # Verify key fields
        if row["user_id"] != sample_task["user_id"]:
            logger.error("Sample task user_id mismatch")
            return False
        if row["description"] != sample_task["description"]:
            logger.error("Sample task description mismatch")
            return False

        logger.info(f"✓ Sample task data verified: {sample_task_id}")

    logger.info("✓ Migration verification passed!")
    return True


def main(data_dir: str = None, db_path: str = None, force: bool = False):
    """Main migration function"""
    # Use config defaults if not provided
    if data_dir is None:
        data_dir = DATA_DIR_STR
    if db_path is None:
        db_path = DATABASE_PATH_STR

    data_dir = Path(data_dir)
    db_path = Path(db_path)

    logger.info("=" * 60)
    logger.info("AgentLab JSON to SQLite Migration")
    logger.info("=" * 60)

    # Check if database already exists
    if db_path.exists() and not force:
        logger.error(f"Database already exists at {db_path}")
        logger.error("Use --force to overwrite existing database")
        return False

    # Create backup directory
    backup_dir = data_dir / "backup" / datetime.now().strftime("%Y%m%d_%H%M%S")
    logger.info(f"Backup directory: {backup_dir}")

    try:
        # Step 1: Backup JSON files
        logger.info("\n[1/6] Backing up JSON files...")
        backed_up = backup_json_files(data_dir, backup_dir)
        logger.info(f"✓ Backed up {len(backed_up)} files")

        # Step 2: Load JSON data
        logger.info("\n[2/6] Loading JSON data...")
        json_data = load_json_data(data_dir)
        total_records = len(json_data["tasks"]) + len(json_data["tool_usage"]) + len(json_data["agent_status"])
        logger.info(f"✓ Loaded {total_records} total records")

        # Step 3: Create database
        logger.info("\n[3/6] Creating SQLite database...")
        if db_path.exists():
            db_path.unlink()
            logger.info(f"Removed existing database at {db_path}")

        db = Database(str(db_path))
        logger.info(f"✓ Created database at {db_path}")

        # Step 4: Migrate data
        logger.info("\n[4/6] Migrating data to SQLite...")

        logger.info("  Migrating tasks...")
        tasks_migrated = migrate_tasks(db, json_data["tasks"])

        logger.info("  Migrating tool usage...")
        tool_usage_migrated = migrate_tool_usage(db, json_data["tool_usage"])

        logger.info("  Migrating agent status...")
        agent_status_migrated = migrate_agent_status(db, json_data["agent_status"])

        total_migrated = tasks_migrated + tool_usage_migrated + agent_status_migrated
        logger.info(f"✓ Migrated {total_migrated} total records")

        # Step 5: Verify migration
        logger.info("\n[5/6] Verifying migration...")
        if not verify_migration(db, json_data):
            raise MigrationError("Migration verification failed!")

        # Step 6: Get database stats
        logger.info("\n[6/6] Database statistics...")
        stats = db.get_database_stats()
        logger.info(f"  Tasks: {stats['tasks']}")
        logger.info(f"  Tool usage records: {stats['tool_usage_records']}")
        logger.info(f"  Agent status records: {stats['agent_status_records']}")
        logger.info(f"  Database size: {stats['database_size_kb']:.2f} KB")

        # Close database
        db.close()

        logger.info("\n" + "=" * 60)
        logger.info("✓ Migration completed successfully!")
        logger.info("=" * 60)
        logger.info(f"\nBackup files saved to: {backup_dir}")
        logger.info(f"Database created at: {db_path}")
        logger.info("\nNext steps:")
        logger.info("1. Test the new database with your application")
        logger.info("2. If everything works, you can delete the backup directory")
        logger.info("3. The original JSON files are still in place as a backup")

        return True

    except Exception as e:
        logger.error(f"\n✗ Migration failed: {e}")
        logger.error(f"Backup files are preserved at: {backup_dir}")
        logger.error("You can restore from backup if needed")
        return False


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Migrate AgentLab data from JSON to SQLite")
    parser.add_argument(
        "--data-dir",
        default=None,
        help=f"Data directory containing JSON files (default: {DATA_DIR_STR})",
    )
    parser.add_argument(
        "--db-path",
        default=None,
        help=f"Path for SQLite database (default: {DATABASE_PATH_STR})",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing database",
    )

    args = parser.parse_args()

    success = main(
        data_dir=args.data_dir,
        db_path=args.db_path,
        force=args.force,
    )

    exit(0 if success else 1)
