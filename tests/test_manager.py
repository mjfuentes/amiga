"""
Tests for TaskManager cleanup functionality
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import asyncio
import tempfile
from datetime import datetime

import pytest

from tasks.database import Database
from tasks.manager import TaskManager


@pytest.fixture
def temp_db():
    """Create a temporary database for testing"""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    
    db = Database(db_path)
    yield db
    
    # Cleanup
    db.conn.close()
    Path(db_path).unlink(missing_ok=True)


@pytest.fixture
def task_manager(temp_db):
    """Create a TaskManager with temporary database"""
    return TaskManager(db=temp_db)


class TestCleanupAllPendingTasks:
    """Test cleanup_all_pending_tasks method"""
    
    def test_cleanup_pending_tasks_all_users(self, task_manager):
        """Test cleanup of pending tasks across all users"""
        # Create test tasks
        asyncio.run(task_manager.create_task(
            user_id=1,
            description="Task 1",
            workspace="/tmp/test",
            model="sonnet",
        ))
        asyncio.run(task_manager.create_task(
            user_id=2,
            description="Task 2",
            workspace="/tmp/test",
            model="sonnet",
        ))
        
        # Verify tasks are pending
        tasks = task_manager.get_user_tasks(user_id=1, status="pending")
        assert len(tasks) == 1
        tasks = task_manager.get_user_tasks(user_id=2, status="pending")
        assert len(tasks) == 1
        
        # Cleanup all pending tasks
        cleaned_count = task_manager.cleanup_all_pending_tasks()
        
        # Verify cleanup
        assert cleaned_count == 2
        
        # Verify tasks are now stopped
        tasks = task_manager.get_user_tasks(user_id=1, status="pending")
        assert len(tasks) == 0
        tasks = task_manager.get_user_tasks(user_id=2, status="pending")
        assert len(tasks) == 0
        
        # Verify tasks have stopped status
        stopped_tasks = task_manager.get_stopped_tasks()
        assert len(stopped_tasks) == 2
        assert stopped_tasks[0].error == "Cleaned up by user request"
        assert stopped_tasks[1].error == "Cleaned up by user request"
    
    def test_cleanup_pending_tasks_specific_user(self, task_manager):
        """Test cleanup of pending tasks for specific user only"""
        # Create test tasks for different users
        asyncio.run(task_manager.create_task(
            user_id=1,
            description="User 1 Task",
            workspace="/tmp/test",
            model="sonnet",
        ))
        asyncio.run(task_manager.create_task(
            user_id=2,
            description="User 2 Task",
            workspace="/tmp/test",
            model="sonnet",
        ))
        
        # Cleanup only user 1's tasks
        cleaned_count = task_manager.cleanup_all_pending_tasks(user_id=1)
        
        # Verify only 1 task cleaned
        assert cleaned_count == 1
        
        # Verify user 1's task is stopped
        tasks = task_manager.get_user_tasks(user_id=1, status="pending")
        assert len(tasks) == 0
        
        # Verify user 2's task is still pending
        tasks = task_manager.get_user_tasks(user_id=2, status="pending")
        assert len(tasks) == 1
    
    def test_cleanup_no_pending_tasks(self, task_manager):
        """Test cleanup when no pending tasks exist"""
        # Create a completed task
        task = asyncio.run(task_manager.create_task(
            user_id=1,
            description="Completed Task",
            workspace="/tmp/test",
            model="sonnet",
        ))
        asyncio.run(task_manager.update_task(task.task_id, status="completed"))
        
        # Cleanup should return 0
        cleaned_count = task_manager.cleanup_all_pending_tasks()
        assert cleaned_count == 0
    
    def test_cleanup_mixed_status_tasks(self, task_manager):
        """Test cleanup only affects pending tasks, not other statuses"""
        # Create tasks with different statuses
        pending_task = asyncio.run(task_manager.create_task(
            user_id=1,
            description="Pending Task",
            workspace="/tmp/test",
            model="sonnet",
        ))
        
        running_task = asyncio.run(task_manager.create_task(
            user_id=1,
            description="Running Task",
            workspace="/tmp/test",
            model="sonnet",
        ))
        asyncio.run(task_manager.update_task(running_task.task_id, status="running", pid=12345))
        
        completed_task = asyncio.run(task_manager.create_task(
            user_id=1,
            description="Completed Task",
            workspace="/tmp/test",
            model="sonnet",
        ))
        asyncio.run(task_manager.update_task(completed_task.task_id, status="completed"))
        
        # Cleanup
        cleaned_count = task_manager.cleanup_all_pending_tasks(user_id=1)
        
        # Verify only 1 task cleaned (the pending one)
        assert cleaned_count == 1
        
        # Verify other tasks still have their original status
        running = task_manager.get_task(running_task.task_id)
        assert running.status == "running"
        
        completed = task_manager.get_task(completed_task.task_id)
        assert completed.status == "completed"
        
        # Verify pending task is now stopped
        stopped = task_manager.get_task(pending_task.task_id)
        assert stopped.status == "stopped"
        assert stopped.error == "Cleaned up by user request"


class TestCleanupAllPendingTasksDatabase:
    """Test database-level cleanup_all_pending_tasks method"""
    
    def test_database_cleanup_all_users(self, temp_db):
        """Test database cleanup across all users"""
        # Create tasks directly in database
        asyncio.run(temp_db.create_task(
            task_id="task1",
            user_id=1,
            description="Task 1",
            workspace="/tmp/test",
            model="sonnet",
        ))
        asyncio.run(temp_db.create_task(
            task_id="task2",
            user_id=2,
            description="Task 2",
            workspace="/tmp/test",
            model="sonnet",
        ))
        
        # Cleanup
        cleaned_count = temp_db.cleanup_all_pending_tasks()
        assert cleaned_count == 2
        
        # Verify both tasks are stopped
        task1 = temp_db.get_task("task1")
        assert task1["status"] == "stopped"
        assert task1["error"] == "Cleaned up by user request"
        
        task2 = temp_db.get_task("task2")
        assert task2["status"] == "stopped"
        assert task2["error"] == "Cleaned up by user request"
    
    def test_database_cleanup_specific_user(self, temp_db):
        """Test database cleanup for specific user"""
        # Create tasks for different users
        asyncio.run(temp_db.create_task(
            task_id="task1",
            user_id=1,
            description="User 1 Task",
            workspace="/tmp/test",
            model="sonnet",
        ))
        asyncio.run(temp_db.create_task(
            task_id="task2",
            user_id=2,
            description="User 2 Task",
            workspace="/tmp/test",
            model="sonnet",
        ))
        
        # Cleanup only user 1
        cleaned_count = temp_db.cleanup_all_pending_tasks(user_id=1)
        assert cleaned_count == 1
        
        # Verify user 1's task is stopped
        task1 = temp_db.get_task("task1")
        assert task1["status"] == "stopped"
        
        # Verify user 2's task is still pending
        task2 = temp_db.get_task("task2")
        assert task2["status"] == "pending"
