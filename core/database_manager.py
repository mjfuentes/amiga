"""Thread-local database manager for application-wide database access."""
import threading

from core.config import DATABASE_PATH_STR
from tasks.database import Database

# Thread-local storage for Database instances
_thread_local = threading.local()


def get_database() -> Database:
    """
    Get thread-local Database instance.

    Each thread gets its own Database connection, avoiding SQLite thread-safety issues.
    This prevents "sqlite3.InterfaceError: bad parameter or other API misuse" errors
    that occur when multiple Flask threads share a single connection.

    Returns:
        Database instance for current thread
    """
    if not hasattr(_thread_local, 'db') or _thread_local.db is None:
        _thread_local.db = Database(DATABASE_PATH_STR)
    return _thread_local.db


def close_database():
    """
    Close database connection for current thread (call on shutdown).

    Note: In a multi-threaded environment, this only closes the connection
    for the calling thread. Other threads maintain their connections.
    """
    if hasattr(_thread_local, 'db') and _thread_local.db:
        _thread_local.db.close()
        _thread_local.db = None
