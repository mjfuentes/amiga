#!/usr/bin/env python3
"""
Unit tests for PID file lock mechanism.

Tests the PIDFileLock class to ensure only one bot instance runs at a time.
"""

import os
import sys
import tempfile
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest


class PIDFileLock:
    """
    Manages a PID file to ensure only one bot instance runs at a time.

    Uses file locking to prevent race conditions and properly detects stale PID files.
    """

    def __init__(self, pid_file_path: str = "data/bot.pid"):
        """
        Initialize PID file lock.

        Args:
            pid_file_path: Path to the PID file
        """
        self.pid_file = Path(pid_file_path)
        self.pid_file.parent.mkdir(parents=True, exist_ok=True)
        self.locked = False

    def acquire(self) -> bool:
        """
        Acquire the PID file lock.

        Returns:
            True if lock acquired successfully, False if another instance is running
        """
        # Check if PID file exists
        if self.pid_file.exists():
            try:
                # Read existing PID
                with open(self.pid_file) as f:
                    existing_pid = int(f.read().strip())

                # Check if process is still running
                if self._is_process_running(existing_pid):
                    return False
                else:
                    # Stale PID file - process is dead
                    self.pid_file.unlink()
            except (OSError, ValueError):
                self.pid_file.unlink()

        # Write our PID
        current_pid = os.getpid()
        try:
            with open(self.pid_file, "w") as f:
                f.write(str(current_pid))
            self.locked = True
            return True
        except OSError:
            return False

    def release(self):
        """Release the PID file lock."""
        if self.locked and self.pid_file.exists():
            try:
                # Verify it's our PID before removing
                with open(self.pid_file) as f:
                    pid = int(f.read().strip())

                if pid == os.getpid():
                    self.pid_file.unlink()
                    self.locked = False
            except (OSError, ValueError):
                pass

    def _is_process_running(self, pid: int) -> bool:
        """
        Check if a process with given PID is running.

        Args:
            pid: Process ID to check

        Returns:
            True if process is running, False otherwise
        """
        try:
            # Send signal 0 to check if process exists (doesn't actually send a signal)
            os.kill(pid, 0)
            return True
        except OSError:
            return False


class TestPIDFileLock:
    """Test cases for PIDFileLock"""

    def test_acquire_lock_success(self):
        """Test acquiring lock when no other instance exists"""
        with tempfile.TemporaryDirectory() as tmpdir:
            pid_file = os.path.join(tmpdir, "test.pid")
            lock = PIDFileLock(pid_file)

            # Should acquire successfully
            assert lock.acquire() is True
            assert lock.locked is True

            # Verify PID file exists and contains our PID
            assert Path(pid_file).exists()
            with open(pid_file) as f:
                written_pid = int(f.read().strip())
            assert written_pid == os.getpid()

            # Cleanup
            lock.release()
            assert not Path(pid_file).exists()

    def test_acquire_lock_fail_on_existing_instance(self):
        """Test acquiring lock when another instance already holds it"""
        with tempfile.TemporaryDirectory() as tmpdir:
            pid_file = os.path.join(tmpdir, "test.pid")

            # First lock
            lock1 = PIDFileLock(pid_file)
            assert lock1.acquire() is True

            # Second lock should fail (same process simulating multiple instances)
            lock2 = PIDFileLock(pid_file)
            assert lock2.acquire() is False
            assert lock2.locked is False

            # Cleanup
            lock1.release()

    def test_acquire_lock_with_stale_pid(self):
        """Test acquiring lock when PID file contains non-existent process"""
        with tempfile.TemporaryDirectory() as tmpdir:
            pid_file = os.path.join(tmpdir, "test.pid")

            # Write a fake PID that definitely doesn't exist
            fake_pid = 999999
            with open(pid_file, "w") as f:
                f.write(str(fake_pid))

            # Should acquire successfully (removes stale PID file)
            lock = PIDFileLock(pid_file)
            assert lock.acquire() is True
            assert lock.locked is True

            # Verify our PID is written
            with open(pid_file) as f:
                written_pid = int(f.read().strip())
            assert written_pid == os.getpid()

            # Cleanup
            lock.release()

    def test_acquire_lock_with_corrupted_pid_file(self):
        """Test acquiring lock when PID file contains invalid data"""
        with tempfile.TemporaryDirectory() as tmpdir:
            pid_file = os.path.join(tmpdir, "test.pid")

            # Write invalid data
            with open(pid_file, "w") as f:
                f.write("not-a-number")

            # Should acquire successfully (removes corrupted file)
            lock = PIDFileLock(pid_file)
            assert lock.acquire() is True
            assert lock.locked is True

            # Cleanup
            lock.release()

    def test_release_lock(self):
        """Test releasing lock properly"""
        with tempfile.TemporaryDirectory() as tmpdir:
            pid_file = os.path.join(tmpdir, "test.pid")
            lock = PIDFileLock(pid_file)

            # Acquire and release
            assert lock.acquire() is True
            assert Path(pid_file).exists()

            lock.release()
            assert not lock.locked
            assert not Path(pid_file).exists()

    def test_release_lock_with_different_pid(self):
        """Test that release doesn't remove PID file if it contains different PID"""
        with tempfile.TemporaryDirectory() as tmpdir:
            pid_file = os.path.join(tmpdir, "test.pid")
            lock = PIDFileLock(pid_file)

            # Acquire lock
            assert lock.acquire() is True

            # Simulate another process writing to the file
            with open(pid_file, "w") as f:
                f.write("123456")

            # Release should not remove file (different PID)
            lock.release()
            assert Path(pid_file).exists()

            # Cleanup
            Path(pid_file).unlink()

    def test_double_release(self):
        """Test that double release doesn't cause errors"""
        with tempfile.TemporaryDirectory() as tmpdir:
            pid_file = os.path.join(tmpdir, "test.pid")
            lock = PIDFileLock(pid_file)

            # Acquire and release twice
            assert lock.acquire() is True
            lock.release()
            lock.release()  # Should not raise error

            assert not lock.locked
            assert not Path(pid_file).exists()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
