"""
Authentication module for web chat interface.

Provides user registration, login, and JWT token management.
"""

import os
import jwt
import bcrypt
from datetime import datetime, timedelta
from pathlib import Path
import json
import uuid
from typing import Tuple, Dict, Optional

SECRET_KEY = os.getenv('JWT_SECRET_KEY', 'dev-secret-change-in-prod-IMPORTANT')
TOKEN_EXPIRATION_HOURS = 1
REFRESH_TOKEN_EXPIRATION_DAYS = 7

# Simple user database (JSON file for now, can migrate to SQLite later)
USERS_FILE = Path(__file__).parent / 'data' / 'users.json'


def load_users() -> Dict:
    """Load users from JSON file."""
    if not USERS_FILE.exists():
        return {}
    try:
        with open(USERS_FILE, 'r') as f:
            return json.load(f)
    except json.JSONDecodeError:
        return {}


def save_users(users: Dict) -> None:
    """Save users to JSON file."""
    USERS_FILE.parent.mkdir(exist_ok=True, parents=True)
    with open(USERS_FILE, 'w') as f:
        json.dump(users, f, indent=2)


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
        'user_id': user_id,
        'exp': datetime.utcnow() + timedelta(hours=expiration_hours),
        'iat': datetime.utcnow()
    }
    return jwt.encode(payload, SECRET_KEY, algorithm='HS256')


def verify_token(token: str) -> Optional[str]:
    """Verify JWT token and return user_id, or None if invalid."""
    if not token:
        return None

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=['HS256'])
        return payload.get('user_id')
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


def register_user(username: str, email: str, password: str) -> Tuple[bool, str]:
    """
    Register new user.

    Returns:
        (success, message/user_id): If success=True, returns user_id. If False, returns error message.
    """
    if not username or not email or not password:
        return False, "All fields are required"

    if len(password) < 8:
        return False, "Password must be at least 8 characters"

    users = load_users()

    # Check if username or email already exists
    if username in users:
        return False, "Username already exists"

    if any(u.get('email') == email for u in users.values()):
        return False, "Email already registered"

    # Create user
    user_id = str(uuid.uuid4())
    users[username] = {
        'id': user_id,
        'email': email,
        'password_hash': hash_password(password),
        'created_at': datetime.utcnow().isoformat(),
        'is_admin': False
    }

    save_users(users)
    return True, user_id


def login_user(username: str, password: str) -> Tuple[bool, str]:
    """
    Login user.

    Returns:
        (success, token/error_message): If success=True, returns JWT token. If False, returns error.
    """
    users = load_users()

    if username not in users:
        return False, "Invalid username or password"

    user = users[username]
    if not verify_password(password, user['password_hash']):
        return False, "Invalid username or password"

    # Create token
    token = create_token(user['id'])
    return True, token


def get_user_info(user_id: str) -> Optional[Dict]:
    """Get user information by user_id."""
    users = load_users()
    for username, user in users.items():
        if user.get('id') == user_id:
            return {
                'user_id': user_id,
                'username': username,
                'email': user['email'],
                'created_at': user['created_at'],
                'is_admin': user.get('is_admin', False)
            }
    return None


def get_user_by_username(username: str) -> Optional[Dict]:
    """Get user information by username."""
    users = load_users()
    if username in users:
        user = users[username]
        return {
            'user_id': user['id'],
            'username': username,
            'email': user['email'],
            'created_at': user['created_at'],
            'is_admin': user.get('is_admin', False)
        }
    return None
