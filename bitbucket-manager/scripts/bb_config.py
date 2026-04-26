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
from typing import Any

_ENV_VAR_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

CONFIG_FILENAME = ".bitbucket.json"


@dataclass
class BitbucketConfig:
    workspace: str
    auth_mode: str = "basic"
    email_env: str = "BITBUCKET_EMAIL"
    token_env: str = "BITBUCKET_TOKEN"
    env_file: str | None = None
    default_reviewers: list[str] = field(default_factory=list)
    default_destination: str = "master"
    repo_tokens: dict[str, str] = field(default_factory=dict)

    # Resolved at runtime
    project_root: Path = field(default_factory=lambda: Path.cwd())

    def auto_detect_repo(self) -> str | None:
        """Detect repo_slug from git remote origin URL.

        Parses SSH and HTTPS Bitbucket remote URLs:
          git@bitbucket.org:workspace/repo.git  -> repo
          https://bitbucket.org/workspace/repo.git -> repo
          https://user@bitbucket.org/workspace/repo.git -> repo
        """
        try:
            result = subprocess.run(
                ["git", "remote", "get-url", "origin"],
                capture_output=True,
                text=True,
                cwd=str(self.project_root),
            )
            if result.returncode != 0:
                return None
            url = result.stdout.strip()
            return _parse_repo_slug(url)
        except FileNotFoundError:
            return None


@dataclass(frozen=True)
class AuthCandidate:
    mode: str
    token: str
    email: str | None
    source: str
    token_env: str
    repo_key: str | None = None


@dataclass(frozen=True)
class AuthSelection:
    candidate: AuthCandidate
    fallback_used: bool
    attempted_sources: tuple[str, ...]


class AuthResolutionError(RuntimeError):
    """Raised when no usable Bitbucket auth path can be resolved."""


def build_repo_key(workspace: str, repo_slug: str) -> str:
    """Return the canonical repo key used by repo_tokens."""
    return f"{workspace}/{repo_slug}"


def _parse_repo_slug(remote_url: str) -> str | None:
    """Extract repo_slug from a Bitbucket remote URL."""
    # SSH: git@bitbucket.org:workspace/repo.git
    if remote_url.startswith("git@"):
        path = remote_url.split(":")[-1].rstrip(".git")
        segments = path.split("/")
        if len(segments) >= 2:
            return segments[-1]
    # HTTPS: https://bitbucket.org/workspace/repo.git
    elif "bitbucket.org" in remote_url:
        segments = remote_url.rstrip("/").rstrip(".git").split("/")
        if len(segments) >= 2:
            return segments[-1]
    return None


def _parse_workspace_and_repo(remote_url: str) -> tuple[str | None, str | None]:
    """Extract workspace and repo_slug from a Bitbucket remote URL."""
    # SSH: git@bitbucket.org:workspace/repo.git
    if remote_url.startswith("git@"):
        path = remote_url.split(":")[-1].rstrip(".git")
        segments = path.split("/")
        if len(segments) >= 2:
            return segments[-2], segments[-1]
    # HTTPS: https://bitbucket.org/workspace/repo.git
    elif "bitbucket.org" in remote_url:
        segments = remote_url.rstrip("/").rstrip(".git").split("/")
        if len(segments) >= 2:
            return segments[-2], segments[-1]
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


