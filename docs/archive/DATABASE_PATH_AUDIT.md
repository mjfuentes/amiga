# Database Path Audit Report

**Generated:** 2025-10-21
**Purpose:** Comprehensive audit of all hardcoded database paths in AMIGA codebase
**Scope:** All Python files with database path references

---

## Executive Summary

The AMIGA codebase has **16 files** with hardcoded database paths. The main database file is `agentlab.db`, stored in the `data/` directory. Most components use a `data_dir` parameter pattern, but the default value `"data"` is hardcoded in multiple locations.

**Key Findings:**
- **Core modules** (Database, TaskManager, ToolUsageTracker, CostTracker, SessionManager) all accept `data_dir` parameter with default `"data"`
- **Main entry points** (main.py, monitoring_server.py, web_chat servers) hardcode database initialization
- **Analysis scripts** have hardcoded `"data/agentlab.db"` paths
- **Path construction** is inconsistent across files (some use Path objects, some use strings)

---

## 1. Core Database Module

### `/Users/matifuentes/Workspace/agentlab/telegram_bot/database.py`

**Line 23:** Database class initialization
```python
def __init__(self, db_path: str = "data/agentlab.db"):
    self.db_path = Path(db_path)
    self.db_path.parent.mkdir(exist_ok=True)
```

**Current Logic:**
- Accepts `db_path` as parameter
- Default: `"data/agentlab.db"` (relative path)
- Converts to Path object internally
- Creates parent directory if missing

**Dependencies:**
- Used by: TaskManager, ToolUsageTracker, GameManager, migrate_to_sqlite.py

---

## 2. Task Management System

### `/Users/matifuentes/Workspace/agentlab/telegram_bot/tasks.py`

**Line 230-239:** TaskManager initialization
```python
def __init__(self, db: Database = None, data_dir: str = "data"):
    self.data_dir = Path(data_dir)
    self.data_dir.mkdir(exist_ok=True)

    # Use provided database or create new one
    if db is not None:
        self.db = db
    else:
        db_path = self.data_dir / "agentlab.db"
        self.db = Database(str(db_path))
```

**Current Logic:**
- Accepts optional `Database` instance OR `data_dir` parameter
- Default `data_dir`: `"data"` (relative path)
- Constructs DB path: `{data_dir}/agentlab.db`
- Creates directory if missing

**Dependencies:**
- Imports: `from database import Database`
- Used by: main.py, monitoring_server.py, web_chat/server.py, web_chat/api_routes.py

---

## 3. Tool Usage Tracker

### `/Users/matifuentes/Workspace/agentlab/telegram_bot/tool_usage_tracker.py`

**Line 60-69:** ToolUsageTracker initialization
```python
def __init__(self, db: Database = None, data_dir: str = "data"):
    self.data_dir = Path(data_dir)
    self.data_dir.mkdir(exist_ok=True)

    # Use provided database or create new one
    if db is not None:
        self.db = db
    else:
        db_path = self.data_dir / "agentlab.db"
        self.db = Database(str(db_path))
```

**Current Logic:**
- Same pattern as TaskManager
- Accepts optional `Database` instance OR `data_dir` parameter
- Default `data_dir`: `"data"`
- Constructs DB path: `{data_dir}/agentlab.db`

**Dependencies:**
- Imports: `from database import Database`
- Used by: main.py, monitoring_server.py, claude_interactive.py

---

## 4. Cost Tracker

### `/Users/matifuentes/Workspace/agentlab/telegram_bot/cost_tracker.py`

**Line 92-95:** CostTracker initialization
```python
def __init__(self, data_dir: str = "data"):
    self.data_dir = Path(data_dir)
    self.data_dir.mkdir(exist_ok=True)
    self.usage_file = self.data_dir / "usage.json"
```

**Current Logic:**
- Accepts `data_dir` parameter
- Default: `"data"`
- Uses **JSON file** (`usage.json`), NOT the SQLite database
- This is a **separate file** from agentlab.db

**Dependencies:**
- Does NOT use Database class
- Used by: main.py, monitoring_server.py, web_chat servers

---

## 5. Session Manager

### `/Users/matifuentes/Workspace/agentlab/telegram_bot/session.py`

**Line 54-57:** SessionManager initialization
```python
def __init__(self, data_dir: str = "data"):
    self.data_dir = Path(data_dir)
    self.data_dir.mkdir(exist_ok=True)
    self.sessions_file = self.data_dir / "sessions.json"
```

