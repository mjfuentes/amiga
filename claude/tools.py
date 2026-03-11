"""
Claude API Tool Definitions and Executors

Provides tool definitions and execution logic for Claude API tool calling.
Provides SQLite database queries, web search, git repository queries,
and project-scoped file/code/database tools.
"""

import json
import logging
import re
import shutil
import sqlite3
import subprocess
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Maximum file size for read_file (1 MB)
_MAX_READ_FILE_SIZE = 1_048_576

# Directories excluded from search/listing
_EXCLUDED_DIRS = frozenset(
    {
        "node_modules",
        "venv",
        ".venv",
        ".git",
        "__pycache__",
        "dist",
        "build",
        ".next",
        "target",
        ".tox",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        "egg-info",
    }
)

_NO_ACTIVE_PROJECT_MSG = "No active project. Run 'amiga init' in your project directory first."


# ---------------------------------------------------------------------------
# Helper: active project resolution
# ---------------------------------------------------------------------------


def _get_active_project_path() -> Path | None:
    """Return the filesystem path of the active project, or None."""
    try:
        from projects.registry import get_active_project

        project = get_active_project()
        if project and project.get("path"):
            return Path(project["path"])
    except Exception:
        pass
    return None


def _validate_project_path(project_root: Path, relative_path: str) -> tuple[Path | None, str | None]:
    """
    Resolve *relative_path* inside *project_root* safely.

    Returns (resolved_path, None) on success or (None, error_message) on failure.
    """
    if not relative_path:
        return None, "Path is empty"

    # Reject obvious traversal attempts before resolving
    if ".." in relative_path.split("/") or ".." in relative_path.split("\\"):
        return None, "Path traversal ('..') is not allowed"

    resolved = (project_root / relative_path).resolve()

    # Ensure the resolved path stays inside the project
    try:
        resolved.relative_to(project_root.resolve())
    except ValueError:
        return None, "Path escapes the project directory"

    return resolved, None


def _is_excluded_path(rel_path: Path) -> bool:
    """Return True if any part of *rel_path* is in the exclusion set."""
    for part in rel_path.parts:
        if part in _EXCLUDED_DIRS or part.startswith("."):
            return True
    return False


# ---------------------------------------------------------------------------
# Tool Definitions -- AMIGA internal tools
# ---------------------------------------------------------------------------

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

Security: Only SELECT queries allowed.""",
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

WEBSEARCH_TOOL = {
    "name": "web_search",
    "description": """Search the web for current information, documentation, or answers to questions that require up-to-date data.

Use this tool when:
- User asks about current events, recent releases, or time-sensitive information
- Looking up documentation, API references, or technical specifications
- Finding latest versions, compatibility info, or release notes
- Researching libraries, frameworks, or tools
- Getting real-world examples or usage patterns

The search will return relevant web results with titles, URLs, and snippets.""",
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search query to execute. Be specific and include relevant keywords.",
            },
            "num_results": {
                "type": "integer",
                "description": "Number of results to return (default: 5, max: 10)",
                "minimum": 1,
                "maximum": 10,
            },
        },
        "required": ["query"],
    },
}

GIT_TOOL = {
    "name": "git_query",
    "description": """Query git repository information for the active project (falls back to AMIGA repo if no active project).

Common operations:
- git status: Check working tree status
- git log: View commit history (last N commits)
- git diff: Show uncommitted changes
- git branch: List branches or show current branch
- git show: Show specific commit details

