"""Custom exceptions for AMIGA.

This module defines a hierarchy of exceptions used throughout the application
to provide better error handling and more specific error messages.
"""


class AMIGAError(Exception):
    """Base exception for AMIGA.

    All custom exceptions in the application should inherit from this class.
    """
    pass


class DatabaseError(AMIGAError):
    """Database operation failed.

    Raised when database queries, connections, or transactions fail.
    """
    pass


class ConfigError(AMIGAError):
    """Configuration error.

    Raised when configuration is missing, invalid, or cannot be loaded.
    """
    pass


class APIError(AMIGAError):
    """External API error.

    Raised when external API calls (Anthropic, Telegram, etc.) fail.
    """
    pass


class TaskError(AMIGAError):
    """Task execution error.

    Raised when background tasks fail to execute or complete.
    """
    pass


class ValidationError(AMIGAError):
    """Input validation error.

    Raised when user input or data validation fails.
    """
    pass


class RateLimitError(AMIGAError):
    """Rate limit exceeded.

    Raised when rate limits (API or Telegram) are exceeded.
    """
    pass


class AuthenticationError(AMIGAError):
    """Authentication failed.

    Raised when user authentication or authorization fails.
    """
    pass
