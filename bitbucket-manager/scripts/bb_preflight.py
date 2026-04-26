#!/usr/bin/env python3
"""Pre-flight checks for bitbucket-manager skill.

Verifies Python version, config file, credentials, and repo auto-detection.
Run this before any other script. Exits 0 if all checks pass, 1 if any fail.
"""

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from bb_config import (
    CONFIG_FILENAME,
    AuthResolutionError,
    BitbucketConfig,
    _deep_merge,
    _find_global_config,
    _find_project_config,
    _parse_workspace_and_repo,
    add_common_args,
    load_config,
    resolve_auth_candidates,
    resolve_workspace,
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
        print("  Create ~/.bitbucket.json with:")
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
    if "workspace" not in raw or not raw["workspace"].strip():
        print(f"{_FAIL} Config — missing required field 'workspace'")
        if not project_cfg:
            print(
                f"  Hint: create a project-level {CONFIG_FILENAME} or add workspace to ~/.bitbucket.json"
            )
        return False, raw, project_root

    print(f"{_PASS} Config — workspace: {raw['workspace']} ({', '.join(sources)})")
    return True, raw, project_root


def _check_credentials(config: BitbucketConfig, workspace: str, repo_slug: str | None) -> bool:
    """Check whether at least one usable auth path exists for the target repo."""
    try:
        candidates, _ = resolve_auth_candidates(config, workspace, repo_slug)
    except AuthResolutionError as e:
        print(f"{_FAIL} Credentials — {e}")
        return False

    for candidate in candidates:
        if candidate.source == "basic":
            print(
                f"{_PASS} Credentials — basic auth available via "
                f"{config.email_env} + {config.token_env}"
            )
        elif candidate.source == "repo_token":
            print(
                f"{_PASS} Credentials — repo token available via {candidate.token_env} "
                f"for {candidate.repo_key}"
            )
        else:
            print(f"{_PASS} Credentials — bearer auth available via {candidate.token_env}")
    return True


def _check_repo_detection(raw: dict, explicit_repo: str | None = None) -> tuple[bool, str | None]:
    """Check if repo slug can be auto-detected from git remote."""
    if explicit_repo:
        print(f"{_PASS} Repo detection — {raw.get('workspace', '?')}/{explicit_repo} (from --repo)")
        return True, explicit_repo
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            print(f"{_WARN} Repo detection — no git remote 'origin' found (use --repo flag)")
            return True, None  # warn, not fail

        url = result.stdout.strip()
        workspace, repo = _parse_workspace_and_repo(url)
        if repo:
            cfg_workspace = raw.get("workspace", "")
            workspace_match = (
                ""
                if not cfg_workspace or cfg_workspace == workspace
                else f" (remote workspace '{workspace}' differs from config '{cfg_workspace}')"
            )
            print(f"{_PASS} Repo detection — {workspace}/{repo} (from origin){workspace_match}")
            return True, repo
        print(f"{_WARN} Repo detection — could not parse Bitbucket repo from: {url}")
        print("  Use --repo <slug> when running scripts")
        return True, None  # warn, not fail

    except FileNotFoundError:
        print(f"{_WARN} Repo detection — git not found (use --repo flag)")
        return True, None  # warn, not fail


def _check_connectivity(
    config: BitbucketConfig, workspace: str, repo_slug: str | None, env_vars_ok: bool
) -> bool:
    """Optional connectivity check — only if credentials are available."""
    if not env_vars_ok:
        print(f"{_WARN} Connectivity — skipped (credentials missing)")
        return True

    # Import here to avoid failing on credential resolution during other checks
    try:
        from bb_client import BitbucketClient

        client = BitbucketClient(config)
        ok, detail = client.test_connection(workspace, repo_slug)
        if ok:
            print(f"{_PASS} Connectivity — {detail or 'API reachable, credentials valid'}")
            return True
        if detail:
            print(f"{_FAIL} Connectivity — {detail}")
        else:
            print(f"{_FAIL} Connectivity — API returned error (check credentials and target repo)")
        return False
    except SystemExit:
        print(f"{_FAIL} Connectivity — config/credential resolution failed")
        return False
    except Exception as e:
        print(f"{_FAIL} Connectivity — {e}")
        return False


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Pre-flight checks for bitbucket-manager")
    add_common_args(parser)
    parser.add_argument(
        "--skip-connectivity", action="store_true", help="Skip the API connectivity check"
    )
    args = parser.parse_args()

    print("Bitbucket Manager — Pre-flight Checks")
    print("=" * 40)
    print()

    results = []

    # 1. Python version
    results.append(_check_python())

    # 2. Config file
    config_ok, raw, project_root = _check_config()
    results.append(config_ok)
    config = None
    workspace = raw.get("workspace", "")
    repo_slug: str | None = args.repo
    repo_detection_ok = True

    # 3. Credentials
    if config_ok:
        config = load_config(args.config)
        workspace = resolve_workspace(config, args.workspace)
        repo_detection_ok, repo_slug = _check_repo_detection(raw, args.repo)
        creds_ok = _check_credentials(config, workspace, repo_slug)
        results.append(creds_ok)
    else:
        creds_ok = False
        results.append(False)

    # 4. Repo detection
    if config_ok:
        results.append(repo_detection_ok)

    # 5. Connectivity (optional)
    if not args.skip_connectivity and config_ok and config is not None:
        results.append(_check_connectivity(config, workspace, repo_slug, creds_ok))

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
