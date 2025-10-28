"""
Tests for session isolation between browser windows.
Ensures Playwright automation and user Chrome browser maintain separate session states.
"""

import sys
from pathlib import Path

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from core.session import SessionManager, Session, Message
from datetime import datetime


class TestSessionIsolation:
    """Test session isolation between different browser windows"""

    def test_create_separate_sessions_same_user(self, tmp_path):
        """Test that same user can have multiple isolated sessions"""
        # Setup
        session_manager = SessionManager(data_dir=str(tmp_path))
        user_id = 123456
        session_id_1 = "session_chrome_abc123"
        session_id_2 = "session_playwright_def456"

        # Create two sessions for same user
        session1 = session_manager.get_or_create_session(user_id, session_id_1)
        session2 = session_manager.get_or_create_session(user_id, session_id_2)

        # Verify sessions are separate
        assert session1.session_id == session_id_1
        assert session2.session_id == session_id_2
        assert session1 is not session2
        assert len(session1.history) == 0
        assert len(session2.history) == 0

    def test_isolated_conversation_history(self, tmp_path):
        """Test that conversation history is isolated per session"""
        # Setup
        session_manager = SessionManager(data_dir=str(tmp_path))
        user_id = 123456
        session_id_chrome = "session_chrome"
        session_id_playwright = "session_playwright"

        # Add messages to Chrome session
        session_manager.add_message(user_id, "user", "Hello from Chrome", session_id_chrome)
        session_manager.add_message(user_id, "assistant", "Hi Chrome user", session_id_chrome)

        # Add different messages to Playwright session
        session_manager.add_message(user_id, "user", "Testing from Playwright", session_id_playwright)
        session_manager.add_message(user_id, "assistant", "Hi Playwright automation", session_id_playwright)

        # Verify histories are isolated
        chrome_history = session_manager.get_history(user_id, session_id_chrome)
        playwright_history = session_manager.get_history(user_id, session_id_playwright)

        assert len(chrome_history) == 2
        assert len(playwright_history) == 2

        assert chrome_history[0].content == "Hello from Chrome"
        assert chrome_history[1].content == "Hi Chrome user"

        assert playwright_history[0].content == "Testing from Playwright"
        assert playwright_history[1].content == "Hi Playwright automation"

    def test_clear_session_only_affects_target(self, tmp_path):
        """Test that clearing one session doesn't affect others"""
        # Setup
        session_manager = SessionManager(data_dir=str(tmp_path))
        user_id = 123456
        session_id_1 = "session_1"
        session_id_2 = "session_2"

        # Add messages to both sessions
        session_manager.add_message(user_id, "user", "Message in session 1", session_id_1)
        session_manager.add_message(user_id, "user", "Message in session 2", session_id_2)

        # Clear only session 1
        session_manager.clear_session(user_id, session_id_1)

        # Verify session 1 is cleared but session 2 is intact
        history_1 = session_manager.get_history(user_id, session_id_1)
        history_2 = session_manager.get_history(user_id, session_id_2)

        assert len(history_1) == 0
        assert len(history_2) == 1
        assert history_2[0].content == "Message in session 2"

    def test_session_persistence_across_restarts(self, tmp_path):
        """Test that sessions are persisted to disk and survive restarts"""
        user_id = 123456
        session_id_1 = "session_chrome"
        session_id_2 = "session_playwright"

        # Create first manager and add messages
        manager1 = SessionManager(data_dir=str(tmp_path))
        manager1.add_message(user_id, "user", "Chrome message", session_id_1)
        manager1.add_message(user_id, "user", "Playwright message", session_id_2)

        # Simulate restart by creating new manager (loads from disk)
        manager2 = SessionManager(data_dir=str(tmp_path))

        # Verify both sessions are loaded
        history_1 = manager2.get_history(user_id, session_id_1)
        history_2 = manager2.get_history(user_id, session_id_2)

        assert len(history_1) == 1
        assert len(history_2) == 1
        assert history_1[0].content == "Chrome message"
        assert history_2[0].content == "Playwright message"

    def test_session_id_key_format(self, tmp_path):
        """Test that session storage uses correct composite key format"""
        # Setup
        session_manager = SessionManager(data_dir=str(tmp_path))
        user_id = 123456
        session_id = "session_abc123"

        # Add message
        session_manager.add_message(user_id, "user", "Test message", session_id)

        # Verify internal storage uses composite key
        composite_key = (user_id, session_id)
        assert composite_key in session_manager.sessions
        assert session_manager.sessions[composite_key].session_id == session_id

    def test_backward_compatibility_default_session(self, tmp_path):
        """Test backward compatibility with old session format (no session_id)"""
        # Setup
        session_manager = SessionManager(data_dir=str(tmp_path))
        user_id = 123456

        # Add message without explicit session_id (should use "default")
        session_manager.add_message(user_id, "user", "Old format message")

        # Verify message is stored in default session
        default_history = session_manager.get_history(user_id, "default")
        assert len(default_history) == 1
        assert default_history[0].content == "Old format message"

    def test_multiple_users_multiple_sessions(self, tmp_path):
        """Test that multiple users can each have multiple sessions"""
        # Setup
        session_manager = SessionManager(data_dir=str(tmp_path))
        user1_id = 111111
        user2_id = 222222
        session_chrome = "session_chrome"
        session_playwright = "session_playwright"

        # User 1: Add messages to both Chrome and Playwright sessions
        session_manager.add_message(user1_id, "user", "User 1 Chrome", session_chrome)
        session_manager.add_message(user1_id, "user", "User 1 Playwright", session_playwright)

        # User 2: Add messages to both Chrome and Playwright sessions
        session_manager.add_message(user2_id, "user", "User 2 Chrome", session_chrome)
        session_manager.add_message(user2_id, "user", "User 2 Playwright", session_playwright)

        # Verify all 4 sessions are isolated
        assert len(session_manager.sessions) == 4

        u1_chrome = session_manager.get_history(user1_id, session_chrome)
        u1_playwright = session_manager.get_history(user1_id, session_playwright)
        u2_chrome = session_manager.get_history(user2_id, session_chrome)
        u2_playwright = session_manager.get_history(user2_id, session_playwright)

        assert u1_chrome[0].content == "User 1 Chrome"
        assert u1_playwright[0].content == "User 1 Playwright"
        assert u2_chrome[0].content == "User 2 Chrome"
        assert u2_playwright[0].content == "User 2 Playwright"

    def test_workspace_isolation_per_session(self, tmp_path):
        """Test that workspace settings are isolated per session"""
        # Setup
        session_manager = SessionManager(data_dir=str(tmp_path))
        user_id = 123456
        session_id_1 = "session_1"
        session_id_2 = "session_2"

        # Set different workspaces for different sessions
        session_manager.set_workspace(user_id, "/workspace/project_a", session_id_1)
        session_manager.set_workspace(user_id, "/workspace/project_b", session_id_2)

        # Verify workspaces are isolated
        workspace_1 = session_manager.get_workspace(user_id, session_id_1)
        workspace_2 = session_manager.get_workspace(user_id, session_id_2)

        assert workspace_1 == "/workspace/project_a"
        assert workspace_2 == "/workspace/project_b"

    def test_get_session_stats_per_session(self, tmp_path):
        """Test that session stats are calculated per session"""
        # Setup
        session_manager = SessionManager(data_dir=str(tmp_path))
        user_id = 123456
        session_id_1 = "session_1"
        session_id_2 = "session_2"

        # Add different amounts of messages to each session
        session_manager.add_message(user_id, "user", "User msg 1", session_id_1)
        session_manager.add_message(user_id, "assistant", "Assistant msg 1", session_id_1)
        session_manager.add_message(user_id, "user", "User msg 2", session_id_1)

        session_manager.add_message(user_id, "user", "Single message", session_id_2)

        # Get stats for each session
        stats_1 = session_manager.get_session_stats(user_id, session_id_1)
        stats_2 = session_manager.get_session_stats(user_id, session_id_2)

        assert stats_1["message_count"] == 3
        assert stats_1["user_messages"] == 2
        assert stats_1["assistant_messages"] == 1

        assert stats_2["message_count"] == 1
        assert stats_2["user_messages"] == 1
        assert stats_2["assistant_messages"] == 0

    def test_session_id_generation_uniqueness(self):
        """Test that session IDs are unique (for frontend logic)"""
        # This tests the logic that would be in the frontend
        # Simulating multiple session ID generations
        session_ids = set()
        for _ in range(100):
            # Simulate frontend session ID generation
            import time
            import random
            session_id = f"session_{int(time.time() * 1000)}_{random.randint(100000, 999999)}"
            session_ids.add(session_id)
            time.sleep(0.001)  # Small delay to ensure timestamp difference

        # All session IDs should be unique
        assert len(session_ids) == 100


# Fixtures
@pytest.fixture
def tmp_path(tmp_path_factory):
    """Provide temporary directory for testing"""
    return tmp_path_factory.mktemp("test_sessions")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
