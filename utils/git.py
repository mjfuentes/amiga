"""
Git dirty state tracker for managing uncommitted changes across repositories
"""

import json
import logging
import subprocess
from pathlib import Path

from core.exceptions import AMIGAError

logger = logging.getLogger(__name__)


class GitTracker:
    """Track repositories with uncommitted changes"""

    def __init__(self, data_file: str = "data/git_tracker.json"):
        self.data_file = data_file
        self.dirty_repos: dict[str, str] = {}  # {repo_path: last_operation}
        self._load()

    def _load(self) -> None:
        """Load dirty repos from disk"""
        try:
            if Path(self.data_file).exists():
                with open(self.data_file) as f:
                    self.dirty_repos = json.load(f)
                logger.info(f"Loaded {len(self.dirty_repos)} dirty repos from disk")
        except Exception as e:
            logger.error(
                f"Error loading git tracker: {e}",
                exc_info=True,
                extra={"data_file": self.data_file}
            )
            self.dirty_repos = {}

    def _save(self) -> None:
        """Save dirty repos to disk"""
        try:
            Path(self.data_file).parent.mkdir(parents=True, exist_ok=True)
            with open(self.data_file, "w") as f:
                json.dump(self.dirty_repos, f, indent=2)
        except Exception as e:
            logger.error(
                f"Error saving git tracker: {e}",
                exc_info=True,
                extra={"data_file": self.data_file}
            )

    def check_repo_status(self, repo_path: str) -> tuple[bool, str]:
        """
        Check if repo has uncommitted changes

        Returns:
            (has_changes, status_message)
        """
        try:
            # Run git status --porcelain
            result = subprocess.run(["git", "status", "--porcelain"], cwd=repo_path, capture_output=True, text=True)

            if result.returncode != 0:
                return False, "Not a git repository"

            # If output is not empty, there are changes
            has_changes = bool(result.stdout.strip())

            if has_changes:
                # Count staged and unstaged
                lines = result.stdout.strip().split("\n")
                staged = sum(1 for line in lines if line[0] in "MADRC")
                unstaged = sum(1 for line in lines if line[1] in "MADRC?")

                status = f"{len(lines)} files changed"
                if staged:
                    status += f" ({staged} staged)"
                if unstaged:
                    status += f" ({unstaged} unstaged)"

                return True, status

            return False, "Clean"
        except Exception as e:
            logger.error(
                f"Error checking git status for {repo_path}: {e}",
                exc_info=True,
                extra={"repo_path": repo_path}
            )
            return False, f"Error: {e}"

    def mark_dirty(self, repo_path: str, operation: str = "modified") -> bool:
        """Mark repo as having uncommitted changes"""
        repo_path = str(Path(repo_path).resolve())

        # Verify it actually has changes
        has_changes, status = self.check_repo_status(repo_path)

        if has_changes:
            self.dirty_repos[repo_path] = operation
            self._save()
            logger.info(f"Marked {repo_path} as dirty: {status}")
            return True
        else:
            # Remove from dirty if it's actually clean
            if repo_path in self.dirty_repos:
                del self.dirty_repos[repo_path]
                self._save()
            return False

    def mark_clean(self, repo_path: str) -> None:
        """Mark repo as clean (changes committed)"""
        repo_path = str(Path(repo_path).resolve())

        if repo_path in self.dirty_repos:
            del self.dirty_repos[repo_path]
            self._save()
            logger.info(f"Marked {repo_path} as clean")

    def get_dirty_repos(self) -> dict[str, str]:
        """Get all repos with uncommitted changes"""
        # Verify each one still has changes
        to_remove = []
        for repo_path in list(self.dirty_repos.keys()):
            has_changes, _ = self.check_repo_status(repo_path)
            if not has_changes:
                to_remove.append(repo_path)

        # Clean up false positives
        for repo_path in to_remove:
            del self.dirty_repos[repo_path]

        if to_remove:
            self._save()

        return self.dirty_repos.copy()

    def is_dirty(self, repo_path: str) -> bool:
        """Check if repo is marked as dirty"""
        repo_path = str(Path(repo_path).resolve())

        # Check actual status
        has_changes, _ = self.check_repo_status(repo_path)

        # Update our records
        if has_changes and repo_path not in self.dirty_repos:
            self.mark_dirty(repo_path)
        elif not has_changes and repo_path in self.dirty_repos:
            self.mark_clean(repo_path)

        return has_changes

    def get_blocking_message(self, target_repo: str) -> str | None:
        """
        Get message if there are dirty repos blocking work on target_repo

        Returns None if no blocking, otherwise returns warning message
        """
        dirty = self.get_dirty_repos()

        if not dirty:
            return None

        target_path = str(Path(target_repo).resolve())

        # If target is already dirty, allow continuing work on it
        if target_path in dirty:
            return None

        # Block if trying to work on different repo
        lines = ["⚠️ Can't work on that repo yet. You have uncommitted changes:"]
        for repo_path, _operation in dirty.items():
            repo_name = Path(repo_path).name
            has_changes, status = self.check_repo_status(repo_path)
            lines.append(f"\n• {repo_name}: {status}")

        lines.append("\n\nCommit or discard changes first:")
        lines.append("- Say 'commit [repo]' to commit changes")
        lines.append("- Say 'discard [repo]' to discard changes")
        lines.append("- Say 'show diff [repo]' to see what changed")

        return "\n".join(lines)

    def format_status_message(self) -> str:
        """Format status message showing all dirty repos"""
        dirty = self.get_dirty_repos()

        if not dirty:
            return "All repos clean ✓"

        lines = [f"📝 Uncommitted changes in {len(dirty)} repo(s):"]
        for repo_path in dirty:
            repo_name = Path(repo_path).name
            has_changes, status = self.check_repo_status(repo_path)
            lines.append(f"\n• {repo_name}: {status}")

        return "\n".join(lines)


# Global instance
_tracker: GitTracker | None = None


def get_git_tracker() -> GitTracker:
    """Get global git tracker instance"""
    global _tracker
    if _tracker is None:
        _tracker = GitTracker()
    return _tracker
