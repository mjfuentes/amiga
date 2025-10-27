"""
DEPRECATED: Git worktree manager for concurrent Claude Code sessions

⚠️  DEPRECATION NOTICE ⚠️
=====================
This module is DEPRECATED as of 2025-10-22.

Worktree management has moved to explicit workflow control via the git-worktree agent.

OLD APPROACH (deprecated):
- ClaudeSessionPool automatically created/cleaned worktrees
- Invisible to workflows
- Less control over lifecycle

NEW APPROACH (current):
- Workflows explicitly create worktrees via git-worktree agent (step 0)
- Workflows explicitly cleanup worktrees via git-worktree agent (final step)
- Full visibility and control
- See .claude/agents/git-worktree.md

This module remains for backward compatibility but should not be used for new code.
Existing code should migrate to using the git-worktree agent within workflows.

---

Original documentation preserved below:

Git worktree manager for concurrent Claude Code sessions

Manages git worktrees to allow multiple Claude Code instances to work
on different branches simultaneously without conflicts.

IMPORTANT: Merge Responsibility
================================
This module does NOT handle merging branches to main. That is the
responsibility of agents (code_agent, frontend_agent, etc.).

Workflow:
1. WorktreeManager creates isolated worktree for task
2. Agent works in worktree, commits to task/{task_id} branch
3. **Agent merges to main** before completing (critical!)
4. WorktreeManager removes worktree and deletes branch on cleanup

Safety Protection:
The remove_worktree() method includes a safety check that ABORTS deletion
if unmerged commits are detected. Work is preserved and the worktree/branch
remain intact for manual merge. Check logs for recovery instructions.

See .claude/agents/code_agent.md for agent merge instructions.
"""

import logging
import shutil
import subprocess
from pathlib import Path

from core.exceptions import AMIGAError

logger = logging.getLogger(__name__)


