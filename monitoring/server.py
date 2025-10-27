import eventlet

eventlet.monkey_patch()

"""
Flask-based monitoring server for bot metrics
Provides web UI and REST API for real-time metrics with SSE support
Includes WebSocket support for web chat interface
"""

import sys  # noqa: E402
from pathlib import Path  # noqa: E402

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import asyncio  # noqa: E402
import json  # noqa: E402
import logging  # noqa: E402
import os  # noqa: E402
import time  # noqa: E402
import uuid  # noqa: E402
from collections.abc import Generator  # noqa: E402
from datetime import datetime, timedelta  # noqa: E402

import bcrypt  # noqa: E402
import jwt as pyjwt  # noqa: E402
from claude.code_cli import ClaudeSessionPool  # noqa: E402
from core.config import get_data_dir_for_cwd, get_sessions_dir_for_cwd  # noqa: E402
from core.session import SessionManager  # noqa: E402
from dotenv import load_dotenv  # noqa: E402
from flask import Flask, Response, jsonify, render_template, request, send_from_directory, session  # noqa: E402
from flask_cors import CORS  # noqa: E402
from flask_socketio import SocketIO, emit, join_room, leave_room  # noqa: E402
from monitoring.hooks_reader import HooksReader  # noqa: E402
from monitoring.metrics import MetricsAggregator  # noqa: E402
from tasks.manager import TaskManager  # noqa: E402
from tasks.pool import AgentPool, TaskPriority  # noqa: E402
from tasks.tracker import ToolUsageTracker  # noqa: E402
from monitoring.commands import CommandHandler  # noqa: E402
from utils.logging_setup import configure_root_logger  # noqa: E402

# Load environment variables from parent directory's .env file
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path)

from core.exceptions import AMIGAError

logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__, template_folder="../templates", static_folder="../static")
app.config["TEMPLATES_AUTO_RELOAD"] = True
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0
app.config["SECRET_KEY"] = os.getenv("JWT_SECRET_KEY", "dev-secret-change-in-prod-IMPORTANT")

# CORS configuration
allowed_origins = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:3001").split(",")
CORS(app, origins=allowed_origins, supports_credentials=True)

# Initialize SocketIO
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="eventlet", logger=False, engineio_logger=False)

# Initialize tracking systems (determine data paths based on where we're running from)
# Use centralized config helper functions for CWD-relative paths
data_dir = get_data_dir_for_cwd()
sessions_dir = get_sessions_dir_for_cwd()

# Add workspace sessions directory for bot task sessions
workspace_path = os.getenv("WORKSPACE_PATH", "/Users/matifuentes/Workspace")
workspace_sessions_dir = str(Path(workspace_path) / "logs" / "sessions")
BOT_REPOSITORY = str(Path(__file__).parent.parent)

task_manager = TaskManager(data_dir=data_dir)
command_handler = CommandHandler(task_manager)
tool_usage_tracker = ToolUsageTracker(data_dir=data_dir)
hooks_reader = HooksReader(sessions_dir=sessions_dir, additional_dirs=[workspace_sessions_dir])

# Initialize metrics aggregator
metrics_aggregator = MetricsAggregator(task_manager, tool_usage_tracker, hooks_reader)

# Initialize session manager for web chat
session_manager = SessionManager(data_dir=data_dir)

# Initialize Claude session pool for task execution
# CRITICAL: Pass usage_tracker to enable session_uuid tracking for tool usage correlation
claude_pool = ClaudeSessionPool(max_concurrent=3, usage_tracker=tool_usage_tracker)
logger.info(f"Initialized ClaudeSessionPool with usage_tracker: {tool_usage_tracker is not None}")

# Initialize agent pool for task execution (shared with Telegram bot)
agent_pool = AgentPool(max_agents=3)

# Global event loop for agent pool (set in run_server())
_agent_pool_loop = None

# Store last sent data for change detection
last_metrics_snapshot = None

# Initialize database for user management
from core.database_manager import get_database, close_database  # noqa: E402
from tasks.analytics import AnalyticsDB  # noqa: E402

user_db = get_database()
analytics_db = AnalyticsDB(user_db)

# --- Authentication Helper Functions ---

SECRET_KEY = os.getenv("JWT_SECRET_KEY", "dev-secret-change-in-prod-IMPORTANT")
TOKEN_EXPIRATION_HOURS = 1


def hash_password(password: str) -> str:
    """Hash password with bcrypt."""
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    """Verify password against hash."""
    try:
        return bcrypt.checkpw(password.encode(), password_hash.encode())
    except Exception:
        return False


def create_token(user_id: str, expiration_hours: int = TOKEN_EXPIRATION_HOURS) -> str:
    """Create JWT token."""
    payload = {
        "user_id": user_id,
        "exp": datetime.utcnow() + timedelta(hours=expiration_hours),
        "iat": datetime.utcnow(),
    }
    return pyjwt.encode(payload, SECRET_KEY, algorithm="HS256")


def verify_token(token: str) -> str | None:
    """Verify JWT token and return user_id, or None if invalid."""
    if not token:
        return None
    try:
        payload = pyjwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        return payload.get("user_id")
    except pyjwt.ExpiredSignatureError:
        return None
    except pyjwt.InvalidTokenError:
        return None


def register_user(username: str, email: str, password: str) -> tuple[bool, str]:
    """
    Register new user using SQLite database.

    Args:
        username: Username (must be unique)
        email: Email address (must be unique)
        password: Plain text password (will be hashed)

    Returns:
        Tuple of (success, user_id or error_message)
    """
    if not username or not email or not password:
        return False, "All fields are required"
    if len(password) < 8:
        return False, "Password must be at least 8 characters"

    # Check if username already exists
    if user_db.get_user_by_username(username):
        return False, "Username already exists"

    # Check if email already exists
    if user_db.get_user_by_email(email):
        return False, "Email already registered"

    # Create new user
    user_id = str(uuid.uuid4())
    password_hash_value = hash_password(password)

    success = user_db.create_user(
        user_id=user_id, username=username, email=email, password_hash=password_hash_value, is_admin=False
    )

    if success:
        return True, user_id
    else:
        return False, "Failed to create user"


def login_user(username: str, password: str) -> tuple[bool, str]:
    """
    Login user using SQLite database.

    Args:
        username: Username
        password: Plain text password

    Returns:
        Tuple of (success, token or error_message)
    """
    user = user_db.get_user_by_username(username)
    if not user:
        return False, "Invalid username or password"

    if not verify_password(password, user["password_hash"]):
        return False, "Invalid username or password"

    token = create_token(user["user_id"])
    return True, token


def get_user_info(user_id: str) -> dict | None:
    """
    Get user information by user_id from SQLite database.

    Args:
        user_id: User ID to search for

    Returns:
        User info dictionary (without password_hash) or None if not found
    """
    user = user_db.get_user_by_id(user_id)
    if not user:
        return None

    # Return user info without password hash
    return {
        "user_id": user["user_id"],
        "username": user["username"],
        "email": user["email"],
        "created_at": user["created_at"],
        "is_admin": user["is_admin"],
    }


# --- Task Execution Functions ---


async def _execute_web_chat_task(task, user_id: str) -> None:
    """
    Execute a task created from web chat interface.
    Runs task through Claude session pool and updates task status.
    Emits real-time updates to user via SocketIO.

    Args:
        task: Task object to execute
        user_id: User ID for SocketIO notifications
    """
    try:
        # Update task status
        await task_manager.update_task(task.task_id, status="running")
        logger.info(f"Starting web chat task execution: {task.task_id} in {task.workspace}")

        # Emit task started notification
        socketio.emit(
            "task_update",
            {
                "task_id": task.task_id,
                "status": "running",
                "message": "Task execution started",
            },
            room=user_id,
        )

        workspace_path = Path(task.workspace)

        # Define PID callback to save PID immediately when process starts
        def save_pid_immediately(pid: int):
            """Called by claude_pool as soon as process starts"""
            asyncio.create_task(task_manager.update_task(task.task_id, pid=pid))
            logger.info(f"Task {task.task_id} process started with PID {pid}")

        # Define progress callback to log activity and notify user
        def send_progress_update(status_message: str, elapsed_seconds: int):
            """Called periodically with progress updates"""
            # Extract output line count if present
            output_lines = None
            if "output lines" in status_message:
                import re

                match = re.search(r"(\d+) output lines", status_message)
                if match:
                    output_lines = int(match.group(1))

            # Log to task manager
            asyncio.create_task(task_manager.log_activity(task.task_id, status_message, output_lines, save=True))

            # Emit progress update to user
            socketio.emit(
                "task_progress",
                {
                    "task_id": task.task_id,
                    "status": "running",
                    "message": status_message,
                    "elapsed_seconds": elapsed_seconds,
                },
                room=user_id,
            )

        # Execute using Claude session pool
        success, result, pid, workflow = await claude_pool.execute_task(
            task_id=task.task_id,
            description=task.description,
            workspace=workspace_path,
            bot_repo_path=BOT_REPOSITORY,
            model=task.model,
            context=task.context,
            pid_callback=save_pid_immediately,
            progress_callback=send_progress_update,
        )

        # Update task with result
        if success:
            await task_manager.update_task(task.task_id, status="completed", result=result, workflow=workflow)
            logger.info(f"Task {task.task_id} completed successfully")

            # Notify user of completion
            socketio.emit(
                "task_complete",
                {
                    "task_id": task.task_id,
                    "status": "completed",
                    "message": "Task completed successfully",
                    "result": result[:500] if result else "",  # Send preview
                },
                room=user_id,
            )
        else:
            await task_manager.update_task(task.task_id, status="failed", error=result, workflow=workflow)
            logger.error(f"Task {task.task_id} failed: {result}", exc_info=True)

            # Notify user of failure
            socketio.emit(
                "task_failed",
                {
                    "task_id": task.task_id,
                    "status": "failed",
                    "message": "Task failed",
                    "error": result[:500] if result else "Unknown error",
                },
                room=user_id,
            )

    except Exception as e:
        logger.error(f"Error executing web chat task {task.task_id}: {e}", exc_info=True)
        await task_manager.update_task(task.task_id, status="failed", error=str(e))

        # Notify user of error
        socketio.emit(
            "task_failed",
            {
                "task_id": task.task_id,
                "status": "failed",
                "message": "Task execution error",
                "error": str(e)[:500],
            },
            room=user_id,
        )


# --- WebSocket Event Handlers ---


@socketio.on("connect")
def handle_connect(auth_data):
    """Client connected - verify JWT token, allow no-auth mode, or allow dashboard monitoring."""
    try:
        token = auth_data.get("token") if isinstance(auth_data, dict) else None

        if not token:
            # Allow connection without token for dashboard monitoring (read-only)
            logger.info("Dashboard monitoring connection (no auth)")
            emit("connected", {"message": "Connected to dashboard monitoring"})
            return True

        # Check if it's a dummy token (no-auth mode for web chat)
        if token.startswith("dummy-token-"):
            # Extract user_id from dummy token
            user_id = token.replace("dummy-token-", "")
            logger.info(f"No-auth mode: Auto-authenticating user {user_id}")
        else:
            # Real JWT token authentication
            user_id = verify_token(token)
            if not user_id:
                logger.warning("Connection attempt with invalid token")
                return False

        # Store user_id in Flask session
        session["user_id"] = user_id
        join_room(user_id)  # Join user-specific room

        logger.info(f"User {user_id} connected via WebSocket")
        emit("connected", {"user_id": user_id, "message": "Connected successfully"})

    except Exception as e:
        logger.error(f"Connection error: {e}", exc_info=True)
        return False


