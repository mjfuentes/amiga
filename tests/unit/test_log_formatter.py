"""
Test script for log_formatter.py
Verifies file path extraction and terminal-style formatting
"""

import json
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.log_formatter import TerminalLogFormatter, format_for_dashboard


def test_file_path_formatting():
    """Test file path formatting with various path types"""
    print("=" * 60)
    print("TEST 1: File Path Formatting")
    print("=" * 60)

    formatter = TerminalLogFormatter()

    test_paths = [
        "/Users/matifuentes/Workspace/agentlab/telegram_bot/main.py",
        "relative/path/to/file.py",
        "glob:*.py",
        "glob:**/*.ts",
        "/very/long/path/that/should/be/shortened/to/make/it/readable/file.py",
    ]

    for path in test_paths:
        formatted = formatter.format_file_path(path)
        print(f"\nOriginal: {path}")
        print(f"Filename: {formatted['filename']}")
        print(f"Directory: {formatted['directory']}")
        display_formatted = formatted["display"].replace("<span", "\n  <span")
        print(f"Display HTML (stripped): {display_formatted}")


def test_tool_params_formatting():
    """Test tool parameter formatting"""
    print("\n" + "=" * 60)
    print("TEST 2: Tool Parameter Formatting")
    print("=" * 60)

    formatter = TerminalLogFormatter()

    test_cases = [
        {
            "tool": "Bash",
            "params": {"command": "ls -la /Users/matifuentes/Workspace"},
        },
        {
            "tool": "Read",
            "params": {"file_path": "/Users/matifuentes/Workspace/agentlab/telegram_bot/main.py"},
        },
        {
            "tool": "Grep",
            "params": {"pattern": "def.*format", "glob": "*.py", "path": "telegram_bot"},
        },
        {
            "tool": "Glob",
            "params": {"pattern": "**/*.py", "path": "."},
        },
        {
            "tool": "Task",
            "params": {"description": "Analyze codebase", "subagent_type": "Explore"},
        },
    ]

    for case in test_cases:
        formatted = formatter.format_tool_params(case["tool"], case["params"])
        print(f"\nTool: {case['tool']}")
        print(f"Parameters: {case['params']}")
        print(f"Formatted: {formatted}")


def test_log_entry_formatting():
    """Test complete log entry formatting"""
    print("\n" + "=" * 60)
    print("TEST 3: Log Entry Formatting")
    print("=" * 60)

    formatter = TerminalLogFormatter()

    test_entries = [
        {
            "timestamp": "2025-10-20T14:35:22.123456Z",
            "tool": "Read",
            "file_paths": ["/Users/matifuentes/Workspace/agentlab/telegram_bot/main.py"],
            "parameters": {"file_path": "/Users/matifuentes/Workspace/agentlab/telegram_bot/main.py"},
            "status": "completed",
            "has_error": False,
        },
        {
            "timestamp": "2025-10-20T14:35:23.456789Z",
            "tool": "Glob",
            "file_paths": ["telegram_bot/main.py", "telegram_bot/session.py", "telegram_bot/orchestrator.py"],
            "parameters": {"pattern": "**/*.py"},
            "status": "completed",
            "has_error": False,
        },
        {
            "timestamp": "2025-10-20T14:35:24.789012Z",
            "tool": "Bash",
            "file_paths": [],
            "parameters": {"command": "git status"},
            "status": "completed",
            "has_error": False,
        },
        {
            "timestamp": "2025-10-20T14:35:25.012345Z",
            "tool": "Edit",
            "file_paths": ["/Users/matifuentes/Workspace/agentlab/telegram_bot/hooks_reader.py"],
            "parameters": {
                "file_path": "/Users/matifuentes/Workspace/agentlab/telegram_bot/hooks_reader.py",
                "old_string": "old code",
                "new_string": "new code",
            },
            "status": "completed",
            "has_error": False,
        },
        {
            "timestamp": "2025-10-20T14:35:26.345678Z",
            "tool": "Write",
            "file_paths": ["/Users/matifuentes/Workspace/agentlab/telegram_bot/log_formatter.py"],
            "parameters": {"file_path": "/Users/matifuentes/Workspace/agentlab/telegram_bot/log_formatter.py"},
            "status": "completed",
            "has_error": True,
        },
    ]

    for i, entry in enumerate(test_entries, start=1):
        formatted = formatter.format_log_entry(entry)
        print(f"\n--- Log Entry {i} ---")
        print(f"Tool: {formatted['tool_name']} (color: {formatted['tool_color']})")
        print(f"Timestamp: {formatted['timestamp']} (ISO: {formatted['timestamp_iso']})")
        print(f"Status: {formatted['status_display']} (color: {formatted['status_color']})")
        print(f"File count: {formatted['file_count']}")
        print(f"Has files: {formatted['has_files']}")
        if formatted["has_files"]:
            print(f"Files HTML: {formatted['file_paths_html'][:100]}...")


