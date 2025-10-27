#!/usr/bin/env python3
"""
Deep dive into error patterns and agent spawning
"""

import argparse
import json
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

# Add telegram_bot to path for config imports
sys.path.insert(0, str(Path(__file__).parent.parent))
from core.config import get_db_path_with_fallback

# DB_PATH will be set from CLI args or config in main()

def connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def analyze_edit_failures():
    """Analyze Edit tool failures in detail"""
    conn = connect()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT timestamp, task_id, error, parameters
        FROM tool_usage
        WHERE tool_name = 'Edit' AND success = 0
        ORDER BY timestamp DESC
        LIMIT 20
    """)

    print("\n" + "="*80)
    print("EDIT TOOL FAILURE SAMPLES")
    print("="*80)

    for row in cursor.fetchall():
        print(f"\nTimestamp: {row['timestamp']}")
        print(f"Task: {row['task_id'][:40]}...")
        print(f"Error: {row['error'][:200] if row['error'] else 'N/A'}")
        if row['parameters']:
            try:
                params = json.loads(row['parameters'])
                if 'file_path' in params:
                    print(f"File: {params['file_path']}")
            except:
                pass

    conn.close()

def analyze_read_failures():
    """Analyze Read tool failures"""
    conn = connect()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT timestamp, task_id, error, parameters
        FROM tool_usage
        WHERE tool_name = 'Read' AND success = 0
        ORDER BY timestamp DESC
        LIMIT 20
    """)

    print("\n" + "="*80)
    print("READ TOOL FAILURE SAMPLES")
    print("="*80)

    for row in cursor.fetchall():
        print(f"\nTimestamp: {row['timestamp']}")
        print(f"Task: {row['task_id'][:40]}...")
        print(f"Error: {row['error'][:200] if row['error'] else 'N/A'}")
        if row['parameters']:
            try:
                params = json.loads(row['parameters'])
                if 'file_path' in params:
                    print(f"File: {params['file_path']}")
            except:
                pass

    conn.close()

def analyze_webfetch_failures():
    """Analyze WebFetch failures"""
    conn = connect()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT timestamp, task_id, error, parameters
        FROM tool_usage
        WHERE tool_name = 'WebFetch'
        ORDER BY timestamp DESC
    """)

    print("\n" + "="*80)
    print("WEBFETCH USAGE (ALL)")
    print("="*80)

    for row in cursor.fetchall():
        print(f"\nTimestamp: {row['timestamp']}")
        print(f"Task: {row['task_id'][:40]}...")
        print(f"Error: {row['error'][:300] if row['error'] else 'SUCCESS'}")
        if row['parameters']:
            try:
                params = json.loads(row['parameters'])
                if 'url' in params:
                    print(f"URL: {params['url']}")
            except:
                pass

    conn.close()

def analyze_task_spawning():
    """Check if orchestrator is spawning agents"""
    conn = connect()
    cursor = conn.cursor()

    # Get Task tool usage (agent spawning)
    cursor.execute("""
        SELECT
            tu.timestamp,
            t.task_id,
            t.agent_type,
            t.description,
            tu.success,
            tu.error,
            tu.parameters
        FROM tool_usage tu
        JOIN tasks t ON tu.task_id = t.task_id
        WHERE tu.tool_name = 'Task'
        ORDER BY tu.timestamp DESC
    """)

    print("\n" + "="*80)
    print("AGENT SPAWNING ANALYSIS (Task tool usage)")
    print("="*80)

    for row in cursor.fetchall():
        print(f"\nTimestamp: {row['timestamp']}")
        print(f"Parent Agent: {row['agent_type']}")
        print(f"Success: {row['success']}")
        if row['parameters']:
            try:
                params = json.loads(row['parameters'])
                print(f"  Subagent Type: {params.get('subagent_type', 'N/A')}")
                print(f"  Description: {params.get('description', 'N/A')[:80]}...")
            except:
                pass
        if row['error']:
            print(f"  Error: {row['error'][:200]}")

    conn.close()

def analyze_agent_distribution():
    """Check distribution of agent types"""
    conn = connect()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            agent_type,
            status,
            COUNT(*) as count
        FROM tasks
        GROUP BY agent_type, status
        ORDER BY agent_type, status
    """)

    print("\n" + "="*80)
    print("AGENT TYPE DISTRIBUTION (All Time)")
    print("="*80)

    agent_stats = defaultdict(lambda: defaultdict(int))
    for row in cursor.fetchall():
        agent_stats[row['agent_type']][row['status']] = row['count']

    for agent, statuses in sorted(agent_stats.items()):
        print(f"\n{agent}:")
        total = sum(statuses.values())
        for status, count in sorted(statuses.items()):
            pct = (count / total * 100) if total > 0 else 0
            print(f"  {status}: {count} ({pct:.1f}%)")

    conn.close()

def analyze_orchestrator_behavior():
    """Analyze orchestrator task patterns"""
    conn = connect()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            task_id,
            description,
            status,
            workflow,
            created_at,
            updated_at,
            result
        FROM tasks
        WHERE agent_type = 'orchestrator'
        ORDER BY created_at DESC
        LIMIT 20
    """)

    print("\n" + "="*80)
    print("RECENT ORCHESTRATOR TASKS")
    print("="*80)

    for row in cursor.fetchall():
        print(f"\nTask: {row['task_id'][:40]}...")
        print(f"  Description: {row['description'][:80]}...")
        print(f"  Status: {row['status']}")
        print(f"  Workflow: {row['workflow'] or 'N/A'}")
        print(f"  Duration: {row['created_at']} to {row['updated_at']}")
        if row['result']:
            print(f"  Result: {row['result'][:150]}...")

    conn.close()

def analyze_failed_tasks():
    """Analyze failed task patterns"""
    conn = connect()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            agent_type,
            error,
            COUNT(*) as count
        FROM tasks
        WHERE status = 'failed'
        AND error IS NOT NULL
        GROUP BY agent_type, SUBSTR(error, 1, 100)
        ORDER BY count DESC
        LIMIT 20
    """)

    print("\n" + "="*80)
    print("COMMON FAILURE PATTERNS")
    print("="*80)

    for row in cursor.fetchall():
        print(f"\nAgent: {row['agent_type']}")
        print(f"Count: {row['count']}")
        print(f"Error: {row['error'][:200]}...")

    conn.close()

def main():
    global DB_PATH

    # Parse command-line arguments
    parser = argparse.ArgumentParser(description="Deep dive into error patterns and agent spawning")
    parser.add_argument(
        "--db-path",
        default=None,
        help="Path to database file (default: from config.py, supports AGENTLAB_DB_PATH env var)",
    )
    args = parser.parse_args()

    # Set DB_PATH using config helper (CLI arg > env var > default)
    DB_PATH = get_db_path_with_fallback(args.db_path)

    print(f"Analyzing database: {DB_PATH}\n")

    analyze_agent_distribution()
    analyze_orchestrator_behavior()
    analyze_task_spawning()
    analyze_edit_failures()
    analyze_read_failures()
    analyze_webfetch_failures()
    analyze_failed_tasks()

if __name__ == "__main__":
    main()
