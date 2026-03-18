#!/usr/bin/env python3
"""Pre-flight checks for jenkins-manager skill.

Verifies Python version, config file, credentials, connectivity, and job discovery.
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
    """Check config file exists and is valid JSON with required fields.
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
                    "base_url": "https://your-jenkins-instance.example.com",
                    "credentials": {
                        "username_env": "JENKINS_USER",
                        "token_env": "JENKINS_TOKEN",
                    },
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

    # Parse and merge
    try:
        global_raw = json.loads(global_cfg.read_text(encoding="utf-8")) if global_cfg else {}
        project_raw = json.loads(project_cfg.read_text(encoding="utf-8")) if project_cfg else {}
    except json.JSONDecodeError as e:
        print(f"{_FAIL} Config — invalid JSON: {e}")
        return False, {}, None

    raw = _deep_merge(global_raw, project_raw)
    project_root = project_cfg.parent if project_cfg else Path.cwd()

    # Check required field
    if "base_url" not in raw or not raw["base_url"].strip():
        print(f"{_FAIL} Config — missing required field 'base_url'")
        if not project_cfg:
            print(
                f"  Hint: create a project-level {CONFIG_FILENAME} or add base_url to ~/.jenkins.json"
            )
        return False, raw, project_root

    print(f"{_PASS} Config — base_url: {raw['base_url']} ({', '.join(sources)})")
    return True, raw, project_root


def _check_credentials(raw: dict, project_root: Path | None) -> bool:
    """Check credential env vars are set. Never prints values."""
    creds = raw.get("credentials", {})
    username_env = creds.get("username_env", "JENKINS_USER")
    token_env = creds.get("token_env", "JENKINS_TOKEN")

    # Load .env file if configured
    env_vars: dict[str, str] = {}
    env_file = raw.get("env_file")
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
                env_path = None  # skip — relative path escapes project root
        else:
            env_path = None
        if env_path and env_path.exists():
            env_vars = load_env_file(env_path)
        elif env_path and not env_path.exists():
            print(f"{_WARN} env_file not found: {env_path}")

    username = env_vars.get(username_env) or os.environ.get(username_env)
    token = env_vars.get(token_env) or os.environ.get(token_env)

    ok = True
    if username:
        print(f"{_PASS} Credentials — {username_env}: SET")
    else:
        print(f"{_FAIL} Credentials — {username_env}: MISSING")
        print(_credential_hint(username_env))
        ok = False

    if token:
        print(f"{_PASS} Credentials — {token_env}: SET")
    else:
        print(f"{_FAIL} Credentials — {token_env}: MISSING")
        print(_credential_hint(token_env))
        ok = False

    return ok


def _check_connectivity(raw: dict, env_vars_ok: bool) -> bool:
    """Optional connectivity check — only if credentials are available."""
    if not env_vars_ok:
        print(f"{_WARN} Connectivity — skipped (credentials missing)")
        return True

    try:
        from jenkins_client import JenkinsClient
        from jenkins_config import load_config

        config = load_config()
        client = JenkinsClient(config)
        if client.test_connection():
            print(f"{_PASS} Connectivity — API reachable, credentials valid")
            return True
        print(f"{_FAIL} Connectivity — API returned error (check credentials and base_url)")
        return False
    except SystemExit:
        print(f"{_FAIL} Connectivity — config/credential resolution failed")
        return False
    except Exception as e:
        print(f"{_FAIL} Connectivity — {e}")
        return False


def _check_repo_detection() -> tuple[bool, str | None]:
    """Check if repo name can be auto-detected from git remote.
    Returns (ok, repo_name)."""
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            print(f"{_WARN} Repo detection — no git remote 'origin' found (use --job flag)")
            return True, None  # warn, not fail

        url = result.stdout.strip()
        repo_name = _parse_repo_name(url)
        if repo_name:
            print(f"{_PASS} Repo detection — {repo_name} (from origin)")
            return True, repo_name
        print(f"{_WARN} Repo detection — could not parse repo name from: {url}")
        print("  Use --job <name> when running scripts")
        return True, None  # warn, not fail

    except FileNotFoundError:
        print(f"{_WARN} Repo detection — git not found (use --job flag)")
        return True, None  # warn, not fail


def _check_job_discovery(raw: dict, repo_name: str | None, creds_ok: bool) -> bool:
    """Search Jenkins API for a job matching the repo name."""
    if not repo_name:
        print(f"{_WARN} Job discovery — skipped (no repo name detected)")
        return True
    if not creds_ok:
        print(f"{_WARN} Job discovery — skipped (credentials missing)")
        return True

    # Check job_cache first
    job_cache = raw.get("job_cache", {})
    if repo_name in job_cache:
        print(f"{_PASS} Job discovery — {repo_name} -> {job_cache[repo_name]} (from job_cache)")
        return True

    # Search API
    try:
        from jenkins_client import JenkinsClient
        from jenkins_config import load_config

        config = load_config()
        client = JenkinsClient(config)
        result = client.find_job(repo_name)
        if result:
            folder, job = result
            path = f"{folder}/{job}" if folder else job
            print(f"{_PASS} Job discovery — found {repo_name} at {path}")
            print(f"  Tip: add to job_cache in {CONFIG_FILENAME} for faster lookups:")
            print(f'    "job_cache": {{ "{repo_name}": "{path}" }}')
            return True
        print(f"{_WARN} Job discovery — no job named '{repo_name}' found in Jenkins")
        print("  Use --folder and --job flags explicitly, or add to job_cache")
        return True  # warn, not fail
    except Exception as e:
        print(f"{_WARN} Job discovery — search failed: {e}")
        return True  # warn, not fail


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Pre-flight checks for jenkins-manager")
    parser.add_argument(
        "--skip-connectivity",
        action="store_true",
        help="Skip API connectivity and discovery checks",
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

    # 3. Credentials
    if config_ok:
        creds_ok = _check_credentials(raw, project_root)
        results.append(creds_ok)
    else:
        creds_ok = False
        results.append(False)

    # 4. Connectivity (optional)
    if not args.skip_connectivity and config_ok:
        results.append(_check_connectivity(raw, creds_ok))

    # 5. Repo detection
    repo_ok, repo_name = _check_repo_detection()
    results.append(repo_ok)

    # 6. Job discovery (optional)
    if not args.skip_connectivity and config_ok:
        results.append(_check_job_discovery(raw, repo_name, creds_ok))

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
