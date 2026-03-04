"""
Shared configuration loader for confluence-publisher skill scripts.

Loads .confluence.json and resolves credentials from env vars or shell environment.
Supports global config (~/.confluence.json) merged with per-project config.
"""

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

_ENV_VAR_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def ensure_deps(required_packages: dict) -> None:
    """Check that required Python packages are installed. Exits with instructions if not."""
    missing = []
    for pkg, imp in required_packages.items():
        try:
            __import__(imp)
        except ImportError:
            missing.append(pkg)
    if missing:
        skill_dir = Path(__file__).resolve().parent.parent
        req_file = skill_dir / "scripts" / "requirements.txt"
        print(f"ERROR: Missing dependencies: {', '.join(missing)}")
        print(f"Install with: pip install -r {req_file}")
        sys.exit(1)


@dataclass
class ConfluenceConfig:
    confluence_url: str
    space_key: str
    root_page_id: str
    docs_dir: str = "."
    manifest_path: str = ".confluence-manifest.json"
    username_env: str = "CONFLUENCE_EMAIL"
    token_env: str = "CONFLUENCE_TOKEN"
    env_file: Optional[str] = None
    title_map: dict = field(default_factory=dict)
    exclude_patterns: list = field(default_factory=list)

    # Resolved at runtime
    project_root: Path = field(default_factory=lambda: Path.cwd())

    @property
    def docs_root(self) -> Path:
        return self.project_root / self.docs_dir

    @property
    def manifest_file(self) -> Path:
        return self.project_root / self.manifest_path


CONFIG_FILENAME = ".confluence.json"


def add_config_arg(parser: argparse.ArgumentParser) -> None:
    """Add the standard --config argument to any script's parser.
    Centralised here so every script shares the same definition."""
    parser.add_argument(
        "--config",
        help="Path to .confluence.json (omit to auto-discover from project root or ~/.confluence.json)",
    )


def detect_shell() -> tuple[str, str]:
    """Detect user's shell and rc file path.
    Returns (shell_name, rc_file_path).

    Handles macOS, Linux, Windows, and common shells (zsh, bash, fish, pwsh, cmd).
    Falls back to (~/.profile) for unknown Unix shells."""
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
        return f"  [Environment]::SetEnvironmentVariable('{var_name}', '<value>', 'User')  # persists across sessions"
    if shell_name == "cmd":
        return f'  setx {var_name} "<value>"  # persists across sessions'
    return f"  echo 'export {var_name}=\"<value>\"' >> {rc_file} && . {rc_file}"


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
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
    """Walk up from start_dir looking for .confluence.json.
    Stops at the git repo root (if any) to avoid picking up configs from
    unrelated parent directories. Returns None if not found."""
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
    """Check for ~/.confluence.json."""
    candidate = Path.home() / CONFIG_FILENAME
    return candidate if candidate.exists() else None


def find_config(start_dir: Optional[str] = None) -> Path:
    """Find .confluence.json \u2014 project-level first, then global.
    Returns the path to the primary config (project if it exists, else global)."""
    project = _find_project_config(start_dir)
    global_cfg = _find_global_config()
    if project:
        return project
    if global_cfg:
        return global_cfg
    print(f"ERROR: {CONFIG_FILENAME} not found in any parent directory or ~/.")
    print("Create one in your project root or at ~/.confluence.json for global defaults.")
    print("See references/CONFIG.md for format.")
    sys.exit(1)


def load_env_file(env_path: Path) -> dict:
    """Parse a .env file into a dict."""
    env = {}
    if not env_path.exists():
        return env
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if "=" in line and not line.startswith("#"):
            key, _, val = line.partition("=")
            key = key.strip()
            # Handle 'export KEY=VALUE' syntax
            if key.startswith("export "):
                key = key[len("export "):].strip()
            env[key] = val.strip().strip('"').strip("'")
    return env


def _resolve_raw_config(config_path: Optional[str] = None) -> tuple[dict[str, Any], Path]:
    """Resolve raw config dict and project root.

    If config_path is explicit, load it directly.
    Otherwise, discover project-level and global configs and deep-merge them.
    Returns (raw_dict, project_root).
    """
    if config_path:
        path = Path(config_path)
        if not path.exists():
            print(f"ERROR: Config file not found: {path}")
            sys.exit(1)
        return json.loads(path.read_text(encoding="utf-8")), path.parent

    project_cfg = _find_project_config()
    global_cfg = _find_global_config()

    if not project_cfg and not global_cfg:
        print(f"ERROR: {CONFIG_FILENAME} not found in any parent directory or ~/.")
        print("Create one in your project root or at ~/.confluence.json for global defaults.")
        print("See references/CONFIG.md for format.")
        sys.exit(1)

    global_raw = json.loads(global_cfg.read_text(encoding="utf-8")) if global_cfg else {}
    project_raw = json.loads(project_cfg.read_text(encoding="utf-8")) if project_cfg else {}

    raw = _deep_merge(global_raw, project_raw)
    project_root = project_cfg.parent if project_cfg else Path.cwd()
    return raw, project_root


