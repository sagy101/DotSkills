#!/usr/bin/env python3
"""Pre-flight checks for team-notify skill.

Verifies Python version, requests availability, config file, and webhook
environment variables. Run this before notify.py. Exits 0 if all pass.
"""

import json
import os
import sys
from pathlib import Path

_PASS = "[PASS]"
_FAIL = "[FAIL]"
_WARN = "[WARN]"

CONFIG_FILENAME = ".notify.json"

MINIMAL_CONFIG_EXAMPLE = json.dumps(
    {
        "channels": {
            "slack": {"webhook_env": "SLACK_WEBHOOK_URL"},
        },
        "default_channel": "slack",
    },
    indent=2,
)


# ---------------------------------------------------------------------------
# Config helpers (inline — no shared module dependency)
# ---------------------------------------------------------------------------


def _deep_merge(base: dict, override: dict) -> dict:
    result = dict(base)
    for k, v in override.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result


def _find_project_config() -> Path | None:
    here = Path.cwd()
    for directory in [here, *here.parents]:
        candidate = directory / CONFIG_FILENAME
        if candidate.exists():
            return candidate
    return None


def _find_global_config() -> Path | None:
    candidate = Path.home() / CONFIG_FILENAME
    return candidate if candidate.exists() else None


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------


def _check_python() -> bool:
    major, minor = sys.version_info[:2]
    if major >= 3 and minor >= 8:
        print(f"{_PASS} Python {major}.{minor}")
        return True
    print(f"{_FAIL} Python {major}.{minor} — requires 3.8+")
    return False


def _check_requests() -> bool:
    try:
        import urllib.request  # noqa: F401 — stdlib always available
        print(f"{_PASS} HTTP client — urllib (stdlib)")
        return True
    except ImportError:
        print(f"{_FAIL} HTTP client — urllib not available (stdlib issue)")
        return False


def _check_config() -> tuple[bool, dict]:
    project_cfg = _find_project_config()
    global_cfg = _find_global_config()

    if not project_cfg and not global_cfg:
        print(f"{_FAIL} Config — {CONFIG_FILENAME} not found in any parent directory or ~/")
        print()
        print(f"  Create ~/.notify.json with:")
        print("  " + MINIMAL_CONFIG_EXAMPLE.replace("\n", "\n  "))
        return False, {}

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
        return False, {}

    raw = _deep_merge(global_raw, project_raw)

    channels = raw.get("channels", {})
    if not channels:
        print(f"{_FAIL} Config — 'channels' section is empty or missing")
        return False, raw

    default_channel = raw.get("default_channel", "")
    channel_list = ", ".join(channels.keys())
    print(f"{_PASS} Config — channels: {channel_list} | default: {default_channel or '(not set)'} ({', '.join(sources)})")
    return True, raw


def _check_credentials(raw: dict) -> bool:
    channels = raw.get("channels", {})
    if not channels:
        print(f"{_WARN} Credentials — skipped (no channels configured)")
        return True

    all_ok = True
    for name, ch_cfg in channels.items():
        env_var = ch_cfg.get("webhook_env", "")
        if not env_var:
            print(f"{_FAIL} Credentials — channels.{name}.webhook_env is not set in config")
            all_ok = False
            continue

        value = os.environ.get(env_var, "")
        if value:
            print(f"{_PASS} Credentials — {env_var} ({name}): SET")
        else:
            print(f"{_FAIL} Credentials — {env_var} ({name}): MISSING")
            print(f"  Set it: export {env_var}=\"<your-{name}-webhook-url>\"")
            all_ok = False

    return all_ok


def _check_default_channel(raw: dict) -> bool:
    channels = raw.get("channels", {})
    default_channel = raw.get("default_channel", "")

    if not default_channel:
        print(f"{_WARN} Default channel — 'default_channel' not set (use --channel flag each time)")
        return True

    if default_channel not in channels and default_channel != "all":
        print(f"{_FAIL} Default channel — '{default_channel}' not found in channels ({list(channels.keys())})")
        return False

    print(f"{_PASS} Default channel — '{default_channel}'")
    return True


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Pre-flight checks for team-notify")
    parser.add_argument("--config", help="Path to .notify.json config file")
    args = parser.parse_args()

    if args.config:
        # Change to the config's directory so _find_project_config finds it
        p = Path(args.config)
        if p.exists():
            os.chdir(p.parent)

    print("Team Notify — Pre-flight Checks")
    print("=" * 40)
    print()

    results = []

    results.append(_check_python())
    results.append(_check_requests())

    config_ok, raw = _check_config()
    results.append(config_ok)

    if config_ok:
        results.append(_check_default_channel(raw))
        results.append(_check_credentials(raw))

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
