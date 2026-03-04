#!/usr/bin/env python3
"""
confluence-publisher skill — Element Replacement Helper

Simplifies large structural edits (tables, sections) on Confluence pages.
Two modes:

  EXTRACT — fetch page HTML and save a specific element to a file:
    python replace_element.py --config .confluence.json \
        --page 1079706804 --heading "Implementation Phases" \
        --element table --output /tmp/table.html

  APPLY — replace the old element with a modified version:
    python replace_element.py --config .confluence.json \
        --page 1079706804 --old /tmp/table.html --new /tmp/table-new.html --dry-run

Supported --element types: table, ul, ol, div, section (heading + content until next same-or-higher-level heading).
"""

import argparse
import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from config_loader import add_config_arg, load_config
from page_utils import extract_page_id
from confluence_api import fetch_page, update_page_body
from html_diff import (
    normalize_html,
    semantic_diff,
    section_integrity_check,
    format_diff_report,
)

SUPPORTED_ELEMENTS = {"table", "ul", "ol", "div"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract or replace HTML elements on a Confluence page"
    )
    add_config_arg(parser)
    parser.add_argument("--page", required=True, help="Page ID, full URL, or tiny link")

    # Extract mode
    extract = parser.add_argument_group("extract mode")
    extract.add_argument(
        "--heading",
        help="Heading text to locate (searches for the element after this heading)",
    )
    extract.add_argument(
        "--element",
        choices=sorted(SUPPORTED_ELEMENTS) + ["section"],
        help="Type of element to extract (default: table)",
        default="table",
    )
    extract.add_argument(
        "--nth",
        type=int,
        default=1,
        help="Which occurrence after the heading (default: 1st, must be >= 1)",
    )

    # Apply mode
    apply_grp = parser.add_argument_group("apply mode")
    apply_grp.add_argument("--old", help="Path to the original extracted HTML file")
    apply_grp.add_argument("--new", help="Path to the modified HTML file")

    # Shared
    parser.add_argument("-o", "--output", help="Output file path (extract: save element, apply: save report)")
    parser.add_argument("--dry-run", action="store_true", help="Show changes without pushing (apply mode)")
    parser.add_argument("--message", help="Version message for the Confluence edit")
    parser.add_argument("--force", action="store_true", help="Allow replacement when multiple occurrences found (apply mode)")

    args = parser.parse_args()

    # Determine mode
    if args.old and args.new:
        args.mode = "apply"
    elif args.heading:
        args.mode = "extract"
    else:
        parser.error("Specify --heading for extract mode, or --old + --new for apply mode")

    # Validate --nth
    if hasattr(args, 'nth') and args.nth is not None and args.nth < 1:
        parser.error("--nth must be >= 1")

    return args


def find_element_after_heading(html: str, heading_text: str, element: str, nth: int = 1) -> tuple[int, int]:
    """Find the nth element of the given type after a heading containing heading_text.

    For element='section', returns from the heading tag through to the next
    heading of the same or higher level.

    Returns (start, end) indices into the HTML string.
    Exits with error if not found.
    """
    # Find headings individually, then check if heading_text appears in the
    # text content (with inner tags stripped). This avoids the DOTALL regex
    # spanning across multiple headings.
    heading_pattern = re.compile(
        r"<(h[1-6])([^>]*)>(.*?)</\1>",
        re.IGNORECASE | re.DOTALL,
    )
    heading_match = None
    for m in heading_pattern.finditer(html):
        inner_text = re.sub(r"<[^>]+>", "", m.group(3))
        if heading_text.lower() in inner_text.lower():
            heading_match = m
            break
    if not heading_match:
        print(f"ERROR: Heading containing '{heading_text}' not found in page HTML")
        sys.exit(1)

    search_from = heading_match.start()

    if element == "section":
        # Extract from the heading through to the next heading of same/higher level
        heading_tag = heading_match.group(1).lower()  # e.g., 'h2'
        heading_level = int(heading_tag[1])
        # Find next heading of same or higher level
        next_heading = re.compile(
            r"<(h[1-" + str(heading_level) + r"])[^>]*>",
            re.IGNORECASE,
        )
        next_match = next_heading.search(html, heading_match.end())
        if next_match:
            return search_from, next_match.start()
        else:
            return search_from, len(html)

    # For regular elements, find the nth occurrence after the heading.
    # Uses depth tracking: start at depth=1 when we find the opening tag,
    # then scan forward for nested open/close tokens until depth returns to 0.
    tag = element.lower()
    open_token = f"<{tag}"
    close_token = f"</{tag}>"
    pos = heading_match.end()
    count = 0

    while pos < len(html):
        tag_start = html.find(open_token, pos)
        if tag_start == -1:
            break

        # Start inside the opening tag, depth=1
        depth = 1
        scan = tag_start + len(open_token)

        while depth > 0 and scan < len(html):
            next_open = html.find(open_token, scan)
            next_close = html.find(close_token, scan)

            if next_close == -1:
                print(f"ERROR: Unclosed <{tag}> element")
                sys.exit(1)

            if next_open != -1 and next_open < next_close:
                depth += 1
                scan = next_open + len(open_token)
            else:
                depth -= 1
                if depth == 0:
                    tag_end = next_close + len(close_token)
                    count += 1
                    if count == nth:
                        return tag_start, tag_end
                    pos = tag_end
                    break
                scan = next_close + len(close_token)

    ordinal = {1: "1st", 2: "2nd", 3: "3rd"}.get(nth, f"{nth}th")
    print(f"ERROR: Could not find {ordinal} <{tag}> element after heading '{heading_text}'")
    sys.exit(1)


