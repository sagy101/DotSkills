#!/usr/bin/env python3
"""
Bootstrap a virtual environment for the jira-manager skill.

Creates .jira-venv/ in the project root (the directory containing .jira.json)
and installs dependencies from requirements.txt.
"""

import os
import subprocess
import sys
import venv
from pathlib import Path


def find_project_root() -> Path:
    """Walk up from cwd looking for .jira.json; fall back to cwd."""
    current = Path.cwd()
    while current != current.parent:
        if (current / ".jira.json").exists():
            return current
        current = current.parent
    return Path.cwd()


def main():
    project_root = find_project_root()
    venv_dir = project_root / ".jira-venv"
    skill_dir = Path(__file__).resolve().parent
    requirements = skill_dir / "requirements.txt"

    if venv_dir.exists():
        print(f"Virtual environment already exists at {venv_dir}")
        python = venv_dir / "bin" / "python"
        if not python.exists():
            python = venv_dir / "Scripts" / "python.exe"  # Windows
    else:
        print(f"Creating virtual environment at {venv_dir} ...")
        venv.create(str(venv_dir), with_pip=True)
        python = venv_dir / "bin" / "python"
        if not python.exists():
            python = venv_dir / "Scripts" / "python.exe"

    if not python.exists():
        print(f"ERROR: Could not locate python binary in {venv_dir}")
        sys.exit(1)

    print("Installing dependencies ...")
    subprocess.check_call(
        [str(python), "-m", "pip", "install", "--quiet", "-r", str(requirements)],
    )

    print(f"Setup complete. Use: {python}")
    print(f"Example: {python} <skill_dir>/scripts/create_ticket.py --config .jira.json ...")


if __name__ == "__main__":
    main()
