"""
Tests for tool call consolidation in monitoring server
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def test_consolidate_empty_list():
    """Test consolidation with empty list"""
    from monitoring.server import _consolidate_tool_calls

    result = _consolidate_tool_calls([])
    assert result == []


def test_consolidate_single_operation():
    """Test consolidation with single operation"""
    from monitoring.server import _consolidate_tool_calls

    calls = [{"tool": "Read", "timestamp": "2025-01-01T00:00:00", "duration": 100, "success": True, "has_error": False}]

    result = _consolidate_tool_calls(calls)
    assert len(result) == 1
    assert result[0] == calls[0]
    assert "count" not in result[0]  # Single operations don't get count


def test_consolidate_consecutive_identical():
    """Test consolidation of consecutive identical operations"""
    from monitoring.server import _consolidate_tool_calls

    calls = [
        {
            "tool": "mcp__playwright__browser_take_screenshot",
            "timestamp": "2025-01-01T00:00:00",
            "duration": 100,
            "success": True,
            "has_error": False,
        },
        {
            "tool": "mcp__playwright__browser_take_screenshot",
            "timestamp": "2025-01-01T00:00:01",
            "duration": 110,
            "success": True,
            "has_error": False,
        },
        {
            "tool": "mcp__playwright__browser_take_screenshot",
            "timestamp": "2025-01-01T00:00:02",
            "duration": 105,
            "success": True,
            "has_error": False,
        },
    ]

    result = _consolidate_tool_calls(calls)
    assert len(result) == 1
    assert result[0]["tool"] == "mcp__playwright__browser_take_screenshot"
    assert result[0]["count"] == 3
    assert result[0]["duration"] == 315  # Sum of durations
    assert result[0]["timestamp"] == "2025-01-01T00:00:00"
    assert result[0]["last_timestamp"] == "2025-01-01T00:00:02"


def test_consolidate_different_operations():
    """Test that different operations are not consolidated"""
    from monitoring.server import _consolidate_tool_calls

    calls = [
        {"tool": "Read", "timestamp": "2025-01-01T00:00:00", "duration": 100, "success": True, "has_error": False},
        {"tool": "Write", "timestamp": "2025-01-01T00:00:01", "duration": 150, "success": True, "has_error": False},
        {"tool": "Read", "timestamp": "2025-01-01T00:00:02", "duration": 95, "success": True, "has_error": False},
    ]

    result = _consolidate_tool_calls(calls)
    assert len(result) == 3  # All different, no consolidation
    assert "count" not in result[0]
    assert "count" not in result[1]
    assert "count" not in result[2]


def test_consolidate_mixed_consecutive():
    """Test consolidation with mixed consecutive operations"""
    from monitoring.server import _consolidate_tool_calls

    calls = [
        {"tool": "Read", "timestamp": "2025-01-01T00:00:00", "duration": 100, "success": True, "has_error": False},
        {"tool": "Read", "timestamp": "2025-01-01T00:00:01", "duration": 105, "success": True, "has_error": False},
        {"tool": "Write", "timestamp": "2025-01-01T00:00:02", "duration": 150, "success": True, "has_error": False},
        {"tool": "Read", "timestamp": "2025-01-01T00:00:03", "duration": 95, "success": True, "has_error": False},
        {"tool": "Read", "timestamp": "2025-01-01T00:00:04", "duration": 98, "success": True, "has_error": False},
        {"tool": "Read", "timestamp": "2025-01-01T00:00:05", "duration": 102, "success": True, "has_error": False},
    ]

    result = _consolidate_tool_calls(calls)
    assert len(result) == 3

    # First group: 2 Reads
    assert result[0]["tool"] == "Read"
    assert result[0]["count"] == 2
    assert result[0]["duration"] == 205

    # Second group: 1 Write (no consolidation)
    assert result[1]["tool"] == "Write"
    assert "count" not in result[1]

    # Third group: 3 Reads
    assert result[2]["tool"] == "Read"
    assert result[2]["count"] == 3
    assert result[2]["duration"] == 295


def test_consolidate_respects_error_status():
    """Test that operations with different error status are not consolidated"""
    from monitoring.server import _consolidate_tool_calls

    calls = [
        {"tool": "Read", "timestamp": "2025-01-01T00:00:00", "duration": 100, "success": True, "has_error": False},
        {"tool": "Read", "timestamp": "2025-01-01T00:00:01", "duration": 105, "success": False, "has_error": True},
        {"tool": "Read", "timestamp": "2025-01-01T00:00:02", "duration": 95, "success": True, "has_error": False},
    ]

    result = _consolidate_tool_calls(calls)
    assert len(result) == 3  # Different error status prevents consolidation


def test_consolidate_playwright_operations():
    """Test real-world Playwright operation consolidation"""
    from monitoring.server import _consolidate_tool_calls

    calls = [
        {
            "tool": "mcp__playwright__browser_type",
            "timestamp": "2025-01-01T00:00:00",
            "duration": 50,
            "success": True,
            "has_error": False,
        },
        {
            "tool": "mcp__playwright__browser_type",
            "timestamp": "2025-01-01T00:00:01",
            "duration": 48,
            "success": True,
            "has_error": False,
        },
        {
            "tool": "mcp__playwright__browser_type",
            "timestamp": "2025-01-01T00:00:02",
            "duration": 52,
            "success": True,
            "has_error": False,
        },
        {
            "tool": "mcp__playwright__browser_take_screenshot",
            "timestamp": "2025-01-01T00:00:03",
            "duration": 200,
            "success": True,
            "has_error": False,
        },
        {
            "tool": "mcp__playwright__browser_take_screenshot",
            "timestamp": "2025-01-01T00:00:04",
            "duration": 195,
            "success": True,
            "has_error": False,
        },
    ]

    result = _consolidate_tool_calls(calls)
    assert len(result) == 2

    # 3 browser_type operations consolidated
    assert result[0]["tool"] == "mcp__playwright__browser_type"
    assert result[0]["count"] == 3
    assert result[0]["duration"] == 150

    # 2 browser_take_screenshot operations consolidated
    assert result[1]["tool"] == "mcp__playwright__browser_take_screenshot"
    assert result[1]["count"] == 2
    assert result[1]["duration"] == 395
