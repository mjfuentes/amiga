"""Tests for config validation."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
import os
from core.config_validator import validate_production_config


class TestProductionConfig:
    """Test production configuration validation."""

    def test_production_safe_config(self, monkeypatch):
        """Test configuration with all production settings."""
        # Set all safe production values
        monkeypatch.delenv("DEBUG", raising=False)
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-valid-key-123456")
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "1234567890:ABCdefGHIjklMNOpqrsTUVwxyz")
        monkeypatch.setenv("ALLOWED_USERS", "12345,67890")
        monkeypatch.setenv("DAILY_COST_LIMIT", "100")
        monkeypatch.setenv("MONTHLY_COST_LIMIT", "1000")
        monkeypatch.setenv("LOG_LEVEL", "INFO")
        monkeypatch.setenv("SESSION_TIMEOUT_MINUTES", "60")
        monkeypatch.delenv("AGENTLAB_DB_PATH", raising=False)
        monkeypatch.setenv("MONITORING_AUTO_RESTART", "false")

        warnings = validate_production_config()
        assert len(warnings) == 0, f"Expected no warnings but got: {warnings}"

    def test_insecure_defaults(self, monkeypatch):
        """Test detection of insecure defaults."""
        # Clear all sensitive env vars
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
        monkeypatch.delenv("ALLOWED_USERS", raising=False)
        monkeypatch.delenv("DAILY_COST_LIMIT", raising=False)
        monkeypatch.delenv("MONTHLY_COST_LIMIT", raising=False)

        warnings = validate_production_config()
        assert len(warnings) >= 5, f"Expected at least 5 warnings but got {len(warnings)}: {warnings}"
        assert any("ANTHROPIC_API_KEY" in w for w in warnings)
        assert any("TELEGRAM_BOT_TOKEN" in w for w in warnings)
        assert any("ALLOWED_USERS" in w for w in warnings)
        assert any("DAILY_COST_LIMIT" in w for w in warnings)
        assert any("MONTHLY_COST_LIMIT" in w for w in warnings)

    def test_debug_mode_detection(self, monkeypatch):
        """Test detection of DEBUG mode."""
        monkeypatch.setenv("DEBUG", "true")
        # Set other required vars
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-valid")
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:valid")
        monkeypatch.setenv("ALLOWED_USERS", "123")

        warnings = validate_production_config()
        assert any("DEBUG mode" in w for w in warnings)

    def test_default_api_key_values(self, monkeypatch):
        """Test detection of default placeholder API keys."""
        test_cases = [
            "your_anthropic_api_key_here",
            "test-key",
            "",
        ]

        for api_key in test_cases:
            monkeypatch.setenv("ANTHROPIC_API_KEY", api_key)
            monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:valid")
            monkeypatch.setenv("ALLOWED_USERS", "123")

            warnings = validate_production_config()
            assert any(
                "ANTHROPIC_API_KEY" in w for w in warnings
            ), f"Expected warning for API key '{api_key}' but got: {warnings}"

    def test_default_bot_token_values(self, monkeypatch):
        """Test detection of default placeholder bot tokens."""
        test_cases = [
            "your_bot_token_here",
            "test-token",
            "",
        ]

        for bot_token in test_cases:
            monkeypatch.setenv("TELEGRAM_BOT_TOKEN", bot_token)
            monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-valid")
            monkeypatch.setenv("ALLOWED_USERS", "123")

            warnings = validate_production_config()
            assert any(
                "TELEGRAM_BOT_TOKEN" in w for w in warnings
            ), f"Expected warning for bot token '{bot_token}' but got: {warnings}"

    def test_wildcard_allowed_users(self, monkeypatch):
        """Test detection of wildcard in ALLOWED_USERS."""
        monkeypatch.setenv("ALLOWED_USERS", "*")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-valid")
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:valid")

        warnings = validate_production_config()
        assert any("ALLOWED_USERS" in w and "wildcard" in w for w in warnings)

    def test_missing_cost_limits(self, monkeypatch):
        """Test detection of missing cost limits."""
        monkeypatch.delenv("DAILY_COST_LIMIT", raising=False)
        monkeypatch.delenv("MONTHLY_COST_LIMIT", raising=False)
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-valid")
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:valid")
        monkeypatch.setenv("ALLOWED_USERS", "123")

        warnings = validate_production_config()
        assert any("DAILY_COST_LIMIT" in w for w in warnings)
        assert any("MONTHLY_COST_LIMIT" in w for w in warnings)

    def test_high_session_timeout(self, monkeypatch):
        """Test detection of excessive session timeout."""
        monkeypatch.setenv("SESSION_TIMEOUT_MINUTES", "180")  # 3 hours
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-valid")
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:valid")
        monkeypatch.setenv("ALLOWED_USERS", "123")

        warnings = validate_production_config()
        assert any("SESSION_TIMEOUT_MINUTES" in w and "180" in w for w in warnings)

    def test_invalid_session_timeout(self, monkeypatch):
        """Test detection of invalid session timeout value."""
        monkeypatch.setenv("SESSION_TIMEOUT_MINUTES", "not-a-number")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-valid")
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:valid")
        monkeypatch.setenv("ALLOWED_USERS", "123")

        warnings = validate_production_config()
        assert any("SESSION_TIMEOUT_MINUTES" in w and "invalid" in w for w in warnings)

    def test_tmp_database_location(self, monkeypatch):
        """Test detection of database in /tmp/."""
        monkeypatch.setenv("AGENTLAB_DB_PATH", "/tmp/agentlab.db")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-valid")
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:valid")
        monkeypatch.setenv("ALLOWED_USERS", "123")

        warnings = validate_production_config()
        assert any("Database in /tmp/" in w for w in warnings)

    def test_debug_log_level(self, monkeypatch):
        """Test detection of DEBUG log level."""
        monkeypatch.setenv("LOG_LEVEL", "DEBUG")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-valid")
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:valid")
        monkeypatch.setenv("ALLOWED_USERS", "123")

        warnings = validate_production_config()
        assert any("LOG_LEVEL is DEBUG" in w for w in warnings)

    def test_monitoring_auto_restart(self, monkeypatch):
        """Test detection of monitoring auto-restart in production."""
        monkeypatch.setenv("MONITORING_AUTO_RESTART", "true")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-valid")
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:valid")
        monkeypatch.setenv("ALLOWED_USERS", "123")

        warnings = validate_production_config()
        assert any("MONITORING_AUTO_RESTART" in w for w in warnings)

    def test_acceptable_session_timeout(self, monkeypatch):
        """Test that reasonable session timeouts don't trigger warnings."""
        for timeout in ["30", "60", "90", "120"]:
            monkeypatch.setenv("SESSION_TIMEOUT_MINUTES", timeout)
            monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-valid")
            monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:valid")
            monkeypatch.setenv("ALLOWED_USERS", "123")
            monkeypatch.setenv("DAILY_COST_LIMIT", "100")
            monkeypatch.setenv("MONTHLY_COST_LIMIT", "1000")

            warnings = validate_production_config()
            assert not any(
                "SESSION_TIMEOUT_MINUTES" in w for w in warnings
            ), f"Unexpected warning for timeout {timeout}: {warnings}"

    def test_safe_database_location(self, monkeypatch):
        """Test that non-tmp database locations don't trigger warnings."""
        monkeypatch.setenv("AGENTLAB_DB_PATH", "/var/lib/agentlab/agentlab.db")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-valid")
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:valid")
        monkeypatch.setenv("ALLOWED_USERS", "123")
        monkeypatch.setenv("DAILY_COST_LIMIT", "100")
        monkeypatch.setenv("MONTHLY_COST_LIMIT", "1000")

        warnings = validate_production_config()
        assert not any("Database" in w for w in warnings), f"Unexpected database warning: {warnings}"
