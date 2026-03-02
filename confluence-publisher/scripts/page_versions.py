#!/usr/bin/env python3
"""
confluence-publisher skill — Page Version Management

List version history, fetch a specific version's content, or revert a page
to a previous version.

Usage:
    # List version history
    python page_versions.py --config .confluence.json \
        --page 1079706804 --list

    # List more versions
    python page_versions.py --config .confluence.json \
        --page 1079706804 --list --limit 50

    # Fetch a specific version's HTML content
    python page_versions.py --config .confluence.json \
        --page 1079706804 --fetch 56

    # Fetch and save to file
    python page_versions.py --config .confluence.json \
        --page 1079706804 --fetch 56 --output /tmp/page_v56.html

    # Fetch as plain text (HTML tags stripped)
    python page_versions.py --config .confluence.json \
        --page 1079706804 --fetch 56 --output /tmp/page_v56.txt --text

    # Revert to a previous version (requires --confirm)
    python page_versions.py --config .confluence.json \
        --page 1079706804 --revert 56 --confirm

    # Revert dry run (show what would happen)
    python page_versions.py --config .confluence.json \
        --page 1079706804 --revert 56
"""

import argparse
import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from config_loader import load_config, extract_page_id
from page_ops import (
    fetch_page,
    list_versions,
    update_page_body,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Manage Confluence page versions: list, fetch, or revert"
    )
    parser.add_argument(
        "--config",
        help="Path to .confluence.json (default: auto-detect from cwd up)",
    )
    parser.add_argument(
        "--page",
        required=True,
        help="Page ID, full URL, or tiny link",
    )

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--list",
        action="store_true",
        help="List version history",
    )
    group.add_argument(
        "--fetch",
        type=int,
        metavar="VERSION",
        help="Fetch content of a specific version",
    )
    group.add_argument(
        "--revert",
        type=int,
        metavar="VERSION",
        help="Revert page to a previous version",
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=25,
        help="Number of versions to list (default: 25)",
    )
    parser.add_argument(
        "--output",
        help="Save fetched content to file instead of stdout",
    )
    parser.add_argument(
        "--text",
        action="store_true",
        help="Strip HTML tags when fetching (plain text output)",
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Required flag to actually execute a revert",
    )
    parser.add_argument(
        "--message",
        help="Version message for the revert",
    )
    return parser.parse_args()


def cmd_list(config, page_id: str, limit: int) -> None:
    """List version history."""
    versions = list_versions(config, page_id, limit=limit)

    if not versions:
        print("No versions found.")
        return

    # Fetch current page title
    current = fetch_page(config, page_id)
    print(f"Version history for: {current.title} (id={page_id})")
    print(f"Current version: {current.version}")
    print()

    # Table header
    print(f"{'Ver':>5}  {'Author':<25}  {'Date':<25}  Message")
    print(f"{'---':>5}  {'---':<25}  {'---':<25}  ---")

    for v in versions:
        date_short = v.when[:19].replace("T", " ") if v.when else ""
        msg = v.message[:60] if v.message else ""
        print(f"{v.number:>5}  {v.by:<25}  {date_short:<25}  {msg}")

    print(f"\nShowing {len(versions)} of {current.version} version(s)")


def cmd_fetch(config, page_id: str, version: int, output: str | None, text: bool) -> None:
    """Fetch content of a specific version."""
    print(f"Fetching version {version} of page {page_id}...")
    snapshot = fetch_page(config, page_id, version=version)

    print(f"  Title:   {snapshot.title}")
    print(f"  Version: {snapshot.version}")
    print(f"  Author:  {snapshot.by}")
    print(f"  Date:    {snapshot.when}")
    print(f"  Size:    {len(snapshot.html)} chars")

    content = snapshot.html
    if text:
        content = re.sub(r"<[^>]+>", "", content).strip()
        content = re.sub(r"\s+", " ", content)

    if output:
        Path(output).write_text(content, encoding="utf-8")
        fmt = "text" if text else "HTML"
        print(f"\nSaved {fmt} content to {output} ({len(content)} chars)")
    else:
        print(f"\n--- Content (v{snapshot.version}) ---")
        print(content)


def cmd_revert(
    config, page_id: str, version: int, confirm: bool, message: str | None,
) -> None:
    """Revert page to a previous version."""
    # Fetch the target version
    print(f"Fetching version {version} of page {page_id}...")
    old_snap = fetch_page(config, page_id, version=version)

    # Fetch current version
    current = fetch_page(config, page_id)

    print("\nRevert plan:")
    print(f"  Page:    {current.title} (id={page_id})")
    print(f"  Current: v{current.version} by {current.by} ({current.when[:19]})")
    print(f"  Target:  v{old_snap.version} by {old_snap.by} ({old_snap.when[:19]})")
    print(f"  Size:    {len(current.html)} -> {len(old_snap.html)} chars")

    if not confirm:
        print("\n[DRY RUN] To execute this revert, add --confirm")
        print(f"  This will create version {current.version + 1} with the content from v{version}.")
        sys.exit(0)

    # Execute revert
    version_msg = message or f"Reverted to version {version}"
    new_version = update_page_body(
        config, page_id, old_snap.title, old_snap.html, message=version_msg,
    )

    print(f"\nReverted to version {version}")
    print(f"  New version: {new_version}")
    print(f"  {config.confluence_url}/pages/{page_id}")


def main():
    args = parse_args()
    config = load_config(args.config)
    page_id = extract_page_id(args.page)

    if args.list:
        cmd_list(config, page_id, args.limit)
    elif args.fetch is not None:
        cmd_fetch(config, page_id, args.fetch, args.output, args.text)
    elif args.revert is not None:
        cmd_revert(config, page_id, args.revert, args.confirm, args.message)


if __name__ == "__main__":
    main()
