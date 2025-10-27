# Log Formatter - Terminal-Style Dashboard Display

## Overview

The log formatter module provides terminal-style formatting for Claude Code tool execution logs with enhanced file path extraction and display. This enables a professional, GitHub-inspired dashboard view with color-coded tool operations and prominent file path highlighting.

## Features

### 1. Enhanced File Path Extraction

**Post-tool-use Hook Improvements** (`/Users/matifuentes/Workspace/agentlab/.claude/hooks/post-tool-use`):

- **Multiple response format support**: Handles string, dict, and list responses from tools
- **Enhanced Glob support**: Checks multiple response keys (`files`, `paths`, `matches`, `results`)
- **Improved Grep support**: Extracts file paths from both `matches` and `files` keys
- **Read tool support**: Captures file paths from response confirmations
- **Smart path extraction**: Uses regex to extract paths from string responses
- **False positive filtering**: Removes temp/system paths (`/tmp/`, `/dev/`, `/proc/`)

### 2. Terminal-Style Log Formatting

**TerminalLogFormatter Class** (`log_formatter.py`):

Provides methods to format tool execution logs for dashboard display:

#### Key Methods

- **`format_file_path(path)`**: Formats individual file paths with directory/filename separation
  - Shortens long directories (>50 chars)
  - Handles glob patterns with special prefix display
  - Returns dict with `filename`, `directory`, `display` HTML, and `full_path`

- **`format_file_paths(paths)`**: Formats multiple file paths
  - Shows all paths inline (up to 3 files)
  - Truncates with "X more files" for large lists
  - Deduplicates while preserving order

- **`format_tool_params(tool, params)`**: Smart parameter formatting by tool type
  - **Bash**: Shows command (truncated to 100 chars)
  - **Read/Write/Edit**: Displays formatted file path
  - **Grep/Glob**: Shows pattern and search location
  - **Task**: Shows description and subagent type
  - **TodoWrite**: Shows todo count

- **`format_log_entry(entry)`**: Formats complete log entry
  - Color-codes by tool type
  - Formats timestamps (24-hour format)
  - Generates status badges (OK, ERROR, BLOCKED, RUNNING)
  - Combines file paths and parameters into HTML

- **`format_session_summary(session_data)`**: Aggregates session statistics
  - Counts unique files accessed
  - Groups files by tool type
  - Creates tool badges with counts
  - Returns formatted summary dict

- **`render_terminal_line(entry, line_num)`**: Renders HTML for single terminal line
  - Line numbers (3-digit format)
  - Timestamps
  - Tool badges with color borders
  - File paths or parameters
  - Status indicators

#### Convenience Function

**`format_for_dashboard(session_id, file_operations)`**: Complete session formatting
  - Formats all log entries
  - Generates session summary
  - Renders HTML for each line
  - Returns dashboard-ready JSON structure

### 3. API Endpoints

**New Monitoring Server Endpoints** (`monitoring_server.py`):

#### `/api/sessions/<session_id>/formatted-logs`

Returns formatted terminal-style logs for a session.

**Request**:
```bash
GET /api/sessions/abc123-def456/formatted-logs
```

**Response**:
```json
{
  "session_id": "abc123-def456",
  "summary": {
    "total_operations": 15,
    "unique_files": 8,
    "unique_files_list": ["file1.py", "file2.py", ...],
    "tool_badges": [
      {
        "tool": "Read",
        "count": 5,
        "color": "#3fb950",
        "has_files": true,
        "file_count": 5
      },
      ...
    ],
    "files_by_tool": {
      "Read": 5,
      "Edit": 2,
      "Glob": 3
    },
    "total_tools": 15
  },
  "log_entries": [
    {
      "tool_name": "Read",
      "tool_color": "#3fb950",
      "timestamp": "14:35:22",
      "timestamp_iso": "2025-10-20T14:35:22.123456Z",
      "file_paths_html": "<span style='color: #8b949e'>telegram_bot/</span><span style='color: #58a6ff'>main.py</span>",
      "file_paths_raw": ["/path/to/file.py"],
      "file_count": 1,
      "parameters_html": "<formatted params>",
      "status": "completed",
      "status_display": "OK",
      "status_color": "#3fb950",
      "has_error": false,
      "has_files": true,
      "line_number": 1,
      "html": "<div class='terminal-line'>...</div>"
    },
    ...
  ],
  "total_lines": 15
}
```

