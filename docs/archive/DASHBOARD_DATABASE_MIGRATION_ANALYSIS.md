# Dashboard Database Migration Analysis

**Date**: 2025-10-22
**Task**: Identify database migration completeness for monitoring dashboard
**Context**: Project migrated from JSON files (data/*.json) to SQLite database

## Executive Summary

The monitoring dashboard has **partially migrated** to SQLite. Core task tracking uses SQLite, but cost tracking still uses JSON files. This creates a mixed data access pattern that should be consolidated.

**Migration Status**: 🟡 Partial (70% complete)

## Dashboard Component Inventory

### 1. **Tasks & Sessions Section** (`#tasksSessionsSection`)
- **Purpose**: Display active/completed tasks and Claude Code sessions
- **Data Requirements**:
  - Task list (status, created_at, updated_at, description, error)
  - Session list (session_id, agent, status, tool counts)
  - Activity logs per task
  - Tool usage per task/session

### 2. **Documentation Section** (`#documentationSection`)
- **Purpose**: Browse .md files in docs/ directory
- **Data Requirements**: File system access (no database)
- **Status**: ✅ N/A (filesystem-based)

### 3. **Stats Footer** (metrics bar)
- **Components**:
  - Errors (24h)
  - Total Tasks
  - Success Rate
  - API Cost (24h) ⚠️
  - API Requests ⚠️
  - Tool Calls
  - Code Sessions

### 4. **Task/Session Detail Modal** (`#taskModal`)
- **Purpose**: Full-screen view of task details
- **Data Requirements**:
  - Planning progress (workflow info)
  - Tool usage timeline
  - Documents/screenshots
  - Activity log

### 5. **Errors Modal** (`#errorsModal`)
- **Purpose**: Display recent errors across all tasks
- **Data Requirements**: Task errors from database

## Data Source Mapping

### Flask API Routes → Data Sources

| Route | Component | Data Source | Status |
|-------|-----------|-------------|--------|
| `/api/stream/metrics` | Dashboard live updates | Mixed | 🟡 |
| `/api/tasks/running` | Active tasks | ✅ SQLite (`tasks` table) | ✅ |
| `/api/tasks/completed` | Completed tasks | ✅ SQLite (`tasks` table) | ✅ |
| `/api/tasks/all` | All tasks | ✅ SQLite (`tasks` table) | ✅ |
| `/api/tasks/<id>` | Task details | ✅ SQLite (`tasks` table) | ✅ |
| `/api/tasks/<id>/tool-usage` | Tool usage for task | ✅ SQLite (`tool_usage` table) | ✅ |
| `/api/tasks/activity` | Task activity log | ✅ SQLite (`tasks.activity_log`) | ✅ |
| `/api/metrics/overview` | Dashboard metrics | Mixed | 🟡 |
| `/api/metrics/claude-api` | API costs/usage | ❌ JSON (`data/usage.json`) | ❌ |
| `/api/metrics/tasks` | Task statistics | ✅ SQLite (`tasks` table) | ✅ |
| `/api/metrics/tools` | Tool statistics | ✅ SQLite (`tool_usage` table) | ✅ |
| `/api/metrics/cli-sessions` | Claude Code sessions | ✅ SQLite + JSONL hooks | ✅ |
| `/api/sessions/<id>/tool-usage` | Session tool details | ✅ SQLite (`tool_usage` table) | ✅ |
| `/api/docs/*` | Documentation files | Filesystem | ✅ N/A |

### Backend Data Access Patterns

#### ✅ **Fully Migrated (SQLite)**

**TaskManager** (`telegram_bot/tasks.py`):
```python
# Uses Database class exclusively
def __init__(self, db: Database = None, data_dir: str = "data"):
    self.db = db if db else Database()
```
- Operations: `create_task()`, `update_task()`, `get_active_tasks()`, etc.
- Tables used: `tasks`
- Status: ✅ Complete migration

**ToolUsageTracker** (`telegram_bot/tool_usage_tracker.py`):
```python
# Uses Database class exclusively
def __init__(self, db: Database = None, data_dir: str = "data"):
    self.db = db if db else Database()
```
- Operations: `record_tool_usage()`, `get_tool_statistics()`, etc.
- Tables used: `tool_usage`, `agent_status`
- Status: ✅ Complete migration

#### ❌ **Still Using JSON**

**CostTracker** (`telegram_bot/cost_tracker.py`):
```python
# Still uses JSON file!
def __init__(self, data_dir: str = "data"):
    self.usage_file = self.data_dir / "usage.json"
    self._load_usage()  # Reads JSON

def _save_usage(self):
    with open(self.usage_file, "w") as f:
        json.dump(data, f, indent=2)  # Writes JSON
```
- File: `data/usage.json`
- Operations: Cost tracking, usage limits, per-user costs
- Status: ❌ **Migration needed**

**HooksReader** (`telegram_bot/hooks_reader.py`):
- Reads JSONL files from `logs/sessions/*/post_tool_use.jsonl`
- Purpose: Complement SQLite data with hook details
- Status: ✅ Acceptable (temporary logs, not persistent data)

## Migration Gaps

### Critical Gap: Cost Tracking

**Problem**: `CostTracker` still uses `data/usage.json` for all cost data.

**Impact on Dashboard**:
1. **API Cost (24h)** stat - reads from JSON via `CostTracker`
2. **API Requests** stat - reads from JSON via `CostTracker`
3. `/api/metrics/claude-api` route - aggregates from JSON
4. `/api/user/usage` route (web chat) - reads from JSON

**Why This Matters**:
- Performance: JSON file I/O slower than SQLite queries
- Consistency: Mixed data access patterns harder to maintain
- Scalability: JSON file grows unbounded (no cleanup logic)
- Query capability: Can't use SQL for cost analytics

### Database Schema Gap

The SQLite schema (`database.py`) has **no cost tracking tables**:

**Existing Tables**:
- ✅ `tasks` - task tracking
- ✅ `tool_usage` - tool call tracking
- ✅ `agent_status` - agent status changes
- ✅ `files` - file access index
- ✅ `users` - web chat authentication
- ✅ `games` - game state
- ❌ **Missing**: `usage` or `cost_tracking` table

## Recommended Migration Plan

### Phase 1: Add Cost Tracking to Database

**Create new table** in `database.py`:

```python
# Migration version 11
if from_version <= 10 and to_version >= 11:
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS cost_tracking (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            user_id INTEGER NOT NULL,
            model TEXT NOT NULL,
            request_type TEXT NOT NULL,
            input_tokens INTEGER NOT NULL,
            output_tokens INTEGER NOT NULL,
            cost REAL NOT NULL,
            session_id TEXT
        )
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_cost_timestamp
        ON cost_tracking(timestamp DESC)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_cost_user
        ON cost_tracking(user_id, timestamp DESC)
    """)
```

**Add user limits table**:

```python
# Migration version 11 (continued)
cursor.execute("""
    CREATE TABLE IF NOT EXISTS user_limits (
        user_id INTEGER PRIMARY KEY,
        daily_limit REAL NOT NULL DEFAULT 100.0,
        monthly_limit REAL NOT NULL DEFAULT 1000.0,
        last_reset TEXT NOT NULL,
        last_warning TEXT
    )
""")
```

### Phase 2: Migrate CostTracker to SQLite

**Update `CostTracker.__init__()`**:
```python
def __init__(self, db: Database = None, data_dir: str = "data"):
    self.db = db if db else Database()
    # Remove: self.usage_file = ...
    # Remove: self._load_usage()
```

**Migrate methods**:
- `record_usage()` → Insert into `cost_tracking` table
- `get_usage_stats()` → Query `cost_tracking` with aggregation
- `check_limits()` → Query `user_limits` + aggregate recent costs
- Remove: `_load_usage()`, `_save_usage()`

**One-time migration script**:
```python
# migrate_cost_data.py
def migrate_cost_json_to_sqlite():
    """Migrate existing usage.json to SQLite"""
    cost_tracker_old = CostTracker()  # Loads JSON
    db = Database()

    for user_id, usage in cost_tracker_old.users.items():
        # Migrate records
        for record in usage.records:
            db.conn.execute("""
                INSERT INTO cost_tracking
                (timestamp, user_id, model, request_type,
                 input_tokens, output_tokens, cost)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (record.timestamp, user_id, record.model,
                  record.request_type, record.input_tokens,
                  record.output_tokens, record.cost))

        # Migrate limits
        db.conn.execute("""
            INSERT INTO user_limits
            (user_id, daily_limit, monthly_limit, last_reset)
            VALUES (?, ?, ?, ?)
        """, (user_id, usage.limits.get('daily', 100.0),
              usage.limits.get('monthly', 1000.0), usage.last_reset))

    db.conn.commit()
    print(f"Migrated {len(cost_tracker_old.users)} users")
