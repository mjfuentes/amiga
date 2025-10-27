#!/usr/bin/env python3
"""
Migrate task descriptions from tasks table to messages table.
Task descriptions represent user prompts that triggered background tasks.
"""

import logging
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.config import DATABASE_PATH_STR
from tasks.database import Database
from tasks.analytics import AnalyticsDB
from utils.logging_setup import setup_logging

logger = setup_logging(__name__, console=True)


def main():
    """Migrate task descriptions to messages table as user prompts."""

    db_path = Path(DATABASE_PATH_STR)

    logger.info("=" * 80)
    logger.info("Migrate Task Descriptions to Messages Table")
    logger.info("=" * 80)
    logger.info(f"Database: {db_path}")
    logger.info("")

    # Initialize database connections
    db = Database(str(db_path))
    analytics_db = AnalyticsDB(db)

    # Get all tasks with descriptions
    cursor = db.conn.cursor()
    cursor.execute("""
        SELECT task_id, user_id, description, created_at, model, status
        FROM tasks
        WHERE description IS NOT NULL AND LENGTH(description) > 0
        ORDER BY created_at
    """)
    tasks = cursor.fetchall()

    logger.info(f"Found {len(tasks)} tasks with descriptions")

    # Check existing messages to avoid duplicates
    cursor = db.conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM messages")
    existing_count = cursor.fetchone()[0]

    logger.info(f"Current messages in database: {existing_count}")
    logger.info("")

    # Confirm migration
    response = input(f"Migrate {len(tasks)} task descriptions as user messages? [y/N]: ")
    if response.lower() != 'y':
        logger.info("Migration cancelled")
        return

    # Migrate tasks - insert directly with historical timestamps
    migrated = 0
    skipped = 0

    cursor = db.conn.cursor()

    for task in tasks:
        task_id, user_id, description, created_at, model, status = task

        # Insert directly to preserve historical timestamps
        try:
            cursor.execute("""
                INSERT INTO messages (
                    user_id, timestamp, role, content,
                    tokens_input, tokens_output,
                    cache_creation_tokens, cache_read_tokens,
                    conversation_id, input_method, has_image, model
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                str(user_id),
                created_at,
                "user",  # Task descriptions are user prompts
                description,
                None,  # Token tracking not available for historical tasks
                None,
                None,
                None,
                task_id,  # Use task_id as conversation thread
                "text",  # Tasks triggered by text
                False,  # No images in task descriptions
                model or "sonnet"
            ))

            migrated += 1

            if migrated % 50 == 0:
                logger.info(f"  Migrated {migrated}/{len(tasks)} tasks...")

        except Exception as e:
            logger.warning(f"  Skipped task {task_id}: {e}")
            skipped += 1

    # Commit all insertions
    db.conn.commit()

    logger.info("")
    logger.info("=" * 80)
    logger.info(f"Migration complete:")
    logger.info(f"  Tasks migrated: {migrated}")
    logger.info(f"  Tasks skipped: {skipped}")
    logger.info("")

    # Show updated statistics
    cursor = db.conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM messages")
    total_messages = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(DISTINCT user_id) FROM messages")
    total_users = cursor.fetchone()[0]

    cursor.execute("""
        SELECT role, COUNT(*)
        FROM messages
        GROUP BY role
    """)
    by_role = dict(cursor.fetchall())

    logger.info("Updated database statistics:")
    logger.info(f"  Total messages: {total_messages}")
    logger.info(f"  By role: {by_role}")
    logger.info(f"  Active users: {total_users}")
    logger.info("=" * 80)


if __name__ == "__main__":
    main()
