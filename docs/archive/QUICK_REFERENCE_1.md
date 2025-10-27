# File Path Extraction & Log Formatting - Quick Reference

## 🎯 What Was Built

Enhanced file path tracking and terminal-style log formatting for the Telegram bot's Claude Code dashboard.

## 📦 New Components

| File | Purpose | Lines |
|------|---------|-------|
| `telegram_bot/log_formatter.py` | Terminal-style formatter module | 380 |
| `telegram_bot/test_log_formatter.py` | Comprehensive test suite | 330 |
| `telegram_bot/LOG_FORMATTER_USAGE.md` | Complete usage documentation | 450 |
| `.claude/hooks/post-tool-use` | Enhanced file path extraction | ~70 modified |
| `telegram_bot/monitoring_server.py` | New API endpoints | ~60 added |

## 🚀 Quick Start

### Test the Formatter

```bash
cd telegram_bot
python3 test_log_formatter.py
```

### Use in Python

```python
from log_formatter import format_for_dashboard
from hooks_reader import HooksReader

hooks_reader = HooksReader(sessions_dir="logs/sessions")
operations = hooks_reader.get_session_file_operations("session_id")
formatted = format_for_dashboard("session_id", operations)

print(f"Found {formatted['summary']['unique_files']} unique files")
for entry in formatted['log_entries']:
    print(entry['html'])  # Pre-formatted HTML
```

### Use via API

```bash
# Get formatted logs
curl http://localhost:3000/api/sessions/<session_id>/formatted-logs

# Get summary only
curl http://localhost:3000/api/sessions/<session_id>/formatted-logs | jq '.summary'

# List unique files
curl http://localhost:3000/api/sessions/<session_id>/formatted-logs | jq '.summary.unique_files_list[]'
```

### Use in JavaScript

```javascript
fetch('/api/sessions/abc123/formatted-logs')
  .then(r => r.json())
  .then(data => {
    // Insert pre-formatted HTML
    data.log_entries.forEach(entry => {
      document.getElementById('terminal').innerHTML += entry.html;
    });
  });
```

## 🎨 Tool Colors

| Tool | Color | Hex |
|------|-------|-----|
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

## 📍 New API Endpoints

### GET `/api/sessions/<session_id>/formatted-logs`

Returns formatted terminal logs with file paths highlighted.

**Response Keys**:
- `session_id` - Session identifier
- `summary` - Aggregated statistics (operations, files, tool counts)
- `log_entries` - Array of formatted log lines with HTML
- `total_lines` - Total number of log entries

### GET `/api/tasks/<task_id>/formatted-logs`

Same as above, using task ID instead of session ID.

## 🔧 Key Functions

### `TerminalLogFormatter`

```python
formatter = TerminalLogFormatter()

# Format a file path
formatted_path = formatter.format_file_path("/path/to/file.py")
# Returns: {"filename": "file.py", "directory": "/path/to", "display": "<html>", "full_path": "..."}

# Format tool parameters
params_html = formatter.format_tool_params("Read", {"file_path": "/path/to/file.py"})

# Format complete log entry
entry = formatter.format_log_entry({
    "tool": "Read",
    "timestamp": "2025-10-20T14:35:22Z",
    "file_paths": ["/path/to/file.py"],
    "status": "completed"
})

# Get tool color
color = formatter.get_tool_color("Read")  # Returns: "#3fb950"
```

### `format_for_dashboard()`

```python
from log_formatter import format_for_dashboard

# One-line formatting for complete session
formatted = format_for_dashboard(session_id, file_operations)

# Access formatted data
summary = formatted['summary']
log_entries = formatted['log_entries']
```

## 📊 Response Structure

```json
{
  "session_id": "abc123",
  "summary": {
    "total_operations": 15,
    "unique_files": 8,
    "unique_files_list": ["file1.py", "file2.py"],
    "tool_badges": [
      {"tool": "Read", "count": 5, "color": "#3fb950", "file_count": 5}
    ],
    "files_by_tool": {"Read": 5, "Edit": 2},
    "total_tools": 15
  },
  "log_entries": [
    {
      "tool_name": "Read",
      "tool_color": "#3fb950",
      "timestamp": "14:35:22",
      "file_paths_html": "<formatted html>",
      "file_count": 1,
      "status_display": "OK",
      "html": "<div class='terminal-line'>...</div>"
    }
  ],
  "total_lines": 15
}
```

