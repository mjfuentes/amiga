"""
Centralized logging configuration for AMIGA.

Provides a single source of truth for logging setup to eliminate duplication
across entry points (main.py, server.py, scripts).
"""

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path


def setup_logging(
    name: str,
    log_file: str | Path | None = None,
    level: str | None = None,
    format_string: str | None = None,
    console: bool = True,
    force: bool = True,
) -> logging.Logger:
    """
    Configure and return logger with file and console handlers.

    Args:
        name: Logger name (usually __name__)
        log_file: Path to log file (default: logs/bot.log)
        level: Log level string (default: INFO, or LOG_LEVEL env var)
        format_string: Custom format (default: standard timestamp format)
        console: Whether to add console handler (default: True)
        force: Whether to replace existing handlers (default: True)

    Returns:
        Configured logger instance

    Example:
        >>> from utils.logging_setup import setup_logging
        >>> logger = setup_logging(__name__)
        >>> logger.info("Application started")

        >>> # Custom log file and level
        >>> logger = setup_logging(__name__, log_file="logs/custom.log", level="DEBUG")

        >>> # Script without console output
        >>> logger = setup_logging(__name__, console=False)
    """
    # Default format
    if format_string is None:
        format_string = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

    # Use environment variable or default level
    if level is None:
        level = os.getenv("LOG_LEVEL", "INFO")

    # Convert string level to logging constant
    level_value = getattr(logging, level.upper(), logging.INFO)

    # Default log file
    if log_file is None:
        log_file = "logs/bot.log"

    # Create logger
    logger = logging.getLogger(name)
    logger.setLevel(level_value)

    # Remove existing handlers if force=True
    if force and logger.handlers:
        logger.handlers.clear()

    # Create formatter
    formatter = logging.Formatter(format_string)

    # File handler with rotation
    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    file_handler = RotatingFileHandler(
        log_path,
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5,
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(level_value)
    logger.addHandler(file_handler)

    # Console handler (optional)
    if console:
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        console_handler.setLevel(level_value)
        logger.addHandler(console_handler)

    return logger


def configure_root_logger(
    level: str | None = None,
    format_string: str | None = None,
    handlers: list | None = None,
    force: bool = True,
) -> None:
    """
    Configure the root logger with basicConfig-style settings.

    Useful for applications that need to configure logging globally before
    any other modules create loggers.

    Args:
        level: Log level string (default: INFO, or LOG_LEVEL env var)
        format_string: Custom format (default: standard timestamp format)
        handlers: List of handlers (default: file + console)
        force: Whether to replace existing configuration (default: True)

    Example:
        >>> from utils.logging_setup import configure_root_logger
        >>> configure_root_logger(level="DEBUG")
        >>> logger = logging.getLogger(__name__)
        >>> logger.info("Using root logger config")
    """
    # Default format
    if format_string is None:
        format_string = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

    # Use environment variable or default level
    if level is None:
        level = os.getenv("LOG_LEVEL", "INFO")

    # Convert string level to logging constant
    level_value = getattr(logging, level.upper(), logging.INFO)

    # Create default handlers if none provided
    if handlers is None:
        # File handler with rotation
        log_path = Path("logs/bot.log")
        log_path.parent.mkdir(parents=True, exist_ok=True)

        file_handler = RotatingFileHandler(
            log_path,
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=5,
        )

        handlers = [file_handler]

    # Configure root logger
    logging.basicConfig(
        format=format_string,
        level=level_value,
        handlers=handlers,
        force=force,
    )
