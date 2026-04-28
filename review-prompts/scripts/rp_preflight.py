#!/usr/bin/env python3
"""Pre-flight checks for review-prompts skill.

Verifies Python version, build-prompt.py script, prompt files, and shared
template. Run this before first use. Exits 0 if all checks pass, 1 if any fail.

Usage:
    python3 rp_preflight.py
"""

import subprocess
import sys
from pathlib import Path

_PASS = "[PASS]"
_FAIL = "[FAIL]"
_WARN = "[WARN]"

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
PROMPTS_DIR = SKILL_DIR / "prompts"


def _check_python() -> bool:
    """Check Python version >= 3.10."""
    major, minor = sys.version_info[:2]
    if major >= 3 and minor >= 10:
        print(f"{_PASS} Python {major}.{minor}")
        return True
    print(f"{_FAIL} Python {major}.{minor} — requires 3.10+")
    return False


def _check_build_script() -> bool:
    """Check that build-prompt.py exists."""
    script = SCRIPT_DIR / "build-prompt.py"
    if script.exists():
        print(f"{_PASS} build-prompt.py — found")
        return True
    print(f"{_FAIL} build-prompt.py — not found at {script}")
    return False


def _check_shared_template() -> bool:
    """Check that prompts/_shared.md exists."""
    shared = PROMPTS_DIR / "_shared.md"
    if shared.exists():
        print(f"{_PASS} Shared template — prompts/_shared.md found")
        return True
    print(f"{_FAIL} Shared template — prompts/_shared.md not found")
    return False


def _check_prompt_files() -> bool:
    """Check that at least one review prompt file exists."""
    if not PROMPTS_DIR.is_dir():
        print(f"{_FAIL} Prompt files — prompts/ directory not found")
        return False

    prompts = [p for p in PROMPTS_DIR.glob("*.md") if p.name != "_shared.md"]
    if prompts:
        print(f"{_PASS} Prompt files — {len(prompts)} review type(s) found")
        return True
    print(f"{_FAIL} Prompt files — no .md prompt files found in prompts/")
    return False


def _check_build_runs() -> bool:
    """Test that build-prompt.py --list runs successfully."""
    script = SCRIPT_DIR / "build-prompt.py"
    if not script.exists():
        print(f"{_WARN} build-prompt.py test — skipped (script not found)")
        return True

    try:
        result = subprocess.run(
            [sys.executable, str(script), "--list"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode == 0:
            types = [line.strip() for line in result.stdout.strip().splitlines() if line.strip()]
            print(f"{_PASS} build-prompt.py test — lists {len(types)} type(s)")
            return True
        print(f"{_FAIL} build-prompt.py test — exited with error")
        if result.stderr.strip():
            print(f"  {result.stderr.strip().splitlines()[-1]}")
        return False
    except subprocess.TimeoutExpired:
        print(f"{_WARN} build-prompt.py test — timed out")
        return True
    except Exception as e:
        print(f"{_FAIL} build-prompt.py test — {e}")
        return False


def main() -> None:
    print("Review Prompts — Pre-flight Checks")
    print("=" * 36)
    print()

    results = []

    # 1. Python version
    results.append(_check_python())

    # 2. build-prompt.py exists
    results.append(_check_build_script())

    # 3. Shared template
    results.append(_check_shared_template())

    # 4. Prompt files
    results.append(_check_prompt_files())

    # 5. build-prompt.py runs
    results.append(_check_build_runs())

    # Summary
    passed = sum(results)
    total = len(results)
    print()
    print("=" * 36)
    if all(results):
        print(f"All {total} checks passed. Ready to use.")
        sys.exit(0)
    else:
        failed = total - passed
        print(f"{passed}/{total} passed, {failed} failed. Fix the issues above.")
        sys.exit(1)


if __name__ == "__main__":
    main()
