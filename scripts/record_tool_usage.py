#!/usr/bin/env python3
"""
Hook script for recording Claude Code tool usage to SQLite database.
Called by ~/.claude/hooks/post-tool-use hook.

Reads tool usage data from INPUT_JSON environment variable and records it
using the centralized Database class. This ensures hooks use the correct
database path and connection handling.
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path

# CRITICAL: Set data directory from PROJECT_ROOT env var BEFORE importing config
# This ensures worktrees use the correct database path in the main repo
project_root_env = os.getenv("PROJECT_ROOT")
if project_root_env:
    # Set AGENTLAB_DATA_DIR so config.py uses correct data directory
    os.environ["AGENTLAB_DATA_DIR"] = str(Path(project_root_env) / "data")

# Add parent directory to Python path so we can import modules
# This is needed because hooks run from worktree directories
script_dir = Path(__file__).parent
parent_dir = script_dir.parent
sys.path.insert(0, str(parent_dir))

# Database will be at project root
from tasks.database import Database


def extract_error_message(tool_response):
    """Extract actual error message from tool response"""
    if not tool_response:
        return None

    # If tool_response is a dict, check for explicit error fields only
    if isinstance(tool_response, dict):
        # Check for 'error' key (actual error)
        if "error" in tool_response:
            return str(tool_response["error"])
        # Check for stderr in bash commands (only if non-empty and indicates error)
        if "stderr" in tool_response and tool_response["stderr"]:
            stderr = tool_response["stderr"].strip()
            # Only treat stderr as error if it contains error indicators
            if stderr and any(indicator in stderr.lower() for indicator in ["error:", "exception:", "failed:", "traceback", "fatal:"]):
                return stderr
        # Don't treat normal tool output (mode, content, etc.) as errors
        return None

    # If it's a string containing error indicators
    if isinstance(tool_response, str):
        tool_str_lower = tool_response.lower()
        if any(indicator in tool_str_lower for indicator in ["error:", "exception:", "failed:", "traceback", "fatal:"]):
            # Try to extract just the error message
            lines = tool_response.split("\n")
            for line in lines:
                line_lower = line.lower()
                if any(indicator in line_lower for indicator in ["error:", "exception:", "failed:", "fatal:"]):
                    return line.strip()
            return tool_response[:500]  # Truncate if no specific line found

    return None


def extract_token_usage(tool_response):
    """
    Extract token usage from tool response.

    Args:
        tool_response: Tool response dict or string

    Returns:
        dict with keys: input_tokens, output_tokens, cache_creation_tokens, cache_read_tokens
        All values None if no token data found
    """
    token_data = {
        "input_tokens": None,
        "output_tokens": None,
        "cache_creation_tokens": None,
        "cache_read_tokens": None,
    }

    if not tool_response:
        return token_data

    # If tool_response is a dict, look for usage or tokens field
    if isinstance(tool_response, dict):
        # Check for 'usage' key (Claude API format)
        usage = tool_response.get("usage")
        if usage and isinstance(usage, dict):
            token_data["input_tokens"] = usage.get("input_tokens")
            token_data["output_tokens"] = usage.get("output_tokens")
            token_data["cache_creation_tokens"] = usage.get("cache_creation_tokens")
            token_data["cache_read_tokens"] = usage.get("cache_read_tokens")
            return token_data

        # Check for 'tokens' key (alternative format)
        tokens = tool_response.get("tokens")
        if tokens and isinstance(tokens, dict):
            token_data["input_tokens"] = tokens.get("input_tokens") or tokens.get("input")
            token_data["output_tokens"] = tokens.get("output_tokens") or tokens.get("output")
            token_data["cache_creation_tokens"] = tokens.get("cache_creation_tokens") or tokens.get("cache_creation")
            token_data["cache_read_tokens"] = tokens.get("cache_read_tokens") or tokens.get("cache_read")
            return token_data

        # Check for direct token fields in response
        if "input_tokens" in tool_response or "output_tokens" in tool_response:
            token_data["input_tokens"] = tool_response.get("input_tokens")
            token_data["output_tokens"] = tool_response.get("output_tokens")
            token_data["cache_creation_tokens"] = tool_response.get("cache_creation_tokens")
            token_data["cache_read_tokens"] = tool_response.get("cache_read_tokens")
            return token_data

    return token_data


def categorize_error(error: str) -> str:
    """Categorize error based on error message patterns"""
    if not error:
        return "unknown_error"

    error_lower = error.lower()

    # Permission errors
    if any(pattern in error_lower for pattern in ["permission denied", "access denied", "forbidden", "not permitted"]):
        return "permission_error"

    # File not found errors
    if any(pattern in error_lower for pattern in ["no such file", "file not found", "cannot find", "does not exist"]):
        return "file_not_found"

    # Timeout errors
    if any(pattern in error_lower for pattern in ["timed out", "timeout", "deadline exceeded"]):
        return "timeout"

    # Syntax errors
    if any(pattern in error_lower for pattern in ["syntax error", "invalid syntax", "parsing error", "parse error"]):
        return "syntax_error"

    # Network errors
    if any(
        pattern in error_lower
        for pattern in ["connection", "network", "refused", "unreachable", "dns", "socket", "ssl", "tls"]
    ):
        return "network_error"

    # Git errors
    if any(
        pattern in error_lower for pattern in ["git error", "merge conflict", "rebase", "detached head", "not a git"]
    ):
        return "git_error"

    # Validation errors
    if any(pattern in error_lower for pattern in ["validation", "invalid", "malformed", "bad request"]):
        return "validation_error"

    # Resource errors
    if any(
        pattern in error_lower
        for pattern in ["out of memory", "disk full", "quota", "too many", "resource", "limit exceeded"]
    ):
        return "resource_error"

    # Command not found
    if any(pattern in error_lower for pattern in ["command not found", "not recognized", "no such command"]):
        return "command_not_found"

    return "unknown_error"


def sanitize_parameters(params: dict) -> dict:
    """Sanitize parameters to remove sensitive data"""
    if not params:
        return {}

    sanitized = {}
    sensitive_keys = {"token", "password", "secret", "api_key", "auth", "credential"}

    for key, value in params.items():
        # Skip sensitive keys
        if any(sensitive in str(key).lower() for sensitive in sensitive_keys):
            sanitized[key] = "<redacted>"
        # Truncate long strings
        elif isinstance(value, str) and len(value) > 500:
            sanitized[key] = value[:500] + "..."
        else:
            sanitized[key] = value

    return sanitized


def main():
    """Main hook execution"""
    try:
        # Read input from environment
        input_json = os.environ.get("INPUT_JSON", "{}")
        input_data = json.loads(input_json)

        # Extract data - prioritize env SESSION_ID (set by bot) over JSON session_id (set by Claude)
        env_session_id = os.environ.get("SESSION_ID")
        json_session_id = input_data.get("session_id", "unknown")
        session_id = env_session_id if env_session_id else json_session_id

        # Extract task_id from worktree path if in /tmp/agentlab-worktrees/
        task_id = os.environ.get('TASK_ID')
        if not task_id:
            pwd = os.getcwd()
            if '/tmp/agentlab-worktrees/' in pwd or '/private/tmp/agentlab-worktrees/' in pwd:
                # Extract task_id from path like /tmp/agentlab-worktrees/0e89c3
                task_id = os.path.basename(pwd)

        # Fallback to session_id if no task_id found (for non-worktree tasks)
        if not task_id:
            task_id = session_id

        # Debug: log which session_id and task_id was used
        with open("/tmp/hook_session_debug.log", "a") as f:  # nosec B108
            f.write(f"[{datetime.now().isoformat()}] ENV_SESSION={env_session_id}, JSON_SESSION={json_session_id}, USED_SESSION={session_id}, TASK_ID={task_id}, PWD={os.getcwd()}\n")
        tool_name = input_data.get("tool_name", "unknown")
        tool_response = input_data.get("tool_response", {})
        tool_input = input_data.get("tool_input", {})

        # Extract and sanitize parameters
        parameters = sanitize_parameters(tool_input)

        # Detect errors and extract error message
        error_message = extract_error_message(tool_response)
        has_error = error_message is not None

        # Categorize error if present
        error_category = categorize_error(error_message) if has_error else None

        # Extract token usage from tool response
        token_data = extract_token_usage(tool_response)

        # Initialize database connection (uses DATABASE_PATH from config)
        db = Database()

        # Update existing tool usage record (created by pre-tool-use hook)
        # Pass parameters to match the correct in-progress record (handles concurrent calls)
        # If no record exists (shouldn't happen), fall back to creating new one
        updated = db.update_tool_usage(
            task_id=task_id,
            tool_name=tool_name,
            success=not has_error,
            error=error_message if has_error else None,
            error_category=error_category,
            input_tokens=token_data["input_tokens"],
            output_tokens=token_data["output_tokens"],
            cache_creation_tokens=token_data["cache_creation_tokens"],
            cache_read_tokens=token_data["cache_read_tokens"],
            parameters=parameters,  # Pass parameters for matching
        )

        # Fallback: if no in-progress record found, create new one
        # This shouldn't happen if pre-tool-use hook is working correctly
        if not updated:
            # Log to file since logger may not be available
            with open("/tmp/hook_script_debug.log", "a") as f:  # nosec B108
                f.write(f"[{datetime.now().isoformat()}] Creating new tool usage record for {task_id} - {tool_name} (pre-tool-use may have failed)\n")
            db.record_tool_usage(
                task_id=task_id,
                tool_name=tool_name,
                duration_ms=None,
                success=not has_error,
                error=error_message if has_error else None,
                parameters=parameters,
                error_category=error_category,
                input_tokens=token_data["input_tokens"],
                output_tokens=token_data["output_tokens"],
                cache_creation_tokens=token_data["cache_creation_tokens"],
                cache_read_tokens=token_data["cache_read_tokens"],
            )

        # Record agent status
        db.record_agent_status(
            task_id=task_id,
            status="tool_call",
            message=f"{tool_name} completed",
            metadata={"tool": tool_name, "success": not has_error},
        )

        # Track phase progression for Task tool calls
        # The Task tool is used to delegate work to subagents, so we track which subagent
        # is being invoked and increment the phase counter
        if tool_name == "Task" and not has_error:
            try:
                # Extract subagent_type from tool parameters
                # Parameters format: {"subagent_type": "code_agent", "task_description": "..."}
                subagent_type = parameters.get("subagent_type", "unknown")

                # Count number of Task tool calls for this task_id to determine phase number
                # Query tool_usage table for count of Task calls
                cursor = db.conn.cursor()
                cursor.execute(
                    "SELECT COUNT(*) FROM tool_usage WHERE task_id = ? AND tool_name = 'Task'",
                    (task_id,)
                )
                task_call_count = cursor.fetchone()[0]

                # Phase number is the count (since we just recorded this call, it's included)
                phase_num = task_call_count

                # Update task phase information (async method, but we're in sync context)
                # Run synchronously using asyncio
                import asyncio
                try:
                    # Try to get current event loop
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        # If loop is running, create a new task
                        asyncio.create_task(db.update_task_phase(task_id, subagent_type, phase_num))
                    else:
                        # If no loop or not running, run synchronously
                        loop.run_until_complete(db.update_task_phase(task_id, subagent_type, phase_num))
                except RuntimeError:
                    # No event loop, create new one
                    asyncio.run(db.update_task_phase(task_id, subagent_type, phase_num))

            except Exception as phase_error:
                # Log error but don't fail the hook
                with open("/tmp/hook_script_errors.log", "a") as f:  # nosec B108
                    f.write(f"[{datetime.now().isoformat()}] Phase tracking error: {phase_error}\n")

        # Notify monitoring server via HTTP POST for real-time dashboard updates
        try:
            import urllib.request
            import urllib.error

            timestamp = datetime.utcnow().isoformat() + 'Z'
            notification = {
                'task_id': task_id,
                'tool_name': tool_name,
                'timestamp': timestamp,
                'success': not has_error,
                'error': error_message,
                'parameters': parameters,
                'error_category': error_category
            }

            req = urllib.request.Request(
                'http://localhost:3000/api/tool-execution',
                data=json.dumps(notification).encode('utf-8'),
                headers={'Content-Type': 'application/json'}
            )
            urllib.request.urlopen(req, timeout=0.5)
        except:
            # Silently fail - monitoring server might not be running
            pass

        # Debug logging (optional, can be removed in production)
        with open("/tmp/hook_script_debug.log", "a") as f:  # nosec B108
            db_path = db.db_path if hasattr(db, 'db_path') else 'unknown'
            f.write(f"[{datetime.now().isoformat()}] Recorded {tool_name} for task {task_id} to {db_path}\n")

    except Exception:
        # Log errors but don't fail (hooks should be resilient)
        with open("/tmp/hook_script_errors.log", "a") as f:  # nosec B108
            import traceback

            f.write(f"\n=== Error at {datetime.now().isoformat()} ===\n")
            f.write(traceback.format_exc())
            f.write("\n")
        sys.exit(0)  # Exit cleanly even on error


if __name__ == "__main__":
    main()
