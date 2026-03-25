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

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from atlassian import Confluence
    from confluence_config import ConfluenceConfig

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from confluence_api import fetch_page, update_page_body  # noqa: E402
from confluence_config import add_config_arg, connect, load_config  # noqa: E402
from html_diff import (  # noqa: E402
    format_diff_report,
    normalize_html,
    section_integrity_check,
    semantic_diff,
)
from page_utils import extract_page_id  # noqa: E402

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
    apply_grp.add_argument(
        "--new-md",
        help="Path to a markdown file to convert and use as the replacement "
        "(auto-converts to Confluence HTML, renders mermaid diagrams, adjusts heading levels)",
    )

    # Shared
    parser.add_argument(
        "-o", "--output", help="Output file path (extract: save element, apply: save report)"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Show changes without pushing (apply mode)"
    )
    parser.add_argument("--message", help="Version message for the Confluence edit")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Allow replacement when multiple occurrences found (apply mode)",
    )

    args = parser.parse_args()

    # Determine mode
    if args.old and (args.new or args.new_md):
        args.mode = "apply"
    elif args.heading and args.new_md and args.element == "section":
        # --heading + --new-md: extract old section, convert md, replace in one step
        args.mode = "apply-md"
    elif args.heading:
        args.mode = "extract"
    else:
        parser.error(
            "Specify --heading for extract mode, --old + --new for apply mode, "
            "or --heading + --new-md + --element section for markdown replacement"
        )

    # Validate --nth
    if hasattr(args, "nth") and args.nth is not None and args.nth < 1:
        parser.error("--nth must be >= 1")

    return args


def _find_heading_match(html_content: str, heading_text: str) -> re.Match:
    """Find the first heading whose text content contains *heading_text* (case-insensitive).

    Handles HTML entities transparently: ``"Testing & Evaluation"`` matches
    ``<h1>Testing &amp; Evaluation</h1>`` because the inner text is decoded
    before comparison.

    Returns the regex Match object, or exits with an error if no heading matches.
    """
    import html as html_mod

    heading_pattern = re.compile(
        r"<(h[1-6])([^>]*)>(.*?)</\1>",
        re.IGNORECASE | re.DOTALL,
    )
    needle = heading_text.lower()
    for m in heading_pattern.finditer(html_content):
        raw_inner = re.sub(r"<[^>]+>", "", m.group(3))
        # Decode HTML entities (e.g. &amp; → &, &ndash; → –) before matching
        decoded_inner = html_mod.unescape(raw_inner).lower()
        if needle in decoded_inner or needle in raw_inner.lower():
            return m
    print(f"ERROR: Heading containing '{heading_text}' not found in page HTML")
    sys.exit(1)


def _extract_section_range(html: str, heading_match: re.Match) -> tuple[int, int]:
    """Return (start, end) for the section starting at *heading_match*.

    The section spans from the heading through to the next heading of the same
    or higher level, or to the end of the HTML if no such heading exists.
    """
    heading_tag = heading_match.group(1).lower()  # e.g., 'h2'
    heading_level = int(heading_tag[1])
    next_heading = re.compile(
        r"<(h[1-" + str(heading_level) + r"])[^>]*>",
        re.IGNORECASE,
    )
    next_match = next_heading.search(html, heading_match.end())
    if next_match:
        return heading_match.start(), next_match.start()
    return heading_match.start(), len(html)


def _find_nth_element_after(
    html: str, start_pos: int, tag: str, nth: int, heading_text: str
) -> tuple[int, int]:
    """Find the *nth* occurrence of *tag* in *html* starting from *start_pos*.

    Uses depth tracking to correctly handle nested elements of the same type.
    Returns (start, end) indices, or exits with an error if not found.
    """
    open_token = f"<{tag}"
    close_token = f"</{tag}>"
    pos = start_pos
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


def find_element_after_heading(
    html: str, heading_text: str, element: str, nth: int = 1
) -> tuple[int, int]:
    """Find the nth element of the given type after a heading containing heading_text.

    For element='section', returns from the heading tag through to the next
    heading of the same or higher level.

    Returns (start, end) indices into the HTML string.
    Exits with error if not found.
    """
    heading_match = _find_heading_match(html, heading_text)

    if element == "section":
        return _extract_section_range(html, heading_match)

    return _find_nth_element_after(html, heading_match.end(), element.lower(), nth, heading_text)


def extract_mode(args: argparse.Namespace) -> None:
    """Extract an HTML element from a Confluence page and save to file."""
    config = load_config(args.config)
    page_id = extract_page_id(args.page)

    print(f"Fetching page {page_id}...")
    snapshot = fetch_page(config, page_id)
    print(f"  Title:   {snapshot.title}")
    print(f"  Version: {snapshot.version}")
    print(f"  Size:    {len(snapshot.html)} chars")

    start, end = find_element_after_heading(snapshot.html, args.heading, args.element, args.nth)
    element_html = snapshot.html[start:end]

    output_path = args.output or f"/tmp/element-{args.element}.html"
    Path(output_path).write_text(element_html, encoding="utf-8")
    print(
        f"\nExtracted <{args.element}> ({len(element_html)} chars) after heading '{args.heading}'"
    )
    print(f"  Saved to: {output_path}")
    print("\nEdit this file, then apply with:")
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
        print(
            "ERROR: New file is empty (would delete the element). Use surgical_edit.py for deletions."
        )
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
        print(
            "  Cannot determine which one to replace. Use --force to replace the first occurrence,"
        )
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

    print(
        f"HTML size: {len(snapshot.html)} -> {len(modified_html)} ({len(modified_html) - len(snapshot.html):+d} chars)"
    )

    if args.dry_run:
        print("\n[DRY RUN] No changes pushed to Confluence.")
        sys.exit(0)

    version_msg = args.message or f"Element replacement on page {page_id}"
    new_version = update_page_body(
        config,
        page_id,
        snapshot.title,
        modified_html,
        message=version_msg,
    )
    print(f"\nPage updated to version {new_version}")
    print(f"  {config.confluence_url}/pages/{page_id}")


