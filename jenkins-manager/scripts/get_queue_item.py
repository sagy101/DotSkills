#!/usr/bin/env python3
"""Check status of a queued Jenkins build."""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from jenkins_client import JenkinsClient
from jenkins_config import load_config, resolve_instance


def _format_timestamp(ts: int) -> str:
    """Format Unix timestamp (ms) to human-readable datetime."""
    dt = datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
    return dt.strftime("%Y-%m-%d %H:%M:%S UTC")


def main() -> None:
    parser = argparse.ArgumentParser(description="Check status of a queued Jenkins build")
    parser.add_argument("--config", help="Path to .jenkins.json (omit to auto-discover)")
    parser.add_argument("--instance", help="Named Jenkins instance (omit to use default)")
    parser.add_argument("--queue-id", type=int, required=True, help="Queue item ID")
    parser.add_argument(
        "--format", choices=["table", "json"], default="table", help="Output format"
    )
    args = parser.parse_args()

    config = load_config(args.config)
    instance = resolve_instance(config, args.instance)
    client = JenkinsClient(instance)

    item = client.get_queue_item(args.queue_id)
    if not item:
        print(f"Queue item {args.queue_id} not found (may have already started or expired).")
        sys.exit(0)

    if args.format == "json":
        print(json.dumps(item, indent=2))
        return

    _print_queue_table(item, args.queue_id)


def _print_queue_table(item: dict, queue_id: int) -> None:
    """Print queue item details in table format."""
    print(f"Queue item #{item.get('id', queue_id)}:")
    print()

    executable = item.get("executable")
    if executable:
        print("  Status     STARTED")
        print(f"  Build      #{executable.get('number', '?')}")
        print(f"  URL        {executable.get('url', '')}")
    elif item.get("stuck"):
        print("  Status     STUCK")
    elif item.get("blocked"):
        print("  Status     BLOCKED")
    elif item.get("buildable"):
        print("  Status     WAITING")
    else:
        print("  Status     QUEUED")

    why = item.get("why")
    if why:
        print(f"  Reason     {why}")

    task = item.get("task", {})
    if task:
        print(f"  Job        {task.get('name', '')}")

    in_queue_since = item.get("inQueueSince")
    if in_queue_since:
        print(f"  Queued at  {_format_timestamp(in_queue_since)}")

    # Causes
    actions = item.get("actions", [])
    for action in actions:
        causes = action.get("causes", [])
        for cause in causes:
            desc = cause.get("shortDescription", "")
            if desc:
                print(f"  Cause      {desc}")


if __name__ == "__main__":
    main()