def load_config(config_path: Optional[str] = None) -> ConfluenceConfig:
    """Load and validate .confluence.json.

    Resolution order:
    1. If config_path is given explicitly, use it.
    2. Otherwise, search for project-level config (CWD walk-up) and global (~/.confluence.json).
    3. If both exist, deep-merge them (project-level wins).
    """
    raw, project_root = _resolve_raw_config(config_path)

    for field_name in ("confluence_url", "space_key", "root_page_id"):
        if field_name not in raw:
            print(f"ERROR: Missing required field '{field_name}' in merged config")
            if not _find_project_config():
                print("Hint: create a project-level .confluence.json with at least space_key and root_page_id.")
            sys.exit(1)
        if not isinstance(raw[field_name], (str, int)) or not str(raw[field_name]).strip():
            print(f"ERROR: '{field_name}' must be a non-empty string or number (got {type(raw[field_name]).__name__})")
            sys.exit(1)

    creds = raw.get("credentials", {})
    if not isinstance(creds, dict):
        print(f"ERROR: 'credentials' must be an object (got {type(creds).__name__})")
        sys.exit(1)

    url = raw["confluence_url"].rstrip("/")
    if not url.startswith("https://"):
        print(f"ERROR: confluence_url must use HTTPS (got: {url})")
        print("Confluence Cloud requires HTTPS. Sending credentials over HTTP is unsafe.")
        sys.exit(1)

    config = ConfluenceConfig(
        confluence_url=url,
        space_key=raw["space_key"],
        root_page_id=str(raw["root_page_id"]),
        docs_dir=raw.get("docs_dir", "."),
        manifest_path=raw.get("manifest_path", ".confluence-manifest.json"),
        username_env=creds.get("username_env", "CONFLUENCE_EMAIL"),
        token_env=creds.get("token_env", "CONFLUENCE_TOKEN"),
        env_file=raw.get("env_file"),
        title_map=raw.get("title_map", {}),
        exclude_patterns=raw.get("exclude_patterns", []),
        project_root=project_root,
    )

    return config


def resolve_credentials(config: ConfluenceConfig) -> tuple[str, str]:
    """Resolve username and API token from env file or environment variables.
    Returns (username, token). Exits on failure with shell-specific advice."""
    env_vars = {}

    # Load .env file if configured
    if config.env_file:
        env_path = (config.project_root / config.env_file).resolve()
        root_resolved = config.project_root.resolve()
        if not str(env_path).startswith(str(root_resolved) + os.sep) and env_path != root_resolved:
            print(f"ERROR: env_file escapes project root: {config.env_file}")
            sys.exit(1)
        env_vars = load_env_file(env_path)

    username = env_vars.get(config.username_env) or os.environ.get(config.username_env)
    token = env_vars.get(config.token_env) or os.environ.get(config.token_env)

    if not username:
        print(f"ERROR: Credential not found: {config.username_env}")
        print("Set it globally in your shell profile (recommended):")
        print(_credential_hint(config.username_env))
        sys.exit(1)
    if not token:
        print(f"ERROR: Credential not found: {config.token_env}")
        print("Set it globally in your shell profile (recommended):")
        print(_credential_hint(config.token_env))
        sys.exit(1)

    return username, token


def load_manifest(config: ConfluenceConfig) -> dict:
    """Load the manifest file. Returns empty dict if not found."""
    if config.manifest_file.exists():
        return json.loads(config.manifest_file.read_text(encoding="utf-8"))
    return {}


def save_manifest(config: ConfluenceConfig, manifest: dict) -> None:
    """Save the manifest file."""
    config.manifest_file.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def connect(config: ConfluenceConfig):
    """Create a Confluence client from config credentials."""
    ensure_deps({"atlassian-python-api": "atlassian"})
    from atlassian import Confluence

    username, token = resolve_credentials(config)
    return Confluence(
        url=config.confluence_url,
        username=username,
        password=token,
        cloud=True,
        timeout=120,
    )


# ---------------------------------------------------------------------------
# Re-exports from page_utils for backward compatibility
# ---------------------------------------------------------------------------
from page_utils import (  # noqa: F401, E402
    get_all_children,
    decode_tiny_link,
    encode_tiny_id,
    extract_page_id,
    resolve_title,
)