@socketio.on("disconnect")
def handle_disconnect():
    """Client disconnected."""
    try:
        user_id = session.get("user_id")
        if user_id:
            leave_room(user_id)
            logger.info(f"User {user_id} disconnected")
    except Exception as e:
        logger.error(f"Disconnect error: {e}", exc_info=True)


async def _handle_message_async(data, user_id: str):
    """Async handler for client messages."""
    if not user_id:
        socketio.emit("error", {"message": "Unauthorized - please reconnect"})
        return

    message_text = data.get("message")
    if not message_text:
        socketio.emit("error", {"message": "Empty message"}, room=user_id)
        return

    # Check if message is a command
    if message_text.strip().startswith('/'):
        command = message_text.strip()
        
        # Handle commands that don't go through Claude
        if command.split()[0] in ['/status', '/stop', '/stopall', '/retry', '/view']:
            logger.info(f"User {user_id}: Command {command[:100]}")
            result = await command_handler.handle_command(command, user_id)
            
            # Check if we need to retry a task
            if result.get('data', {}).get('action') == 'retry':
                task = result['data']['task']
                # Re-create and submit the task
                new_task = await task_manager.create_task(
                    user_id=user_id,
                    description=task.description,
                    workspace=task.workspace,
                    model=task.model,
                    agent_type=task.agent_type,
                    context=task.context,
                )
                await agent_pool.submit(_execute_web_chat_task, new_task, user_id, priority=TaskPriority.HIGH)
                result['message'] += f" (New task #{new_task.task_id})"
            
            # Send command result
            socketio.emit("command_result", result, room=user_id)
            return

        logger.info(f"User {user_id}: {message_text[:100]}")

    # Get session history
    session_obj = session_manager.get_or_create_session(user_id)
    history = [{"role": msg.role, "content": msg.content} for msg in session_obj.history[-10:]]  # Last 10 messages

    # Add user message to history
    session_manager.add_message(user_id, "user", message_text)

    # Import here to avoid circular dependency
    from claude.api_client import ask_claude
    from core.orchestrator import discover_repositories

    # Call Claude API asynchronously
    response, background_task_info, usage_info = await ask_claude(
        user_query=message_text,
        input_method="text",
        conversation_history=history,
        current_workspace=session_manager.get_workspace(user_id) or workspace_path,
        bot_repository=BOT_REPOSITORY,
        workspace_path=workspace_path,
        available_repositories=discover_repositories(workspace_path) if workspace_path else [],
        active_tasks=task_manager.get_active_tasks(user_id),
    )

    # Log user message to analytics database
    analytics_db.log_message(
        user_id=user_id,
        role="user",
        content=message_text,
        input_method="text",
    )

    # Log assistant response to analytics database (if we got usage info)
    if usage_info:
        analytics_db.log_message(
            user_id=user_id,
            role="assistant",
            content=response,
            tokens_input=usage_info.get("input_tokens"),
            tokens_output=usage_info.get("output_tokens"),
            model="claude-haiku-4-5",
            input_method="text",
        )

    # Add assistant response to history
    session_manager.add_message(user_id, "assistant", response)

    # Check if background task needed
    if background_task_info:
        # Create task - TaskManager provides defaults for model and agent_type
        task_params = {
            "user_id": user_id,
            "description": background_task_info["description"],
            "workspace": session_manager.get_workspace(user_id) or BOT_REPOSITORY,
        }

        # Add optional parameters if provided
        if "model" in background_task_info:
            task_params["model"] = background_task_info["model"]
        if "agent_type" in background_task_info:
            task_params["agent_type"] = background_task_info["agent_type"]
        if "context" in background_task_info and background_task_info["context"]:
            task_params["context"] = background_task_info["context"]

        task = await task_manager.create_task(**task_params)

        logger.info(f"Created task {task.task_id} for user {user_id}")

        # Submit task to agent pool (same as Telegram bot)
        await agent_pool.submit(_execute_web_chat_task, task, user_id, priority=TaskPriority.HIGH)
        logger.info(f"Submitted task {task.task_id} to agent pool for execution")

        # Always append task number to the user message
        user_message = background_task_info.get("user_message", "Task created")
        if f"#{task.task_id}" not in user_message and f"Task {task.task_id}" not in user_message:
            user_message = f"{user_message} (Task #{task.task_id})"

        # Notify user
        socketio.emit(
            "response",
            {
                "message": user_message,
                "task_id": task.task_id,
                "type": "task_started",
            },
            room=user_id,
        )
    else:
        # Direct response
        socketio.emit("response", {"message": response, "type": "direct"}, room=user_id)


@socketio.on("message")
def handle_message(data):
    """Client sent a message - sync wrapper for async handler."""
    try:
        # Get user_id from Flask session BEFORE entering async context
        user_id = session.get("user_id")
        if not user_id:
            emit("error", {"message": "Unauthorized - please reconnect"})
            return

        # Use the agent pool's event loop to ensure tasks run in same context
        global _agent_pool_loop
        if _agent_pool_loop is None:
            logger.error("Agent pool not started - cannot process message", exc_info=True)
            emit("error", {"message": "Server not ready"})
            return

        # Schedule coroutine in agent pool's event loop and wait for result
        future = asyncio.run_coroutine_threadsafe(_handle_message_async(data, user_id), _agent_pool_loop)
        future.result(timeout=300)  # 5 min timeout
    except Exception as e:
        logger.error(f"Error handling message: {e}", exc_info=True)
        user_id = session.get("user_id")
        if user_id:
            socketio.emit("error", {"message": f"Error processing message: {str(e)}"}, room=user_id)
        else:
            emit("error", {"message": f"Error processing message: {str(e)}"})


@socketio.on("typing")
def handle_typing(data):
    """Client is typing - broadcast to workspace members (future feature)."""
    try:
        user_id = session.get("user_id")
        if not user_id:
            return

        logger.debug(f"User {user_id} is typing")

    except Exception as e:
        logger.error(f"Error handling typing: {e}", exc_info=True)


@socketio.on("ping")
def handle_ping():
    """Keepalive ping."""
    emit("pong", {"timestamp": time.time()})


# --- Helper Functions ---


def check_task_has_output_file(task_id: str) -> bool:
    """Check if a task has an output .md file in its session directory"""
    try:
        workspace_path_env = os.getenv("WORKSPACE_PATH", "/Users/matifuentes/Workspace")
        possible_locations = [
            Path(sessions_dir) / task_id,  # Local (agentlab/logs/sessions/)
            Path(workspace_path_env) / "logs" / "sessions" / task_id,  # Workspace
        ]

        for loc in possible_locations:
            if loc.exists():
                md_files = list(loc.glob("*.md"))
                if md_files:
                    return True
        return False
    except Exception:
        return False


def get_task_token_usage(task_id: str) -> dict[str, int]:
    """
    Get aggregated token usage for a task from tool_usage table.

    Args:
        task_id: Task ID to query

    Returns:
        Dictionary with token usage totals:
        - input_tokens
        - output_tokens
        - cache_creation_tokens
        - cache_read_tokens
    """
    try:
        cursor = task_manager.db.conn.cursor()
        cursor.execute(
            """
            SELECT
                COALESCE(SUM(input_tokens), 0) as total_input_tokens,
                COALESCE(SUM(output_tokens), 0) as total_output_tokens,
                COALESCE(SUM(cache_creation_tokens), 0) as total_cache_creation_tokens,
                COALESCE(SUM(cache_read_tokens), 0) as total_cache_read_tokens
            FROM tool_usage
            WHERE task_id = ?
            """,
            (task_id,),
        )

        row = cursor.fetchone()
        if row:
            return {
                "input_tokens": row[0],
                "output_tokens": row[1],
                "cache_creation_tokens": row[2],
                "cache_read_tokens": row[3],
            }
        else:
            return {
                "input_tokens": 0,
                "output_tokens": 0,
                "cache_creation_tokens": 0,
                "cache_read_tokens": 0,
            }
    except Exception as e:
        logger.warning(f"Error getting token usage for task {task_id}: {e}")
        return {
            "input_tokens": 0,
            "output_tokens": 0,
            "cache_creation_tokens": 0,
            "cache_read_tokens": 0,
        }


# --- HTTP Routes ---


@app.route("/")
def index():
    """Serve the main dashboard"""
    return render_template("dashboard.html")


@app.route("/chat")
@app.route("/chat/")
def chat_view():
    """Serve the chat interface (React app)"""
    # Static files are at project root, not monitoring/
    chat_static_dir = Path(__file__).parent.parent / "static" / "chat"
    return send_from_directory(chat_static_dir, "index.html")


@app.route("/chat/<path:filename>")
def chat_files(filename):
    """Serve chat app static files (favicon, manifest, etc)"""
    # Static files are at project root, not monitoring/
    chat_static_dir = Path(__file__).parent.parent / "static" / "chat"
    return send_from_directory(chat_static_dir, filename)


# --- Authentication API Endpoints ---


@app.route("/api/auth/register", methods=["POST"])
def auth_register():
    """Register a new user."""
    try:
        data = request.json
        username = data.get("username")
        email = data.get("email")
        password = data.get("password")

        if not all([username, email, password]):
            return jsonify({"error": "Missing required fields"}), 400

        success, result = register_user(username, email, password)
        if success:
            token = create_token(result)
            user_info = get_user_info(result)
            return jsonify({"token": token, "user": user_info})
        else:
            return jsonify({"error": result}), 400

    except Exception as e:
        logger.error(f"Registration error: {e}", exc_info=True)
        return jsonify({"error": "Internal server error"}), 500


@app.route("/api/auth/login", methods=["POST"])
def auth_login():
    """Login an existing user."""
    try:
        data = request.json
        username = data.get("username")
        password = data.get("password")

        if not all([username, password]):
            return jsonify({"error": "Missing required fields"}), 400

        success, result = login_user(username, password)
        if success:
            # result is the JWT token, decode it to get user_id
            user_id = verify_token(result)
            user_info = get_user_info(user_id)
            return jsonify({"token": result, "user": user_info})
        else:
            return jsonify({"error": result}), 401

    except Exception as e:
        logger.error(f"Login error: {e}", exc_info=True)
        return jsonify({"error": "Internal server error"}), 500


@app.route("/api/auth/verify", methods=["GET"])
def auth_verify():
    """Verify JWT token and return user info."""
    try:
        token = request.headers.get("Authorization", "").replace("Bearer ", "")
        user_id = verify_token(token)

        if not user_id:
            return jsonify({"error": "Invalid or expired token"}), 401

        user_info = get_user_info(user_id)
        if not user_info:
            return jsonify({"error": "User not found"}), 404

        return jsonify(user_info)

    except Exception as e:
        logger.error(f"Token verification error: {e}", exc_info=True)
        return jsonify({"error": "Internal server error"}), 500


# --- Chat API Endpoints ---


@app.route("/api/chat/history", methods=["GET"])
def chat_history():
    """Get chat history for authenticated user."""
    try:
        token = request.headers.get("Authorization", "").replace("Bearer ", "")
        user_id = verify_token(token)

        if not user_id:
            return jsonify({"error": "Unauthorized"}), 401

        session_obj = session_manager.get_or_create_session(user_id)
        history = [
            {"role": msg.role, "content": msg.content, "timestamp": msg.timestamp} for msg in session_obj.history
        ]

        return jsonify({"history": history})

    except Exception as e:
        logger.error(f"Error getting history: {e}", exc_info=True)
        return jsonify({"error": "Internal server error"}), 500