**Current Logic:**
- Accepts `data_dir` parameter
- Default: `"data"`
- Uses **JSON file** (`sessions.json`), NOT the SQLite database
- This is a **separate file** from agentlab.db

**Dependencies:**
- Does NOT use Database class
- Used by: main.py, monitoring_server.py, web_chat servers

---

## 6. Main Entry Point - Telegram Bot

### `/Users/matifuentes/Workspace/agentlab/telegram_bot/main.py`

**Line 205:** Database initialization
```python
db = Database("data/agentlab.db")  # Shared database instance
```

**Current Logic:**
- **HARDCODED** path: `"data/agentlab.db"`
- Creates shared Database instance
- Passed to TaskManager, ToolUsageTracker, GameManager
- NO environment variable override
- Path is relative to current working directory

**Dependencies:**
- Imports: `from database import Database`
- This is the **single source of truth** for the Telegram bot

**Related Lines:**
- Line 1155: `restart_state_path = Path("data/restart_state.json")`
- Line 2490: `restart_state_path = Path("data/restart_state.json")`

---

## 7. Monitoring Server

### `/Users/matifuentes/Workspace/agentlab/telegram_bot/monitoring_server.py`

**Line 55-71:** Data directory determination
```python
if Path.cwd().name == "telegram_bot":
    # Running from telegram_bot/ directory
    data_dir = "../data"
    sessions_dir = "../logs/sessions"
else:
    # Running from project root
    data_dir = "data"
    sessions_dir = "logs/sessions"

# Initialize tracking systems
cost_tracker = CostTracker(data_dir=data_dir)
task_manager = TaskManager(data_dir=data_dir)
tool_usage_tracker = ToolUsageTracker(data_dir=data_dir)
```

**Current Logic:**
- **Conditional path** based on current working directory
- Uses relative paths (`"data"` or `"../data"`)
- Passes `data_dir` to all managers (which construct `agentlab.db` internally)
- NO environment variable override

**Dependencies:**
- Imports: CostTracker, TaskManager, ToolUsageTracker
- Each manager constructs its own DB path

---

## 8. Web Chat Server

### `/Users/matifuentes/Workspace/agentlab/web_chat/server.py`

**Line 62-66:** Data directory path
```python
DATA_DIR = str(Path(__file__).parent.parent / "telegram_bot" / "data")
session_manager = SessionManager(data_dir=DATA_DIR)
task_manager = TaskManager(data_dir=DATA_DIR)
agent_pool = AgentPool(max_agents=3)
cost_tracker = CostTracker(data_dir=DATA_DIR)
```

**Current Logic:**
- **HARDCODED** relative path construction
- Resolves to: `{web_chat_parent}/telegram_bot/data`
- Passes to managers (which construct `agentlab.db` internally)
- NO environment variable override

**Dependencies:**
- Imports: SessionManager, TaskManager, CostTracker

---

## 9. Web Chat API Routes

### `/Users/matifuentes/Workspace/agentlab/web_chat/api_routes.py`

**Line 27-30:** Data directory path
```python
DATA_DIR = str(Path(__file__).parent.parent / "telegram_bot" / "data")
session_manager = SessionManager(data_dir=DATA_DIR)
task_manager = TaskManager(data_dir=DATA_DIR)
cost_tracker = CostTracker(data_dir=DATA_DIR)
```

**Current Logic:**
- **DUPLICATE** of web_chat/server.py logic
- Same hardcoded relative path construction
- Creates **separate instances** of managers (not shared with server.py)

**Dependencies:**
- Imports: SessionManager, TaskManager, CostTracker

---

## 10. Metrics Aggregator

### `/Users/matifuentes/Workspace/agentlab/telegram_bot/metrics_aggregator.py`

**Line 208-221:** System health check
```python
def get_system_health(self) -> dict[str, Any]:
    # Check data file sizes (now includes database)
    data_dir = Path("data")
    file_sizes = {}

    if data_dir.exists():
        # Include JSON files
        for file in data_dir.glob("*.json"):
            size_mb = file.stat().st_size / (1024 * 1024)
            file_sizes[file.name] = round(size_mb, 2)

        # Include database file
        db_file = data_dir / "agentlab.db"
        if db_file.exists():
            size_mb = db_file.stat().st_size / (1024 * 1024)
            file_sizes["agentlab.db"] = round(size_mb, 2)
```

