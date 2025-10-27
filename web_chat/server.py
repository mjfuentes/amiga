"""
Web chat server with Flask-SocketIO.

Provides WebSocket real-time communication and REST API endpoints.
"""

import os
import sys
import asyncio
import logging
from pathlib import Path
from flask import Flask, request, session
from flask_socketio import SocketIO, emit, join_room, leave_room
from flask_cors import CORS
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import shared modules
from core.config import DATA_DIR_STR
from core.session import SessionManager
from core.orchestrator import discover_repositories
from tasks.manager import TaskManager, Task
from tasks.pool import AgentPool
from utils.logging_setup import configure_root_logger

# Import local modules
import auth
from api_routes import api

# Configure logging
configure_root_logger()
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('JWT_SECRET_KEY', 'dev-secret-change-in-prod-IMPORTANT')

# CORS configuration
allowed_origins = os.getenv('CORS_ORIGINS', 'http://localhost:3000,http://localhost:3001').split(',')
CORS(app, origins=allowed_origins, supports_credentials=True)

# Initialize SocketIO
socketio = SocketIO(
    app,
    cors_allowed_origins='*',
    async_mode='eventlet',
    logger=True,
    engineio_logger=True
)

# Register API blueprint
app.register_blueprint(api)

# Initialize managers (shared with API routes)
# Use centralized config path instead of constructing from __file__
session_manager = SessionManager(data_dir=DATA_DIR_STR)
task_manager = TaskManager(data_dir=DATA_DIR_STR)
agent_pool = AgentPool(max_agents=3)

# Environment variables
WORKSPACE_PATH = os.getenv('WORKSPACE_PATH')
BOT_REPOSITORY = str(Path(__file__).parent.parent / 'telegram_bot')

logger.info(f"Data directory: {DATA_DIR_STR}")
logger.info(f"Workspace path: {WORKSPACE_PATH}")
logger.info(f"Bot repository: {BOT_REPOSITORY}")


# --- WebSocket Event Handlers ---

@socketio.on('connect')
def handle_connect(auth_data):
    """Client connected - verify JWT token."""
    try:
        token = auth_data.get('token') if isinstance(auth_data, dict) else None

        if not token:
            logger.warning("Connection attempt without token")
            return False

        user_id = auth.verify_token(token)
        if not user_id:
            logger.warning("Connection attempt with invalid token")
            return False

        # Store user_id in Flask session
        session['user_id'] = user_id
        join_room(user_id)  # Join user-specific room

        logger.info(f"User {user_id} connected")
        emit('connected', {'user_id': user_id, 'message': 'Connected successfully'})

    except Exception as e:
        logger.error(f"Connection error: {e}", exc_info=True)
        return False


@socketio.on('disconnect')
def handle_disconnect():
    """Client disconnected."""
    try:
        user_id = session.get('user_id')
        if user_id:
            leave_room(user_id)
            logger.info(f"User {user_id} disconnected")
    except Exception as e:
        logger.error(f"Disconnect error: {e}", exc_info=True)


@socketio.on('message')
def handle_message(data):
    """Client sent a message."""
    try:
        user_id = session.get('user_id')
        if not user_id:
            emit('error', {'message': 'Unauthorized - please reconnect'})
            return

        message_text = data.get('message')
        if not message_text:
            emit('error', {'message': 'Empty message'})
            return

        logger.info(f"User {user_id}: {message_text[:100]}")

        # Get session history
        session_obj = session_manager.get_or_create_session(user_id)
        history = [
            {"role": msg.role, "content": msg.content}
            for msg in session_obj.history[-10:]  # Last 10 messages
        ]

        # Add user message to history
        session_manager.add_message(user_id, "user", message_text)

        # Import here to avoid circular dependency
        from claude_api import ask_claude

        # Call Claude API asynchronously
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        response, background_task_info, usage_info = loop.run_until_complete(
            ask_claude(
                user_query=message_text,
                input_method="text",
                conversation_history=history,
                current_workspace=session_manager.get_workspace(user_id) or WORKSPACE_PATH,
                bot_repository=BOT_REPOSITORY,
                workspace_path=WORKSPACE_PATH,
                available_repositories=discover_repositories(WORKSPACE_PATH) if WORKSPACE_PATH else [],
                active_tasks=task_manager.get_active_tasks(user_id)
            )
        )

        # Add assistant response to history
        session_manager.add_message(user_id, "assistant", response)

        # Check if background task needed
        if background_task_info:
            # Create task
            task = task_manager.create_task(
                user_id=user_id,
                description=background_task_info['description'],
                workspace=session_manager.get_workspace(user_id) or WORKSPACE_PATH,
                model='sonnet',
                agent_type=background_task_info.get('agent_type', 'orchestrator')
            )

            logger.info(f"Created task {task.task_id} for user {user_id}")

            # Submit to agent pool (will be implemented later)
            # For now, just acknowledge
            emit('response', {
                'message': background_task_info.get('user_message', f"Task #{task.task_id} created"),
                'task_id': task.task_id,
                'type': 'task_started'
            })
        else:
            # Direct response
            emit('response', {
                'message': response,
                'type': 'direct'
            })

    except Exception as e:
        logger.error(f"Error handling message: {e}", exc_info=True)
        emit('error', {'message': f'Error processing message: {str(e)}'})


@socketio.on('typing')
def handle_typing(data):
    """Client is typing - broadcast to workspace members (future feature)."""
    try:
        user_id = session.get('user_id')
        if not user_id:
            return

        # For now, just log
        logger.debug(f"User {user_id} is typing")

    except Exception as e:
        logger.error(f"Error handling typing: {e}", exc_info=True)


@socketio.on('ping')
def handle_ping():
    """Keepalive ping."""
    emit('pong', {'timestamp': asyncio.get_event_loop().time()})


# --- HTTP Routes ---

@app.route('/')
def index():
    """Root endpoint."""
    return {
        'service': 'AgentLab Web Chat',
        'status': 'running',
        'endpoints': {
            'websocket': 'ws://localhost:5000/socket.io',
            'api': '/api'
        }
    }


@app.route('/health')
def health():
    """Health check."""
    return {'status': 'ok'}


# --- Main ---

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    debug = os.getenv('DEBUG', 'False').lower() == 'true'

    logger.info(f"Starting web chat server on port {port}")
    logger.info(f"Debug mode: {debug}")
    logger.info(f"CORS origins: {allowed_origins}")

    socketio.run(
        app,
        host='0.0.0.0',
        port=port,
        debug=debug,
        use_reloader=False  # Disable reloader to avoid double execution
    )
