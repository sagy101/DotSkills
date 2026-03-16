"""Config loading and environment resolution."""

import json
import os
import sys
from pathlib import Path
from typing import Optional


def find_config() -> Optional[Path]:
    """Search CWD upward for .eks-config.json, then ~/.eks-config.json."""
    cwd = Path.cwd()
    for d in [cwd, *cwd.parents]:
        p = d / ".eks-config.json"
        if p.is_file():
            return p
    home = Path.home() / ".eks-config.json"
    if home.is_file():
        return home
    return None


def load_config(path: Path) -> dict:
    with open(path) as f:
        return json.load(f)


def get_env_config(config: dict, env_name: str) -> dict:
    """Resolve environment config by name or alias."""
    envs = config.get("environments", {})
    if env_name in envs:
        return envs[env_name]
    # Check aliases
    for name, cfg in envs.items():
        if cfg.get("alias") == env_name:
            return cfg
    available = ", ".join(sorted(envs.keys()))
    die(f"Environment '{env_name}' not found in config. Available: {available}")
    return {}  # unreachable


def get_kubeconfig_path(config: dict, env_name: str) -> str:
    """Build absolute kubeconfig path for an environment."""
    kube_dir = os.path.expanduser(config.get("kubeconfig_dir", "~/.kube"))
    pattern = config.get("kubeconfig_pattern", "config_{env}")
    filename = pattern.replace("{env}", env_name)
    return os.path.join(kube_dir, filename)


def require_config() -> tuple[Path, dict]:
    """Find and load config, or die with helpful message."""
    path = find_config()
    if not path:
        die(
            "Config not found.\n"
            "Create ~/.eks-config.json (recommended) or .eks-config.json in project root.\n"
            "See references/CONFIG.md for format."
        )
    return path, load_config(path)


def die(msg: str):
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)
