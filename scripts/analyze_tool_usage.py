#!/usr/bin/env python3
"""
Analyze tool usage patterns from AgentLab database
"""

import argparse
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

# Add parent directory to path for config imports
sys.path.insert(0, str(Path(__file__).parent.parent))
from core.config import get_db_path_with_fallback

# DB_PATH will be set from CLI args or config in main()

def connect():
    """Connect to database"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def analyze_tool_usage_by_task():
    """Analyze which tools are used by each task/agent"""
    conn = connect()
    cursor = conn.cursor()

    # Get tasks with their tool usage
    cursor.execute("""
        SELECT
            t.task_id,
            t.agent_type,
            t.workflow,
            t.description,
            t.status,
            COUNT(tu.id) as tool_calls,
            GROUP_CONCAT(tu.tool_name) as tools_used
        FROM tasks t
        LEFT JOIN tool_usage tu ON t.task_id = tu.task_id
        GROUP BY t.task_id
        ORDER BY t.created_at DESC
        LIMIT 50
    """)

    print("\n" + "="*80)
    print("RECENT TASKS AND THEIR TOOL USAGE")
    print("="*80)

    for row in cursor.fetchall():
        print(f"\nTask: {row['task_id'][:40]}...")
        print(f"  Agent: {row['agent_type']}")
        print(f"  Workflow: {row['workflow'] or 'N/A'}")
        print(f"  Status: {row['status']}")
        print(f"  Tool Calls: {row['tool_calls']}")
        if row['tools_used']:
            tools = row['tools_used'].split(',')
            tool_counts = {}
            for tool in tools:
                tool_counts[tool] = tool_counts.get(tool, 0) + 1
            print(f"  Tools: {', '.join([f'{k}({v})' for k, v in sorted(tool_counts.items())])}")

    conn.close()

def analyze_tool_frequency():
    """Analyze tool usage frequency and patterns"""
    conn = connect()
    cursor = conn.cursor()

    # Overall tool usage stats
    cursor.execute("""
        SELECT
            tool_name,
            COUNT(*) as total_uses,
            SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) as successes,
            SUM(CASE WHEN success = 0 THEN 1 ELSE 0 END) as failures,
            AVG(duration_ms) as avg_duration_ms,
            MIN(duration_ms) as min_duration_ms,
            MAX(duration_ms) as max_duration_ms
        FROM tool_usage
        WHERE timestamp >= datetime('now', '-7 days')
        GROUP BY tool_name
        ORDER BY total_uses DESC
    """)

    print("\n" + "="*80)
    print("TOOL USAGE STATISTICS (Last 7 Days)")
    print("="*80)
    print(f"{'Tool':<30} {'Uses':<8} {'Success':<10} {'Failures':<10} {'Avg Duration':<15}")
    print("-"*80)

    for row in cursor.fetchall():
        success_rate = (row['successes'] / row['total_uses'] * 100) if row['total_uses'] > 0 else 0
        avg_dur = row['avg_duration_ms'] if row['avg_duration_ms'] else 0
        print(f"{row['tool_name']:<30} {row['total_uses']:<8} {row['successes']:<10} {row['failures']:<10} {avg_dur:>10.2f} ms")

    conn.close()

def analyze_agent_tool_patterns():
    """Analyze which tools each agent type uses"""
    conn = connect()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            t.agent_type,
            tu.tool_name,
            COUNT(*) as usage_count
        FROM tasks t
        JOIN tool_usage tu ON t.task_id = tu.task_id
        WHERE t.created_at >= datetime('now', '-7 days')
        GROUP BY t.agent_type, tu.tool_name
        ORDER BY t.agent_type, usage_count DESC
    """)

    print("\n" + "="*80)
    print("TOOL USAGE BY AGENT TYPE (Last 7 Days)")
    print("="*80)

    agent_tools = defaultdict(list)
    for row in cursor.fetchall():
        agent_tools[row['agent_type']].append((row['tool_name'], row['usage_count']))

    for agent, tools in sorted(agent_tools.items()):
        print(f"\n{agent}:")
        for tool, count in tools:
            print(f"  - {tool}: {count} uses")

    conn.close()

