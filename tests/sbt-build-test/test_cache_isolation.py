"""Tests for sbt-build-test cache isolation — verify all SBT subsystem caches are isolated."""

import os
import subprocess
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent.parent.parent / "sbt-build-test" / "scripts"
RUN_SBT = SCRIPT_DIR / "run_sbt.sh"
COMMON_SH = SCRIPT_DIR / "common.sh"


def _source_common_and_eval(cache_root: str, expression: str) -> str:
    """Source common.sh with a custom cache root and evaluate a bash expression."""
    result = subprocess.run(
        [
            "bash",
            "-c",
            f'export SBT_BUILD_CACHE_ROOT="{cache_root}"; source "{COMMON_SH}"; {expression}',
        ],
        capture_output=True,
        text=True,
        timeout=10,
    )
    return result.stdout.strip()


class TestCachePathHelpers:
    def test_coursier_cache_root_uses_cache_root(self, tmp_path: Path) -> None:
        """coursier_cache_root() should return $SBT_BUILD_CACHE_ROOT/coursier."""
        result = _source_common_and_eval(str(tmp_path), "coursier_cache_root")
        assert result == f"{tmp_path}/coursier"

    def test_sbt_boot_dir_uses_cache_root(self, tmp_path: Path) -> None:
        """sbt_boot_dir() should return $SBT_BUILD_CACHE_ROOT/boot."""
        result = _source_common_and_eval(str(tmp_path), "sbt_boot_dir")
        assert result == f"{tmp_path}/boot"

    def test_sbt_global_base_uses_cache_root(self, tmp_path: Path) -> None:
        """sbt_global_base() should return $SBT_BUILD_CACHE_ROOT/global."""
        result = _source_common_and_eval(str(tmp_path), "sbt_global_base")
        assert result == f"{tmp_path}/global"


class TestEnsureSbtSkillDirs:
    def test_creates_all_cache_subdirectories(self, tmp_path: Path) -> None:
        """ensure_sbt_skill_dirs() should create all required subdirectories."""
        cache_root = tmp_path / "cache"
        _source_common_and_eval(str(cache_root), "ensure_sbt_skill_dirs")
        expected_dirs = ["locks", "logs", "coursier", "boot", "global"]
        for d in expected_dirs:
            assert (cache_root / d).is_dir(), f"Missing directory: {d}"


class TestSbtCommandIsolation:
    def test_sbt_command_includes_all_isolation_flags(self, tmp_path: Path) -> None:
        """run_sbt.sh should pass -Dsbt.ivy.home, -Dsbt.coursier.home,
        -Dsbt.boot.directory, and -Dsbt.global.base to SBT."""
        cache_root = tmp_path / ".sbt-build-cache"
        cache_root.mkdir()
        (cache_root / "locks").mkdir()
        (cache_root / "logs").mkdir()
        (cache_root / "coursier").mkdir()
        (cache_root / "boot").mkdir()
        (cache_root / "global").mkdir()

        project_dir = tmp_path / "test-project"
        project_dir.mkdir()
        (project_dir / "build.sbt").write_text('name := "test"\n')

        env = dict(os.environ, SBT_BUILD_CACHE_ROOT=str(cache_root))
        # run_sbt.sh will fail because sbt is not installed in test env,
        # but we can check the error/debug output or use bash -x to trace
        result = subprocess.run(
            [
                "bash",
                "-x",
                str(RUN_SBT),
                str(project_dir),
                "--",
                "compile",
            ],
            capture_output=True,
            text=True,
            timeout=30,
            env=env,
        )
        # bash -x traces all commands to stderr
        trace = result.stderr
        assert f"-Dsbt.ivy.home={cache_root}" in trace
        assert f"-Dsbt.coursier.home={cache_root}/coursier" in trace
        assert f"-Dsbt.boot.directory={cache_root}/boot" in trace
        assert f"-Dsbt.global.base={cache_root}/global" in trace


class TestPerWorktreeIsolation:
    def test_different_cache_roots_produce_different_paths(self, tmp_path: Path) -> None:
        """Two different SBT_BUILD_CACHE_ROOT values should produce fully separate paths."""
        root_a = str(tmp_path / "wt-a")
        root_b = str(tmp_path / "wt-b")

        for func in ["coursier_cache_root", "sbt_boot_dir", "sbt_global_base"]:
            path_a = _source_common_and_eval(root_a, func)
            path_b = _source_common_and_eval(root_b, func)
            assert path_a != path_b, f"{func} returned same path for different roots"
            assert root_a in path_a
            assert root_b in path_b
