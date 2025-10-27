"""
Tests for custom exception hierarchy
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from core.exceptions import (
    AMIGAError,
    APIError,
    AuthenticationError,
    ConfigError,
    DatabaseError,
    RateLimitError,
    TaskError,
    ValidationError,
)


class TestExceptionHierarchy:
    """Test exception hierarchy"""

    def test_all_inherit_from_agentlab_error(self):
        """All custom exceptions should inherit from AMIGAError"""
        exceptions = [
            DatabaseError,
            ConfigError,
            APIError,
            TaskError,
            ValidationError,
            RateLimitError,
            AuthenticationError,
        ]

        for exc_class in exceptions:
            assert issubclass(exc_class, AMIGAError)
            assert issubclass(exc_class, Exception)

    def test_base_exception_creation(self):
        """AMIGAError can be created and raised"""
        with pytest.raises(AMIGAError) as exc_info:
            raise AMIGAError("Test error")

        assert str(exc_info.value) == "Test error"

    def test_database_error(self):
        """DatabaseError can be created with message"""
        error = DatabaseError("Connection failed")
        assert str(error) == "Connection failed"
        assert isinstance(error, AMIGAError)

    def test_config_error(self):
        """ConfigError can be created with message"""
        error = ConfigError("Missing API key")
        assert str(error) == "Missing API key"
        assert isinstance(error, AMIGAError)

    def test_api_error(self):
        """APIError can be created with message"""
        error = APIError("Rate limit exceeded")
        assert str(error) == "Rate limit exceeded"
        assert isinstance(error, AMIGAError)

    def test_task_error(self):
        """TaskError can be created with message"""
        error = TaskError("Task execution failed")
        assert str(error) == "Task execution failed"
        assert isinstance(error, AMIGAError)

    def test_validation_error(self):
        """ValidationError can be created with message"""
        error = ValidationError("Invalid input")
        assert str(error) == "Invalid input"
        assert isinstance(error, AMIGAError)

    def test_rate_limit_error(self):
        """RateLimitError can be created with message"""
        error = RateLimitError("Too many requests")
        assert str(error) == "Too many requests"
        assert isinstance(error, AMIGAError)

    def test_authentication_error(self):
        """AuthenticationError can be created with message"""
        error = AuthenticationError("Invalid credentials")
        assert str(error) == "Invalid credentials"
        assert isinstance(error, AMIGAError)

    def test_exception_catch_patterns(self):
        """Test that exceptions can be caught properly"""

        # Catch specific exception
        with pytest.raises(DatabaseError):
            raise DatabaseError("DB error")

        # Catch base exception
        with pytest.raises(AMIGAError):
            raise DatabaseError("DB error")

        # Catch as Exception
        with pytest.raises(Exception):
            raise DatabaseError("DB error")

    def test_exception_with_cause(self):
        """Test exception chaining"""
        try:
            try:
                raise ValueError("Original error")
            except ValueError as e:
                raise DatabaseError("Database operation failed") from e
        except DatabaseError as e:
            assert str(e) == "Database operation failed"
            assert isinstance(e.__cause__, ValueError)
            assert str(e.__cause__) == "Original error"
