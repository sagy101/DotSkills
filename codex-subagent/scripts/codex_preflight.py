#!/usr/bin/env python3
"""Pre-flight checks for codex-subagent skill.

Verifies Python version, Codex CLI installation, version, authentication,
git repo presence, wrapper script existence, and model strictness config.
Run this before the first delegation in a session. Exits 0 if all checks pass, 1 if any fail.
"""

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

_PASS = "[PASS]"
_FAIL = "[FAIL]"
_WARN = "[WARN]"

_MIN_CODEX_VERSION = (0, 106, 0)
_MIN_CODEX_VERSION_STR = "0.106.0"


def _check_python() -> bool:
    """Check Python version >= 3.10."""
    major, minor = sys.version_info[:2]
    if major >= 3 and minor >= 10:
        print(f"{_PASS} Python {major}.{minor}")
        return True
    print(f"{_FAIL} Python {major}.{minor} — requires 3.10+")
    print("  Hint: install Python 3.10+ from https://python.org or via your package manager")
    return False


def _check_codex_installed() -> bool:
    """Check codex CLI is installed and on PATH."""
    result = subprocess.run(
        ["which", "codex"],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        path = result.stdout.strip()
        print(f"{_PASS} Codex CLI — found at {path}")
        return True
    print(f"{_FAIL} Codex CLI — not found on PATH")
    print("  Hint: install with: npm i -g @openai/codex")
    return False


def _parse_semver(version_str: str) -> tuple[int, int, int] | None:
    """Parse a semver string like '0.108.2' into a tuple. Returns None if unparseable."""
    match = re.search(r"(\d+)\.(\d+)\.(\d+)", version_str)
    if match:
        return (int(match.group(1)), int(match.group(2)), int(match.group(3)))
    return None


def _check_codex_version() -> bool:
    """Check codex CLI version meets minimum requirement."""
    try:
        result = subprocess.run(
            ["codex", "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except FileNotFoundError:
        print(f"{_FAIL} Codex version — codex not found (install with: npm i -g @openai/codex)")
        return False
    except subprocess.TimeoutExpired:
        print(f"{_FAIL} Codex version — timed out running 'codex --version'")
        return False

    output = (result.stdout + result.stderr).strip()
    version = _parse_semver(output)
    if version is None:
        print(f"{_FAIL} Codex version — could not parse version from: {output!r}")
        return False

    version_str = ".".join(str(x) for x in version)
    if version >= _MIN_CODEX_VERSION:
        print(f"{_PASS} Codex version — {version_str} (minimum {_MIN_CODEX_VERSION_STR})")
        return True

    print(f"{_FAIL} Codex version — {version_str} found, but {_MIN_CODEX_VERSION_STR}+ is needed")
    print("  Hint: upgrade with: npm i -g @openai/codex")
    return False


def _check_auth(skip: bool) -> bool:
    """Check codex authentication status."""
    if skip:
        print(f"{_WARN} Auth — skipped (--skip-auth)")
        return True

    try:
        result = subprocess.run(
            ["codex", "login", "status"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except FileNotFoundError:
        print(f"{_FAIL} Auth — codex not found")
        return False
    except subprocess.TimeoutExpired:
        print(f"{_FAIL} Auth — timed out running 'codex login status'")
        print("  Hint: run 'codex login' to authenticate, or use --skip-auth in CI environments")
        return False

    if result.returncode == 0:
        print(f"{_PASS} Auth — logged in")
        return True

    print(f"{_FAIL} Auth — not authenticated")
    print("  Hint: run 'codex login' to authenticate")
    return False


def _check_git_repo(skip: bool) -> bool:
    """Check if we are inside a git repository. Warns but does not fail if missing."""
    if skip:
        print(f"{_WARN} Git repo — skipped (--skip-git-repo-check)")
        return True

    try:
        result = subprocess.run(
            ["git", "rev-parse", "--git-dir"],
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        print(f"{_WARN} Git repo — git not found; install git or use --skip-git-repo-check")
        return True  # warn, not fail

    if result.returncode == 0:
        print(f"{_PASS} Git repo — detected")
        return True

    print(f"{_WARN} Git repo — not inside a git repository")
    print("  Hint: run from inside a git repo, or pass --skip-git-repo-check to the wrapper")
    return True  # warn, not fail


def _check_wrapper_script() -> bool:
    """Check that run_codex.py is co-located in the same scripts/ directory."""
    wrapper = Path(__file__).resolve().parent / "run_codex.py"
    if wrapper.exists():
        print(f"{_PASS} Wrapper script — found at {wrapper}")
        return True
    print(f"{_FAIL} Wrapper script — run_codex.py not found at {wrapper}")
    print(
        "  Hint: the skill may not be fully installed; check the codex-subagent/scripts/ directory"
    )
    return False


def _check_model_strictness() -> bool:
    """Check optional CODEX_SUBAGENT_MODEL_STRICTNESS env var. Warns if not set."""
    valid_values = {"conservative", "balanced", "aggressive"}
    value = os.environ.get("CODEX_SUBAGENT_MODEL_STRICTNESS", "").strip()

    if not value:
        print(
            f"{_WARN} Model strictness — CODEX_SUBAGENT_MODEL_STRICTNESS not set, using default: balanced"
        )
        print(
            "  Hint: export CODEX_SUBAGENT_MODEL_STRICTNESS=balanced  # or conservative / aggressive"
        )
        return True  # warn, not fail

    if value in valid_values:
        print(f"{_PASS} Model strictness — {value}")
        return True

    print(
        f"{_WARN} Model strictness — unrecognised value '{value}' (valid: conservative, balanced, aggressive)"
    )
    return True  # warn, not fail


def main() -> None:
    parser = argparse.ArgumentParser(description="Pre-flight checks for codex-subagent")
    parser.add_argument(
        "--skip-git-repo-check",
        action="store_true",
        help="Skip the git repository check (mirrors wrapper flag)",
    )
    parser.add_argument(
        "--skip-auth",
        action="store_true",
        help="Skip the 'codex login status' check (useful in CI / no-TTY environments)",
    )
    args = parser.parse_args()

    print("Codex Sub-Agent — Pre-flight Checks")
    print("=" * 40)
    print()

    results: list[bool] = []

    # 1. Python version
    results.append(_check_python())

    # 2. Codex CLI installed
    codex_found = _check_codex_installed()
    results.append(codex_found)

    # 3. Codex version (only meaningful if codex is installed)
    if codex_found:
        results.append(_check_codex_version())
    else:
        results.append(False)

    # 4. Authentication
    results.append(_check_auth(skip=args.skip_auth))

    # 5. Git repo (warn only)
    _check_git_repo(skip=args.skip_git_repo_check)

    # 6. Wrapper script
    results.append(_check_wrapper_script())

    # 7. Model strictness (warn only)
    _check_model_strictness()

    # Summary
    passed = sum(results)
    total = len(results)
    print()
    print("=" * 40)
    if all(results):
        print(f"All {total} checks passed. Ready to use.")
        sys.exit(0)
    else:
        failed = total - passed
        print(f"{passed}/{total} passed, {failed} failed. Fix the issues above.")
        sys.exit(1)


if __name__ == "__main__":
    main()
