#!/usr/bin/env python3
"""Pre-flight checks for super-review skill.

Verifies that the dependency stack is in place: review-prompts skill,
sub-agent backend (codex-subagent), and Codex CLI login status.

Exits 0 if all checks pass, 1 if any fail.

Usage:
    python3 sr_preflight.py
"""

import subprocess
import sys
from pathlib import Path

_PASS = "[PASS]"
_FAIL = "[FAIL]"
_WARN = "[WARN]"

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
REPO_DIR = SKILL_DIR.parent

REVIEW_PROMPTS_DIR = REPO_DIR / "review-prompts"
CODEX_SUBAGENT_DIR = REPO_DIR / "codex-subagent"


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------


def _check_review_prompts() -> bool:
    """Check that the review-prompts skill is installed as a sibling directory."""
    skill_md = REVIEW_PROMPTS_DIR / "SKILL.md"
    build_prompt = REVIEW_PROMPTS_DIR / "scripts" / "build-prompt.py"

    if not skill_md.exists():
        print(f"{_WARN} review-prompts skill — not found at {REVIEW_PROMPTS_DIR}")
        print("  Install review-prompts as a sibling directory to super-review")
        print("  Custom inline prompts can be used as a fallback")
        return True  # warn only — custom prompts are a valid fallback

    if not build_prompt.exists():
        print(f"{_WARN} review-prompts skill — SKILL.md found but scripts/build-prompt.py missing")
        return True

    print(f"{_PASS} review-prompts skill — found at {REVIEW_PROMPTS_DIR}")
    return True


def _check_build_prompt() -> bool:
    """Test that build-prompt.py runs and can list review types."""
    build_prompt = REVIEW_PROMPTS_DIR / "scripts" / "build-prompt.py"
    if not build_prompt.exists():
        print(f"{_WARN} build-prompt.py — skipped (review-prompts not found)")
        return True

    try:
        result = subprocess.run(
            [sys.executable, str(build_prompt), "--list"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode == 0:
            types = [line.strip() for line in result.stdout.strip().splitlines() if line.strip()]
            print(f"{_PASS} build-prompt.py — {len(types)} review type(s) available")
            return True
        print(f"{_FAIL} build-prompt.py — exited with error")
        if result.stderr.strip():
            print(f"  {result.stderr.strip().splitlines()[-1]}")
        return False
    except subprocess.TimeoutExpired:
        print(f"{_WARN} build-prompt.py — timed out")
        return True
    except Exception as e:
        print(f"{_FAIL} build-prompt.py — {e}")
        return False


def _check_subagent_backend() -> bool:
    """Check if codex-subagent skill is installed as a sibling directory."""
    preflight = CODEX_SUBAGENT_DIR / "scripts" / "codex_preflight.py"

    if not CODEX_SUBAGENT_DIR.exists():
        print(f"{_WARN} Sub-agent backend — codex-subagent not found at {CODEX_SUBAGENT_DIR}")
        print("  Ensure you have a sub-agent backend (e.g., Claude Code Agent tool)")
        return True  # warn only — other backends work

    if not preflight.exists():
        print(
            f"{_WARN} Sub-agent backend — codex-subagent found but"
            " scripts/codex_preflight.py missing"
        )
        return True

    print(f"{_PASS} Sub-agent backend — codex-subagent found at {CODEX_SUBAGENT_DIR}")
    return True


def _check_codex_preflight() -> bool:
    """Run the codex-subagent preflight to check CLI, version, and login."""
    preflight = CODEX_SUBAGENT_DIR / "scripts" / "codex_preflight.py"
    if not preflight.exists():
        print(f"{_WARN} Codex preflight — skipped (codex-subagent not found)")
        return True

    try:
        result = subprocess.run(
            [sys.executable, str(preflight)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        # Relay key lines from codex preflight output
        for line in result.stdout.splitlines():
            stripped = line.strip()
            if stripped.startswith(("[PASS]", "[FAIL]", "[WARN]")):
                print(f"  {stripped}")

        if result.returncode == 0:
            print(f"{_PASS} Codex preflight — all checks passed")
            return True
        print(f"{_FAIL} Codex preflight — some checks failed (see above)")
        return False
    except subprocess.TimeoutExpired:
        print(f"{_WARN} Codex preflight — timed out")
        return True
    except Exception as e:
        print(f"{_FAIL} Codex preflight — {e}")
        return False


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    print("Super-Review — Pre-flight Checks")
    print("=" * 34)
    print()

    results = []

    # 1. review-prompts skill
    results.append(_check_review_prompts())

    # 2. build-prompt.py test
    results.append(_check_build_prompt())

    # 3. Sub-agent backend
    results.append(_check_subagent_backend())

    # 4. Codex preflight (CLI, version, login)
    results.append(_check_codex_preflight())

    # Summary
    passed = sum(results)
    total = len(results)
    print()
    print("=" * 34)
    if all(results):
        print(f"All {total} checks passed. Ready to use.")
        sys.exit(0)
    else:
        failed = total - passed
        print(f"{passed}/{total} passed, {failed} failed. Fix the issues above.")
        sys.exit(1)


if __name__ == "__main__":
    main()
