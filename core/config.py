"""
Configuration constants for AMIGA project.

Centralizes all file paths and directory configurations to eliminate hardcoded paths
throughout the codebase. Supports environment variable overrides for flexibility.
"""

import os
from pathlib import Path

# Project root directory (parent of telegram_bot/)
PROJECT_ROOT = Path(__file__).parent.parent


# Data directory (for database and JSON files)
# Can be overridden via AGENTLAB_DATA_DIR environment variable
_data_dir_env = os.getenv("AGENTLAB_DATA_DIR")
if _data_dir_env:
    DATA_DIR = Path(_data_dir_env)
else:
    DATA_DIR = PROJECT_ROOT / "data"


# Ensure data directory exists
DATA_DIR.mkdir(exist_ok=True, parents=True)


# Database path (SQLite database for tasks, tool usage, games)
# Can be overridden via AGENTLAB_DB_PATH environment variable
_db_path_env = os.getenv("AGENTLAB_DB_PATH")
if _db_path_env:
    DATABASE_PATH = Path(_db_path_env)
else:
    DATABASE_PATH = DATA_DIR / "agentlab.db"


# JSON storage paths (legacy, to be migrated to SQLite)
SESSIONS_FILE = DATA_DIR / "sessions.json"
RESTART_STATE_FILE = DATA_DIR / "restart_state.json"


# Logs directory
LOGS_DIR = PROJECT_ROOT / "logs"
LOGS_DIR.mkdir(exist_ok=True, parents=True)


# Session logs directory
SESSIONS_LOGS_DIR = LOGS_DIR / "sessions"
SESSIONS_LOGS_DIR.mkdir(exist_ok=True, parents=True)


# Main bot log file
BOT_LOG_FILE = LOGS_DIR / "bot.log"


# Monitoring log file
MONITORING_LOG_FILE = LOGS_DIR / "monitoring.log"


# Convert paths to strings for backward compatibility with code expecting strings
DATABASE_PATH_STR = str(DATABASE_PATH)
DATA_DIR_STR = str(DATA_DIR)
SESSIONS_FILE_STR = str(SESSIONS_FILE)
RESTART_STATE_FILE_STR = str(RESTART_STATE_FILE)
SESSIONS_LOGS_DIR_STR = str(SESSIONS_LOGS_DIR)
BOT_LOG_FILE_STR = str(BOT_LOG_FILE)
MONITORING_LOG_FILE_STR = str(MONITORING_LOG_FILE)


def get_data_dir_for_cwd() -> str:
    """
    Get data directory path relative to current working directory.

    This is a helper function for scripts that may be run from different locations.
    Used by monitoring_server.py which can be run from telegram_bot/ or project root.

    Returns:
        str: Path to data directory relative to CWD
    """
    if Path.cwd().name == "telegram_bot":
        # Running from telegram_bot/ directory
        return "../data"
    else:
        # Running from project root
        return "data"


def get_sessions_dir_for_cwd() -> str:
    """
    Get sessions logs directory path relative to current working directory.

    Returns:
        str: Path to sessions logs directory relative to CWD
    """
    if Path.cwd().name == "telegram_bot":
        # Running from telegram_bot/ directory
        return "../logs/sessions"
    else:
        # Running from project root
        return "logs/sessions"


def get_db_path_with_fallback(cli_arg: str | None = None) -> str:
    """
    Get database path with priority: CLI arg > env var > default.

    This helper is useful for analysis scripts that accept --db-path argument.

    Args:
        cli_arg: Optional database path from command-line argument

    Returns:
        str: Resolved database path
    """
    if cli_arg:
        return cli_arg
    return DATABASE_PATH_STR
