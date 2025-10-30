"""
Session management for AMIGA with activity tracking and automatic cleanup.
"""
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Optional
import logging

logger = logging.getLogger(__name__)

# Session configuration
ACCESS_TOKEN_EXPIRATION_MINUTES = 15  # Short-lived access tokens
REFRESH_TOKEN_EXPIRATION_DAYS = 30    # Long-lived refresh tokens
INACTIVITY_TIMEOUT_MINUTES = 30       # Auto-logout after inactivity


class SessionManager:
    """Manages user sessions with activity tracking and cleanup."""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._ensure_sessions_table()
    
    def _get_connection(self) -> sqlite3.Connection:
        """Get database connection."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    def _ensure_sessions_table(self):
        """Create sessions table if it doesn't exist."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                access_token TEXT NOT NULL,
                refresh_token TEXT NOT NULL,
                created_at TEXT NOT NULL,
                last_activity TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                user_agent TEXT,
                ip_address TEXT,
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
            )
        """)
        
        # Create indices for performance
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_sessions_access_token ON sessions(access_token)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_sessions_refresh_token ON sessions(refresh_token)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_sessions_expires_at ON sessions(expires_at)")
        
        conn.commit()
        conn.close()
        logger.info("Sessions table initialized")
    
    def create_session(
        self,
        user_id: str,
        access_token: str,
        user_agent: Optional[str] = None,
        ip_address: Optional[str] = None
    ) -> tuple[str, str]:
        """
        Create a new session with access and refresh tokens.
        
        Returns:
            tuple[str, str]: (session_id, refresh_token)
        """
        session_id = secrets.token_urlsafe(32)
        refresh_token = secrets.token_urlsafe(32)
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(days=REFRESH_TOKEN_EXPIRATION_DAYS)
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute(
                """
                INSERT INTO sessions (
                    session_id, user_id, access_token, refresh_token,
                    created_at, last_activity, expires_at, user_agent, ip_address
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id, user_id, access_token, refresh_token,
                    now.isoformat(), now.isoformat(), expires_at.isoformat(),
                    user_agent, ip_address
                )
            )
            conn.commit()
            logger.info(f"Created session {session_id} for user {user_id}")
            return session_id, refresh_token
            
        finally:
            conn.close()
    
    def get_session_by_access_token(self, access_token: str) -> Optional[dict]:
        """Get session by access token."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute(
                "SELECT * FROM sessions WHERE access_token = ?",
                (access_token,)
            )
            row = cursor.fetchone()
            
            if row:
                return dict(row)
            return None
            
        finally:
            conn.close()
    
    def get_session_by_refresh_token(self, refresh_token: str) -> Optional[dict]:
        """Get session by refresh token."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute(
                "SELECT * FROM sessions WHERE refresh_token = ?",
                (refresh_token,)
            )
            row = cursor.fetchone()
            
            if row:
                return dict(row)
            return None
            
        finally:
            conn.close()
    
    def update_activity(self, session_id: str) -> bool:
        """Update last activity timestamp for session."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            now = datetime.now(timezone.utc)
            cursor.execute(
                "UPDATE sessions SET last_activity = ? WHERE session_id = ?",
                (now.isoformat(), session_id)
            )
            conn.commit()
            
            if cursor.rowcount > 0:
                logger.debug(f"Updated activity for session {session_id}")
                return True
            return False
            
        finally:
            conn.close()
    
    def update_access_token(self, session_id: str, new_access_token: str) -> bool:
        """Update access token for session (during refresh)."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            now = datetime.now(timezone.utc)
            cursor.execute(
                """
                UPDATE sessions 
                SET access_token = ?, last_activity = ?
                WHERE session_id = ?
                """,
                (new_access_token, now.isoformat(), session_id)
            )
            conn.commit()
            
            if cursor.rowcount > 0:
                logger.info(f"Updated access token for session {session_id}")
                return True
            return False
            
        finally:
            conn.close()
    
    def delete_session(self, session_id: str) -> bool:
        """Delete a session (logout)."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
            conn.commit()
            
            if cursor.rowcount > 0:
                logger.info(f"Deleted session {session_id}")
                return True
            return False
            
        finally:
            conn.close()
    
    def delete_user_sessions(self, user_id: str) -> int:
        """Delete all sessions for a user."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
            conn.commit()
            count = cursor.rowcount
            
            if count > 0:
                logger.info(f"Deleted {count} sessions for user {user_id}")
            return count
            
        finally:
            conn.close()
    
    def is_session_valid(self, session: dict) -> tuple[bool, Optional[str]]:
        """
        Check if session is valid (not expired, not inactive).
        
        Returns:
            tuple[bool, Optional[str]]: (is_valid, reason_if_invalid)
        """
        now = datetime.now(timezone.utc)
        
        # Check expiration - parse and make timezone-aware if needed
        expires_at = datetime.fromisoformat(session['expires_at'])
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if now > expires_at:
            return False, "Session expired"
        
        # Check inactivity timeout
        last_activity = datetime.fromisoformat(session['last_activity'])
        if last_activity.tzinfo is None:
            last_activity = last_activity.replace(tzinfo=timezone.utc)
        inactivity_threshold = now - timedelta(minutes=INACTIVITY_TIMEOUT_MINUTES)
        
        if last_activity < inactivity_threshold:
            return False, "Session inactive"
        
        return True, None
    
    def cleanup_expired_sessions(self) -> int:
        """
        Remove expired and inactive sessions.
        
        Returns:
            int: Number of sessions deleted
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            now = datetime.now(timezone.utc)
            inactivity_threshold = now - timedelta(minutes=INACTIVITY_TIMEOUT_MINUTES)
            
            # Delete expired sessions
            cursor.execute(
                "DELETE FROM sessions WHERE expires_at < ?",
                (now.isoformat(),)
            )
            expired_count = cursor.rowcount
            
            # Delete inactive sessions
            cursor.execute(
                "DELETE FROM sessions WHERE last_activity < ?",
                (inactivity_threshold.isoformat(),)
            )
            inactive_count = cursor.rowcount
            
            conn.commit()
            total = expired_count + inactive_count
            
            if total > 0:
                logger.info(f"Cleaned up {total} sessions ({expired_count} expired, {inactive_count} inactive)")
            
            return total
            
        finally:
            conn.close()
    
    def get_user_sessions(self, user_id: str) -> list[dict]:
        """Get all active sessions for a user."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute(
                """
                SELECT session_id, created_at, last_activity, user_agent, ip_address
                FROM sessions 
                WHERE user_id = ?
                ORDER BY last_activity DESC
                """,
                (user_id,)
            )
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
            
        finally:
            conn.close()
