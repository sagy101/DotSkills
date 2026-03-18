"""Tests for sbt-build-test lock file management — stale lock detection."""

import os
import subprocess
import time
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent.parent.parent / "sbt-build-test" / "scripts"
RUN_SBT = SCRIPT_DIR / "run_sbt.sh"


def _create_lock_file(lock_path: Path, pid: int, age_seconds: int = 0) -> None:
    """Create a lock file with the given PID and optional age."""
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text(
        f"pid={pid}\nproject=/tmp/test-project\nstarted_at=2026-03-19 12:00:00\ncommand=test\n"
    )
    if age_seconds > 0:
        # Set mtime to age_seconds ago
        old_time = time.time() - age_seconds
        os.utime(str(lock_path), (old_time, old_time))


def _sanitize(path: str) -> str:
    """Match the sanitize_skill_key function from common.sh."""
    return "".join(c if c.isalnum() or c in "._-" else "_" for c in path)


class TestStaleLockWithDeadPid:
    def test_stale_lock_auto_cleared(self, tmp_path: Path) -> None:
        """Lock file with a non-existent PID should be auto-cleared."""
        cache_root = tmp_path / ".sbt-build-cache"
        locks_dir = cache_root / "locks"
        locks_dir.mkdir(parents=True)

        project_dir = tmp_path / "test-project"
        project_dir.mkdir()
        (project_dir / "build.sbt").write_text('name := "test"\n')

        # Use a PID that definitely doesn't exist
        dead_pid = 99999
        while True:
            try:
                os.kill(dead_pid, 0)
                dead_pid += 1  # This PID exists, try another
            except ProcessLookupError:
                break  # This PID doesn't exist, good
            except PermissionError:
                dead_pid += 1  # Exists but no permission, try another

        key = _sanitize(str(project_dir))
        lock_file = locks_dir / f"{key}.sbt-test.lock"
        _create_lock_file(lock_file, dead_pid)

        # The run_sbt.sh should clear the stale lock and proceed
        # We'll test just the lock detection by running a minimal SBT command
        # that will fail (no SBT installed in test env) but should get past the lock check
        env = dict(os.environ, SBT_BUILD_CACHE_ROOT=str(cache_root))
        result = subprocess.run(
            ["bash", str(RUN_SBT), str(project_dir), "--", "compile"],
            capture_output=True,
            text=True,
            timeout=30,
            env=env,
        )
        combined = result.stdout + result.stderr
        # Should see the warning about stale lock, not the "already active" error
        assert "Stale lock file detected" in combined or "already active" not in combined


class TestLockWithLivePid:
    def test_lock_with_live_pid_blocks(self, tmp_path: Path) -> None:
        """Lock file with a live PID (current process) should block."""
        cache_root = tmp_path / ".sbt-build-cache"
        locks_dir = cache_root / "locks"
        locks_dir.mkdir(parents=True)

        project_dir = tmp_path / "test-project"
        project_dir.mkdir()
        (project_dir / "build.sbt").write_text('name := "test"\n')

        # Use current PID (definitely alive)
        key = _sanitize(str(project_dir))
        lock_file = locks_dir / f"{key}.sbt-test.lock"
        _create_lock_file(lock_file, os.getpid())

        env = dict(os.environ, SBT_BUILD_CACHE_ROOT=str(cache_root))
        result = subprocess.run(
            ["bash", str(RUN_SBT), str(project_dir), "--", "test"],
            capture_output=True,
            text=True,
            timeout=30,
            env=env,
        )
        combined = result.stdout + result.stderr
        assert result.returncode == 2
        assert "already active" in combined


class TestLockOlderThan2Hours:
    def test_old_lock_auto_cleared(self, tmp_path: Path) -> None:
        """Lock older than 2 hours should be treated as stale regardless of PID."""
        cache_root = tmp_path / ".sbt-build-cache"
        locks_dir = cache_root / "locks"
        locks_dir.mkdir(parents=True)

        project_dir = tmp_path / "test-project"
        project_dir.mkdir()
        (project_dir / "build.sbt").write_text('name := "test"\n')

        # Use current PID but make the lock 3 hours old
        key = _sanitize(str(project_dir))
        lock_file = locks_dir / f"{key}.sbt-test.lock"
        _create_lock_file(lock_file, os.getpid(), age_seconds=3 * 60 * 60)

        env = dict(os.environ, SBT_BUILD_CACHE_ROOT=str(cache_root))
        result = subprocess.run(
            ["bash", str(RUN_SBT), str(project_dir), "--", "test"],
            capture_output=True,
            text=True,
            timeout=30,
            env=env,
        )
        combined = result.stdout + result.stderr
        # Should not block — the stale lock should be auto-cleared
        assert "Stale lock file detected" in combined or "already active" not in combined
