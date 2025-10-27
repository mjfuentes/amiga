# CLI Session Tracking Validation Report

**Date**: 2025-10-21
**Session ID**: dccca803-5244-4324-bed2-8cd75854d0ae
**Validator**: frontend_agent

## Executive Summary

**ISSUE FOUND**: CLI sessions are being tracked in the database but NOT displayed in the monitoring dashboard.

**Root Cause**: Frontend fetches sessions from `/api/metrics/claude-sessions` (log files only), but ignores the `activity` data from SSE stream (which includes database-tracked CLI sessions).

## Validation Results

### 1. Database Tracking ✅ WORKING

**Current Session Tool Usage**:
```sql
SELECT task_id, timestamp, tool_name
FROM tool_usage
WHERE task_id = 'dccca803-5244-4324-bed2-8cd75854d0ae'
ORDER BY timestamp DESC LIMIT 5;
```

**Results**:
- Session ID: `dccca803-5244-4324-bed2-8cd75854d0ae`
- Tool calls: 38+ recorded
- Last activity: 2025-10-21T21:15:10.991101
- Tools used: Read, Grep, Bash, mcp__playwright__browser_*

**Verification Query**:
```sql
SELECT
    tool_usage.task_id,
    MAX(tool_usage.timestamp) as last_activity,
    COUNT(*) as tool_count
FROM tool_usage
LEFT JOIN tasks ON tool_usage.task_id = tasks.task_id
WHERE tool_usage.timestamp >= '2025-10-21T21:10:11'
  AND tasks.task_id IS NULL
GROUP BY tool_usage.task_id;
```

**Result**: 1 CLI session found (this session) with 38 tool calls

### 2. Backend SSE Stream ✅ WORKING

**File**: `monitoring_server.py:1933-1963`

**Logic**:
1. Queries `tool_usage` table for activity in last 5 minutes
2. Filters out entries that exist in `tasks` table (bot tasks)
3. Groups by `task_id` to get CLI sessions
4. Includes in `activity` array sent via SSE

**SSE Data Structure**:
```json
{
  "overview": { ... },
  "sessions": { ... },
  "activity": [
    {
      "task_id": "dccca803-5244-4324-bed2-8cd75854d0ae",
      "description": "CLI Session (active)",
      "status": "running",
      "timestamp": "2025-10-21T21:15:10.991101",
      "message": "38 tool calls in last 5min",
      "output_lines": null
    }
  ]
}
```

### 3. Frontend Display ❌ NOT WORKING

**File**: `static/js/dashboard.js:333-375`

**Current Logic**:
```javascript
async function fetchUnifiedData() {
    // 1. Fetch tasks from /api/tasks/running
    // 2. Fetch sessions from /api/metrics/claude-sessions
    // 3. IGNORES activity data from SSE stream
}
```

**Problem**:
- Frontend calls `/api/metrics/claude-sessions` which only reads log files via `hooks_reader`
- Current session has no log files (hooks write to both DB and logs, but logs may be delayed/missing)
- SSE stream sends `activity` array with DB-tracked CLI sessions, but frontend never uses it

**Evidence**:
- Network requests show repeated calls to `/api/metrics/claude-sessions`
- No code in `dashboard.js` accesses `data.activity` from SSE
- Badge shows `0` despite SSE containing activity data

## Screenshots

### Initial Load
![Dashboard Initial](./.playwright-mcp/dashboard-initial-load.jpeg)
- Tasks & Sessions badge: 0
- Status: "No active items"

### After SSE Connection
![Dashboard After SSE](./.playwright-mcp/dashboard-after-sse-load.jpeg)
- SSE connected (console: "SSE connection established")
- Footer stats updated (errors: 10, tasks: 206, sessions: 73)
- Tasks & Sessions still shows 0 (not using activity data)

