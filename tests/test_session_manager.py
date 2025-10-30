"""
Tests for session management functionality.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
import tempfile
import os
from datetime import datetime, timedelta, timezone
from auth.session_manager import SessionManager


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    with tempfile.NamedTemporaryFile(delete=False, suffix='.db') as f:
        db_path = f.name
    yield db_path
    os.unlink(db_path)


@pytest.fixture
def session_manager(temp_db):
    """Create SessionManager instance with temp database."""
    return SessionManager(temp_db)


class TestSessionManager:
    """Tests for SessionManager class."""
    
    def test_create_session(self, session_manager):
        """Test creating a new session."""
        user_id = "test_user_123"
        access_token = "test_access_token"
        user_agent = "Mozilla/5.0"
        ip_address = "127.0.0.1"
        
        session_id, refresh_token = session_manager.create_session(
            user_id=user_id,
            access_token=access_token,
            user_agent=user_agent,
            ip_address=ip_address
        )
        
        assert session_id is not None
        assert refresh_token is not None
        assert len(session_id) > 20  # URL-safe tokens are reasonably long
        assert len(refresh_token) > 20
    
    def test_get_session_by_access_token(self, session_manager):
        """Test retrieving session by access token."""
        user_id = "test_user_123"
        access_token = "test_access_token"
        
        session_id, refresh_token = session_manager.create_session(
            user_id=user_id,
            access_token=access_token
        )
        
        session = session_manager.get_session_by_access_token(access_token)
        
        assert session is not None
        assert session['user_id'] == user_id
        assert session['session_id'] == session_id
        assert session['access_token'] == access_token
        assert session['refresh_token'] == refresh_token
    
    def test_get_session_by_refresh_token(self, session_manager):
        """Test retrieving session by refresh token."""
        user_id = "test_user_123"
        access_token = "test_access_token"
        
        session_id, refresh_token = session_manager.create_session(
            user_id=user_id,
            access_token=access_token
        )
        
        session = session_manager.get_session_by_refresh_token(refresh_token)
        
        assert session is not None
        assert session['user_id'] == user_id
        assert session['session_id'] == session_id
    
    def test_update_activity(self, session_manager):
        """Test updating last activity timestamp."""
        user_id = "test_user_123"
        access_token = "test_access_token"
        
        session_id, _ = session_manager.create_session(
            user_id=user_id,
            access_token=access_token
        )
        
        # Get initial activity time
        session = session_manager.get_session_by_access_token(access_token)
        initial_activity = session['last_activity']
        
        # Wait a tiny bit and update
        import time
        time.sleep(0.1)
        
        success = session_manager.update_activity(session_id)
        assert success is True
        
        # Check activity was updated
        session = session_manager.get_session_by_access_token(access_token)
        new_activity = session['last_activity']
        assert new_activity > initial_activity
    
    def test_update_access_token(self, session_manager):
        """Test updating access token."""
        user_id = "test_user_123"
        old_token = "old_access_token"
        new_token = "new_access_token"
        
        session_id, _ = session_manager.create_session(
            user_id=user_id,
            access_token=old_token
        )
        
        success = session_manager.update_access_token(session_id, new_token)
        assert success is True
        
        # Old token should not work
        session = session_manager.get_session_by_access_token(old_token)
        assert session is None
        
        # New token should work
        session = session_manager.get_session_by_access_token(new_token)
        assert session is not None
        assert session['access_token'] == new_token
    
    def test_delete_session(self, session_manager):
        """Test deleting a session."""
        user_id = "test_user_123"
        access_token = "test_access_token"
        
        session_id, _ = session_manager.create_session(
            user_id=user_id,
            access_token=access_token
        )
        
        success = session_manager.delete_session(session_id)
        assert success is True
        
        # Session should not exist
        session = session_manager.get_session_by_access_token(access_token)
        assert session is None
    
    def test_delete_user_sessions(self, session_manager):
        """Test deleting all sessions for a user."""
        user_id = "test_user_123"
        
        # Create multiple sessions
        session_manager.create_session(user_id=user_id, access_token="token1")
        session_manager.create_session(user_id=user_id, access_token="token2")
        session_manager.create_session(user_id=user_id, access_token="token3")
        
        count = session_manager.delete_user_sessions(user_id)
        assert count == 3
        
        # All sessions should be deleted
        assert session_manager.get_session_by_access_token("token1") is None
        assert session_manager.get_session_by_access_token("token2") is None
        assert session_manager.get_session_by_access_token("token3") is None
    
    def test_is_session_valid_active(self, session_manager):
        """Test session validation for active session."""
        user_id = "test_user_123"
        access_token = "test_access_token"
        
        session_id, _ = session_manager.create_session(
            user_id=user_id,
            access_token=access_token
        )
        
        session = session_manager.get_session_by_access_token(access_token)
        is_valid, reason = session_manager.is_session_valid(session)
        
        assert is_valid is True
        assert reason is None
    
    def test_is_session_valid_expired(self, session_manager, temp_db):
        """Test session validation for expired session."""
        import sqlite3
        
        user_id = "test_user_123"
        access_token = "test_access_token"
        
        session_id, _ = session_manager.create_session(
            user_id=user_id,
            access_token=access_token
        )
        
        # Manually set expiration to past
        past_time = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE sessions SET expires_at = ? WHERE session_id = ?",
            (past_time, session_id)
        )
        conn.commit()
        conn.close()
        
        session = session_manager.get_session_by_access_token(access_token)
        is_valid, reason = session_manager.is_session_valid(session)
        
        assert is_valid is False
        assert reason == "Session expired"
    
    def test_is_session_valid_inactive(self, session_manager, temp_db):
        """Test session validation for inactive session."""
        import sqlite3
        
        user_id = "test_user_123"
        access_token = "test_access_token"
        
        session_id, _ = session_manager.create_session(
            user_id=user_id,
            access_token=access_token
        )
        
        # Manually set last_activity to past (>30 minutes ago)
        past_time = (datetime.now(timezone.utc) - timedelta(minutes=35)).isoformat()
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE sessions SET last_activity = ? WHERE session_id = ?",
            (past_time, session_id)
        )
        conn.commit()
        conn.close()
        
        session = session_manager.get_session_by_access_token(access_token)
        is_valid, reason = session_manager.is_session_valid(session)
        
        assert is_valid is False
        assert reason == "Session inactive"
    
    def test_cleanup_expired_sessions(self, session_manager, temp_db):
        """Test cleanup of expired and inactive sessions."""
        import sqlite3
        
        # Create valid session
        session_manager.create_session(
            user_id="user1",
            access_token="valid_token"
        )
        
        # Create expired session
        sid1, _ = session_manager.create_session(
            user_id="user2",
            access_token="expired_token"
        )
        
        # Create inactive session
        sid2, _ = session_manager.create_session(
            user_id="user3",
            access_token="inactive_token"
        )
        
        # Manually set expired and inactive times
        past_time = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        inactive_time = (datetime.now(timezone.utc) - timedelta(minutes=35)).isoformat()
        
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE sessions SET expires_at = ? WHERE session_id = ?",
            (past_time, sid1)
        )
        cursor.execute(
            "UPDATE sessions SET last_activity = ? WHERE session_id = ?",
            (inactive_time, sid2)
        )
        conn.commit()
        conn.close()
        
        # Run cleanup
        count = session_manager.cleanup_expired_sessions()
        assert count == 2
        
        # Valid session should still exist
        assert session_manager.get_session_by_access_token("valid_token") is not None
        
        # Expired and inactive sessions should be gone
        assert session_manager.get_session_by_access_token("expired_token") is None
        assert session_manager.get_session_by_access_token("inactive_token") is None
    
    def test_get_user_sessions(self, session_manager):
        """Test getting all sessions for a user."""
        user_id = "test_user_123"
        
        # Create multiple sessions
        session_manager.create_session(user_id=user_id, access_token="token1")
        session_manager.create_session(user_id=user_id, access_token="token2")
        
        sessions = session_manager.get_user_sessions(user_id)
        
        assert len(sessions) == 2
        assert all('session_id' in s for s in sessions)
        assert all('created_at' in s for s in sessions)
        assert all('last_activity' in s for s in sessions)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
