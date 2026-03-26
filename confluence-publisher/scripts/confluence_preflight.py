#!/usr/bin/env python3
"""Pre-flight checks for confluence-publisher skill.

Verifies Python version, venv/dependencies, config file, credentials, and
optional connectivity. Run this before any other script.

Exits 0 if all checks pass, 1 if any fail.

Usage:
    python3 confluence_preflight.py
    python3 confluence_preflight.py --skip-connectivity
"""

import json
import os
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from confluence_config import (  # noqa: E402
    CONFIG_FILENAME,
    _credential_hint,
    _deep_merge,
    _find_global_config,
    _find_project_config,
    load_env_file,
)

_PASS = "[PASS]"
_FAIL = "[FAIL]"
_WARN = "[WARN]"

SKILL_DIR = SCRIPT_DIR.parent
VENV_PYTHON = SKILL_DIR / ".venv" / "bin" / "python"
REQUIRED_IMPORTS = ["atlassian", "markdown"]


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------


def _check_python() -> bool:
    """Check Python version >= 3.10."""
    major, minor = sys.version_info[:2]
    if major >= 3 and minor >= 10:
        print(f"{_PASS} Python {major}.{minor}")
        return True
    print(f"{_FAIL} Python {major}.{minor} — requires 3.10+")
    return False


def _check_venv() -> bool:
    """Check that the skill venv exists and has required dependencies."""
    if not VENV_PYTHON.exists():
        print(f"{_FAIL} Virtual environment — {VENV_PYTHON} not found")
        setup_script = SCRIPT_DIR / "confluence_setup_env.py"
        print(f"  Run: python3 {setup_script}")
        return False

    # Check imports inside the venv
    import_check = "; ".join(f"import {mod}" for mod in REQUIRED_IMPORTS)
    try:
        result = subprocess.run(
            [str(VENV_PYTHON), "-c", import_check],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode == 0:
            print(f"{_PASS} Virtual environment — dependencies OK ({', '.join(REQUIRED_IMPORTS)})")
            return True
        print(f"{_FAIL} Virtual environment — missing dependencies")
        print(
            f"  {result.stderr.strip().splitlines()[-1] if result.stderr.strip() else 'unknown error'}"
        )
        setup_script = SCRIPT_DIR / "confluence_setup_env.py"
        print(f"  Run: python3 {setup_script}")
        return False
    except subprocess.TimeoutExpired:
        print(f"{_WARN} Virtual environment — import check timed out")
        return True
    except Exception as e:
        print(f"{_FAIL} Virtual environment — {e}")
        return False


def _check_config() -> tuple[bool, dict, Path | None]:
    """Check config file exists and is valid JSON with required fields.
    Returns (ok, merged_raw, project_root)."""
    project_cfg = _find_project_config()
    global_cfg = _find_global_config()

    if not project_cfg and not global_cfg:
        print(f"{_FAIL} Config — {CONFIG_FILENAME} not found in any parent directory or ~/")
        print()
        print(f"  Create ~/.confluence.json (global) or ./{CONFIG_FILENAME} (project) with:")
        print(
            json.dumps(
                {
                    "confluence_url": "https://mycompany.atlassian.net/wiki",
                    "space_key": "DOCS",
                    "root_page_id": "123456",
                    "credentials": {
                        "username_env": "CONFLUENCE_EMAIL",
                        "token_env": "CONFLUENCE_TOKEN",
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

    # Check required fields
    required = ["confluence_url", "space_key", "root_page_id"]
    missing = [f for f in required if f not in raw or not str(raw[f]).strip()]
    if missing:
        print(f"{_FAIL} Config — missing required field(s): {', '.join(missing)}")
        return False, raw, project_root

    url = raw["confluence_url"]
    if not url.startswith("https://"):
        print(f"{_FAIL} Config — confluence_url must use HTTPS (got: {url})")
        return False, raw, project_root

    print(
        f"{_PASS} Config — space: {raw['space_key']}, root_page_id: {raw['root_page_id']} ({', '.join(sources)})"
    )
    return True, raw, project_root


def _check_credentials(raw: dict, project_root: Path | None) -> bool:
    """Check credential env vars are set. Never prints values."""
    creds = raw.get("credentials", {})
    username_env = creds.get("username_env", "CONFLUENCE_EMAIL")
    token_env = creds.get("token_env", "CONFLUENCE_TOKEN")

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
                env_path = None
        else:
            env_path = None
        if env_path and env_path.exists():
            env_vars = load_env_file(env_path)
        elif env_path and not env_path.exists():
            print(f"{_WARN} env_file not found: {env_path}")

    email = env_vars.get(username_env) or os.environ.get(username_env)
    token = env_vars.get(token_env) or os.environ.get(token_env)

    ok = True
    if email:
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


def _check_connectivity(raw: dict, creds_ok: bool) -> bool:
    """Optional connectivity check — test API access and root page."""
    if not creds_ok:
        print(f"{_WARN} Connectivity — skipped (credentials missing)")
        return True

    if not VENV_PYTHON.exists():
        print(f"{_WARN} Connectivity — skipped (venv not available)")
        return True

    try:
        from confluence_config import connect, load_config

        config = load_config()
        confluence = connect(config)

        # Test space access
        space = confluence.get_space(config.space_key)
        if not space or (isinstance(space, dict) and "statusCode" in space):
            print(f"{_FAIL} Connectivity — cannot access space '{config.space_key}'")
            if isinstance(space, dict) and space.get("statusCode") == 401:
                print("  Bad credentials — check your API token")
            return False

        # Test root page access
        root = confluence.get_page_by_id(config.root_page_id, expand="version")
        if not root or (isinstance(root, dict) and "statusCode" in root):
            print(f"{_FAIL} Connectivity — root page {config.root_page_id} not found")
            print("  Check root_page_id in .confluence.json — it may be wrong or deleted")
            return False

        root_title = root.get("title", "<unknown>") if isinstance(root, dict) else "<unknown>"
        print(
            f'{_PASS} Connectivity — API OK, root page: "{root_title}" (id={config.root_page_id})'
        )
        return True

    except SystemExit:
        print(f"{_FAIL} Connectivity — config/credential resolution failed")
        return False
    except Exception as e:
        print(f"{_FAIL} Connectivity — {e}")
        return False


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Pre-flight checks for confluence-publisher")
    parser.add_argument(
        "--skip-connectivity", action="store_true", help="Skip the API connectivity check"
    )
    args = parser.parse_args()

    print("Confluence Publisher — Pre-flight Checks")
    print("=" * 42)
    print()

    results = []

    # 1. Python version
    results.append(_check_python())

    # 2. Virtual environment and dependencies
    results.append(_check_venv())

    # 3. Config file
    config_ok, raw, project_root = _check_config()
    results.append(config_ok)

    # 4. Credentials
    if config_ok:
        creds_ok = _check_credentials(raw, project_root)
        results.append(creds_ok)
    else:
        creds_ok = False
        results.append(False)

    # 5. Connectivity (optional)
    if not args.skip_connectivity and config_ok:
        results.append(_check_connectivity(raw, creds_ok))

    # Summary
    passed = sum(results)
    total = len(results)
    print()
    print("=" * 42)
    if all(results):
        print(f"All {total} checks passed. Ready to use.")
        sys.exit(0)
    else:
        failed = total - passed
        print(f"{passed}/{total} passed, {failed} failed. Fix the issues above.")
        sys.exit(1)


if __name__ == "__main__":
    main()