## 🧪 Testing

```bash
# Run all tests
python3 test_log_formatter.py

# Test with real session
python3 test_log_formatter.py <session_id>

# Tests verify:
# ✅ File path formatting
# ✅ Tool parameter formatting
# ✅ Log entry formatting
# ✅ Session summaries
# ✅ Color mapping
# ✅ Complete dashboard format
```

## 📝 Log Entry Fields

Each formatted log entry contains:

| Field | Type | Description |
|-------|------|-------------|
| `tool_name` | string | Tool name (e.g., "Read") |
| `tool_color` | string | Hex color for tool |
| `timestamp` | string | Time in HH:MM:SS format |
| `timestamp_iso` | string | Full ISO timestamp |
| `file_paths_html` | string | Formatted file paths (HTML) |
| `file_paths_raw` | array | Raw file path strings |
| `file_count` | number | Number of files |
| `parameters_html` | string | Formatted parameters (HTML) |
| `status` | string | Status code |
| `status_display` | string | Display text (OK/ERROR/BLOCKED) |
| `status_color` | string | Status color |
| `has_error` | boolean | Whether operation failed |
| `has_files` | boolean | Whether operation touched files |
| `line_number` | number | Line number in terminal |
| `html` | string | Complete terminal line HTML |

## 🎯 Use Cases

### 1. Dashboard Integration
```javascript
// Fetch and display formatted logs
fetch('/api/sessions/' + sessionId + '/formatted-logs')
  .then(r => r.json())
  .then(data => renderTerminal(data.log_entries));
```

### 2. File Access Analysis
```python
# Find all files accessed in a session
formatted = format_for_dashboard(session_id, operations)
unique_files = formatted['summary']['unique_files_list']
print(f"Accessed {len(unique_files)} files")
```

### 3. Tool Usage Statistics
```bash
# Get tool usage breakdown
curl http://localhost:3000/api/sessions/abc123/formatted-logs \
  | jq '.summary.tool_badges[] | "\(.tool): \(.count) calls"'
```

### 4. Error Tracking
```python
# Find failed operations
errors = [e for e in formatted['log_entries'] if e['has_error']]
print(f"Found {len(errors)} errors")
```

## 🔍 Troubleshooting

### No file paths showing?
- Check hooks are running: `cat /tmp/hook_debug.log`
- Verify session exists: `ls logs/sessions/<session_id>/`
- Check log files: `cat logs/sessions/<session_id>/post_tool_use.jsonl`

### API returns empty?
- Verify session ID is correct
- Check monitoring server is running: `http://localhost:3000`
- Test hooks reader: `python3 -c "from hooks_reader import HooksReader; print(HooksReader().get_all_sessions())"`

### Colors not showing?
- Verify tool name spelling (case-sensitive)
- Check CSS classes are loaded in dashboard
- MCP tools must start with `mcp__`

## 📚 Documentation

- **Complete Usage Guide**: `telegram_bot/LOG_FORMATTER_USAGE.md`
- **Implementation Summary**: `IMPLEMENTATION_SUMMARY.md`
- **Terminal UI Details**: `TERMINAL_UI_IMPROVEMENTS.md`
- **File Path Logging Spec**: `telegram_bot/FILEPATH_LOGGING.md`

## ✅ What Works

- ✅ File path extraction from Read, Write, Edit, Glob, Grep, Bash, NotebookEdit
- ✅ Multiple response format handling (string, dict, list)
- ✅ Terminal-style formatting with color coding
- ✅ GitHub-inspired design system
- ✅ API endpoints for formatted logs
- ✅ Pre-formatted HTML ready for dashboard
- ✅ Session summary statistics
- ✅ Tool usage badges
- ✅ Comprehensive test suite
- ✅ Complete documentation

## 🎉 Ready to Use!

The formatter is production-ready and can be integrated into the dashboard immediately. All tests pass and documentation is complete.

---

**Quick Links**:
- Test: `python3 telegram_bot/test_log_formatter.py`
- API: `http://localhost:3000/api/sessions/<id>/formatted-logs`
- Docs: `telegram_bot/LOG_FORMATTER_USAGE.md`