def extract_mode(args: argparse.Namespace) -> None:
    """Extract an HTML element from a Confluence page and save to file."""
    config = load_config(args.config)
    page_id = extract_page_id(args.page)

    print(f"Fetching page {page_id}...")
    snapshot = fetch_page(config, page_id)
    print(f"  Title:   {snapshot.title}")
    print(f"  Version: {snapshot.version}")
    print(f"  Size:    {len(snapshot.html)} chars")

    start, end = find_element_after_heading(
        snapshot.html, args.heading, args.element, args.nth
    )
    element_html = snapshot.html[start:end]

    output_path = args.output or f"/tmp/element-{args.element}.html"
    Path(output_path).write_text(element_html, encoding="utf-8")
    print(f"\nExtracted <{args.element}> ({len(element_html)} chars) after heading '{args.heading}'")
    print(f"  Saved to: {output_path}")
    print(f"\nEdit this file, then apply with:")
    print(f"  python {Path(__file__).name} --config {args.config or '.confluence.json'} \\")
    print(f"      --page {page_id} --old {output_path} --new <modified-file> --dry-run")


def apply_mode(args: argparse.Namespace) -> None:
    """Replace an HTML element on a Confluence page."""
    config = load_config(args.config)
    page_id = extract_page_id(args.page)

    old_path = Path(args.old)
    new_path = Path(args.new)

    for label, p in [("Old", old_path), ("New", new_path)]:
        if not p.is_file():
            print(f"ERROR: {label} file not found or is not a file: {p}")
            sys.exit(1)

    try:
        old_html = old_path.read_text(encoding="utf-8").strip()
        new_html = new_path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeDecodeError) as exc:
        print(f"ERROR: Failed to read input files: {exc}")
        sys.exit(1)

    if not old_html:
        print("ERROR: Old file is empty (would match everywhere). Re-extract and try again.")
        sys.exit(1)
    if not new_html:
        print("ERROR: New file is empty (would delete the element). Use surgical_edit.py for deletions.")
        sys.exit(1)

    if old_html == new_html:
        print("No differences between old and new files.")
        sys.exit(0)

    print(f"Fetching page {page_id}...")
    snapshot = fetch_page(config, page_id)
    print(f"  Title:   {snapshot.title}")
    print(f"  Version: {snapshot.version}")
    print(f"  Size:    {len(snapshot.html)} chars")

    if old_html not in snapshot.html:
        print(f"\nERROR: The content of '{args.old}' was not found in the page HTML.")
        print("  The page may have been edited since extraction. Re-extract and try again.")
        sys.exit(1)

    count = snapshot.html.count(old_html)
    if count > 1 and not args.force:
        print(f"\nERROR: Found {count} occurrences of the old element in the page.")
        print("  Cannot determine which one to replace. Use --force to replace the first occurrence,")
        print("  or re-extract with a more specific --heading + --nth to get a unique element.")
        sys.exit(1)
    if count > 1:
        print(f"\nWARNING: Found {count} occurrences (--force). Replacing the first only.")

    modified_html = snapshot.html.replace(old_html, new_html, 1)
    print(f"\nReplaced element ({len(old_html)} chars -> {len(new_html)} chars)")

    # Compute semantic diff
    old_normalized = normalize_html(snapshot.html)
    new_normalized = normalize_html(modified_html)
    changes = semantic_diff(old_normalized, new_normalized)
    integrity = section_integrity_check(snapshot.html, modified_html)

    report = format_diff_report(changes, integrity)

    if args.output:
        Path(args.output).write_text(report, encoding="utf-8")
        print(f"Diff report saved to {args.output}")
    else:
        print(report)

    print(f"HTML size: {len(snapshot.html)} -> {len(modified_html)} ({len(modified_html) - len(snapshot.html):+d} chars)")

    if args.dry_run:
        print("\n[DRY RUN] No changes pushed to Confluence.")
        sys.exit(0)

    version_msg = args.message or f"Element replacement on page {page_id}"
    new_version = update_page_body(
        config, page_id, snapshot.title, modified_html, message=version_msg,
    )
    print(f"\nPage updated to version {new_version}")
    print(f"  {config.confluence_url}/pages/{page_id}")


def main():
    args = parse_args()
    if args.mode == "extract":
        extract_mode(args)
    else:
        apply_mode(args)


if __name__ == "__main__":
    main()
