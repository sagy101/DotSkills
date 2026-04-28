#!/usr/bin/env python3
"""Pre-flight checks for skill-creator skill.

Verifies Python version, PyYAML dependency, and expected scripts.
Run this before first use. Exits 0 if all checks pass, 1 if any fail.

Usage:
    python3 sc_preflight.py
"""

import subprocess
import sys
from pathlib import Path

_PASS = "[PASS]"
_FAIL = "[FAIL]"
_WARN = "[WARN]"

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent


def _check_python() -> bool:
    """Check Python version >= 3.10."""
    major, minor = sys.version_info[:2]
    if major >= 3 and minor >= 10:
        print(f"{_PASS} Python {major}.{minor}")
        return True
    print(f"{_FAIL} Python {major}.{minor} — requires 3.10+")
    return False


def _check_pyyaml() -> bool:
    """Check that PyYAML is importable."""
    try:
        result = subprocess.run(
            [sys.executable, "-c", "import yaml; print(yaml.__version__)"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            version = result.stdout.strip()
            print(f"{_PASS} PyYAML — {version}")
            return True
        print(f"{_FAIL} PyYAML — not installed")
        print("  Hint: pip install PyYAML>=6.0")
        return False
    except subprocess.TimeoutExpired:
        print(f"{_WARN} PyYAML — import check timed out")
        return True
    except Exception as e:
        print(f"{_FAIL} PyYAML — {e}")
        return False


def _check_scripts() -> bool:
    """Check that expected scripts exist."""
    expected = [
        "init_skill.py",
        "quick_validate.py",
        "generate_openai_yaml.py",
    ]
    missing = [s for s in expected if not (SCRIPT_DIR / s).exists()]
    if missing:
        print(f"{_FAIL} Skill scripts — missing: {', '.join(missing)}")
        return False
    print(f"{_PASS} Skill scripts — all {len(expected)} scripts present")
    return True


def _check_references() -> bool:
    """Check that key reference docs exist."""
    refs_dir = SKILL_DIR / "references"
    expected = ["SKILL_SPEC.md", "PROMPT_ENGINEERING.md", "SKILL_TEMPLATE.md"]
    if not refs_dir.is_dir():
        print(f"{_FAIL} References — references/ directory not found")
        return False

    missing = [r for r in expected if not (refs_dir / r).exists()]
    if missing:
        print(f"{_FAIL} References — missing: {', '.join(missing)}")
        return False
    print(f"{_PASS} References — all {len(expected)} reference docs present")
    return True


def main() -> None:
    print("Skill Creator — Pre-flight Checks")
    print("=" * 36)
    print()

    results = []

    # 1. Python version
    results.append(_check_python())

    # 2. PyYAML dependency
    results.append(_check_pyyaml())

    # 3. Scripts
    results.append(_check_scripts())

    # 4. Reference docs
    results.append(_check_references())

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