#### `/api/tasks/<task_id>/formatted-logs`

Same as above but for task IDs (alias for sessions endpoint).

## Color Scheme

Following GitHub's Primer design system (from `TERMINAL_UI_IMPROVEMENTS.md`):

| Tool Type | Color | Hex Code |
|-----------|-------|----------|
| Bash | Cyan | `#58a6ff` |
| Read | Green | `#3fb950` |
| Write | Purple | `#a371f7` |
| Edit | Light Purple | `#d2a8ff` |
| Grep | Orange | `#f0883e` |
| Glob | Light Orange | `#ffa657` |
| Task | Light Cyan | `#79c0ff` |
| TodoWrite | Light Green | `#56d364` |
| MCP Tools | Dark Orange | `#db6d28` |
| Errors | Red | `#f85149` |

**Text Colors**:
- Primary: `#c9d1d9`
- Muted: `#8b949e`
- Accent: `#58a6ff`

**Background**:
- Dark: `#0d1117`
- Medium: `#161b22`

## Usage Examples

### Python Usage

```python
from log_formatter import TerminalLogFormatter, format_for_dashboard
from hooks_reader import HooksReader

# Initialize hooks reader
hooks_reader = HooksReader(sessions_dir="logs/sessions")

# Get file operations for a session
file_operations = hooks_reader.get_session_file_operations("session_id_123")

# Format for dashboard
formatted = format_for_dashboard("session_id_123", file_operations)

# Access formatted data
print(f"Total operations: {formatted['summary']['total_operations']}")
print(f"Unique files: {formatted['summary']['unique_files']}")

# Render each log entry
for entry in formatted['log_entries']:
    print(entry['html'])  # Ready-to-use HTML
```

### JavaScript/Frontend Usage

```javascript
// Fetch formatted logs from API
fetch('/api/sessions/abc123/formatted-logs')
  .then(response => response.json())
  .then(data => {
    // Display summary
    console.log(`Total operations: ${data.summary.total_operations}`);
    console.log(`Unique files: ${data.summary.unique_files}`);

    // Render tool badges
    data.summary.tool_badges.forEach(badge => {
      console.log(`${badge.tool}: ${badge.count} calls, ${badge.file_count} files`);
    });

    // Render log entries in terminal
    const terminalDiv = document.getElementById('terminal');
    data.log_entries.forEach(entry => {
      // HTML is pre-formatted and ready to insert
      terminalDiv.innerHTML += entry.html;
    });
  });
```

### cURL Examples

```bash
# Get formatted logs for a session
curl http://localhost:3000/api/sessions/abc123-def456/formatted-logs

# Get formatted logs for a task
curl http://localhost:3000/api/tasks/task_789/formatted-logs

# Filter and process with jq
curl -s http://localhost:3000/api/sessions/abc123/formatted-logs \
  | jq '.summary.unique_files_list[]'
```

## Testing

Run the test suite:

```bash
cd telegram_bot
python3 test_log_formatter.py
```

Run with a real session ID:

```bash
python3 test_log_formatter.py <session_id>
```

The test suite verifies:
- ✅ File path formatting (absolute, relative, glob patterns)
- ✅ Tool parameter formatting for all tool types
- ✅ Log entry formatting with status indicators
- ✅ Session summary aggregation
- ✅ Complete dashboard formatting
- ✅ Tool color mapping including MCP tools

## Integration with Dashboard

