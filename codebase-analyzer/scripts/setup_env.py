#!/usr/bin/env python3
"""
Codebase Analyzer — Environment Setup

Creates a virtual environment and installs all required dependencies.
Safe to run multiple times (idempotent).

Usage:
    python3 setup_env.py
    python3 setup_env.py --venv-dir .codebase-analyzer-venv
"""

import argparse
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REQUIREMENTS = SCRIPT_DIR / "requirements.txt"
DEFAULT_VENV_DIR = SCRIPT_DIR.parent / ".codebase-analyzer-venv"
VERIFY_IMPORTS = "import yaml, rich; print('OK')"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Set up Python environment for codebase-analyzer"
    )
    parser.add_argument(
        "--venv-dir",
        default=DEFAULT_VENV_DIR,
        help=f"Virtual environment directory (default: {DEFAULT_VENV_DIR})",
    )
    return parser.parse_args()


def check_python_version() -> None:
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


def create_venv(venv_dir: Path) -> None:
    """Create virtual environment if it doesn't exist."""
    if venv_dir.exists():
        print(f"Virtual environment already exists at {venv_dir}")
        return
    print(f"Creating virtual environment at {venv_dir}...")
    subprocess.check_call([sys.executable, "-m", "venv", str(venv_dir)])
    print("Virtual environment created")


def get_venv_python(venv_dir: Path) -> Path:
    """Get path to Python in the virtual environment."""
    for candidate in [venv_dir / "bin" / "python", venv_dir / "Scripts" / "python.exe"]:
        if candidate.exists():
            return candidate
    print(f"ERROR: Could not find Python in {venv_dir}")
    sys.exit(1)


def install_dependencies(venv_python: Path) -> None:
    """Install requirements into the virtual environment."""
    if not REQUIREMENTS.exists():
        print(f"ERROR: requirements.txt not found at {REQUIREMENTS}")
        sys.exit(1)

    print(f"Installing dependencies from {REQUIREMENTS}...")
    subprocess.check_call(
        [str(venv_python), "-m", "pip", "install", "--quiet", "--upgrade", "pip"],
    )
    subprocess.check_call(
        [str(venv_python), "-m", "pip", "install", "--quiet", "-r", str(REQUIREMENTS)],
    )
    print("Dependencies installed")


def verify_installation(venv_python: Path) -> None:
    """Verify that all required packages can be imported."""
    result = subprocess.run(
        [str(venv_python), "-c", VERIFY_IMPORTS],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print("ERROR: Verification failed — packages not importable")
        print(result.stderr)
        sys.exit(1)
    print("Verification passed: all packages importable")


def main() -> None:
    args = parse_args()
    venv_dir = Path(args.venv_dir).resolve()

    print("=== codebase-analyzer environment setup ===\n")

    check_python_version()
    create_venv(venv_dir)

    venv_python = get_venv_python(venv_dir)
    install_dependencies(venv_python)
    verify_installation(venv_python)

    print("\n=== Setup complete ===")
    print(f"Virtual environment: {venv_dir}")
    print(f"Python:             {venv_python}")
    print("\nUse this Python for all codebase-analyzer scripts:")
    print(f"  {venv_python} <skill_dir>/scripts/analyze.py --path . --output terminal")


if __name__ == "__main__":
    main()