def test_session_summary():
    """Test session summary formatting"""
    print("\n" + "=" * 60)
    print("TEST 4: Session Summary Formatting")
    print("=" * 60)

    formatter = TerminalLogFormatter()

    session_data = {
        "session_id": "test_session_123",
        "file_operations": [
            {
                "tool": "Read",
                "file_paths": ["/Users/matifuentes/Workspace/agentlab/telegram_bot/main.py"],
            },
            {
                "tool": "Read",
                "file_paths": ["/Users/matifuentes/Workspace/agentlab/telegram_bot/session.py"],
            },
            {
                "tool": "Glob",
                "file_paths": ["glob:**/*.py", "telegram_bot/main.py", "telegram_bot/session.py"],
            },
            {
                "tool": "Edit",
                "file_paths": ["/Users/matifuentes/Workspace/agentlab/telegram_bot/main.py"],
            },
            {
                "tool": "Bash",
                "file_paths": [],
            },
        ],
        "tools_by_type": {
            "Read": 2,
            "Glob": 1,
            "Edit": 1,
            "Bash": 1,
        },
    }

    summary = formatter.format_session_summary(session_data)

    print(f"\nSession ID: {summary['session_id']}")
    print(f"Total operations: {summary['total_operations']}")
    print(f"Unique files: {summary['unique_files']}")
    print(f"Unique files list: {summary['unique_files_list']}")
    print(f"Total tools: {summary['total_tools']}")
    print("\nFiles by tool:")
    for tool, count in summary["files_by_tool"].items():
        print(f"  {tool}: {count} files")
    print("\nTool badges:")
    for badge in summary["tool_badges"]:
        print(f"  {badge['tool']}: {badge['count']} calls, {badge['file_count']} files, color: {badge['color']}")


def test_complete_dashboard_format():
    """Test complete dashboard formatting"""
    print("\n" + "=" * 60)
    print("TEST 5: Complete Dashboard Formatting")
    print("=" * 60)

    file_operations = [
        {
            "timestamp": "2025-10-20T14:35:22.123456Z",
            "tool": "Read",
            "file_paths": ["/Users/matifuentes/Workspace/agentlab/telegram_bot/main.py"],
            "parameters": {"file_path": "/Users/matifuentes/Workspace/agentlab/telegram_bot/main.py"},
            "status": "completed",
            "has_error": False,
        },
        {
            "timestamp": "2025-10-20T14:35:23.456789Z",
            "tool": "Glob",
            "file_paths": ["glob:**/*.py"],
            "parameters": {"pattern": "**/*.py"},
            "status": "completed",
            "has_error": False,
        },
    ]

    formatted = format_for_dashboard("test_session_456", file_operations)

    print(f"\nSession ID: {formatted['session_id']}")
    print(f"Total lines: {formatted['total_lines']}")
    print("\nSummary:")
    print(f"  Total operations: {formatted['summary']['total_operations']}")
    print(f"  Unique files: {formatted['summary']['unique_files']}")
    print(f"  Tool badges: {len(formatted['summary']['tool_badges'])}")

    print("\nLog entries:")
    for entry in formatted["log_entries"]:
        print(f"  Line {entry['line_number']}: {entry['tool_name']} - {entry['status_display']}")
        # Print first 100 chars of HTML
        print(f"    HTML preview: {entry['html'][:100]}...")


def test_color_mapping():
    """Test tool color mapping"""
    print("\n" + "=" * 60)
    print("TEST 6: Tool Color Mapping")
    print("=" * 60)

    formatter = TerminalLogFormatter()

    tools = [
        "Bash",
        "Read",
        "Write",
        "Edit",
        "Grep",
        "Glob",
        "Task",
        "TodoWrite",
        "mcp__chrome_devtools__navigate",
        "mcp__github__create_issue",
        "UnknownTool",
    ]

    print("\nTool color assignments:")
    for tool in tools:
        color = formatter.get_tool_color(tool)
        print(f"  {tool:40s} -> {color}")


def test_with_real_session(session_id: str = None):
    """Test with real session data if available"""
    print("\n" + "=" * 60)
    print("TEST 7: Real Session Data (if available)")
    print("=" * 60)

    if not session_id:
        print("\nNo session ID provided. Skipping real session test.")
        print("To test with real data, run:")
        print("  python test_log_formatter.py <session_id>")
        return

    # Try to load real session data
    from hooks_reader import HooksReader

    hooks_reader = HooksReader(
        sessions_dir="../logs/sessions", additional_dirs=["/Users/matifuentes/Workspace/logs/sessions"]
    )

    print(f"\nTesting with session: {session_id}")

    file_operations = hooks_reader.get_session_file_operations(session_id)

    if not file_operations:
        print(f"No file operations found for session {session_id}")
        return

    print(f"\nFound {len(file_operations)} file operations")

    formatted = format_for_dashboard(session_id, file_operations)

    print("\nFormatted summary:")
    print(f"  Total operations: {formatted['summary']['total_operations']}")
    print(f"  Unique files: {formatted['summary']['unique_files']}")
    print(f"  Total tools: {formatted['summary']['total_tools']}")

    print("\nFirst 5 log entries:")
    for entry in formatted["log_entries"][:5]:
        print(f"  [{entry['timestamp']}] {entry['tool_name']}: {entry['status_display']}")
        if entry["has_files"]:
            print(f"    Files: {entry['file_count']}")

    # Save to file for inspection
    output_file = Path("test_formatted_output.json")
    with open(output_file, "w") as f:
        json.dump(formatted, f, indent=2)
    print(f"\nFull formatted data saved to: {output_file}")


if __name__ == "__main__":
    import sys

    print("\n" + "=" * 60)
    print("LOG FORMATTER TEST SUITE")
    print("=" * 60)

    # Run all basic tests
    test_file_path_formatting()
    test_tool_params_formatting()
    test_log_entry_formatting()
    test_session_summary()
    test_complete_dashboard_format()
    test_color_mapping()

    # Run real session test if session_id provided
    session_id = sys.argv[1] if len(sys.argv) > 1 else None
    test_with_real_session(session_id)

    print("\n" + "=" * 60)
    print("ALL TESTS COMPLETED")
    print("=" * 60)
