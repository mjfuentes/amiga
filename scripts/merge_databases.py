#!/usr/bin/env python3
"""
Database Merge Utility for AgentLab

Merges tool_usage records from a source database into a target database using
SQLite's ATTACH DATABASE feature. Supports dry-run mode for validation before
actual merge.

Usage:
    python merge_databases.py --source path/to/source.db --target path/to/target.db --dry-run
    python merge_databases.py --source path/to/source.db --target path/to/target.db

Features:
    - Transactional merge with ATTACH DATABASE
    - Automatic duplicate detection (timestamp + task_id + tool_name)
    - Dry-run mode for validation
    - Comprehensive integrity checks
    - Detailed logging and statistics
"""

import argparse
import logging
import sqlite3
import sys
from pathlib import Path
from typing import Any

# Add parent directory to path for config imports
sys.path.insert(0, str(Path(__file__).parent.parent))
from core.config import DATABASE_PATH_STR
from utils.logging_setup import setup_logging

# Configure logging
logger = setup_logging(__name__, console=True)


class DatabaseMerger:
    """Handles database merging operations with safety checks"""

    def __init__(self, source_path: str, target_path: str, dry_run: bool = False):
        """
        Initialize database merger

        Args:
            source_path: Path to source database
            target_path: Path to target database
            dry_run: If True, perform validation only without actual merge
        """
        self.source_path = Path(source_path)
        self.target_path = Path(target_path)
        self.dry_run = dry_run

        # Validate paths
        if not self.source_path.exists():
            raise FileNotFoundError(f"Source database not found: {self.source_path}")
        if not self.target_path.exists():
            raise FileNotFoundError(f"Target database not found: {self.target_path}")

        # Check if paths are the same (symlink case)
        self.is_same_file = self.source_path.resolve() == self.target_path.resolve()

    def validate_schema(self) -> tuple[bool, str]:
        """
        Validate that both databases have compatible tool_usage schemas

        Returns:
            Tuple of (is_valid, message)
        """
        logger.info("Validating database schemas...")

        try:
            # Connect to source
            source_conn = sqlite3.connect(str(self.source_path))
            source_cursor = source_conn.cursor()

            # Connect to target
            target_conn = sqlite3.connect(str(self.target_path))
            target_cursor = target_conn.cursor()

            # Get source schema
            source_cursor.execute(
                """
                SELECT sql FROM sqlite_master
                WHERE type='table' AND name='tool_usage'
            """
            )
            source_schema = source_cursor.fetchone()

            # Get target schema
            target_cursor.execute(
                """
                SELECT sql FROM sqlite_master
                WHERE type='table' AND name='tool_usage'
            """
            )
            target_schema = target_cursor.fetchone()

            source_conn.close()
            target_conn.close()

            # Check if table exists in both
            if not source_schema:
                return False, "Source database missing tool_usage table"
            if not target_schema:
                return False, "Target database missing tool_usage table"

            # Note: We don't require exact schema match because target may have
            # additional columns (error_category, screenshot_path) that source lacks
            logger.info("✓ Schema validation passed")
            return True, "Schemas compatible"

        except Exception as e:
            return False, f"Schema validation error: {e}"

    def get_record_count(self, db_path: Path, table: str = "tool_usage") -> int:
        """Get record count from a database table"""
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute(f"SELECT COUNT(*) FROM {table}")  # nosec B608
        count = cursor.fetchone()[0]
        conn.close()
        return count

    def get_statistics(self, db_path: Path) -> dict[str, Any]:
        """Get detailed statistics from tool_usage table"""
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        stats = {}

        # Total records
        cursor.execute("SELECT COUNT(*) FROM tool_usage")
        stats["total_records"] = cursor.fetchone()[0]

        # Date range
        cursor.execute("SELECT MIN(timestamp), MAX(timestamp) FROM tool_usage")
        min_ts, max_ts = cursor.fetchone()
        stats["date_range"] = {"min": min_ts, "max": max_ts}

        # Unique tasks
        cursor.execute("SELECT COUNT(DISTINCT task_id) FROM tool_usage")
        stats["unique_tasks"] = cursor.fetchone()[0]

        # Tool breakdown
        cursor.execute(
            """
            SELECT tool_name, COUNT(*) as count
            FROM tool_usage
            GROUP BY tool_name
            ORDER BY count DESC
            LIMIT 10
        """
        )
        stats["top_tools"] = [{"tool": row[0], "count": row[1]} for row in cursor.fetchall()]

        # Success/failure counts
        cursor.execute(
            """
            SELECT
                SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) as successes,
                SUM(CASE WHEN success = 0 THEN 1 ELSE 0 END) as failures,
                SUM(CASE WHEN success IS NULL THEN 1 ELSE 0 END) as unknown
            FROM tool_usage
        """
        )
        success_stats = cursor.fetchone()
        stats["success_breakdown"] = {
            "successes": success_stats[0] or 0,
            "failures": success_stats[1] or 0,
            "unknown": success_stats[2] or 0,
        }

        conn.close()
        return stats

    def check_for_duplicates(self) -> tuple[int, list[dict]]:
        """
        Check for potential duplicate records between databases

        Returns:
            Tuple of (duplicate_count, sample_duplicates)
        """
        logger.info("Checking for potential duplicates...")

        target_conn = sqlite3.connect(str(self.target_path))
        target_cursor = target_conn.cursor()

        # Attach source database
        target_cursor.execute(f"ATTACH DATABASE '{self.source_path}' AS source")

        # Find duplicates based on timestamp + task_id + tool_name
        target_cursor.execute(
            """
            SELECT
                COUNT(*) as dup_count
            FROM source.tool_usage s
            WHERE EXISTS (
                SELECT 1 FROM main.tool_usage t
                WHERE t.timestamp = s.timestamp
                AND t.task_id = s.task_id
                AND t.tool_name = s.tool_name
            )
        """
        )
        duplicate_count = target_cursor.fetchone()[0]

        # Get sample duplicates
        sample_duplicates = []
        if duplicate_count > 0:
            target_cursor.execute(
                """
                SELECT
                    s.timestamp, s.task_id, s.tool_name, s.duration_ms
                FROM source.tool_usage s
                WHERE EXISTS (
                    SELECT 1 FROM main.tool_usage t
                    WHERE t.timestamp = s.timestamp
                    AND t.task_id = s.task_id
                    AND t.tool_name = s.tool_name
                )
                LIMIT 5
            """
            )
            sample_duplicates = [
                {
                    "timestamp": row[0],
                    "task_id": row[1],
                    "tool_name": row[2],
                    "duration_ms": row[3],
                }
                for row in target_cursor.fetchall()
            ]

        target_cursor.execute("DETACH DATABASE source")
        target_conn.close()

        return duplicate_count, sample_duplicates

    def perform_merge(self) -> dict[str, Any]:
        """
        Perform the actual database merge

        Returns:
            Dictionary with merge statistics
        """
        logger.info("=" * 80)
        logger.info("DATABASE MERGE OPERATION")
        logger.info("=" * 80)
        logger.info(f"Source: {self.source_path}")
        logger.info(f"Target: {self.target_path}")
        logger.info(f"Mode: {'DRY-RUN' if self.dry_run else 'LIVE'}")
        logger.info("=" * 80)

        # Check if same file (symlink case)
        if self.is_same_file:
            logger.warning("⚠️  Source and target are the same file (symlink detected)")
            logger.info("No merge needed - databases are already unified")
            return {
                "status": "skipped",
                "reason": "source_and_target_are_same_file",
                "source_count": self.get_record_count(self.source_path),
                "target_count": self.get_record_count(self.target_path),
                "merged": 0,
            }

        # Validate schemas
        schema_valid, schema_msg = self.validate_schema()
        if not schema_valid:
            logger.error(f"✗ Schema validation failed: {schema_msg}")
            return {
                "status": "failed",
                "reason": schema_msg,
            }

        # Get pre-merge statistics
        source_count_before = self.get_record_count(self.source_path)
        target_count_before = self.get_record_count(self.target_path)

        logger.info(f"Source records: {source_count_before:,}")
        logger.info(f"Target records: {target_count_before:,}")

        # Check for empty source
        if source_count_before == 0:
            logger.info("ℹ️  Source database is empty - nothing to merge")
            return {
                "status": "skipped",
                "reason": "source_empty",
                "source_count": source_count_before,
                "target_count": target_count_before,
                "merged": 0,
            }

        # Check for duplicates
        duplicate_count, sample_duplicates = self.check_for_duplicates()
        if duplicate_count > 0:
            logger.warning(f"⚠️  Found {duplicate_count} potential duplicates")
            logger.info("Sample duplicates:")
            for dup in sample_duplicates[:3]:
                logger.info(f"  - {dup['timestamp']} | {dup['task_id']} | {dup['tool_name']}")

        # Calculate expected merge count (excluding duplicates)
        expected_new_records = source_count_before - duplicate_count

        if self.dry_run:
            logger.info("")
            logger.info("=" * 80)
            logger.info("DRY-RUN SUMMARY")
            logger.info("=" * 80)
            logger.info(f"Would merge {expected_new_records:,} new records")
            logger.info(f"Would skip {duplicate_count:,} duplicates")
            logger.info(f"Target would have {target_count_before + expected_new_records:,} records")
            logger.info("=" * 80)
            logger.info("✓ Dry-run validation complete - ready for actual merge")

            return {
                "status": "dry_run",
                "source_count": source_count_before,
                "target_count_before": target_count_before,
                "target_count_after": target_count_before + expected_new_records,
                "duplicates_found": duplicate_count,
                "would_merge": expected_new_records,
            }

        # Perform actual merge
        logger.info("")
        logger.info("Performing merge...")

        try:
            target_conn = sqlite3.connect(str(self.target_path))
            target_cursor = target_conn.cursor()

            # Begin transaction
            target_cursor.execute("BEGIN TRANSACTION")

            # Attach source database
            target_cursor.execute(f"ATTACH DATABASE '{self.source_path}' AS source")

            # Merge records, excluding duplicates
            target_cursor.execute(
                """
                INSERT INTO main.tool_usage (
                    timestamp, task_id, tool_name, duration_ms, success, error, parameters
                )
                SELECT
                    timestamp, task_id, tool_name, duration_ms, success, error, parameters
                FROM source.tool_usage s
                WHERE NOT EXISTS (
                    SELECT 1 FROM main.tool_usage t
                    WHERE t.timestamp = s.timestamp
                    AND t.task_id = s.task_id
                    AND t.tool_name = s.tool_name
                )
            """
            )

            merged_count = target_cursor.rowcount

            # Commit transaction
            target_conn.commit()

            # Detach source
            target_cursor.execute("DETACH DATABASE source")

            target_conn.close()

            # Get post-merge count
            target_count_after = self.get_record_count(self.target_path)

            logger.info("")
            logger.info("=" * 80)
            logger.info("MERGE COMPLETE")
            logger.info("=" * 80)
            logger.info(f"✓ Merged {merged_count:,} new records")
            logger.info(f"✓ Skipped {duplicate_count:,} duplicates")
            logger.info(f"✓ Target now has {target_count_after:,} records")
            logger.info("=" * 80)

            return {
                "status": "success",
                "source_count": source_count_before,
                "target_count_before": target_count_before,
                "target_count_after": target_count_after,
                "merged": merged_count,
                "duplicates_skipped": duplicate_count,
            }

        except Exception as e:
            logger.error(f"✗ Merge failed: {e}")
            if target_conn:
                target_conn.rollback()
                target_conn.close()
            return {
                "status": "failed",
                "reason": str(e),
            }

    def verify_integrity(self) -> tuple[bool, str]:
        """
        Verify database integrity after merge

        Returns:
            Tuple of (is_valid, message)
        """
        logger.info("")
        logger.info("Verifying database integrity...")

        try:
            conn = sqlite3.connect(str(self.target_path))
            cursor = conn.cursor()

            # Run integrity check
            cursor.execute("PRAGMA integrity_check")
            result = cursor.fetchone()[0]

            if result != "ok":
                conn.close()
                return False, f"Integrity check failed: {result}"

            # Check for orphaned records (optional - task_id references)
            cursor.execute(
                """
                SELECT COUNT(*) FROM tool_usage
                WHERE task_id NOT IN (SELECT task_id FROM tasks)
            """
            )
            orphaned = cursor.fetchone()[0]
            if orphaned > 0:
                logger.warning(f"⚠️  Found {orphaned} tool_usage records with no matching task")

            # Check for invalid timestamps
            cursor.execute(
                """
                SELECT COUNT(*) FROM tool_usage
                WHERE timestamp IS NULL OR timestamp = ''
            """
            )
            invalid_timestamps = cursor.fetchone()[0]
            if invalid_timestamps > 0:
                logger.warning(f"⚠️  Found {invalid_timestamps} records with invalid timestamps")

            conn.close()

            logger.info("✓ Integrity verification passed")
            return True, "Integrity check OK"

        except Exception as e:
            return False, f"Integrity check error: {e}"


