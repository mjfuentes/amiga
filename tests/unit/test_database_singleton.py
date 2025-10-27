"""
Tests for database singleton pattern
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pytest
from core.database_manager import get_database, close_database, _db_instance


class TestDatabaseSingleton:
    """Test database singleton manager"""

    def test_get_database_returns_same_instance(self):
        """Test that get_database returns the same instance"""
        # Get database twice
        db1 = get_database()
        db2 = get_database()

        # Should be same instance
        assert db1 is db2

    def test_close_database_clears_instance(self):
        """Test that close_database clears the singleton"""
        # Get database
        db1 = get_database()
        assert db1 is not None

        # Close it
        close_database()

        # Get new instance - should be different (new connection)
        db2 = get_database()
        assert db2 is not None
        assert db2 is not db1

        # Note: db2 is now the active singleton for other tests to use

    def test_close_database_when_none(self):
        """Test that close_database handles None gracefully"""
        # Save current state
        import core.database_manager as dbm
        original_db = dbm._db_instance

        # Set to None manually
        dbm._db_instance = None

        # Call close - should not raise
        close_database()

        # Ensure database is reopened for other tests
        # Don't restore old instance (it might be closed), just get a new one
        get_database()

    def test_database_manager_in_application_context(self):
        """Test that database manager works in application-like scenario"""
        # Simulate multiple components getting database
        db_main = get_database()
        db_task_manager = get_database()
        db_tracker = get_database()

        # All should be same instance
        assert db_main is db_task_manager
        assert db_main is db_tracker

        # Don't cleanup - leave singleton active for other tests

    def teardown_method(self):
        """Cleanup after each test"""
        # Don't close singleton here - let pytest handle cleanup
        # or it will break other tests that use the singleton
        pass