**Current Logic:**
- **HARDCODED** path: `Path("data")`
- Used for file size statistics
- NO access to injected data_dir from parent

**Dependencies:**
- Standalone file size check
- Does NOT use Database class

---

## 11. Analysis Scripts

### Analysis Scripts with Hardcoded Paths:

All located in project root:

#### `/Users/matifuentes/Workspace/agentlab/analyze_tool_usage.py`
**Line 11:** `DB_PATH = "data/agentlab.db"`

#### `/Users/matifuentes/Workspace/agentlab/analyze_errors.py`
**Line 10:** `DB_PATH = "data/agentlab.db"`

#### `/Users/matifuentes/Workspace/agentlab/analyze_actual_errors.py`
**Line 9:** `DB_PATH = "data/agentlab.db"`

#### `/Users/matifuentes/Workspace/agentlab/check_improvement.py`
**Line 9:** `DB_PATH = "data/agentlab.db"`

#### `/Users/matifuentes/Workspace/agentlab/query_top_tools.py`
**Line 76:** `db_path = script_dir / "data" / "agentlab.db"`

**Current Logic:**
- All use **HARDCODED** constant `DB_PATH = "data/agentlab.db"`
- Relative to script execution directory (assumes run from project root)
- NO command-line argument override
- Direct sqlite3 connections (not using Database class)

**Dependencies:**
- Import: `import sqlite3`
- Standalone analysis scripts

---

## 12. Migration Script

### `/Users/matifuentes/Workspace/agentlab/telegram_bot/migrate_to_sqlite.py`

**Line 284-286:** Main function signature
```python
def main(data_dir: str = "data", db_path: str = "data/agentlab.db", force: bool = False):
    data_dir = Path(data_dir)
```

**Line 385-386:** Argument parser
```python
parser.add_argument(
    "--db-path",
    default="data/agentlab.db",
    help="Path for SQLite database (default: data/agentlab.db)",
)
```

**Current Logic:**
- Accepts command-line arguments for both `data_dir` and `db_path`
- Defaults: `data_dir="data"`, `db_path="data/agentlab.db"`
- Uses Database class for migration

**Dependencies:**
- Imports: `from database import Database`

---

## 13. Test Files

### Test File Path Usage:

#### `/Users/matifuentes/Workspace/agentlab/test_cost_rate_limiting.py`
**Line 21:** `tracker = CostTracker(data_dir="data/test")`

#### `/Users/matifuentes/Workspace/agentlab/test_file_indexing.py`
**Line 235:** `tracker = ToolUsageTracker(db=db, data_dir=tmpdir)`

**Current Logic:**
- Tests use custom `data_dir` paths
- Good: Uses temporary directories for testing
- No hardcoded production paths in tests

---

## Dependency Graph

```
Database (database.py)
├── Default: "data/agentlab.db"
└── Used by:
    ├── TaskManager (tasks.py)
    │   ├── Default data_dir: "data"
    │   └── Constructs: {data_dir}/agentlab.db
    ├── ToolUsageTracker (tool_usage_tracker.py)
    │   ├── Default data_dir: "data"
    │   └── Constructs: {data_dir}/agentlab.db
    ├── GameManager (game_manager.py)
    │   └── Uses injected Database instance
    └── migrate_to_sqlite.py
        ├── Default: "data/agentlab.db"
        └── CLI override available

Main Entry Points:
├── main.py
│   ├── HARDCODED: Database("data/agentlab.db")
│   └── Shares single instance with all managers
├── monitoring_server.py
│   ├── Conditional: "data" or "../data"
│   └── Each manager creates own DB instance
├── web_chat/server.py
│   ├── HARDCODED: Path(...) / "telegram_bot" / "data"
│   └── Each manager creates own DB instance
└── web_chat/api_routes.py
    ├── HARDCODED: Path(...) / "telegram_bot" / "data"
    └── DUPLICATE instances (not shared with server.py!)

Analysis Scripts:
├── analyze_tool_usage.py → "data/agentlab.db"
├── analyze_errors.py → "data/agentlab.db"
├── analyze_actual_errors.py → "data/agentlab.db"
├── check_improvement.py → "data/agentlab.db"
└── query_top_tools.py → script_dir / "data" / "agentlab.db"

Standalone JSON Files:
├── CostTracker (cost_tracker.py)
│   ├── Default: "data/usage.json"
│   └── NOT using SQLite database
└── SessionManager (session.py)
    ├── Default: "data/sessions.json"
    └── NOT using SQLite database
```