@app.route("/api/chat/clear", methods=["POST"])
def chat_clear():
    """Clear chat history for authenticated user."""
    try:
        token = request.headers.get("Authorization", "").replace("Bearer ", "")
        user_id = verify_token(token)

        if not user_id:
            return jsonify({"error": "Unauthorized"}), 401

        session_manager.clear_session(user_id)
        return jsonify({"success": True})

    except Exception as e:
        logger.error(f"Error clearing history: {e}", exc_info=True)
        return jsonify({"error": "Internal server error"}), 500


# --- User Task API Endpoints ---


@app.route("/api/user/tasks", methods=["GET"])
def user_tasks():
    """Get active tasks for authenticated user."""
    try:
        token = request.headers.get("Authorization", "").replace("Bearer ", "")
        user_id = verify_token(token)

        if not user_id:
            return jsonify({"error": "Unauthorized"}), 401

        tasks = task_manager.get_active_tasks(user_id)
        tasks_with_tokens = []
        for task in tasks:
            token_usage = get_task_token_usage(task.task_id)
            tasks_with_tokens.append(
                {
                    "task_id": task.task_id,
                    "description": task.description,
                    "status": task.status,
                    "created_at": task.created_at,
                    "workspace": task.workspace,
                    "model": task.model,
                    "token_usage": token_usage,
                }
            )

        return jsonify({"tasks": tasks_with_tokens})

    except Exception as e:
        logger.error(f"Error getting tasks: {e}", exc_info=True)
        return jsonify({"error": "Internal server error"}), 500


@app.route("/api/user/tasks/<task_id>", methods=["GET"])
def user_task_detail(task_id):
    """Get specific task by ID for authenticated user."""
    try:
        token = request.headers.get("Authorization", "").replace("Bearer ", "")
        user_id = verify_token(token)

        if not user_id:
            return jsonify({"error": "Unauthorized"}), 401

        task = task_manager.get_task(task_id)
        if not task or task.user_id != user_id:
            return jsonify({"error": "Task not found"}), 404

        # Get token usage for this task
        token_usage = get_task_token_usage(task_id)

        return jsonify(
            {
                "task_id": task.task_id,
                "description": task.description,
                "status": task.status,
                "created_at": task.created_at,
                "updated_at": task.updated_at,
                "workspace": task.workspace,
                "model": task.model,
                "result": task.result,
                "error": task.error,
                "token_usage": token_usage,
            }
        )

    except Exception as e:
        logger.error(f"Error getting task: {e}", exc_info=True)
        return jsonify({"error": "Internal server error"}), 500


@app.route("/api/tasks/<task_id>/stop", methods=["POST"])
def stop_task(task_id):
    """
    Stop a running task by terminating its Claude CLI session.
    
    The task status will be updated to 'stopped' and any partial progress
    will be preserved in the tool usage logs.
    
    Returns:
        200: Task stop requested successfully
        404: Task not found or not running
        500: Internal server error
    """
    try:
        logger.info(f"Stop request received for task {task_id}")
        
        # Use asyncio to call the async terminate_session method
        global _agent_pool_loop
        if _agent_pool_loop is None:
            logger.error("Agent pool event loop not available")
            return jsonify({"error": "Server not ready"}), 503
        
        async def stop_task_async():
            """Terminate the Claude session for this task"""
            success = await claude_pool.terminate_session(task_id)
            return success
        
        # Execute in agent pool's event loop
        future = asyncio.run_coroutine_threadsafe(stop_task_async(), _agent_pool_loop)
        success = future.result(timeout=5)  # 5s timeout
        
        if success:
            # Emit stop event to all connected clients
            socketio.emit(
                "task_stopped",
                {
                    "task_id": task_id,
                    "message": "Task stopped by user",
                    "timestamp": datetime.now().isoformat()
                }
            )
            
            logger.info(f"Task {task_id} stopped successfully")
            return jsonify({
                "success": True,
                "message": "Task stopped successfully"
            })
        else:
            logger.warning(f"Task {task_id} not found in active sessions")
            return jsonify({
                "error": "Task not found or not running"
            }), 404
            
    except Exception as e:
        logger.error(f"Error stopping task {task_id}: {e}", exc_info=True)
        return jsonify({"error": f"Failed to stop task: {str(e)}"}), 500


@app.route("/api/tasks", methods=["POST"])
def create_task():
    """
    Create a new task from API request.

    Accepts JSON payload:
    {
        "prompt": "Task description/prompt",
        "workspace": "/path/to/workspace" (optional, defaults to BOT_REPOSITORY),
        "model": "sonnet" or "haiku" (optional, defaults to "sonnet"),
        "agent_type": "orchestrator" or "code_agent" (optional, defaults to "orchestrator"),
        "context": "Additional context for task" (optional)
    }

    Returns:
    {
        "task_id": "abc123",
        "status": "pending",
        "message": "Task created and submitted for execution"
    }
    """
    try:
        # Authenticate user
        token = request.headers.get("Authorization", "").replace("Bearer ", "")
        user_id = verify_token(token)

        if not user_id:
            return jsonify({"error": "Unauthorized"}), 401

        # Get request data
        data = request.json
        if not data:
            return jsonify({"error": "No data provided"}), 400

        prompt = data.get("prompt")
        if not prompt:
            return jsonify({"error": "Missing required field: prompt"}), 400

        # Get optional parameters with defaults
        workspace = data.get("workspace", BOT_REPOSITORY)
        model = data.get("model", "sonnet")
        agent_type = data.get("agent_type", "orchestrator")
        context = data.get("context")

        # Validate model
        if model not in ["sonnet", "haiku", "opus"]:
            return jsonify({"error": "Invalid model. Must be 'sonnet', 'haiku', or 'opus'"}), 400

        # Validate agent_type
        if agent_type not in ["orchestrator", "code_agent", "frontend_agent", "research_agent"]:
            return jsonify({"error": "Invalid agent_type"}), 400

        # Validate workspace exists
        workspace_path = Path(workspace)
        if not workspace_path.exists():
            return jsonify({"error": f"Workspace does not exist: {workspace}"}), 400

        # Create task using asyncio
        global _agent_pool_loop
        if _agent_pool_loop is None:
            return jsonify({"error": "Server not ready - agent pool not started"}), 503

        async def create_and_submit_task():
            """Create task and submit to agent pool"""
            # Create task in database
            task = await task_manager.create_task(
                user_id=int(user_id),
                description=prompt,
                workspace=str(workspace_path),
                model=model,
                agent_type=agent_type,
                context=context,
            )

            # Submit task to agent pool for execution
            await agent_pool.submit(
                _execute_web_chat_task,
                task,
                user_id,
                priority=TaskPriority.HIGH,
            )

            return task

        # Execute in agent pool's event loop
        future = asyncio.run_coroutine_threadsafe(create_and_submit_task(), _agent_pool_loop)
        task = future.result(timeout=30)  # 30s timeout for task creation

        logger.info(f"API: Created task {task.task_id} for user {user_id}: {prompt[:100]}")

        return jsonify({
            "task_id": task.task_id,
            "status": "pending",
            "message": "Task created and submitted for execution",
            "workspace": str(workspace_path),
            "model": model,
            "agent_type": agent_type,
        }), 201

    except asyncio.TimeoutError:
        logger.error("Timeout creating task via API", exc_info=True)
        return jsonify({"error": "Task creation timed out"}), 504
    except Exception as e:
        logger.error(f"Error creating task via API: {e}", exc_info=True)
        return jsonify({"error": f"Internal server error: {str(e)}"}), 500


# --- Monitoring API Endpoints (Existing) ---