Security: Read-only operations only. No commits, pushes, or destructive operations allowed.""",
    "input_schema": {
        "type": "object",
        "properties": {
            "operation": {
                "type": "string",
                "enum": ["status", "log", "diff", "branch", "show"],
                "description": "Git operation to perform: status (working tree), log (history), diff (changes), branch (list), show (commit details)",
            },
            "options": {
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "For 'log': number of commits to show (default: 10, max: 50)",
                        "minimum": 1,
                        "maximum": 50,
                    },
                    "commit_hash": {
                        "type": "string",
                        "description": "For 'show': specific commit hash to display",
                    },
                    "branch_name": {
                        "type": "string",
                        "description": "For 'branch' or 'log': specific branch name",
                    },
                    "file_path": {
                        "type": "string",
                        "description": "For 'log' or 'diff': limit to specific file or directory",
                    },
                },
            },
        },
        "required": ["operation"],
    },
}

# ---------------------------------------------------------------------------
# Tool Definitions -- Project-scoped tools
# ---------------------------------------------------------------------------

READ_FILE_TOOL = {
    "name": "read_file",
    "description": "Read a file from the active project. Returns file contents with line numbers. "
    "Use for viewing source code, config files, docs, etc. Path is relative to project root.",
    "input_schema": {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "File path relative to project root (e.g., 'src/auth.py', 'package.json')",
            },
            "start_line": {
                "type": "integer",
                "description": "Start reading from this line (1-indexed, default: 1)",
            },
            "max_lines": {
                "type": "integer",
                "description": "Maximum lines to return (default: 100, max: 500)",
            },
        },
        "required": ["path"],
    },
}

SEARCH_CODE_TOOL = {
    "name": "search_code",
    "description": "Search for text/patterns in the active project's codebase. Like grep/ripgrep. "
    "Returns matching lines with file paths and line numbers.",
    "input_schema": {
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "Search pattern (supports basic regex)",
            },
            "file_pattern": {
                "type": "string",
                "description": "Glob to filter files (e.g., '*.py', '*.ts', 'src/**/*.js')",
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum results (default: 20, max: 50)",
            },
        },
        "required": ["pattern"],
    },
}

LIST_FILES_TOOL = {
    "name": "list_files",
    "description": "List files in the active project matching a pattern. "
    "Use to explore project structure, find files by name, or see directory contents.",
    "input_schema": {
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "Glob pattern (e.g., '**/*.py', 'src/components/*.tsx', '*') or directory path",
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum files to return (default: 50, max: 200)",
            },
        },
        "required": ["pattern"],
    },
}

QUERY_PROJECT_DB_TOOL = {
    "name": "query_project_database",
    "description": "Query a SQLite database in the active project. Use this to check application data, "
    "look up records, explore schemas. The project's databases and their schemas are described "
    "in the project profile.",
    "input_schema": {
        "type": "object",
        "properties": {
            "database_path": {
                "type": "string",
                "description": "Path to database file relative to project root (e.g., 'data/app.db', 'db.sqlite3')",
            },
            "query": {
                "type": "string",
                "description": "SQL SELECT query to execute",
            },
            "parameters": {
                "type": "array",
                "items": {"type": ["string", "number", "boolean", "null"]},
                "description": "Query parameters for ? placeholders",
            },
        },
        "required": ["database_path", "query"],
    },
}

PROJECT_INFO_TOOL = {
    "name": "project_info",
    "description": "Get information about the active project: languages, frameworks, structure, databases, "
    "and their schemas. Use this to understand what you're working with.",
    "input_schema": {
        "type": "object",
        "properties": {},
    },
}

QUERY_SUPABASE_TOOL = {
    "name": "query_supabase",
    "description": "Query the active project's Supabase database using the REST API. "
    "Reads SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY from the project's .env files. "
    "Use this for querying Supabase tables when the project has a remote Supabase database.",
    "input_schema": {
        "type": "object",
        "properties": {
            "table": {"type": "string", "description": "Table name to query"},
            "select": {
                "type": "string",
                "description": "Columns to select (default: '*'). Use PostgREST syntax.",
            },
            "filters": {
                "type": "string",
                "description": "PostgREST filter string (e.g., 'status=eq.pending', 'email=ilike.*@gmail.com')",
            },
            "limit": {
                "type": "integer",
                "description": "Max rows (default: 20, max: 100)",
            },
            "order": {
                "type": "string",
                "description": "Order by (e.g., 'created_at.desc')",
            },
        },
        "required": ["table"],
    },
}


# ---------------------------------------------------------------------------
# Tool collections
# ---------------------------------------------------------------------------

_BASE_TOOLS = [SQLITE_TOOL, WEBSEARCH_TOOL, GIT_TOOL]
_PROJECT_TOOLS = [READ_FILE_TOOL, SEARCH_CODE_TOOL, LIST_FILES_TOOL, QUERY_PROJECT_DB_TOOL, PROJECT_INFO_TOOL, QUERY_SUPABASE_TOOL]

# All available tools -- includes project tools so they are always registered.
# Individual executors return a helpful error when no active project is set.
AVAILABLE_TOOLS = _BASE_TOOLS + _PROJECT_TOOLS


def get_available_tools(has_active_project: bool = False) -> list[dict]:
    """Return tool definitions, including project tools if an active project exists."""
    if has_active_project:
        return _BASE_TOOLS + _PROJECT_TOOLS
    return list(_BASE_TOOLS)


# ---------------------------------------------------------------------------
# Query validation (shared)
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Executors -- AMIGA internal tools
# ---------------------------------------------------------------------------


async def execute_sqlite_query(query: str, database: str, parameters: list[Any] | None = None) -> str:
    """
    Execute read-only SQLite query against AMIGA's own databases.

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

    # Get database path - find project root dynamically
    current = Path(__file__).parent.parent  # Go up to project root from claude/tools.py
    data_dir = current / "data"

    # If not found, try CWD parents
    if not data_dir.exists():
        current = Path.cwd()
        while current != current.parent:
            data_dir = current / "data"
            if data_dir.exists():
                break
            current = current.parent

    db_path = data_dir / f"{database}.db"

    if not db_path.exists():
        logger.error(f"Database not found: {db_path}")
        return json.dumps(
            {"success": False, "error": f"Database '{database}' not found", "row_count": 0, "results": []}
        )

    try:
        conn = sqlite3.connect(str(db_path), timeout=5.0)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        params = parameters or []
        clean_query = query.rstrip(";")

        logger.info(f"Executing SQLite query on {database}: {clean_query}")

        cursor.execute(clean_query, params)
        rows = cursor.fetchall()
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