def main():
    """Main entry point for database merge utility"""
    parser = argparse.ArgumentParser(
        description="Merge tool_usage records from source database into target database",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
Examples:
  # Dry-run to validate merge
  python merge_databases.py --source data/old.db --target {DATABASE_PATH_STR} --dry-run

  # Actual merge
  python merge_databases.py --source data/old.db --target {DATABASE_PATH_STR}

  # With statistics
  python merge_databases.py --source data/old.db --target {DATABASE_PATH_STR} --stats
        """,
    )

    parser.add_argument(
        "--source",
        required=True,
        help="Path to source database",
    )

    parser.add_argument(
        "--target",
        required=True,
        help="Path to target database",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate without performing actual merge",
    )

    parser.add_argument(
        "--stats",
        action="store_true",
        help="Show detailed statistics after merge",
    )

    args = parser.parse_args()

    try:
        # Create merger
        merger = DatabaseMerger(
            source_path=args.source,
            target_path=args.target,
            dry_run=args.dry_run,
        )

        # Perform merge
        result = merger.perform_merge()

        # Show statistics if requested
        if args.stats and result["status"] in ["success", "skipped"]:
            logger.info("")
            logger.info("=" * 80)
            logger.info("DETAILED STATISTICS")
            logger.info("=" * 80)
            stats = merger.get_statistics(merger.target_path)
            logger.info(f"Total records: {stats['total_records']:,}")
            logger.info(f"Date range: {stats['date_range']['min']} to {stats['date_range']['max']}")
            logger.info(f"Unique tasks: {stats['unique_tasks']:,}")
            logger.info(f"Success rate: {stats['success_breakdown']['successes']}/{stats['total_records']}")
            logger.info("")
            logger.info("Top 10 tools:")
            for tool in stats["top_tools"]:
                logger.info(f"  {tool['tool']}: {tool['count']:,}")

        # Verify integrity if not dry-run
        if not args.dry_run and result["status"] == "success":
            valid, msg = merger.verify_integrity()
            if not valid:
                logger.error(f"✗ {msg}")
                sys.exit(1)

        # Exit code based on result
        if result["status"] in ["success", "skipped", "dry_run"]:
            sys.exit(0)
        else:
            sys.exit(1)

    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
