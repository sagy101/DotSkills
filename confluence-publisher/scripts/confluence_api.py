"""
confluence-publisher skill — Confluence REST API Client

Version-aware REST operations on Confluence pages. Handles authentication,
URL normalization (/wiki prefix), and error handling for all API calls.

Used by surgical_edit.py, diff_versions.py, and page_versions.py.
"""

import sys
from dataclasses import dataclass
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


def _rest_get(
    config: ConfluenceConfig,
    path: str,
    params: dict[str, str] | None = None,
) -> dict[str, Any]:
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
        return resp.json()  # type: ignore[no-any-return]
    except ValueError:
        print(f"ERROR: GET {path} returned non-JSON response ({len(resp.text)} chars)")
        sys.exit(1)


def _rest_put(
    config: ConfluenceConfig,
    path: str,
    json_body: dict[str, Any],
) -> dict[str, Any]:
    """Make a PUT request to the Confluence REST API."""
    username, token = resolve_credentials(config)
    url = f"{_wiki_base(config)}/rest/api{path}"
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
) -> dict[str, Any]:
    """Make a POST request to the Confluence REST API."""
    username, token = resolve_credentials(config)
    url = f"{_wiki_base(config)}/rest/api{path}"
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
    comment_type: str  # "comment" for footer, "inline" for inline


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
    params = {
        "expand": "body.storage,version",
        "limit": str(limit),
    }
    # For footer comments: /content/{id}/child/comment
    # depth=all includes replies
    path = f"/content/{page_id}/child/comment"
    if comment_type == "inline":
        params["location"] = "inline"

    data = _rest_get(config, path, params)

    comments = []
    for item in data.get("results", []):
        author = item.get("version", {}).get("by", {}).get("displayName", "unknown")
        created = item.get("version", {}).get("when", "")
        body = item.get("body", {}).get("storage", {}).get("value", "")
        comments.append(
            PageComment(
                comment_id=str(item["id"]),
                body_html=body,
                author=author,
                created=created,
                comment_type=comment_type,
            )
        )
    return comments


def add_page_comment(
    config: ConfluenceConfig,
    page_id: str,
    body_html: str,
    comment_type: str = "comment",
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
        "type": comment_type,
        "container": {"id": page_id, "type": "page", "status": "current"},
        "body": {
            "storage": {
                "value": body_html,
                "representation": "storage",
            }
        },
    }
    result = _rest_post(config, "/content", payload)
    return str(result["id"])


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

    data = _rest_get(config, "/space", params)

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
