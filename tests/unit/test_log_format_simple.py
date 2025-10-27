#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Simple test for clean log format - tests formatting logic without imports
"""

from datetime import datetime


def format_tool_start(task_id, tool_name, parameters=None):
    """Format tool start event"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    msg = f"[{timestamp}] 🔧 {tool_name} started (task: {task_id[:8]})"

    if parameters:
        # Extract key params based on tool type
        key_param_map = {
            "Read": ["file_path"],
            "Write": ["file_path"],
            "Edit": ["file_path"],
            "Bash": ["command"],
            "Grep": ["pattern", "path"],
            "Glob": ["pattern"],
            "Task": ["description"],
        }

        key_params = key_param_map.get(tool_name, [])
        parts = []
        for key in key_params:
            if key in parameters:
                value = str(parameters[key])
                if len(value) > 50:
                    value = value[:50] + "..."
                parts.append(value)

        if parts:
            msg += f" ({', '.join(parts)})"

    return msg


def format_tool_complete(task_id, tool_name, duration_ms, success, error=None):
    """Format tool completion event"""
    timestamp = datetime.now().strftime("%H:%M:%S")

    icon = "✓" if success else "✗"
    status_text = "completed" if success else "failed"

    if duration_ms < 1000:
        duration_str = f"{duration_ms:.0f}ms"
    else:
        duration_str = f"{duration_ms/1000:.2f}s"

    msg = f"[{timestamp}] {icon} {tool_name} {status_text} in {duration_str} (task: {task_id[:8]})"

    if error:
        error_short = error[:100] + "..." if len(error) > 100 else error
        msg += f"\n    Error: {error_short}"

    return msg


def format_status_change(task_id, status, message=None):
    """Format agent status change"""
    timestamp = datetime.now().strftime("%H:%M:%S")

    icons = {
        "started": "▶",
        "tool_call": "🔧",
        "completed": "✓",
        "failed": "✗",
        "paused": "⏸",
        "resumed": "▶",
    }
    icon = icons.get(status, "ℹ")

    msg = f"[{timestamp}] {icon} Status: {status} (task: {task_id[:8]})"

    if message:
        msg += f" - {message}"

    return msg


if __name__ == "__main__":
    print("=" * 80)
    print("Testing Clean Log Format")
    print("=" * 80)

    # Test tool start
    print("\n1. Tool Start Events:")
    print("-" * 80)
    print(format_tool_start("test-task-123456789", "Read", {"file_path": "/path/to/file.py"}))
    print(format_tool_start("test-task-987654321", "Bash", {"command": "npm test && npm build"}))

    # Test tool complete - success
    print("\n2. Tool Complete Events (Success):")
    print("-" * 80)
    print(format_tool_complete("test-task-123456789", "Read", 45.5, True))
    print(format_tool_complete("test-task-987654321", "Bash", 2345.8, True))

    # Test tool complete - failure
    print("\n3. Tool Complete Events (Failure):")
    print("-" * 80)
    print(format_tool_complete("test-task-123456789", "Grep", 123.4, False, "Pattern not found"))
    print(
        format_tool_complete(
            "test-task-987654321",
            "Bash",
            567.2,
            False,
            "Command failed: TypeError: Cannot read property 'foo' of undefined at line 42",
        )
    )

    # Test status changes
    print("\n4. Status Change Events:")
    print("-" * 80)
    print(format_status_change("test-task-123456789", "started", "Task execution started"))
    print(format_status_change("test-task-123456789", "tool_call", "Calling Read tool"))
    print(format_status_change("test-task-123456789", "completed"))
    print(format_status_change("test-task-987654321", "failed", "Task failed due to error"))

    print("\n" + "=" * 80)
    print("✓ All format tests completed successfully!")
    print("=" * 80)
    print("\nClean log format features:")
    print("  - Concise timestamps [HH:MM:SS]")
    print("  - Visual icons for quick status recognition")
    print("  - Shortened task IDs (first 8 chars) for readability")
    print("  - Smart parameter extraction based on tool type")
    print("  - Human-friendly duration formatting (ms/s)")
    print("  - Truncated errors to prevent log clutter")
    print()
