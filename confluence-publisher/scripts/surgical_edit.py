#!/usr/bin/env python3
"""
confluence-publisher skill — Surgical Page Editor

Apply targeted find/replace edits to a Confluence page's storage HTML without
overwriting the entire page. Preserves manual formatting in untouched sections.

This script does NOT involve markdown conversion — it operates directly on
Confluence storage format HTML.

Usage:
    # Apply replacements from a JSON file
    python surgical_edit.py --config .confluence.json \
        --page 1079706804 --replacements edits.json

    # Inline single replacement
    python surgical_edit.py --config .confluence.json \
        --page 1079706804 --find "old text" --replace "new text"

    # Dry run (show diff without pushing)
    python surgical_edit.py --config .confluence.json \
        --page 1079706804 --replacements edits.json --dry-run

    # Replace all occurrences (default: first occurrence only)
    python surgical_edit.py --config .confluence.json \
        --page 1079706804 --find "old" --replace "new" --replace-all

    # Save diff report to file
    python surgical_edit.py --config .confluence.json \
        --page 1079706804 --replacements edits.json --output /tmp/report.txt

Replacements JSON format:
    [
        {"find": "old text 1", "replace": "new text 1"},
        {"find": "old text 2", "replace": "new text 2", "replace_all": true}
    ]
"""

import argparse
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from config_loader import load_config, extract_page_id
from confluence_api import fetch_page, update_page_body
from html_diff import (
    normalize_html,
    semantic_diff,
    section_integrity_check,
    format_diff_report,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Apply surgical find/replace edits to a Confluence page"
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
    parser.add_argument(
        "--replacements",
        help="Path to JSON file with replacement pairs",
    )
    parser.add_argument("--find", help="Text to find (inline single replacement)")
    parser.add_argument("--replace", help="Text to replace with (inline single replacement)")
    parser.add_argument(
        "--replace-all",
        action="store_true",
        help="Replace all occurrences (default: first only)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would change without pushing",
    )
    parser.add_argument(
        "--output",
        help="Save diff report to file instead of stdout",
    )
    parser.add_argument(
        "--message",
        help="Version message for the Confluence edit",
    )
    parser.add_argument(
        "--check-sections",
        help="Comma-separated list of section markers to verify after edit",
    )
    return parser.parse_args()


def _validate_replacement_item(item, idx: int) -> None:
    """Validate a single replacement dict from a JSON file. Exits on error."""
    if not isinstance(item, dict):
        print(f"ERROR: Replacement #{idx} is not an object")
        sys.exit(1)
    if "find" not in item or "replace" not in item:
        print(f"ERROR: Replacement #{idx} missing 'find' or 'replace' key")
        sys.exit(1)
    if not isinstance(item["find"], str) or not isinstance(item["replace"], str):
        print(f"ERROR: Replacement #{idx} 'find'/'replace' must be strings")
        sys.exit(1)


def _load_replacements_file(path: Path) -> list[dict]:
    """Load and validate a replacements JSON file. Exits on error."""
    if not path.exists():
        print(f"ERROR: Replacements file not found: {path}")
        sys.exit(1)
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        print("ERROR: Replacements JSON must be a list of {find, replace} objects")
        sys.exit(1)
    for idx, item in enumerate(data, 1):
        _validate_replacement_item(item, idx)
    return data


def load_replacements(args: argparse.Namespace) -> list[dict]:
    """Build the replacement list from CLI args."""
    replacements = []

    if args.replacements:
        replacements.extend(_load_replacements_file(Path(args.replacements)))

    if args.find is not None and args.replace is not None:
        replacements.append({
            "find": args.find,
            "replace": args.replace,
            "replace_all": args.replace_all,
        })
    elif args.find is not None or args.replace is not None:
        print("ERROR: --find and --replace must be used together")
        sys.exit(1)

    if not replacements:
        print("ERROR: No replacements specified. Use --replacements or --find/--replace")
        sys.exit(1)

    return replacements


def apply_replacements(html: str, replacements: list[dict]) -> tuple[str, list[str]]:
    """Apply replacements to HTML. Returns (modified_html, log_messages)."""
    log = []
    for i, r in enumerate(replacements, 1):
        find = r["find"]
        replace = r["replace"]

        if not find:
            log.append(f"  #{i} SKIPPED: empty 'find' string (would corrupt HTML)")
            continue
        replace_all = r.get("replace_all", False)

        count = html.count(find)
        if count == 0:
            log.append(f"  #{i} NOT FOUND: {find[:80]}...")
            continue

        if replace_all:
            html = html.replace(find, replace)
            log.append(f"  #{i} Replaced {count} occurrence(s): {find[:60]}... -> {replace[:60]}...")
        else:
            html = html.replace(find, replace, 1)
            log.append(f"  #{i} Replaced 1 of {count} occurrence(s): {find[:60]}... -> {replace[:60]}...")

    return html, log


def main():
    args = parse_args()
    config = load_config(args.config)
    page_id = extract_page_id(args.page)
    replacements = load_replacements(args)

    # Fetch current page
    print(f"Fetching page {page_id}...")
    snapshot = fetch_page(config, page_id)
    print(f"  Title:   {snapshot.title}")
    print(f"  Version: {snapshot.version}")
    print(f"  Size:    {len(snapshot.html)} chars")
    print()

    # Apply replacements
    print(f"Applying {len(replacements)} replacement(s)...")
    modified_html, log = apply_replacements(snapshot.html, replacements)
    for msg in log:
        print(msg)
    print()

    if modified_html == snapshot.html:
        print("No changes were made (all find strings not found or identical).")
        sys.exit(0)

    # Compute semantic diff
    old_normalized = normalize_html(snapshot.html)
    new_normalized = normalize_html(modified_html)
    changes = semantic_diff(old_normalized, new_normalized)

    # Section integrity check
    markers = None
    if args.check_sections:
        markers = [m.strip() for m in args.check_sections.split(",")]
    integrity = section_integrity_check(snapshot.html, modified_html, markers)

    # Format report
    report = format_diff_report(changes, integrity)

    # Output report
    if args.output:
        Path(args.output).write_text(report, encoding="utf-8")
        print(f"Diff report saved to {args.output}")
    else:
        print(report)

    # Summary
    print(f"HTML size: {len(snapshot.html)} -> {len(modified_html)} ({len(modified_html) - len(snapshot.html):+d} chars)")

    if args.dry_run:
        print("\n[DRY RUN] No changes pushed to Confluence.")
        sys.exit(0)

    # Push update
    version_msg = args.message or f"Surgical edit: {len(replacements)} replacement(s)"
    new_version = update_page_body(
        config, page_id, snapshot.title, modified_html, message=version_msg,
    )
    print(f"\nPage updated to version {new_version}")
    print(f"  {config.confluence_url}/pages/{page_id}")


if __name__ == "__main__":
    main()