The formatter is designed to work with the existing dashboard (`templates/dashboard.html`):

1. **Existing Terminal Display**: Already has CSS classes and styling
2. **Color Scheme**: Matches the GitHub-inspired theme
3. **Interactive Features**: Compatible with filter, copy, and expand functions
4. **Auto-scroll**: Works with existing scroll behavior

### Required CSS Classes

The dashboard should include these classes (already present in current implementation):

```css
.terminal-line          /* Individual log line */
.terminal-line-number   /* Line number column */
.terminal-timestamp     /* Timestamp column */
.terminal-tool-badge    /* Tool name badge */
.terminal-files         /* File paths display */
.terminal-params        /* Parameter display */
.terminal-status        /* Status indicator */
.terminal-content       /* Main content area */
```

## File Structure

```
telegram_bot/
├── log_formatter.py              # Main formatter module (NEW)
├── test_log_formatter.py         # Test suite (NEW)
├── LOG_FORMATTER_USAGE.md        # This documentation (NEW)
├── monitoring_server.py          # Updated with new endpoints
├── hooks_reader.py               # Existing - reads session logs
├── templates/
│   └── dashboard.html            # Existing - terminal UI
└── .claude/hooks/
    ├── pre-tool-use              # Existing - extracts file paths from params
    └── post-tool-use             # UPDATED - enhanced file path extraction
```

## Benefits

1. **Better File Tracking**: Enhanced extraction captures more file operations
2. **Visual Clarity**: Color-coded tools and prominent file path display
3. **Professional Appearance**: GitHub-inspired terminal styling
4. **Easy Integration**: Pre-formatted HTML ready for dashboard
5. **Flexible Usage**: Works via API or direct Python import
6. **Comprehensive**: Handles all Claude Code tools including MCP
7. **Robust**: Handles various response formats and edge cases

## Troubleshooting

### No file paths extracted

**Issue**: File operations don't show file paths

**Solution**: Check that:
1. Hooks are executing (check `/tmp/hook_debug.log`)
2. Session logs exist in `logs/sessions/<session_id>/`
3. Both `pre_tool_use.jsonl` and `post_tool_use.jsonl` are present
4. Post-tool-use hook was updated with enhanced extraction

### Colors not displaying

**Issue**: Tool names show without colors

**Solution**:
1. Verify CSS is loaded in dashboard
2. Check tool name matches color mapping (case-sensitive)
3. For MCP tools, ensure name starts with `mcp__`

### API returns empty data

**Issue**: `/api/sessions/<id>/formatted-logs` returns no data

**Solution**:
1. Verify session ID exists: `ls logs/sessions/`
2. Check `hooks_reader` can find session: Test with `get_all_sessions()`
3. Ensure log files contain valid JSON lines
4. Check server logs for errors

### Python import errors

**Issue**: `TypeError: unsupported operand type(s) for |`

**Solution**: You're using Python < 3.10. Update type hints in `hooks_reader.py`:
```python
# Change this:
additional_dirs: list[str] | None = None

# To this:
from typing import Optional, List
additional_dirs: Optional[List[str]] = None
```

## Future Enhancements

- **Syntax highlighting**: Code highlighting for Bash/Python outputs
- **Diff view**: Compare file operations between sessions
- **Performance metrics**: Show execution time per tool
- **Export functionality**: Download logs as JSON/CSV/Markdown
- **Search capability**: Full-text search across file paths and outputs
- **Real-time updates**: WebSocket streaming for live sessions

## Related Documentation

- `TERMINAL_UI_IMPROVEMENTS.md` - Dashboard UI enhancements
- `FILEPATH_LOGGING.md` - Original file path logging spec
- `telegram_bot/hooks_reader.py` - Session log reading logic
- `.claude/hooks/` - Hook scripts for tool tracking

---

**Last Updated**: 2025-10-20
**Author**: Claude (Anthropic)
**Project**: AgentLab Telegram Bot
