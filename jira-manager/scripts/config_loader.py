"""
Shared configuration loader for jira-manager skill scripts.

Loads .jira.json and resolves credentials from env vars or .env file.
Mirrors the confluence-publisher config_loader.py pattern.
"""

import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional


@dataclass
class JiraConfig:
    jira_url: str
    project_key: str
    username_env: str = "JIRA_EMAIL"
    token_env: str = "JIRA_TOKEN"
    env_file: Optional[str] = None
    manifest_path: str = ".jira-manifest.json"
    source_dir: str = "."
    git_remote: str = "auto"
    git_branch: str = "main"
    estimation_pattern: str = r"Estimation:\s*([\d.]+)\s*days?"
    field_mappings: Dict[str, str] = field(default_factory=dict)
    issue_types: Dict[str, str] = field(default_factory=dict)

    # Resolved at runtime
    project_root: Path = field(default_factory=lambda: Path.cwd())

    @property
    def manifest_file(self) -> Path:
        return self.project_root / self.manifest_path

    @property
    def source_root(self) -> Path:
        return self.project_root / self.source_dir

    def get_field_id(self, name: str) -> Optional[str]:
        """Resolve a friendly field name to its Jira field ID."""
        return self.field_mappings.get(name)

    def get_issue_type_id(self, name: str) -> Optional[str]:
        """Resolve an issue type name to its Jira ID."""
        return self.issue_types.get(name.lower())

    def resolve_git_remote_url(self) -> Optional[str]:
        """Resolve the git remote URL for link rewriting."""
        if self.git_remote != "auto":
            return self.git_remote
        try:
            result = subprocess.run(
                ["git", "remote", "get-url", "origin"],
                capture_output=True, text=True, cwd=str(self.project_root),
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except FileNotFoundError:
            pass
        return None

    def resolve_git_branch(self) -> str:
        """Resolve the current git branch."""
        if self.git_branch != "auto":
            return self.git_branch
        try:
            result = subprocess.run(
                ["git", "branch", "--show-current"],
                capture_output=True, text=True, cwd=str(self.project_root),
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
        except FileNotFoundError:
            pass
        return "main"


def find_config(start_dir: Optional[str] = None) -> Path:
    """Walk up from start_dir looking for .jira.json."""
    current = Path(start_dir) if start_dir else Path.cwd()
    while current != current.parent:
        candidate = current / ".jira.json"
        if candidate.exists():
            return candidate
        current = current.parent
    print("ERROR: .jira.json not found in any parent directory")
    print("Create one in your project root. See references/CONFIG.md for format.")
    sys.exit(1)


def _parse_env_line(line: str) -> Optional[tuple[str, str]]:
    """Parse a single line from a .env file."""
    line = line.strip()
    if not line or line.startswith("#"):
        return None

    # Remove inline comments
    if " #" in line:
        line = line.split(" #", 1)[0]

    if "=" not in line:
        return None

    key, _, val = line.partition("=")
    key = key.strip()
    if key.startswith("export "):
        key = key[len("export "):].strip()

    val = val.strip()
    # Handle quoted values
    if (val.startswith('"') and val.endswith('"')) or \
       (val.startswith("'") and val.endswith("'")):
        val = val[1:-1]

    return key, val


def load_env_file(env_path: Path) -> dict:
    """Parse a .env file into a dict."""
    env = {}
    if not env_path.exists():
        return env
    for line in env_path.read_text().splitlines():
        result = _parse_env_line(line)
        if result:
            key, val = result
            env[key] = val
    return env


def load_config(config_path: Optional[str] = None) -> JiraConfig:
    """Load and validate .jira.json."""
    if config_path:
        path = Path(config_path)
    else:
        path = find_config()

    if not path.exists():
        print(f"ERROR: Config file not found: {path}")
        sys.exit(1)

    raw = json.loads(path.read_text(encoding="utf-8"))
    project_root = path.parent

    for field_name in ("jira_url", "project_key"):
        if field_name not in raw:
            print(f"ERROR: Missing required field '{field_name}' in {path}")
            sys.exit(1)

    creds = raw.get("credentials", {})

    config = JiraConfig(
        jira_url=raw["jira_url"].rstrip("/"),
        project_key=raw["project_key"],
        username_env=creds.get("username_env", "JIRA_EMAIL"),
        token_env=creds.get("token_env", "JIRA_TOKEN"),
        env_file=raw.get("env_file"),
        manifest_path=raw.get("manifest_path", ".jira-manifest.json"),
        source_dir=raw.get("source_dir", "."),
        git_remote=raw.get("git_remote", "auto"),
        git_branch=raw.get("git_branch", "main"),
        estimation_pattern=raw.get(
            "estimation_pattern", r"Estimation:\s*([\d.]+)\s*days?"
        ),
        field_mappings=raw.get("field_mappings", {}),
        issue_types=raw.get("issue_types", {}),
        project_root=project_root,
    )

    return config


def resolve_credentials(config: JiraConfig) -> tuple:
    """Resolve username and API token from env file or environment variables.
    Returns (username, token). Exits on failure."""
    env_vars = {}

    if config.env_file:
        env_path = config.project_root / config.env_file
        env_vars = load_env_file(env_path)

    username = env_vars.get(config.username_env) or os.environ.get(config.username_env)
    token = env_vars.get(config.token_env) or os.environ.get(config.token_env)

    if not username:
        print(
            f"ERROR: Credential not found: set {config.username_env} "
            f"as an environment variable or in your env_file"
        )
        sys.exit(1)
    if not token:
        print(
            f"ERROR: Credential not found: set {config.token_env} "
            f"as an environment variable or in your env_file"
        )
        sys.exit(1)

    return username, token


def load_manifest(config: JiraConfig) -> dict:
    """Load the manifest file. Returns empty dict if not found."""
    if config.manifest_file.exists():
        return json.loads(config.manifest_file.read_text(encoding="utf-8"))
    return {}


def save_manifest(config: JiraConfig, manifest: dict) -> None:
    """Save the manifest file."""
    config.manifest_file.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
