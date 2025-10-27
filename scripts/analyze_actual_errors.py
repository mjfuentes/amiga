#!/usr/bin/env python3
"""
Analyze actual tool outputs to verify false positive hypothesis
"""

import argparse
import json
import sqlite3
import sys
from pathlib import Path

# Add telegram_bot to path for config imports
sys.path.insert(0, str(Path(__file__).parent.parent))
from core.config import get_db_path_with_fallback

# DB_PATH will be set from CLI args or config in main()

def connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def check_false_positives():
    """Check if failed Edit/Read operations have 'error' in output"""
    conn = connect()
    cursor = conn.cursor()

    # Get recent failed Edit operations
    cursor.execute("""
        SELECT
            timestamp,
            task_id,
            tool_name,
            error,
            parameters
        FROM tool_usage
        WHERE tool_name IN ('Edit', 'Read', 'Write')
        AND success = 0
        ORDER BY timestamp DESC
        LIMIT 30
    """)

    print("="*80)
    print("ANALYZING FAILED TOOL OPERATIONS")
    print("="*80)

    false_positives = 0
    total = 0

    for row in cursor.fetchall():
        total += 1
        print(f"\n{row['tool_name']} - {row['timestamp']}")
        print(f"  Error: {row['error']}")

        # Check parameters for file content
        if row['parameters']:
            try:
                params = json.loads(row['parameters'])

                # For Edit operations, check if old_string or new_string contains "error"
                if row['tool_name'] == 'Edit':
                    old_str = params.get('old_string', '')
                    new_str = params.get('new_string', '')

                    if 'error' in old_str.lower() or 'error' in new_str.lower():
                        print(f"  ⚠️  FALSE POSITIVE: Edit involves error handling code")
                        false_positives += 1
                    else:
                        print(f"  ✓ Likely genuine failure")

                # For Read operations
                elif row['tool_name'] == 'Read':
                    file_path = params.get('file_path', '')
                    print(f"  File: {file_path}")

                    # Can't know file content from parameters alone
                    if row['error'] == 'Tool output contains error':
                        print(f"  ⚠️  SUSPECTED FALSE POSITIVE: Generic error message")
                        false_positives += 1

                # For Write operations
                elif row['tool_name'] == 'Write':
                    content = params.get('content', '')
                    if 'error' in content.lower():
                        print(f"  ⚠️  FALSE POSITIVE: Writing error handling code")
                        false_positives += 1

            except:
                pass

    print("\n" + "="*80)
    print(f"ANALYSIS SUMMARY")
    print("="*80)
    print(f"Total failed operations: {total}")
    print(f"Suspected false positives: {false_positives}")
    print(f"False positive rate: {false_positives/total*100:.1f}%")

    conn.close()

def check_successful_with_errors():
    """Check if successful operations might have 'error' in output"""
    conn = connect()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            tool_name,
            COUNT(*) as success_count
        FROM tool_usage
        WHERE success = 1
        AND tool_name IN ('Edit', 'Read', 'Write', 'Grep')
        GROUP BY tool_name
    """)

    print("\n" + "="*80)
    print("SUCCESSFUL OPERATIONS (baseline)")
    print("="*80)

    for row in cursor.fetchall():
        print(f"{row['tool_name']}: {row['success_count']} successes")

    conn.close()

def check_json_logs():
    """Check if tool_usage.json has more detail"""
    import json
    from pathlib import Path

    json_file = Path("data/tool_usage.json")
    if json_file.exists():
        with open(json_file) as f:
            data = json.load(f)

        print("\n" + "="*80)
        print("RECENT TOOL_USAGE.JSON ENTRIES")
        print("="*80)

        # Get last 10 Edit failures
        edit_failures = [
            r for r in data
            if r.get('tool_name') == 'Edit'
            and r.get('success') == False
        ][-10:]

        for record in edit_failures:
            print(f"\n{record['timestamp']}")
            print(f"  Tool: {record['tool_name']}")
            print(f"  Error: {record['error']}")
            print(f"  Task: {record['task_id'][:20]}...")

def main():
    global DB_PATH

    # Parse command-line arguments
    parser = argparse.ArgumentParser(description="Analyze actual tool outputs to verify false positive hypothesis")
    parser.add_argument(
        "--db-path",
        default=None,
        help="Path to database file (default: from config.py, supports AGENTLAB_DB_PATH env var)",
    )
    args = parser.parse_args()

    # Set DB_PATH using config helper (CLI arg > env var > default)
    DB_PATH = get_db_path_with_fallback(args.db_path)

    print(f"Analyzing database: {DB_PATH}\n")

    check_false_positives()
    check_successful_with_errors()
    check_json_logs()

if __name__ == "__main__":
    main()
