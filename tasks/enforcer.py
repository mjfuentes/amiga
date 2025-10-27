"""
Workflow Enforcement System
Ensures all coding tasks follow proper testing and commit workflows
"""

import logging
import subprocess
from pathlib import Path

from core.exceptions import AMIGAError

logger = logging.getLogger(__name__)


class WorkflowEnforcer:
    """Enforces testing and commit requirements for code changes"""

    def __init__(self, workspace: Path):
        self.workspace = Path(workspace)
        self.pre_commit_installed = False
        self._check_pre_commit()

    def _check_pre_commit(self):
        """Check if pre-commit is installed in the repository"""
        try:
            # Try python3 -m pre_commit first (more reliable)
            result = subprocess.run(
                ["python3", "-m", "pre_commit", "--version"],
                capture_output=True,
                text=True,
                cwd=str(self.workspace),
            )
            self.pre_commit_installed = result.returncode == 0

            # Fallback to pre-commit command
            if not self.pre_commit_installed:
                result = subprocess.run(
                    ["pre-commit", "--version"], capture_output=True, text=True, cwd=str(self.workspace)
                )
                self.pre_commit_installed = result.returncode == 0

            if self.pre_commit_installed:
                logger.info(f"Pre-commit is available in {self.workspace}")
        except Exception as e:
            logger.debug(f"Pre-commit not available: {e}")
            self.pre_commit_installed = False

    def get_changed_files(self) -> list[str]:
        """Get list of modified/untracked files"""
        try:
            # Get modified files
            result = subprocess.run(
                ["git", "diff", "--name-only"], capture_output=True, text=True, cwd=str(self.workspace)
            )
            modified = result.stdout.strip().split("\n") if result.stdout.strip() else []

            # Get untracked files
            result = subprocess.run(
                ["git", "ls-files", "--others", "--exclude-standard"],
                capture_output=True,
                text=True,
                cwd=str(self.workspace),
            )
            untracked = result.stdout.strip().split("\n") if result.stdout.strip() else []

            all_files = modified + untracked
            return [f for f in all_files if f and f.endswith(".py")]

        except Exception as e:
            logger.error(f"Error getting changed files: {e}", exc_info=True)
            return []

    def has_uncommitted_changes(self) -> bool:
        """Check if there are uncommitted changes"""
        try:
            result = subprocess.run(
                ["git", "status", "--porcelain"], capture_output=True, text=True, cwd=str(self.workspace)
            )
            return bool(result.stdout.strip())
        except Exception as e:
            logger.error(f"Error checking git status: {e}", exc_info=True)
            return False

    def run_tests(self) -> tuple[bool, str]:
        """Run tests if they exist"""
        test_paths = [
            self.workspace / "tests",
            self.workspace / "test",
        ]

        # Check for test files
        test_files = []
        for pattern in ["test_*.py", "*_test.py"]:
            test_files.extend(list(self.workspace.rglob(pattern)))

        # Check for test directories
        test_dirs = [p for p in test_paths if p.exists() and p.is_dir()]

        if not test_files and not test_dirs:
            return True, "No tests found - skipping test execution"

        try:
            logger.info(f"Running tests in {self.workspace}")
            result = subprocess.run(
                ["python3", "-m", "pytest", "-v", "--tb=short"],
                capture_output=True,
                text=True,
                cwd=str(self.workspace),
            )

            if result.returncode == 0:
                return True, f"Tests passed:\n{result.stdout}"
            else:
                return False, f"Tests failed:\n{result.stdout}\n{result.stderr}"
        except FileNotFoundError:
            return False, "pytest not available - install with: pip install pytest"
        except Exception as e:
            return False, f"Error running tests: {str(e)}"

    def run_pre_commit_hooks(self) -> tuple[bool, str]:
        """Run pre-commit hooks on changed files"""
        if not self.pre_commit_installed:
            return True, "Pre-commit not installed - skipping hooks"

        try:
            changed_files = self.get_changed_files()
            if not changed_files:
                return True, "No changed files to check"

            logger.info(f"Running pre-commit hooks on {len(changed_files)} files")

            # Try python3 -m pre_commit first
            cmd = ["python3", "-m", "pre_commit", "run", "--files"] + changed_files
            result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(self.workspace))

            # If that fails, try pre-commit command
            if result.returncode != 0 and "No module named" in result.stderr:
                cmd = ["pre-commit", "run", "--files"] + changed_files
                result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(self.workspace))

            # Pre-commit returns 0 if all hooks pass, 1 if any fail
            if result.returncode == 0:
                return True, "Pre-commit hooks passed"
            else:
                return False, f"Pre-commit hooks failed:\n{result.stdout}\n{result.stderr}"
        except Exception as e:
            return False, f"Error running pre-commit hooks: {str(e)}"

    def create_commit(self, message: str) -> tuple[bool, str]:
        """Create a git commit with all changes"""
        try:
            # Stage all changes
            result = subprocess.run(["git", "add", "-A"], capture_output=True, text=True, cwd=str(self.workspace))

            if result.returncode != 0:
                return False, f"Failed to stage changes: {result.stderr}"

            # Create commit
            result = subprocess.run(
                ["git", "commit", "-m", message], capture_output=True, text=True, cwd=str(self.workspace)
            )

            if result.returncode == 0:
                return True, f"Commit created successfully:\n{result.stdout}"
            else:
                return False, f"Commit failed:\n{result.stderr}"

        except Exception as e:
            return False, f"Error creating commit: {str(e)}"

    def enforce_workflow(self, task_description: str) -> tuple[bool, str]:
        """
        Enforce the complete workflow:
        1. Run pre-commit hooks
        2. Run tests
        3. Create commit if everything passes

        Returns: (success, message)
        """
        messages = []

        # Check if there are changes to commit
        if not self.has_uncommitted_changes():
            return True, "No changes to commit"

        # Step 1: Run pre-commit hooks
        messages.append("\n=== Pre-commit Hooks ===")
        hooks_passed, hooks_msg = self.run_pre_commit_hooks()
        messages.append(hooks_msg)

        if not hooks_passed:
            return False, "\n".join(messages) + "\n\nWorkflow failed: Pre-commit hooks did not pass"

        # Step 2: Run tests
        messages.append("\n=== Running Tests ===")
        tests_passed, tests_msg = self.run_tests()
        messages.append(tests_msg)

        if not tests_passed:
            return False, "\n".join(messages) + "\n\nWorkflow failed: Tests did not pass"

        # Step 3: Create commit
        messages.append("\n=== Creating Commit ===")

        # Generate commit message from task description
        commit_msg = self._generate_commit_message(task_description)

        commit_success, commit_msg_result = self.create_commit(commit_msg)
        messages.append(commit_msg_result)

        if not commit_success:
            return False, "\n".join(messages) + "\n\nWorkflow failed: Could not create commit"

        return True, "\n".join(messages) + "\n\nWorkflow completed successfully!"

    def _generate_commit_message(self, task_description: str) -> str:
        """Generate a commit message from task description"""
        # Truncate if too long
        if len(task_description) > 100:
            first_line = task_description[:97] + "..."
        else:
            first_line = task_description

        commit_msg = f"{first_line}\n\n"
        commit_msg += "Automated commit from Claude Code workflow enforcement"

        return commit_msg

    def get_workflow_prompt_context(self) -> str:
        """Get context about workflow requirements to add to Claude prompts"""
        context = """
WORKFLOW REQUIREMENTS:
After completing any code changes, you MUST:
1. Ensure pre-commit hooks pass (formatting, linting, security checks)
2. Run tests and ensure they pass
3. Create a git commit with your changes

Use the workflow enforcement system to validate your changes before considering the task complete.

IMPORTANT: Never use placeholder messages like "I'll work on this" or "Working on it". Always complete the entire task and provide the actual implementation. The workflow enforcer will run after you finish, so ensure all code is properly written and tested.
"""
        return context