def _convert_md_to_confluence_html(
    md_path: Path,
    page_id: str,
    target_heading_level: int,
    config: ConfluenceConfig,
    confluence: Confluence,
) -> str:
    """Convert a markdown file to Confluence HTML with mermaid rendering and heading adjustment.

    Args:
        md_path: Path to the markdown file.
        page_id: Confluence page ID (for uploading mermaid PNGs).
        target_heading_level: The heading level (1-6) of the top-level heading in the old section.
        config: ConfluenceConfig instance.
        confluence: Confluence API connection.

    Returns:
        Confluence storage HTML ready for insertion.
    """
    import tempfile

    from transforms import (
        MERMAID_BLOCK_RE,
        inject_image_macros,
        markdown_to_confluence_storage,
        render_mermaid_blocks,
    )

    md_content = md_path.read_text(encoding="utf-8")

    # Detect the heading level used in the markdown (first heading)
    md_heading_match = re.match(r"^(#+)\s", md_content, re.MULTILINE)
    md_level = len(md_heading_match.group(1)) if md_heading_match else target_heading_level

    # Shift headings in markdown to match target level
    level_shift = target_heading_level - md_level
    if level_shift != 0:
        lines = md_content.split("\n")
        adjusted = []
        for line in lines:
            hm = re.match(r"^(#+)(\s)", line)
            if hm:
                current = len(hm.group(1))
                new_level = max(1, min(6, current + level_shift))
                line = "#" * new_level + line[current:]
            adjusted.append(line)
        md_content = "\n".join(adjusted)

    # Render mermaid diagrams
    png_files: list[Path] = []
    if MERMAID_BLOCK_RE.search(md_content):
        with tempfile.TemporaryDirectory() as tmp_dir:
            md_content, png_files = render_mermaid_blocks(md_content, Path(tmp_dir))
            html = markdown_to_confluence_storage(md_content)
            html = inject_image_macros(html)
            # Upload mermaid PNGs as attachments
            for png in png_files:
                if png.exists():
                    try:
                        confluence.attach_file(str(png), name=png.name, page_id=page_id)
                        print(f"  Uploaded mermaid diagram: {png.name}")
                    except Exception as e:
                        print(f"  WARNING: Failed to upload {png.name}: {e}")
    else:
        html = markdown_to_confluence_storage(md_content)

    return html


def apply_md_mode(args: argparse.Namespace) -> None:
    """Extract a section by heading and replace it with converted markdown content."""
    config = load_config(args.config)
    page_id = extract_page_id(args.page)
    confluence = connect(config)

    md_path = Path(args.new_md)
    if not md_path.is_file():
        print(f"ERROR: Markdown file not found: {md_path}")
        sys.exit(1)

    print(f"Fetching page {page_id}...")
    snapshot = fetch_page(config, page_id)
    print(f"  Title:   {snapshot.title}")
    print(f"  Version: {snapshot.version}")
    print(f"  Size:    {len(snapshot.html)} chars")

    # Find the old section
    heading_match = _find_heading_match(snapshot.html, args.heading)
    start, end = _extract_section_range(snapshot.html, heading_match)
    old_html = snapshot.html[start:end]

    # Detect heading level in old section
    tag_match = re.match(r"<(h[1-6])", old_html, re.IGNORECASE)
    target_level = int(tag_match.group(1)[1]) if tag_match else 1

    print(f"  Old section: {len(old_html)} chars (heading level h{target_level})")
    print(f"  Converting {md_path.name} to Confluence HTML...")

    new_html = _convert_md_to_confluence_html(md_path, page_id, target_level, config, confluence)
    print(f"  New section: {len(new_html)} chars")

    modified_html = snapshot.html[:start] + new_html + snapshot.html[end:]

    # Diff report
    old_normalized = normalize_html(snapshot.html)
    new_normalized = normalize_html(modified_html)
    changes = semantic_diff(old_normalized, new_normalized)
    integrity = section_integrity_check(snapshot.html, modified_html)
    report = format_diff_report(changes, integrity)

    if args.output:
        Path(args.output).write_text(report, encoding="utf-8")
        print(f"Diff report saved to {args.output}")
    else:
        # Truncate to avoid flooding terminal
        if len(report) > 3000:
            print(report[:3000])
            print(
                f"\n... (truncated, {len(report)} chars total — use --output to save full report)"
            )
        else:
            print(report)

    print(
        f"HTML size: {len(snapshot.html)} -> {len(modified_html)} "
        f"({len(modified_html) - len(snapshot.html):+d} chars)"
    )

    if args.dry_run:
        print("\n[DRY RUN] No changes pushed to Confluence.")
        sys.exit(0)

    version_msg = args.message or f"Replace section '{args.heading}' from {md_path.name}"
    new_version = update_page_body(
        config,
        page_id,
        snapshot.title,
        modified_html,
        message=version_msg,
    )
    print(f"\nPage updated to version {new_version}")
    print(f"  {config.confluence_url}/pages/{page_id}")


def main():
    args = parse_args()
    if args.mode == "extract":
        extract_mode(args)
    elif args.mode == "apply-md":
        apply_md_mode(args)
    else:
        apply_mode(args)


if __name__ == "__main__":
    main()