class WorktreeManager:
    """
    Manages git worktrees for concurrent task execution

    Each task gets its own worktree in a temporary location, allowing
    multiple Claude Code sessions to work on different branches without
    conflicts.
    """

    def __init__(self, worktree_base_path: Path | str = "/tmp/agentlab-worktrees"):  # nosec B108
        """
        Initialize worktree manager

        Args:
            worktree_base_path: Base directory for all worktrees
        """
        self.worktree_base = Path(worktree_base_path)
        self.worktree_base.mkdir(parents=True, exist_ok=True)
        self.active_worktrees: dict[str, Path] = {}  # task_id -> worktree_path

    def create_worktree(self, repo_path: Path, task_id: str, base_branch: str = "main") -> Path | None:
        """
        Create a git worktree for a task

        Args:
            repo_path: Path to the main git repository
            task_id: Unique task identifier
            base_branch: Branch to base the worktree on (default: main)

        Returns:
            Path to the worktree, or None if creation failed
        """
        try:
            # Generate worktree path and branch name
            worktree_path = self.worktree_base / task_id
            branch_name = f"task/{task_id}"

            # Check if worktree already exists
            if worktree_path.exists():
                logger.warning(f"Worktree path {worktree_path} already exists, removing it first")
                self._cleanup_worktree_dir(worktree_path)

            # Ensure we're in a git repo
            if not (repo_path / ".git").exists():
                logger.error(
                    f"{repo_path} is not a git repository",
                    exc_info=True,
                    extra={"repo_path": str(repo_path), "task_id": task_id}
                )
                return None

            # Check if branch already exists (from previous run)
            result = subprocess.run(
                ["git", "branch", "--list", branch_name],
                cwd=str(repo_path),
                capture_output=True,
                text=True,
                check=False,
            )

            if result.stdout.strip():
                # Branch exists, delete it first
                logger.info(f"Branch {branch_name} already exists, deleting it")
                delete_result = subprocess.run(
                    ["git", "branch", "-D", branch_name],
                    cwd=str(repo_path),
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if delete_result.returncode != 0:
                    logger.warning(f"Failed to delete branch {branch_name}: {delete_result.stderr}")

            # Create worktree with new branch
            logger.info(f"Creating worktree at {worktree_path} for task {task_id}")
            result = subprocess.run(
                ["git", "worktree", "add", "-b", branch_name, str(worktree_path), base_branch],
                cwd=str(repo_path),
                capture_output=True,
                text=True,
                check=False,
            )

            if result.returncode != 0:
                logger.error(
                    f"Failed to create worktree: {result.stderr}",
                    exc_info=True,
                    extra={"task_id": task_id, "repo_path": str(repo_path), "stderr": result.stderr}
                )
                return None

            logger.info(f"Successfully created worktree for task {task_id} at {worktree_path}")
            self.active_worktrees[task_id] = worktree_path
            return worktree_path

        except Exception as e:
            logger.error(
                f"Error creating worktree for task {task_id}: {e}",
                exc_info=True,
                extra={"task_id": task_id, "repo_path": str(repo_path)}
            )
            return None

    def remove_worktree(self, repo_path: Path, task_id: str, check_merge: bool = True) -> bool:
        """
        Remove a git worktree after task completion

        IMPORTANT: This does NOT merge changes. The agent/workflow is responsible
        for merging to the target branch before cleanup. This method only removes
        the worktree and branch.

        Args:
            repo_path: Path to the main git repository
            task_id: Task identifier
            check_merge: If True, warn if branch has unmerged commits (default: True)

        Returns:
            True if successful, False otherwise
        """
        try:
            if task_id not in self.active_worktrees:
                logger.warning(f"Task {task_id} not in active worktrees")
                return False

            worktree_path = self.active_worktrees[task_id]
            branch_name = f"task/{task_id}"

            # Check for unmerged commits (safety check)
            if check_merge:
                result = subprocess.run(
                    ["git", "cherry", "-v", "main", branch_name],
                    cwd=str(repo_path),
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if result.returncode == 0 and result.stdout.strip():
                    unmerged_commits = len(result.stdout.strip().splitlines())
                    logger.error(
                        f"ABORTING cleanup: Branch {branch_name} has {unmerged_commits} unmerged commit(s). "
                        "Work would be LOST if we proceed! Agent should have merged before cleanup.",
                        exc_info=True,
                        extra={"task_id": task_id, "branch": branch_name, "unmerged_commits": unmerged_commits}
                    )
                    logger.error(
                        f"Unmerged commits:\n{result.stdout[:500]}",
                        exc_info=True,
                        extra={"task_id": task_id, "branch": branch_name}
                    )
                    logger.error(
                        f"Worktree preserved at {worktree_path}. "
                        f"To recover: cd {repo_path} && git merge {branch_name}",
                        exc_info=True,
                        extra={"task_id": task_id, "worktree_path": str(worktree_path)}
                    )
                    # DO NOT delete - keep worktree and branch intact
                    return False

            # Remove worktree from git
            logger.info(f"Removing worktree for task {task_id}")
            result = subprocess.run(
                ["git", "worktree", "remove", str(worktree_path), "--force"],
                cwd=str(repo_path),
                capture_output=True,
                text=True,
                check=False,
            )

            if result.returncode != 0:
                logger.warning(f"git worktree remove failed (may already be removed): {result.stderr}")
                # Continue with directory cleanup anyway

            # Clean up directory if it still exists
            self._cleanup_worktree_dir(worktree_path)

            # Delete the branch
            logger.info(f"Deleting branch {branch_name}")
            result = subprocess.run(
                ["git", "branch", "-D", branch_name],
                cwd=str(repo_path),
                capture_output=True,
                text=True,
                check=False,
            )

            if result.returncode != 0:
                logger.warning(f"Failed to delete branch {branch_name}: {result.stderr}")

            # Remove from tracking
            del self.active_worktrees[task_id]
            logger.info(f"Successfully removed worktree for task {task_id}")
            return True

        except Exception as e:
            logger.error(
                f"Error removing worktree for task {task_id}: {e}",
                exc_info=True,
                extra={"task_id": task_id, "repo_path": str(repo_path)}
            )
            return False

    def cleanup_orphaned_worktrees(self, repo_path: Path) -> int:
        """
        Clean up orphaned worktrees from previous runs

        This should be called on startup to clean up worktrees from
        tasks that were interrupted or crashed.

        Args:
            repo_path: Path to the main git repository

        Returns:
            Number of worktrees cleaned up
        """
        try:
            cleaned = 0

            # List all git worktrees
            result = subprocess.run(
                ["git", "worktree", "list", "--porcelain"],
                cwd=str(repo_path),
                capture_output=True,
                text=True,
                check=True,
            )

            # Parse worktree list
            worktrees = []
            current_worktree: dict[str, str] = {}
            for line in result.stdout.splitlines():
                if line.startswith("worktree "):
                    if current_worktree:
                        worktrees.append(current_worktree)
                    current_worktree = {"path": line.split(" ", 1)[1]}
                elif line.startswith("branch "):
                    current_worktree["branch"] = line.split(" ", 1)[1]

            if current_worktree:
                worktrees.append(current_worktree)

            # Find and remove orphaned worktrees (under our base path)
            for worktree in worktrees:
                wt_path = Path(worktree["path"])

                # Only handle worktrees under our base path
                if not wt_path.is_relative_to(self.worktree_base):
                    continue

                # Extract task_id from path
                task_id = wt_path.name
                branch = worktree.get("branch", "")

                logger.info(f"Found orphaned worktree for task {task_id} at {wt_path}")

                # Remove worktree
                subprocess.run(
                    ["git", "worktree", "remove", str(wt_path), "--force"],
                    cwd=str(repo_path),
                    capture_output=True,
                    text=True,
                    check=False,
                )

                # Clean up directory
                self._cleanup_worktree_dir(wt_path)

                # Delete branch if it matches our pattern
                if branch.startswith("refs/heads/task/"):
                    branch_name = branch.replace("refs/heads/", "")
                    subprocess.run(
                        ["git", "branch", "-D", branch_name],
                        cwd=str(repo_path),
                        capture_output=True,
                        text=True,
                        check=False,
                    )

                cleaned += 1

            if cleaned > 0:
                logger.info(f"Cleaned up {cleaned} orphaned worktrees")

            return cleaned

        except Exception as e:
            logger.error(
                f"Error cleaning up orphaned worktrees: {e}",
                exc_info=True,
                extra={"repo_path": str(repo_path)}
            )
            return 0

    def _cleanup_worktree_dir(self, path: Path) -> None:
        """
        Force remove a worktree directory

        Args:
            path: Path to the worktree directory
        """
        try:
            if path.exists():
                logger.debug(f"Removing directory {path}")
                shutil.rmtree(path, ignore_errors=True)
        except Exception as e:
            logger.warning(f"Failed to remove directory {path}: {e}")

    def get_worktree_path(self, task_id: str) -> Path | None:
        """
        Get the worktree path for a task

        Args:
            task_id: Task identifier

        Returns:
            Path to the worktree, or None if not found
        """
        return self.active_worktrees.get(task_id)

    def is_active(self, task_id: str) -> bool:
        """
        Check if a worktree is active for a task

        Args:
            task_id: Task identifier

        Returns:
            True if worktree exists and is active
        """
        return task_id in self.active_worktrees

    def cleanup_all_worktrees(self) -> int:
        """
        Clean up all worktrees in the base directory

        This is useful on startup to clean up any worktrees from previous runs
        that may not have been properly cleaned up due to crashes or interruptions.

        Returns:
            Number of worktrees cleaned up
        """
        try:
            if not self.worktree_base.exists():
                return 0

            cleaned = 0
            for worktree_dir in self.worktree_base.iterdir():
                if worktree_dir.is_dir():
                    logger.info(f"Cleaning up orphaned worktree directory: {worktree_dir}")
                    self._cleanup_worktree_dir(worktree_dir)
                    cleaned += 1

            # Clear active worktrees tracking
            self.active_worktrees.clear()

            if cleaned > 0:
                logger.info(f"Cleaned up {cleaned} orphaned worktree directories on startup")

            return cleaned

        except Exception as e:
            logger.error(
                f"Error cleaning up all worktrees: {e}",
                exc_info=True,
                extra={"worktree_base": str(self.worktree_base)}
            )
            return 0
