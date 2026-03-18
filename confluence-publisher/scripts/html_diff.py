"""
confluence-publisher skill — HTML Diff Engine

Semantic diffing and section integrity checking for Confluence storage HTML.
Strips Confluence noise attributes and compares meaningful content changes.

Used by surgical_edit.py and diff_versions.py.
"""

import re
from dataclasses import dataclass
from typing import TypedDict

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class DiffChange:
    """A single semantic change between two HTML strings."""

    change_type: str  # 'replace', 'insert', 'delete'
    old_text: str
    new_text: str


# ---------------------------------------------------------------------------
# HTML normalization
# ---------------------------------------------------------------------------


# Attributes that Confluence auto-generates and differ between edits
_NOISE_PATTERNS = [
    (re.compile(r'\s+ac:local-id="[^"]*"'), ""),
    (re.compile(r'(?<=\s)local-id="[^"]*"'), ""),
    (re.compile(r'\s+data-table-width="\d+"'), ""),
]


def normalize_html(html: str) -> str:
    """Strip Confluence-generated noise attributes for clean comparison.

    Removes ac:local-id, local-id, and data-table-width attributes that
    change on every edit but carry no semantic meaning.
    """
    for pattern, replacement in _NOISE_PATTERNS:
        html = pattern.sub(replacement, html)
    return html


class SectionStatus(TypedDict):
    """Result of a single section integrity check."""

    section: str
    in_old: bool
    in_new: bool
    status: str  # 'ok', 'MISSING', or 'ADDED'


# ---------------------------------------------------------------------------
# Diff computation
# ---------------------------------------------------------------------------


def _tag_split(html: str) -> list[str]:
    """Split HTML into alternating tags and text chunks."""
    return re.findall(r"<[^>]+>|[^<]+", html)


def _strip_tags(text: str) -> str:
    """Remove HTML tags, returning only text content."""
    return re.sub(r"<[^>]+>", "", text).strip()


def semantic_diff(old_html: str, new_html: str) -> list[DiffChange]:
    """Compute a semantic diff between two normalized HTML strings.

    Splits HTML into tag/text tokens, runs SequenceMatcher, and returns
    only changes where the text content (ignoring tags) actually differs.

    Args:
        old_html: Normalized HTML (before).
        new_html: Normalized HTML (after).

    Returns:
        List of DiffChange objects with meaningful text changes.
    """
    import difflib

    old_tokens = _tag_split(old_html)
    new_tokens = _tag_split(new_html)

    matcher = difflib.SequenceMatcher(None, old_tokens, new_tokens)
    changes = []

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue

        old_text = _strip_tags("".join(old_tokens[i1:i2]))
        new_text = _strip_tags("".join(new_tokens[j1:j2]))

        if old_text or new_text:
            changes.append(
                DiffChange(
                    change_type=tag,
                    old_text=old_text,
                    new_text=new_text,
                )
            )

    return changes


def section_integrity_check(
    old_html: str,
    new_html: str,
    markers: list[str] | None = None,
) -> list[SectionStatus]:
    """Check that named sections are preserved between two HTML versions.

    Args:
        old_html: HTML before changes.
        new_html: HTML after changes.
        markers: List of text strings to look for. If None, auto-detects
                 headings from old_html.

    Returns:
        List of dicts: {section, in_old, in_new, status}.
    """
    if markers is None:
        markers = re.findall(r"<h[1-6][^>]*>(.*?)</h[1-6]>", old_html)
        markers = [_strip_tags(m) for m in markers if _strip_tags(m)]

    results: list[SectionStatus] = []
    for m in markers:
        in_old = m in old_html
        in_new = m in new_html
        if in_old == in_new:
            status = "ok"
        elif in_old:
            status = "MISSING"
        else:
            status = "ADDED"
        results.append(
            SectionStatus(
                section=m,
                in_old=in_old,
                in_new=in_new,
                status=status,
            )
        )
    return results


# ---------------------------------------------------------------------------
# Report formatting
# ---------------------------------------------------------------------------


def _truncate(text: str, max_len: int) -> str:
    """Truncate text with ellipsis if it exceeds max_len."""
    if len(text) <= max_len:
        return text
    return text[:max_len] + "..."


def _format_changes(changes: list[DiffChange], max_text_len: int) -> list[str]:
    """Format the list of changes into report lines."""
    lines = [f"=== SEMANTIC DIFF ({len(changes)} changes) ===\n"]
    for i, c in enumerate(changes, 1):
        lines.append(f"Change {i} [{c.change_type}]:")
        if c.old_text:
            lines.append(f"  OLD: {_truncate(c.old_text, max_text_len)}")
        if c.new_text:
            lines.append(f"  NEW: {_truncate(c.new_text, max_text_len)}")
        lines.append("")
    return lines


def _format_integrity(integrity: list[SectionStatus]) -> list[str]:
    """Format the integrity check results into report lines."""
    lines = ["=== SECTION INTEGRITY CHECK ==="]
    for item in integrity:
        icon = "\u2705" if item["status"] == "ok" else "\u274c"
        lines.append(f"  {icon} {item['section']} [{item['status']}]")
    lines.append("")
    return lines


def format_diff_report(
    changes: list[DiffChange],
    integrity: list[SectionStatus] | None = None,
    max_text_len: int = 500,
) -> str:
    """Format a semantic diff and optional integrity check into a readable report.

    Args:
        changes: List of DiffChange from semantic_diff().
        integrity: Optional list from section_integrity_check().
        max_text_len: Truncate text snippets at this length.

    Returns:
        Multi-line report string.
    """
    lines = _format_changes(changes, max_text_len)
    if integrity:
        lines.extend(_format_integrity(integrity))
    return "\n".join(lines)
