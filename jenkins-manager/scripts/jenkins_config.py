"""
Shared configuration loader for jenkins-manager skill scripts.

Loads .jenkins.json and resolves credentials from env vars or shell environment.
Supports global config (~/.jenkins.json) merged with per-project config.
Mirrors the bitbucket-manager bb_config.py pattern.
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
from urllib.parse import quote

_ENV_VAR_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

CONFIG_FILENAME = ".jenkins.json"


@dataclass
class InstanceConfig:
    """Configuration for a single Jenkins instance."""

    name: str
    base_url: str
    description: str = ""
    username_env: str = "JENKINS_USER"
    token_env: str = "JENKINS_TOKEN"
    env_file: str | None = None
    job_cache: dict[str, str] = field(default_factory=dict)
    default_branch: str | None = None
    default_username: str | None = None
    ssl_verify: bool = True
    project_root: Path = field(default_factory=lambda: Path.cwd())


@dataclass
class JenkinsConfig:
    """Top-level config holding all named instances."""

    instances: dict[str, InstanceConfig] = field(default_factory=dict)
    default_instance: str | None = None
    env_file: str | None = None
    project_root: Path = field(default_factory=lambda: Path.cwd())


def detect_repo_name(project_root: Path | None = None) -> str | None:
    """Detect repo name from git remote origin URL.

    Works with any git host (Bitbucket, GitHub, GitLab, etc.).
    Extracts the last path segment, stripping .git suffix.
    """
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            cwd=str(project_root) if project_root else None,
        )
        if result.returncode != 0:
            return None
        url = result.stdout.strip()
        return _parse_repo_name(url)
    except FileNotFoundError:
        return None


def _parse_repo_name(remote_url: str) -> str | None:
    """Extract repo name from any git remote URL.

    Handles SSH, HTTPS, and any host:
      git@host.com:org/repo.git  -> repo
      https://host.com/org/repo.git -> repo
      ssh://git@host.com/org/repo.git -> repo
    """
    # Strip trailing slashes and .git suffix
    url = remote_url.rstrip("/")
    if url.endswith(".git"):
        url = url[:-4]

    # SSH: git@host:org/repo
    if url.startswith("git@"):
        parts = url.split(":")[-1]
        segments = parts.split("/")
        return segments[-1] if segments else None

    # HTTPS or SSH with scheme: https://host/org/repo or ssh://git@host/org/repo
    url_parts = url.split("/")
    return url_parts[-1] if url_parts else None


def detect_current_branch(project_root: Path | None = None) -> str | None:
    """Detect current git branch name."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            cwd=str(project_root) if project_root else None,
        )
        if result.returncode != 0:
            return None
        branch = result.stdout.strip()
        return branch if branch and branch != "HEAD" else None
    except FileNotFoundError:
        return None


def url_encode_branch(branch: str) -> str:
    """URL-encode a branch name for Jenkins API paths.

    Jenkins encodes '/' as '%2F' in URL paths for branch names.
    """
    return quote(branch, safe="")


