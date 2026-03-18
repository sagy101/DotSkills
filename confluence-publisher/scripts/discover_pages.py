#!/usr/bin/env python3
"""
confluence-publisher skill — Page Discovery

Walks the Confluence tree under root_page_id and builds a manifest by matching
page titles to local markdown files. Useful for bootstrapping a manifest when
pages already exist on Confluence.

Usage:
    python discover_pages.py --config .confluence.json
    python discover_pages.py --config .confluence.json --dry-run
"""

from __future__ import annotations

import argparse
import fnmatch
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from atlassian import Confluence
    from confluence_config import ConfluenceConfig

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from confluence_config import (  # noqa: E402
    add_config_arg,
    connect,
    load_config,
    load_manifest,
    save_manifest,
)
from page_utils import get_all_children, resolve_title  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Discover Confluence pages and build manifest")
    add_config_arg(parser)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be written without saving",
    )
    return parser.parse_args()


def find_md_files(config: ConfluenceConfig) -> dict[str, str]:
    """Find all .md files under docs_dir, returning {relative_path: title}."""
    files: dict[str, str] = {}
    docs_root = config.docs_root

    for md_file in sorted(docs_root.rglob("*.md")):
        rel = str(md_file.relative_to(docs_root))

        excluded = any(fnmatch.fnmatch(rel, pattern) for pattern in config.exclude_patterns)
        if excluded:
            continue

        content = md_file.read_text(encoding="utf-8")
        title = resolve_title(rel, content, config)
        files[rel] = title

    return files


def walk_confluence_tree(confluence: Confluence, page_id: str) -> list[tuple[str, str, str]]:
    """Recursively walk Confluence tree, returning list of (id, title, parent_id)."""
    pages: list[tuple[str, str, str]] = []
    children = get_all_children(confluence, page_id)
    for child in children:
        cid = child["id"]
        ctitle = child["title"]
        pages.append((cid, ctitle, page_id))
        pages.extend(walk_confluence_tree(confluence, cid))
    return pages


def match_pages_to_files(
    confluence_pages: list[tuple[str, str, str | None]], local_files: dict[str, str]
) -> dict[str, dict[str, Any]]:
    """Match Confluence pages to local files by title similarity.
    Returns {relative_path: {id, title, parent_id}}."""
    title_to_page: dict[str, tuple[str, str, str | None]] = {}
    for pid, ptitle, pparent in confluence_pages:
        normalized = ptitle.strip().lower()
        title_to_page[normalized] = (pid, ptitle, pparent)

    matches: dict[str, dict[str, Any]] = {}
    for rel_path, local_title in local_files.items():
        normalized = local_title.strip().lower()
        if normalized in title_to_page:
            pid, ptitle, pparent = title_to_page[normalized]
            matches[rel_path] = {
                "id": pid,
                "title": ptitle,
                "parent_id": pparent,
                "last_published": None,
            }

    return matches


def main():
    args = parse_args()
    config = load_config(args.config)

    confluence = connect(config)

    print(f"Discovering pages under root {config.root_page_id}...")
    print(f"  URL:      {config.confluence_url}")
    print(f"  Space:    {config.space_key}")
    print(f"  Docs dir: {config.docs_root}")

    # Get root page
    root = confluence.get_page_by_id(config.root_page_id)
    if not root:
        print(f"ERROR: Root page {config.root_page_id} not found")
        sys.exit(1)

    print(f"  Root:     {root['title']}")
    print()

    # Walk Confluence tree
    confluence_pages = [(config.root_page_id, root["title"], None)]
    confluence_pages.extend(walk_confluence_tree(confluence, config.root_page_id))
    print(f"Found {len(confluence_pages)} pages on Confluence")

    # Find local files
    local_files = find_md_files(config)
    print(f"Found {len(local_files)} markdown files locally")
    print()

    # Match
    matches = match_pages_to_files(confluence_pages, local_files)

    # Merge with existing manifest
    existing = load_manifest(config)
    merged = {**existing, **matches}

    print(f"{'Status':<12} {'File':<50} {'Confluence Title':<35} {'Page ID'}")
    print("-" * 130)

    for rel_path, local_title in sorted(local_files.items()):
        if rel_path in matches:
            info = matches[rel_path]
            status = "MATCHED"
            print(f"{status:<12} {rel_path:<50} {info['title']:<35} {info['id']}")
        else:
            status = "UNMATCHED"
            print(f"{status:<12} {rel_path:<50} {local_title:<35} (no match)")

    # Show Confluence pages not matched to local files
    matched_ids = {info["id"] for info in matches.values()}
    print()
    print("--- Confluence pages not matched to local files ---")
    unmatched_count = 0
    for pid, ptitle, _pparent in confluence_pages:
        if pid not in matched_ids:
            print(f"  {ptitle} (id={pid})")
            unmatched_count += 1
    if unmatched_count == 0:
        print("  (none)")

    print()
    print(
        f"Summary: {len(matches)} matched, "
        f"{len(local_files) - len(matches)} unmatched local files, "
        f"{unmatched_count} unmatched Confluence pages"
    )

    if args.dry_run:
        print("\n[DRY RUN] Manifest not saved.")
    else:
        save_manifest(config, merged)
        print(f"\nManifest saved to {config.manifest_file}")
        print(f"  Total entries: {len(merged)}")


if __name__ == "__main__":
    main()