### Final State
![Dashboard Final](./.playwright-mcp/dashboard-final-state.jpeg)
- Network shows repeated polling (every 2 seconds)
- `/api/metrics/claude-sessions` returns 20 old sessions
- `/api/tasks/running` returns 0 tasks
- Current CLI session not visible

## Comparison: Log-based vs Database-tracked Sessions

### `/api/metrics/claude-sessions` Response
**Source**: Log files via `hooks_reader.get_aggregate_statistics()`

**Last Session**:
```json
{
  "session_id": "c4842a6e-a54a-4aef-92f6-052e8bad333f",
  "last_activity": "2025-10-21T18:42:05.796342Z",
  "total_tools": 157,
  "errors": 20,
  "blocked": 0
}
```
**Note**: 3 hours old, not current session

### Database Query (SSE Stream)
**Source**: `tool_usage` table direct query

**Current Session**:
```json
{
  "task_id": "dccca803-5244-4324-bed2-8cd75854d0ae",
  "last_activity": "2025-10-21T21:15:10.991101",
  "tool_count": 38
}
```
**Note**: Active within last 5 minutes, includes THIS session

## Recommended Solutions

### Option A: Use SSE Activity Data (Minimal Change)
**Change**: Modify `fetchUnifiedData()` to use `data.activity` from SSE instead of calling `/api/metrics/claude-sessions`

**Pros**:
- Data already available in SSE stream
- No new API endpoints needed
- Real-time updates

**Cons**:
- Requires frontend refactor
- Activity data structure different from session structure

### Option B: Create New API Endpoint
**Add**: `GET /api/sessions/active` that returns database CLI sessions

**Pros**:
- Clean separation of concerns
- Consistent with existing API patterns
- Easy to implement

**Cons**:
- Adds new endpoint
- Frontend still needs small change

### Option C: Enhance Existing Endpoint (Recommended)
**Modify**: `/api/metrics/claude-sessions` to merge log-based + database sessions

**Implementation**:
```python
@app.route("/api/metrics/claude-sessions")
def claude_sessions_metrics():
    # Get log-based sessions
    sessions_stats = hooks_reader.get_aggregate_statistics(hours=hours)

    # Get DB-tracked CLI sessions (last 5 min)
    cutoff = (datetime.now() - timedelta(minutes=5)).isoformat()
    cursor.execute("""
        SELECT task_id, MAX(timestamp), COUNT(*)
        FROM tool_usage
        LEFT JOIN tasks ON tool_usage.task_id = tasks.task_id
        WHERE timestamp >= ? AND tasks.task_id IS NULL
        GROUP BY task_id
    """, (cutoff,))

    # Merge and deduplicate
    db_sessions = [...]
    all_sessions = merge_sessions(sessions_stats["recent_sessions"], db_sessions)

    return jsonify({...})
```

**Pros**:
- No frontend changes needed
- Backwards compatible
- Includes both log and DB sessions

**Cons**:
- Slightly more complex backend logic

## Network Activity

**Polling Pattern**:
- SSE stream: Open connection to `/api/stream/metrics?hours=24`
- Every 2 seconds:
  - `GET /api/tasks/running?page=1&page_size=8`
  - `GET /api/metrics/claude-sessions?hours=168`

**Issue**: Frontend polls every 2 seconds but doesn't use the SSE activity data it's receiving

## Conclusion

**Status**: CLI session tracking is WORKING at the database level, but INVISIBLE in the UI.

**Impact**:
- Users cannot see active CLI sessions in dashboard
- Badge count inaccurate (shows 0 instead of 1+)
- Activity feed missing real-time session data

**Priority**: Medium (functionality works, visibility issue only)

**Recommended Fix**: Option C (enhance `/api/metrics/claude-sessions` to include DB sessions)

---

**Validation Tools Used**:
- Playwright MCP: Browser automation and screenshot capture
- SQLite: Database queries for verification
- Network inspection: API endpoint analysis
- Code review: Backend SSE stream and frontend data flow
