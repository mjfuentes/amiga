"""
REST API routes for web chat interface.

Provides endpoints for authentication, chat history, tasks, and cost tracking.
"""

import os
import sys
from pathlib import Path
from flask import Blueprint, request, jsonify
import logging

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import auth
from core.config import DATA_DIR_STR
from core.session import SessionManager
from tasks.manager import TaskManager

logger = logging.getLogger(__name__)

# Create blueprint
api = Blueprint('api', __name__, url_prefix='/api')

# Initialize managers (shared with WebSocket handlers)
# Use centralized config path instead of constructing from __file__
session_manager = SessionManager(data_dir=DATA_DIR_STR)
task_manager = TaskManager(data_dir=DATA_DIR_STR)


# --- Authentication Endpoints ---

@api.route('/auth/register', methods=['POST'])
def register():
    """Register a new user."""
    try:
        data = request.json
        username = data.get('username')
        email = data.get('email')
        password = data.get('password')

        if not all([username, email, password]):
            return jsonify({'error': 'Missing required fields'}), 400

        success, result = auth.register_user(username, email, password)
        if success:
            token = auth.create_token(result)
            user_info = auth.get_user_info(result)
            return jsonify({
                'token': token,
                'user': user_info
            })
        else:
            return jsonify({'error': result}), 400

    except Exception as e:
        logger.error(f"Registration error: {e}", exc_info=True)
        return jsonify({'error': 'Internal server error'}), 500


@api.route('/auth/login', methods=['POST'])
def login():
    """Login an existing user."""
    try:
        data = request.json
        username = data.get('username')
        password = data.get('password')

        if not all([username, password]):
            return jsonify({'error': 'Missing required fields'}), 400

        success, result = auth.login_user(username, password)
        if success:
            # Get user info
            users = auth.load_users()
            user = users.get(username)
            user_info = auth.get_user_info(user['id'])

            return jsonify({
                'token': result,
                'user': user_info
            })
        else:
            return jsonify({'error': result}), 401

    except Exception as e:
        logger.error(f"Login error: {e}", exc_info=True)
        return jsonify({'error': 'Internal server error'}), 500


@api.route('/auth/verify', methods=['GET'])
def verify():
    """Verify JWT token and return user info."""
    try:
        token = request.headers.get('Authorization', '').replace('Bearer ', '')
        user_id = auth.verify_token(token)

        if not user_id:
            return jsonify({'error': 'Invalid or expired token'}), 401

        user_info = auth.get_user_info(user_id)
        if not user_info:
            return jsonify({'error': 'User not found'}), 404

        return jsonify(user_info)

    except Exception as e:
        logger.error(f"Token verification error: {e}", exc_info=True)
        return jsonify({'error': 'Internal server error'}), 500


# --- Chat Endpoints ---

@api.route('/chat/history', methods=['GET'])
def get_history():
    """Get chat history for authenticated user."""
    try:
        token = request.headers.get('Authorization', '').replace('Bearer ', '')
        user_id = auth.verify_token(token)

        if not user_id:
            return jsonify({'error': 'Unauthorized'}), 401

        session = session_manager.get_or_create_session(user_id)
        history = [
            {
                'role': msg.role,
                'content': msg.content,
                'timestamp': msg.timestamp
            }
            for msg in session.history
        ]

        return jsonify({'history': history})

    except Exception as e:
        logger.error(f"Error getting history: {e}", exc_info=True)
        return jsonify({'error': 'Internal server error'}), 500


@api.route('/chat/clear', methods=['POST'])
def clear_history():
    """Clear chat history for authenticated user."""
    try:
        token = request.headers.get('Authorization', '').replace('Bearer ', '')
        user_id = auth.verify_token(token)

        if not user_id:
            return jsonify({'error': 'Unauthorized'}), 401

        session_manager.clear_session(user_id)
        return jsonify({'success': True})

    except Exception as e:
        logger.error(f"Error clearing history: {e}", exc_info=True)
        return jsonify({'error': 'Internal server error'}), 500


# --- Task Endpoints ---

@api.route('/tasks', methods=['GET'])
def get_tasks():
    """Get active tasks for authenticated user."""
    try:
        token = request.headers.get('Authorization', '').replace('Bearer ', '')
        user_id = auth.verify_token(token)

        if not user_id:
            return jsonify({'error': 'Unauthorized'}), 401

        tasks = task_manager.get_active_tasks(user_id)
        return jsonify({
            'tasks': [
                {
                    'task_id': task.task_id,
                    'description': task.description,
                    'status': task.status,
                    'created_at': task.created_at,
                    'workspace': task.workspace,
                    'model': task.model
                }
                for task in tasks
            ]
        })

    except Exception as e:
        logger.error(f"Error getting tasks: {e}", exc_info=True)
        return jsonify({'error': 'Internal server error'}), 500


@api.route('/tasks/<task_id>', methods=['GET'])
def get_task(task_id):
    """Get specific task by ID for authenticated user."""
    try:
        token = request.headers.get('Authorization', '').replace('Bearer ', '')
        user_id = auth.verify_token(token)

        if not user_id:
            return jsonify({'error': 'Unauthorized'}), 401

        task = task_manager.get_task(task_id)
        if not task or task.user_id != user_id:
            return jsonify({'error': 'Task not found'}), 404

        return jsonify({
            'task_id': task.task_id,
            'description': task.description,
            'status': task.status,
            'created_at': task.created_at,
            'updated_at': task.updated_at,
            'workspace': task.workspace,
            'model': task.model,
            'result': task.result,
            'error': task.error
        })

    except Exception as e:
        logger.error(f"Error getting task: {e}", exc_info=True)
        return jsonify({'error': 'Internal server error'}), 500


# --- Health Check ---

@api.route('/health', methods=['GET'])
def health():
    """Health check endpoint."""
    return jsonify({'status': 'ok'})
