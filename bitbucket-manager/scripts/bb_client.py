"""
Low-level Bitbucket Cloud REST API v2 client.

Pure stdlib (urllib + json + base64). Zero pip dependencies.
"""

import base64
import json
import os
import socket
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

from bb_config import BitbucketConfig, resolve_credentials

_DEBUG = os.environ.get("BB_DEBUG", "").lower() in ("1", "true", "yes")
_BASE_URL = "https://api.bitbucket.org/2.0"


class BitbucketClient:
    """Thin wrapper around Bitbucket Cloud REST API v2."""

    def __init__(self, config: BitbucketConfig):
        self.config = config
        email, app_password = resolve_credentials(config)
        creds = base64.b64encode(f"{email}:{app_password}".encode()).decode()
        self._headers = {
            "Authorization": f"Basic {creds}",
            "Content-Type": "application/json",
        }

    # -----------------------------------------------------------------
    # Low-level HTTP
    # -----------------------------------------------------------------
    def _request(
        self,
        method: str,
        path: str,
        data: Optional[dict] = None,
        params: Optional[dict] = None,
    ) -> Any:
        """Execute an HTTP request against the Bitbucket REST API."""
        url = f"{_BASE_URL}{path}"
        if params:
            qs = "&".join(
                f"{urllib.parse.quote(str(k))}={urllib.parse.quote(str(v))}"
                for k, v in params.items()
            )
            url = f"{url}?{qs}"

        # Always send a JSON body for POST/PUT — Bitbucket rejects
        # Content-Type: application/json with no body on some endpoints.
        if data is not None:
            body = json.dumps(data).encode()
        elif method in ("POST", "PUT"):
            body = b"{}"
        else:
            body = None
        req = urllib.request.Request(
            url, data=body, headers=self._headers, method=method,
        )

        if _DEBUG:
            print(f"DEBUG: {method} {url}", file=sys.stderr)
            if body:
                print(f"DEBUG: body={body[:500]}", file=sys.stderr)

        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                if resp.status == 204:
                    return {}
                raw = resp.read().decode()
                return json.loads(raw) if raw else {}
        except socket.timeout:
            print(f"ERROR: Request timed out (60s) {method} {path}", file=sys.stderr)
            raise
        except urllib.error.HTTPError as e:
            error_body = e.read().decode()
            try:
                error_json = json.loads(error_body)
                msg = error_json.get("error", {}).get("message", "")
                detail = msg if msg else error_body[:500]
            except (json.JSONDecodeError, AttributeError):
                detail = error_body[:500] if _DEBUG else f"HTTP {e.code} (set BB_DEBUG=1 for details)"
            print(f"ERROR {e.code} {method} {path}: {detail}", file=sys.stderr)
            raise
        except urllib.error.URLError as e:
            if isinstance(e.reason, (socket.timeout, TimeoutError)):
                print(f"ERROR: Request timed out (60s) {method} {path}", file=sys.stderr)
            else:
                print(f"ERROR: URL error {method} {path}: {e.reason}", file=sys.stderr)
            raise

    def _paginate(
        self,
        path: str,
        params: Optional[dict] = None,
        max_results: int = 0,
    ) -> List[dict]:
        """Fetch all pages from a paginated Bitbucket API endpoint.

        Args:
            max_results: Maximum total items to return. 0 = unlimited.
        """
        all_items: List[dict] = []
        unlimited = max_results == 0
        remaining = max_results if not unlimited else float("inf")
        current_params = dict(params) if params else {}

        while remaining > 0:
            page_size = 50 if unlimited else min(int(remaining), 50)
            current_params["pagelen"] = str(page_size)
            result = self._request("GET", path, params=current_params)
            items = result.get("values", [])
            if not items:
                break
            all_items.extend(items)
            remaining -= len(items)
            next_url = result.get("next")
            if not next_url:
                break
            # Parse next URL to extract query params for the next request
            parsed = urllib.parse.urlparse(next_url)
            current_params = dict(urllib.parse.parse_qsl(parsed.query))

        return all_items

    # -----------------------------------------------------------------
    # Pull Request CRUD
    # -----------------------------------------------------------------
    def create_pr(
        self,
        workspace: str,
        repo_slug: str,
        title: str,
        source_branch: str,
        destination_branch: str,
        description: str = "",
        reviewers: Optional[List[str]] = None,
        close_source_branch: bool = False,
    ) -> dict:
        """Create a pull request."""
        payload: Dict[str, Any] = {
            "title": title,
            "source": {"branch": {"name": source_branch}},
            "destination": {"branch": {"name": destination_branch}},
            "close_source_branch": close_source_branch,
        }
        if description:
            payload["description"] = description
        if reviewers:
            payload["reviewers"] = [{"uuid": r} for r in reviewers]
        return self._request(
            "POST",
            f"/repositories/{workspace}/{repo_slug}/pullrequests",
            data=payload,
        )

    def update_pr(
        self,
        workspace: str,
        repo_slug: str,
        pr_id: int,
        **fields: Any,
    ) -> dict:
        """Update a pull request. Accepts title, description, destination, reviewers."""
        payload: Dict[str, Any] = {}
        if "title" in fields:
            payload["title"] = fields["title"]
        if "description" in fields:
            payload["description"] = fields["description"]
        if "destination" in fields:
            payload["destination"] = {"branch": {"name": fields["destination"]}}
        if "reviewers" in fields:
            payload["reviewers"] = [{"uuid": r} for r in fields["reviewers"]]
        return self._request(
            "PUT",
            f"/repositories/{workspace}/{repo_slug}/pullrequests/{pr_id}",
            data=payload,
        )

    def get_pr(self, workspace: str, repo_slug: str, pr_id: int) -> dict:
        """Fetch a single pull request by ID."""
        return self._request(
            "GET",
            f"/repositories/{workspace}/{repo_slug}/pullrequests/{pr_id}",
        )

    def list_prs(
        self,
        workspace: str,
        repo_slug: str,
        state: str = "OPEN",
        max_results: int = 50,
    ) -> List[dict]:
        """List pull requests with optional state filter."""
        params = {"state": state}
        return self._paginate(
            f"/repositories/{workspace}/{repo_slug}/pullrequests",
            params=params,
            max_results=max_results,
        )

    def merge_pr(
        self,
        workspace: str,
        repo_slug: str,
        pr_id: int,
        merge_strategy: str = "merge_commit",
        close_source_branch: bool = False,
        message: Optional[str] = None,
    ) -> dict:
        """Merge a pull request."""
        payload: Dict[str, Any] = {
            "type": merge_strategy,
            "close_source_branch": close_source_branch,
        }
        if message:
            payload["message"] = message
        return self._request(
            "POST",
            f"/repositories/{workspace}/{repo_slug}/pullrequests/{pr_id}/merge",
            data=payload,
        )

    def decline_pr(self, workspace: str, repo_slug: str, pr_id: int) -> dict:
        """Decline a pull request."""
        return self._request(
            "POST",
            f"/repositories/{workspace}/{repo_slug}/pullrequests/{pr_id}/decline",
        )

    # -----------------------------------------------------------------
    # PR Comments
    # -----------------------------------------------------------------
    def add_pr_comment(
        self,
        workspace: str,
        repo_slug: str,
        pr_id: int,
        body: str,
        inline: Optional[Dict[str, Any]] = None,
    ) -> dict:
        """Add a comment to a PR. Pass inline dict for file-level comments."""
        payload: Dict[str, Any] = {
            "content": {"raw": body},
        }
        if inline:
            payload["inline"] = inline
        return self._request(
            "POST",
            f"/repositories/{workspace}/{repo_slug}/pullrequests/{pr_id}/comments",
            data=payload,
        )

    def get_pr_comments(
        self,
        workspace: str,
        repo_slug: str,
        pr_id: int,
        max_results: int = 0,
    ) -> List[dict]:
        """List all comments on a PR."""
        return self._paginate(
            f"/repositories/{workspace}/{repo_slug}/pullrequests/{pr_id}/comments",
            max_results=max_results,
        )

    # -----------------------------------------------------------------
    # PR Statuses / Checks
    # -----------------------------------------------------------------
    def get_pr_statuses(
        self,
        workspace: str,
        repo_slug: str,
        pr_id: int,
    ) -> List[dict]:
        """Fetch build/pipeline status checks for a PR."""
        return self._paginate(
            f"/repositories/{workspace}/{repo_slug}/pullrequests/{pr_id}/statuses",
        )

    # -----------------------------------------------------------------
    # Build Status (commit-level)
    # -----------------------------------------------------------------
    def get_commit_statuses(
        self,
        workspace: str,
        repo_slug: str,
        commit_sha: str,
    ) -> List[dict]:
        """Fetch build statuses for a specific commit."""
        return self._paginate(
            f"/repositories/{workspace}/{repo_slug}/commit/{commit_sha}/statuses",
        )

    # -----------------------------------------------------------------
    # Repo
    # -----------------------------------------------------------------
    def list_repos(
        self,
        workspace: str,
        max_results: int = 50,
        q: Optional[str] = None,
    ) -> List[dict]:
        """List repositories in a workspace."""
        params: Dict[str, str] = {}
        if q:
            params["q"] = q
        return self._paginate(
            f"/repositories/{workspace}",
            params=params,
            max_results=max_results,
        )

    # -----------------------------------------------------------------
    # Utility
    # -----------------------------------------------------------------
    def test_connection(self, workspace: str) -> bool:
        """Test connectivity and credentials."""
        try:
            self._request("GET", f"/repositories/{workspace}", params={"pagelen": "1"})
            return True
        except (urllib.error.HTTPError, urllib.error.URLError):
            return False