async def execute_websearch(query: str, num_results: int = 5) -> str:
    """
    Execute web search using DuckDuckGo.

    Args:
        query: Search query
        num_results: Number of results to return (max 10)

    Returns:
        JSON string with results or error
    """
    try:
        from ddgs import DDGS

        num_results = min(num_results, 10)

        logger.info(f"Executing web search: {query[:100]}... (requesting {num_results} results)")

        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=num_results))

        formatted_results = []
        for result in results:
            formatted_results.append(
                {
                    "title": result.get("title", ""),
                    "url": result.get("href", ""),
                    "snippet": result.get("body", ""),
                }
            )

        logger.info(f"Web search returned {len(formatted_results)} results")

        return json.dumps({"success": True, "result_count": len(formatted_results), "results": formatted_results})

    except ImportError:
        logger.error("ddgs library not installed")
        return json.dumps(
            {
                "success": False,
                "error": "Web search library not available. Install with: pip install ddgs",
                "result_count": 0,
                "results": [],
            }
        )
    except Exception as e:
        logger.error(f"Web search error: {e}", exc_info=True)
        return json.dumps({"success": False, "error": f"Search error: {str(e)}", "result_count": 0, "results": []})


async def execute_git_query(operation: str, options: dict[str, Any] | None = None) -> str:
    """
    Execute read-only git query operations against the active project.

    Falls back to AMIGA's own repo if no active project is set.

    Args:
        operation: Git operation (status, log, diff, branch, show)
        options: Optional parameters specific to the operation

    Returns:
        JSON string with results or error
    """
    opts = options or {}

    # Prefer active project; fall back to AMIGA repo
    project_path = _get_active_project_path()
    if project_path and (project_path / ".git").exists():
        current = project_path
    else:
        current = Path(__file__).parent.parent
        if not (current / ".git").exists():
            current = Path.cwd()
            while current != current.parent:
                if (current / ".git").exists():
                    break
                current = current.parent

    if not (current / ".git").exists():
        logger.error("Git repository not found")
        return json.dumps({"success": False, "error": "Git repository not found", "output": ""})

    try:
        if operation == "status":
            cmd = ["git", "status", "--short", "--branch"]

        elif operation == "log":
            limit = min(opts.get("limit", 10), 50)
            cmd = ["git", "log", f"-{limit}", "--oneline", "--decorate"]
            if opts.get("branch_name"):
                cmd.append(opts["branch_name"])
            if opts.get("file_path"):
                cmd.extend(["--", opts["file_path"]])

        elif operation == "diff":
            cmd = ["git", "diff", "--stat"]
            if opts.get("file_path"):
                cmd.append(opts["file_path"])

        elif operation == "branch":
            cmd = ["git", "branch", "-a", "-v"]
            if opts.get("branch_name"):
                cmd = ["git", "branch", "--list", opts["branch_name"]]

        elif operation == "show":
            commit_hash = opts.get("commit_hash", "HEAD")
            cmd = ["git", "show", "--stat", "--oneline", commit_hash]

        else:
            logger.error(f"Invalid git operation: {operation}")
            return json.dumps({"success": False, "error": f"Invalid operation: {operation}", "output": ""})

        logger.info(f"Executing git command: {' '.join(cmd)} in {current}")
        result = subprocess.run(
            cmd,
            cwd=str(current),
            capture_output=True,
            text=True,
            timeout=10,
        )

        if result.returncode != 0:
            logger.warning(f"Git command failed: {result.stderr}")
            return json.dumps(
                {
                    "success": False,
                    "error": result.stderr.strip() or "Git command failed",
                    "output": result.stdout.strip(),
                }
            )

        output = result.stdout.strip()
        logger.info(f"Git command succeeded, output length: {len(output)} chars")

        return json.dumps({"success": True, "operation": operation, "output": output})

    except subprocess.TimeoutExpired:
        logger.error("Git command timed out")
        return json.dumps({"success": False, "error": "Git command timed out (>10s)", "output": ""})
    except Exception as e:
        logger.error(f"Git command error: {e}", exc_info=True)
        return json.dumps({"success": False, "error": f"Unexpected error: {str(e)}", "output": ""})


