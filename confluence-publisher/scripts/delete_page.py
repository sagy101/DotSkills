#!/usr/bin/env python3
"""
confluence-publisher skill — Delete Confluence Pages

Deletes one or more Confluence pages by manifest file key or page ID,
and removes the corresponding manifest entries.

Usage:
    # Delete by manifest file path
    python delete_page.py --config .confluence.json --file plan/old-design.md

    # Delete multiple files
    python delete_page.py --config .confluence.json \
        --file "plan/old-design.md,plan/deprecated.md"

    # Delete by page ID (not in manifest)
    python delete_page.py --config .confluence.json --page-id 123456

    # Dry run — show what would be deleted without actually deleting
    python delete_page.py --config .confluence.json --file plan/old-design.md --dry-run
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from atlassian import Confluence

# ---------------------------------------------------------------------------
# Ensure script dir is on path for shared module imports
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from confluence_config import (  # noqa: E402
    add_config_arg,
    connect,
    load_config,
    load_manifest,
    save_manifest,
)

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Delete Confluence pages and remove manifest entries"
    )
    add_config_arg(parser)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--file",
        help="Manifest file key(s) to delete, comma-separated",
    )
    group.add_argument(
        "--page-id",
        help="Confluence page ID to delete directly (no manifest lookup)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be deleted without deleting",
    )
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Delete logic
# ---------------------------------------------------------------------------


def delete_page(confluence: Confluence, page_id: str, title: str, dry_run: bool) -> bool:
    """Delete a single Confluence page. Returns True on success."""
    if dry_run:
        print(f"  [DRY RUN] Would delete: {title} (id={page_id})")
        return True

    try:
        confluence.remove_page(page_id)
        print(f"  Deleted: {title} (id={page_id})")
        return True
    except Exception as e:
        print(f"  ERROR deleting page {page_id} ({title}): {e}")
        return False


def _delete_by_page_id(
    confluence: Confluence, page_id: str, manifest: dict[str, Any], dry_run: bool
) -> tuple[list[str], list[str]]:
    """Delete a page by its Confluence ID. Returns (deleted_keys, failed)."""
    page = confluence.get_page_by_id(page_id)
    if not page:
        print(f"ERROR: Page {page_id} not found on Confluence")
        sys.exit(1)

    title = page.get("title", f"id={page_id}")
    print(f"Deleting page: {title} (id={page_id})")

    if not delete_page(confluence, page_id, title, dry_run):
        return [], [page_id]

    matched = [key for key, entry in manifest.items() if str(entry.get("id")) == str(page_id)]
    return matched, []


def _delete_by_file_keys(
    confluence: Confluence, file_keys: list[str], manifest: dict[str, Any], dry_run: bool
) -> tuple[list[str], list[str]]:
    """Delete pages by manifest file keys. Returns (deleted_keys, failed)."""
    deleted_keys = []
    failed = []

    for file_key in file_keys:
        if file_key not in manifest:
            print(f"  WARNING: '{file_key}' not found in manifest — skipping")
            failed.append(file_key)
            continue

        entry = manifest[file_key]
        page_id = str(entry["id"])
        title = entry.get("title", file_key)

        if delete_page(confluence, page_id, title, dry_run):
            deleted_keys.append(file_key)
        else:
            failed.append(file_key)

    return deleted_keys, failed


def main():
    args = parse_args()

    config = load_config(args.config)
    manifest = load_manifest(config)
    confluence = connect(config)

    # Test connection
    try:
        confluence.get_space(config.space_key)
    except Exception as e:
        print(f"ERROR: Cannot connect to Confluence space {config.space_key}: {e}")
        sys.exit(1)

    print(f"  Target: {config.confluence_url} / {config.space_key}")
    print(f"  Manifest: {len(manifest)} pages known")

    if args.page_id:
        deleted_keys, failed = _delete_by_page_id(confluence, args.page_id, manifest, args.dry_run)
    else:
        file_keys = [f.strip() for f in args.file.split(",") if f.strip()]
        print(f"Deleting {len(file_keys)} page(s)")
        print()
        deleted_keys, failed = _delete_by_file_keys(confluence, file_keys, manifest, args.dry_run)

    # Update manifest
    if deleted_keys and not args.dry_run:
        for key in deleted_keys:
            manifest.pop(key, None)
        save_manifest(config, manifest)

    # Summary
    print()
    if args.dry_run:
        print(f"[DRY RUN] Would delete {len(deleted_keys)} page(s), {len(failed)} skipped/failed")
    else:
        print(f"Deleted {len(deleted_keys)} page(s), {len(failed)} failed")
        if deleted_keys:
            print(f"Manifest updated: {len(manifest)} pages remaining")


if __name__ == "__main__":
    main()
