"""
Page reference utilities for confluence-publisher skill scripts.

Extracted from confluence_config.py to reduce module coupling.
Contains: page ID extraction, tiny link encoding/decoding, title resolution,
and child page pagination.
"""

import base64
import re
import struct
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from atlassian import Confluence
    from confluence_config import ConfluenceConfig


def get_all_children(confluence: "Confluence", page_id: str) -> list[dict[str, Any]]:
    """Fetch all child pages with pagination (handles >100 children)."""
    all_children: list[dict[str, Any]] = []
    start = 0
    limit = 100
    while True:
        batch = confluence.get_page_child_by_type(
            page_id=page_id, type="page", start=start, limit=limit
        )
        if not batch:
            break
        all_children.extend(batch)
        if len(batch) < limit:
            break
        start += limit
    return all_children


def decode_tiny_link(tiny_id: str) -> int:
    """Decode a Confluence tiny link ID to a numeric page ID.

    Confluence tiny links encode the page ID as a little-endian unsigned 32-bit
    integer, stripped of trailing zero bytes, then base64-encoded with URL-safe
    altchars (_-) and padding removed.

    Args:
        tiny_id: The encoded portion after ``/x/`` in a tiny link URL.

    Returns:
        The decoded numeric page ID.
    """
    raw = tiny_id.encode("ascii") if isinstance(tiny_id, str) else tiny_id
    # The encoding strips trailing 'A' chars (base64 zeros) and '=' padding.
    # Restore to a valid base64 length: data chars mod 4 must be 0, 2, or 3.
    remainder = len(raw) % 4
    if remainder == 1:
        raw += b"A"
        remainder = 2
    raw += b"=" * ((4 - remainder) % 4)
    page_id_bytes = (base64.b64decode(raw, altchars=b"_-") + b"\x00\x00\x00\x00")[:4]
    return struct.unpack("<L", page_id_bytes)[0]  # type: ignore[no-any-return]


def encode_tiny_id(page_id: int) -> str:
    """Encode a numeric page ID into a Confluence tiny link ID.

    Inverse of :func:`decode_tiny_link`.
    """
    return (
        base64.b64encode(struct.pack("<L", int(page_id)).rstrip(b"\x00"), altchars=b"_-")
        .rstrip(b"=")
        .decode("ascii")
    )


_TINY_LINK_RE = re.compile(r"/x/([-_A-Za-z0-9]+)")


def extract_page_id(page_ref: str) -> str:
    """Extract a numeric page ID from a page reference.

    Accepts:
      - A plain numeric ID (``"774112245"``)
      - A standard Confluence URL containing ``/pages/<id>``
      - A Confluence tiny link containing ``/x/<encoded>``

    Returns:
        The page ID as a string.

    Raises:
        ValueError: If the reference format is not recognised.
    """
    if page_ref.isdigit():
        return page_ref
    match = re.search(r"/pages/(\d+)", page_ref)
    if match:
        return match.group(1)
    tiny_match = _TINY_LINK_RE.search(page_ref)
    if tiny_match:
        return str(decode_tiny_link(tiny_match.group(1)))
    raise ValueError(f"Could not extract page ID from: {page_ref}")


def strip_title_heading(md_content: str, title: str) -> str:
    """Strip the first H1 heading if it matches *title*.

    Confluence displays the page title in its own header, so keeping the
    identical H1 inside the body produces a visual duplicate.
    """
    h1_match = re.match(r"^#\s+(.+?)(\s*\n)", md_content)
    if h1_match and h1_match.group(1).strip() == title.strip():
        return md_content[h1_match.end() :]
    return md_content


def resolve_title(file_path: str, md_content: str, config: "ConfluenceConfig") -> str:
    """Resolve page title using: title_map > first heading > filename."""
    # 1. Explicit title_map
    if file_path in config.title_map:
        return config.title_map[file_path]  # type: ignore[no-any-return]

    # 2. First # heading in the markdown
    match = re.search(r"^#\s+(.+)$", md_content, re.MULTILINE)
    if match:
        return match.group(1).strip()

    # 3. Filename-based
    name = Path(file_path).stem
    if name.lower() == "readme":
        # Use parent directory name
        parent = Path(file_path).parent.name
        if parent and parent != ".":
            name = parent
    return name.replace("-", " ").replace("_", " ").title()