# ---------------------------------------------------------------------------
# Executors -- Project-scoped tools
# ---------------------------------------------------------------------------


async def execute_read_file(
    path: str,
    start_line: int = 1,
    max_lines: int = 100,
) -> str:
    """Read a file from the active project with line numbers."""
    project_root = _get_active_project_path()
    if project_root is None:
        return json.dumps({"success": False, "error": _NO_ACTIVE_PROJECT_MSG})

    resolved, err = _validate_project_path(project_root, path)
    if err:
        return json.dumps({"success": False, "error": err})

    if not resolved.is_file():
        return json.dumps({"success": False, "error": f"File not found: {path}"})

    # Size guard
    try:
        size = resolved.stat().st_size
    except OSError as e:
        return json.dumps({"success": False, "error": f"Cannot stat file: {e}"})

    if size > _MAX_READ_FILE_SIZE:
        return json.dumps(
            {
                "success": False,
                "error": f"File too large ({size:,} bytes). Maximum is {_MAX_READ_FILE_SIZE:,} bytes.",
            }
        )

    # Clamp parameters
    start_line = max(1, start_line)
    max_lines = max(1, min(max_lines, 500))

    try:
        text = resolved.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        return json.dumps({"success": False, "error": f"Cannot read file: {e}"})

    all_lines = text.splitlines()
    total = len(all_lines)
    selected = all_lines[start_line - 1 : start_line - 1 + max_lines]

    # Build numbered output, truncating long lines
    numbered = []
    for i, line in enumerate(selected, start=start_line):
        truncated = line[:500] + "..." if len(line) > 500 else line
        numbered.append(f"{i:>6}\t{truncated}")

    content = "\n".join(numbered)
    return json.dumps(
        {
            "success": True,
            "path": path,
            "total_lines": total,
            "start_line": start_line,
            "lines_returned": len(selected),
            "content": content,
        }
    )


