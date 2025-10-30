"""
Claude API Tool Definitions and Executors

Provides tool definitions and execution logic for Claude API tool calling.
Currently supports SQLite database queries for accessing task and analytics data.
"""

import json
import logging
import re
import sqlite3
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# Tool Definitions
SQLITE_TOOL = {
    "name": "query_database",
    "description": """Query the SQLite database for information about tasks, tool usage, sessions, or analytics.

Available databases:
- agentlab: Contains tasks, tool_usage tables for task tracking and metrics
- analytics: Contains user messages, conversation history, and usage analytics

Common queries:
- Active tasks: SELECT task_id, status, description FROM tasks WHERE status='running'
- Recent errors: SELECT task_id, error FROM tasks WHERE error IS NOT NULL ORDER BY updated_at DESC LIMIT 10
- Tool usage: SELECT tool_name, COUNT(*) as count FROM tool_usage GROUP BY tool_name ORDER BY count DESC
- User activity: SELECT COUNT(*) as message_count FROM messages WHERE user_id=? AND timestamp > datetime('now', '-24 hours')

Security: Only SELECT queries allowed. Results limited to 100 rows.""",
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "SQL SELECT query to execute. Must be a valid SELECT statement. Use parameterized queries with ? placeholders for safety.",
            },
            "database": {
                "type": "string",
                "enum": ["agentlab", "analytics"],
                "description": "Which database to query: 'agentlab' for tasks/tool_usage, 'analytics' for messages/sessions",
            },
            "parameters": {
                "type": "array",
                "items": {"type": ["string", "number", "boolean", "null"]},
                "description": "Optional parameters for parameterized queries (? placeholders). Use this for safe value substitution.",
            },
        },
        "required": ["query", "database"],
    },
}


# All available tools
AVAILABLE_TOOLS = [SQLITE_TOOL]


def _validate_select_query(query: str) -> tuple[bool, str | None]:
    """
    Validate that query is a safe SELECT statement.

    Args:
        query: SQL query to validate

    Returns:
        (is_valid, error_message) - True if valid, with None error
    """
    if not query:
        return False, "Query is empty"

    # Normalize whitespace and remove comments
    normalized = " ".join(query.split())
    normalized = re.sub(r"--.*$", "", normalized, flags=re.MULTILINE)
    normalized = re.sub(r"/\*.*?\*/", "", normalized, flags=re.DOTALL)

    # Must start with SELECT (case insensitive)
    if not normalized.strip().upper().startswith("SELECT"):
        return False, "Only SELECT queries are allowed"

    # Check for dangerous operations
    dangerous_patterns = [
        r"\b(DROP|DELETE|INSERT|UPDATE|ALTER|CREATE|REPLACE|TRUNCATE)\b",
        r"\b(ATTACH|DETACH)\b",  # Database attachment
        r"\bPRAGMA\b",  # Pragma commands
        r"\b(EXECUTE|EXEC)\b",  # Dynamic execution
        r";.*SELECT",  # Multiple statements
    ]

    for pattern in dangerous_patterns:
        if re.search(pattern, normalized, re.IGNORECASE):
            return False, f"Query contains forbidden operation: {pattern}"

    return True, None


async def execute_sqlite_query(query: str, database: str, parameters: list[Any] | None = None) -> str:
    """
    Execute read-only SQLite query.

    Args:
        query: SQL SELECT query
        database: "agentlab" or "analytics"
        parameters: Optional list of parameters for parameterized queries

    Returns:
        JSON string with results or error
    """
    # Validate query
    is_valid, error = _validate_select_query(query)
    if not is_valid:
        logger.warning(f"Invalid SQL query rejected: {error}")
        return json.dumps({"success": False, "error": error, "row_count": 0, "results": []})

    # Get database path
    from core.config import get_data_dir_for_cwd

    data_dir = Path(get_data_dir_for_cwd())
    db_path = data_dir / f"{database}.db"

    if not db_path.exists():
        logger.error(f"Database not found: {db_path}")
        return json.dumps(
            {"success": False, "error": f"Database '{database}' not found", "row_count": 0, "results": []}
        )

    try:
        # Connect with timeout
        conn = sqlite3.connect(str(db_path), timeout=5.0)
        conn.row_factory = sqlite3.Row  # Dict-like rows
        cursor = conn.cursor()

        # Execute with row limit and parameters
        params = parameters or []
        limited_query = f"{query.rstrip(';')} LIMIT 100"

        logger.info(f"Executing SQLite query on {database}: {limited_query[:100]}...")

        cursor.execute(limited_query, params)
        rows = cursor.fetchall()

        # Convert to dicts
        results = [dict(row) for row in rows]

        conn.close()

        logger.info(f"SQLite query returned {len(results)} rows")

        return json.dumps({"success": True, "row_count": len(results), "results": results})

    except sqlite3.Error as e:
        logger.error(f"SQLite error: {e}", exc_info=True)
        return json.dumps({"success": False, "error": f"Database error: {str(e)}", "row_count": 0, "results": []})
    except Exception as e:
        logger.error(f"Unexpected error executing SQLite query: {e}", exc_info=True)
        return json.dumps({"success": False, "error": f"Unexpected error: {str(e)}", "row_count": 0, "results": []})


async def execute_tool(tool_name: str, tool_input: dict[str, Any]) -> str:
    """
    Execute a tool by name with given input.

    Args:
        tool_name: Name of the tool to execute
        tool_input: Input parameters matching the tool's input_schema

    Returns:
        Tool execution result as JSON string
    """
    if tool_name == "query_database":
        return await execute_sqlite_query(
            query=tool_input.get("query", ""),
            database=tool_input.get("database", "agentlab"),
            parameters=tool_input.get("parameters"),
        )
    else:
        logger.error(f"Unknown tool requested: {tool_name}")
        return json.dumps({"success": False, "error": f"Unknown tool: {tool_name}"})
