#!/usr/bin/env python3
"""Pre-flight checks for jenkins-manager skill.

Verifies Python version, config file, credentials, and connectivity for all instances.
Run this before any other script. Exits 0 if all checks pass, 1 if any fail.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from jenkins_config import (
    CONFIG_FILENAME,
    _credential_hint,
    _deep_merge,
    _find_global_config,
    _find_project_config,
    _parse_repo_name,
    load_env_file,
)

_PASS = "[PASS]"
_FAIL = "[FAIL]"
_WARN = "[WARN]"


def _check_python() -> bool:
    """Check Python version >= 3.10."""
    major, minor = sys.version_info[:2]
    if major >= 3 and minor >= 10:
        print(f"{_PASS} Python {major}.{minor}")
        return True
    print(f"{_FAIL} Python {major}.{minor} — requires 3.10+")
    return False


def _check_config() -> tuple[bool, dict, Path | None]:
    """Check config file exists and is valid JSON with instances.
    Returns (ok, merged_raw, project_root)."""
    project_cfg = _find_project_config()
    global_cfg = _find_global_config()

    if not project_cfg and not global_cfg:
        print(f"{_FAIL} Config — {CONFIG_FILENAME} not found in any parent directory or ~/")
        print()
        print("  Create ~/.jenkins.json with:")
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
        return False, {}, None

    sources = []
    if global_cfg:
        sources.append(f"global: {global_cfg}")
    if project_cfg:
        sources.append(f"project: {project_cfg}")

    try:
        global_raw = json.loads(global_cfg.read_text(encoding="utf-8")) if global_cfg else {}
        project_raw = json.loads(project_cfg.read_text(encoding="utf-8")) if project_cfg else {}
    except json.JSONDecodeError as e:
        print(f"{_FAIL} Config — invalid JSON: {e}")
        return False, {}, None

    raw = _deep_merge(global_raw, project_raw)
    project_root = project_cfg.parent if project_cfg else Path.cwd()

    if "instances" not in raw or not isinstance(raw["instances"], dict):
        print(f"{_FAIL} Config — missing required field 'instances'")
        return False, raw, project_root

    instance_names = list(raw["instances"].keys())
    default = raw.get("default_instance", instance_names[0] if len(instance_names) == 1 else None)
    default_str = f", default: {default}" if default else ""
    print(
        f"{_PASS} Config — {len(instance_names)} instance(s): {', '.join(instance_names)}{default_str} ({', '.join(sources)})"
    )
    return True, raw, project_root


def _check_instance_credentials(
    name: str, inst_raw: dict, top_env_file: str | None, project_root: Path | None
) -> bool:
    """Check credentials for a single instance."""
    creds = inst_raw.get("credentials", {})
    username_env = creds.get("username_env", "JENKINS_USER")
    token_env = creds.get("token_env", "JENKINS_TOKEN")

    env_vars: dict[str, str] = {}
    env_file = inst_raw.get("env_file") or creds.get("env_file") or top_env_file
    if env_file:
        raw_path = Path(env_file)
        if raw_path.is_absolute():
            env_path = raw_path
        elif project_root:
            env_path = (project_root / env_file).resolve()
            root_resolved = project_root.resolve()
            if (
                not str(env_path).startswith(str(root_resolved) + os.sep)
                and env_path != root_resolved
            ):
                env_path = None
        else:
            env_path = None
        if env_path and env_path.exists():
            env_vars = load_env_file(env_path)

    username = env_vars.get(username_env) or os.environ.get(username_env)
    token = env_vars.get(token_env) or os.environ.get(token_env)

    ok = True
    if username:
        print(f"  {_PASS} {username_env}: SET")
    else:
        print(f"  {_FAIL} {username_env}: MISSING")
        print(f"    {_credential_hint(username_env)}")
        ok = False

    if token:
        print(f"  {_PASS} {token_env}: SET")
    else:
        print(f"  {_FAIL} {token_env}: MISSING")
        print(f"    {_credential_hint(token_env)}")
        ok = False

    return ok


def _check_instance_connectivity(
    name: str, inst_raw: dict, top_env_file: str | None, project_root: Path | None
) -> bool:
    """Check connectivity for a single instance."""
    try:
        from jenkins_config import InstanceConfig

        creds = inst_raw.get("credentials", {})
        env_file = inst_raw.get("env_file") or creds.get("env_file") or top_env_file
        instance = InstanceConfig(
            name=name,
            base_url=inst_raw["base_url"].rstrip("/"),
            username_env=creds.get("username_env", "JENKINS_USER"),
            token_env=creds.get("token_env", "JENKINS_TOKEN"),
            env_file=env_file,
            project_root=project_root or Path.cwd(),
        )

        from jenkins_client import JenkinsClient

        client = JenkinsClient(instance)
        if client.test_connection():
            print(f"  {_PASS} Connectivity — API reachable")
            return True
        print(f"  {_FAIL} Connectivity — API returned error")
        return False
    except SystemExit:
        print(f"  {_FAIL} Connectivity — credential resolution failed")
        return False
    except Exception as e:
        print(f"  {_FAIL} Connectivity — {e}")
        return False


def _check_repo_detection() -> tuple[bool, str | None]:
    """Check if repo name can be auto-detected from git remote."""
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            print(f"{_WARN} Repo detection — no git remote 'origin' found (use --job flag)")
            return True, None

        url = result.stdout.strip()
        repo_name = _parse_repo_name(url)
        if repo_name:
            print(f"{_PASS} Repo detection — {repo_name} (from origin)")
            return True, repo_name
        print(f"{_WARN} Repo detection — could not parse repo name from: {url}")
        return True, None

    except FileNotFoundError:
        print(f"{_WARN} Repo detection — git not found (use --job flag)")
        return True, None


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Pre-flight checks for jenkins-manager")
    parser.add_argument(
        "--skip-connectivity",
        action="store_true",
        help="Skip API connectivity checks",
    )
    args = parser.parse_args()

    print("Jenkins Manager — Pre-flight Checks")
    print("=" * 40)
    print()

    results = []

    # 1. Python version
    results.append(_check_python())

    # 2. Config file
    config_ok, raw, project_root = _check_config()
    results.append(config_ok)

    if not config_ok:
        print()
        print("=" * 40)
        print("Config check failed. Fix the issues above.")
        sys.exit(1)

    # 3. Per-instance checks
    top_env_file = raw.get("env_file")
    for name, inst_raw in raw["instances"].items():
        base_url = inst_raw.get("base_url", "?")
        desc = inst_raw.get("description", "")
        desc_str = f" — {desc}" if desc else ""
        print(f"\nInstance: {name} ({base_url}){desc_str}")

        creds_ok = _check_instance_credentials(name, inst_raw, top_env_file, project_root)
        results.append(creds_ok)

        if not args.skip_connectivity and creds_ok:
            results.append(_check_instance_connectivity(name, inst_raw, top_env_file, project_root))

    # 4. Repo detection
    print()
    repo_ok, repo_name = _check_repo_detection()
    results.append(repo_ok)

    # Summary
    passed = sum(results)
    total = len(results)
    print()
    print("=" * 40)
    if all(results):
        print(f"All {total} checks passed. Ready to use.")
        sys.exit(0)
    else:
        failed = total - passed
        print(f"{passed}/{total} passed, {failed} failed. Fix the issues above.")
        sys.exit(1)


if __name__ == "__main__":
    main()
