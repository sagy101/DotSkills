#!/usr/bin/env python3
"""Opt-in live smoke test for Bitbucket pipeline support.

This script is intentionally gated so it does not run accidentally in CI.
Set BITBUCKET_PIPELINES_E2E=1 to enable it, along with normal Bitbucket auth.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_SCRIPT_DIR = _REPO_ROOT / "bitbucket-manager" / "scripts"
_PYTHON = sys.executable


def _run(script: str, *args: str) -> subprocess.CompletedProcess:
    cmd = [_PYTHON, str(_SCRIPT_DIR / script), *args]
    return subprocess.run(cmd, capture_output=True, text=True)


def main() -> None:
    if os.environ.get("BITBUCKET_PIPELINES_E2E") != "1":
        print("Skipping: set BITBUCKET_PIPELINES_E2E=1 to run this live smoke test.")
        return

    print("Bitbucket Pipelines E2E Smoke Test")
    print("=" * 40)
    print()

    # This is a smoke test, not a destructive integration flow.
    # It verifies the new pipeline commands can be invoked against a live repo.
    r = _run("bb_preflight.py", "--skip-connectivity")
    if r.returncode != 0:
        print(r.stdout)
        print(r.stderr, file=sys.stderr)
        raise SystemExit(r.returncode)

    r = _run("pipeline_list.py", "--format", "json")
    print("[PASS] pipeline_list" if r.returncode == 0 else "[FAIL] pipeline_list")
    if r.returncode != 0:
        print(r.stderr, file=sys.stderr)
        raise SystemExit(r.returncode)

    # If the repo has at least one pipeline, we also try the step inspection path.
    # We keep this intentionally lightweight because pipeline UUIDs are ephemeral.
    try:
        import json

        pipelines = json.loads(r.stdout or "[]")
    except Exception:
        pipelines = []

    if pipelines:
        pipeline_uuid = pipelines[0].get("uuid")
        if pipeline_uuid:
            r = _run("pipeline_get.py", "--pipeline", pipeline_uuid, "--format", "json")
            print("[PASS] pipeline_get" if r.returncode == 0 else "[FAIL] pipeline_get")
            if r.returncode != 0:
                print(r.stderr, file=sys.stderr)
                raise SystemExit(r.returncode)

            r = _run("pipeline_steps.py", "--pipeline", pipeline_uuid, "--format", "json")
            print("[PASS] pipeline_steps" if r.returncode == 0 else "[FAIL] pipeline_steps")
            if r.returncode != 0:
                print(r.stderr, file=sys.stderr)
                raise SystemExit(r.returncode)

            steps = json.loads(r.stdout or "[]")
            if steps:
                step_uuid = steps[0].get("uuid")
                if step_uuid:
                    r = _run(
                        "pipeline_step_get.py",
                        "--pipeline",
                        pipeline_uuid,
                        "--step",
                        step_uuid,
                        "--format",
                        "json",
                    )
                    print(
                        "[PASS] pipeline_step_get"
                        if r.returncode == 0
                        else "[FAIL] pipeline_step_get"
                    )
                    if r.returncode != 0:
                        print(r.stderr, file=sys.stderr)
                        raise SystemExit(r.returncode)

    print()
    print("Smoke test complete.")


def test_pipelines_e2e() -> None:
    if os.environ.get("BITBUCKET_PIPELINES_E2E") != "1":
        pytest.skip("set BITBUCKET_PIPELINES_E2E=1 to run this live smoke test")
    main()


if __name__ == "__main__":
    main()