def analyze_workflow_patterns():
    """Analyze tool usage by workflow"""
    conn = connect()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            t.workflow,
            COUNT(DISTINCT t.task_id) as task_count,
            COUNT(tu.id) as total_tool_calls,
            AVG(tu.duration_ms) as avg_duration
        FROM tasks t
        LEFT JOIN tool_usage tu ON t.task_id = tu.task_id
        WHERE t.workflow IS NOT NULL
        AND t.created_at >= datetime('now', '-7 days')
        GROUP BY t.workflow
        ORDER BY task_count DESC
    """)

    print("\n" + "="*80)
    print("WORKFLOW USAGE PATTERNS (Last 7 Days)")
    print("="*80)
    print(f"{'Workflow':<30} {'Tasks':<10} {'Tool Calls':<15} {'Avg Duration':<15}")
    print("-"*80)

    for row in cursor.fetchall():
        avg_dur = row['avg_duration'] if row['avg_duration'] else 0
        print(f"{row['workflow']:<30} {row['task_count']:<10} {row['total_tool_calls']:<15} {avg_dur:>10.2f} ms")

    conn.close()

def analyze_research_agent_compliance():
    """Check if research_agent is using the right tools"""
    conn = connect()
    cursor = conn.cursor()

    # Expected tools for research_agent
    expected_tools = {'Read', 'Glob', 'Grep', 'WebSearch', 'WebFetch'}

    cursor.execute("""
        SELECT
            t.task_id,
            t.description,
            GROUP_CONCAT(DISTINCT tu.tool_name) as tools_used
        FROM tasks t
        JOIN tool_usage tu ON t.task_id = tu.task_id
        WHERE t.agent_type = 'research_agent'
        AND t.created_at >= datetime('now', '-30 days')
        GROUP BY t.task_id
    """)

    print("\n" + "="*80)
    print("RESEARCH AGENT COMPLIANCE ANALYSIS")
    print("="*80)
    print(f"Expected tools: {', '.join(sorted(expected_tools))}")
    print()

    compliant_count = 0
    total_count = 0

    for row in cursor.fetchall():
        total_count += 1
        tools = set(row['tools_used'].split(',')) if row['tools_used'] else set()

        # Check for forbidden tools (Write, Edit, Bash)
        forbidden_tools = {'Write', 'Edit', 'Bash'}
        violations = tools & forbidden_tools

        # Check if using allowed tools
        allowed_tools = tools & expected_tools

        if violations:
            print(f"❌ VIOLATION - Task {row['task_id'][:40]}...")
            print(f"   Used forbidden tools: {', '.join(violations)}")
        elif allowed_tools:
            compliant_count += 1
            print(f"✅ Compliant - {len(allowed_tools)} allowed tools used")
        else:
            print(f"⚠️  Unusual - Task {row['task_id'][:40]}...")
            print(f"   Used tools: {', '.join(tools)}")

    if total_count > 0:
        print(f"\nCompliance rate: {compliant_count}/{total_count} ({compliant_count/total_count*100:.1f}%)")
    else:
        print("\nNo research_agent tasks found in last 30 days")

    conn.close()

def analyze_failure_patterns():
    """Analyze which tools fail most often and why"""
    conn = connect()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            tool_name,
            COUNT(*) as failure_count,
            GROUP_CONCAT(DISTINCT SUBSTR(error, 1, 100)) as error_samples
        FROM tool_usage
        WHERE success = 0
        AND timestamp >= datetime('now', '-7 days')
        GROUP BY tool_name
        ORDER BY failure_count DESC
        LIMIT 10
    """)

    print("\n" + "="*80)
    print("TOP TOOL FAILURES (Last 7 Days)")
    print("="*80)

    for row in cursor.fetchall():
        print(f"\n{row['tool_name']}: {row['failure_count']} failures")
        if row['error_samples']:
            errors = row['error_samples'].split(',')[:3]  # Show max 3 samples
            for i, err in enumerate(errors, 1):
                print(f"  Sample {i}: {err[:80]}...")

    conn.close()

def analyze_task_efficiency():
    """Analyze task completion efficiency"""
    conn = connect()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            agent_type,
            status,
            COUNT(*) as count,
            AVG(CAST((julianday(updated_at) - julianday(created_at)) * 24 * 60 AS REAL)) as avg_minutes
        FROM tasks
        WHERE created_at >= datetime('now', '-7 days')
        GROUP BY agent_type, status
        ORDER BY agent_type, status
    """)

    print("\n" + "="*80)
    print("TASK COMPLETION EFFICIENCY (Last 7 Days)")
    print("="*80)
    print(f"{'Agent':<30} {'Status':<15} {'Count':<10} {'Avg Duration':<15}")
    print("-"*80)

    for row in cursor.fetchall():
        avg_min = row['avg_minutes'] if row['avg_minutes'] else 0
        print(f"{row['agent_type']:<30} {row['status']:<15} {row['count']:<10} {avg_min:>10.2f} min")

    conn.close()

def get_database_summary():
    """Get overall database stats"""
    conn = connect()
    cursor = conn.cursor()

    print("\n" + "="*80)
    print("DATABASE SUMMARY")
    print("="*80)

    cursor.execute("SELECT COUNT(*) FROM tasks")
    print(f"Total tasks: {cursor.fetchone()[0]}")

    cursor.execute("SELECT COUNT(*) FROM tool_usage")
    print(f"Total tool usage records: {cursor.fetchone()[0]}")

    cursor.execute("SELECT COUNT(*) FROM agent_status")
    print(f"Total status changes: {cursor.fetchone()[0]}")

    cursor.execute("SELECT MIN(created_at), MAX(created_at) FROM tasks")
    row = cursor.fetchone()
    if row[0] and row[1]:
        print(f"Task date range: {row[0]} to {row[1]}")

    conn.close()

def main():
    """Run all analyses"""
    global DB_PATH

    # Parse command-line arguments
    parser = argparse.ArgumentParser(description="Analyze tool usage patterns from AgentLab database")
    parser.add_argument(
        "--db-path",
        default=None,
        help="Path to database file (default: from config.py, supports AGENTLAB_DB_PATH env var)",
    )
    args = parser.parse_args()

    # Set DB_PATH using config helper (CLI arg > env var > default)
    DB_PATH = get_db_path_with_fallback(args.db_path)

    print("\n" + "="*80)
    print("AGENTLAB TOOL USAGE ANALYSIS")
    print("="*80)
    print(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Database: {DB_PATH}")

    get_database_summary()
    analyze_tool_frequency()
    analyze_agent_tool_patterns()
    analyze_workflow_patterns()
    analyze_task_efficiency()
    analyze_failure_patterns()
    analyze_research_agent_compliance()
    analyze_tool_usage_by_task()

    print("\n" + "="*80)
    print("ANALYSIS COMPLETE")
    print("="*80)

if __name__ == "__main__":
    main()
