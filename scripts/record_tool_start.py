#!/usr/bin/env python3
"""
Hook script for recording Claude Code tool starts to SQLite database.
Called by ~/.claude/hooks/pre-tool-use hook.

Records all tool usage immediately when tools start (before completion)
so dashboard shows real-time activity.
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path

# CRITICAL: Set data directory from PROJECT_ROOT env var BEFORE importing config
project_root_env = os.getenv("PROJECT_ROOT")
if project_root_env:
    os.environ["AGENTLAB_DATA_DIR"] = str(Path(project_root_env) / "data")

# Add parent directory to Python path
script_dir = Path(__file__).parent
parent_dir = script_dir.parent
sys.path.insert(0, str(parent_dir))

from tasks.database import Database


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
    """Record tool invocations immediately when they start"""
    try:
        # Read input from environment
        input_json = os.environ.get("INPUT_JSON", "{}")
        input_data = json.loads(input_json)

        # Extract tool name
        tool_name = input_data.get("tool_name", "unknown")

        # Extract session and task IDs
        env_session_id = os.environ.get("SESSION_ID")
        json_session_id = input_data.get("session_id", "unknown")
        session_id = env_session_id if env_session_id else json_session_id

        # Extract task_id from environment or worktree path
        task_id = os.environ.get('TASK_ID')
        if not task_id:
            pwd = os.getcwd()
            if '/tmp/agentlab-worktrees/' in pwd or '/private/tmp/agentlab-worktrees/' in pwd:
                task_id = os.path.basename(pwd)

        # Fallback to session_id if no task_id found
        if not task_id:
            task_id = session_id

        # Extract and sanitize tool input parameters
        tool_input = input_data.get("tool_input", {})
        parameters = sanitize_parameters(tool_input)

        # Initialize database
        db = Database()

        # Record tool invocation as "starting" (success=None means in-progress)
        db.record_tool_usage(
            task_id=task_id,
            tool_name=tool_name,
            duration_ms=None,
            success=None,  # None = in-progress, True/False = completed
            error=None,
            parameters=parameters,
            error_category=None,
            input_tokens=None,
            output_tokens=None,
            cache_creation_tokens=None,
            cache_read_tokens=None,
        )

        # Notify monitoring server for real-time dashboard update
        try:
            import urllib.request

            timestamp = datetime.utcnow().isoformat() + 'Z'
            notification = {
                'task_id': task_id,
                'tool_name': tool_name,
                'timestamp': timestamp,
                'success': None,  # In-progress
                'error': None,
                'parameters': parameters,
                'has_error': False,  # Not an error, just starting
                'in_progress': True,  # Flag for frontend
            }

            req = urllib.request.Request(
                'http://localhost:3000/api/tool-execution',
                data=json.dumps(notification).encode('utf-8'),
                headers={'Content-Type': 'application/json'}
            )
            urllib.request.urlopen(req, timeout=0.5)
        except:
            pass  # Silently fail if monitoring server not running

    except Exception:
        # Log errors but don't fail (hooks should be resilient)
        with open("/tmp/hook_script_errors.log", "a") as f:
            import traceback
            f.write(f"\n=== Tool Start Recording Error at {datetime.now().isoformat()} ===\n")
            f.write(traceback.format_exc())
            f.write("\n")
        sys.exit(0)


if __name__ == "__main__":
    main()
