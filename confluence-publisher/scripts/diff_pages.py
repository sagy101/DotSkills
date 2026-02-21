#!/usr/bin/env python3
"""
confluence-publisher skill — Diff/Preview

Compares local markdown files against their published Confluence pages.

Both sides are normalized to the same representation before diffing:
  1. Local markdown is transformed through the publish pipeline (mermaid
     blocks → image placeholders, .md links → Confluence link macros)
     to produce Confluence storage HTML.
  2. Remote Confluence page storage HTML is fetched as-is.
  3. Both HTML strings are converted to markdown via markdownify.
  4. The two markdown strings are diffed.

This eliminates false positives from mermaid diagrams and cross-page links.
Minor whitespace differences may still appear due to round-trip formatting.

Usage:
    # Diff a single file
    python diff_pages.py --config .confluence.json --file README.md

    # Diff all manifest entries
    python diff_pages.py --config .confluence.json --all

    # Summary only (no full diff output)
    python diff_pages.py --config .confluence.json --all --summary
"""

import argparse
import difflib
import re
import sys
from pathlib import Path
from typing import Optional

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from config_loader import load_config, connect, load_manifest, ensure_deps

ensure_deps({"atlassian-python-api": "atlassian", "markdownify": "markdownify", "markdown": "markdown"})

from atlassian import Confluence  # noqa: E402
from markdownify import markdownify as md_convert  # noqa: E402
from transforms import (  # noqa: E402
    markdown_to_confluence_storage,
    rewrite_md_links,
    strip_mermaid_blocks,
    normalize_remote_mermaid_macros,
    preprocess_confluence_storage,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Diff local markdown against Confluence pages"
    )
    parser.add_argument(
        "--config",
        help="Path to .confluence.json (default: auto-detect from cwd up)",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--file", help="Single file to diff (relative to docs_dir)")
    group.add_argument("--all", action="store_true", help="Diff all manifest entries")
    parser.add_argument(
        "--summary",
        action="store_true",
        help="Show only summary (changed/unchanged counts), no full diff",
    )
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Normalization helpers
# ---------------------------------------------------------------------------

def storage_html_to_normalized_md(html: str) -> str:
    """Convert Confluence storage HTML to normalized markdown for diffing."""
    # Preprocess specific Confluence macros (like code blocks)
    html = preprocess_confluence_storage(html)

    markdown_content = md_convert(
        html,
        heading_style="atx",
        bullets="-",
    )
    markdown_content = re.sub(r"\n{3,}", "\n\n", markdown_content)
    return markdown_content.strip()


def local_md_to_storage_html(md_content: str, rel_path: str, manifest: dict, space_key: str) -> str:
    """Transform local markdown through the publish pipeline to produce
    Confluence storage HTML (without actually publishing).
    Mermaid blocks are replaced with stable placeholders."""
    processed = strip_mermaid_blocks(md_content)
    html = markdown_to_confluence_storage(processed)
    html = rewrite_md_links(html, rel_path, manifest, space_key)
    return html


# ---------------------------------------------------------------------------
# Fetch + diff
# ---------------------------------------------------------------------------

def fetch_page_storage_html(confluence: Confluence, page_id: str) -> Optional[str]:
    """Fetch a Confluence page's raw storage format HTML."""
    page = confluence.get_page_by_id(
        page_id=page_id,
        expand="body.storage",
    )
    if not page:
        return None
    return page["body"]["storage"]["value"]


def normalize_for_diff(text: str) -> list:
    """Normalize text for diffing — strip trailing whitespace per line."""
    return [line.rstrip() for line in text.splitlines()]


def compute_diff(remote_lines, local_lines, remote_label, local_label):
    """Compute unified diff and return (diff_lines, added_count, removed_count)."""
    diff_result = list(difflib.unified_diff(
        remote_lines,
        local_lines,
        fromfile=remote_label,
        tofile=local_label,
        lineterm="",
    ))
    added = sum(1 for line in diff_result if line.startswith("+") and not line.startswith("+++"))
    removed = sum(1 for line in diff_result if line.startswith("-") and not line.startswith("---"))
    return diff_result, added, removed


def diff_file(
    confluence: Confluence,
    config,
    manifest: dict,
    rel_path: str,
    show_full_diff: bool,
) -> str:
    """Diff one file. Returns status: 'changed', 'unchanged', 'new', 'no_page', 'no_file'."""
    file_path = config.docs_root / rel_path

    if not file_path.exists():
        print(f"  {rel_path}: LOCAL FILE MISSING")
        return "no_file"

    if rel_path not in manifest:
        print(f"  {rel_path}: NOT IN MANIFEST (would be a new page)")
        return "new"

    page_id = manifest[rel_path]["id"]

    # Fetch remote storage HTML
    remote_html = fetch_page_storage_html(confluence, page_id)
    if remote_html is None:
        print(f"  {rel_path}: CONFLUENCE PAGE NOT FOUND (id={page_id})")
        return "no_page"

    # Transform local markdown through the same publish pipeline
    local_md_raw = file_path.read_text(encoding="utf-8")
    local_html = local_md_to_storage_html(local_md_raw, rel_path, manifest, config.space_key)

    # Normalize remote HTML (replace mermaid image macros with placeholders)
    remote_html = normalize_remote_mermaid_macros(remote_html)

    # Convert both to markdown for human-readable diff
    local_normalized = storage_html_to_normalized_md(local_html)
    remote_normalized = storage_html_to_normalized_md(remote_html)

    local_lines = normalize_for_diff(local_normalized)
    remote_lines = normalize_for_diff(remote_normalized)

    if local_lines == remote_lines:
        print(f"  {rel_path}: UNCHANGED")
        return "unchanged"

    diff_result, added, removed = compute_diff(
        remote_lines,
        local_lines,
        remote_label=f"confluence:{manifest[rel_path]['title']} (id={page_id})",
        local_label=f"local:{rel_path}",
    )

    print(f"  {rel_path}: CHANGED (+{added} -{removed} lines)")

    if show_full_diff:
        print()
        for line in diff_result:
            print(f"    {line}")
        print()

    return "changed"


def main():
    args = parse_args()
    config = load_config(args.config)
    manifest = load_manifest(config)

    if not manifest and not args.file:
        print("ERROR: No manifest found. Run discover_pages.py or publish first.")
        sys.exit(1)

    confluence = connect(config)

    print("Diff: local docs vs Confluence (normalized)")
    print(f"  Target: {config.confluence_url} / {config.space_key}")
    print()

    show_full_diff = not args.summary
    counts = {"changed": 0, "unchanged": 0, "new": 0, "no_page": 0, "no_file": 0}

    if args.file:
        files_to_diff = [args.file]
    else:
        files_to_diff = sorted(manifest.keys())

    for rel_path in files_to_diff:
        status = diff_file(confluence, config, manifest, rel_path, show_full_diff)
        counts[status] = counts.get(status, 0) + 1

    print("-" * 60)
    print(f"Summary: {counts['changed']} changed, {counts['unchanged']} unchanged, "
          f"{counts['new']} new, {counts['no_page']} missing on Confluence, "
          f"{counts['no_file']} missing locally")

    if counts["changed"] > 0 or counts["new"] > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