---

## Path Construction Patterns

### Pattern 1: Database Class Direct Initialization
```python
# Used by: main.py
db = Database("data/agentlab.db")
```

### Pattern 2: Manager with data_dir Parameter
```python
# Used by: TaskManager, ToolUsageTracker
def __init__(self, data_dir: str = "data"):
    self.data_dir = Path(data_dir)
    db_path = self.data_dir / "agentlab.db"
    self.db = Database(str(db_path))
```

### Pattern 3: Manager with Injected Database
```python
# Used by: TaskManager, ToolUsageTracker (alternative)
def __init__(self, db: Database = None):
    if db is not None:
        self.db = db
    else:
        # Fallback to pattern 2
```

### Pattern 4: Conditional Path Resolution
```python
# Used by: monitoring_server.py
if Path.cwd().name == "telegram_bot":
    data_dir = "../data"
else:
    data_dir = "data"
```

### Pattern 5: Relative Path Construction
```python
# Used by: web_chat servers
DATA_DIR = str(Path(__file__).parent.parent / "telegram_bot" / "data")
```

### Pattern 6: Hardcoded Constant
```python
# Used by: analysis scripts
DB_PATH = "data/agentlab.db"
```

---

## Issues Identified

### 1. Multiple Database Instances
**Problem:** Different modules create separate Database instances instead of sharing one.

**Affected Files:**
- monitoring_server.py (creates via TaskManager, ToolUsageTracker)
- web_chat/server.py (creates via managers)
- web_chat/api_routes.py (creates DUPLICATE instances!)

**Impact:**
- Multiple SQLite connections to same file
- Potential for WAL file conflicts
- Unnecessary resource usage

**Recommendation:**
- Pass shared Database instance to all managers
- Follow main.py pattern (single db instance)

### 2. Inconsistent Path Resolution
**Problem:** Different strategies for resolving `data_dir` path.

**Examples:**
- main.py: Assumes CWD is correct
- monitoring_server.py: Checks CWD name and adjusts
- web_chat: Uses `__file__` relative paths

**Impact:**
- Confusing when scripts run from different directories
- Hard to predict which database file will be used

**Recommendation:**
- Standardize on one path resolution strategy
- Use environment variable override

### 3. No Environment Variable Override
**Problem:** Cannot override database path via environment variable.

**Current State:**
- All paths are hardcoded or defaulted to `"data"`
- No `DB_PATH` or `DATA_DIR` env var support

**Impact:**
- Cannot easily switch between dev/test/prod databases
- Cannot isolate tests without code changes

**Recommendation:**
- Add env var: `AGENTLAB_DATA_DIR` or `AGENTLAB_DB_PATH`
- Read in Database.__init__ and managers

### 4. Analysis Scripts Not Parameterized
**Problem:** Analysis scripts have hardcoded `DB_PATH = "data/agentlab.db"`.

**Affected Files:**
- analyze_tool_usage.py
- analyze_errors.py
- analyze_actual_errors.py
- check_improvement.py
- query_top_tools.py

**Impact:**
- Cannot analyze non-default database
- Cannot run in CI/CD with custom paths

**Recommendation:**
- Add argparse support for `--db-path`
- Default to env var or `"data/agentlab.db"`

### 5. JSON Files Not Migrated to SQLite
**Problem:** CostTracker and SessionManager still use JSON files.

**Current State:**
- `data/usage.json` (CostTracker)
- `data/sessions.json` (SessionManager)

**Impact:**
- Inconsistent storage backend
- Potential data race conditions (JSON writes not atomic)

**Future Work:**
- Migrate usage tracking to SQLite
- Migrate sessions to SQLite

### 6. Metrics Aggregator Hardcoded Path
**Problem:** `get_system_health()` uses `Path("data")` instead of injected path.

**Line:** metrics_aggregator.py:208

**Impact:**
- Won't work if data_dir is customized
- Can't monitor custom database locations

**Recommendation:**
- Pass data_dir to MetricsAggregator constructor
- Store as instance variable

---

## Recommendations for Refactoring

