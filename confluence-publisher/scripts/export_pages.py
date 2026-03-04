#!/usr/bin/env python3
"""
confluence-publisher skill — Export from Confluence

Fetches Confluence pages and converts them to local markdown files.
Supports exporting a single page, all manifest entries, or the full
tree under root_page_id.

Usage:
    # Export a single page by ID or URL
    python export_pages.py --config .confluence.json --page 123456
    python export_pages.py --config .confluence.json \
        --page https://mycompany.atlassian.net/wiki/spaces/DOCS/pages/123456/My+Page

    # Export all pages in the manifest
    python export_pages.py --config .confluence.json --manifest

    # Export full tree under root_page_id (discovers and exports everything)
    python export_pages.py --config .confluence.json --tree

    # Dry run — show what would be exported without writing files
    python export_pages.py --config .confluence.json --tree --dry-run
"""

import argparse
import re
import sys
from pathlib import Path
from typing import Optional

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from config_loader import (
    add_config_arg,
    load_config,
    connect,
    load_manifest,
    save_manifest,
    ensure_deps,
)
from page_utils import get_all_children, extract_page_id

ensure_deps({"atlassian-python-api": "atlassian", "markdownify": "markdownify"})

from atlassian import Confluence  # noqa: E402
from markdownify import markdownify as md_convert  # noqa: E402
from transforms import preprocess_confluence_storage  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export Confluence pages to local markdown"
    )
    add_config_arg(parser)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--page",
        help="Single page ID or Confluence URL to export",
    )
    group.add_argument(
        "--manifest",
        action="store_true",
        help="Export all pages listed in the manifest",
    )
    group.add_argument(
        "--tree",
        action="store_true",
        help="Export full page tree under root_page_id",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be exported without writing files",
    )
    parser.add_argument(
        "--output", "-o",
        help="Output file path (only for --page mode, default: stdout)",
    )
    return parser.parse_args()


def html_to_markdown(html_content: str) -> str:
    """Convert Confluence HTML storage format to markdown."""
    # Preprocess specific Confluence macros (like code blocks)
    html_content = preprocess_confluence_storage(html_content)

    markdown_content = md_convert(
        html_content,
        heading_style="atx",
        bullets="-",
    )
    markdown_content = re.sub(r"\n{3,}", "\n\n", markdown_content)
    return markdown_content.strip()


def fetch_page(confluence: Confluence, page_id: str) -> Optional[dict]:
    """Fetch a single page with its content. Returns dict with title, html, markdown."""
    page = confluence.get_page_by_id(
        page_id=page_id,
        expand="body.storage,version,space,ancestors",
    )
    if not page:
        return None

    html_content = page["body"]["storage"]["value"]
    return {
        "id": page_id,
        "title": page["title"],
        "space": page.get("space", {}).get("key", ""),
        "markdown": html_to_markdown(html_content),
        "version": page["version"]["number"],
    }


def get_children(confluence: Confluence, page_id: str) -> list:
    """Get child pages of a given page."""
    children = get_all_children(confluence, page_id)
    return [(c["id"], c["title"]) for c in children]


def walk_tree(confluence: Confluence, page_id: str) -> list:
    """Walk full tree under page_id. Returns list of (id, title, parent_id)."""
    pages = []
    children = get_children(confluence, page_id)
    for child_id, child_title in children:
        pages.append((child_id, child_title, page_id))
        pages.extend(walk_tree(confluence, child_id))
    return pages


def title_to_filename(title: str) -> str:
    """Convert a page title to a safe filename."""
    name = title.lower()
    name = re.sub(r"[^\w\s-]", "", name)
    name = re.sub(r"[\s]+", "-", name.strip())
    return name + ".md"


