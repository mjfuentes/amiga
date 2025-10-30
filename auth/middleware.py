"""
Authentication middleware for Flask with session tracking.
"""
import logging
from datetime import datetime, timedelta, timezone
from functools import wraps
from typing import Optional
from flask import request, jsonify
import jwt as pyjwt

logger = logging.getLogger(__name__)

# Token configuration
ACCESS_TOKEN_EXPIRATION_MINUTES = 15
SECRET_KEY = None  # Will be set by init_auth_middleware


def init_auth_middleware(secret_key: str, session_manager):
    """Initialize authentication middleware with config."""
    global SECRET_KEY
    SECRET_KEY = secret_key
    AuthMiddleware.session_manager = session_manager
    logger.info("Auth middleware initialized")


class AuthMiddleware:
    """Middleware for handling authentication and session tracking."""
    
    session_manager = None  # Set by init_auth_middleware
    
    @staticmethod
    def generate_tokens(user_id: str) -> tuple[str, str, str]:
        """
        Generate access and refresh tokens.
        
        Returns:
            tuple[str, str, str]: (access_token, refresh_token, session_id)
        """
        # Generate access token (short-lived)
        payload = {
            "user_id": user_id,
            "exp": datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRATION_MINUTES),
            "iat": datetime.now(timezone.utc),
            "type": "access"
        }
        access_token = pyjwt.encode(payload, SECRET_KEY, algorithm="HS256")
        
        # Create session with refresh token
        user_agent = request.headers.get("User-Agent")
        ip_address = request.remote_addr
        
        session_id, refresh_token = AuthMiddleware.session_manager.create_session(
            user_id=user_id,
            access_token=access_token,
            user_agent=user_agent,
            ip_address=ip_address
        )
        
        return access_token, refresh_token, session_id
    
    @staticmethod
    def verify_access_token(token: str) -> Optional[str]:
        """
        Verify access token and return user_id.
        Also checks session validity and updates activity.
        
        Returns:
            str | None: user_id if valid, None otherwise
        """
        if not token:
            return None
        
        # Support dummy tokens for NO_AUTH_MODE
        if token.startswith("dummy-token-"):
            user_id = token.replace("dummy-token-", "")
            return user_id if user_id else None
        
        try:
            # Decode JWT
            payload = pyjwt.decode(token, SECRET_KEY, algorithms=["HS256"])
            user_id = payload.get("user_id")
            
            if not user_id:
                return None
            
            # Check session validity
            session = AuthMiddleware.session_manager.get_session_by_access_token(token)
            if not session:
                logger.warning(f"No session found for token")
                return None
            
            # Validate session (expiration, inactivity)
            is_valid, reason = AuthMiddleware.session_manager.is_session_valid(session)
            if not is_valid:
                logger.info(f"Session invalid: {reason}")
                # Clean up invalid session
                AuthMiddleware.session_manager.delete_session(session['session_id'])
                return None
            
            # Update activity timestamp
            AuthMiddleware.session_manager.update_activity(session['session_id'])
            
            return user_id
            
        except pyjwt.ExpiredSignatureError:
            logger.debug("Access token expired")
            return None
        except pyjwt.InvalidTokenError as e:
            logger.debug(f"Invalid token: {e}")
            return None
        except Exception as e:
            logger.error(f"Token verification error: {e}", exc_info=True)
            return None
    
    @staticmethod
    def refresh_access_token(refresh_token: str) -> Optional[tuple[str, str]]:
        """
        Refresh access token using refresh token.
        
        Returns:
            tuple[str, str] | None: (new_access_token, user_id) if successful, None otherwise
        """
        try:
            # Get session by refresh token
            session = AuthMiddleware.session_manager.get_session_by_refresh_token(refresh_token)
            if not session:
                logger.warning("No session found for refresh token")
                return None
            
            # Validate session
            is_valid, reason = AuthMiddleware.session_manager.is_session_valid(session)
            if not is_valid:
                logger.info(f"Session invalid during refresh: {reason}")
                AuthMiddleware.session_manager.delete_session(session['session_id'])
                return None
            
            user_id = session['user_id']
            
            # Generate new access token
            payload = {
                "user_id": user_id,
                "exp": datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRATION_MINUTES),
                "iat": datetime.now(timezone.utc),
                "type": "access"
            }
            new_access_token = pyjwt.encode(payload, SECRET_KEY, algorithm="HS256")
            
            # Update session with new access token
            AuthMiddleware.session_manager.update_access_token(
                session['session_id'],
                new_access_token
            )
            
            logger.info(f"Refreshed access token for user {user_id}")
            return new_access_token, user_id
            
        except Exception as e:
            logger.error(f"Token refresh error: {e}", exc_info=True)
            return None
    
    @staticmethod
    def logout_session(token: str) -> bool:
        """
        Logout session by access token.
        
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            session = AuthMiddleware.session_manager.get_session_by_access_token(token)
            if not session:
                return False
            
            return AuthMiddleware.session_manager.delete_session(session['session_id'])
            
        except Exception as e:
            logger.error(f"Logout error: {e}", exc_info=True)
            return False


def require_auth(f):
    """
    Decorator to require authentication for Flask routes.
    Verifies token, checks session validity, and updates activity.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        token = request.headers.get("Authorization", "").replace("Bearer ", "")
        user_id = AuthMiddleware.verify_access_token(token)
        
        if not user_id:
            return jsonify({"error": "Unauthorized"}), 401
        
        # Attach user_id to request context
        request.user_id = user_id
        
        return f(*args, **kwargs)
    
    return decorated_function