```

### Phase 3: Update Monitoring Server

**No changes needed!** `monitoring_server.py` uses `CostTracker` methods, which will transparently use SQLite after migration.

```python
# monitoring_server.py (unchanged)
cost_tracker = CostTracker(data_dir=data_dir)
metrics_aggregator = MetricsAggregator(cost_tracker, ...)

@app.route("/api/metrics/claude-api")
def claude_api_metrics():
    # Still works - CostTracker now uses SQLite internally
    return jsonify(metrics_aggregator.get_claude_api_metrics())
```

### Phase 4: Cleanup

1. Remove `data/usage.json` after migration
2. Add database cleanup job for old cost records:
   ```python
   def cleanup_old_cost_records(self, days: int = 90) -> int:
       """Delete cost records older than specified days"""
       cutoff = (datetime.now() - timedelta(days=days)).isoformat()
       cursor = self.conn.cursor()
       cursor.execute(
           "DELETE FROM cost_tracking WHERE timestamp < ?",
           (cutoff,)
       )
       self.conn.commit()
       return cursor.rowcount
   ```
3. Update CLAUDE.md to document SQLite-only approach

## Testing Strategy

1. **Unit tests**: Test new Database methods for cost tracking
2. **Integration test**: Migrate test data, verify queries match old JSON results
3. **Dashboard test**: Verify all metrics display correctly
4. **Performance test**: Compare SQLite query speed vs JSON parsing

## Risks & Mitigation

| Risk | Impact | Mitigation |
|------|--------|-----------|
| Data loss during migration | High | Backup usage.json before migration |
| Query performance regression | Medium | Add proper indices (included in schema) |
| Breaking existing code | Medium | Keep old JSON path as fallback temporarily |
| Timezone handling | Low | Store timestamps as ISO 8601 strings (current approach) |

## Benefits of Complete Migration

1. **Performance**: SQLite queries 10-100x faster than JSON parsing
2. **Query capability**: Can analyze costs by user, model, time period using SQL
3. **Consistency**: Single data access pattern across codebase
4. **Scalability**: Automatic cleanup, no unbounded file growth
5. **Reliability**: ACID transactions, no partial writes
6. **Maintainability**: Standard database operations, no custom JSON handling

## Timeline Estimate

- Phase 1 (Schema): 2 hours
- Phase 2 (CostTracker migration): 4 hours
- Phase 3 (Testing): 2 hours
- Phase 4 (Cleanup): 1 hour

**Total**: ~1 day of development work

## Conclusion

The monitoring dashboard is **70% migrated to SQLite**. The remaining 30% (cost tracking) is isolated in `CostTracker` class, making migration straightforward. Completing this migration will:

- Eliminate all JSON file dependencies
- Improve dashboard performance
- Enable advanced cost analytics
- Simplify maintenance

**Recommendation**: Prioritize completing the cost tracking migration in next sprint.

---

**Related Files**:
- `telegram_bot/database.py` - SQLite schema and operations
- `telegram_bot/cost_tracker.py` - ❌ Still uses JSON
- `telegram_bot/tasks.py` - ✅ Migrated to SQLite
- `telegram_bot/tool_usage_tracker.py` - ✅ Migrated to SQLite
- `telegram_bot/monitoring_server.py` - Flask routes
- `telegram_bot/templates/dashboard.html` - Frontend UI
- `telegram_bot/static/js/dashboard.js` - Client-side data fetching