### Phase 1: Environment Variable Support
1. Add `AGENTLAB_DATA_DIR` environment variable support
2. Update Database class to read from env var
3. Update all managers to read from env var
4. Document in README.md and CLAUDE.md

### Phase 2: Shared Database Instance
1. Refactor monitoring_server.py to create single Database instance
2. Pass db instance to TaskManager, ToolUsageTracker
3. Do same for web_chat servers
4. Eliminate duplicate Database instances

### Phase 3: Analysis Script Parameterization
1. Add argparse to all analysis scripts
2. Support `--db-path` argument
3. Default to env var if set, else `"data/agentlab.db"`
4. Update docs with usage examples

### Phase 4: Path Resolution Standardization
1. Choose ONE strategy (recommend: env var > __file__ relative > CWD)
2. Update all modules to use same strategy
3. Add helper function: `get_data_dir()` in utils module
4. Document assumptions in CLAUDE.md

### Phase 5: Migrate JSON to SQLite (Future)
1. Add tables for usage tracking and sessions
2. Migrate CostTracker to use Database
3. Migrate SessionManager to use Database
4. Keep JSON as fallback for backwards compatibility

---

## Summary Table

| File | Line(s) | Current Path Logic | Uses Database Class | Hardcoded? |
|------|---------|-------------------|-------------------|-----------|
| database.py | 23 | Default: `"data/agentlab.db"` | ✅ (defines it) | ✅ Default only |
| tasks.py | 238 | `{data_dir}/agentlab.db` | ✅ | ⚠️ Default data_dir |
| tool_usage_tracker.py | 68 | `{data_dir}/agentlab.db` | ✅ | ⚠️ Default data_dir |
| cost_tracker.py | 93 | `{data_dir}/usage.json` | ❌ JSON file | ⚠️ Default data_dir |
| session.py | 55 | `{data_dir}/sessions.json` | ❌ JSON file | ⚠️ Default data_dir |
| main.py | 205 | `"data/agentlab.db"` | ✅ | ✅ Fully hardcoded |
| monitoring_server.py | 55-71 | `"data"` or `"../data"` | ✅ (via managers) | ✅ Conditional |
| web_chat/server.py | 62 | `Path(__file__)/.../data` | ✅ (via managers) | ✅ Relative path |
| web_chat/api_routes.py | 27 | `Path(__file__)/.../data` | ✅ (via managers) | ✅ Relative path |
| metrics_aggregator.py | 208, 218 | `Path("data")` | ❌ File stats only | ✅ Fully hardcoded |
| migrate_to_sqlite.py | 284 | Default: `"data/agentlab.db"` | ✅ | ⚠️ CLI override available |
| analyze_tool_usage.py | 11 | `"data/agentlab.db"` | ❌ sqlite3 direct | ✅ Constant |
| analyze_errors.py | 10 | `"data/agentlab.db"` | ❌ sqlite3 direct | ✅ Constant |
| analyze_actual_errors.py | 9 | `"data/agentlab.db"` | ❌ sqlite3 direct | ✅ Constant |
| check_improvement.py | 9 | `"data/agentlab.db"` | ❌ sqlite3 direct | ✅ Constant |
| query_top_tools.py | 76 | `script_dir/"data"/agentlab.db` | ❌ sqlite3 direct | ✅ Relative path |

**Legend:**
- ✅ Yes / Fully hardcoded
- ❌ No
- ⚠️ Partially (has default but parameterizable)

---

## Files NOT Requiring Changes

The following files reference database paths but are correctly parameterized:

1. **test_cost_rate_limiting.py** - Uses custom test directory
2. **test_file_indexing.py** - Uses tmpdir parameter
3. **game_manager.py** - Accepts injected Database instance (no hardcoded path)

---

## Conclusion

The AMIGA codebase has **extensive hardcoding** of the database path, but most components follow a **consistent pattern** of accepting a `data_dir` parameter with a default value. The main issues are:

1. **No environment variable override** for production flexibility
2. **Multiple Database instances** instead of sharing one
3. **Analysis scripts lack parameterization**
4. **Inconsistent path resolution strategies** across entry points

A phased refactoring approach is recommended, starting with environment variable support and progressing to shared database instances and standardized path resolution.

**Next Steps:**
1. Review this audit with team
2. Prioritize refactoring phases
3. Create GitHub issues for each phase
4. Implement Phase 1 (env var support) first

---

**End of Report**