async def execute_search_code(
    pattern: str,
    file_pattern: str | None = None,
    max_results: int = 20,
) -> str:
    """Search code in the active project using rg (preferred) or grep."""
    project_root = _get_active_project_path()
    if project_root is None:
        return json.dumps({"success": False, "error": _NO_ACTIVE_PROJECT_MSG})

    if not pattern:
        return json.dumps({"success": False, "error": "Search pattern is empty"})

    max_results = max(1, min(max_results, 50))

    # Decide whether to use rg or grep
    rg_path = shutil.which("rg")

    if rg_path:
        cmd: list[str] = [
            rg_path,
            "--no-heading",
            "--line-number",
            "--color=never",
            f"--max-count={max_results}",
        ]
        for d in sorted(_EXCLUDED_DIRS):
            cmd.append(f"--glob=!{d}")
        if file_pattern:
            cmd.extend(["--glob", file_pattern])
        cmd.append("--")
        cmd.append(pattern)
        cmd.append(".")
    else:
        cmd = [
            "grep",
            "-rn",
            "--color=never",
        ]
        for d in sorted(_EXCLUDED_DIRS):
            cmd.extend(["--exclude-dir", d])
        if file_pattern:
            cmd.extend(["--include", file_pattern])
        cmd.append("--")
        cmd.append(pattern)
        cmd.append(".")

    try:
        result = subprocess.run(
            cmd,
            cwd=str(project_root),
            capture_output=True,
            text=True,
            timeout=15,
        )
    except subprocess.TimeoutExpired:
        return json.dumps({"success": False, "error": "Search timed out (>15s)"})
    except Exception as e:
        return json.dumps({"success": False, "error": f"Search error: {e}"})

    # rg returns 1 when no matches, 2 on error; grep returns 1 for no matches
    if result.returncode == 2 and rg_path:
        return json.dumps({"success": False, "error": result.stderr.strip() or "Search failed"})

    lines = result.stdout.strip().splitlines() if result.stdout.strip() else []

    # Trim leading "./" from paths
    cleaned = []
    for line in lines[:max_results]:
        if line.startswith("./"):
            line = line[2:]
        cleaned.append(line)

    return json.dumps(
        {
            "success": True,
            "match_count": len(cleaned),
            "matches": cleaned,
        }
    )


async def execute_list_files(
    pattern: str,
    max_results: int = 50,
) -> str:
    """List files in the active project matching a glob pattern."""
    project_root = _get_active_project_path()
    if project_root is None:
        return json.dumps({"success": False, "error": _NO_ACTIVE_PROJECT_MSG})

    if not pattern:
        return json.dumps({"success": False, "error": "Pattern is empty"})

    max_results = max(1, min(max_results, 200))

    try:
        matches: list[str] = []
        for p in sorted(project_root.glob(pattern)):
            if not p.is_file():
                continue
            rel = p.relative_to(project_root)
            if _is_excluded_path(rel):
                continue
            matches.append(str(rel))
            if len(matches) >= max_results:
                break
    except Exception as e:
        return json.dumps({"success": False, "error": f"Glob error: {e}"})

    return json.dumps(
        {
            "success": True,
            "file_count": len(matches),
            "files": matches,
        }
    )


