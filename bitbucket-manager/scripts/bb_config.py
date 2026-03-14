"""
Shared configuration loader for bitbucket-manager skill scripts.

Loads .bitbucket.json and resolves credentials from env vars or shell environment.
Supports global config (~/.bitbucket.json) merged with per-project config.
Mirrors the jira-manager config_loader.py pattern.
"""

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

_ENV_VAR_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

CONFIG_FILENAME = ".bitbucket.json"


@dataclass
class BitbucketConfig:
    workspace: str
    email_env: str = "BITBUCKET_EMAIL"
    token_env: str = "BITBUCKET_TOKEN"
    env_file: Optional[str] = None
    default_reviewers: list = field(default_factory=list)
    default_destination: str = "master"

    # Resolved at runtime
    project_root: Path = field(default_factory=lambda: Path.cwd())

    def auto_detect_repo(self) -> Optional[str]:
        """Detect repo_slug from git remote origin URL.

        Parses SSH and HTTPS Bitbucket remote URLs:
          git@bitbucket.org:workspace/repo.git  -> repo
          https://bitbucket.org/workspace/repo.git -> repo
          https://user@bitbucket.org/workspace/repo.git -> repo
        """
        try:
            result = subprocess.run(
                ["git", "remote", "get-url", "origin"],
                capture_output=True, text=True, cwd=str(self.project_root),
            )
            if result.returncode != 0:
                return None
            url = result.stdout.strip()
            return _parse_repo_slug(url)
        except FileNotFoundError:
            return None


def _parse_repo_slug(remote_url: str) -> Optional[str]:
    """Extract repo_slug from a Bitbucket remote URL."""
    # SSH: git@bitbucket.org:workspace/repo.git
    if remote_url.startswith("git@"):
        parts = remote_url.split(":")[-1]
        parts = parts.rstrip(".git")
        segments = parts.split("/")
        if len(segments) >= 2:
            return segments[-1]
    # HTTPS: https://bitbucket.org/workspace/repo.git
    elif "bitbucket.org" in remote_url:
        parts = remote_url.rstrip("/").rstrip(".git").split("/")
        if len(parts) >= 2:
            return parts[-1]
    return None


def _parse_workspace_and_repo(remote_url: str) -> Tuple[Optional[str], Optional[str]]:
    """Extract workspace and repo_slug from a Bitbucket remote URL."""
    # SSH: git@bitbucket.org:workspace/repo.git
    if remote_url.startswith("git@"):
        parts = remote_url.split(":")[-1]
        parts = parts.rstrip(".git")
        segments = parts.split("/")
        if len(segments) >= 2:
            return segments[-2], segments[-1]
    # HTTPS: https://bitbucket.org/workspace/repo.git
    elif "bitbucket.org" in remote_url:
        parts = remote_url.rstrip("/").rstrip(".git").split("/")
        if len(parts) >= 2:
            return parts[-2], parts[-1]
    return None, None


def add_common_args(parser: argparse.ArgumentParser) -> None:
    """Add standard --config, --repo, and --workspace arguments."""
    parser.add_argument(
        "--config",
        help="Path to .bitbucket.json (omit to auto-discover)",
    )
    parser.add_argument(
        "--repo",
        help="Repo slug (omit to auto-detect from git remote)",
    )
    parser.add_argument(
        "--workspace",
        help="Bitbucket workspace (omit to use config value)",
    )


def _normalize_argv() -> None:
    """Normalize sys.argv: convert single-dash long flags to double-dash.

    LLM agents frequently write ``-format`` instead of ``--format``.
    """
    for i, arg in enumerate(sys.argv[1:], start=1):
        if (
            arg.startswith("-")
            and not arg.startswith("--")
            and len(arg) > 2
            and not arg.lstrip("-").isdigit()
        ):
            sys.argv[i] = "-" + arg


_normalize_argv()


