"""Singleton database manager for application-wide database access."""
from core.config import DATABASE_PATH_STR
from tasks.database import Database

_db_instance = None


def get_database() -> Database:
    """Get singleton Database instance."""
    global _db_instance
    if _db_instance is None:
        _db_instance = Database(DATABASE_PATH_STR)
    return _db_instance


def close_database():
    """Close database connection (call on shutdown)."""
    global _db_instance
    if _db_instance:
        _db_instance.close()
        _db_instance = None
