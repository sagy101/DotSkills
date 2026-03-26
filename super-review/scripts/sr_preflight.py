#!/usr/bin/env python3
"""Pre-flight checks for super-review skill.

Verifies that the dependency stack is in place: review-prompts skill and
sub-agent capability. Detects the running agent and checks accordingly:
- Windsurf/Cascade: no built-in sub-agents, so codex-subagent skill + CLI required
- Claude Code, Codex CLI, Cursor, Antigravity: have built-in sub-agents

Exits 0 if all checks pass, 1 if any fail.

Usage:
    python3 sr_preflight.py
"""

import os
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


def _is_cascade() -> bool:
    """Detect if running inside Windsurf Cascade."""
    return os.environ.get("WINDSURF_CASCADE_TERMINAL") == "1"


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


def _check_subagent_capability() -> bool:
    """Check sub-agent capability based on the detected agent.

    - Windsurf/Cascade: no built-in sub-agents → require codex-subagent skill + CLI
    - All other agents (Claude Code, Codex, Cursor, Antigravity): have built-in sub-agents
    """
    if not _is_cascade():
        print(f"{_PASS} Sub-agent capability — agent has built-in sub-agents")
        return True

    # Running in Windsurf Cascade — needs codex-subagent skill
    print("  Detected: Windsurf Cascade (no built-in sub-agents)")
    preflight = CODEX_SUBAGENT_DIR / "scripts" / "codex_preflight.py"

    if not CODEX_SUBAGENT_DIR.exists() or not preflight.exists():
        print(f"{_FAIL} Sub-agent capability — codex-subagent skill not found")
        print("  Windsurf Cascade requires the codex-subagent skill for parallel reviews")
        print(f"  Expected at: {CODEX_SUBAGENT_DIR}")
        return False

    # Run codex preflight to check CLI + version + login
    try:
        result = subprocess.run(
            [sys.executable, str(preflight)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        for line in result.stdout.splitlines():
            stripped = line.strip()
            if stripped.startswith(("[PASS]", "[FAIL]", "[WARN]")):
                print(f"  {stripped}")

        if result.returncode == 0:
            print(f"{_PASS} Sub-agent capability — codex-subagent ready")
            return True
        print(f"{_FAIL} Sub-agent capability — codex preflight failed (see above)")
        return False
    except subprocess.TimeoutExpired:
        print(f"{_WARN} Sub-agent capability — codex preflight timed out")
        return True
    except Exception as e:
        print(f"{_FAIL} Sub-agent capability — {e}")
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

    # 3. Sub-agent capability (agent-aware)
    results.append(_check_subagent_capability())

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