def detect_shell() -> Tuple[str, str]:
    """Detect user's shell and rc file path."""
    if sys.platform == "win32":
        comspec = os.environ.get("COMSPEC", "")
        if "pwsh" in comspec.lower() or "powershell" in comspec.lower():
            return "pwsh", "$PROFILE"
        if os.environ.get("PSModulePath"):
            return "pwsh", "$PROFILE"
        return "cmd", "%USERPROFILE%\\.env"

    shell = os.environ.get("SHELL", "")
    shell_name = Path(shell).name if shell else "sh"
    rc_files = {
        "zsh": "~/.zshrc",
        "bash": "~/.bash_profile" if sys.platform == "darwin" else "~/.bashrc",
        "fish": "~/.config/fish/config.fish",
    }
    return shell_name, rc_files.get(shell_name, "~/.profile")


def _credential_hint(var_name: str) -> str:
    """Return a shell-specific hint for setting a credential env var."""
    if not _ENV_VAR_RE.match(var_name):
        return f"  Set environment variable '{var_name}' in your shell profile."
    shell_name, rc_file = detect_shell()
    if shell_name == "fish":
        return f"  set -Ux {var_name} '<value>'  # or add to {rc_file}"
    if shell_name == "pwsh":
        return f"  [Environment]::SetEnvironmentVariable('{var_name}', '<value>', 'User')"
    if shell_name == "cmd":
        return f'  setx {var_name} "<value>"'
    return f"  echo 'export {var_name}=\"<value>\"' >> {rc_file} && . {rc_file}"


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """Deep-merge two dicts. override wins on conflicts."""
    merged = base.copy()
    for key, val in override.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(val, dict):
            merged[key] = _deep_merge(merged[key], val)
        else:
            merged[key] = val
    return merged


def _find_git_root(start_dir: Path) -> Optional[Path]:
    """Find the nearest .git directory walking up from start_dir."""
    current = start_dir
    while current != current.parent:
        if (current / ".git").exists():
            return current
        current = current.parent
    return None


def _find_project_config(start_dir: Optional[str] = None) -> Optional[Path]:
    """Walk up from start_dir looking for .bitbucket.json."""
    current = Path(start_dir) if start_dir else Path.cwd()
    home = Path.home()
    git_root = _find_git_root(current)
    while current != current.parent:
        candidate = current / CONFIG_FILENAME
        if candidate.exists() and current != home:
            return candidate
        if git_root and current == git_root:
            break
        current = current.parent
    return None


def _find_global_config() -> Optional[Path]:
    """Check for ~/.bitbucket.json."""
    candidate = Path.home() / CONFIG_FILENAME
    return candidate if candidate.exists() else None


def _parse_env_line(line: str) -> Optional[Tuple[str, str]]:
    """Parse a single line from a .env file."""
    line = line.strip()
    if not line or line.startswith("#"):
        return None
    if " #" in line:
        line = line.split(" #", 1)[0]
    if "=" not in line:
        return None
    key, _, val = line.partition("=")
    key = key.strip()
    if key.startswith("export "):
        key = key[len("export "):].strip()
    val = val.strip()
    if (val.startswith('"') and val.endswith('"')) or \
       (val.startswith("'") and val.endswith("'")):
        val = val[1:-1]
    return key, val


def load_env_file(env_path: Path) -> Dict[str, str]:
    """Parse a .env file into a dict."""
    env: Dict[str, str] = {}
    if not env_path.exists():
        return env
    for line in env_path.read_text().splitlines():
        result = _parse_env_line(line)
        if result:
            key, val = result
            env[key] = val
    return env


