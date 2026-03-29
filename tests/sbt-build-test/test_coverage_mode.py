"""Tests for sbt-build-test coverage and no-remote-cache wrapper behavior."""

import os
import subprocess
import textwrap
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent.parent.parent / "sbt-build-test" / "scripts"
RUN_SBT = SCRIPT_DIR / "run_sbt.sh"
RUN_SBT_CAPTURE = SCRIPT_DIR / "run_sbt_capture.sh"


def _write_fake_sbt(bin_dir: Path) -> None:
    """Create a fake sbt binary that records its invocation and exits successfully."""
    fake_sbt = bin_dir / "sbt"
    fake_sbt.write_text(
        textwrap.dedent(
            """\
            #!/usr/bin/env bash
            set -euo pipefail
            if [ -n "${FAKE_SBT_CAPTURE:-}" ]; then
              exec > >(tee "$FAKE_SBT_CAPTURE")
            fi
            echo "PWD=$PWD"
            echo "JAVA_HOME=${JAVA_HOME:-}"
            for arg in "$@"; do
              echo "ARG=$arg"
            done
            """
        )
    )
    fake_sbt.chmod(0o755)


def _create_project(tmp_path: Path) -> Path:
    """Create a minimal SBT project under a workspace root."""
    project_dir = tmp_path / "workspace" / "demo"
    project_dir.mkdir(parents=True)
    (project_dir / "build.sbt").write_text('name := "demo"\nscalaVersion := "2.13.14"\n')
    return project_dir


def _run_env(tmp_path: Path, capture_file: Path, bin_dir: Path) -> dict[str, str]:
    """Construct an environment that makes run_sbt.sh fully deterministic."""
    fake_jdk = tmp_path / "fake-jdk"
    fake_jdk.mkdir()
    return dict(
        os.environ,
        PATH=f"{bin_dir}:{os.environ['PATH']}",
        JAVA_HOME=str(fake_jdk),
        SBT_BUILD_CACHE_ROOT=str(tmp_path / ".sbt-build-cache"),
        FAKE_SBT_CAPTURE=str(capture_file),
    )


class TestNoRemoteCache:
    def test_removes_nested_scala_targets_recursively(self, tmp_path: Path) -> None:
        """--no-remote-cache should clear nested target/scala-* directories, not just one level."""
        project_dir = _create_project(tmp_path)
        root_target = project_dir / "target" / "scala-2.13" / "classes"
        nested_target = project_dir / "sdks" / "aws" / "target" / "scala-2.13" / "classes"
        root_target.mkdir(parents=True)
        nested_target.mkdir(parents=True)
        (root_target / "root.marker").write_text("root")
        (nested_target / "nested.marker").write_text("nested")

        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        _write_fake_sbt(bin_dir)
        capture_file = tmp_path / "fake-sbt.log"

        result = subprocess.run(
            ["bash", str(RUN_SBT), str(project_dir), "--no-remote-cache", "--", "compile"],
            capture_output=True,
            text=True,
            timeout=30,
            env=_run_env(tmp_path, capture_file, bin_dir),
        )

        assert result.returncode == 0
        assert not (project_dir / "target" / "scala-2.13").exists()
        assert not (project_dir / "sdks" / "aws" / "target" / "scala-2.13").exists()
        captured = capture_file.read_text()
        assert "set every Compile / maybePullRemoteCache := None" in captured
        assert "set every Test / maybePullRemoteCache := None" in captured
        assert "ARG=; set every Compile / maybePullRemoteCache := None" in captured


class TestCoverageMode:
    def test_scoped_coverage_disables_remote_cache_pull_and_forking(self, tmp_path: Path) -> None:
        """--coverage should scope clean/reporting and disable CAP remote-cache pulls."""
        project_dir = _create_project(tmp_path)
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        _write_fake_sbt(bin_dir)
        capture_file = tmp_path / "fake-sbt.log"

        result = subprocess.run(
            [
                "bash",
                str(RUN_SBT),
                str(project_dir),
                "--coverage",
                "--",
                "aws / testOnly com.example.MyTest",
            ],
            capture_output=True,
            text=True,
            timeout=30,
            env=_run_env(tmp_path, capture_file, bin_dir),
        )

        captured = capture_file.read_text()
        assert result.returncode == 0
        assert "ARG=--batch" in captured
        assert "set aws / Compile / maybePullRemoteCache := None" in captured
        assert "set aws / Test / maybePullRemoteCache := None" in captured
        assert "aws / clean" in captured
        assert "coverage" in captured
        assert "set aws / Test / fork := false" in captured
        assert "aws / testOnly com.example.MyTest" in captured
        assert "aws / coverageReport" in captured

    def test_run_sbt_capture_forwards_coverage_mode(self, tmp_path: Path) -> None:
        """run_sbt_capture.sh should pass --coverage through to run_sbt.sh."""
        project_dir = _create_project(tmp_path)
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        _write_fake_sbt(bin_dir)
        capture_file = tmp_path / "fake-sbt.log"
        log_file = tmp_path / "captured-run.log"

        result = subprocess.run(
            [
                "bash",
                str(RUN_SBT_CAPTURE),
                str(project_dir),
                "--log-file",
                str(log_file),
                "--coverage",
                "--",
                "aws / testOnly com.example.MyTest",
            ],
            capture_output=True,
            text=True,
            timeout=30,
            env=_run_env(tmp_path, capture_file, bin_dir),
        )

        assert result.returncode == 0
        captured = capture_file.read_text()
        assert log_file.is_file()
        assert "set aws / Compile / maybePullRemoteCache := None" in captured
        assert "set aws / Test / maybePullRemoteCache := None" in captured
        assert "aws / coverageReport" in captured
