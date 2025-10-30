"""
Tests for database thread-local pattern
"""

import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pytest
from core.database_manager import get_database, close_database, _thread_local


class TestDatabaseThreadLocal:
    """Test database thread-local manager"""

    def test_get_database_returns_same_instance_per_thread(self):
        """Test that get_database returns the same instance within a thread"""
        # Get database twice in same thread
        db1 = get_database()
        db2 = get_database()

        # Should be same instance within same thread
        assert db1 is db2

    def test_different_threads_get_different_instances(self):
        """Test that different threads get different database instances"""
        main_db = get_database()
        thread_db = None

        def thread_func():
            nonlocal thread_db
            thread_db = get_database()

        thread = threading.Thread(target=thread_func)
        thread.start()
        thread.join()

        # Different threads should have different instances
        assert main_db is not thread_db

    def test_close_database_clears_thread_local(self):
        """Test that close_database clears the thread-local instance"""
        # Get database
        db1 = get_database()
        assert db1 is not None

        # Close it
        close_database()

        # Get new instance - should be different (new connection)
        db2 = get_database()
        assert db2 is not None
        assert db2 is not db1

    def test_close_database_when_none(self):
        """Test that close_database handles None gracefully"""
        # Clear thread-local storage manually
        if hasattr(_thread_local, 'db'):
            _thread_local.db = None

        # Call close - should not raise
        close_database()

        # Ensure database is reopened for other tests
        get_database()

    def test_database_manager_in_application_context(self):
        """Test that database manager works in application-like scenario"""
        # Simulate multiple components getting database in same thread
        db_main = get_database()
        db_task_manager = get_database()
        db_tracker = get_database()

        # All should be same instance within same thread
        assert db_main is db_task_manager
        assert db_main is db_tracker

    def test_thread_isolation(self):
        """Test that thread-local storage properly isolates database instances"""
        results = []

        def worker(worker_id):
            db = get_database()
            # Store the id of the database instance
            results.append((worker_id, id(db)))

        threads = []
        for i in range(3):
            thread = threading.Thread(target=worker, args=(i,))
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()

        # Each thread should have gotten a unique instance
        instance_ids = [result[1] for result in results]
        assert len(set(instance_ids)) == 3, "Each thread should have unique database instance"

    def teardown_method(self):
        """Cleanup after each test"""
        # Close current thread's database connection
        close_database()
