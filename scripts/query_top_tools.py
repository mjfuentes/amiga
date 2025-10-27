#!/usr/bin/env python3
"""
Query agentlab.db for top 5 most used tools.

This script connects to the agentlab.db database and queries the tool_usage
table to find the most frequently used tools.
"""

import argparse
import sqlite3
import sys
from pathlib import Path
from typing import List, Tuple

# Add telegram_bot to path for config imports
sys.path.insert(0, str(Path(__file__).parent.parent))
from core.config import get_db_path_with_fallback


def get_top_tools(db_path: str, limit: int = 5) -> List[Tuple[str, int, float, float]]:
    """
    Query the database for the top N most used tools.

    Args:
        db_path: Path to the agentlab.db database file
        limit: Number of top tools to return (default: 5)

    Returns:
        List of tuples containing (tool_name, usage_count, success_rate, avg_duration_ms)
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    query = """
    SELECT
        tool_name,
        COUNT(*) as usage_count,
        ROUND(AVG(CASE WHEN success = 1 THEN 1.0 ELSE 0.0 END) * 100, 2) as success_rate,
        ROUND(AVG(duration_ms), 2) as avg_duration_ms
    FROM tool_usage
    GROUP BY tool_name
    ORDER BY usage_count DESC
    LIMIT ?
    """

    cursor.execute(query, (limit,))
    results = cursor.fetchall()
    conn.close()

    return results


def format_output(results: List[Tuple[str, int, float, float]]) -> None:
    """
    Format and print the results in a readable table.

    Args:
        results: List of tuples from get_top_tools()
    """
    if not results:
        print("No tool usage data found in the database.")
        return

    # Print header
    print("\n" + "=" * 80)
    print(f"{'Rank':<6} {'Tool Name':<30} {'Count':<10} {'Success %':<12} {'Avg Duration (ms)':<16}")
    print("=" * 80)

    # Print results
    for idx, (tool_name, count, success_rate, avg_duration) in enumerate(results, 1):
        duration_str = f"{avg_duration:.2f}" if avg_duration else "N/A"
        print(f"{idx:<6} {tool_name:<30} {count:<10} {success_rate:<12.2f} {duration_str:<16}")

    print("=" * 80 + "\n")


def main():
    """Main entry point for the script."""
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description="Query top 5 most used tools from AgentLab database")
    parser.add_argument(
        "--db-path",
        default=None,
        help="Path to database file (default: from config.py, supports AGENTLAB_DB_PATH env var)",
    )
    args = parser.parse_args()

    # Get database path using config helper (CLI arg > env var > default)
    db_path = Path(get_db_path_with_fallback(args.db_path))

    # Check if database exists
    if not db_path.exists():
        print(f"Error: Database not found at {db_path}", file=sys.stderr)
        sys.exit(1)

    # Query top 5 tools
    print(f"Querying database: {db_path}")
    results = get_top_tools(str(db_path), limit=5)

    # Display results
    format_output(results)

    # Print summary
    total_usage = sum(count for _, count, _, _ in results)
    print(f"Total usage across top 5 tools: {total_usage:,}")


if __name__ == "__main__":
    main()
