#!/usr/bin/env python3
"""
Codebase Analyzer — Pre-flight Checks

Run before first operation in a conversation. Validates the environment,
dependencies, and optional tools in a single pass.

Usage:
    python3 analyzer_preflight.py
    python3 analyzer_preflight.py --path /repo
"""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
VENV_DIR = SKILL_DIR / ".codebase-analyzer-venv"
SETUP_SCRIPT = SCRIPT_DIR / "analyzer_setup_env.py"

CORE_IMPORTS = ["yaml", "rich"]
WEB_IMPORTS = ["streamlit", "pandas"]
ALL_IMPORTS = CORE_IMPORTS + WEB_IMPORTS


def check(label: str, ok: bool, detail: str = "") -> bool:
    """Print a check result and return whether it passed."""
    status = "OK" if ok else "FAIL"
    msg = f"  [{status}] {label}"
    if detail:
        msg += f" — {detail}"
    print(msg)
    return ok


def check_python_version() -> bool:
    """Check 1: Python 3.10+ is available."""
    v = sys.version_info
    return check("Python 3.10+", v >= (3, 10), f"{v.major}.{v.minor}.{v.micro}")


def check_venv_exists() -> bool:
    """Check 2: Virtual environment exists."""
    venv_python = VENV_DIR / "bin" / "python"
    if not venv_python.exists():
        # Try Windows path
        venv_python = VENV_DIR / "Scripts" / "python.exe"
    if venv_python.exists():
        return check("Virtual environment", True, str(VENV_DIR))
    return check(
        "Virtual environment",
        False,
        f"Not found at {VENV_DIR}\n           Fix: python3 {SETUP_SCRIPT}",
    )


def _get_venv_python() -> Path | None:
    """Resolve the venv Python path."""
    for candidate in [VENV_DIR / "bin" / "python", VENV_DIR / "Scripts" / "python.exe"]:
        if candidate.exists():
            return candidate
    return None


def check_core_deps() -> bool:
    """Check 3: Core dependencies (PyYAML, Rich) are importable."""
    venv_python = _get_venv_python()
    if not venv_python:
        return check("Core dependencies (yaml, rich)", False, "Venv not found")

    result = subprocess.run(
        [str(venv_python), "-c", f"import {', '.join(CORE_IMPORTS)}; print('OK')"],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        return check("Core dependencies (yaml, rich)", True, "All importable")
    return check(
        "Core dependencies (yaml, rich)",
        False,
        f"Missing packages\n           Fix: python3 {SETUP_SCRIPT}",
    )


def check_web_deps() -> bool:
    """Check 4: Web dashboard dependencies (streamlit, pandas) are importable."""
    venv_python = _get_venv_python()
    if not venv_python:
        return check("Web dependencies (streamlit, pandas)", False, "Venv not found")

    result = subprocess.run(
        [str(venv_python), "-c", f"import {', '.join(WEB_IMPORTS)}; print('OK')"],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        return check("Web dependencies (streamlit, pandas)", True, "All importable")
    return check(
        "Web dependencies (streamlit, pandas)",
        False,
        f"Missing packages — --output web will not work\n           Fix: python3 {SETUP_SCRIPT}",
    )


def check_git() -> bool:
    """Check 5: Git availability (optional)."""
    git = shutil.which("git")
    if git:
        try:
            result = subprocess.run(["git", "--version"], capture_output=True, text=True, timeout=5)
            version = result.stdout.strip() if result.returncode == 0 else "unknown"
            return check("git (optional)", True, version)
        except subprocess.TimeoutExpired:
            return check("git (optional)", True, "Found but version check timed out")
    return check(
        "git (optional)",
        True,
        "Not installed — churn metrics will be skipped, directory walking used instead",
    )


def check_scripts() -> bool:
    """Check 6: All expected scripts exist."""
    expected = [
        "analyze.py",
        "analyzer_setup_env.py",
        "analyzer_preflight.py",
        "report_terminal.py",
        "report_json.py",
        "report_markdown.py",
        "report_web.py",
    ]
    missing = [s for s in expected if not (SCRIPT_DIR / s).exists()]
    if missing:
        return check("Skill scripts", False, f"Missing: {', '.join(missing)}")
    return check("Skill scripts", True, f"All {len(expected)} scripts present")


def check_target_path(path: str) -> bool:
    """Check 7: Target analysis path exists and is a directory."""
    p = Path(path).resolve()
    if not p.exists():
        return check("Target path", False, f"Does not exist: {p}")
    if not p.is_dir():
        return check("Target path", False, f"Not a directory: {p}")
    return check("Target path", True, str(p))


def check_config(path: str) -> bool:
    """Check 8: Config file in target repo (optional)."""
    config_path = Path(path).resolve() / ".codebase-analysis.yaml"
    if config_path.exists():
        return check("Config file", True, str(config_path))
    return check(
        "Config file (optional)",
        True,
        "Not found — built-in defaults will be used",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Pre-flight checks for codebase-analyzer.")
    parser.add_argument(
        "--path",
        default=None,
        help="Target repository path to also validate (optional)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    print("Codebase Analyzer — Pre-flight Checks\n")
    all_ok = True

    # Required checks
    all_ok &= check_python_version()
    all_ok &= check_venv_exists()
    all_ok &= check_core_deps()
    all_ok &= check_web_deps()

    # Optional checks
    check_git()
    all_ok &= check_scripts()

    # Path-specific checks (only if --path provided)
    if args.path:
        print()
        all_ok &= check_target_path(args.path)
        check_config(args.path)

    print(f"\n{'All checks passed.' if all_ok else 'Some checks failed — see above.'}")
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
