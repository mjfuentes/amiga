"""
Tests for worktree manager

Tests git worktree creation, cleanup, and concurrent usage.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from utils.worktree import WorktreeManager

# Skip tests if running in pre-commit hook with incompatible git environment
# This happens when the repo itself is in a worktree or has special git config
IN_PRECOMMIT = os.environ.get("PRE_COMMIT", "0") == "1"


@pytest.fixture
def temp_repo(tmp_path):
    """Create a temporary git repository for testing"""
    repo_path = tmp_path / "test_repo"
    repo_path.mkdir()

    # Create clean environment without GIT_DIR/GIT_WORK_TREE that might interfere
    clean_env = {k: v for k, v in os.environ.items() if k not in ("GIT_DIR", "GIT_WORK_TREE")}

    # Initialize git repo
    subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True, env=clean_env)
    subprocess.run(
        ["git", "config", "user.name", "Test User"], cwd=repo_path, check=True, capture_output=True, env=clean_env
    )
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=repo_path,
        check=True,
        capture_output=True,
        env=clean_env,
    )

    # Create initial commit
    test_file = repo_path / "README.md"
    test_file.write_text("# Test Repo")
    subprocess.run(["git", "add", "README.md"], cwd=repo_path, check=True, capture_output=True, env=clean_env)
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"], cwd=repo_path, check=True, capture_output=True, env=clean_env
    )

    yield repo_path

    # Cleanup
    shutil.rmtree(repo_path, ignore_errors=True)


@pytest.fixture
def worktree_manager(tmp_path):
    """Create a worktree manager with temporary base path"""
    base_path = tmp_path / "worktrees"
    manager = WorktreeManager(base_path)

    yield manager

    # Cleanup
    if base_path.exists():
        shutil.rmtree(base_path, ignore_errors=True)


def test_create_worktree(temp_repo, worktree_manager):
    """Test creating a worktree"""
    task_id = "test-task-001"

    # Create worktree
    worktree_path = worktree_manager.create_worktree(temp_repo, task_id)

    # Verify worktree was created
    assert worktree_path is not None
    assert worktree_path.exists()
    assert (worktree_path / ".git").exists()
    assert (worktree_path / "README.md").exists()

    # Verify it's in the active worktrees
    assert worktree_manager.is_active(task_id)
    assert worktree_manager.get_worktree_path(task_id) == worktree_path


def test_create_multiple_worktrees(temp_repo, worktree_manager):
    """Test creating multiple worktrees concurrently"""
    task_ids = ["test-task-001", "test-task-002", "test-task-003"]
    worktree_paths = []

    # Create multiple worktrees
    for task_id in task_ids:
        worktree_path = worktree_manager.create_worktree(temp_repo, task_id)
        assert worktree_path is not None
        assert worktree_path.exists()
        worktree_paths.append(worktree_path)

    # Verify all worktrees exist and are different
    assert len(set(worktree_paths)) == len(task_ids)
    for i, task_id in enumerate(task_ids):
        assert worktree_manager.is_active(task_id)
        assert worktree_manager.get_worktree_path(task_id) == worktree_paths[i]


def test_remove_worktree(temp_repo, worktree_manager):
    """Test removing a worktree"""
    task_id = "test-task-001"

    # Create worktree
    worktree_path = worktree_manager.create_worktree(temp_repo, task_id)
    assert worktree_path is not None

    # Remove worktree
    success = worktree_manager.remove_worktree(temp_repo, task_id)
    assert success

    # Verify worktree was removed
    assert not worktree_path.exists()
    assert not worktree_manager.is_active(task_id)
    assert worktree_manager.get_worktree_path(task_id) is None


def test_cleanup_all_worktrees(temp_repo, worktree_manager):
    """Test cleaning up all worktrees"""
    task_ids = ["test-task-001", "test-task-002"]

    # Create multiple worktrees
    for task_id in task_ids:
        worktree_manager.create_worktree(temp_repo, task_id)

    # Clean up all worktrees
    cleaned = worktree_manager.cleanup_all_worktrees()
    assert cleaned == len(task_ids)

    # Verify all worktrees were removed
    for task_id in task_ids:
        assert not worktree_manager.is_active(task_id)


def test_worktree_isolation(temp_repo, worktree_manager):
    """Test that worktrees are isolated from each other"""
    task_id_1 = "test-task-001"
    task_id_2 = "test-task-002"

    # Create two worktrees
    worktree_1 = worktree_manager.create_worktree(temp_repo, task_id_1)
    worktree_2 = worktree_manager.create_worktree(temp_repo, task_id_2)

    # Modify a file in worktree 1
    test_file_1 = worktree_1 / "test1.txt"
    test_file_1.write_text("Modified in worktree 1")

    # Verify the file doesn't exist in worktree 2
    test_file_2 = worktree_2 / "test1.txt"
    assert not test_file_2.exists()

    # Modify a file in worktree 2
    test_file_2 = worktree_2 / "test2.txt"
    test_file_2.write_text("Modified in worktree 2")

    # Verify the file doesn't exist in worktree 1
    test_file_1 = worktree_1 / "test2.txt"
    assert not test_file_1.exists()


def test_worktree_git_operations(temp_repo, worktree_manager):
    """Test that git operations work in worktrees"""
    task_id = "test-task-001"

    # Create worktree
    worktree_path = worktree_manager.create_worktree(temp_repo, task_id)

    # Make a change in the worktree
    test_file = worktree_path / "new_file.txt"
    test_file.write_text("New content")

    # Git operations should work
    subprocess.run(["git", "add", "new_file.txt"], cwd=worktree_path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Add new file"], cwd=worktree_path, check=True, capture_output=True)

    # Verify commit was created
    result = subprocess.run(
        ["git", "log", "--oneline", "-1"], cwd=worktree_path, check=True, capture_output=True, text=True
    )
    assert "Add new file" in result.stdout


def test_cleanup_orphaned_worktrees(temp_repo, worktree_manager):
    """Test cleaning up orphaned worktrees from previous runs"""
    task_id = "test-task-001"

    # Create worktree
    worktree_path = worktree_manager.create_worktree(temp_repo, task_id)
    assert worktree_path is not None

    # Simulate crash: clear active worktrees without proper cleanup
    worktree_manager.active_worktrees.clear()

    # Create a new manager (simulating restart)
    new_manager = WorktreeManager(worktree_manager.worktree_base)

    # Clean up orphaned worktrees
    cleaned = new_manager.cleanup_all_worktrees()
    assert cleaned >= 1

    # Verify worktree was removed
    assert not worktree_path.exists()
