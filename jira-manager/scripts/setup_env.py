#!/usr/bin/env python3
"""
Bootstrap a virtual environment for the jira-manager skill.

Creates .venv/ inside the skill directory (next to SKILL.md) so that
one venv is shared across all projects. Safe to run multiple times.

Usage:
    python3 setup_env.py
    python3 setup_env.py --venv-dir /custom/path/.venv
"""

import argparse
import subprocess
import sys
import venv
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
REQUIREMENTS = SCRIPT_DIR / "requirements.txt"
DEFAULT_VENV_DIR = SKILL_DIR / ".venv"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Set up Python environment for jira-manager"
    )
    parser.add_argument(
        "--venv-dir",
        default=str(DEFAULT_VENV_DIR),
        help=f"Virtual environment directory (default: {DEFAULT_VENV_DIR})",
    )
    return parser.parse_args()


def check_python_version():
    """Verify Python 3.10+ is available."""
    major, minor = sys.version_info[:2]
    if major < 3 or (major == 3 and minor < 10):
        print(f"ERROR: Python 3.10+ required, found {major}.{minor}")
        print("Install Python 3.10+:")
        print("  macOS:  brew install python3")
        print("  Ubuntu: sudo apt install python3.10")
        print("  Other:  https://www.python.org/downloads/")
        sys.exit(1)
    print(f"Python {major}.{minor} detected")


def get_venv_python(venv_dir: Path) -> Path:
    """Get path to Python in the virtual environment."""
    candidate = venv_dir / "bin" / "python"
    if candidate.exists():
        return candidate
    candidate = venv_dir / "Scripts" / "python.exe"  # Windows
    if candidate.exists():
        return candidate
    print(f"ERROR: Could not find Python in {venv_dir}")
    sys.exit(1)


def main():
    args = parse_args()
    venv_dir = Path(args.venv_dir).resolve()

    print("=== jira-manager environment setup ===\n")

    check_python_version()

    if venv_dir.exists():
        print(f"Virtual environment already exists at {venv_dir}")
    else:
        print(f"Creating virtual environment at {venv_dir}...")
        venv.create(str(venv_dir), with_pip=True)
        print("Virtual environment created")

    python = get_venv_python(venv_dir)

    if not REQUIREMENTS.exists():
        print(f"ERROR: requirements.txt not found at {REQUIREMENTS}")
        sys.exit(1)

    print(f"Installing dependencies from {REQUIREMENTS}...")
    subprocess.check_call(
        [str(python), "-m", "pip", "install", "--quiet", "--upgrade", "pip"],
    )
    subprocess.check_call(
        [str(python), "-m", "pip", "install", "--quiet", "-r", str(REQUIREMENTS)],
    )
    print("Dependencies installed")

    print("\n=== Setup complete ===")
    print(f"Virtual environment: {venv_dir}")
    print(f"Python:             {python}")
    print("\nUse this Python for all jira-manager scripts:")
    print(f"  {python} {SCRIPT_DIR}/create_ticket.py ...")


if __name__ == "__main__":
    main()
