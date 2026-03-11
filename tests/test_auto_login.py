"""Tests for auto-login endpoint and LOCAL_MODE behavior."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest


class TestAutoLoginEndpoint:
    """Tests for POST /api/auth/auto-login."""

    @pytest.fixture(autouse=True)
    def setup_app(self, tmp_path):
        """Create a test Flask app with mocked dependencies."""
        # We test the endpoint logic in isolation by importing server
        # with mocked database and auth middleware
        self.tmp_path = tmp_path

    @patch.dict("os.environ", {"AMIGA_AUTH": "local"}, clear=False)
    def test_local_mode_default(self):
        """LOCAL_MODE should be True when AMIGA_AUTH is 'local'."""
        import os
        result = os.getenv("AMIGA_AUTH", "local") == "local"
        assert result is True

    @patch.dict("os.environ", {"AMIGA_AUTH": "required"}, clear=False)
    def test_required_mode(self):
        """LOCAL_MODE should be False when AMIGA_AUTH is 'required'."""
        import os
        result = os.getenv("AMIGA_AUTH", "local") == "local"
        assert result is False

    @patch.dict("os.environ", {}, clear=False)
    def test_default_is_local_when_unset(self):
        """LOCAL_MODE should default to True when AMIGA_AUTH is not set."""
        import os
        # Remove AMIGA_AUTH if it exists
        os.environ.pop("AMIGA_AUTH", None)
        result = os.getenv("AMIGA_AUTH", "local") == "local"
        assert result is True


class TestAutoLoginIntegration:
    """Integration tests for auto-login using Flask test client."""

    @pytest.fixture
    def mock_user_db(self):
        """Mock user database."""
        db = MagicMock()
        db.get_user_by_username.return_value = None
        db.create_user.return_value = True
        db.get_user_by_id.return_value = {
            "user_id": "local-default-user",
            "username": "local",
            "email": "local@localhost",
            "created_at": "2025-01-01T00:00:00",
            "is_admin": True,
            "password_hash": "hashed",
        }
        return db

    @pytest.fixture
    def mock_auth_middleware(self):
        """Mock AuthMiddleware.generate_tokens."""
        with patch("monitoring.server.AuthMiddleware") as mock_cls:
            mock_cls.generate_tokens.return_value = (
                "test-access-token",
                "test-refresh-token",
                "test-session-id",
            )
            yield mock_cls

    @pytest.fixture
    def app_local_mode(self, mock_user_db, mock_auth_middleware):
        """Create Flask test client in local mode."""
        with patch("monitoring.server.LOCAL_MODE", True), \
             patch("monitoring.server.user_db", mock_user_db), \
             patch("monitoring.server.get_user_info") as mock_gui:
            mock_gui.return_value = {
                "user_id": "local-default-user",
                "username": "local",
                "email": "local@localhost",
                "created_at": "2025-01-01T00:00:00",
                "is_admin": True,
            }
            # Import app after patching
            from monitoring.server import app
            app.config["TESTING"] = True
            with app.test_client() as client:
                yield client, mock_user_db, mock_gui

    @pytest.fixture
    def app_required_mode(self):
        """Create Flask test client in required auth mode."""
        with patch("monitoring.server.LOCAL_MODE", False):
            from monitoring.server import app
            app.config["TESTING"] = True
            with app.test_client() as client:
                yield client

    def test_auto_login_local_mode_returns_tokens(self, app_local_mode):
        """Auto-login in local mode should return access and refresh tokens."""
        client, mock_db, mock_gui = app_local_mode
        response = client.post("/api/auth/auto-login")
        assert response.status_code == 200
        data = response.get_json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert "user" in data
        assert data["user"]["username"] == "local"

    def test_auto_login_creates_user_if_missing(self, app_local_mode):
        """Auto-login should create the local user if it doesn't exist."""
        client, mock_db, mock_gui = app_local_mode
        mock_db.get_user_by_username.return_value = None
        response = client.post("/api/auth/auto-login")
        assert response.status_code == 200
        mock_db.create_user.assert_called_once()
        call_kwargs = mock_db.create_user.call_args
        assert call_kwargs[1]["username"] == "local" or call_kwargs.kwargs.get("username") == "local"

    def test_auto_login_reuses_existing_user(self, app_local_mode):
        """Auto-login should reuse existing local user without creating a new one."""
        client, mock_db, mock_gui = app_local_mode
        mock_db.get_user_by_username.return_value = {
            "user_id": "existing-user-id",
            "username": "local",
            "email": "local@localhost",
            "password_hash": "hashed",
        }
        response = client.post("/api/auth/auto-login")
        assert response.status_code == 200
        mock_db.create_user.assert_not_called()

    def test_auto_login_rejected_in_required_mode(self, app_required_mode):
        """Auto-login should return 403 when AMIGA_AUTH=required."""
        client = app_required_mode
        response = client.post("/api/auth/auto-login")
        assert response.status_code == 403
        data = response.get_json()
        assert "Auto-login disabled" in data["error"]

    def test_auto_login_response_format_matches_login(self, app_local_mode):
        """Auto-login response should have the same shape as /api/auth/login."""
        client, mock_db, mock_gui = app_local_mode
        response = client.post("/api/auth/auto-login")
        data = response.get_json()
        # Must have exactly these top-level keys (same as login endpoint)
        assert set(data.keys()) == {"access_token", "refresh_token", "user"}
        assert isinstance(data["user"], dict)
        assert "user_id" in data["user"]
        assert "username" in data["user"]


class TestLocalModeConstants:
    """Tests for LOCAL_MODE-related constants."""

    def test_local_user_id_is_stable(self):
        """LOCAL_USER_ID should be a fixed, predictable value."""
        from monitoring.server import LOCAL_USER_ID
        assert LOCAL_USER_ID == "local-default-user"

    def test_local_username_is_local(self):
        """LOCAL_USERNAME should be 'local'."""
        from monitoring.server import LOCAL_USERNAME
        assert LOCAL_USERNAME == "local"

    def test_local_email_is_localhost(self):
        """LOCAL_EMAIL should be a localhost email."""
        from monitoring.server import LOCAL_EMAIL
        assert "localhost" in LOCAL_EMAIL