def detect_shell() -> tuple[str, str]:
    """Detect user's shell and rc file path."""
    if sys.platform == "win32":
        comspec = os.environ.get("COMSPEC", "")
        if "pwsh" in comspec.lower() or "powershell" in comspec.lower():
            return "pwsh", "$PROFILE"
        if os.environ.get("PSModulePath"):  # noqa: SIM112
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


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Deep-merge two dicts. override wins on conflicts."""
    merged = base.copy()
    for key, val in override.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(val, dict):
            merged[key] = _deep_merge(merged[key], val)
        else:
            merged[key] = val
    return merged


def _find_git_root(start_dir: Path) -> Path | None:
    """Find the nearest .git directory walking up from start_dir."""
    current = start_dir
    while current != current.parent:
        if (current / ".git").exists():
            return current
        current = current.parent
    return None


def _find_project_config(start_dir: str | None = None) -> Path | None:
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


def _find_global_config() -> Path | None:
    """Check for ~/.bitbucket.json."""
    candidate = Path.home() / CONFIG_FILENAME
    return candidate if candidate.exists() else None


def _parse_env_line(line: str) -> tuple[str, str] | None:
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
        key = key[len("export ") :].strip()
    val = val.strip()
    if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
        val = val[1:-1]
    return key, val


def load_env_file(env_path: Path) -> dict[str, str]:
    """Parse a .env file into a dict."""
    env: dict[str, str] = {}
    if not env_path.exists():
        return env
    for line in env_path.read_text().splitlines():
        result = _parse_env_line(line)
        if result:
            key, val = result
            env[key] = val
    return env


def _load_raw_config(config_path: str | None = None) -> tuple[dict[str, Any], Path]:
    """Load raw config dict and determine project root."""
    if config_path:
        path = Path(config_path)
        if not path.exists():
            print(f"ERROR: Config file not found: {path}")
            sys.exit(2)
        return json.loads(path.read_text(encoding="utf-8")), path.parent

    project_cfg = _find_project_config()
    global_cfg = _find_global_config()

    if not project_cfg and not global_cfg:
        print(f"ERROR: {CONFIG_FILENAME} not found in any parent directory or ~/.")
        print()
        print("Create ~/.bitbucket.json with:")
        print(
            json.dumps(
                {
                    "workspace": "<your-workspace>",
                    "credentials": {
                        "email_env": "BITBUCKET_EMAIL",
                        "token_env": "BITBUCKET_TOKEN",
                    },
                },
                indent=2,
            )
        )
        print()
        print("See references/CONFIG.md for full schema.")
        sys.exit(2)

    global_raw = json.loads(global_cfg.read_text(encoding="utf-8")) if global_cfg else {}
    project_raw = json.loads(project_cfg.read_text(encoding="utf-8")) if project_cfg else {}
    project_root = project_cfg.parent if project_cfg else Path.cwd()
    return _deep_merge(global_raw, project_raw), project_root


def _parse_repo_tokens(raw: dict[str, Any]) -> dict[str, str]:
    """Validate and normalize repo_tokens config."""
    repo_tokens_raw = raw.get("repo_tokens", {})
    if repo_tokens_raw is None:
        return {}
    if not isinstance(repo_tokens_raw, dict):
        print(f"ERROR: 'repo_tokens' must be an object (got {type(repo_tokens_raw).__name__})")
        sys.exit(2)

    repo_tokens: dict[str, str] = {}
    for repo_key, entry in repo_tokens_raw.items():
        if not isinstance(repo_key, str) or "/" not in repo_key:
            print(f"ERROR: repo_tokens keys must look like 'workspace/repo' (got {repo_key!r})")
            sys.exit(2)
        if not isinstance(entry, dict):
            print(
                f"ERROR: repo_tokens[{repo_key!r}] must be an object (got {type(entry).__name__})"
            )
            sys.exit(2)
        token_env = entry.get("token_env")
        if not isinstance(token_env, str) or not token_env.strip():
            print(f"ERROR: repo_tokens[{repo_key!r}].token_env must be a non-empty string")
            sys.exit(2)
        repo_tokens[repo_key] = token_env
    return repo_tokens


def _resolve_env_vars(config: BitbucketConfig) -> dict[str, str]:
    """Load configured env_file values, if any."""
    env_vars: dict[str, str] = {}

    if not config.env_file:
        return env_vars

    raw_path = Path(config.env_file)
    if raw_path.is_absolute():
        env_path = raw_path
    else:
        env_path = (config.project_root / config.env_file).resolve()
        root_resolved = config.project_root.resolve()
        if not str(env_path).startswith(str(root_resolved) + os.sep) and env_path != root_resolved:
            print(f"ERROR: env_file escapes project root: {config.env_file}")
            print("Use an absolute path in global config, or a relative path in project config.")
            sys.exit(2)
    if env_path.exists():
        env_vars = load_env_file(env_path)
    else:
        print(f"WARN: env_file not found: {env_path}", file=sys.stderr)

    return env_vars


def load_config(config_path: str | None = None) -> BitbucketConfig:
    """Load and validate .bitbucket.json.

    Resolution order:
    1. If config_path is given explicitly, use it.
    2. Otherwise, search for project-level config (CWD walk-up) and global (~/.bitbucket.json).
    3. If both exist, deep-merge them (project-level wins).
    """
    raw, project_root = _load_raw_config(config_path)

    if "workspace" not in raw:
        print("ERROR: Missing required field 'workspace' in merged config")
        sys.exit(2)
    if not isinstance(raw["workspace"], str) or not raw["workspace"].strip():
        print(
            f"ERROR: 'workspace' must be a non-empty string (got {type(raw['workspace']).__name__})"
        )
        sys.exit(2)

    creds = raw.get("credentials", {})
    if not isinstance(creds, dict):
        print(f"ERROR: 'credentials' must be an object (got {type(creds).__name__})")
        sys.exit(2)

    repo_tokens = _parse_repo_tokens(raw)

    return BitbucketConfig(
        workspace=raw["workspace"],
        auth_mode=creds.get("auth_mode", "basic"),
        email_env=creds.get("email_env", "BITBUCKET_EMAIL"),
        token_env=creds.get("token_env", "BITBUCKET_TOKEN"),
        env_file=raw.get("env_file"),
        default_reviewers=raw.get("default_reviewers", []),
        default_destination=raw.get("default_destination", "master"),
        repo_tokens=repo_tokens,
        project_root=project_root,
    )


def resolve_credentials(config: BitbucketConfig) -> tuple[str, str]:
    """Resolve email and API token from env file or environment variables.
    Returns (email, api_token). Exits on failure with shell-specific advice."""
    env_vars = _resolve_env_vars(config)

    email = env_vars.get(config.email_env) or os.environ.get(config.email_env)
    token = env_vars.get(config.token_env) or os.environ.get(config.token_env)

    if not email:
        print(f"ERROR: Credential not found: {config.email_env}")
        if config.env_file:
            print(
                "Set it globally in your shell profile, or fix the configured env_file path and "
                "re-run."
            )
        else:
            print("Set it globally in your shell profile (recommended):")
        print(_credential_hint(config.email_env))
        sys.exit(2)
    if not token:
        print(f"ERROR: Credential not found: {config.token_env}")
        if config.env_file:
            print(
                "Set it globally in your shell profile, or fix the configured env_file path and "
                "re-run."
            )
        else:
            print("Set it globally in your shell profile (recommended):")
        print(_credential_hint(config.token_env))
        sys.exit(2)

    return email, token


def resolve_auth(config: BitbucketConfig) -> tuple[str, str | None, str]:
    """Resolve only the explicitly configured default auth path.

    This helper exists for backward compatibility. Shared runtime auth should use
    ``resolve_auth_candidates`` so repo-token fallback can be considered.
    """
    auth_mode = (config.auth_mode or "basic").strip().lower()
    if auth_mode not in {"basic", "bearer"}:
        print(f"ERROR: Unsupported credentials.auth_mode: {config.auth_mode!r}")
        print("Use 'basic' for personal Bitbucket API tokens or 'bearer' for access tokens.")
        sys.exit(2)

    env_vars = _resolve_env_vars(config)

    token = env_vars.get(config.token_env) or os.environ.get(config.token_env)
    if not token:
        print(f"ERROR: Credential not found: {config.token_env}")
        if config.env_file:
            print(
                "Set it globally in your shell profile, or fix the configured env_file path and "
                "re-run."
            )
        else:
            print("Set it globally in your shell profile (recommended):")
        print(_credential_hint(config.token_env))
        sys.exit(2)

    if auth_mode == "bearer":
        return auth_mode, None, token

    email = env_vars.get(config.email_env) or os.environ.get(config.email_env)
    if not email:
        print(f"ERROR: Credential not found: {config.email_env}")
        if config.env_file:
            print(
                "Set it globally in your shell profile, or fix the configured env_file path and "
                "re-run."
            )
        else:
            print("Set it globally in your shell profile (recommended):")
        print(_credential_hint(config.email_env))
        sys.exit(2)

    return auth_mode, email, token


def resolve_auth_candidates(
    config: BitbucketConfig,
    workspace: str,
    repo_slug: str | None,
) -> tuple[list[AuthCandidate], tuple[str, ...]]:
    """Resolve usable auth candidates for a target repo.

    Returns ``(candidates, attempted_sources)`` where candidates are ordered by preference.
    Raises ``AuthResolutionError`` when no usable auth path can be built.
    """
    auth_mode = (config.auth_mode or "basic").strip().lower()
    if auth_mode not in {"basic", "bearer"}:
        raise AuthResolutionError(
            f"Unsupported credentials.auth_mode {config.auth_mode!r}. "
            "Use 'basic' for personal Bitbucket auth or 'bearer' for a legacy direct bearer token."
        )

    env_vars = _resolve_env_vars(config)
    candidates: list[AuthCandidate] = []
    attempted_sources: list[str] = []
    issues: list[str] = []

    default_token = env_vars.get(config.token_env) or os.environ.get(config.token_env)
    default_email = env_vars.get(config.email_env) or os.environ.get(config.email_env)

    if auth_mode == "basic":
        attempted_sources.append("basic")
        if default_email and default_token:
            candidates.append(
                AuthCandidate(
                    mode="basic",
                    token=default_token,
                    email=default_email,
                    source="basic",
                    token_env=config.token_env,
                )
            )
        else:
            missing_parts: list[str] = []
            if not default_email:
                missing_parts.append(config.email_env)
            if not default_token:
                missing_parts.append(config.token_env)
            issues.append(
                "Default basic auth is not fully configured"
                + (f" (missing {', '.join(missing_parts)})" if missing_parts else "")
            )
    else:
        attempted_sources.append("legacy_bearer")
        if default_token:
            candidates.append(
                AuthCandidate(
                    mode="bearer",
                    token=default_token,
                    email=None,
                    source="legacy_bearer",
                    token_env=config.token_env,
                )
            )
        else:
            issues.append(f"Default bearer auth is missing {config.token_env}")

    repo_key = build_repo_key(workspace, repo_slug) if repo_slug else None
    if repo_key:
        repo_token_env = config.repo_tokens.get(repo_key)
        if repo_token_env:
            attempted_sources.append("repo_token")
            repo_token = env_vars.get(repo_token_env) or os.environ.get(repo_token_env)
            if repo_token:
                candidates.append(
                    AuthCandidate(
                        mode="bearer",
                        token=repo_token,
                        email=None,
                        source="repo_token",
                        token_env=repo_token_env,
                        repo_key=repo_key,
                    )
                )
            else:
                issues.append(
                    f"Repo token for '{repo_key}' is configured, but {repo_token_env} is missing"
                )
        else:
            issues.append(
                f"No repo token configured for '{repo_key}'. Ask the human to add a repo token "
                "entry for this repo in ~/.bitbucket.json if fallback auth is needed."
            )

    if candidates:
        return candidates, tuple(attempted_sources)

    if issues:
        raise AuthResolutionError("; ".join(issues))

    raise AuthResolutionError("No usable Bitbucket auth candidates were found.")


def select_auth(
    config: BitbucketConfig,
    workspace: str,
    repo_slug: str | None,
    preferred_source: str | None = None,
) -> AuthSelection:
    """Select the current auth candidate for a repo.

    If ``preferred_source`` is provided and still valid, keep using it.
    Otherwise pick the first available candidate.
    """
    candidates, attempted_sources = resolve_auth_candidates(config, workspace, repo_slug)
    if preferred_source:
        for candidate in candidates:
            if candidate.source == preferred_source:
                return AuthSelection(
                    candidate=candidate,
                    fallback_used=(candidate.source == "repo_token"),
                    attempted_sources=attempted_sources,
                )
    candidate = candidates[0]
    return AuthSelection(
        candidate=candidate,
        fallback_used=(candidate.source == "repo_token"),
        attempted_sources=attempted_sources,
    )


def resolve_repo(config: BitbucketConfig, cli_repo: str | None = None) -> str:
    """Resolve repo slug: CLI flag > git remote auto-detect. Exits if unresolvable."""
    if cli_repo:
        return cli_repo
    detected = config.auto_detect_repo()
    if detected:
        return detected
    print("ERROR: Could not detect repo slug from git remote.")
    print("Provide --repo <repo_slug> explicitly.")
    sys.exit(1)


def resolve_workspace(config: BitbucketConfig, cli_workspace: str | None = None) -> str:
    """Resolve workspace: CLI flag > config. Exits if unresolvable."""
    if cli_workspace:
        return cli_workspace
    return config.workspace
