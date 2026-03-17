"""Shared thread-building and filtering logic for Bitbucket PR comments.

Used by pr_comments.py (display) and pr_comment.py (bulk resolve).
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Thread:
    """A comment thread: root comment + its replies."""

    root: dict
    children: list[dict] = field(default_factory=list)
    resolved: bool = False
    resolver: str | None = None
    resolved_on: str | None = None
    reply_count: int = 0
    file_path: str | None = None
    line: int | None = None

    @property
    def root_id(self) -> int:
        return int(self.root.get("id", 0))

    @property
    def root_author(self) -> str:
        return str(self.root.get("user", {}).get("display_name", "?"))


def build_threads(comments: list[dict[str, Any]]) -> list[Thread]:
    """Convert a flat comment list into Thread objects.

    Args:
        comments: Flat list from BitbucketClient.get_pr_comments()
                  (already enriched with resolution status).

    Returns:
        List of Thread objects, unresolved first, then by root comment creation time.
    """
    roots: list[dict] = []
    children_map: dict[int, list[dict]] = {}

    for c in comments:
        parent_id = (c.get("parent") or {}).get("id")
        if parent_id:
            children_map.setdefault(parent_id, []).append(c)
        else:
            roots.append(c)

    threads: list[Thread] = []
    for root in roots:
        rid = root.get("id", 0)
        kids = children_map.get(rid, [])
        # Sort children by creation time
        kids.sort(key=lambda c: c.get("created_on", ""))

        resolution = root.get("resolution")
        resolved = bool(resolution and resolution.get("type"))

        resolver = None
        resolved_on = None
        if resolved and resolution:
            resolver = resolution.get("user", {}).get("display_name")
            resolved_on = (resolution.get("created_on") or "")[:19]

        inline = root.get("inline")
        file_path = inline.get("path") if inline else None
        line = inline.get("to") if inline else None

        threads.append(
            Thread(
                root=root,
                children=kids,
                resolved=resolved,
                resolver=resolver,
                resolved_on=resolved_on,
                reply_count=len(kids),
                file_path=file_path,
                line=line,
            )
        )

    # Sort: unresolved first, then by creation time
    threads.sort(key=lambda t: (t.resolved, t.root.get("created_on", "")))
    return threads


def filter_threads(
    threads: list[Thread],
    *,
    status: str = "all",
    author: str | None = None,
    file: str | None = None,
    has_replies: bool | None = None,
) -> list[Thread]:
    """Filter threads. All filters are AND-combined.

    Args:
        status: "resolved", "unresolved", or "all".
        author: Substring match (case-insensitive) on root comment author.
        file: Substring match (case-insensitive) on inline file path.
        has_replies: True = only threads with replies, False = only without, None = all.
    """
    result = threads

    if status == "resolved":
        result = [t for t in result if t.resolved]
    elif status == "unresolved":
        result = [t for t in result if not t.resolved]

    if author:
        author_lower = author.lower()
        result = [t for t in result if author_lower in t.root_author.lower()]

    if file:
        file_lower = file.lower()
        result = [t for t in result if t.file_path and file_lower in t.file_path.lower()]

    if has_replies is True:
        result = [t for t in result if t.reply_count > 0]
    elif has_replies is False:
        result = [t for t in result if t.reply_count == 0]

    return result