def add_common_args(parser: argparse.ArgumentParser) -> None:
    """Add standard --config, --instance, --folder, --job, and --branch arguments."""
    parser.add_argument(
        "--config",
        help="Path to .jenkins.json (omit to auto-discover)",
    )
    parser.add_argument(
        "--instance",
        help="Named Jenkins instance (omit to use default_instance or JENKINS_INSTANCE env var)",
    )
    parser.add_argument(
        "--folder",
        help="Jenkins folder name (omit to auto-discover from job_cache or API)",
    )
    parser.add_argument(
        "--job",
        help="Jenkins job name (omit to auto-detect from git remote)",
    )
    parser.add_argument(
        "--branch",
        help="Branch name (omit to auto-detect from current git branch)",
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
    """Walk up from start_dir looking for .jenkins.json."""
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
    """Check for ~/.jenkins.json."""
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


def load_config(config_path: str | None = None) -> JenkinsConfig:
    """Load and validate .jenkins.json with named instances.

    Resolution order:
    1. If config_path is given explicitly, use it.
    2. Otherwise, search for project-level config (CWD walk-up) and global (~/.jenkins.json).
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
            print("Create ~/.jenkins.json with:")
            print(
                json.dumps(
                    {
                        "instances": {
                            "ci": {
                                "base_url": "https://your-jenkins-ci.example.com",
                                "credentials": {
                                    "username_env": "JENKINS_USER",
                                    "token_env": "JENKINS_TOKEN",
                                },
                            }
                        },
                        "default_instance": "ci",
                    },
                    indent=2,
                )
            )
            print()
            print("See references/CONFIG.md for full schema.")
            sys.exit(2)

        global_raw = json.loads(global_cfg.read_text(encoding="utf-8")) if global_cfg else {}
        project_raw = json.loads(project_cfg.read_text(encoding="utf-8")) if project_cfg else {}
        raw = _deep_merge(global_raw, project_raw)
        project_root = project_cfg.parent if project_cfg else Path.cwd()

    if "instances" not in raw or not isinstance(raw["instances"], dict):
        print("ERROR: Missing required field 'instances' in config.")
        print("Config must contain named instances. See references/CONFIG.md for the schema.")
        sys.exit(2)

    top_env_file = raw.get("env_file")
    instances: dict[str, InstanceConfig] = {}

    for name, inst_raw in raw["instances"].items():
        if not isinstance(inst_raw, dict):
            print(f"ERROR: Instance '{name}' must be an object")
            sys.exit(2)
        if "base_url" not in inst_raw:
            print(f"ERROR: Instance '{name}' missing required field 'base_url'")
            sys.exit(2)

        creds = inst_raw.get("credentials", {})
        inst_env_file = inst_raw.get("env_file") or creds.get("env_file") or top_env_file

        instances[name] = InstanceConfig(
            name=name,
            base_url=inst_raw["base_url"].rstrip("/"),
            description=inst_raw.get("description", ""),
            username_env=creds.get("username_env", "JENKINS_USER"),
            token_env=creds.get("token_env", "JENKINS_TOKEN"),
            env_file=inst_env_file,
            job_cache=inst_raw.get("job_cache", {}),
            default_branch=inst_raw.get("default_branch"),
            default_username=inst_raw.get("default_username"),
            ssl_verify=inst_raw.get("ssl_verify", True),
            project_root=project_root,
        )

    return JenkinsConfig(
        instances=instances,
        default_instance=raw.get("default_instance"),
        env_file=top_env_file,
        project_root=project_root,
    )


def _print_available_instances(config: JenkinsConfig) -> None:
    """Print available instances with descriptions."""
    print("Available instances:")
    for name, inst in config.instances.items():
        desc = f" — {inst.description}" if inst.description else ""
        default_marker = " (default)" if name == config.default_instance else ""
        print(f"  {name}{default_marker}: {inst.base_url}{desc}")


def resolve_instance(config: JenkinsConfig, cli_instance: str | None = None) -> InstanceConfig:
    """Resolve which Jenkins instance to use.

    Priority:
    1. --instance flag (explicit)
    2. JENKINS_INSTANCE env var
    3. default_instance from config
    4. If only one instance exists, use it
    5. Error with list of available instances
    """
    available = list(config.instances.keys())

    # 1. CLI flag
    name = cli_instance
    # 2. Env var
    if not name:
        name = os.environ.get("JENKINS_INSTANCE")
    # 3. Config default
    if not name:
        name = config.default_instance
    # 4. Single instance
    if not name and len(available) == 1:
        name = available[0]

    if not name:
        print("ERROR: Multiple Jenkins instances configured but no instance selected.")
        _print_available_instances(config)
        print(
            "Use --instance <name>, set JENKINS_INSTANCE env var, or set default_instance in config."
        )
        sys.exit(2)

    if name not in config.instances:
        print(f"ERROR: Instance '{name}' not found in config.")
        _print_available_instances(config)
        sys.exit(2)

    return config.instances[name]


def resolve_credentials(instance: InstanceConfig) -> tuple[str, str]:
    """Resolve username and API token from env file or environment variables.
    Returns (username, token). Exits on failure with shell-specific advice."""
    env_vars: dict[str, str] = {}

    if instance.env_file:
        raw_path = Path(instance.env_file)
        if raw_path.is_absolute():
            env_path = raw_path
        else:
            env_path = (instance.project_root / instance.env_file).resolve()
            root_resolved = instance.project_root.resolve()
            if (
                not str(env_path).startswith(str(root_resolved) + os.sep)
                and env_path != root_resolved
            ):
                print(f"ERROR: env_file escapes project root: {instance.env_file}")
                print(
                    "Use an absolute path in global config, or a relative path in project config."
                )
                sys.exit(2)
        if not env_path.exists():
            print(f"ERROR: env_file not found: {env_path}")
            sys.exit(2)
        env_vars = load_env_file(env_path)

    username = env_vars.get(instance.username_env) or os.environ.get(instance.username_env)
    if not username and instance.default_username:
        username = instance.default_username
    token = env_vars.get(instance.token_env) or os.environ.get(instance.token_env)

    if not username:
        print(f"ERROR: Credential not found: {instance.username_env} (instance: {instance.name})")
        print("Set it globally in your shell profile (recommended):")
        print(_credential_hint(instance.username_env))
        print("Or set 'default_username' in the instance config as a fallback.")
        sys.exit(2)
    if not token:
        print(f"ERROR: Credential not found: {instance.token_env} (instance: {instance.name})")
        print("Set it globally in your shell profile (recommended):")
        print(_credential_hint(instance.token_env))
        sys.exit(2)

    return username, token


def resolve_job_path(
    instance: InstanceConfig,
    cli_folder: str | None = None,
    cli_job: str | None = None,
) -> tuple[str | None, str | None]:
    """Resolve Jenkins folder and job name.

    Priority: CLI flags > job_cache > None (caller handles discovery).
    """
    if cli_folder and cli_job:
        return cli_folder, cli_job

    # Try job_cache using auto-detected repo name
    repo_name = cli_job or detect_repo_name(instance.project_root)
    if repo_name and repo_name in instance.job_cache:
        cached = instance.job_cache[repo_name]
        parts = cached.split("/", 1)
        if len(parts) == 2:
            folder = cli_folder or parts[0]
            job = parts[1]
            return folder, job

    # If only job provided (no folder), return it with None folder
    if cli_job:
        return cli_folder, cli_job

    return cli_folder, repo_name


def resolve_full_job_path(
    instance: InstanceConfig,
    client: Any,
    cli_folder: str | None = None,
    cli_job: str | None = None,
) -> tuple[str | None, str | None]:
    """Resolve folder + job with full auto-discovery.

    Priority: CLI flags > job_cache > API search via find_job().
    Prints a hint to add to job_cache on first API discovery.
    """
    folder, job = resolve_job_path(instance, cli_folder, cli_job)

    if not job:
        return folder, job

    # If folder is already known, we're done
    if folder:
        return folder, job

    # Try API discovery
    try:
        discovered = client.find_job(job)
    except Exception:
        discovered = None

    if discovered:
        folder, job = discovered
        if folder:
            print(
                f"Hint: Add to job_cache in .jenkins.json to skip discovery next time: "
                f'"{job}": "{folder}/{job}"',
                file=sys.stderr,
            )
        return folder, job

    return None, job


def resolve_branch(
    instance: InstanceConfig,
    cli_branch: str | None = None,
) -> str | None:
    """Resolve branch name: CLI flag > current git branch > config default."""
    if cli_branch:
        return cli_branch
    detected = detect_current_branch(instance.project_root)
    if detected:
        return detected
    return instance.default_branch
