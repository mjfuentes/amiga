# 5. SQLite for Persistence

Date: 2025-01-15

## Status

Accepted

## Context

The bot needs to persist data across restarts:

1. **Task tracking**: Active, pending, completed, failed tasks
2. **Tool usage metrics**: Performance data, errors, costs
3. **Agent status**: Status changes, workflow progress
4. **File index**: Which files accessed by which tasks
5. **User management**: Web chat authentication
6. **Query requirements**: Complex queries (by status, time range, user)

**Requirements:**
- Survive bot restarts without data loss
- Support concurrent reads and writes (async environment)
- Enable complex queries (JOIN, aggregation, filtering)
- Simple deployment (no separate database server)
- Backup and recovery capabilities
- Migration support for schema evolution

**Constraints:**
- Single-user bot (not multi-tenant SaaS)
- Running on single machine (no distributed deployment needed)
- Development focus (not enterprise scale)

## Decision

Use **SQLite as the primary persistence layer** instead of PostgreSQL or other database systems.

**Architecture** (implemented in `tasks/database.py`):

```python
class Database:
    """SQLite database wrapper for AMIGA storage"""
    def __init__(self, db_path: str = "data/agentlab.db"):
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row  # Column access by name
        self.conn.execute("PRAGMA journal_mode=WAL")  # Better concurrency
        self.conn.execute("PRAGMA foreign_keys = ON")  # Referential integrity
```

**Schema** (version 13 as of 2025-01-15):
- `tasks` - Task tracking with status, timestamps, results
- `tool_usage` - Tool calls with duration, success, errors, tokens
- `agent_status` - Agent status changes
- `files` - File access index
- `users` - Web chat authentication
- `games` - Game state (if enabled)
- `documents` - Documentation tracking

**Features:**
- **WAL mode**: Better concurrent read/write performance
- **Foreign keys**: Referential integrity enforcement
- **Migrations**: Versioned schema with migration functions
- **Async-safe**: Lock for write operations in async environment
- **Row factory**: Column access by name (cleaner code)

## Consequences

### Positive

- **Zero configuration**: No database server to install or configure
- **Simple deployment**: Single file (`data/agentlab.db`)
- **Easy backup**: Copy single file for full backup
- **Fast queries**: Excellent performance for single-user workload
- **ACID compliance**: Reliable transactions, no data corruption
- **Good tooling**: sqlite3 CLI, DB Browser, Python stdlib support
- **Low overhead**: Minimal memory/CPU compared to server databases
- **Version control friendly**: Can commit schema migrations to git

### Negative

- **No horizontal scaling**: Can't distribute across multiple machines
- **Limited concurrency**: Write locks (mitigated by WAL mode)
- **No network access**: Can't query from other machines (fine for our use case)
- **Single file corruption risk**: If file corrupts, all data at risk (mitigated by backups)
- **Manual migrations**: No automatic migration framework (acceptable trade-off)

## Alternatives Considered

1. **PostgreSQL**
   - Rejected: Overkill for single-user bot
   - Requires separate server process
   - More complex deployment and backup
   - Would enable horizontal scaling (not needed)

2. **MySQL/MariaDB**
   - Rejected: Same issues as PostgreSQL
   - No significant advantages for our use case

3. **JSON Files** (original approach)
   - Rejected: Used initially, migrated to SQLite in v2
   - Issues: Race conditions, no querying, file corruption
   - Can't do complex queries (JOIN, aggregation)
   - Difficult to maintain consistency

4. **NoSQL (MongoDB, Redis)**
   - Rejected: Document model doesn't fit relational data
   - Redis is in-memory (not suitable for persistence)
   - More complex deployment

5. **ORMs (SQLAlchemy, Django ORM)**
   - Considered but not used
   - Decided to use direct SQL for simplicity and performance
   - ORM adds abstraction overhead
   - Direct SQL is more transparent and debuggable

6. **Cloud Database (AWS RDS, Google Cloud SQL)**
   - Rejected: Unnecessary complexity and cost
   - Adds network latency
   - Requires cloud account and credentials
   - SQLite is sufficient for single-machine deployment

## Migration Strategy

**Schema versioning** (`tasks/database.py:21`):
```python
SCHEMA_VERSION = 13  # Current schema version
```

**Migration functions** (`tasks/database.py:88-410`):
- Each version has dedicated migration function
- Migrations are idempotent (safe to re-run)
- Version tracked in `schema_version` table
- Automatic migration on startup if needed

**Example migration** (v10 - token tracking):
```python
def _migration_v10_add_token_columns(self, cursor):
    """Migration v10: Add token usage columns to tool_usage table"""
    # Check existing columns
    cursor.execute("PRAGMA table_info(tool_usage)")
    columns = [col[1] for col in cursor.fetchall()]

    # Add new columns if missing
    for col_name, col_type in token_columns.items():
        if col_name not in columns:
            cursor.execute(f"ALTER TABLE tool_usage ADD COLUMN {col_name} {col_type}")
```

## References

- Implementation: `tasks/database.py:24-2138`
- Schema version: `tasks/database.py:21`
- Migrations: `tasks/database.py:88-410`
- WAL mode: `tasks/database.py:49`
- Migration strategy: `tasks/database.py:88-132`
- Database path: `core/config.py` (DATABASE_PATH constant)
- Usage examples: `tasks/manager.py`, `monitoring/server.py`
