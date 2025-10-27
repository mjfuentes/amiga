#!/usr/bin/env python3
"""
Check if tool usage improved after hook fix deployment
"""

import argparse
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Add telegram_bot to path for config imports
sys.path.insert(0, str(Path(__file__).parent.parent))
from core.config import get_db_path_with_fallback

# DB_PATH will be set from CLI args or config in main()

def connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def get_commit_time():
    """Get approximate time of hook fix deployment"""
    # The fix was committed around 2025-10-20 13:00-14:00
    # Let's use 2025-10-20 14:00 as cutoff
    return "2025-10-20T14:00:00"

def compare_before_after():
    """Compare tool usage before and after fix"""
    conn = connect()
    cursor = conn.cursor()

    cutoff = get_commit_time()

    print("="*80)
    print("TOOL USAGE COMPARISON: BEFORE vs AFTER HOOK FIX")
    print("="*80)
    print(f"Cutoff time: {cutoff}")
    print()

    # Get stats before fix
    cursor.execute("""
        SELECT
            tool_name,
            COUNT(*) as total,
            SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) as successes,
            SUM(CASE WHEN success = 0 THEN 1 ELSE 0 END) as failures
        FROM tool_usage
        WHERE timestamp < ?
        AND tool_name IN ('Edit', 'Read', 'Write', 'Grep')
        GROUP BY tool_name
        ORDER BY tool_name
    """, (cutoff,))

    before_stats = {}
    for row in cursor.fetchall():
        before_stats[row['tool_name']] = {
            'total': row['total'],
            'successes': row['successes'],
            'failures': row['failures'],
            'success_rate': (row['successes'] / row['total'] * 100) if row['total'] > 0 else 0
        }

    # Get stats after fix
    cursor.execute("""
        SELECT
            tool_name,
            COUNT(*) as total,
            SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) as successes,
            SUM(CASE WHEN success = 0 THEN 1 ELSE 0 END) as failures
        FROM tool_usage
        WHERE timestamp >= ?
        AND tool_name IN ('Edit', 'Read', 'Write', 'Grep')
        GROUP BY tool_name
        ORDER BY tool_name
    """, (cutoff,))

    after_stats = {}
    for row in cursor.fetchall():
        after_stats[row['tool_name']] = {
            'total': row['total'],
            'successes': row['successes'],
            'failures': row['failures'],
            'success_rate': (row['successes'] / row['total'] * 100) if row['total'] > 0 else 0
        }

    # Display comparison
    print(f"{'Tool':<15} {'Period':<10} {'Total':<10} {'Success':<10} {'Failures':<10} {'Rate':<10}")
    print("-"*80)

    for tool in ['Edit', 'Read', 'Write', 'Grep']:
        if tool in before_stats:
            b = before_stats[tool]
            print(f"{tool:<15} {'BEFORE':<10} {b['total']:<10} {b['successes']:<10} {b['failures']:<10} {b['success_rate']:>6.1f}%")

        if tool in after_stats:
            a = after_stats[tool]
            print(f"{tool:<15} {'AFTER':<10} {a['total']:<10} {a['successes']:<10} {a['failures']:<10} {a['success_rate']:>6.1f}%")

            # Calculate improvement
            if tool in before_stats:
                improvement = a['success_rate'] - before_stats[tool]['success_rate']
                status = "✅ IMPROVED" if improvement > 0 else "⚠️  WORSE" if improvement < 0 else "→ SAME"
                print(f"{'':<15} {status:<10} {'':<10} {'':<10} {'':<10} {improvement:>+6.1f}%")

        print()

    conn.close()

def get_recent_tasks():
    """Check recent tasks for branch usage"""
    conn = connect()
    cursor = conn.cursor()

    cutoff = get_commit_time()

    cursor.execute("""
        SELECT
            task_id,
            description,
            status,
            created_at,
            workflow
        FROM tasks
        WHERE created_at >= ?
        ORDER BY created_at DESC
        LIMIT 10
    """, (cutoff,))

    print("\n" + "="*80)
    print("RECENT TASKS AFTER FIX")
    print("="*80)

    tasks = cursor.fetchall()
    if not tasks:
        print("No tasks created after fix deployment")
    else:
        for row in tasks:
            print(f"\nTask: {row['task_id'][:30]}...")
            print(f"  Description: {row['description'][:60]}...")
            print(f"  Status: {row['status']}")
            print(f"  Workflow: {row['workflow'] or 'N/A'}")
            print(f"  Created: {row['created_at']}")

    conn.close()

def check_recent_errors():
    """Check if recent errors are still false positives"""
    conn = connect()
    cursor = conn.cursor()

    cutoff = get_commit_time()

    cursor.execute("""
        SELECT
            timestamp,
            task_id,
            tool_name,
            success,
            error
        FROM tool_usage
        WHERE timestamp >= ?
        AND tool_name IN ('Edit', 'Read', 'Write')
        ORDER BY timestamp DESC
        LIMIT 20
    """, (cutoff,))

    print("\n" + "="*80)
    print("RECENT TOOL OPERATIONS AFTER FIX (Last 20)")
    print("="*80)

    rows = cursor.fetchall()
    if not rows:
        print("No tool usage after fix deployment yet")
    else:
        for row in rows:
            status = "✅ SUCCESS" if row['success'] else "❌ FAILED"
            print(f"\n{row['timestamp']} - {row['tool_name']} - {status}")
            if not row['success'] and row['error']:
                print(f"  Error: {row['error'][:100]}")

    conn.close()

def get_latest_timestamp():
    """Check when last activity was"""
    conn = connect()
    cursor = conn.cursor()

    cursor.execute("SELECT MAX(timestamp) as latest FROM tool_usage")
    row = cursor.fetchone()

    print("\n" + "="*80)
    print("ACTIVITY CHECK")
    print("="*80)
    print(f"Latest tool usage: {row['latest']}")
    print(f"Fix deployed at: {get_commit_time()}")

    if row['latest']:
        latest = datetime.fromisoformat(row['latest'].replace('Z', '+00:00'))
        cutoff = datetime.fromisoformat(get_commit_time())

        if latest < cutoff:
            print(f"\n⚠️  WARNING: No activity since fix deployment!")
            print(f"   Bot may not be running or no tasks executed yet.")
        else:
            time_since = (datetime.now() - latest.replace(tzinfo=None)).total_seconds() / 60
            print(f"\n✅ Recent activity: {time_since:.1f} minutes ago")

    conn.close()

def main():
    global DB_PATH

    # Parse command-line arguments
    parser = argparse.ArgumentParser(description="Check if tool usage improved after hook fix deployment")
    parser.add_argument(
        "--db-path",
        default=None,
        help="Path to database file (default: from config.py, supports AGENTLAB_DB_PATH env var)",
    )
    args = parser.parse_args()

    # Set DB_PATH using config helper (CLI arg > env var > default)
    DB_PATH = get_db_path_with_fallback(args.db_path)

    print(f"Analyzing database: {DB_PATH}\n")

    get_latest_timestamp()
    compare_before_after()
    check_recent_errors()
    get_recent_tasks()

if __name__ == "__main__":
    main()
