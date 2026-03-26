#!/usr/bin/env python3
"""Trigger a Jenkins build with dry-run support."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from jenkins_client import JenkinsClient
from jenkins_config import (
    add_common_args,
    load_config,
    resolve_branch,
    resolve_instance,
    resolve_job_path,
)
from jenkins_redaction import redact_text


def _parse_parameters(param_strings: list[str] | None) -> dict[str, str] | None:
    """Parse key=value parameter strings into a dict."""
    if not param_strings:
        return None
    params = {}
    for p in param_strings:
        if "=" not in p:
            print(f"ERROR: Invalid parameter format: {p} (expected key=value)")
            sys.exit(1)
        key, _, value = p.partition("=")
        params[key.strip()] = value.strip()
    return params or None


def main() -> None:
    parser = argparse.ArgumentParser(description="Trigger a Jenkins build")
    add_common_args(parser)
    parser.add_argument(
        "--parameters",
        nargs="*",
        metavar="KEY=VALUE",
        help="Build parameters (e.g. --parameters ENV=staging VERSION=1.2.3)",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Show what would be triggered without executing"
    )
    args = parser.parse_args()

    config = load_config(args.config)
    instance = resolve_instance(config, args.instance)
    client = JenkinsClient(instance)

    folder, job = resolve_job_path(instance, args.folder, args.job)
    if not job:
        print("ERROR: Could not determine job name.")
        print("Provide --job <name> or set job_cache in .jenkins.json")
        sys.exit(1)

    branch = resolve_branch(instance, args.branch)

    # If no folder, try to discover it
    if not folder and job:
        result = client.find_job(job)
        if result:
            folder, job = result
        else:
            print(f"ERROR: Job '{job}' not found in Jenkins.")
            sys.exit(1)

    parameters = _parse_parameters(args.parameters)

    # Build display info
    job_path = f"{folder}/{job}" if folder else job
    branch_str = f" @ {branch}" if branch else ""

    if args.dry_run:
        print("DRY RUN — would trigger:")
        print(f"  Job:        {job_path}{branch_str}")
        if parameters:
            print("  Parameters:")
            for k, v in parameters.items():
                # Redact parameter values that look like secrets
                redacted_v = redact_text(f"param={v}")
                display_v = redacted_v.split("=", 1)[1] if "=" in redacted_v else v
                print(f"    {k} = {display_v}")
        else:
            print("  Parameters: (none)")
        print()
        print("Remove --dry-run to execute.")
        return

    # Trigger the build
    try:
        client.trigger_build(folder, job, branch, parameters)
        print(f"Build triggered: {job_path}{branch_str}")
        if parameters:
            print(f"  with {len(parameters)} parameter(s)")
        print()
        print("Check status with:")
        print(
            f"  python3 <skill_dir>/scripts/get_status.py --folder {folder} --job {job}"
            f"{' --branch ' + branch if branch else ''}"
        )
    except Exception as e:
        print(f"ERROR: Failed to trigger build: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
