"""
confluence-publisher skill — Confluence REST API Client

Version-aware REST operations on Confluence pages. Handles authentication,
URL normalization (/wiki prefix), and error handling for all API calls.

Used by surgical_edit.py, diff_versions.py, and page_versions.py.
"""

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

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
    params: Optional[dict[str, str]] = None,
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
        return resp.json()
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


# ---------------------------------------------------------------------------
# Page operations
# ---------------------------------------------------------------------------


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
