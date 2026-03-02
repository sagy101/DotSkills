"""
confluence-publisher skill — Shared Page Operations

Low-level operations on Confluence pages that work directly with storage HTML
(no markdown conversion). Used by surgical_edit.py, diff_versions.py, and
page_versions.py.
"""

import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import requests

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from config_loader import (
    ConfluenceConfig,
    resolve_credentials,
)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class PageSnapshot:
    """A snapshot of a Confluence page at a specific version."""
    page_id: str
    title: str
    version: int
    html: str
    by: str
    when: str
    message: str = ""


@dataclass
class VersionInfo:
    """Summary of a single page version."""
    number: int
    by: str
    when: str
    message: str = ""


@dataclass
class DiffChange:
    """A single semantic change between two HTML strings."""
    change_type: str  # 'replace', 'insert', 'delete'
    old_text: str
    new_text: str


# ---------------------------------------------------------------------------
# Fetch operations (use REST API directly for version support)
# ---------------------------------------------------------------------------


def _wiki_base(config: ConfluenceConfig) -> str:
    """Return the base URL for the Confluence wiki REST API.

    Handles both ``https://host.atlassian.net`` and
    ``https://host.atlassian.net/wiki`` as ``confluence_url``.
    """
    url = config.confluence_url.rstrip("/")
    if not url.endswith("/wiki"):
        url += "/wiki"
    return url


def _rest_get(config: ConfluenceConfig, path: str, params: Optional[dict] = None):
    """Make a GET request to the Confluence REST API."""
    username, token = resolve_credentials(config)
    url = f"{_wiki_base(config)}/rest/api{path}"
    try:
        resp = requests.get(url, auth=(username, token), params=params or {}, timeout=60)
    except requests.RequestException as exc:
        print(f"ERROR: GET {path} failed: {exc}")
        sys.exit(1)
    if resp.status_code != 200:
        print(f"ERROR: GET {path} returned {resp.status_code}: {resp.text[:300]}")
        sys.exit(1)
    try:
        return resp.json()
    except ValueError:
        print(f"ERROR: GET {path} returned non-JSON response ({len(resp.text)} chars)")
        sys.exit(1)


def _rest_put(config: ConfluenceConfig, path: str, json_body: dict):
    """Make a PUT request to the Confluence REST API."""
    username, token = resolve_credentials(config)
    url = f"{_wiki_base(config)}/rest/api{path}"
    try:
        resp = requests.put(
            url, auth=(username, token),
            headers={"Content-Type": "application/json"},
            json=json_body,
            timeout=120,
        )
    except requests.RequestException as exc:
        print(f"ERROR: PUT {path} failed: {exc}")
        sys.exit(1)
    if resp.status_code != 200:
        print(f"ERROR: PUT {path} returned {resp.status_code}: {resp.text[:500]}")
        sys.exit(1)
    try:
        return resp.json()
    except ValueError:
        print(f"ERROR: PUT {path} returned non-JSON response ({len(resp.text)} chars)")
        sys.exit(1)


def fetch_page(
    config: ConfluenceConfig,
    page_id: str,
    version: Optional[int] = None,
) -> PageSnapshot:
    """Fetch a Confluence page, optionally at a specific version.

    Args:
        config: Confluence configuration.
        page_id: Numeric page ID.
        version: Version number to fetch. None = latest.

    Returns:
        PageSnapshot with title, version, HTML body, author, and timestamp.
    """
    params = {"expand": "body.storage,version"}
    if version is not None:
        params["status"] = "historical"
        params["version"] = str(version)

    data = _rest_get(config, f"/content/{page_id}", params)

    ver = data["version"]
    return PageSnapshot(
        page_id=page_id,
        title=data["title"],
        version=ver["number"],
        html=data["body"]["storage"]["value"],
        by=ver.get("by", {}).get("displayName", "unknown"),
        when=ver.get("when", ""),
        message=ver.get("message", ""),
    )


def list_versions(
    config: ConfluenceConfig,
    page_id: str,
    limit: int = 25,
) -> list[VersionInfo]:
    """List the version history of a page.

    Args:
        config: Confluence configuration.
        page_id: Numeric page ID.
        limit: Maximum number of versions to return.

    Returns:
        List of VersionInfo, newest first.
    """
    data = _rest_get(
        config,
        f"/content/{page_id}/version",
        params={"limit": str(limit)},
    )

    versions = []
    for v in data.get("results", []):
        versions.append(VersionInfo(
            number=v["number"],
            by=v.get("by", {}).get("displayName", "unknown"),
            when=v.get("when", ""),
            message=v.get("message", ""),
        ))
    return versions


def update_page_body(
    config: ConfluenceConfig,
    page_id: str,
    title: str,
    html: str,
    message: Optional[str] = None,
) -> int:
    """Push new HTML content as a new version of an existing page.

    Args:
        config: Confluence configuration.
        page_id: Numeric page ID.
        title: Page title (must match or be the new title).
        html: Full Confluence storage HTML body.
        message: Optional version message.

    Returns:
        The new version number.
    """
    current = _rest_get(config, f"/content/{page_id}", {"expand": "version"})
    current_version = current["version"]["number"]

    body = {
        "version": {"number": current_version + 1},
        "title": title,
        "type": "page",
        "body": {
            "storage": {
                "value": html,
                "representation": "storage",
            }
        },
    }
    if message:
        body["version"]["message"] = message

    result = _rest_put(config, f"/content/{page_id}", body)
    return result["version"]["number"]


# ---------------------------------------------------------------------------
# HTML normalization and diffing
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
            changes.append(DiffChange(
                change_type=tag,
                old_text=old_text,
                new_text=new_text,
            ))

    return changes


def section_integrity_check(
    old_html: str,
    new_html: str,
    markers: Optional[list[str]] = None,
) -> list[dict]:
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

    results = []
    for m in markers:
        in_old = m in old_html
        in_new = m in new_html
        if in_old == in_new:
            status = "ok"
        elif in_old:
            status = "MISSING"
        else:
            status = "ADDED"
        results.append({
            "section": m,
            "in_old": in_old,
            "in_new": in_new,
            "status": status,
        })
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


def _format_integrity(integrity: list[dict]) -> list[str]:
    """Format the integrity check results into report lines."""
    lines = ["=== SECTION INTEGRITY CHECK ==="]
    for item in integrity:
        icon = "\u2705" if item["status"] == "ok" else "\u274c"
        lines.append(f"  {icon} {item['section']} [{item['status']}]")
    lines.append("")
    return lines


def format_diff_report(
    changes: list[DiffChange],
    integrity: Optional[list[dict]] = None,
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
