"""
SQLite database backend for AMIGA
Replaces JSON file storage with SQLite for better performance and querying
"""

import asyncio
import json
import logging
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from core.config import DATABASE_PATH

from core.exceptions import AMIGAError

logger = logging.getLogger(__name__)

# Database schema version for migrations
SCHEMA_VERSION = 13


class Database:
    """SQLite database wrapper for AMIGA storage"""

    def __init__(self, db_path: str | Path | None = None):
        """
        Initialize database connection.

        Args:
            db_path: Path to database file. If None, uses centralized config (recommended).
                     Can be str or Path for backward compatibility.
        """
        if db_path is None:
            self.db_path = DATABASE_PATH
        else:
            self.db_path = Path(db_path)

        self.db_path.parent.mkdir(exist_ok=True)

        self.conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row  # Enable column access by name

        # Lock for serializing write operations in async environment
        self._write_lock = asyncio.Lock()

        # Enable WAL mode for better concurrency
        self.conn.execute("PRAGMA journal_mode=WAL")

        # Enable foreign keys
        self.conn.execute("PRAGMA foreign_keys = ON")

        # Initialize schema
        self._init_schema()

        logger.info(f"Database initialized at {self.db_path}")

    def _init_schema(self):
        """Initialize database schema"""
        cursor = self.conn.cursor()

        # Create schema version table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_version (
                version INTEGER PRIMARY KEY,
                applied_at TEXT NOT NULL
            )
        """
        )

        # Check current version
        cursor.execute("SELECT version FROM schema_version ORDER BY version DESC LIMIT 1")
        row = cursor.fetchone()
        current_version = row[0] if row else 0

        if current_version < SCHEMA_VERSION:
            self._migrate_schema(current_version, SCHEMA_VERSION)
            cursor.execute(
                "INSERT INTO schema_version (version, applied_at) VALUES (?, ?)",
                (SCHEMA_VERSION, datetime.now().isoformat()),
            )
            self.conn.commit()

        logger.info(f"Database schema version: {SCHEMA_VERSION}")

    def _migrate_schema(self, from_version: int, to_version: int):
        """
        Apply schema migrations by calling version-specific migration functions.

        This orchestrates the migration process by invoking individual migration
        handlers for each version upgrade.
        """
        cursor = self.conn.cursor()

        if from_version == 0 and to_version >= 1:
            self._migration_v1_initial_schema(cursor)

        if from_version <= 1 and to_version >= 2:
            self._migration_v2_add_games(cursor)

        if from_version <= 2 and to_version >= 3:
            self._migration_v3_add_workflow_column(cursor)

        if from_version <= 3 and to_version >= 4:
            self._migration_v4_add_context_column(cursor)

        if from_version <= 4 and to_version >= 5:
            self._migration_v5_add_error_category(cursor)

        if from_version <= 5 and to_version >= 6:
            self._migration_v6_add_screenshot_path(cursor)

        if from_version <= 6 and to_version >= 7:
            self._migration_v7_add_files_table(cursor)

        if from_version <= 7 and to_version >= 8:
            self._migration_v8_add_users_table(cursor)

        if from_version <= 8 and to_version >= 9:
            self._migration_v9_add_session_uuid(cursor)

        if from_version <= 9 and to_version >= 10:
            self._migration_v10_add_token_columns(cursor)

        if from_version <= 10 and to_version >= 11:
            self._migration_v11_add_phase_tracking(cursor)

        if from_version <= 12 and to_version >= 13:
            self._migration_v13_add_documents_table(cursor)

    def _migration_v1_initial_schema(self, cursor):
        """Migration v1: Create initial database schema with tasks, tool_usage, and agent_status tables"""
        logger.info("Creating initial schema...")

        # Tasks table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                task_id TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                description TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                model TEXT NOT NULL,
                workspace TEXT NOT NULL,
                agent_type TEXT NOT NULL DEFAULT 'code_agent',
                result TEXT,
                error TEXT,
                pid INTEGER,
                activity_log TEXT,  -- JSON array
                session_uuid TEXT  -- Claude Code session UUID (for tool_usage correlation)
            )
        """
        )

        # Tool usage table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS tool_usage (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                task_id TEXT NOT NULL,
                tool_name TEXT NOT NULL,
                duration_ms REAL,
                success BOOLEAN,
                error TEXT,
                parameters TEXT  -- JSON blob
            )
        """
        )

        # Agent status table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS agent_status (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                task_id TEXT NOT NULL,
                status TEXT NOT NULL,
                message TEXT,
                metadata TEXT  -- JSON blob
            )
        """
        )

        # Create indices for tasks table
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_tasks_user_status ON tasks(user_id, status, created_at DESC)"
        )
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_tasks_created ON tasks(created_at DESC)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status)")

        # Create indices for tool_usage table
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_tool_timestamp ON tool_usage(timestamp DESC)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_tool_task ON tool_usage(task_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_tool_name ON tool_usage(tool_name)")

        # Create indices for agent_status table
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_status_timestamp ON agent_status(timestamp DESC)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_status_task ON agent_status(task_id)")

        logger.info("Initial schema created successfully")

    def _migration_v2_add_games(self, cursor):
        """Migration v2: Add games table for game state tracking"""
        logger.info("Adding games schema...")

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS games (
                game_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                game_type TEXT NOT NULL,
                status TEXT NOT NULL,
                score INTEGER DEFAULT 0,
                level INTEGER DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                state_data TEXT  -- JSON blob with game state
            )
        """
        )

        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_games_user_status ON games(user_id, status, updated_at DESC)"
        )
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_games_user_type ON games(user_id, game_type)")

        logger.info("Games schema created successfully")

    def _migration_v3_add_workflow_column(self, cursor):
        """Migration v3: Add workflow column to tasks table"""
        logger.info("Adding workflow column to tasks table...")

        cursor.execute("PRAGMA table_info(tasks)")
        columns = [col[1] for col in cursor.fetchall()]

        if "workflow" not in columns:
            cursor.execute("ALTER TABLE tasks ADD COLUMN workflow TEXT")
            logger.info("Workflow column added successfully")
        else:
            logger.info("Workflow column already exists, skipping")

    def _migration_v4_add_context_column(self, cursor):
        """Migration v4: Add context column to tasks table"""
        logger.info("Adding context column to tasks table...")

        cursor.execute("PRAGMA table_info(tasks)")
        columns = [col[1] for col in cursor.fetchall()]

        if "context" not in columns:
            cursor.execute("ALTER TABLE tasks ADD COLUMN context TEXT")
            logger.info("Context column added successfully")
        else:
            logger.info("Context column already exists, skipping")

    def _migration_v5_add_error_category(self, cursor):
        """Migration v5: Add error_category column to tool_usage table"""
        logger.info("Adding error_category column to tool_usage table...")

        cursor.execute("PRAGMA table_info(tool_usage)")
        columns = [col[1] for col in cursor.fetchall()]

        if "error_category" not in columns:
            cursor.execute("ALTER TABLE tool_usage ADD COLUMN error_category TEXT")
            logger.info("Error_category column added successfully")
        else:
            logger.info("Error_category column already exists, skipping")

    def _migration_v6_add_screenshot_path(self, cursor):
        """Migration v6: Add screenshot_path column to tool_usage table"""
        logger.info("Adding screenshot_path column to tool_usage table...")

        cursor.execute("PRAGMA table_info(tool_usage)")
        columns = [col[1] for col in cursor.fetchall()]

        if "screenshot_path" not in columns:
            cursor.execute("ALTER TABLE tool_usage ADD COLUMN screenshot_path TEXT")
            logger.info("Screenshot_path column added successfully")
        else:
            logger.info("Screenshot_path column already exists, skipping")

    def _migration_v7_add_files_table(self, cursor):
        """Migration v7: Add files table for file access tracking"""
        logger.info("Creating files table...")

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS files (
                file_path TEXT PRIMARY KEY,
                first_seen TEXT NOT NULL,
                last_accessed TEXT NOT NULL,
                access_count INTEGER NOT NULL DEFAULT 0,
                task_ids TEXT,  -- JSON array
                operations TEXT,  -- JSON object with read/write/edit counts
                file_size INTEGER,
                file_hash TEXT
            )
        """
        )

        cursor.execute("CREATE INDEX IF NOT EXISTS idx_files_last_accessed ON files(last_accessed DESC)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_files_access_count ON files(access_count DESC)")

        logger.info("Files table created successfully")

    def _migration_v8_add_users_table(self, cursor):
        """Migration v8: Add users table for web chat authentication"""
        logger.info("Creating users table...")

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL,
                is_admin BOOLEAN NOT NULL DEFAULT 0
            )
        """
        )

        cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)")

        logger.info("Users table created successfully")

    def _migration_v9_add_session_uuid(self, cursor):
        """Migration v9: Add session_uuid column to tasks table for tool usage correlation"""
        logger.info("Adding session_uuid column to tasks table...")

        cursor.execute("PRAGMA table_info(tasks)")
        columns = [col[1] for col in cursor.fetchall()]

        if "session_uuid" not in columns:
            cursor.execute("ALTER TABLE tasks ADD COLUMN session_uuid TEXT")
            logger.info("Session_uuid column added successfully")
        else:
            logger.info("Session_uuid column already exists, skipping")

    def _migration_v10_add_token_columns(self, cursor):
        """Migration v10: Add token usage columns to tool_usage table"""
        logger.info("Adding token usage columns to tool_usage table...")

        cursor.execute("PRAGMA table_info(tool_usage)")
        columns = [col[1] for col in cursor.fetchall()]

        token_columns = {
            "input_tokens": "INTEGER",
            "output_tokens": "INTEGER",
            "cache_creation_tokens": "INTEGER",
            "cache_read_tokens": "INTEGER",
        }

        for col_name, col_type in token_columns.items():
            if col_name not in columns:
                cursor.execute(f"ALTER TABLE tool_usage ADD COLUMN {col_name} {col_type}")  # nosec B608
                logger.info(f"{col_name} column added successfully")
            else:
                logger.info(f"{col_name} column already exists, skipping")

    def _migration_v11_add_phase_tracking(self, cursor):
        """Migration v11: Add phase tracking columns to tasks table"""
        logger.info("Adding phase tracking columns to tasks table...")

        cursor.execute("PRAGMA table_info(tasks)")
        columns = [col[1] for col in cursor.fetchall()]

        if "current_phase" not in columns:
            cursor.execute("ALTER TABLE tasks ADD COLUMN current_phase TEXT")
            logger.info("current_phase column added successfully")
        else:
            logger.info("current_phase column already exists, skipping")

        if "phase_number" not in columns:
            cursor.execute("ALTER TABLE tasks ADD COLUMN phase_number INTEGER DEFAULT 0")
            logger.info("phase_number column added successfully")
        else:
            logger.info("phase_number column already exists, skipping")

    def _migration_v13_add_documents_table(self, cursor):
        """Migration v13: Add documents table for tracking documentation status"""
        logger.info("Creating documents table...")

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                path TEXT NOT NULL UNIQUE,
                status TEXT NOT NULL DEFAULT 'active',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                archived_at TEXT,
                task_id TEXT,
                notes TEXT,
                FOREIGN KEY (task_id) REFERENCES tasks(task_id)
            )
        """
        )

        cursor.execute("CREATE INDEX IF NOT EXISTS idx_documents_status ON documents(status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_documents_path ON documents(path)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_documents_task_id ON documents(task_id)")

        logger.info("Documents table created successfully")

    # ========== TASK OPERATIONS ==========

    async def create_task(
        self,
        task_id: str,
        user_id: int,
        description: str,
        workspace: str,
        model: str = "sonnet",
        agent_type: str = "code_agent",
        workflow: str | None = None,
        context: str | None = None,
    ) -> dict:
        """Create a new task"""
        now = datetime.now().isoformat()

        async with self._write_lock:
            cursor = self.conn.cursor()
            cursor.execute(
                """
                INSERT INTO tasks (
                    task_id, user_id, description, status, created_at, updated_at,
                    model, workspace, agent_type, workflow, context, activity_log
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    task_id,
                    user_id,
                    description,
                    "pending",
                    now,
                    now,
                    model,
                    workspace,
                    agent_type,
                    workflow,
                    context,
                    "[]",
                ),
            )
            self.conn.commit()

        logger.info(f"Created task {task_id} for user {user_id}")
        return self.get_task(task_id)

    def get_task(self, task_id: str) -> dict | None:
        """Get task by ID"""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,))
        row = cursor.fetchone()

        if not row:
            return None

        return self._row_to_task_dict(row)

    async def update_task(
        self,
        task_id: str,
        status: str | None = None,
        result: str | None = None,
        error: str | None = None,
        pid: int | None = None,
        workflow: str | None = None,
        session_uuid: str | None = None,
    ) -> bool:
        """Update task fields"""
        updates = []
        params = []

        if status is not None:
            updates.append("status = ?")
            params.append(status)
        if result is not None:
            updates.append("result = ?")
            params.append(result)
        if error is not None:
            updates.append("error = ?")
            params.append(error)
        if pid is not None:
            updates.append("pid = ?")
            params.append(pid)
        if session_uuid is not None:
            updates.append("session_uuid = ?")
            params.append(session_uuid)
        if workflow is not None:
            updates.append("workflow = ?")
            params.append(workflow)

        if not updates:
            return False

        updates.append("updated_at = ?")
        params.append(datetime.now().isoformat())
        params.append(task_id)

        async with self._write_lock:
            cursor = self.conn.cursor()
            cursor.execute(f"UPDATE tasks SET {', '.join(updates)} WHERE task_id = ?", params)  # nosec B608
            self.conn.commit()
            rowcount = cursor.rowcount

        logger.info(f"Updated task {task_id}: {', '.join(updates)}")
        return rowcount > 0

    async def update_task_phase(self, task_id: str, subagent_type: str, phase_num: int) -> bool:
        """
        Update task phase information (used for tracking workflow progress).

        This method is called from post-tool-use hook when Task tool is invoked,
        allowing us to track which subagent is currently active and what phase
        the task is in (e.g., "code_agent - phase 2/4").

        Args:
            task_id: Task ID to update
            subagent_type: Type of subagent being invoked (e.g., "code_agent", "git-merge")
            phase_num: Phase number (1-indexed, incremented on each Task tool call)

        Returns:
            True if task was updated, False if task not found
        """
        async with self._write_lock:
            cursor = self.conn.cursor()
            cursor.execute(
                """
                UPDATE tasks
                SET current_phase = ?, phase_number = ?, updated_at = ?
                WHERE task_id = ?
            """,
                (subagent_type, phase_num, datetime.now().isoformat(), task_id),
            )
            self.conn.commit()
            rowcount = cursor.rowcount

        if rowcount > 0:
            logger.debug(f"Updated task {task_id} phase: {subagent_type} (phase {phase_num})")
        else:
            logger.warning(f"Failed to update phase for task {task_id} - task not found")

        return rowcount > 0

    async def add_activity(self, task_id: str, message: str, output_lines: int | None = None) -> bool:
        """Add activity entry to task log"""
        async with self._write_lock:
            cursor = self.conn.cursor()
            cursor.execute("SELECT activity_log FROM tasks WHERE task_id = ?", (task_id,))
            row = cursor.fetchone()

            if not row:
                logger.error(f"Task {task_id} not found", exc_info=True)
                return False

            # Parse existing log
            activity_log = json.loads(row[0]) if row[0] else []

            # Add new entry
            entry = {
                "timestamp": datetime.now().isoformat(),
                "message": message,
            }
            if output_lines is not None:
                entry["output_lines"] = output_lines

            activity_log.append(entry)

            # Update task
            cursor.execute(
                "UPDATE tasks SET activity_log = ?, updated_at = ? WHERE task_id = ?",
                (json.dumps(activity_log), datetime.now().isoformat(), task_id),
            )
            self.conn.commit()

        logger.debug(f"Added activity to task {task_id}: {message}")
        return True

    def get_user_tasks(self, user_id: int, status: str | None = None, limit: int = 10) -> list[dict]:
        """Get tasks for a user"""
        cursor = self.conn.cursor()

        if status:
            cursor.execute(
                """
                SELECT * FROM tasks
                WHERE user_id = ? AND status = ?
                ORDER BY created_at DESC
                LIMIT ?
            """,
                (user_id, status, limit),
            )
        else:
            cursor.execute(
                """
                SELECT * FROM tasks
                WHERE user_id = ?
                ORDER BY created_at DESC
                LIMIT ?
            """,
                (user_id, limit),
            )

        return [self._row_to_task_dict(row) for row in cursor.fetchall()]

    def get_active_tasks(self, user_id: int) -> list[dict]:
        """Get active (pending/running) tasks for user"""
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT * FROM tasks
            WHERE user_id = ? AND status IN ('pending', 'running')
            ORDER BY created_at DESC
        """,
            (user_id,),
        )

        return [self._row_to_task_dict(row) for row in cursor.fetchall()]

    def get_failed_tasks(self, user_id: int, limit: int = 10) -> list[dict]:
        """Get failed tasks for a user"""
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT * FROM tasks
            WHERE user_id = ? AND status = 'failed'
            ORDER BY created_at DESC
            LIMIT ?
        """,
            (user_id, limit),
        )

        return [self._row_to_task_dict(row) for row in cursor.fetchall()]

    def get_stopped_tasks(self, user_id: int | None = None, limit: int = 100) -> list[dict]:
        """Get stopped tasks, optionally filtered by user"""
        cursor = self.conn.cursor()

        if user_id is not None:
            cursor.execute(
                """
                SELECT * FROM tasks
                WHERE user_id = ? AND status = 'stopped'
                ORDER BY created_at DESC
                LIMIT ?
            """,
                (user_id, limit),
            )
        else:
            cursor.execute(
                """
                SELECT * FROM tasks
                WHERE status = 'stopped'
                ORDER BY created_at DESC
                LIMIT ?
            """,
                (limit,),
            )

        return [self._row_to_task_dict(row) for row in cursor.fetchall()]

    def get_interrupted_tasks(self) -> list[dict]:
        """
        Get tasks interrupted by bot restart or shutdown.
        Returns tasks with 'stopped' status that have specific error messages.
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT task_id, user_id, description, error, created_at
            FROM tasks
            WHERE status = 'stopped'
            AND (error = 'Task stopped due to bot restart' OR error = 'Task stopped during bot shutdown')
            ORDER BY user_id, created_at DESC
        """
        )

        return [
            {
                "task_id": row[0],
                "user_id": row[1],
                "description": row[2],
                "error": row[3],
                "created_at": row[4],
            }
            for row in cursor.fetchall()
        ]

    def delete_task(self, task_id: str) -> bool:
        """Delete a task"""
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM tasks WHERE task_id = ?", (task_id,))
        self.conn.commit()

        return cursor.rowcount > 0

    def clear_old_failed_tasks(self, user_id: int, older_than_hours: int = 24) -> int:
        """Clear old failed tasks for a user"""
        cutoff_time = (datetime.now() - timedelta(hours=older_than_hours)).isoformat()

        cursor = self.conn.cursor()
        cursor.execute(
            """
            DELETE FROM tasks
            WHERE user_id = ? AND status = 'failed' AND created_at < ?
        """,
            (user_id, cutoff_time),
        )
        self.conn.commit()

        deleted_count = cursor.rowcount
        if deleted_count > 0:
            logger.info(f"Cleared {deleted_count} old failed tasks for user {user_id}")

        return deleted_count

    def cleanup_stale_pending_tasks(self, max_age_hours: int = 1) -> int:
        """Mark stale pending tasks as failed"""
        cutoff_time = (datetime.now() - timedelta(hours=max_age_hours)).isoformat()
        now = datetime.now().isoformat()

        cursor = self.conn.cursor()
        cursor.execute(
            """
            UPDATE tasks
            SET status = 'failed',
                error = ?,
                updated_at = ?
            WHERE status = 'pending' AND created_at < ?
        """,
            (f"Task was pending for more than {max_age_hours}h without being picked up by worker", now, cutoff_time),
        )
        self.conn.commit()

        updated_count = cursor.rowcount
        if updated_count > 0:
            logger.info(f"Cleaned up {updated_count} stale pending tasks")

        return updated_count

    def mark_all_running_as_stopped(self) -> int:
        """
        Mark all running tasks as stopped during shutdown.
        Also adds activity log entries for tracking.
        """
        now = datetime.now().isoformat()

        cursor = self.conn.cursor()

        # First, get task IDs and their activity logs
        cursor.execute("SELECT task_id, activity_log FROM tasks WHERE status = 'running'")
        running_tasks = cursor.fetchall()

        # Update each task's status and activity log
        for task_id, activity_log_json in running_tasks:
            # Parse existing activity log
            activity_log = json.loads(activity_log_json) if activity_log_json else []

            # Add shutdown entry
            activity_log.append(
                {
                    "timestamp": now,
                    "message": "Task stopped during bot shutdown - will notify user on restart",
                }
            )

            # Update task
            cursor.execute(
                """
                UPDATE tasks
                SET status = 'stopped',
                    error = 'Task stopped during bot shutdown',
                    updated_at = ?,
                    activity_log = ?
                WHERE task_id = ?
            """,
                (now, json.dumps(activity_log), task_id),
            )

        self.conn.commit()

        stopped_count = len(running_tasks)
        if stopped_count > 0:
            logger.info(f"Marked {stopped_count} tasks as stopped during shutdown")

        return stopped_count

    def get_task_statistics(self) -> dict:
        """Get task statistics"""
        cursor = self.conn.cursor()

        # Count by status
        cursor.execute(
            """
            SELECT status, COUNT(*) as count
            FROM tasks
            GROUP BY status
        """
        )
        by_status = {row[0]: row[1] for row in cursor.fetchall()}

        # Total tasks
        cursor.execute("SELECT COUNT(*) FROM tasks")
        total = cursor.fetchone()[0]

        # Tasks in last 24 hours
        cutoff = (datetime.now() - timedelta(hours=24)).isoformat()
        cursor.execute("SELECT COUNT(*) FROM tasks WHERE created_at >= ?", (cutoff,))
        recent_24h = cursor.fetchone()[0]

        # Calculate success rate
        completed = by_status.get("completed", 0)
        failed = by_status.get("failed", 0)
        success_rate = (completed / (completed + failed) * 100) if (completed + failed) > 0 else 0

        return {
            "total": total,
            "by_status": by_status,
            "recent_24h": recent_24h,
            "success_rate": success_rate,
        }

    # ========== TOOL USAGE OPERATIONS ==========

    def record_tool_usage(
        self,
        task_id: str,
        tool_name: str,
        duration_ms: float | None = None,
        success: bool | None = None,
        error: str | None = None,
        parameters: dict | None = None,
        error_category: str | None = None,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        cache_creation_tokens: int | None = None,
        cache_read_tokens: int | None = None,
    ):
        """Record tool usage with optional token tracking"""
        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT INTO tool_usage (
                timestamp, task_id, tool_name, duration_ms, success, error, parameters, error_category,
                input_tokens, output_tokens, cache_creation_tokens, cache_read_tokens
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                datetime.now().isoformat(),
                task_id,
                tool_name,
                duration_ms,
                success,
                error,
                json.dumps(parameters) if parameters else None,
                error_category,
                input_tokens,
                output_tokens,
                cache_creation_tokens,
                cache_read_tokens,
            ),
        )
        self.conn.commit()

        logger.debug(f"Recorded tool usage: {task_id} - {tool_name}")

    def update_tool_usage(
        self,
        task_id: str,
        tool_name: str,
        success: bool,
        error: str | None = None,
        error_category: str | None = None,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        cache_creation_tokens: int | None = None,
        cache_read_tokens: int | None = None,
        parameters: dict | None = None,
    ) -> bool:
        """
        Update the most recent in-progress tool usage record with completion data.

        Finds the most recent record for task_id + tool_name + parameters where success IS NULL
        and updates it with completion data from post-tool-use hook.

        Args:
            parameters: Tool parameters used to match the specific tool invocation

        Returns:
            bool: True if record was updated, False if no matching record found
        """
        import hashlib
        cursor = self.conn.cursor()

        # Find most recent in-progress record for this task + tool + parameters
        # Use timestamp proximity (within 5 seconds) to handle concurrent calls
        if parameters:
            # Extract distinguishing parameter for matching
            if tool_name in ('Read', 'Write', 'Edit'):
                param_key = parameters.get('file_path', '')
            elif tool_name == 'Bash':
                cmd = parameters.get('command', '')
                param_key = hashlib.md5(cmd.encode()).hexdigest()[:8]
            elif tool_name in ('Grep', 'Glob'):
                param_key = parameters.get('pattern', '')[:50]
            else:
                param_key = hashlib.md5(json.dumps(parameters, sort_keys=True).encode()).hexdigest()[:8]

            # Find matching in-progress record by parameters
            cursor.execute(
                """
                SELECT id, parameters FROM tool_usage
                WHERE task_id = ? AND tool_name = ? AND success IS NULL
                AND timestamp >= datetime('now', '-5 seconds')
                ORDER BY timestamp DESC
                """,
                (task_id, tool_name)
            )

            # Find first record with matching parameters
            record_id = None
            for row in cursor.fetchall():
                stored_params_json = row[1]
                if stored_params_json:
                    try:
                        stored_params = json.loads(stored_params_json)
                        # Extract same key from stored params
                        if tool_name in ('Read', 'Write', 'Edit'):
                            stored_key = stored_params.get('file_path', '')
                        elif tool_name == 'Bash':
                            cmd = stored_params.get('command', '')
                            stored_key = hashlib.md5(cmd.encode()).hexdigest()[:8]
                        elif tool_name in ('Grep', 'Glob'):
                            stored_key = stored_params.get('pattern', '')[:50]
                        else:
                            stored_key = hashlib.md5(json.dumps(stored_params, sort_keys=True).encode()).hexdigest()[:8]

                        if stored_key == param_key:
                            record_id = row[0]
                            break
                    except (json.JSONDecodeError, TypeError):
                        continue
        else:
            # No parameters provided, fall back to most recent
            cursor.execute(
                """
                SELECT id FROM tool_usage
                WHERE task_id = ? AND tool_name = ? AND success IS NULL
                ORDER BY timestamp DESC
                LIMIT 1
                """,
                (task_id, tool_name)
            )
            row = cursor.fetchone()
            record_id = row[0] if row else None

        if not record_id:
            logger.warning(f"No matching in-progress tool usage record found for {task_id} - {tool_name}")
            return False

        # Update the record with completion data
        cursor.execute(
            """
            UPDATE tool_usage
            SET success = ?, error = ?, error_category = ?,
                input_tokens = ?, output_tokens = ?,
                cache_creation_tokens = ?, cache_read_tokens = ?
            WHERE id = ?
            """,
            (
                success,
                error,
                error_category,
                input_tokens,
                output_tokens,
                cache_creation_tokens,
                cache_read_tokens,
                record_id,
            )
        )
        self.conn.commit()

        logger.debug(f"Updated tool usage: {task_id} - {tool_name} (id={record_id})")
        return True

    def get_tool_statistics(self, task_id: str | None = None, hours: int = 24) -> dict[str, Any]:
        """Get tool usage statistics"""
        cutoff_time = (datetime.now() - timedelta(hours=hours)).isoformat()

        cursor = self.conn.cursor()

        # Filter by time and optionally task_id
        if task_id:
            cursor.execute(
                """
                SELECT tool_name, duration_ms, success
                FROM tool_usage
                WHERE task_id = ? AND timestamp >= ?
            """,
                (task_id, cutoff_time),
            )
        else:
            cursor.execute(
                """
                SELECT tool_name, duration_ms, success
                FROM tool_usage
                WHERE timestamp >= ?
            """,
                (cutoff_time,),
            )

        rows = cursor.fetchall()

        if not rows:
            return {
                "total_calls": 0,
                "time_window_hours": hours,
                "tools": {},
            }

        # Aggregate by tool
        tool_stats = {}
        for row in rows:
            tool_name, duration_ms, success = row

            if tool_name not in tool_stats:
                tool_stats[tool_name] = {
                    "count": 0,
                    "successes": 0,
                    "failures": 0,
                    "total_duration_ms": 0.0,
                    "min_duration_ms": float("inf"),
                    "max_duration_ms": 0.0,
                }

            stats = tool_stats[tool_name]
            stats["count"] += 1

            if success is True:
                stats["successes"] += 1
            elif success is False:
                stats["failures"] += 1

            if duration_ms is not None:
                stats["total_duration_ms"] += duration_ms
                stats["min_duration_ms"] = min(stats["min_duration_ms"], duration_ms)
                stats["max_duration_ms"] = max(stats["max_duration_ms"], duration_ms)

        # Calculate averages and success rates
        for _tool, stats in tool_stats.items():
            if stats["count"] > 0:
                if stats["total_duration_ms"] > 0:
                    stats["avg_duration_ms"] = stats["total_duration_ms"] / stats["count"]
                else:
                    stats["avg_duration_ms"] = 0.0
                stats["success_rate"] = stats["successes"] / stats["count"] if stats["count"] > 0 else 0.0

        return {
            "total_calls": len(rows),
            "time_window_hours": hours,
            "tools": tool_stats,
        }

    def get_task_timeline(self, task_id: str) -> list[dict]:
        """Get complete timeline of events for a task"""
        cursor = self.conn.cursor()

        events = []

        # Get tool usage events
        cursor.execute(
            """
            SELECT timestamp, tool_name, duration_ms, success, error
            FROM tool_usage
            WHERE task_id = ?
            ORDER BY timestamp ASC, id ASC
        """,
            (task_id,),
        )

        for row in cursor.fetchall():
            events.append(
                {
                    "timestamp": row[0],
                    "type": "tool_usage",
                    "tool_name": row[1],
                    "duration_ms": row[2],
                    "success": row[3],
                    "error": row[4],
                }
            )

        # Get status change events
        cursor.execute(
            """
            SELECT timestamp, status, message
            FROM agent_status
            WHERE task_id = ?
            ORDER BY timestamp ASC, id ASC
        """,
            (task_id,),
        )

        for row in cursor.fetchall():
            events.append(
                {
                    "timestamp": row[0],
                    "type": "status_change",
                    "status": row[1],
                    "message": row[2],
                }
            )

        # Sort by timestamp
        events.sort(key=lambda e: e["timestamp"])

        return events

    def get_tool_usage_by_session(self, session_id: str) -> list[dict]:
        """
        Get tool usage records for a specific session/task.
        Session ID is stored as task_id in the database.

        Deduplicates pre-hook (success=NULL) and post-hook (success=True/False) records
        by keeping only the latest completed version of each tool call.

        Args:
            session_id: Session ID (same as task_id in tool_usage table)

        Returns:
            List of deduplicated tool usage records with tool, timestamp, duration, error fields
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT tool_name, timestamp, duration_ms, error, success, parameters, error_category, id
            FROM tool_usage
            WHERE task_id = ?
            ORDER BY timestamp ASC, id ASC
        """,
            (session_id,),
        )

        # Group by (tool_name, timestamp_second, parameters) to find duplicates
        # Keep completed record (success != NULL) or most recent if all NULL
        from collections import defaultdict
        import hashlib
        records_by_key = defaultdict(list)

        for row in cursor.fetchall():
            tool_name = row[0]
            timestamp = row[1]
            duration_ms = row[2]
            error = row[3]
            success = row[4]
            parameters_json = row[5]
            error_category = row[6]
            record_id = row[7]

            # Parse parameters to extract distinguishing info
            try:
                params = json.loads(parameters_json) if parameters_json else {}
            except json.JSONDecodeError:
                params = {}

            # Create distinguishing key based on tool type and parameters
            # This ensures we only group pre/post hooks of the SAME tool invocation
            if tool_name in ('Read', 'Write', 'Edit'):
                # File tools: use file_path
                param_key = params.get('file_path', '')
            elif tool_name == 'Bash':
                # Bash: use command hash (commands can be long)
                cmd = params.get('command', '')
                param_key = hashlib.md5(cmd.encode()).hexdigest()[:8]
            elif tool_name in ('Grep', 'Glob'):
                # Search tools: use pattern
                param_key = params.get('pattern', '')[:50]
            else:
                # Other tools: hash all parameters
                param_key = hashlib.md5(json.dumps(params, sort_keys=True).encode()).hexdigest()[:8]

            # Group by tool_name + timestamp (second precision) + parameter key
            key = (tool_name, timestamp[:19], param_key)
            records_by_key[key].append({
                'id': record_id,
                'tool_name': tool_name,
                'timestamp': timestamp,
                'duration_ms': duration_ms,
                'error': error,
                'success': success,
                'parameters_json': parameters_json,
                'error_category': error_category,
            })

        # Deduplicate: prefer completed (success != NULL) over in-progress (success == NULL)
        result = []
        for key, records in sorted(records_by_key.items()):
            completed = [r for r in records if r['success'] is not None]
            selected = completed[-1] if completed else records[-1]

            result.append({
                "tool": selected['tool_name'],
                "timestamp": selected['timestamp'],
                "duration": selected['duration_ms'],
                "error": selected['error'],
                "success": selected['success'],
                "parameters": json.loads(selected['parameters_json']) if selected['parameters_json'] else None,
                "error_category": selected['error_category'],
            })

        return result

    def cleanup_old_tool_usage(self, days: int = 30) -> int:
        """Delete tool usage records older than specified days"""
        cutoff_time = (datetime.now() - timedelta(days=days)).isoformat()

        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM tool_usage WHERE timestamp < ?", (cutoff_time,))
        self.conn.commit()

        deleted_count = cursor.rowcount
        if deleted_count > 0:
            logger.info(f"Deleted {deleted_count} old tool usage records")

        return deleted_count

    # ========== AGENT STATUS OPERATIONS ==========

    def record_agent_status(
        self,
        task_id: str,
        status: str,
        message: str | None = None,
        metadata: dict | None = None,
    ):
        """Record agent status change"""
        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT INTO agent_status (timestamp, task_id, status, message, metadata)
            VALUES (?, ?, ?, ?, ?)
        """,
            (
                datetime.now().isoformat(),
                task_id,
                status,
                message,
                json.dumps(metadata) if metadata else None,
            ),
        )
        self.conn.commit()

        logger.debug(f"Recorded status change: {task_id} - {status}")

    def get_agent_status_summary(self, task_id: str | None = None) -> dict[str, Any]:
        """Get summary of agent status changes"""
        cursor = self.conn.cursor()

        if task_id:
            cursor.execute(
                """
                SELECT status, timestamp, task_id, message
                FROM agent_status
                WHERE task_id = ?
                ORDER BY timestamp DESC
            """,
                (task_id,),
            )
        else:
            cursor.execute(
                """
                SELECT status, timestamp, task_id, message
                FROM agent_status
                ORDER BY timestamp DESC
            """
            )

        rows = cursor.fetchall()

        if not rows:
            return {
                "total_status_changes": 0,
                "by_status": {},
                "recent_changes": [],
            }

        # Aggregate by status
        status_counts = {}
        for row in rows:
            status = row[0]
            status_counts[status] = status_counts.get(status, 0) + 1

        # Get recent changes (last 10)
        recent_changes = [
            {
                "timestamp": row[1],
                "task_id": row[2],
                "status": row[0],
                "message": row[3],
            }
            for row in rows[:10]
        ]

        return {
            "total_status_changes": len(rows),
            "by_status": status_counts,
            "recent_changes": recent_changes,
        }

    def cleanup_old_agent_status(self, days: int = 30) -> int:
        """Delete agent status records older than specified days"""
        cutoff_time = (datetime.now() - timedelta(days=days)).isoformat()

        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM agent_status WHERE timestamp < ?", (cutoff_time,))
        self.conn.commit()

        deleted_count = cursor.rowcount
        if deleted_count > 0:
            logger.info(f"Deleted {deleted_count} old agent status records")

        return deleted_count

    # ========== FILE INDEXING OPERATIONS ==========

    async def record_file_access(
        self, file_path: str, task_id: str, operation: str, file_size: int | None = None, file_hash: str | None = None
    ):
        """
        Record file access in the files index

        Args:
            file_path: Absolute path to the file
            task_id: Task ID that accessed the file
            operation: Operation type ('read', 'write', 'edit')
            file_size: File size in bytes (optional)
            file_hash: File hash for integrity checking (optional)
        """
        now = datetime.now().isoformat()

        async with self._write_lock:
            cursor = self.conn.cursor()

            # Check if file already exists
            cursor.execute(
                "SELECT file_path, task_ids, operations, access_count FROM files WHERE file_path = ?", (file_path,)
            )
            row = cursor.fetchone()

            if row:
                # Update existing record
                task_ids = json.loads(row[1]) if row[1] else []
                operations = json.loads(row[2]) if row[2] else {"read": 0, "write": 0, "edit": 0}
                access_count = row[3]

                # Add task_id if not already present
                if task_id not in task_ids:
                    task_ids.append(task_id)

                # Increment operation count
                operation_lower = operation.lower()
                if operation_lower in operations:
                    operations[operation_lower] += 1
                else:
                    operations[operation_lower] = 1

                # Increment access count
                access_count += 1

                # Update record
                cursor.execute(
                    """
                    UPDATE files
                    SET last_accessed = ?, access_count = ?, task_ids = ?, operations = ?,
                        file_size = COALESCE(?, file_size), file_hash = COALESCE(?, file_hash)
                    WHERE file_path = ?
                """,
                    (now, access_count, json.dumps(task_ids), json.dumps(operations), file_size, file_hash, file_path),
                )
            else:
                # Create new record
                task_ids = [task_id]
                operations = {"read": 0, "write": 0, "edit": 0}
                operation_lower = operation.lower()
                if operation_lower in operations:
                    operations[operation_lower] = 1
                else:
                    operations[operation_lower] = 1

                cursor.execute(
                    """
                    INSERT INTO files (file_path, first_seen, last_accessed, access_count, task_ids, operations, file_size, file_hash)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    (file_path, now, now, 1, json.dumps(task_ids), json.dumps(operations), file_size, file_hash),
                )

            self.conn.commit()

        logger.debug(f"Recorded file access: {file_path} - {operation} by task {task_id}")

    def get_file_info(self, file_path: str) -> dict | None:
        """
        Get file metadata from index

        Args:
            file_path: Absolute path to the file

        Returns:
            Dictionary with file metadata or None if not found
        """
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM files WHERE file_path = ?", (file_path,))
        row = cursor.fetchone()

        if not row:
            return None

        return {
            "file_path": row[0],
            "first_seen": row[1],
            "last_accessed": row[2],
            "access_count": row[3],
            "task_ids": json.loads(row[4]) if row[4] else [],
            "operations": json.loads(row[5]) if row[5] else {},
            "file_size": row[6],
            "file_hash": row[7],
        }

    def get_frequently_accessed_files(self, limit: int = 50) -> list[dict]:
        """
        Get most frequently accessed files

        Args:
            limit: Maximum number of files to return

        Returns:
            List of file metadata dictionaries sorted by access count
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT file_path, first_seen, last_accessed, access_count, task_ids, operations, file_size, file_hash
            FROM files
            ORDER BY access_count DESC, last_accessed DESC
            LIMIT ?
        """,
            (limit,),
        )

        return [
            {
                "file_path": row[0],
                "first_seen": row[1],
                "last_accessed": row[2],
                "access_count": row[3],
                "task_ids": json.loads(row[4]) if row[4] else [],
                "operations": json.loads(row[5]) if row[5] else {},
                "file_size": row[6],
                "file_hash": row[7],
            }
            for row in cursor.fetchall()
        ]

    def get_task_files(self, task_id: str) -> list[dict]:
        """
        Get all files accessed by a task

        Args:
            task_id: Task ID

        Returns:
            List of file metadata dictionaries
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT file_path, first_seen, last_accessed, access_count, task_ids, operations, file_size, file_hash
            FROM files
        """
        )

        # Filter by task_id in JSON array
        results = []
        for row in cursor.fetchall():
            task_ids = json.loads(row[4]) if row[4] else []
            if task_id in task_ids:
                results.append(
                    {
                        "file_path": row[0],
                        "first_seen": row[1],
                        "last_accessed": row[2],
                        "access_count": row[3],
                        "task_ids": task_ids,
                        "operations": json.loads(row[5]) if row[5] else {},
                        "file_size": row[6],
                        "file_hash": row[7],
                    }
                )

        return results

    def cleanup_old_file_records(self, days: int = 90) -> int:
        """
        Delete file records not accessed in specified days

        Args:
            days: Number of days of inactivity before deletion

        Returns:
            Number of records deleted
        """
        cutoff_time = (datetime.now() - timedelta(days=days)).isoformat()

        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM files WHERE last_accessed < ?", (cutoff_time,))
        self.conn.commit()

        deleted_count = cursor.rowcount
        if deleted_count > 0:
            logger.info(f"Deleted {deleted_count} old file records")

        return deleted_count

    def get_file_statistics(self) -> dict[str, Any]:
        """Get file index statistics"""
        cursor = self.conn.cursor()

        # Total files
        cursor.execute("SELECT COUNT(*) FROM files")
        total_files = cursor.fetchone()[0]

        # Total accesses
        cursor.execute("SELECT SUM(access_count) FROM files")
        total_accesses = cursor.fetchone()[0] or 0

        # Files by operation type (most common operation)
        cursor.execute("SELECT operations FROM files")
        operations_by_type = {"read": 0, "write": 0, "edit": 0}
        for row in cursor.fetchall():
            if row[0]:
                ops = json.loads(row[0])
                for op_type, count in ops.items():
                    if op_type in operations_by_type:
                        operations_by_type[op_type] += count

        # Files accessed in last 24 hours
        cutoff = (datetime.now() - timedelta(hours=24)).isoformat()
        cursor.execute("SELECT COUNT(*) FROM files WHERE last_accessed >= ?", (cutoff,))
        recent_24h = cursor.fetchone()[0]

        # Top 10 files by access count
        cursor.execute(
            """
            SELECT file_path, access_count, last_accessed
            FROM files
            ORDER BY access_count DESC
            LIMIT 10
        """
        )
        top_files = [
            {"file_path": row[0], "access_count": row[1], "last_accessed": row[2]} for row in cursor.fetchall()
        ]

        return {
            "total_files": total_files,
            "total_accesses": total_accesses,
            "operations_by_type": operations_by_type,
            "recent_24h": recent_24h,
            "top_files": top_files,
        }

    # ========== USER MANAGEMENT OPERATIONS ==========

    def create_user(self, user_id: str, username: str, email: str, password_hash: str, is_admin: bool = False) -> bool:
        """
        Create a new user.

        Args:
            user_id: Unique user ID (UUID)
            username: Username (must be unique)
            email: Email address (must be unique)
            password_hash: Bcrypt password hash
            is_admin: Whether user has admin privileges

        Returns:
            True if user created successfully, False otherwise
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                """
                INSERT INTO users (user_id, username, email, password_hash, created_at, is_admin)
                VALUES (?, ?, ?, ?, ?, ?)
            """,
                (user_id, username, email, password_hash, datetime.now().isoformat(), is_admin),
            )
            self.conn.commit()
            logger.info(f"Created user: {username}")
            return True
        except sqlite3.IntegrityError as e:
            logger.error(f"Failed to create user {username}: {e}", exc_info=True)
            return False

    def get_user_by_username(self, username: str) -> dict | None:
        """
        Get user by username.

        Args:
            username: Username to search for

        Returns:
            User dictionary or None if not found
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT user_id, username, email, password_hash, created_at, is_admin
            FROM users
            WHERE username = ?
        """,
            (username,),
        )
        row = cursor.fetchone()

        if not row:
            return None

        return {
            "user_id": row[0],
            "username": row[1],
            "email": row[2],
            "password_hash": row[3],
            "created_at": row[4],
            "is_admin": bool(row[5]),
        }

    def get_user_by_id(self, user_id: str) -> dict | None:
        """
        Get user by user_id.

        Args:
            user_id: User ID to search for

        Returns:
            User dictionary or None if not found
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT user_id, username, email, password_hash, created_at, is_admin
            FROM users
            WHERE user_id = ?
        """,
            (user_id,),
        )
        row = cursor.fetchone()

        if not row:
            return None

        return {
            "user_id": row[0],
            "username": row[1],
            "email": row[2],
            "password_hash": row[3],
            "created_at": row[4],
            "is_admin": bool(row[5]),
        }

    def get_user_by_email(self, email: str) -> dict | None:
        """
        Get user by email.

        Args:
            email: Email address to search for

        Returns:
            User dictionary or None if not found
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT user_id, username, email, password_hash, created_at, is_admin
            FROM users
            WHERE email = ?
        """,
            (email,),
        )
        row = cursor.fetchone()

        if not row:
            return None

        return {
            "user_id": row[0],
            "username": row[1],
            "email": row[2],
            "password_hash": row[3],
            "created_at": row[4],
            "is_admin": bool(row[5]),
        }

    def update_user(self, user_id: str, **kwargs) -> bool:
        """
        Update user fields.

        Args:
            user_id: User ID to update
            **kwargs: Fields to update (email, password_hash, is_admin)

        Returns:
            True if user updated successfully, False otherwise
        """
        allowed_fields = {"email", "password_hash", "is_admin"}
        updates = []
        params = []

        for field, value in kwargs.items():
            if field in allowed_fields:
                updates.append(f"{field} = ?")
                params.append(value)

        if not updates:
            return False

        params.append(user_id)

        cursor = self.conn.cursor()
        cursor.execute(f"UPDATE users SET {', '.join(updates)} WHERE user_id = ?", params)  # nosec B608
        self.conn.commit()

        return cursor.rowcount > 0

    def delete_user(self, user_id: str) -> bool:
        """
        Delete a user.

        Args:
            user_id: User ID to delete

        Returns:
            True if user deleted successfully, False otherwise
        """
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
        self.conn.commit()

        return cursor.rowcount > 0

    def get_all_users(self, limit: int = 100) -> list[dict]:
        """
        Get all users.

        Args:
            limit: Maximum number of users to return

        Returns:
            List of user dictionaries
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT user_id, username, email, created_at, is_admin
            FROM users
            ORDER BY created_at DESC
            LIMIT ?
        """,
            (limit,),
        )

        return [
            {
                "user_id": row[0],
                "username": row[1],
                "email": row[2],
                "created_at": row[3],
                "is_admin": bool(row[4]),
            }
            for row in cursor.fetchall()
        ]

    # ========== UTILITY METHODS ==========

    def _row_to_task_dict(self, row: sqlite3.Row) -> dict:
        """Convert SQLite row to task dictionary"""
        return {
            "task_id": row["task_id"],
            "user_id": row["user_id"],
            "description": row["description"],
            "status": row["status"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "model": row["model"],
            "workspace": row["workspace"],
            "agent_type": row["agent_type"],
            "workflow": row["workflow"] if "workflow" in row.keys() else None,
            "context": row["context"] if "context" in row.keys() else None,
            "current_phase": row["current_phase"] if "current_phase" in row.keys() else None,
            "phase_number": row["phase_number"] if "phase_number" in row.keys() else 0,
            "result": row["result"],
            "error": row["error"],
            "pid": row["pid"],
            "activity_log": json.loads(row["activity_log"]) if row["activity_log"] else [],
        }

    def get_database_stats(self) -> dict:
        """Get database statistics"""
        cursor = self.conn.cursor()

        # Count tasks
        cursor.execute("SELECT COUNT(*) FROM tasks")
        task_count = cursor.fetchone()[0]

        # Count tool usage
        cursor.execute("SELECT COUNT(*) FROM tool_usage")
        tool_usage_count = cursor.fetchone()[0]

        # Count agent status
        cursor.execute("SELECT COUNT(*) FROM agent_status")
        agent_status_count = cursor.fetchone()[0]

        # Database file size
        db_size = self.db_path.stat().st_size if self.db_path.exists() else 0

        return {
            "tasks": task_count,
            "tool_usage_records": tool_usage_count,
            "agent_status_records": agent_status_count,
            "database_size_bytes": db_size,
            "database_size_kb": db_size / 1024,
        }

    def vacuum(self):
        """Vacuum database to reclaim space"""
        logger.info("Vacuuming database...")
        self.conn.execute("VACUUM")
        logger.info("Database vacuumed successfully")

    def close(self):
        """Close database connection"""
        self.conn.close()
        logger.info("Database connection closed")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    # ========== GAME OPERATIONS ==========

    def save_game(
        self,
        user_id: int,
        game_type: str,
        state_data: str,
        score: int,
        status: str = "active",
        level: int = 1,
    ) -> int:
        """Save or update game state"""
        now = datetime.now().isoformat()

        cursor = self.conn.cursor()

        # Check if user already has an active game
        cursor.execute(
            """
            SELECT game_id FROM games
            WHERE user_id = ? AND status = 'active'
        """,
            (user_id,),
        )
        row = cursor.fetchone()

        if row:
            # Update existing game
            game_id = row[0]
            cursor.execute(
                """
                UPDATE games
                SET state_data = ?, score = ?, level = ?, status = ?, updated_at = ?
                WHERE game_id = ?
            """,
                (state_data, score, level, status, now, game_id),
            )
        else:
            # Create new game
            cursor.execute(
                """
                INSERT INTO games (user_id, game_type, status, score, level, created_at, updated_at, state_data)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (user_id, game_type, status, score, level, now, now, state_data),
            )
            game_id = cursor.lastrowid

        self.conn.commit()
        logger.debug(f"Saved {game_type} game for user {user_id}, score: {score}")

        return game_id

    def get_active_games(self) -> list[dict]:
        """Get all active games"""
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT game_id, user_id, game_type, score, level, state_data, created_at, updated_at
            FROM games
            WHERE status = 'active'
            ORDER BY updated_at DESC
        """
        )

        return [
            {
                "game_id": row[0],
                "user_id": row[1],
                "game_type": row[2],
                "score": row[3],
                "level": row[4],
                "state_data": row[5],
                "created_at": row[6],
                "updated_at": row[7],
            }
            for row in cursor.fetchall()
        ]

    def end_game(self, user_id: int) -> bool:
        """End active game for user"""
        now = datetime.now().isoformat()

        cursor = self.conn.cursor()
        cursor.execute(
            """
            UPDATE games
            SET status = 'completed', updated_at = ?
            WHERE user_id = ? AND status = 'active'
        """,
            (now, user_id),
        )
        self.conn.commit()

        return cursor.rowcount > 0

    def get_user_game_stats(self, user_id: int) -> dict:
        """Get game statistics for user"""
        cursor = self.conn.cursor()

        # Total games
        cursor.execute(
            "SELECT COUNT(*) FROM games WHERE user_id = ?",
            (user_id,),
        )
        total_games = cursor.fetchone()[0]

        # High score
        cursor.execute(
            "SELECT MAX(score) FROM games WHERE user_id = ?",
            (user_id,),
        )
        high_score = cursor.fetchone()[0] or 0

        # Total score
        cursor.execute(
            "SELECT SUM(score) FROM games WHERE user_id = ?",
            (user_id,),
        )
        total_score = cursor.fetchone()[0] or 0

        # Average score
        avg_score = total_score / total_games if total_games > 0 else 0

        return {
            "total_games": total_games,
            "high_score": high_score,
            "total_score": total_score,
            "avg_score": avg_score,
        }

    def get_leaderboard(self, limit: int = 10) -> list[dict]:
        """Get top scores leaderboard"""
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT user_id, MAX(score) as high_score, COUNT(*) as games_played
            FROM games
            GROUP BY user_id
            ORDER BY high_score DESC
            LIMIT ?
        """,
            (limit,),
        )

        return [
            {
                "user_id": row[0],
                "high_score": row[1],
                "games_played": row[2],
            }
            for row in cursor.fetchall()
        ]

    def cleanup_old_games(self, max_age_hours: int = 24) -> int:
        """Clean up old inactive games"""
        cutoff_time = (datetime.now() - timedelta(hours=max_age_hours)).isoformat()

        cursor = self.conn.cursor()
        cursor.execute(
            """
            DELETE FROM games
            WHERE status = 'active' AND updated_at < ?
        """,
            (cutoff_time,),
        )
        self.conn.commit()

        deleted_count = cursor.rowcount
        if deleted_count > 0:
            logger.info(f"Cleaned up {deleted_count} old games")

        return deleted_count

    # ========== DOCUMENT TRACKING OPERATIONS ==========

    async def create_document(self, path: str, task_id: str | None = None) -> dict:
        """
        Create a new document tracking record.

        Args:
            path: Relative path to document (relative to docs/ directory)
            task_id: Optional task ID that created/owns this document

        Returns:
            Dictionary with document metadata
        """
        now = datetime.now().isoformat()

        async with self._write_lock:
            cursor = self.conn.cursor()

            # Check if document already exists
            cursor.execute("SELECT path FROM documents WHERE path = ?", (path,))
            if cursor.fetchone():
                logger.warning(f"Document already exists: {path}")
                return self.get_document(path)

            # Create new document record
            cursor.execute(
                """
                INSERT INTO documents (path, status, created_at, updated_at, task_id)
                VALUES (?, 'active', ?, ?, ?)
            """,
                (path, now, now, task_id),
            )
            self.conn.commit()

        logger.info(f"Created document record: {path}")
        return self.get_document(path)

    def get_document(self, path: str) -> dict | None:
        """
        Get document metadata by path.

        Args:
            path: Relative path to document

        Returns:
            Dictionary with document metadata or None if not found
        """
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM documents WHERE path = ?", (path,))
        row = cursor.fetchone()

        if not row:
            return None

        return {
            "id": row[0],
            "path": row[1],
            "status": row[2],
            "created_at": row[3],
            "updated_at": row[4],
            "archived_at": row[5],
            "task_id": row[6],
            "notes": row[7],
        }

    def list_documents(self, status: str | None = None) -> list[dict]:
        """
        List all documents, optionally filtered by status.

        Args:
            status: Filter by status ('active', 'archived', 'deleted'). None = all statuses.

        Returns:
            List of document metadata dictionaries
        """
        cursor = self.conn.cursor()

        if status:
            cursor.execute(
                """
                SELECT * FROM documents
                WHERE status = ?
                ORDER BY updated_at DESC
            """,
                (status,),
            )
        else:
            cursor.execute(
                """
                SELECT * FROM documents
                ORDER BY updated_at DESC
            """
            )

        return [
            {
                "id": row[0],
                "path": row[1],
                "status": row[2],
                "created_at": row[3],
                "updated_at": row[4],
                "archived_at": row[5],
                "task_id": row[6],
                "notes": row[7],
            }
            for row in cursor.fetchall()
        ]

    async def update_document_status(self, path: str, status: str, notes: str | None = None) -> bool:
        """
        Update document status.

        Args:
            path: Relative path to document
            status: New status ('active', 'archived', 'deleted')
            notes: Optional notes about the status change

        Returns:
            True if document was updated, False if not found
        """
        now = datetime.now().isoformat()

        async with self._write_lock:
            cursor = self.conn.cursor()

            # Build update query
            if status == "archived":
                cursor.execute(
                    """
                    UPDATE documents
                    SET status = ?, updated_at = ?, archived_at = ?, notes = ?
                    WHERE path = ?
                """,
                    (status, now, now, notes, path),
                )
            else:
                # For non-archived statuses, clear archived_at
                cursor.execute(
                    """
                    UPDATE documents
                    SET status = ?, updated_at = ?, archived_at = NULL, notes = ?
                    WHERE path = ?
                """,
                    (status, now, notes, path),
                )

            self.conn.commit()
            rowcount = cursor.rowcount

        if rowcount > 0:
            logger.info(f"Updated document {path} to status '{status}'")
        else:
            logger.warning(f"Document not found: {path}")

        return rowcount > 0

    def get_documents_by_task(self, task_id: str) -> list[dict]:
        """
        Get all documents associated with a task.

        Args:
            task_id: Task ID

        Returns:
            List of document metadata dictionaries
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT * FROM documents
            WHERE task_id = ?
            ORDER BY created_at DESC
        """,
            (task_id,),
        )

        return [
            {
                "id": row[0],
                "path": row[1],
                "status": row[2],
                "created_at": row[3],
                "updated_at": row[4],
                "archived_at": row[5],
                "task_id": row[6],
                "notes": row[7],
            }
            for row in cursor.fetchall()
        ]

    def get_document_statistics(self) -> dict[str, Any]:
        """Get document tracking statistics"""
        cursor = self.conn.cursor()

        # Total documents
        cursor.execute("SELECT COUNT(*) FROM documents")
        total_documents = cursor.fetchone()[0]

        # Count by status
        cursor.execute(
            """
            SELECT status, COUNT(*) as count
            FROM documents
            GROUP BY status
        """
        )
        by_status = {row[0]: row[1] for row in cursor.fetchall()}

        # Recently archived (last 7 days)
        cutoff = (datetime.now() - timedelta(days=7)).isoformat()
        cursor.execute("SELECT COUNT(*) FROM documents WHERE archived_at >= ?", (cutoff,))
        recently_archived = cursor.fetchone()[0]

        return {
            "total_documents": total_documents,
            "by_status": by_status,
            "recently_archived": recently_archived,
        }
