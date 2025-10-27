"""
Terminal-style log formatter for dashboard display
Formats tool execution logs with file paths, timestamps, and color coding
"""

from datetime import datetime
from pathlib import Path
from typing import Any


class TerminalLogFormatter:
    """Formats log entries for terminal-style dashboard display"""

    # Tool color mapping (matches TERMINAL_UI_IMPROVEMENTS.md)
    TOOL_COLORS = {
        "Bash": "#58a6ff",  # Cyan
        "Read": "#3fb950",  # Green
        "Write": "#a371f7",  # Purple
        "Edit": "#d2a8ff",  # Light Purple
        "Grep": "#f0883e",  # Orange
        "Glob": "#ffa657",  # Light Orange
        "Task": "#79c0ff",  # Light Cyan
        "TodoWrite": "#56d364",  # Light Green
        "NotebookEdit": "#d2a8ff",  # Light Purple
        "WebFetch": "#79c0ff",  # Light Cyan
        "WebSearch": "#ffa657",  # Light Orange
        "Skill": "#56d364",  # Light Green
        "SlashCommand": "#58a6ff",  # Cyan
    }

    # MCP tools (prefixed with mcp__)
    MCP_COLOR = "#db6d28"  # Dark Orange

    # Error color
    ERROR_COLOR = "#f85149"  # Red

    # Text colors
    TEXT_MUTED = "#8b949e"
    TEXT_PRIMARY = "#c9d1d9"
    TEXT_ACCENT = "#58a6ff"

    # Background colors
    BG_TERTIARY = "#1a1a1a"
    BORDER_COLOR = "#2a2a2a"

    @classmethod
    def get_tool_color(cls, tool_name: str) -> str:
        """Get color for a specific tool"""
        if tool_name.startswith("mcp__"):
            return cls.MCP_COLOR
        return cls.TOOL_COLORS.get(tool_name, cls.TEXT_PRIMARY)

    @classmethod
    def format_timestamp(cls, timestamp_str: str) -> str:
        """Format ISO timestamp to readable format (24-hour)"""
        try:
            dt = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
            return dt.strftime("%H:%M:%S")
        except Exception:
            return timestamp_str[:8] if len(timestamp_str) >= 8 else timestamp_str

    @classmethod
    def format_file_path(cls, file_path: str) -> dict[str, str]:
        """
        Format file path for display with filename and directory separation

        Returns:
            dict with 'filename', 'directory', and 'display' keys
        """
        path = Path(file_path)

        # Handle glob patterns
        if file_path.startswith("glob:"):
            pattern = file_path[5:]
            return {
                "filename": pattern,
                "directory": "",
                "display": f"<span style='color: {cls.TEXT_ACCENT}'>glob:</span> {pattern}",
                "full_path": file_path,
            }

        # Regular file paths
        filename = path.name
        directory = str(path.parent) if path.parent != Path(".") else ""

        # Shorten long directory paths
        if len(directory) > 50:
            parts = directory.split("/")
            if len(parts) > 3:
                directory = f"{parts[0]}/.../{'/'.join(parts[-2:])}"

        display_parts = []
        if directory:
            display_parts.append(f"<span style='color: {cls.TEXT_MUTED}'>{directory}/</span>")
        display_parts.append(f"<span style='color: {cls.TEXT_ACCENT}'>{filename}</span>")

        return {
            "filename": filename,
            "directory": directory,
            "display": "".join(display_parts),
            "full_path": file_path,
        }

    @classmethod
    def format_file_paths(cls, file_paths: list[str]) -> str:
        """Format multiple file paths for display"""
        if not file_paths:
            return ""

        # Deduplicate while preserving order
        seen = set()
        unique_paths = []
        for path in file_paths:
            if path not in seen:
                seen.add(path)
                unique_paths.append(path)

        if len(unique_paths) == 1:
            formatted = cls.format_file_path(unique_paths[0])
            return formatted["display"]
        elif len(unique_paths) <= 3:
            # Show all paths inline
            formatted_paths = [cls.format_file_path(p)["display"] for p in unique_paths]
            return "<br>".join(formatted_paths)
        else:
            # Show first 2 and count remaining
            formatted_paths = [cls.format_file_path(p)["display"] for p in unique_paths[:2]]
            remaining = len(unique_paths) - 2
            formatted_paths.append(f"<span style='color: {cls.TEXT_MUTED}'>+ {remaining} more files</span>")
            return "<br>".join(formatted_paths)

    @classmethod
    def format_tool_params(cls, tool_name: str, parameters: dict[str, Any]) -> str:
        """Format tool parameters for display"""
        if not parameters:
            return ""

        # Extract key parameters based on tool type
        if tool_name == "Bash":
            command = parameters.get("command", "")
            # Smart truncation: preserve command name and beginning
            if len(command) > 80:
                # Try to preserve command name and key parts
                lines = command.split("\n")
                if len(lines) > 1:
                    # Multi-line command (e.g., heredoc)
                    first_line = lines[0][:60] + "..." if len(lines[0]) > 60 else lines[0]
                    command = f"{first_line} ({len(lines)} lines)"
                else:
                    # Single line - truncate but show beginning
                    command = command[:77] + "..."

            # Return styled command without "Bash(command: ...)" wrapper
            return f"<code style='color: {cls.TEXT_ACCENT}; font-family: ui-monospace, Monaco, monospace; background: {cls.BG_TERTIARY}; padding: 0.125rem 0.375rem; border: 1px solid {cls.BORDER_COLOR};'>{command}</code>"

        elif tool_name in ["Read", "Write", "Edit"]:
            file_path = parameters.get("file_path", "")
            if file_path:
                formatted = cls.format_file_path(file_path)
                return formatted["display"]

        elif tool_name == "Grep":
            pattern = parameters.get("pattern", "")
            path = parameters.get("path", ".")
            glob_param = parameters.get("glob", "")
            parts = []
            if pattern:
                parts.append(f"pattern: <code>{pattern}</code>")
            if glob_param:
                parts.append(f"glob: <code>{glob_param}</code>")
            if path and path != ".":
                parts.append(f"in: {path}")
            return " ".join(parts)

        elif tool_name == "Glob":
            pattern = parameters.get("pattern", "")
            path = parameters.get("path", ".")
            if pattern:
                display = f"pattern: <code>{pattern}</code>"
                if path and path != ".":
                    display += f" in: {path}"
                return display

        elif tool_name == "Task":
            description = parameters.get("description", "")
            subagent = parameters.get("subagent_type", "")
            prompt = parameters.get("prompt", "")

            # Build display parts
            parts = []
            if description:
                parts.append(description)
            if subagent:
                parts.append(f"({subagent})")

            # Add prompt preview with smart truncation (like Bash command)
            if prompt:
                # Smart truncation: preserve beginning and handle multi-line
                if len(prompt) > 80:
                    lines = prompt.split("\n")
                    if len(lines) > 1:
                        # Multi-line prompt
                        first_line = lines[0][:60] + "..." if len(lines[0]) > 60 else lines[0]
                        prompt_preview = f"{first_line} ({len(lines)} lines)"
                    else:
                        # Single line - truncate but show beginning
                        prompt_preview = prompt[:77] + "..."
                else:
                    prompt_preview = prompt

                # Format with same styling as Bash command
                prompt_styled = f"<code style='color: {cls.TEXT_ACCENT}; font-family: ui-monospace, Monaco, monospace; background: {cls.BG_TERTIARY}; padding: 0.125rem 0.375rem; border: 1px solid {cls.BORDER_COLOR};'>{prompt_preview}</code>"
                parts.append(f"- {prompt_styled}")

            return " ".join(parts) if parts else ""

        elif tool_name == "TodoWrite":
            todos = parameters.get("todos", [])
            if todos:
                return f"{len(todos)} todo(s)"

        # Generic parameter display
        if len(parameters) <= 3:
            parts = [f"{k}: {v}" for k, v in parameters.items() if len(str(v)) < 50]
            return ", ".join(parts[:3])

        return f"{len(parameters)} parameters"

    @classmethod
    def format_log_entry(cls, log_entry: dict[str, Any]) -> dict[str, Any]:
        """
        Format a single log entry for terminal display

        Args:
            log_entry: Dict with 'timestamp', 'tool', 'file_paths', 'parameters', etc.

        Returns:
            Dict with formatted fields for HTML rendering
        """
        tool_name = log_entry.get("tool", "unknown")
        timestamp = log_entry.get("timestamp", "")
        file_paths = log_entry.get("file_paths", [])
        parameters = log_entry.get("parameters", {})
        status = log_entry.get("status", "completed")
        has_error = log_entry.get("has_error", False)

        # Determine display status
        if has_error:
            status_display = "ERROR"
            status_color = cls.ERROR_COLOR
        elif status == "blocked":
            status_display = "BLOCKED"
            status_color = "#ffa657"
        elif status == "starting":
            status_display = "RUNNING"
            status_color = "#58a6ff"
        else:
            status_display = "OK"
            status_color = cls.get_tool_color(tool_name)

        return {
            "tool_name": tool_name,
            "tool_color": cls.get_tool_color(tool_name),
            "timestamp": cls.format_timestamp(timestamp),
            "timestamp_iso": timestamp,
            "file_paths_html": cls.format_file_paths(file_paths),
            "file_paths_raw": file_paths,
            "file_count": len(file_paths),
            "parameters_html": cls.format_tool_params(tool_name, parameters),
            "status": status,
            "status_display": status_display,
            "status_color": status_color,
            "has_error": has_error,
            "has_files": len(file_paths) > 0,
        }

    @classmethod
    def format_session_summary(cls, session_data: dict[str, Any]) -> dict[str, Any]:
        """
        Format session summary with file operation statistics

        Args:
            session_data: Dict with 'session_id', 'file_operations', 'tools_by_type', etc.

        Returns:
            Dict with formatted summary statistics
        """
        file_operations = session_data.get("file_operations", [])
        tools_by_type = session_data.get("tools_by_type", {})

        # Count unique files accessed
        unique_files = set()
        for op in file_operations:
            for path in op.get("file_paths", []):
                if not path.startswith("glob:"):
                    unique_files.add(path)

        # Count files by tool type
        files_by_tool: dict[str, int] = {}
        for op in file_operations:
            tool = op.get("tool", "unknown")
            file_count = len([p for p in op.get("file_paths", []) if not p.startswith("glob:")])
            files_by_tool[tool] = files_by_tool.get(tool, 0) + file_count

        # Format tool badges with counts
        tool_badges = []
        for tool, count in sorted(tools_by_type.items(), key=lambda x: x[1], reverse=True):
            tool_badges.append(
                {
                    "tool": tool,
                    "count": count,
                    "color": cls.get_tool_color(tool),
                    "has_files": tool in files_by_tool,
                    "file_count": files_by_tool.get(tool, 0),
                }
            )

        return {
            "session_id": session_data.get("session_id", "unknown"),
            "total_operations": len(file_operations),
            "unique_files": len(unique_files),
            "unique_files_list": sorted(unique_files),
            "tool_badges": tool_badges,
            "files_by_tool": files_by_tool,
            "total_tools": sum(tools_by_type.values()),
        }

    @classmethod
    def render_terminal_line(cls, log_entry: dict[str, Any], line_number: int) -> str:
        """
        Render a single terminal line as HTML

        Args:
            log_entry: Formatted log entry from format_log_entry()
            line_number: Line number to display

        Returns:
            HTML string for terminal line
        """
        tool_name = log_entry["tool_name"]
        tool_color = log_entry["tool_color"]
        timestamp = log_entry["timestamp"]
        file_paths_html = log_entry["file_paths_html"]
        params_html = log_entry["parameters_html"]
        status_color = log_entry["status_color"]
        status_display = log_entry["status_display"]
        has_files = log_entry["has_files"]

        # Build line content
        parts = []

        # Tool name badge
        parts.append(
            f'<span class="terminal-tool-badge" style="background-color: {tool_color}20; '
            f'color: {tool_color}; border-left: 3px solid {tool_color};">'
            f"{tool_name}</span>"
        )

        # Parameters or file paths
        if has_files and file_paths_html:
            parts.append(f'<span class="terminal-files">{file_paths_html}</span>')
        elif params_html:
            parts.append(f'<span class="terminal-params">{params_html}</span>')

        # Status badge
        parts.append(f'<span class="terminal-status" style="color: {status_color};">' f"[{status_display}]</span>")

        content = " ".join(parts)

        # Wrap in terminal line
        return (
            f'<div class="terminal-line" data-line="{line_number}" data-tool="{tool_name}">'
            f'  <span class="terminal-line-number">{line_number:03d}</span>'
            f'  <span class="terminal-timestamp">{timestamp}</span>'
            f'  <div class="terminal-content">{content}</div>'
            f"</div>"
        )


def format_for_dashboard(session_id: str, file_operations: list[dict]) -> dict[str, Any]:
    """
    Convenience function to format complete session data for dashboard

    Args:
        session_id: Session identifier
        file_operations: List of file operations from HooksReader.get_session_file_operations()

    Returns:
        Dict with formatted session data and HTML-ready log entries
    """
    formatter = TerminalLogFormatter()

    # Format each log entry
    formatted_entries = []
    for i, operation in enumerate(file_operations, start=1):
        formatted = formatter.format_log_entry(operation)
        formatted["line_number"] = i
        formatted["html"] = formatter.render_terminal_line(formatted, i)
        formatted_entries.append(formatted)

    # Count tools by type
    tools_by_type: dict[str, int] = {}
    for op in file_operations:
        tool = op.get("tool", "unknown")
        tools_by_type[tool] = tools_by_type.get(tool, 0) + 1

    # Format summary
    summary = formatter.format_session_summary(
        {
            "session_id": session_id,
            "file_operations": file_operations,
            "tools_by_type": tools_by_type,
        }
    )

    return {
        "session_id": session_id,
        "summary": summary,
        "log_entries": formatted_entries,
        "total_lines": len(formatted_entries),
    }
