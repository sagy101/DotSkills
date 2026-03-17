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
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from bb_config import BitbucketConfig, resolve_credentials

_DEBUG = os.environ.get("BB_DEBUG", "").lower() in ("1", "true", "yes")
_BASE_URL = "https://api.bitbucket.org/2.0"


class BitbucketClient:
    """Thin wrapper around Bitbucket Cloud REST API v2."""

    def __init__(self, config: BitbucketConfig) -> None:
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
        data: dict | None = None,
        params: dict | None = None,
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
            url,
            data=body,
            headers=self._headers,
            method=method,
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
        except TimeoutError:
            print(f"ERROR: Request timed out (60s) {method} {path}", file=sys.stderr)
            raise
        except urllib.error.HTTPError as e:
            error_body = e.read().decode()
            try:
                error_json = json.loads(error_body)
                msg = error_json.get("error", {}).get("message", "")
                detail = msg if msg else error_body[:500]
            except (json.JSONDecodeError, AttributeError):
                detail = (
                    error_body[:500] if _DEBUG else f"HTTP {e.code} (set BB_DEBUG=1 for details)"
                )
            print(f"ERROR {e.code} {method} {path}: {detail}", file=sys.stderr)
            raise
        except urllib.error.URLError as e:
            if isinstance(e.reason, socket.timeout | TimeoutError):
                print(f"ERROR: Request timed out (60s) {method} {path}", file=sys.stderr)
            else:
                print(f"ERROR: URL error {method} {path}: {e.reason}", file=sys.stderr)
            raise

    def _paginate(
        self,
        path: str,
        params: dict | None = None,
        max_results: int = 0,
    ) -> list[dict]:
        """Fetch all pages from a paginated Bitbucket API endpoint.

        Args:
            max_results: Maximum total items to return. 0 = unlimited.
        """
        all_items: list[dict] = []
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

    def _parallel_fetch(
        self,
        callables: list,
        max_workers: int = 5,
    ) -> list:
        """Execute multiple zero-arg callables in parallel, return results in order."""
        results = [None] * len(callables)
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {pool.submit(fn): i for i, fn in enumerate(callables)}
            for f in as_completed(futures):
                results[futures[f]] = f.result()
        return results

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
        reviewers: list[str] | None = None,
        close_source_branch: bool = False,
    ) -> dict:
        """Create a pull request."""
        payload: dict[str, Any] = {
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
        payload: dict[str, Any] = {}
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
    ) -> list[dict]:
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
        message: str | None = None,
    ) -> dict:
        """Merge a pull request."""
        payload: dict[str, Any] = {
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
        inline: dict[str, Any] | None = None,
        parent_id: int | None = None,
    ) -> dict:
        """Add a comment to a PR. Pass inline dict for file-level comments, parent_id for threaded replies."""
        payload: dict[str, Any] = {
            "content": {"raw": body},
        }
        if inline:
            payload["inline"] = inline
        if parent_id:
            payload["parent"] = {"id": parent_id}
        return self._request(
            "POST",
            f"/repositories/{workspace}/{repo_slug}/pullrequests/{pr_id}/comments",
            data=payload,
        )

    def get_pr_comment(
        self,
        workspace: str,
        repo_slug: str,
        pr_id: int,
        comment_id: int,
    ) -> dict:
        """Fetch a single comment on a PR."""
        return self._request(
            "GET",
            f"/repositories/{workspace}/{repo_slug}/pullrequests/{pr_id}/comments/{comment_id}",
        )

    def resolve_pr_comment(
        self,
        workspace: str,
        repo_slug: str,
        pr_id: int,
        comment_id: int,
    ) -> dict:
        """Mark a PR comment thread as resolved via POST .../comments/{id}/resolve."""
        return self._request(
            "POST",
            f"/repositories/{workspace}/{repo_slug}/pullrequests/{pr_id}/comments/{comment_id}/resolve",
        )

    def unresolve_pr_comment(
        self,
        workspace: str,
        repo_slug: str,
        pr_id: int,
        comment_id: int,
    ) -> dict:
        """Reopen a resolved comment thread via DELETE .../comments/{id}/resolve."""
        return self._request(
            "DELETE",
            f"/repositories/{workspace}/{repo_slug}/pullrequests/{pr_id}/comments/{comment_id}/resolve",
        )

    def get_pr_comments(
        self,
        workspace: str,
        repo_slug: str,
        pr_id: int,
        max_results: int = 0,
    ) -> list[dict]:
        """List all comments on a PR with accurate resolution status.

        The list endpoint does not reliably return resolution details,
        so each root (non-reply) comment is fetched individually to get
        the real resolution object.  Child comments inherit resolution
        from their parent thread.
        """
        comments = self._paginate(
            f"/repositories/{workspace}/{repo_slug}/pullrequests/{pr_id}/comments",
            max_results=max_results,
        )
        root_ids = [c["id"] for c in comments if not c.get("parent") and c.get("id")]
        resolutions = {}
        if root_ids:
            fetchers = [
                lambda c=cid: (c, self.get_pr_comment(workspace, repo_slug, pr_id, c))
                for cid in root_ids
            ]
            for cid, detail in self._parallel_fetch(fetchers):
                resolutions[cid] = detail.get("resolution")
        for c in comments:
            cid = c.get("id")
            parent_id = (c.get("parent") or {}).get("id")
            if cid in resolutions:
                c["resolution"] = resolutions[cid]
            elif parent_id and parent_id in resolutions:
                c["resolution"] = resolutions[parent_id]
        return comments

    # -----------------------------------------------------------------
    # PR Statuses / Checks
    # -----------------------------------------------------------------
    def get_pr_statuses(
        self,
        workspace: str,
        repo_slug: str,
        pr_id: int,
    ) -> list[dict]:
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
    ) -> list[dict]:
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
        q: str | None = None,
    ) -> list[dict]:
        """List repositories in a workspace."""
        params: dict[str, str] = {}
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