def load_config(config_path: Optional[str] = None) -> BitbucketConfig:
    """Load and validate .bitbucket.json.

    Resolution order:
    1. If config_path is given explicitly, use it.
    2. Otherwise, search for project-level config (CWD walk-up) and global (~/.bitbucket.json).
    3. If both exist, deep-merge them (project-level wins).
    """
    if config_path:
        path = Path(config_path)
        if not path.exists():
            print(f"ERROR: Config file not found: {path}")
            sys.exit(2)
        raw = json.loads(path.read_text(encoding="utf-8"))
        project_root = path.parent
    else:
        project_cfg = _find_project_config()
        global_cfg = _find_global_config()

        if not project_cfg and not global_cfg:
            print(f"ERROR: {CONFIG_FILENAME} not found in any parent directory or ~/.")
            print()
            print("Create ~/.bitbucket.json with:")
            print(json.dumps({
                "workspace": "<your-workspace>",
                "credentials": {
                    "email_env": "BITBUCKET_EMAIL",
                    "token_env": "BITBUCKET_TOKEN",
                },
            }, indent=2))
            print()
            print("See references/CONFIG.md for full schema.")
            sys.exit(2)

        global_raw = json.loads(global_cfg.read_text(encoding="utf-8")) if global_cfg else {}
        project_raw = json.loads(project_cfg.read_text(encoding="utf-8")) if project_cfg else {}
        raw = _deep_merge(global_raw, project_raw)
        project_root = project_cfg.parent if project_cfg else Path.cwd()

    if "workspace" not in raw:
        print("ERROR: Missing required field 'workspace' in merged config")
        sys.exit(2)
    if not isinstance(raw["workspace"], str) or not raw["workspace"].strip():
        print(f"ERROR: 'workspace' must be a non-empty string (got {type(raw['workspace']).__name__})")
        sys.exit(2)

    creds = raw.get("credentials", {})
    if not isinstance(creds, dict):
        print(f"ERROR: 'credentials' must be an object (got {type(creds).__name__})")
        sys.exit(2)

    return BitbucketConfig(
        workspace=raw["workspace"],
        email_env=creds.get("email_env", "BITBUCKET_EMAIL"),
        token_env=creds.get("token_env", "BITBUCKET_TOKEN"),
        env_file=raw.get("env_file"),
        default_reviewers=raw.get("default_reviewers", []),
        default_destination=raw.get("default_destination", "master"),
        project_root=project_root,
    )


def resolve_credentials(config: BitbucketConfig) -> Tuple[str, str]:
    """Resolve email and app password from env file or environment variables.
    Returns (email, app_password). Exits on failure with shell-specific advice."""
    env_vars: Dict[str, str] = {}

    if config.env_file:
        raw_path = Path(config.env_file)
        if raw_path.is_absolute():
            # Absolute paths are used as-is (common in global ~/.bitbucket.json)
            env_path = raw_path
        else:
            # Relative paths resolve against project root with traversal check
            env_path = (config.project_root / config.env_file).resolve()
            root_resolved = config.project_root.resolve()
            if not str(env_path).startswith(str(root_resolved) + os.sep) and env_path != root_resolved:
                print(f"ERROR: env_file escapes project root: {config.env_file}")
                print("Use an absolute path in global config, or a relative path in project config.")
                sys.exit(2)
        if not env_path.exists():
            print(f"ERROR: env_file not found: {env_path}")
            sys.exit(2)
        env_vars = load_env_file(env_path)

    email = env_vars.get(config.email_env) or os.environ.get(config.email_env)
    token = env_vars.get(config.token_env) or os.environ.get(config.token_env)

    if not email:
        print(f"ERROR: Credential not found: {config.email_env}")
        print("Set it globally in your shell profile (recommended):")
        print(_credential_hint(config.email_env))
        sys.exit(2)
    if not token:
        print(f"ERROR: Credential not found: {config.token_env}")
        print("Set it globally in your shell profile (recommended):")
        print(_credential_hint(config.token_env))
        sys.exit(2)

    return email, token


def resolve_repo(config: BitbucketConfig, cli_repo: Optional[str] = None) -> str:
    """Resolve repo slug: CLI flag > git remote auto-detect. Exits if unresolvable."""
    if cli_repo:
        return cli_repo
    detected = config.auto_detect_repo()
    if detected:
        return detected
    print("ERROR: Could not detect repo slug from git remote.")
    print("Provide --repo <repo_slug> explicitly.")
    sys.exit(1)


def resolve_workspace(config: BitbucketConfig, cli_workspace: Optional[str] = None) -> str:
    """Resolve workspace: CLI flag > config. Exits if unresolvable."""
    if cli_workspace:
        return cli_workspace
    return config.workspace