def export_single_page(confluence, page_ref, output_path, dry_run):
    """Export a single page by ID or URL."""
    page_id = extract_page_id(page_ref)
    print(f"Fetching page {page_id}...")

    result = fetch_page(confluence, page_id)
    if not result:
        print(f"ERROR: Page {page_id} not found")
        sys.exit(1)

    print(f"  Title:   {result['title']}")
    print(f"  Space:   {result['space']}")
    print(f"  Version: {result['version']}")

    if dry_run:
        print(f"\n[DRY RUN] Would export: {result['title']}")
        return

    if output_path:
        Path(output_path).write_text(result["markdown"] + "\n", encoding="utf-8")
        print(f"  Saved to: {output_path}")
    else:
        print("\n--- MARKDOWN CONTENT ---\n")
        print(result["markdown"])


def export_from_manifest(confluence, config, manifest, dry_run):
    """Export all pages listed in the manifest."""
    if not manifest:
        print("ERROR: Manifest is empty. Nothing to export.")
        sys.exit(1)

    print(f"Exporting {len(manifest)} manifest entries...")
    exported = 0
    failed = 0

    for rel_path, info in sorted(manifest.items()):
        page_id = info["id"]
        result = fetch_page(confluence, page_id)

        if not result:
            print(f"  FAILED  {rel_path}: page {page_id} not found")
            failed += 1
            continue

        file_path = config.docs_root / rel_path
        if dry_run:
            print(f"  EXPORT  {rel_path} <- \"{result['title']}\" (id={page_id})")
        else:
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(result["markdown"] + "\n", encoding="utf-8")
            print(f"  SAVED   {rel_path} <- \"{result['title']}\"")
        exported += 1

    print(f"\nSummary: {exported} exported, {failed} failed")


def export_tree(confluence, config, manifest, dry_run):
    """Export full tree under root_page_id."""
    root_id = config.root_page_id
    root = fetch_page(confluence, root_id)
    if not root:
        print(f"ERROR: Root page {root_id} not found")
        sys.exit(1)

    print(f"Exporting tree under: {root['title']} (id={root_id})")

    # Build tree
    tree_pages = [(root_id, root["title"], None)]
    tree_pages.extend(walk_tree(confluence, root_id))
    print(f"Found {len(tree_pages)} pages\n")

    # Build reverse lookup from manifest (id → rel_path)
    id_to_path = {info["id"]: rel_path for rel_path, info in manifest.items()}

    # Build parent_id → directory mapping for generating paths
    id_to_dir = {root_id: Path(".")}
    exported = 0
    new_manifest_entries = {}

    for page_id, title, parent_id in tree_pages:
        # Determine output path
        if page_id in id_to_path:
            rel_path = id_to_path[page_id]
        else:
            parent_dir = id_to_dir.get(parent_id, Path("."))
            filename = title_to_filename(title)
            rel_path = str(parent_dir / filename)

        # Track directory for children — use the file's stem as subdirectory
        # so children of "child-a.md" go under "child-a/" not "."
        id_to_dir[page_id] = Path(rel_path).with_suffix("")

        result = fetch_page(confluence, page_id)
        if not result:
            print(f"  FAILED  {rel_path}: page {page_id} not found")
            continue

        file_path = config.docs_root / rel_path
        if dry_run:
            print(f"  EXPORT  {rel_path} <- \"{title}\" (id={page_id})")
        else:
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(result["markdown"] + "\n", encoding="utf-8")
            print(f"  SAVED   {rel_path} <- \"{title}\"")

        new_manifest_entries[rel_path] = {
            "id": page_id,
            "title": title,
            "parent_id": parent_id,
            "last_published": None,
        }
        exported += 1

    if not dry_run and new_manifest_entries:
        merged = {**manifest, **new_manifest_entries}
        save_manifest(config, merged)
        print(f"\nManifest updated: {len(merged)} entries")

    print(f"Summary: {exported} pages exported")


def main():
    args = parse_args()
    config = load_config(args.config)
    manifest = load_manifest(config)

    confluence = connect(config)

    print("Export from Confluence")
    print(f"  Target: {config.confluence_url} / {config.space_key}")
    print()

    if args.page:
        export_single_page(confluence, args.page, args.output, args.dry_run)
    elif args.manifest:
        export_from_manifest(confluence, config, manifest, args.dry_run)
    elif args.tree:
        export_tree(confluence, config, manifest, args.dry_run)


if __name__ == "__main__":
    main()