async def execute_query_project_database(
    database_path: str,
    query: str,
    parameters: list[Any] | None = None,
) -> str:
    """Query a SQLite database inside the active project (SELECT only)."""
    project_root = _get_active_project_path()
    if project_root is None:
        return json.dumps({"success": False, "error": _NO_ACTIVE_PROJECT_MSG})

    resolved, err = _validate_project_path(project_root, database_path)
    if err:
        return json.dumps({"success": False, "error": err, "row_count": 0, "results": []})

    if not resolved.is_file():
        return json.dumps(
            {"success": False, "error": f"Database not found: {database_path}", "row_count": 0, "results": []}
        )

    # Validate SELECT-only
    is_valid, val_err = _validate_select_query(query)
    if not is_valid:
        return json.dumps({"success": False, "error": val_err, "row_count": 0, "results": []})

    try:
        conn = sqlite3.connect(str(resolved), timeout=5.0)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        clean_query = query.rstrip(";")
        params = parameters or []

        logger.info(f"Executing project DB query on {database_path}: {clean_query}")
        cursor.execute(clean_query, params)
        rows = cursor.fetchall()
        results = [dict(row) for row in rows]
        conn.close()

        return json.dumps({"success": True, "row_count": len(results), "results": results})

    except sqlite3.Error as e:
        logger.error(f"Project DB error: {e}", exc_info=True)
        return json.dumps({"success": False, "error": f"Database error: {str(e)}", "row_count": 0, "results": []})
    except Exception as e:
        logger.error(f"Unexpected error querying project DB: {e}", exc_info=True)
        return json.dumps({"success": False, "error": f"Unexpected error: {str(e)}", "row_count": 0, "results": []})


