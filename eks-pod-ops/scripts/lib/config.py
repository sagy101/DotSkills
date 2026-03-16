"""Config loading and environment resolution."""

import json
import os
import sys
from pathlib import Path
from typing import Any


class ConfigError(SystemExit):
    """Raised when config is missing or invalid."""

    def __init__(self, msg: str) -> None:
        print(f"ERROR: {msg}", file=sys.stderr)
        super().__init__(1)


def find_config() -> Path | None:
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


def load_config(path: Path) -> dict[str, Any]:
    with open(path) as f:
        return dict(json.load(f))


def get_env_config(config: dict[str, Any], env_name: str) -> dict[str, Any]:
    """Resolve environment config by name or alias."""
    envs: dict[str, Any] = config.get("environments", {})
    if env_name in envs:
        return dict(envs[env_name])
    for cfg in envs.values():
        if cfg.get("alias") == env_name:
            return dict(cfg)
    available = ", ".join(sorted(envs.keys()))
    raise ConfigError(f"Environment '{env_name}' not found in config. Available: {available}")


def get_kubeconfig_path(config: dict[str, Any], env_name: str) -> str:
    """Build absolute kubeconfig path for an environment."""
    kube_dir = os.path.expanduser(config.get("kubeconfig_dir", "~/.kube"))
    pattern: str = config.get("kubeconfig_pattern", "config_{env}")
    filename = pattern.replace("{env}", env_name)
    return str(os.path.join(kube_dir, filename))


def require_config() -> tuple[Path, dict[str, Any]]:
    """Find and load config, or die with helpful message."""
    path = find_config()
    if not path:
        raise ConfigError(
            "Config not found.\n"
            "Create ~/.eks-config.json (recommended) or .eks-config.json in project root.\n"
            "See references/CONFIG.md for format."
        )
    return path, load_config(path)


def die(msg: str) -> None:
    """Print error and exit. Kept for compatibility."""
    raise ConfigError(msg)
