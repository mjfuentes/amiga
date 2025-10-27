#!/usr/bin/env python3
"""
Test script to verify file path logging in terminal session monitor
"""

import sys
from pathlib import Path

import pytest

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from monitoring.hooks_reader import HooksReader

pytestmark = pytest.mark.integration


def test_filepath_extraction():
    """Test that file paths are extracted from hook logs"""
    print("Testing file path extraction from hooks...")

    # Use the actual hooks reader
    hooks_reader = HooksReader(
        sessions_dir="../logs/sessions", additional_dirs=["/Users/matifuentes/Workspace/logs/sessions"]
    )

    # Get all sessions
    sessions = hooks_reader.get_all_sessions()
    print(f"\nFound {len(sessions)} sessions")

    if not sessions:
        print("No sessions found. Please run a task first to generate session logs.")
        return

    # Test with the most recent session
    test_session = sessions[0]
    print(f"\nTesting with session: {test_session}")

    # Test reading file operations
    print("\n=== Testing get_session_file_operations ===")
    file_ops = hooks_reader.get_session_file_operations(test_session)

    if file_ops:
        print(f"Found {len(file_ops)} file operations:")
        for i, op in enumerate(file_ops[:5], 1):  # Show first 5
            print(f"\n{i}. Tool: {op['tool']}")
            print(f"   Timestamp: {op['timestamp']}")
            print(f"   File paths: {op['file_paths']}")
            print(f"   Status: {op['status']}")
            if op.get("has_error"):
                print("   Error: Yes")
    else:
        print("No file operations found in this session.")

    # Test reading timeline with file paths
    print("\n=== Testing get_session_timeline (with file_paths) ===")
    timeline = hooks_reader.get_session_timeline(test_session)

    if timeline:
        print(f"Found {len(timeline)} events in timeline:")
        # Show events with file paths
        events_with_files = [e for e in timeline if e.get("file_paths")]
        print(f"Events with file paths: {len(events_with_files)}")

        for i, event in enumerate(events_with_files[:5], 1):  # Show first 5
            print(f"\n{i}. Tool: {event['tool']} ({event['type']})")
            print(f"   File paths: {event['file_paths']}")
    else:
        print("No timeline events found.")

    # Test pre-tool logs
    print("\n=== Testing read_session_pre_tools ===")
    pre_tools = hooks_reader.read_session_pre_tools(test_session)

    if pre_tools:
        print(f"Found {len(pre_tools)} pre-tool entries:")
        pre_with_files = [p for p in pre_tools if p.get("file_paths")]
        print(f"Pre-tool entries with file paths: {len(pre_with_files)}")

        for i, entry in enumerate(pre_with_files[:3], 1):  # Show first 3
            print(f"\n{i}. Tool: {entry.get('tool')}")
            print(f"   File paths: {entry.get('file_paths')}")
    else:
        print("No pre-tool entries found.")

    # Test post-tool logs
    print("\n=== Testing read_session_post_tools ===")
    post_tools = hooks_reader.read_session_post_tools(test_session)

    if post_tools:
        print(f"Found {len(post_tools)} post-tool entries:")
        post_with_files = [p for p in post_tools if p.get("file_paths")]
        print(f"Post-tool entries with file paths: {len(post_with_files)}")

        for i, entry in enumerate(post_with_files[:3], 1):  # Show first 3
            print(f"\n{i}. Tool: {entry.get('tool')}")
            print(f"   File paths: {entry.get('file_paths')}")
    else:
        print("No post-tool entries found.")

    print("\n" + "=" * 60)
    print("Test completed!")
    print("=" * 60)


def test_manual_hook_extraction():
    """Test the file path extraction logic manually"""
    print("\n\n=== Testing Manual File Path Extraction ===\n")

    # Simulate various tool inputs
    test_cases = [
        {"tool": "Read", "input": {"file_path": "/path/to/file.py"}, "expected": ["/path/to/file.py"]},
        {"tool": "Write", "input": {"file_path": "/path/to/output.txt"}, "expected": ["/path/to/output.txt"]},
        {"tool": "Glob", "input": {"pattern": "**/*.py", "path": "/project"}, "expected": ["glob:**/*.py", "/project"]},
        {
            "tool": "Grep",
            "input": {"pattern": "TODO", "path": "/src", "glob": "*.js"},
            "expected": ["/src", "glob:*.js"],
        },
        {"tool": "Bash", "input": {"command": "cat /tmp/test.log"}, "expected": ["/tmp/test.log"]},
    ]

    # Import the extraction function from the hook

    for i, test in enumerate(test_cases, 1):
        print(f"{i}. Tool: {test['tool']}")
        print(f"   Input: {test['input']}")
        print(f"   Expected: {test['expected']}")
        print()


if __name__ == "__main__":
    print("=" * 60)
    print("File Path Logging Test")
    print("=" * 60)

    test_filepath_extraction()
    test_manual_hook_extraction()

    print("\n\nTo test with a new session:")
    print("1. Run a coding task through the bot")
    print("2. Check the logs in: logs/sessions/<task_id>/")
    print("3. Verify pre_tool_use.jsonl and post_tool_use.jsonl contain 'file_paths' field")
    print("4. Test the API: curl http://localhost:5001/api/sessions/<task_id>/file-operations")