@app.route("/api/metrics/overview")
def metrics_overview():
    """Get overview of all metrics"""
    try:
        # Reload tasks to get latest state
        task_manager.reload_tasks()

        hours = int(request.args.get("hours", 24))
        snapshot = metrics_aggregator.get_complete_snapshot(hours=hours)
        return jsonify(snapshot.to_dict())
    except Exception as e:
        logger.error(f"Error getting metrics overview: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route("/api/metrics/claude-api")
def claude_api_metrics():
    """Get Claude API usage metrics"""
    try:
        hours = int(request.args.get("hours", 24))
        metrics = metrics_aggregator.get_claude_api_metrics(hours=hours)
        return jsonify(metrics)
    except Exception as e:
        logger.error(f"Error getting Claude API metrics: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route("/api/metrics/tasks")
def task_metrics():
    """Get task execution metrics"""
    try:
        # Reload tasks to get latest state
        task_manager.reload_tasks()
        metrics = metrics_aggregator.get_task_statistics()
        return jsonify(metrics)
    except Exception as e:
        logger.error(f"Error getting task metrics: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route("/api/tasks/<task_id>/tool-usage")
def task_tool_usage(task_id):
    """Get tool usage for a specific task from SQLite database and session files"""
    try:
        from collections import defaultdict

        # End any stale read transaction to see latest writes
        task_manager.db.conn.rollback()

        # Get session_uuid for this task (needed for tool_usage correlation)
        task = task_manager.db.get_task(task_id)
        session_uuid = task.get("session_uuid") if task else None

        # Query tool_usage with session_uuid if available, fallback to task_id
        # (session_uuid is Claude's UUID, task_id is short ID for background tasks)
        query_id = session_uuid if session_uuid else task_id

        # Get tool usage from database
        cursor = task_manager.db.conn.cursor()
        cursor.execute(
            """
            SELECT timestamp, tool_name, success, error, parameters
            FROM tool_usage
            WHERE task_id = ?
            ORDER BY timestamp
            """,
            (query_id,),
        )

        # Collect all raw records first
        raw_records = []
        for row in cursor.fetchall():
            timestamp = row[0]
            tool_name = row[1]
            success = row[2]
            error = row[3]
            parameters_json = row[4]

            # Parse parameters JSON
            parameters = {}
            if parameters_json:
                try:
                    parameters = json.loads(parameters_json)
                except json.JSONDecodeError:
                    logger.warning(f"Failed to parse parameters JSON for {tool_name}: {parameters_json[:100]}")

            raw_records.append({
                "timestamp": timestamp,
                "tool_name": tool_name,
                "success": success,
                "error": error,
                "parameters": parameters,
            })

        # Deduplicate: For each tool call, keep only the completed record (success != NULL)
        # Group by (tool_name, timestamp_prefix) where timestamp_prefix is first 19 chars (YYYY-MM-DDTHH:MM:SS)
        # This groups pre+post hook entries for the same tool call
        from collections import defaultdict
        tool_groups = defaultdict(list)
        for record in raw_records:
            # Group key: tool_name + timestamp prefix (to second precision)
            timestamp_prefix = record["timestamp"][:19] if len(record["timestamp"]) >= 19 else record["timestamp"]
            key = (record["tool_name"], timestamp_prefix)
            tool_groups[key].append(record)

        # For each group, prefer completed records (success != NULL) over in-progress (success = NULL)
        tool_calls = []
        tools_by_type = defaultdict(int)
        tools_with_errors = 0
        worker_chain = []

        for (tool_name, timestamp_prefix), records in tool_groups.items():
            # If multiple records, prefer completed (success != NULL) over in-progress (success = NULL)
            completed = [r for r in records if r["success"] is not None]
            record = completed[0] if completed else records[0]

            # Build tool call entry (match real-time WebSocket format)
            entry = {
                "timestamp": record["timestamp"],
                "tool_name": record["tool_name"],
                "tool": record["tool_name"],  # Keep for backward compatibility
                "success": record["success"],
                "has_error": record["success"] is False,
                "error": record["error"],
                "output_preview": record["error"] if record["error"] else None,
                "parameters": record["parameters"],
                "in_progress": record["success"] is None,
                "duration_ms": 0,
            }
            tool_calls.append(entry)

            # Count by type
            tools_by_type[record["tool_name"]] += 1

            # Count errors (only actual failures, not in-progress)
            if record["success"] is False:
                tools_with_errors += 1

            # Track worker spawning (Task tool calls)
            if record["tool_name"] == "Task":
                worker_chain.append(
                    {
                        "worker": "unknown",
                        "description": "Task agent spawned",
                        "timestamp": record["timestamp"],
                    }
                )

        # Sort by timestamp for display order
        tool_calls.sort(key=lambda x: x["timestamp"])

        # Try to enrich with output_preview from session JSONL files
        # This is especially important for TodoWrite calls to show planning progress
        workspace_path_env = os.getenv("WORKSPACE_PATH", "/Users/matifuentes/Workspace")
        possible_locations = [
            Path(sessions_dir) / task_id,  # Local (agentlab/logs/sessions/)
            Path(workspace_path_env) / "logs" / "sessions" / task_id,  # Workspace
        ]

        session_dir = None
        for loc in possible_locations:
            if loc.exists():
                session_dir = loc
                break

        if session_dir:
            post_tool_file = session_dir / "post_tool_use.jsonl"
            if post_tool_file.exists():
                # Read session file and create a lookup by timestamp
                session_tool_data = {}
                try:
                    with open(post_tool_file) as f:
                        for line in f:
                            if line.strip():
                                entry = json.loads(line)
                                # Use timestamp as key (they should match between DB and JSONL)
                                session_tool_data[entry.get("timestamp")] = entry
                except Exception as e:
                    logger.warning(f"Error reading session file for task {task_id}: {e}")

                # Enrich tool_calls with output_preview from session data
                enriched_count = 0
                for call in tool_calls:
                    session_entry = session_tool_data.get(call["timestamp"])
                    if session_entry and session_entry.get("output_preview"):
                        # Always use session data for output_preview (it has richer data than DB)
                        call["output_preview"] = session_entry["output_preview"]
                        # Also update output_length if available
                        if "output_length" in session_entry:
                            call["output_length"] = session_entry["output_length"]
                        enriched_count += 1

                logger.debug(
                    f"Enriched {enriched_count}/{len(tool_calls)} tool calls with session data for task {task_id}"
                )

        # Build summary
        summary = {
            "task_id": task_id,
            "total_tools_used": len(tool_calls),
            "tools_by_type": dict(tools_by_type),
            "blocked_operations": 0,  # Not tracked in DB yet
            "tools_with_errors": tools_with_errors,
        }

        return jsonify(
            {
                "task_id": task_id,
                "summary": summary,
                "tool_calls": tool_calls,
                "worker_chain": worker_chain,
                "has_logs": len(tool_calls) > 0,
            }
        )
    except Exception as e:
        logger.error(f"Error getting tool usage for task {task_id}: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route("/api/tasks/activity")
def task_activity():
    """Get recent task activity for live feed"""
    try:
        limit = int(request.args.get("limit", 8))
        user_id = request.args.get("user_id")  # Optional filter by user

        # End any stale read transaction to see latest writes
        task_manager.db.conn.rollback()

        # Get tasks from database
        cursor = task_manager.db.conn.cursor()
        if user_id:
            cursor.execute(
                """
                SELECT task_id, description, status, activity_log, updated_at
                FROM tasks
                WHERE user_id = ?
                ORDER BY updated_at DESC
                LIMIT ?
            """,
                (int(user_id), limit),
            )
        else:
            cursor.execute(
                """
                SELECT task_id, description, status, activity_log, updated_at
                FROM tasks
                ORDER BY updated_at DESC
                LIMIT ?
            """,
                (limit,),
            )

        # Build activity feed from task activity logs
        activity_feed = []
        for row in cursor.fetchall():
            task_id, description, status, activity_log_json, updated_at = row
            activity_log = json.loads(activity_log_json) if activity_log_json else []

            # Add each activity entry
            if activity_log:
                for activity in reversed(activity_log[-10:]):  # Last 10 per task
                    activity_feed.append(
                        {
                            "task_id": task_id,
                            "description": description[:50],
                            "status": status,
                            "timestamp": activity["timestamp"],
                            "message": activity["message"],
                            "output_lines": activity.get("output_lines"),
                        }
                    )

        # Sort all activity by timestamp (most recent first)
        activity_feed.sort(key=lambda x: x["timestamp"], reverse=True)

        return jsonify({"activity": activity_feed[:limit], "total": len(activity_feed)})

    except Exception as e:
        logger.error(f"Error getting task activity: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route("/api/metrics/tools")
def tool_metrics():
    """Get tool usage metrics from SQLite database"""
    try:
        hours = int(request.args.get("hours", 24))

        # Get tool statistics from database
        db_stats = tool_usage_tracker.get_tool_statistics(hours=hours)

        # Convert to expected format
        tools_breakdown = {tool: stats["count"] for tool, stats in db_stats["tools"].items()}
        most_used = sorted(
            [
                {
                    "tool": tool,
                    "count": stats["count"],
                    "success_rate": stats["success_rate"] * 100,
                    "avg_duration_ms": stats.get("avg_duration_ms", 0.0),
                }
                for tool, stats in db_stats["tools"].items()
            ],
            key=lambda x: x["count"],
            reverse=True,
        )[:10]

        # Get agent status from ToolUsageTracker
        status_summary = tool_usage_tracker.get_agent_status_summary()

        return jsonify(
            {
                "time_window_hours": hours,
                "total_tool_calls": db_stats["total_calls"],
                "tools_breakdown": tools_breakdown,
                "most_used_tools": most_used,
                "agent_status": status_summary,
            }
        )
    except Exception as e:
        logger.error(f"Error getting tool metrics: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route("/api/metrics/hooks")
def hook_metrics():
    """Get hook usage metrics from Claude Code hook logs"""
    try:
        hours = int(request.args.get("hours", 24))
        stats = hooks_reader.get_aggregate_statistics(hours=hours)
        return jsonify(stats)
    except Exception as e:
        logger.error(f"Error getting hook metrics: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route("/api/hooks/sessions")
def hook_sessions():
    """Get list of all hook sessions"""
    try:
        sessions = hooks_reader.get_all_sessions()
        return jsonify({"sessions": sessions, "total": len(sessions)})
    except Exception as e:
        logger.error(f"Error getting sessions: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route("/api/hooks/session/<session_id>")
def hook_session_detail(session_id: str):
    """Get detailed timeline for a specific session"""
    try:
        summary = hooks_reader.read_session_summary(session_id)
        timeline = hooks_reader.get_session_timeline(session_id)

        if not summary:
            return jsonify({"error": "Session not found"}), 404

        return jsonify(
            {
                "session_id": session_id,
                "summary": {
                    "total_tools": summary.total_tools,
                    "tools_by_type": summary.tools_by_type,
                    "blocked_operations": summary.blocked_operations,
                    "tools_with_errors": summary.tools_with_errors,
                },
                "timeline": timeline,
            }
        )
    except Exception as e:
        logger.error(f"Error getting session detail: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route("/api/metrics/system")
def system_health():
    """Get system health metrics"""
    try:
        metrics = metrics_aggregator.get_system_health()
        return jsonify(metrics)
    except Exception as e:
        logger.error(f"Error getting system health: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route("/api/metrics/timeseries")
def timeseries_data():
    """Get time-series data for charts"""
    try:
        hours = int(request.args.get("hours", 24))
        interval = int(request.args.get("interval", 60))
        data = metrics_aggregator.get_time_series_data(hours=hours, interval_minutes=interval)
        return jsonify(data)
    except Exception as e:
        logger.error(f"Error getting timeseries data: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route("/api/metrics/claude-sessions")
def claude_sessions_metrics():
    """Get Claude Code session metrics from database"""
    try:
        hours = int(request.args.get("hours", 24))
        cutoff_time = (datetime.now() - timedelta(hours=hours)).isoformat()

        # End any stale read transaction
        task_manager.db.conn.rollback()
        cursor = task_manager.db.conn.cursor()

        # Get total sessions (distinct task_ids with tool usage in timeframe)
        cursor.execute(
            """
            SELECT COUNT(DISTINCT task_id)
            FROM tool_usage
            WHERE timestamp >= ?
        """,
            (cutoff_time,),
        )
        total_sessions = cursor.fetchone()[0]

        # Get total tool calls
        cursor.execute(
            """
            SELECT COUNT(*)
            FROM tool_usage
            WHERE timestamp >= ?
        """,
            (cutoff_time,),
        )
        total_tool_calls = cursor.fetchone()[0]

        # Get tools breakdown
        cursor.execute(
            """
            SELECT tool_name, COUNT(*) as count
            FROM tool_usage
            WHERE timestamp >= ?
            GROUP BY tool_name
        """,
            (cutoff_time,),
        )
        tools_by_type = {row[0]: row[1] for row in cursor.fetchall()}

        # Get error count
        cursor.execute(
            """
            SELECT COUNT(*)
            FROM tool_usage
            WHERE timestamp >= ? AND success = 0
        """,
            (cutoff_time,),
        )
        total_errors = cursor.fetchone()[0]

        # Get recent sessions (sessions with activity, including bot tasks and CLI sessions)
        cursor.execute(
            """
            SELECT
                tool_usage.task_id,
                COUNT(*) as total_tools,
                SUM(CASE WHEN success = 0 THEN 1 ELSE 0 END) as errors,
                MAX(tool_usage.timestamp) as last_activity
            FROM tool_usage
            WHERE tool_usage.timestamp >= ?
            GROUP BY tool_usage.task_id
            ORDER BY last_activity DESC
            LIMIT 20
        """,
            (cutoff_time,),
        )

        recent_sessions = []
        for row in cursor.fetchall():
            task_id, total_tools, errors, last_activity = row
            recent_sessions.append(
                {
                    "session_id": task_id,
                    "total_tools": total_tools,
                    "blocked": 0,  # Not tracked in database yet
                    "errors": errors,
                    "last_activity": last_activity,
                }
            )

        return jsonify(
            {
                "total_sessions": total_sessions,
                "total_tool_calls": total_tool_calls,
                "tools_by_type": tools_by_type,
                "blocked_operations": 0,  # Not tracked in database yet
                "errors": total_errors,
                "time_window_hours": hours,
                "recent_sessions": recent_sessions,
            }
        )

    except Exception as e:
        logger.error(f"Error getting Claude sessions metrics: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route("/api/metrics/cli-sessions")
def cli_sessions_metrics():
    """Get active CLI sessions (excluding bot tasks) from database"""
    try:
        hours = int(request.args.get("hours", 168))  # Default 7 days
        minutes = request.args.get("minutes")  # Optional minutes filter for active sessions
        page = int(request.args.get("page", 1))
        page_size = int(request.args.get("page_size", 8))
        cutoff_time = (datetime.now() - timedelta(hours=hours)).isoformat()

        # End any stale read transaction
        task_manager.db.conn.rollback()
        cursor = task_manager.db.conn.cursor()

        # Get CLI sessions (tool usage NOT in tasks table)
        # These are user CLI sessions that aren't tracked as bot tasks
        cursor.execute(
            """
            SELECT
                tool_usage.task_id,
                COUNT(*) as tool_count,
                SUM(CASE WHEN success = 0 THEN 1 ELSE 0 END) as errors,
                MIN(tool_usage.timestamp) as start_time,
                MAX(tool_usage.timestamp) as last_activity
            FROM tool_usage
            LEFT JOIN tasks ON tool_usage.task_id = tasks.task_id
            WHERE tool_usage.timestamp >= ? AND tasks.task_id IS NULL
            GROUP BY tool_usage.task_id
            ORDER BY last_activity DESC
        """,
            (cutoff_time,),
        )

        cli_sessions = []
        for row in cursor.fetchall():
            task_id, tool_count, errors, start_time, last_activity = row

            # Calculate duration
            try:
                start_dt = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
                last_dt = datetime.fromisoformat(last_activity.replace("Z", "+00:00"))
                duration_seconds = (last_dt - start_dt).total_seconds()
            except Exception:
                duration_seconds = 0

            # Determine status based on last activity
            try:
                # Tool usage timestamps are stored as naive local time
                last_dt = datetime.fromisoformat(last_activity.replace("Z", ""))
                now = datetime.now()  # Use naive local time for comparison
                minutes_since_activity = (now - last_dt).total_seconds() / 60

                if minutes_since_activity <= 5:
                    status = "active"
                elif minutes_since_activity <= 30:
                    status = "idle"
                else:
                    status = "completed"
            except Exception:
                status = "unknown"

            # Apply minutes filter if provided
            if minutes is not None:
                try:
                    minutes_threshold = int(minutes)
                    if minutes_since_activity > minutes_threshold:
                        continue  # Skip sessions older than threshold
                except (ValueError, TypeError):
                    pass  # Invalid minutes value, ignore filter

            cli_sessions.append(
                {
                    "session_id": task_id,
                    "start_time": start_time,
                    "last_activity": last_activity,
                    "duration_seconds": int(duration_seconds),
                    "tool_count": tool_count,
                    "errors": errors,
                    "status": status,
                }
            )

        # Get summary statistics (before pagination)
        total_sessions = len(cli_sessions)
        active_count = sum(1 for s in cli_sessions if s["status"] == "active")
        idle_count = sum(1 for s in cli_sessions if s["status"] == "idle")
        total_tool_calls = sum(s["tool_count"] for s in cli_sessions)

        # Apply pagination
        offset = (page - 1) * page_size
        paginated_sessions = cli_sessions[offset : offset + page_size]

        return jsonify(
            {
                "total": total_sessions,
                "total_sessions": total_sessions,
                "active_sessions": active_count,
                "idle_sessions": idle_count,
                "total_tool_calls": total_tool_calls,
                "time_window_hours": hours,
                "sessions": paginated_sessions,
            }
        )

    except Exception as e:
        logger.error(f"Error getting CLI sessions metrics: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route("/api/sessions/<session_id>/tool-usage")
def session_tool_usage(session_id: str):
    """Get tool usage for a specific Claude Code session (user or task)"""
    try:
        from collections import defaultdict

        # STEP 1: Query database first for active sessions
        logger.debug(f"Querying database for session {session_id} tool usage")

        # End any stale read transaction to see latest writes
        task_manager.db.conn.rollback()

        db_tool_usage = task_manager.db.get_tool_usage_by_session(session_id)

        if db_tool_usage:
            # Format database results to match expected structure
            logger.info(f"Found {len(db_tool_usage)} tool usage records in database for session {session_id}")

            # Calculate summary from database records
            tools_by_type = defaultdict(int)
            tools_with_errors = 0

            tool_calls = []
            for record in db_tool_usage:
                # Add to summary
                tools_by_type[record["tool"]] += 1
                if record.get("error") or not record.get("success", True):
                    tools_with_errors += 1

                # Format for response (match JSONL structure)
                tool_calls.append(
                    {
                        "tool": record["tool"],
                        "timestamp": record["timestamp"],
                        "duration": record["duration"],
                        "has_error": bool(record.get("error")),
                        "error": record.get("error"),
                        "success": record.get("success", True),
                        "parameters": record.get("parameters"),
                        "error_category": record.get("error_category"),
                    }
                )

            summary = {
                "session_id": session_id,
                "total_tools_used": len(db_tool_usage),
                "tools_by_type": dict(tools_by_type),
                "tools_with_errors": tools_with_errors,
            }

            return jsonify(
                {
                    "session_id": session_id,
                    "summary": summary,
                    "tool_calls": tool_calls,
                    "has_logs": True,
                    "source": "database",
                }
            )

        # STEP 2: Fall back to JSONL files for completed sessions
        logger.debug(f"No database records found for session {session_id}, checking JSONL files")

        # Check multiple possible session log locations
        # 1. Local project sessions (user CLI sessions)
        # 2. Workspace sessions (bot task sessions)
        workspace_path_env = os.getenv("WORKSPACE_PATH", "/Users/matifuentes/Workspace")
        possible_locations = [
            Path(sessions_dir) / session_id,  # Local (agentlab/logs/sessions/)
            Path(workspace_path_env) / "logs" / "sessions" / session_id,  # Workspace
        ]

        session_dir = None
        for loc in possible_locations:
            if loc.exists():
                session_dir = loc
                break

        # Check if session directory exists in any location
        if session_dir is None:
            logger.warning(f"No session logs found for {session_id} in database or JSONL files")
            return jsonify({"error": "No session logs found"}), 404

        summary_file = session_dir / "summary.json"
        post_tool_file = session_dir / "post_tool_use.jsonl"

        # Read or generate summary
        if summary_file.exists():
            with open(summary_file) as f:
                summary = json.load(f)
        else:
            # Generate summary from JSONL files for completed sessions
            summary = {
                "session_id": session_id,
                "total_tools_used": 0,
                "tools_by_type": {},
                "tools_with_errors": 0,
            }

            if post_tool_file.exists():
                tools_by_type = defaultdict(int)
                tools_with_errors = 0
                with open(post_tool_file) as f:
                    for line in f:
                        if line.strip():
                            entry = json.loads(line)
                            tool = entry.get("tool", "unknown")
                            tools_by_type[tool] += 1
                            if entry.get("has_error", False):
                                tools_with_errors += 1

                summary["total_tools_used"] = sum(tools_by_type.values())
                summary["tools_by_type"] = dict(tools_by_type)
                summary["tools_with_errors"] = tools_with_errors

        # Read detailed tool calls
        tool_calls = []
        if post_tool_file.exists():
            with open(post_tool_file) as f:
                for line in f:
                    if line.strip():
                        tool_calls.append(json.loads(line))

        logger.info(f"Found {len(tool_calls)} tool usage records in JSONL files for session {session_id}")

        return jsonify(
            {
                "session_id": session_id,
                "summary": summary,
                "tool_calls": tool_calls,
                "has_logs": True,
                "source": "jsonl",
            }
        )
    except Exception as e:
        logger.error(f"Error getting tool usage for session {session_id}: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route("/api/tasks/running")
def running_tasks():
    """Get list of currently running tasks or all non-completed tasks"""
    try:
        # Get pagination parameters
        page = int(request.args.get("page", 1))
        page_size = int(request.args.get("page_size", 8))
        active_only = request.args.get("active_only", "false").lower() == "true"

        # End any stale read transaction to see latest writes
        task_manager.db.conn.rollback()

        # Get total count and paginated tasks based on active_only parameter
        cursor = task_manager.db.conn.cursor()

        # Calculate offset
        offset = (page - 1) * page_size

        if active_only:
            # Only running tasks (actively executing)
            cursor.execute("SELECT COUNT(*) FROM tasks WHERE status = 'running'")
            total = cursor.fetchone()[0]

            # Get paginated tasks
            cursor.execute(
                """
                SELECT task_id, description, status, agent_type, model, created_at, updated_at, activity_log, workflow
                FROM tasks
                WHERE status = 'running'
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
                """,
                (page_size, offset),
            )
        else:
            # All non-completed tasks (running, pending, failed, stopped)
            cursor.execute("SELECT COUNT(*) FROM tasks WHERE status != 'completed'")
            total = cursor.fetchone()[0]

            # Get paginated tasks
            cursor.execute(
                """
                SELECT task_id, description, status, agent_type, model, created_at, updated_at, activity_log, workflow
                FROM tasks
                WHERE status != 'completed'
                ORDER BY updated_at DESC
                LIMIT ? OFFSET ?
                """,
                (page_size, offset),
            )

        running = []
        for row in cursor.fetchall():
            task_id, description, status, agent_type, model, created_at, updated_at, activity_log_json, workflow = row
            activity_log = json.loads(activity_log_json) if activity_log_json else []

            # Get latest activity message
            latest_activity = None
            if activity_log and len(activity_log) > 0:
                latest_activity = activity_log[-1]["message"]

            # Get token usage for this task
            token_usage = get_task_token_usage(task_id)

            running.append(
                {
                    "task_id": task_id,
                    "description": description,
                    "status": status,
                    "worker_type": agent_type,  # Keep old name for compatibility
                    "workflow": workflow,
                    "model": model,
                    "created_at": created_at,
                    "updated_at": updated_at,
                    "latest_activity": latest_activity,
                    "token_usage": token_usage,
                }
            )

        return jsonify({"tasks": running, "total": total, "page": page, "page_size": page_size})

    except Exception as e:
        logger.error(f"Error getting running tasks: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route("/api/tasks/completed")
def completed_tasks():
    """Get list of completed tasks"""
    try:
        page = int(request.args.get("page", 1))
        page_size = int(request.args.get("page_size", 8))

        # End any stale read transaction to see latest writes
        task_manager.db.conn.rollback()

        # Get total count of completed tasks
        cursor = task_manager.db.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM tasks WHERE status = 'completed'")
        total = cursor.fetchone()[0]

        # Calculate offset
        offset = (page - 1) * page_size

        # Get paginated completed tasks from database
        cursor.execute(
            """
            SELECT task_id, description, status, agent_type, model, created_at, updated_at, activity_log, workflow
            FROM tasks
            WHERE status = 'completed'
            ORDER BY updated_at DESC
            LIMIT ? OFFSET ?
            """,
            (page_size, offset),
        )

        completed = []
        for row in cursor.fetchall():
            task_id, description, status, agent_type, model, created_at, updated_at, activity_log_json, workflow = row
            activity_log = json.loads(activity_log_json) if activity_log_json else []

            latest_activity = None
            if activity_log and len(activity_log) > 0:
                latest_activity = activity_log[-1]["message"]

            # Check if task has output file
            has_output_file = check_task_has_output_file(task_id)

            # Get token usage for this task
            token_usage = get_task_token_usage(task_id)

            completed.append(
                {
                    "task_id": task_id,
                    "description": description,
                    "status": status,
                    "worker_type": agent_type,
                    "workflow": workflow,
                    "model": model,
                    "created_at": created_at,
                    "updated_at": updated_at,
                    "latest_activity": latest_activity,
                    "has_output_file": has_output_file,
                    "token_usage": token_usage,
                }
            )

        return jsonify({"tasks": completed, "total": total, "page": page, "page_size": page_size})

    except Exception as e:
        logger.error(f"Error getting completed tasks: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route("/api/tasks/failed")
def failed_tasks():
    """Get list of failed/stopped tasks"""
    try:
        page = int(request.args.get("page", 1))
        page_size = int(request.args.get("page_size", 8))

        # End any stale read transaction to see latest writes
        task_manager.db.conn.rollback()

        # Get failed/stopped tasks from database
        cursor = task_manager.db.conn.cursor()
        cursor.execute(
            """
            SELECT task_id, description, status, agent_type, model, created_at, updated_at, activity_log, workflow
            FROM tasks
            WHERE status IN ('failed', 'stopped')
            ORDER BY updated_at DESC
        """
        )

        failed = []
        for row in cursor.fetchall():
            task_id, description, status, agent_type, model, created_at, updated_at, activity_log_json, workflow = row
            activity_log = json.loads(activity_log_json) if activity_log_json else []

            latest_activity = None
            if activity_log and len(activity_log) > 0:
                latest_activity = activity_log[-1]["message"]

            # Get token usage for this task
            token_usage = get_task_token_usage(task_id)

            failed.append(
                {
                    "task_id": task_id,
                    "description": description,
                    "status": status,
                    "worker_type": agent_type,
                    "workflow": workflow,
                    "model": model,
                    "created_at": created_at,
                    "updated_at": updated_at,
                    "latest_activity": latest_activity,
                    "token_usage": token_usage,
                }
            )

        # Apply pagination
        total = len(failed)
        start = (page - 1) * page_size
        end = start + page_size
        paginated = failed[start:end]

        return jsonify({"tasks": paginated, "total": total, "page": page, "page_size": page_size})

    except Exception as e:
        logger.error(f"Error getting failed tasks: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route("/api/tasks/all")
def all_tasks():
    """Get list of all tasks"""
    try:
        page = int(request.args.get("page", 1))
        page_size = int(request.args.get("page_size", 8))

        # End any stale read transaction to see latest writes
        task_manager.db.conn.rollback()

        # Get total count of all tasks
        cursor = task_manager.db.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM tasks")
        total = cursor.fetchone()[0]

        # Calculate offset
        offset = (page - 1) * page_size

        # Get paginated tasks from database
        cursor.execute(
            """
            SELECT task_id, description, status, agent_type, model, created_at, updated_at, activity_log, workflow
            FROM tasks
            ORDER BY updated_at DESC
            LIMIT ? OFFSET ?
            """,
            (page_size, offset),
        )

        all_tasks_list = []
        for row in cursor.fetchall():
            task_id, description, status, agent_type, model, created_at, updated_at, activity_log_json, workflow = row
            activity_log = json.loads(activity_log_json) if activity_log_json else []

            latest_activity = None
            if activity_log and len(activity_log) > 0:
                latest_activity = activity_log[-1]["message"]

            # Check if task has output file
            has_output_file = check_task_has_output_file(task_id)

            # Get token usage for this task
            token_usage = get_task_token_usage(task_id)

            all_tasks_list.append(
                {
                    "task_id": task_id,
                    "description": description,
                    "status": status,
                    "worker_type": agent_type,
                    "workflow": workflow,
                    "model": model,
                    "created_at": created_at,
                    "updated_at": updated_at,
                    "latest_activity": latest_activity,
                    "has_output_file": has_output_file,
                    "token_usage": token_usage,
                }
            )

        return jsonify({"tasks": all_tasks_list, "total": total, "page": page, "page_size": page_size})

    except Exception as e:
        logger.error(f"Error getting all tasks: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route("/api/tasks/<task_id>")
def task_detail(task_id: str):
    """Get detailed information about a specific task"""
    try:
        # Get task from database
        task_dict = task_manager.db.get_task(task_id)

        if not task_dict:
            return jsonify({"error": "Task not found"}), 404

        # Add token usage to task details
        token_usage = get_task_token_usage(task_id)
        task_dict["token_usage"] = token_usage

        return jsonify(task_dict)

    except Exception as e:
        logger.error(f"Error getting task detail: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route("/api/docs/list")
def list_docs():
    """Get list of all documentation files with status from database"""
    try:
        # Use absolute path based on server file location (project_root/docs)
        project_root = Path(__file__).parent.parent
        docs_dir = project_root / "docs"

        if not docs_dir.exists():
            return jsonify({"error": "Documentation directory not found"}), 404

        # Get status filter from query params (default: active)
        status_filter = request.args.get("status", "active")

        # Recursively find all markdown and text files
        doc_files = []
        for ext in ["*.md", "*.txt"]:
            doc_files.extend(docs_dir.rglob(ext))

        # Get document status from database
        db_docs = {doc["path"]: doc for doc in task_manager.db.list_documents()}

        # Build file tree structure
        files = []
        for file_path in sorted(doc_files):
            relative_path = file_path.relative_to(docs_dir)
            relative_path_str = str(relative_path)
            stat = file_path.stat()

            # Get status from database, default to 'active' if not tracked
            db_doc = db_docs.get(relative_path_str)
            doc_status = db_doc["status"] if db_doc else "active"

            # Apply status filter
            if status_filter and status_filter != "all" and doc_status != status_filter:
                continue

            files.append(
                {
                    "path": relative_path_str,
                    "name": file_path.name,
                    "size": stat.st_size,
                    "modified": stat.st_mtime,
                    "is_archive": "archive" in relative_path_str,
                    "status": doc_status,
                    "archived_at": db_doc["archived_at"] if db_doc else None,
                    "task_id": db_doc["task_id"] if db_doc else None,
                }
            )

        return jsonify({"files": files, "total": len(files)})

    except Exception as e:
        logger.error(f"Error listing documentation: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route("/api/docs/content")
def get_doc_content():
    """Get content of a specific documentation file"""
    try:
        doc_path = request.args.get("path")
        if not doc_path:
            return jsonify({"error": "Missing path parameter"}), 400

        # Determine docs directory based on where we're running from
        if Path.cwd().name == "telegram_bot":
            docs_dir = Path("../docs")
        else:
            docs_dir = Path("docs")

        # Security: Prevent directory traversal
        file_path = (docs_dir / doc_path).resolve()
        if not file_path.is_relative_to(docs_dir.resolve()):
            return jsonify({"error": "Invalid path"}), 403

        if not file_path.exists():
            return jsonify({"error": "File not found"}), 404

        # Read file content
        with open(file_path, encoding="utf-8") as f:
            content = f.read()

        return jsonify(
            {
                "path": str(doc_path),
                "name": file_path.name,
                "content": content,
                "size": file_path.stat().st_size,
            }
        )

    except Exception as e:
        logger.error(f"Error reading documentation: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route("/api/docs/archive", methods=["POST"])
def archive_doc():
    """Archive a documentation file by updating its status in database (files stay in place)"""
    try:
        global _agent_pool_loop
        if _agent_pool_loop is None:
            return jsonify({"error": "Server not ready"}), 503

        data = request.get_json()
        doc_path = data.get("path")
        notes = data.get("notes")

        if not doc_path:
            return jsonify({"error": "Missing path parameter"}), 400

        # Use absolute path based on server file location
        project_root = Path(__file__).parent.parent
        docs_dir = project_root / "docs"

        # Security: Prevent directory traversal
        file_path = (docs_dir / doc_path).resolve()
        if not file_path.is_relative_to(docs_dir.resolve()):
            return jsonify({"error": "Invalid path"}), 403

        if not file_path.exists():
            return jsonify({"error": "File not found"}), 404

        # Check if already archived in database
        existing_doc = task_manager.db.get_document(doc_path)
        if existing_doc and existing_doc["status"] == "archived":
            return jsonify({"error": "File is already archived"}), 400

        # Create or update document record in database using agent pool's event loop
        if existing_doc:
            # Update existing record
            future = asyncio.run_coroutine_threadsafe(
                task_manager.db.update_document_status(doc_path, "archived", notes), _agent_pool_loop
            )
            future.result(timeout=10)
        else:
            # Create new record with archived status
            future1 = asyncio.run_coroutine_threadsafe(task_manager.db.create_document(doc_path), _agent_pool_loop)
            future1.result(timeout=10)
            future2 = asyncio.run_coroutine_threadsafe(
                task_manager.db.update_document_status(doc_path, "archived", notes), _agent_pool_loop
            )
            future2.result(timeout=10)

        logger.info(f"Archived document in database: {doc_path}")

        return jsonify(
            {
                "success": True,
                "message": "Document archived successfully",
                "path": doc_path,
                "status": "archived",
            }
        )

    except Exception as e:
        logger.error(f"Error archiving documentation: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route("/api/docs/restore", methods=["POST"])
def restore_doc():
    """Restore an archived documentation file by updating its status to active"""
    try:
        global _agent_pool_loop
        if _agent_pool_loop is None:
            return jsonify({"error": "Server not ready"}), 503

        data = request.get_json()
        doc_path = data.get("path")
        notes = data.get("notes")

        if not doc_path:
            return jsonify({"error": "Missing path parameter"}), 400

        # Use absolute path based on server file location
        project_root = Path(__file__).parent.parent
        docs_dir = project_root / "docs"

        # Security: Prevent directory traversal
        file_path = (docs_dir / doc_path).resolve()
        if not file_path.is_relative_to(docs_dir.resolve()):
            return jsonify({"error": "Invalid path"}), 403

        if not file_path.exists():
            return jsonify({"error": "File not found"}), 404

        # Check if document exists in database
        existing_doc = task_manager.db.get_document(doc_path)
        if not existing_doc:
            return jsonify({"error": "Document not found in database"}), 404

        if existing_doc["status"] == "active":
            return jsonify({"error": "Document is already active"}), 400

        # Update document status to active using agent pool's event loop
        future = asyncio.run_coroutine_threadsafe(
            task_manager.db.update_document_status(doc_path, "active", notes), _agent_pool_loop
        )
        future.result(timeout=10)

        logger.info(f"Restored document in database: {doc_path}")

        return jsonify(
            {
                "success": True,
                "message": "Document restored successfully",
                "path": doc_path,
                "status": "active",
            }
        )

    except Exception as e:
        logger.error(f"Error restoring documentation: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route("/api/tasks/<task_id>/output/download")
def download_task_output(task_id: str):
    """Download output file for a completed task"""
    try:
        from flask import send_file

        # Security: Validate task_id format (alphanumeric and hyphens only)
        if not all(c.isalnum() or c in "-_" for c in task_id):
            return jsonify({"error": "Invalid task ID"}), 400

        # Check multiple possible session log locations
        workspace_path_env = os.getenv("WORKSPACE_PATH", "/Users/matifuentes/Workspace")
        possible_locations = [
            Path(sessions_dir) / task_id,  # Local (agentlab/logs/sessions/)
            Path(workspace_path_env) / "logs" / "sessions" / task_id,  # Workspace
        ]

        session_dir = None
        for loc in possible_locations:
            if loc.exists():
                session_dir = loc
                break

        if session_dir is None:
            return jsonify({"error": "No session directory found for this task"}), 404

        # Find first .md file in session directory
        md_files = list(session_dir.glob("*.md"))

        if not md_files:
            return jsonify({"error": "No output file found for this task"}), 404

        # Use the first .md file found
        output_file = md_files[0]

        # Get task details for filename
        task_dict = task_manager.db.get_task(task_id)

        # Generate download filename
        if task_dict:
            # Sanitize description for filename
            safe_description = "".join(
                c if c.isalnum() or c in " -_" else "_" for c in task_dict.get("description", "output")[:50]
            )
            safe_description = safe_description.strip().replace(" ", "_")
            download_name = f"task_{task_id}_{safe_description}.md"
        else:
            download_name = f"task_{task_id}_output.md"

        # Send file for download
        return send_file(output_file, as_attachment=True, download_name=download_name, mimetype="text/markdown")

    except Exception as e:
        logger.error(f"Error downloading output for task {task_id}: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route("/api/tasks/<task_id>/documents")
def task_documents(task_id: str):
    """Get list of markdown documents for a specific task"""
    try:
        # Security: Validate task_id format (alphanumeric and hyphens only)
        if not all(c.isalnum() or c in "-_" for c in task_id):
            return jsonify({"error": "Invalid task ID"}), 400

        # Check if content should be included
        include_content = request.args.get("content", "false").lower() == "true"

        # Check multiple possible session log locations (same as download_task_output)
        workspace_path_env = os.getenv("WORKSPACE_PATH", "/Users/matifuentes/Workspace")
        possible_locations = [
            Path(sessions_dir) / task_id,  # Local (agentlab/logs/sessions/)
            Path(workspace_path_env) / "logs" / "sessions" / task_id,  # Workspace
        ]

        session_dir = None
        for loc in possible_locations:
            if loc.exists():
                session_dir = loc
                break

        if session_dir is None:
            return jsonify({"error": "No session directory found for this task"}), 404

        # Find all .md files in session directory
        md_files = list(session_dir.glob("*.md"))

        if not md_files:
            return jsonify({"documents": [], "total": 0})

        # Build document list with metadata
        documents = []
        for md_file in md_files:
            # Get file stats
            stat = md_file.stat()

            # Build document entry
            doc_entry = {
                "filename": md_file.name,
                "path": f"{task_id}/{md_file.name}",
                "size": stat.st_size,
                "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            }

            # Include content if requested
            if include_content:
                try:
                    with open(md_file, encoding="utf-8") as f:
                        doc_entry["content"] = f.read()
                except Exception as e:
                    logger.warning(f"Error reading document {md_file}: {e}")
                    doc_entry["content"] = None
                    doc_entry["error"] = str(e)

            documents.append(doc_entry)

        # Sort by modified time (newest first)
        documents.sort(key=lambda x: x["modified"], reverse=True)

        return jsonify({"documents": documents, "total": len(documents)})

    except Exception as e:
        logger.error(f"Error getting documents for task {task_id}: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route("/api/tool-execution", methods=["POST"])
def record_tool_execution():
    """Receive tool execution data from bash hooks and broadcast via SocketIO"""
    try:
        data = request.get_json()

        if not data:
            return jsonify({"error": "No data provided"}), 400

        # Extract required fields
        task_id = data.get("task_id")
        tool_name = data.get("tool_name")
        timestamp = data.get("timestamp")
        success = data.get("success", True)
        error = data.get("error")
        parameters = data.get("parameters", {})

        if not all([task_id, tool_name, timestamp]):
            return jsonify({"error": "Missing required fields: task_id, tool_name, timestamp"}), 400

        # Save to database
        try:
            user_db.record_tool_usage(
                task_id=task_id,
                tool_name=tool_name,
                duration_ms=data.get("duration_ms"),
                success=success,
                error=error,
                parameters=parameters,
                error_category=data.get("error_category"),
            )
        except Exception as db_error:
            logger.error(f"Database write error in tool-execution endpoint: {db_error}", exc_info=True)
            # Continue to broadcast even if DB write fails

        # Broadcast to dashboard via SocketIO
        tool_data = {
            "task_id": task_id,
            "tool_name": tool_name,
            "timestamp": timestamp,
            "duration_ms": data.get("duration_ms", 0),
            "success": success,
            "error": error,
            "parameters": parameters,
            "output_preview": error[:500] if error else None,
            "has_error": success is False,  # Only true if explicitly failed
            "in_progress": success is None,  # True if still running
        }

        socketio.emit("tool_execution", tool_data)
        logger.debug(f"Broadcasted tool_execution via HTTP endpoint: {task_id} - {tool_name}")

        return jsonify({"success": True}), 200

    except Exception as e:
        logger.error(f"Error in tool-execution endpoint: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route("/api/screenshots/<path:filepath>")
def serve_screenshot(filepath: str):
    """Serve screenshot files from various locations"""
    try:
        from flask import send_file

        # Security: validate filepath (no directory traversal)
        if ".." in filepath or filepath.startswith("/"):
            return jsonify({"error": "Invalid file path"}), 403

        # Check multiple possible locations for screenshots
        workspace_path_env = os.getenv("WORKSPACE_PATH", "/Users/matifuentes/Workspace")
        possible_locations = [
            # Session directories
            Path(sessions_dir) / filepath,
            Path(workspace_path_env) / "logs" / "sessions" / filepath,
            # Repository directories (e.g., telegram_bot/chat.png)
            Path(workspace_path_env) / "agentlab" / filepath,
            Path(__file__).parent / filepath,
        ]

        screenshot_path = None
        for loc in possible_locations:
            if loc.exists() and loc.is_file():
                # Additional security: ensure it's an image file
                if loc.suffix.lower() in [".png", ".jpg", ".jpeg", ".webp"]:
                    screenshot_path = loc
                    break

        if screenshot_path is None:
            return jsonify({"error": "Screenshot not found"}), 404

        # Determine mimetype
        mimetype = "image/png"
        if screenshot_path.suffix.lower() in [".jpg", ".jpeg"]:
            mimetype = "image/jpeg"
        elif screenshot_path.suffix.lower() == ".webp":
            mimetype = "image/webp"

        return send_file(screenshot_path, mimetype=mimetype)

    except Exception as e:
        logger.error(f"Error serving screenshot {filepath}: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route("/api/tasks/<task_id>/screenshots")
def task_screenshots(task_id: str):
    """Get list of screenshots for a specific task"""
    try:
        # Get screenshots from tool_usage database
        cursor = task_manager.db.conn.cursor()
        cursor.execute(
            """
            SELECT screenshot_path, timestamp, tool_name
            FROM tool_usage
            WHERE task_id = ? AND screenshot_path IS NOT NULL
            ORDER BY timestamp ASC
            """,
            (task_id,),
        )

        screenshots = []
        for row in cursor.fetchall():
            screenshot_path, timestamp, tool_name = row
            screenshots.append(
                {
                    "path": screenshot_path,
                    "timestamp": timestamp,
                    "tool": tool_name,
                    "url": f"/api/screenshots/{screenshot_path}",
                }
            )

        # Also check session directory for screenshot files
        workspace_path_env = os.getenv("WORKSPACE_PATH", "/Users/matifuentes/Workspace")
        possible_locations = [
            Path(sessions_dir) / task_id,
            Path(workspace_path_env) / "logs" / "sessions" / task_id,
        ]

        for session_dir in possible_locations:
            if session_dir.exists() and session_dir.is_dir():
                # Find all image files
                for img_file in session_dir.glob("*.png"):
                    screenshots.append(
                        {
                            "path": f"{task_id}/{img_file.name}",
                            "timestamp": datetime.fromtimestamp(img_file.stat().st_mtime).isoformat(),
                            "tool": "unknown",
                            "url": f"/api/screenshots/{task_id}/{img_file.name}",
                        }
                    )
                for img_file in session_dir.glob("*.jpg"):
                    screenshots.append(
                        {
                            "path": f"{task_id}/{img_file.name}",
                            "timestamp": datetime.fromtimestamp(img_file.stat().st_mtime).isoformat(),
                            "tool": "unknown",
                            "url": f"/api/screenshots/{task_id}/{img_file.name}",
                        }
                    )
                for img_file in session_dir.glob("*.jpeg"):
                    screenshots.append(
                        {
                            "path": f"{task_id}/{img_file.name}",
                            "timestamp": datetime.fromtimestamp(img_file.stat().st_mtime).isoformat(),
                            "tool": "unknown",
                            "url": f"/api/screenshots/{task_id}/{img_file.name}",
                        }
                    )

        # Sort by timestamp
        screenshots.sort(key=lambda x: x["timestamp"])

        return jsonify({"screenshots": screenshots, "total": len(screenshots)})

    except Exception as e:
        logger.error(f"Error getting screenshots for task {task_id}: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route("/api/sessions/<session_id>/screenshots")
def session_screenshots(session_id: str):
    """Get list of screenshots for a specific session"""
    try:
        # Check session directory for screenshot files
        workspace_path_env = os.getenv("WORKSPACE_PATH", "/Users/matifuentes/Workspace")
        possible_locations = [
            Path(sessions_dir) / session_id,
            Path(workspace_path_env) / "logs" / "sessions" / session_id,
        ]

        screenshots = []
        for session_dir in possible_locations:
            if session_dir.exists() and session_dir.is_dir():
                # Find all image files
                for img_file in (
                    list(session_dir.glob("*.png")) + list(session_dir.glob("*.jpg")) + list(session_dir.glob("*.jpeg"))
                ):
                    screenshots.append(
                        {
                            "path": f"{session_id}/{img_file.name}",
                            "timestamp": datetime.fromtimestamp(img_file.stat().st_mtime).isoformat(),
                            "filename": img_file.name,
                            "url": f"/api/screenshots/{session_id}/{img_file.name}",
                        }
                    )

        # Sort by timestamp
        screenshots.sort(key=lambda x: x["timestamp"])

        return jsonify({"screenshots": screenshots, "total": len(screenshots)})

    except Exception as e:
        logger.error(f"Error getting screenshots for session {session_id}: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route("/health")
def health_endpoint():
    """Simple health check endpoint (no /api prefix)"""
    return jsonify(
        {
            "status": "healthy",
            "service": "AMIGA (Autonomous Modular Interactive Graphical Agent)-monitoring",
            "version": "1.0.0",
        }
    )


@app.route("/api/health")
def health_check():
    """Health check endpoint"""
    return jsonify(
        {
            "status": "healthy",
            "service": "AMIGA (Autonomous Modular Interactive Graphical Agent)-monitoring",
            "version": "1.0.0",
        }
    )


# --- SSE Stream ---


def _gather_session_metrics(hours: int) -> dict:
    """
    Gather session metrics from database.

    Args:
        hours: Time window in hours for metrics

    Returns:
        Dictionary containing session statistics
    """
    cutoff_time = (datetime.now() - timedelta(hours=hours)).isoformat()
    task_manager.db.conn.rollback()
    cursor = task_manager.db.conn.cursor()

    # Count distinct sessions
    cursor.execute("SELECT COUNT(DISTINCT task_id) FROM tool_usage WHERE timestamp >= ?", (cutoff_time,))
    total_sessions = cursor.fetchone()[0]

    # Count tool calls
    cursor.execute("SELECT COUNT(*) FROM tool_usage WHERE timestamp >= ?", (cutoff_time,))
    total_tool_calls = cursor.fetchone()[0]

    # Get tools breakdown
    cursor.execute(
        "SELECT tool_name, COUNT(*) FROM tool_usage WHERE timestamp >= ? GROUP BY tool_name",
        (cutoff_time,),
    )
    tools_by_type = {row[0]: row[1] for row in cursor.fetchall()}

    # Get error count
    cursor.execute("SELECT COUNT(*) FROM tool_usage WHERE timestamp >= ? AND success = 0", (cutoff_time,))
    total_errors = cursor.fetchone()[0]

    # Get recent sessions
    cursor.execute(
        """
        SELECT task_id, COUNT(*) as tools, SUM(CASE WHEN success = 0 THEN 1 ELSE 0 END) as errors,
               MAX(timestamp) as last_activity
        FROM tool_usage
        WHERE timestamp >= ?
        GROUP BY task_id
        ORDER BY last_activity DESC
        LIMIT 20
    """,
        (cutoff_time,),
    )
    recent_sessions = [
        {"session_id": r[0], "total_tools": r[1], "blocked": 0, "errors": r[2], "last_activity": r[3]}
        for r in cursor.fetchall()
    ]

    return {
        "total_sessions": total_sessions,
        "total_tool_calls": total_tool_calls,
        "tools_by_type": tools_by_type,
        "blocked_operations": 0,
        "errors": total_errors,
        "time_window_hours": hours,
        "recent_sessions": recent_sessions,
    }


def _gather_activity_data(limit: int = 8) -> list[dict]:
    """
    Gather recent task activity from database.

    Args:
        limit: Maximum number of activity entries to return

    Returns:
        List of activity entries sorted by timestamp
    """
    activity = []

    # End any stale read transaction to see latest writes
    task_manager.db.conn.rollback()
    cursor = task_manager.db.conn.cursor()

    # Get bot tasks
    cursor.execute(
        """
        SELECT task_id, description, status, activity_log
        FROM tasks
        ORDER BY updated_at DESC
        LIMIT ?
    """,
        (limit,),
    )

    for row in cursor.fetchall():
        task_id, description, status, activity_log_json = row
        activity_log = json.loads(activity_log_json) if activity_log_json else []

        if activity_log:
            for activity_entry in reversed(activity_log[-10:]):
                activity.append(
                    {
                        "task_id": task_id,
                        "description": description[:50],
                        "status": status,
                        "timestamp": activity_entry["timestamp"],
                        "message": activity_entry["message"],
                        "output_lines": activity_entry.get("output_lines"),
                    }
                )

    # Add active CLI sessions (tool usage in last 5 minutes, not in tasks table)
    cutoff_cli = (datetime.now() - timedelta(minutes=5)).isoformat()
    cursor.execute(
        """
        SELECT
            tool_usage.task_id,
            MAX(tool_usage.timestamp) as last_activity,
            COUNT(*) as tool_count
        FROM tool_usage
        LEFT JOIN tasks ON tool_usage.task_id = tasks.task_id
        WHERE tool_usage.timestamp >= ? AND tasks.task_id IS NULL
        GROUP BY tool_usage.task_id
        ORDER BY last_activity DESC
        LIMIT 5
    """,
        (cutoff_cli,),
    )

    for row in cursor.fetchall():
        task_id, last_activity, tool_count = row
        activity.append(
            {
                "task_id": task_id,
                "description": "CLI Session (active)",
                "status": "running",
                "timestamp": last_activity,
                "message": f"{tool_count} tool calls in last 5min",
                "output_lines": None,
            }
        )

    # Normalize timestamps to float for consistent sorting
    for item in activity:
        ts = item["timestamp"]
        try:
            item["timestamp"] = float(ts) if ts is not None else 0.0
        except (ValueError, TypeError):
            item["timestamp"] = 0.0

    activity.sort(key=lambda x: x["timestamp"], reverse=True)
    return activity[:limit]


def _format_sse_message(snapshot: dict) -> str:
    """
    Format metrics snapshot as Server-Sent Event message.

    Args:
        snapshot: Metrics snapshot dictionary

    Returns:
        SSE-formatted string
    """
    data = json.dumps(snapshot)
    return f"data: {data}\n\n"


def generate_sse_updates(hours: int = 24) -> Generator[str, None, None]:
    """
    Generator function that yields SSE-formatted metric updates.
    Polls metrics every 2 seconds and sends updates only when data changes.
    """
    global last_metrics_snapshot

    while True:
        try:
            # Reload tasks to get latest state
            task_manager.reload_tasks()

            # Gather all metrics
            overview = metrics_aggregator.get_complete_snapshot(hours=hours)
            sessions_metrics = _gather_session_metrics(hours)
            activity = _gather_activity_data(limit=8)

            # Create current snapshot
            current_snapshot = {
                "overview": overview.to_dict(),
                "sessions": sessions_metrics,
                "activity": activity,
                "timestamp": time.time(),
            }

            # Convert to JSON for comparison
            current_json = json.dumps(current_snapshot, sort_keys=True)
            last_json = json.dumps(last_metrics_snapshot, sort_keys=True) if last_metrics_snapshot else None

            # Only send if data has changed or this is the first update
            if current_json != last_json:
                last_metrics_snapshot = current_snapshot
                yield _format_sse_message(current_snapshot)
                logger.debug("Sent SSE update - metrics changed")
            else:
                # Send heartbeat to keep connection alive
                yield ": heartbeat\n\n"
                logger.debug("Sent SSE heartbeat - no changes")

        except Exception as e:
            logger.error(f"Error generating SSE update: {e}", exc_info=True)
            error_data = json.dumps({"error": str(e)})
            yield f"event: error\ndata: {error_data}\n\n"

        # Poll every 2 seconds for much faster updates than 30s
        time.sleep(2)


@app.route("/api/stream/metrics")
def stream_metrics():
    """
    Server-Sent Events endpoint for real-time metrics updates.
    Clients connect via EventSource and receive updates whenever metrics change.
    """
    hours = int(request.args.get("hours", 24))

    return Response(
        generate_sse_updates(hours=hours),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
            "Connection": "keep-alive",
        },
    )


def run_server(host: str = "0.0.0.0", port: int = 3000, debug: bool = False):  # nosec B104
    """Run the monitoring server with SocketIO support"""
    import threading

    logger.info(f"Starting monitoring server with WebSocket support on {host}:{port}")

    # Register tool usage hook for real-time updates
    def on_tool_start(task_id: str, tool_name: str, parameters: dict):
        """Hook called when tool execution starts - broadcast Task tools immediately"""
        try:
            # Only broadcast for Task tools (agent spawning) - show immediately in UI
            if tool_name != "Task":
                return

            # Get task to find user_id
            task = task_manager.get_task(task_id)
            if not task:
                return

            # Prepare tool execution data for running state
            tool_data = {
                "task_id": task_id,
                "tool_name": tool_name,
                "timestamp": datetime.now().isoformat(),
                "duration_ms": 0,
                "success": None,  # Still running
                "error": None,
                "parameters": parameters or {},
                "output_preview": None,
                "status": "running",  # Indicate tool is still executing
            }

            # Broadcast to all connected clients
            socketio.emit("tool_execution", tool_data)
            logger.debug(f"Broadcasted tool_start for task {task_id} - {tool_name}")

        except Exception as e:
            logger.error(f"Error in tool_start hook: {e}", exc_info=True)

    def on_tool_complete(
        task_id: str,
        tool_name: str,
        duration_ms: float,
        success: bool,
        error: str | None,
        parameters: dict | None,
        output: str | None,
    ):
        """Hook called when tool execution completes - broadcast via SocketIO"""
        try:
            # Get task to find user_id
            task = task_manager.get_task(task_id)
            if not task:
                return

            # Prepare tool execution data
            tool_data = {
                "task_id": task_id,
                "tool_name": tool_name,
                "timestamp": datetime.now().isoformat(),
                "duration_ms": duration_ms,
                "success": success,
                "error": error,
                "parameters": parameters or {},
                "output_preview": output[:500] if output else None,
                "status": "completed",  # Indicate tool completed
            }

            # Broadcast to all connected clients (no room= means broadcast to all)
            socketio.emit("tool_execution", tool_data)
            logger.debug(f"Broadcasted tool_execution for task {task_id}")

        except Exception as e:
            logger.error(f"Error in tool_complete hook: {e}", exc_info=True)

    tool_usage_tracker.register_tool_start_hook(on_tool_start)
    tool_usage_tracker.register_tool_complete_hook(on_tool_complete)
    logger.info("Registered tool usage hooks for real-time updates")

    # Start agent pool in separate thread to avoid eventlet conflicts
    logger.info("Starting agent pool for web chat task execution...")

    def run_agent_pool_loop():
        """Run agent pool event loop in dedicated thread"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        # Store loop globally
        global _agent_pool_loop
        _agent_pool_loop = loop

        # Start agent pool
        loop.run_until_complete(agent_pool.start())
        logger.info(f"Agent pool started with {agent_pool.max_agents} workers")

        # Keep loop running
        try:
            loop.run_forever()
        finally:
            loop.run_until_complete(agent_pool.stop())
            loop.close()

    # Start agent pool thread
    agent_thread = threading.Thread(target=run_agent_pool_loop, daemon=True)
    agent_thread.start()

    # Wait for loop to be ready
    import time

    while _agent_pool_loop is None:
        time.sleep(0.1)

    logger.info("Agent pool ready")

    try:
        socketio.run(app, host=host, port=port, debug=debug)
    finally:
        logger.info("Shutting down agent pool...")
        if _agent_pool_loop:
            _agent_pool_loop.call_soon_threadsafe(_agent_pool_loop.stop)
        logger.info("Closing database connection...")
        close_database()


# --- Auto-Restart on File Changes ---


def setup_auto_restart(watch_dir: str = None) -> None:
    """
    Setup file watcher to auto-restart server on Python file changes.

    Args:
        watch_dir: Directory to watch (defaults to telegram_bot/)
    """
    try:
        from watchdog.events import FileSystemEventHandler
        from watchdog.observers import Observer
    except ImportError:
        logger.warning("watchdog not installed - auto-restart disabled")
        return

    if watch_dir is None:
        watch_dir = str(Path(__file__).parent)

    class ChangeHandler(FileSystemEventHandler):
        """Handler for file system change events"""

        def __init__(self):
            super().__init__()
            self.restart_scheduled = False
            self.last_restart_time = 0
            self.debounce_seconds = 1.0  # Debounce to avoid multiple restarts

        def on_modified(self, event):
            """File modification detected"""
            if event.is_directory:
                return

            # Only restart on Python file changes
            if not event.src_path.endswith(".py"):
                return

            # Debounce: ignore if restart was triggered recently
            current_time = time.time()
            if current_time - self.last_restart_time < self.debounce_seconds:
                return

            # Ignore changes to __pycache__ and other temp files
            if "__pycache__" in event.src_path or event.src_path.endswith(".pyc"):
                return

            file_path = Path(event.src_path)
            logger.info(f"File change detected: {file_path.name}")
            logger.info("Restarting monitoring server...")

            self.last_restart_time = current_time
            self.restart_scheduled = True

            # Trigger graceful shutdown and restart

            # Exit with code 3 to signal restart needed
            os._exit(3)  # nosec B605 - intentional exit for restart

    # Create observer
    observer = Observer()
    event_handler = ChangeHandler()
    observer.schedule(event_handler, watch_dir, recursive=True)
    observer.start()

    logger.info(f"Auto-restart enabled - watching {watch_dir} for changes")

    return observer


def run_with_auto_restart(host: str = "0.0.0.0", port: int = 3000, debug: bool = False):  # nosec B104
    """
    Run server with auto-restart capability.

    Wraps the server in a restart loop that monitors for file changes.
    """
    import subprocess
    import sys

    while True:
        # Start server process
        logger.info("Starting monitoring server...")
        process = subprocess.Popen([sys.executable] + sys.argv)  # nosec B603 - controlled subprocess

        try:
            # Wait for process to exit
            exit_code = process.wait()

            if exit_code == 3:
                # Exit code 3 signals restart needed
                logger.info("Restart requested - reloading server...")
                time.sleep(0.5)  # Brief pause before restart
                continue
            else:
                # Normal exit or error
                logger.info(f"Server exited with code {exit_code}")
                break

        except KeyboardInterrupt:
            logger.info("Keyboard interrupt - shutting down...")
            process.terminate()
            process.wait()
            break


if __name__ == "__main__":
    # Setup logging
    configure_root_logger()

    # Get configuration from environment
    host = os.getenv("MONITORING_HOST", "0.0.0.0")  # nosec B104
    port = int(os.getenv("MONITORING_PORT", "3000"))
    debug = os.getenv("MONITORING_DEBUG", "false").lower() == "true"
    auto_restart = os.getenv("MONITORING_AUTO_RESTART", "true").lower() == "true"

    # Check if we should enable auto-restart
    if auto_restart:
        # Setup file watcher for auto-restart
        observer = setup_auto_restart()

        if observer:
            try:
                # Run server with auto-restart enabled
                run_server(host=host, port=port, debug=debug)
            except KeyboardInterrupt:
                logger.info("Shutting down monitoring server...")
                observer.stop()
                observer.join()
        else:
            # Watchdog not available, run normally
            run_server(host=host, port=port, debug=debug)
    else:
        # Auto-restart disabled
        logger.info("Auto-restart disabled")
        run_server(host=host, port=port, debug=debug)
