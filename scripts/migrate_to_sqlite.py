#!/usr/bin/env python3
"""
Migration script to populate SQLite analytics database with historical session data.
Reads from data/sessions.json and populates the messages table.
"""

import json
import logging
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.config import DATABASE_PATH_STR, SESSIONS_FILE_STR
from tasks.analytics import AnalyticsDB
from tasks.database import Database
from utils.logging_setup import setup_logging

logger = setup_logging(__name__, console=True)


def migrate_sessions_to_sqlite(sessions_file: Path, db_path: Path):
    """
    Migrate session data from JSON to SQLite.

    Args:
        sessions_file: Path to sessions.json
        db_path: Path to SQLite database
    """
    if not sessions_file.exists():
        logger.error(f"Sessions file not found: {sessions_file}")
        return

    # Load sessions data
    logger.info(f"Loading sessions from {sessions_file}")
    with open(sessions_file) as f:
        sessions_data = json.load(f)

    logger.info(f"Found {len(sessions_data)} user sessions")

    # Initialize database and analytics wrapper
    db = Database(db_path)
    analytics = AnalyticsDB(db)

    # Migrate each user's session
    total_messages = 0
    for user_id_str, session_data in sessions_data.items():
        user_id = int(user_id_str)
        history = session_data.get("history", [])

        logger.info(f"Migrating {len(history)} messages for user {user_id}")

        for msg in history:
            role = msg.get("role")
            content = msg.get("content")
            timestamp = msg.get("timestamp")

            # Legacy messages don't have token data, that's OK
            # We're primarily interested in going forward
            analytics.log_message(
                user_id=user_id,
                role=role,
                content=content,
                conversation_id=f"session_{user_id}",  # Use session as conversation ID
                input_method="text",  # Assume text for historical data
            )

            total_messages += 1

    logger.info(f"Migration complete: {total_messages} messages migrated from {len(sessions_data)} users")

    # Display statistics
    stats = analytics.get_message_statistics(days=365)  # All time
    logger.info(f"Database statistics:")
    logger.info(f"  Total messages: {stats['total_messages']}")
    logger.info(f"  By role: {stats['by_role']}")
    logger.info(f"  Active users: {stats['active_users']}")

    db.close()


def main():
    """Main migration function"""
    # Use config paths
    sessions_file = Path(SESSIONS_FILE_STR)
    db_path = Path(DATABASE_PATH_STR)

    logger.info("=" * 80)
    logger.info("AgentLab Session Data Migration to SQLite")
    logger.info("=" * 80)
    logger.info(f"Sessions file: {sessions_file}")
    logger.info(f"Database file: {db_path}")
    logger.info("")

    # Confirm before proceeding
    if sessions_file.exists():
        response = input("Proceed with migration? This will add data to the database. [y/N]: ")
        if response.lower() != "y":
            logger.info("Migration cancelled")
            return

        migrate_sessions_to_sqlite(sessions_file, db_path)
    else:
        logger.error(f"Sessions file not found: {sessions_file}")
        logger.error(f"Please ensure {sessions_file} exists")


if __name__ == "__main__":
    main()