async def execute_project_info() -> str:
    """Return the active project's profile from .amiga/profile.json."""
    project_root = _get_active_project_path()
    if project_root is None:
        return json.dumps({"success": False, "error": _NO_ACTIVE_PROJECT_MSG})

    profile_path = project_root / ".amiga" / "profile.json"
    if not profile_path.is_file():
        return json.dumps(
            {
                "success": True,
                "project_path": str(project_root),
                "profile": None,
                "message": "No .amiga/profile.json found. Run 'amiga scan' to generate a project profile.",
            }
        )

    try:
        profile = json.loads(profile_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        return json.dumps({"success": False, "error": f"Failed to read profile: {e}"})

    return json.dumps(
        {
            "success": True,
            "project_path": str(project_root),
            "profile": profile,
        }
    )


def _read_supabase_credentials(project_root: Path) -> tuple[str | None, str | None]:
    """Read Supabase URL and service role key from project .env files.

    Searches .env, .env.local, .env.production in the project root and
    immediate subdirectories. Returns (url, key) or (None, None).
    """
    env_filenames = (".env", ".env.local", ".env.production")
    search_dirs = [project_root]

    # Also search immediate subdirectories (e.g., website/)
    try:
        for entry in project_root.iterdir():
            if entry.is_dir() and not entry.name.startswith(".") and entry.name not in (
                "node_modules", "venv", ".venv", "dist", "build"
            ):
                search_dirs.append(entry)
    except (PermissionError, OSError):
        pass

    url: str | None = None
    key: str | None = None

    for search_dir in search_dirs:
        for env_name in env_filenames:
            env_file = search_dir / env_name
            if not env_file.is_file():
                continue
            try:
                content = env_file.read_text(encoding="utf-8", errors="replace")
            except (OSError, PermissionError):
                continue

            for line in content.splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" not in line:
                    continue
                name, _, value = line.partition("=")
                name = name.strip()
                value = value.strip().strip("'\"")

                if name in ("SUPABASE_URL", "NEXT_PUBLIC_SUPABASE_URL") and value:
                    url = url or value
                if name == "SUPABASE_SERVICE_ROLE_KEY" and value:
                    key = key or value

            if url and key:
                return url, key

    return url, key


async def execute_query_supabase(
    table: str,
    select: str = "*",
    filters: str | None = None,
    limit: int = 20,
    order: str | None = None,
) -> str:
    """Query a Supabase database via the REST API."""
    project_root = _get_active_project_path()
    if project_root is None:
        return json.dumps({"success": False, "error": _NO_ACTIVE_PROJECT_MSG})

    if not table:
        return json.dumps({"success": False, "error": "Table name is required"})

    # Validate table name (alphanumeric + underscore only)
    if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", table):
        return json.dumps({"success": False, "error": f"Invalid table name: {table}"})

    url, service_key = _read_supabase_credentials(project_root)
    if not url or not service_key:
        return json.dumps({
            "success": False,
            "error": "Supabase credentials not found. Need SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in project .env files.",
        })

    # Clamp limit
    limit = max(1, min(limit, 100))

    # Build request URL
    api_url = f"{url.rstrip('/')}/rest/v1/{table}"
    params: list[str] = [f"select={select}"]
    if filters:
        params.append(filters)
    params.append(f"limit={limit}")
    if order:
        params.append(f"order={order}")

    full_url = f"{api_url}?{'&'.join(params)}"

    headers = {
        "apikey": service_key,
        "Authorization": f"Bearer {service_key}",
        "Accept": "application/json",
    }

    try:
        import httpx

        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(full_url, headers=headers)

        if response.status_code == 200:
            data = response.json()
            return json.dumps({
                "success": True,
                "table": table,
                "row_count": len(data),
                "results": data,
            })
        else:
            error_body = response.text[:500]
            logger.warning(f"Supabase API error {response.status_code}: {error_body}")
            return json.dumps({
                "success": False,
                "error": f"Supabase API error ({response.status_code}): {error_body}",
            })

    except ImportError:
        return json.dumps({
            "success": False,
            "error": "httpx library not available. Install with: pip install httpx",
        })
    except Exception as e:
        logger.error(f"Supabase query error: {e}", exc_info=True)
        return json.dumps({"success": False, "error": f"Request failed: {str(e)}"})


# ---------------------------------------------------------------------------
# Tool dispatcher
# ---------------------------------------------------------------------------


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
    elif tool_name == "web_search":
        return await execute_websearch(
            query=tool_input.get("query", ""),
            num_results=tool_input.get("num_results", 5),
        )
    elif tool_name == "git_query":
        return await execute_git_query(
            operation=tool_input.get("operation", "status"),
            options=tool_input.get("options"),
        )
    elif tool_name == "read_file":
        return await execute_read_file(
            path=tool_input.get("path", ""),
            start_line=tool_input.get("start_line", 1),
            max_lines=tool_input.get("max_lines", 100),
        )
    elif tool_name == "search_code":
        return await execute_search_code(
            pattern=tool_input.get("pattern", ""),
            file_pattern=tool_input.get("file_pattern"),
            max_results=tool_input.get("max_results", 20),
        )
    elif tool_name == "list_files":
        return await execute_list_files(
            pattern=tool_input.get("pattern", ""),
            max_results=tool_input.get("max_results", 50),
        )
    elif tool_name == "query_project_database":
        return await execute_query_project_database(
            database_path=tool_input.get("database_path", ""),
            query=tool_input.get("query", ""),
            parameters=tool_input.get("parameters"),
        )
    elif tool_name == "project_info":
        return await execute_project_info()
    elif tool_name == "query_supabase":
        return await execute_query_supabase(
            table=tool_input.get("table", ""),
            select=tool_input.get("select", "*"),
            filters=tool_input.get("filters"),
            limit=tool_input.get("limit", 20),
            order=tool_input.get("order"),
        )
    else:
        logger.error(f"Unknown tool requested: {tool_name}")
        return json.dumps({"success": False, "error": f"Unknown tool: {tool_name}"})
