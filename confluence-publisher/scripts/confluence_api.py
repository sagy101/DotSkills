"""
confluence-publisher skill — Confluence REST API Client

Version-aware REST operations on Confluence pages. Handles authentication,
URL normalization (/wiki prefix), and error handling for all API calls.

Used by surgical_edit.py, diff_versions.py, and page_versions.py.
"""

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import requests  # type: ignore[import-untyped]

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from confluence_config import (  # noqa: E402
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


# ---------------------------------------------------------------------------
# REST transport
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


def _api_base(config: ConfluenceConfig, api_version: str) -> str:
    """Return the Confluence REST base for the requested API version."""
    if api_version == "v2":
        return f"{_wiki_base(config)}/api/v2"
    return f"{_wiki_base(config)}/rest/api"


def _rest_get(
    config: ConfluenceConfig,
    path: str,
    params: dict[str, str] | None = None,
    *,
    api_version: str = "v1",
) -> dict[str, Any]:
    """Make a GET request to the Confluence REST API."""
    username, token = resolve_credentials(config)
    url = f"{_api_base(config, api_version)}{path}"
    try:
        resp = requests.get(url, auth=(username, token), params=params or {}, timeout=60)
    except requests.RequestException as exc:
        print(f"ERROR: GET {path} failed: {exc}")
        sys.exit(1)
    if resp.status_code != 200:
        print(f"ERROR: GET {path} returned {resp.status_code}: {resp.text[:300]}")
        sys.exit(1)
    try:
        return resp.json()  # type: ignore[no-any-return]
    except ValueError:
        print(f"ERROR: GET {path} returned non-JSON response ({len(resp.text)} chars)")
        sys.exit(1)


def _rest_put(
    config: ConfluenceConfig,
    path: str,
    json_body: dict[str, Any],
    *,
    api_version: str = "v1",
) -> dict[str, Any]:
    """Make a PUT request to the Confluence REST API."""
    username, token = resolve_credentials(config)
    url = f"{_api_base(config, api_version)}{path}"
    try:
        resp = requests.put(
            url,
            auth=(username, token),
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
        return resp.json()  # type: ignore[no-any-return]
    except ValueError:
        print(f"ERROR: PUT {path} returned non-JSON response ({len(resp.text)} chars)")
        sys.exit(1)


def _rest_post(
    config: ConfluenceConfig,
    path: str,
    json_body: dict[str, Any],
    *,
    api_version: str = "v1",
) -> dict[str, Any]:
    """Make a POST request to the Confluence REST API."""
    username, token = resolve_credentials(config)
    url = f"{_api_base(config, api_version)}{path}"
    try:
        resp = requests.post(
            url,
            auth=(username, token),
            headers={"Content-Type": "application/json"},
            json=json_body,
            timeout=120,
        )
    except requests.RequestException as exc:
        print(f"ERROR: POST {path} failed: {exc}")
        sys.exit(1)
    if resp.status_code not in (200, 201):
        print(f"ERROR: POST {path} returned {resp.status_code}: {resp.text[:500]}")
        sys.exit(1)
    try:
        return resp.json()  # type: ignore[no-any-return]
    except ValueError:
        print(f"ERROR: POST {path} returned non-JSON response ({len(resp.text)} chars)")
        sys.exit(1)


def _rest_delete(config: ConfluenceConfig, path: str, *, api_version: str = "v1") -> None:
    """Make a DELETE request to the Confluence REST API."""
    username, token = resolve_credentials(config)
    url = f"{_api_base(config, api_version)}{path}"
    try:
        resp = requests.delete(url, auth=(username, token), timeout=60)
    except requests.RequestException as exc:
        print(f"ERROR: DELETE {path} failed: {exc}")
        sys.exit(1)
    if resp.status_code not in (200, 202, 204):
        print(f"ERROR: DELETE {path} returned {resp.status_code}: {resp.text[:300]}")
        sys.exit(1)


# ---------------------------------------------------------------------------
# Page operations
# ---------------------------------------------------------------------------


def fetch_page(
    config: ConfluenceConfig,
    page_id: str,
    version: int | None = None,
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

    return [
        VersionInfo(
            number=v["number"],
            by=v.get("by", {}).get("displayName", "unknown"),
            when=v.get("when", ""),
            message=v.get("message", ""),
        )
        for v in data.get("results", [])
    ]


def update_page_body(
    config: ConfluenceConfig,
    page_id: str,
    title: str,
    html: str,
    message: str | None = None,
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

    version_info: dict[str, Any] = {"number": current_version + 1}
    body = {
        "version": version_info,
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
        version_info["message"] = message

    result = _rest_put(config, f"/content/{page_id}", body)
    return result["version"]["number"]  # type: ignore[no-any-return]


# ---------------------------------------------------------------------------
# CQL Search
# ---------------------------------------------------------------------------


@dataclass
class SearchResult:
    """A single CQL search result."""

    content_id: str
    title: str
    content_type: str
    space_key: str
    url: str
    excerpt: str = ""


def search_cql(
    config: ConfluenceConfig,
    cql: str,
    limit: int = 25,
) -> list[SearchResult]:
    """Search Confluence content using a CQL query.

    Args:
        config: Confluence configuration.
        cql: CQL query string (e.g. 'type=page AND space=DOCS AND title~"API"').
        limit: Maximum results to return.

    Returns:
        List of SearchResult objects.
    """
    data = _rest_get(
        config,
        "/search",
        params={"cql": cql, "limit": str(limit)},
    )

    results = []
    for item in data.get("results", []):
        content = item.get("content", item)
        space = content.get("space", {}) or content.get("_expandable", {})
        results.append(
            SearchResult(
                content_id=str(content.get("id", "")),
                title=content.get("title", ""),
                content_type=content.get("type", ""),
                space_key=space.get("key", ""),
                url=item.get("url", ""),
                excerpt=item.get("excerpt", ""),
            )
        )
    return results


# ---------------------------------------------------------------------------
# Comments
# ---------------------------------------------------------------------------


@dataclass
class PageComment:
    """A Confluence page comment."""

    comment_id: str
    body_html: str
    author: str
    created: str
    page_id: str
    parent_comment_id: str = ""
    comment_type: str = "comment"  # "comment" for footer, "inline" for inline
    resolved: bool = False
    like_count: int = 0
    like_users: list[str] = field(default_factory=list)


@dataclass
class PageInfo:
    """A page returned by the v2 pages-in-space endpoint."""

    page_id: str
    title: str
    space_id: str
    status: str
    subtype: str = ""
    parent_id: str = ""
    version: int = 0
    url: str = ""


def _comment_path(comment_type: str, comment_id: str | None = None) -> str:
    kind = "inline-comments" if comment_type == "inline" else "footer-comments"
    return f"/{kind}" if comment_id is None else f"/{kind}/{comment_id}"


def _extract_like_users(data: Any) -> list[str]:
    if isinstance(data, dict):
        results = data.get("results", [])
        users = []
        for item in results:
            if isinstance(item, dict):
                account_id = item.get("accountId")
                if account_id:
                    users.append(str(account_id))
            elif item is not None:
                users.append(str(item))
        return users
    if isinstance(data, list):
        return [str(item) for item in data]
    return []


def get_page_comments(
    config: ConfluenceConfig,
    page_id: str,
    comment_type: str = "comment",
    limit: int = 50,
) -> list[PageComment]:
    """Fetch comments on a page.

    Args:
        config: Confluence configuration.
        page_id: Numeric page ID.
        comment_type: 'comment' for footer comments, 'inline' for inline comments.
        limit: Maximum comments to return.

    Returns:
        List of PageComment objects.
    """
    return list_page_comments(config, page_id, comment_type=comment_type, limit=limit)


def list_page_comments(
    config: ConfluenceConfig,
    page_id: str,
    comment_type: str = "comment",
    limit: int = 50,
    resolution_status: str | None = None,
) -> list[PageComment]:
    """List footer or inline comments for a page using REST v2."""
    params: dict[str, str] = {
        "body-format": "storage",
        "limit": str(limit),
    }
    if comment_type == "inline" and resolution_status:
        params["resolution-status"] = resolution_status

    data = _rest_get(
        config,
        _comment_path(comment_type)
        .replace("/footer-comments", f"/pages/{page_id}/footer-comments")
        .replace("/inline-comments", f"/pages/{page_id}/inline-comments"),
        params,
        api_version="v2",
    )

    comments: list[PageComment] = []
    for item in data.get("results", []):
        version = item.get("version", {})
        author = version.get("by", {}).get("displayName") or version.get("authorId", "unknown")
        created = version.get("when") or version.get("createdAt", "")
        body = item.get("body", {}).get("storage", {}).get("value", "")
        like_info = item.get("likes", {})
        comments.append(
            PageComment(
                comment_id=str(item["id"]),
                page_id=str(item.get("pageId", page_id)),
                parent_comment_id=str(item.get("parentCommentId", "")),
                body_html=body,
                author=author,
                created=created,
                comment_type=comment_type,
                resolved=bool(item.get("resolved", item.get("resolutionStatus") == "resolved")),
                like_count=len(like_info.get("results", [])) if isinstance(like_info, dict) else 0,
                like_users=_extract_like_users(like_info),
            )
        )
    return comments


def list_comment_children(
    config: ConfluenceConfig,
    comment_id: str,
    comment_type: str = "comment",
    limit: int = 50,
) -> list[PageComment]:
    """List direct child comments of a footer or inline comment."""
    params = {"body-format": "storage", "limit": str(limit)}
    data = _rest_get(
        config,
        f"{_comment_path(comment_type, comment_id)}/children",
        params,
        api_version="v2",
    )
    children: list[PageComment] = []
    for item in data.get("results", []):
        version = item.get("version", {})
        author = version.get("by", {}).get("displayName") or version.get("authorId", "unknown")
        created = version.get("when") or version.get("createdAt", "")
        body = item.get("body", {}).get("storage", {}).get("value", "")
        like_info = item.get("likes", {})
        children.append(
            PageComment(
                comment_id=str(item["id"]),
                body_html=body,
                author=author,
                created=created,
                page_id=str(item.get("pageId", "")),
                parent_comment_id=str(item.get("parentCommentId", comment_id)),
                comment_type=str(item.get("type", comment_type)),
                resolved=bool(item.get("resolved", item.get("resolutionStatus") == "resolved")),
                like_count=len(like_info.get("results", [])) if isinstance(like_info, dict) else 0,
                like_users=_extract_like_users(like_info),
            )
        )
    return children


def walk_comment_thread(
    config: ConfluenceConfig,
    page_id: str,
    comment_type: str = "comment",
    limit: int = 50,
) -> list[PageComment]:
    """Return root comments and all descendants in depth-first order."""
    roots = list_page_comments(config, page_id, comment_type=comment_type, limit=limit)
    ordered: list[PageComment] = []

    def _walk(comment: PageComment) -> None:
        ordered.append(comment)
        for child in list_comment_children(
            config, comment.comment_id, comment_type=comment_type, limit=limit
        ):
            _walk(child)

    for root in roots:
        _walk(root)
    return ordered


def add_page_comment(
    config: ConfluenceConfig,
    page_id: str,
    body_html: str,
    comment_type: str = "comment",
    parent_comment_id: str | None = None,
    inline_text_selection: str | None = None,
    inline_text_selection_match_count: int | None = None,
    inline_text_selection_match_index: int | None = None,
) -> str:
    """Add a comment to a page.

    Args:
        config: Confluence configuration.
        page_id: Numeric page ID.
        body_html: Comment body in Confluence storage format (HTML).
        comment_type: 'comment' for footer, not used for inline (inline requires
            additional selection context not supported here).

    Returns:
        The created comment ID.
    """
    payload: dict[str, Any] = {
        "body": {
            "representation": "storage",
            "value": body_html,
        },
    }
    if parent_comment_id:
        payload["parentCommentId"] = parent_comment_id
    else:
        payload["pageId"] = page_id

    if comment_type == "inline":
        if not inline_text_selection:
            print("ERROR: inline comments require inline_text_selection")
            sys.exit(1)
        payload["inlineCommentProperties"] = {"textSelection": inline_text_selection}
        if inline_text_selection_match_count is not None:
            payload["inlineCommentProperties"]["textSelectionMatchCount"] = (
                inline_text_selection_match_count
            )
        if inline_text_selection_match_index is not None:
            payload["inlineCommentProperties"]["textSelectionMatchIndex"] = (
                inline_text_selection_match_index
            )
        result = _rest_post(config, "/inline-comments", payload, api_version="v2")
    else:
        result = _rest_post(config, "/footer-comments", payload, api_version="v2")
    return str(result["id"])


def reply_to_comment(
    config: ConfluenceConfig,
    page_id: str,
    parent_comment_id: str,
    body_html: str,
    comment_type: str = "comment",
) -> str:
    """Reply to a footer comment."""
    return add_page_comment(
        config,
        page_id,
        body_html,
        comment_type=comment_type,
        parent_comment_id=parent_comment_id,
    )


def edit_comment(
    config: ConfluenceConfig,
    comment_id: str,
    body_html: str,
    comment_type: str = "comment",
    resolved: bool | None = None,
) -> str:
    """Update a footer or inline comment."""
    current = _rest_get(
        config,
        _comment_path(comment_type, comment_id),
        params={"include-version": "true", "body-format": "storage"},
        api_version="v2",
    )
    current_version = int(current.get("version", {}).get("number", 0))
    payload: dict[str, Any] = {
        "version": {"number": current_version + 1},
        "body": {"representation": "storage", "value": body_html},
    }
    base = current.get("_links", {}).get("base")
    if base:
        payload["_links"] = {"base": base}
    if comment_type == "inline" and resolved is not None:
        payload["resolved"] = resolved
    result = _rest_put(config, _comment_path(comment_type, comment_id), payload, api_version="v2")
    return str(result.get("id", comment_id))


def delete_comment(
    config: ConfluenceConfig, comment_id: str, comment_type: str = "comment"
) -> None:
    """Delete a footer or inline comment."""
    _rest_delete(config, _comment_path(comment_type, comment_id), api_version="v2")


def resolve_comment(config: ConfluenceConfig, comment_id: str, comment_type: str = "inline") -> str:
    """Resolve an inline comment."""
    return edit_comment(
        config,
        comment_id,
        _rest_get(
            config,
            _comment_path(comment_type, comment_id),
            params={"body-format": "storage"},
            api_version="v2",
        )
        .get("body", {})
        .get("storage", {})
        .get("value", ""),
        comment_type=comment_type,
        resolved=True,
    )


def unresolve_comment(
    config: ConfluenceConfig, comment_id: str, comment_type: str = "inline"
) -> str:
    """Unresolve an inline comment."""
    current = _rest_get(
        config,
        _comment_path(comment_type, comment_id),
        params={"body-format": "storage"},
        api_version="v2",
    )
    body = current.get("body", {}).get("storage", {}).get("value", "")
    return edit_comment(config, comment_id, body, comment_type=comment_type, resolved=False)


def get_page_like_count(config: ConfluenceConfig, page_id: str) -> int:
    data = _rest_get(config, f"/pages/{page_id}/likes/count", api_version="v2")
    if isinstance(data, dict):
        return int(data.get("count", 0))
    return int(data)


def get_page_like_users(config: ConfluenceConfig, page_id: str) -> list[str]:
    data = _rest_get(config, f"/pages/{page_id}/likes/users", api_version="v2")
    return _extract_like_users(data)


def get_comment_like_count(
    config: ConfluenceConfig,
    comment_id: str,
    comment_type: str = "comment",
) -> int:
    data = _rest_get(
        config,
        f"{_comment_path(comment_type, comment_id)}/likes/count",
        api_version="v2",
    )
    if isinstance(data, dict):
        return int(data.get("count", 0))
    return int(data)


def get_comment_like_users(
    config: ConfluenceConfig,
    comment_id: str,
    comment_type: str = "comment",
) -> list[str]:
    data = _rest_get(
        config,
        f"{_comment_path(comment_type, comment_id)}/likes/users",
        api_version="v2",
    )
    return _extract_like_users(data)


# ---------------------------------------------------------------------------
# Spaces
# ---------------------------------------------------------------------------


@dataclass
class SpaceInfo:
    """Summary of a Confluence space."""

    key: str
    name: str
    space_type: str
    status: str
    url: str = ""


@dataclass
class PageListItem:
    """A page from the v2 pages-in-space listing."""

    page_id: str
    title: str
    space_id: str
    status: str
    subtype: str = ""
    parent_id: str = ""
    version: int = 0
    url: str = ""


def _resolve_space_id(config: ConfluenceConfig, space_key: str) -> str:
    data = _rest_get(config, "/spaces", {"keys": space_key, "limit": "1"}, api_version="v2")
    results = data.get("results", [])
    if not results:
        print(f"ERROR: Could not resolve space key '{space_key}' to a space id")
        sys.exit(1)
    return str(results[0]["id"])


def list_pages(
    config: ConfluenceConfig,
    space_key: str | None = None,
    title: str | None = None,
    status: str | None = None,
    page_type: str | None = None,
    limit: int = 50,
) -> list[PageListItem]:
    """List pages in a space using the v2 pages endpoint."""
    key = space_key or config.space_key
    space_id = _resolve_space_id(config, key)
    params: dict[str, str] = {"limit": str(limit)}
    if title:
        params["title"] = title
    if status:
        params["status"] = status
    data = _rest_get(config, f"/spaces/{space_id}/pages", params, api_version="v2")
    pages: list[PageListItem] = []
    for item in data.get("results", []):
        subtype = str(item.get("subtype", ""))
        if page_type and subtype != page_type:
            continue
        version = item.get("version", {}) or {}
        links = item.get("_links", {}) or {}
        pages.append(
            PageListItem(
                page_id=str(item.get("id", "")),
                title=item.get("title", ""),
                space_id=str(item.get("spaceId", space_id)),
                status=item.get("status", ""),
                subtype=subtype,
                parent_id=str(item.get("parentId", "")),
                version=int(version.get("number", 0) or 0),
                url=str(links.get("webui", "")),
            )
        )
    return pages


def list_spaces(
    config: ConfluenceConfig,
    space_type: str | None = None,
    limit: int = 50,
) -> list[SpaceInfo]:
    """List Confluence spaces.

    Args:
        config: Confluence configuration.
        space_type: Optional filter: 'global' or 'personal'.
        limit: Maximum spaces to return.

    Returns:
        List of SpaceInfo objects.
    """
    params: dict[str, str] = {"limit": str(limit)}
    if space_type:
        params["type"] = space_type

    data = _rest_get(config, "/spaces", params, api_version="v2")

    spaces = []
    for item in data.get("results", []):
        links = item.get("_links", {})
        base = links.get("base", "")
        webui = links.get("webui", "")
        spaces.append(
            SpaceInfo(
                key=item.get("key", ""),
                name=item.get("name", ""),
                space_type=item.get("type", ""),
                status=item.get("status", ""),
                url=f"{base}{webui}" if base and webui else "",
            )
        )
    return spaces
