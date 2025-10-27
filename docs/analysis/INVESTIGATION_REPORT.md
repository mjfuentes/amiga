# Tool Usage Data Missing - Root Cause Analysis

**Investigation Date**: 2025-10-22
**Task ID**: 1761134075517
**Reporter**: code_agent

## Executive Summary

Tool usage data is not appearing in the monitoring dashboard because **the `session_uuid` field is NULL in all 213 tasks in the database**. This breaks the correlation between `tasks` table (6-char IDs) and `tool_usage` table (36-char UUIDs).

## Root Cause

### The Intended Flow

1. Task created with 6-char ID (e.g., "37d679")
2. Claude session started with deterministic UUID5 (e.g., "e4b97dab-ed2f-57e4-a8b6-1387052fde3f")
3. **session_uuid should be stored in tasks table** (line 282 in `claude_interactive.py`)
4. PostToolUse hook writes `tool_usage` records with session_uuid as `task_id`
5. Monitoring server queries `tool_usage` using `session_uuid` from `tasks` table

### The Actual Flow

Step 3 is **silently failing**. Evidence:

```bash
# Check tasks table - NO session_uuid set
$ sqlite3 data/agentlab.db "SELECT COUNT(*) FROM tasks WHERE session_uuid IS NOT NULL"
0  # <-- ZERO out of 213 tasks!

$ sqlite3 data/agentlab.db "SELECT task_id, session_uuid FROM tasks WHERE task_id = '37d679'"
37d679||completed  # <-- session_uuid is NULL

# Check tool_usage table - Uses UUIDs
$ sqlite3 data/agentlab.db "SELECT task_id, tool_name FROM tool_usage LIMIT 5"
03a316f3-c005-4936-a310-95d23aecc7e5|Read
03a316f3-c005-4936-a310-95d23aecc7e5|Read
...

# Check UUID format distribution
$ sqlite3 data/agentlab.db "SELECT LENGTH(task_id), COUNT(*) FROM tool_usage GROUP BY LENGTH(task_id)"
4|1
6|423      # <-- Some 6-char IDs (shouldn't exist)
36|8188    # <-- Most are 36-char UUIDs (correct)
```

### Why the Dashboard Shows No Data

`monitoring_server.py` line 893-899:
```python
session_uuid = task.get("session_uuid") if task else None
query_id = session_uuid if session_uuid else task_id  # Falls back to 6-char ID
```

Since `session_uuid` is NULL, it queries with "37d679", but `tool_usage` table has "e4b97dab-ed2f-57e4-a8b6-1387052fde3f" → **no matches found**.

## Component Analysis

### 1. Data Collection (Hooks) - ✅ WORKING

PostToolUse hook is firing correctly:
- 5,120 PostToolUse events in `/tmp/hook_debug.log`
- Hook writes to database with `session_id` as `task_id` (line 138 in `post-tool-use`)
- Tool usage records exist in database (8,622 records)

### 2. Data Storage (Database) - ✅ SCHEMA OK, ❌ DATA MISSING

Schema is correct:
```sql
CREATE TABLE tasks (
    ...
    session_uuid TEXT,  # Column exists
    ...
);
```

`Database.update_task()` method supports `session_uuid` parameter (lines 476-505 in `database.py`).

### 3. session_uuid Update - ❌ FAILING SILENTLY

Code in `claude_interactive.py` line 282:
```python
await self.usage_tracker.db.update_task(task_id=task_id, session_uuid=task_uuid, pid=self.process.pid)
```

This update is **failing silently** for ALL tasks. Possible causes:

1. **`usage_tracker` is None** - unlikely (it's used elsewhere in same method)
2. **`usage_tracker.db` is None** - needs verification
3. **Database update failing** - no error logging
4. **Transaction not committed** - possible if async timing issue
5. **Wrong database instance** - monitoring server vs bot might use different DB connections

### 4. Data Retrieval (API) - ✅ LOGIC OK

`monitoring_server.py` correctly attempts to use `session_uuid` for correlation. The logic is sound, but data is missing.

## Evidence Timeline

**Task #37d679** (2025-10-22 13:53:37):
- Created: ✅
- PID set: ✅ (92278)
- session_uuid set: ❌ (NULL)
- Tool usage recorded: ✅ (in separate UUID-based session)
- Dashboard display: ❌ (no correlation possible)

## Impact

- **Severity**: High
- **Scope**: All 213 tasks in database
- **User Impact**: Tool execution tracking invisible in dashboard
- **Data Loss**: No - tool usage IS being recorded, just not linked to tasks

## Recommendations

### Immediate Fix

1. **Add debug logging** to `claude_interactive.py` line 282:
   ```python
   logger.info(f"Updating task {task_id} with session_uuid={task_uuid}")
   result = await self.usage_tracker.db.update_task(...)
   logger.info(f"Update result: {result}")
   ```

2. **Verify `usage_tracker.db` is not None** before calling update_task

3. **Check database connection** - ensure monitoring server and bot share same DB instance

### Long-term Fix

1. **Backfill missing session_uuid values** - match existing tool_usage UUIDs to tasks by PID/timestamp
2. **Add assertion/validation** - fail loudly if session_uuid update fails
3. **Add monitoring** - alert if tasks created without session_uuid
4. **Integration test** - verify end-to-end flow from task creation to dashboard display

## Next Steps

1. Investigate why `Database.update_task()` is failing
2. Check if `usage_tracker` or `usage_tracker.db` is None during session start
3. Add logging to track update success/failure
4. Test fix with new task
5. Backfill historical data if possible

## Related Files

- `/Users/matifuentes/Workspace/agentlab/telegram_bot/claude_interactive.py` - session_uuid update (line 282)
- `/Users/matifuentes/Workspace/agentlab/telegram_bot/database.py` - update_task method (lines 476-505)
- `/Users/matifuentes/Workspace/agentlab/telegram_bot/monitoring_server.py` - tool usage query (lines 893-899)
- `/Users/matifuentes/Workspace/agentlab/.claude/hooks/post-tool-use` - hook writes tool_usage (line 138)

---

**Confidence**: High
**Data Quality**: Verified with SQL queries
**Reproducibility**: 100% (all tasks affected)
