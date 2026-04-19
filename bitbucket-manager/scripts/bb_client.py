"""
Low-level Bitbucket Cloud REST API v2 client.

Pure stdlib (urllib + json + base64). Zero pip dependencies.
"""

import base64
import json
import os
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, NoReturn

from bb_config import BitbucketConfig, resolve_credentials

_DEBUG = os.environ.get("BB_DEBUG", "").lower() in ("1", "true", "yes")
_MAX_429_RETRIES = 3
_429_BACKOFF_BASE = 2  # seconds; doubles each retry: 2, 4, 8
_BASE_URL = "https://api.bitbucket.org/2.0"


class BitbucketClient:
    """Thin wrapper around Bitbucket Cloud REST API v2."""

    def __init__(self, config: BitbucketConfig) -> None:
        self.config = config
        email, api_token = resolve_credentials(config)
        creds = base64.b64encode(f"{email}:{api_token}".encode()).decode()
        self._headers = {
            "Authorization": f"Basic {creds}",
            "Content-Type": "application/json",
        }

    # -----------------------------------------------------------------
    # Low-level HTTP
    # -----------------------------------------------------------------
    @staticmethod
    def _build_url(path: str, params: dict | None) -> str:
        url = f"{_BASE_URL}{path}"
        if params:
            qs = "&".join(
                f"{urllib.parse.quote(str(k))}={urllib.parse.quote(str(v))}"
                for k, v in params.items()
            )
            url = f"{url}?{qs}"
        return url

    @staticmethod
    def _build_body(method: str, data: dict | None) -> bytes | None:
        if data is not None:
            return json.dumps(data).encode()
        if method in ("POST", "PUT"):
            return b"{}"
        return None

    @staticmethod
    def _http_error_hint(code: int, path: str) -> str:
        if code == 401:
            return (
                " Hint: verify BITBUCKET_EMAIL plus a Bitbucket Cloud API token/app password "
                "with REST scopes for this endpoint. Plain no-scope Atlassian tokens will fail "
                "for Bitbucket REST auth. SSH git access alone does not validate REST auth."
            )
        if code == 403:
            return (
                " Hint: credentials were accepted, but this account/token lacks permission for "
                f"{path}."
            )
        return ""

    @staticmethod
    def _handle_http_error(e: urllib.error.HTTPError, method: str, path: str) -> NoReturn:
        """Log and re-raise a non-retryable HTTP error."""
        error_body = e.read().decode()
        try:
            error_json = json.loads(error_body)
            msg = error_json.get("error", {}).get("message", "")
            detail = msg if msg else error_body[:500]
        except (json.JSONDecodeError, AttributeError):
            detail = error_body[:500] if _DEBUG else f"HTTP {e.code} (set BB_DEBUG=1 for details)"
        hint = BitbucketClient._http_error_hint(e.code, path)
        print(f"ERROR {e.code} {method} {path}: {detail}{hint}", file=sys.stderr)
        raise SystemExit(1)

    @staticmethod
    def _log_debug_request(url: str, body: bytes | None) -> None:
        if _DEBUG:
            print(f"DEBUG: {url}", file=sys.stderr)
            if body:
                print(f"DEBUG: body={body[:500].decode()!r}", file=sys.stderr)

    @staticmethod
    def _decode_response(resp: Any, raw: bool) -> Any:
        if resp.status == 204:
            return "" if raw else {}
        response_text = resp.read().decode()
        if not response_text:
            return "" if raw else {}
        if raw:
            return response_text
        return json.loads(response_text)

    @staticmethod
    def _maybe_retry_rate_limit(
        e: urllib.error.HTTPError, attempt: int, method: str, path: str
    ) -> bool:
        if e.code != 429 or attempt >= _MAX_429_RETRIES:
            return False
        wait = _429_BACKOFF_BASE * (2**attempt)
        print(
            f"Rate limited, retrying in {wait}s... (attempt {attempt + 1}/{_MAX_429_RETRIES})",
            file=sys.stderr,
        )
        e.read()  # drain response body
        time.sleep(wait)
        return True

    @staticmethod
    def _handle_url_error(e: urllib.error.URLError, method: str, path: str) -> None:
        if isinstance(e.reason, socket.timeout | TimeoutError):
            print(f"ERROR: Request timed out (60s) {method} {path}", file=sys.stderr)
        else:
            print(f"ERROR: URL error {method} {path}: {e.reason}", file=sys.stderr)
        raise

    def _request_once(
        self,
        method: str,
        url: str,
        path: str,
        body: bytes | None,
        raw: bool,
    ) -> Any:
        req = urllib.request.Request(url, data=body, headers=self._headers, method=method)
        with urllib.request.urlopen(req, timeout=60) as resp:
            return self._decode_response(resp, raw)

    def _request(
        self,
        method: str,
        path: str,
        data: dict | None = None,
        params: dict | None = None,
        raw: bool = False,
    ) -> Any:
        """Execute an HTTP request against the Bitbucket REST API.

        Retries automatically on HTTP 429 (rate limit) with exponential backoff.
        """
        url = self._build_url(path, params)
        body = self._build_body(method, data)
        self._log_debug_request(f"{method} {url}", body)

        last_error: urllib.error.HTTPError | None = None
        for attempt in range(_MAX_429_RETRIES + 1):
            try:
                return self._request_once(method, url, path, body, raw)
            except TimeoutError:
                print(f"ERROR: Request timed out (60s) {method} {path}", file=sys.stderr)
                raise
            except urllib.error.HTTPError as e:
                if self._maybe_retry_rate_limit(e, attempt, method, path):
                    last_error = e
                    continue
                self._handle_http_error(e, method, path)
            except urllib.error.URLError as e:
                self._handle_url_error(e, method, path)

        # All retries exhausted
        if last_error:
            print(
                f"ERROR 429 {method} {path}: Rate limit exceeded after {_MAX_429_RETRIES} retries",
                file=sys.stderr,
            )
            raise last_error
        return {}  # unreachable, satisfies type checker

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
    ) -> list[Any]:
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
        return self._request(  # type: ignore[no-any-return]
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
        return self._request(  # type: ignore[no-any-return]
            "PUT",
            f"/repositories/{workspace}/{repo_slug}/pullrequests/{pr_id}",
            data=payload,
        )

    def get_pr(self, workspace: str, repo_slug: str, pr_id: int) -> dict:
        """Fetch a single pull request by ID."""
        return self._request(  # type: ignore[no-any-return]
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
        return self._request(  # type: ignore[no-any-return]
            "POST",
            f"/repositories/{workspace}/{repo_slug}/pullrequests/{pr_id}/merge",
            data=payload,
        )

    def decline_pr(self, workspace: str, repo_slug: str, pr_id: int) -> dict:
        """Decline a pull request."""
        return self._request(  # type: ignore[no-any-return]
            "POST",
            f"/repositories/{workspace}/{repo_slug}/pullrequests/{pr_id}/decline",
        )

    def get_pr_diff(self, workspace: str, repo_slug: str, pr_id: int) -> str:
        """Fetch the raw unified diff for a pull request."""
        return self._request(  # type: ignore[no-any-return]
            "GET",
            f"/repositories/{workspace}/{repo_slug}/pullrequests/{pr_id}/diff",
            raw=True,
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
        return self._request(  # type: ignore[no-any-return]
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
        return self._request(  # type: ignore[no-any-return]
            "GET",
            f"/repositories/{workspace}/{repo_slug}/pullrequests/{pr_id}/comments/{comment_id}",
        )

    def update_pr_comment(
        self,
        workspace: str,
        repo_slug: str,
        pr_id: int,
        comment_id: int,
        body: str,
    ) -> dict:
        """Update the body of an existing PR comment."""
        return self._request(  # type: ignore[no-any-return]
            "PUT",
            f"/repositories/{workspace}/{repo_slug}/pullrequests/{pr_id}/comments/{comment_id}",
            data={"content": {"raw": body}},
        )

    def delete_pr_comment(
        self,
        workspace: str,
        repo_slug: str,
        pr_id: int,
        comment_id: int,
    ) -> dict:
        """Delete a PR comment. Returns empty dict on success (HTTP 204)."""
        return self._request(  # type: ignore[no-any-return]
            "DELETE",
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
        return self._request(  # type: ignore[no-any-return]
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
        return self._request(  # type: ignore[no-any-return]
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
    # Pipelines / Deployments / Environments
    # -----------------------------------------------------------------
    def list_pipelines(
        self,
        workspace: str,
        repo_slug: str,
        max_results: int = 50,
    ) -> list[dict]:
        """List repository pipelines."""
        return self._paginate(
            f"/repositories/{workspace}/{repo_slug}/pipelines",
            max_results=max_results,
        )

    def get_pipeline(self, workspace: str, repo_slug: str, pipeline_uuid: str) -> dict:
        """Fetch a single pipeline by UUID."""
        return self._request(  # type: ignore[no-any-return]
            "GET",
            f"/repositories/{workspace}/{repo_slug}/pipelines/{pipeline_uuid}",
        )

    def run_pipeline(
        self,
        workspace: str,
        repo_slug: str,
        target: dict[str, Any],
        variables: list[dict[str, Any]] | None = None,
    ) -> dict:
        """Trigger a pipeline run."""
        payload: dict[str, Any] = {"target": target}
        if variables:
            payload["variables"] = variables
        return self._request(  # type: ignore[no-any-return]
            "POST",
            f"/repositories/{workspace}/{repo_slug}/pipelines",
            data=payload,
        )

    def list_pipeline_steps(
        self,
        workspace: str,
        repo_slug: str,
        pipeline_uuid: str,
        max_results: int = 50,
    ) -> list[dict]:
        """List steps for a pipeline."""
        return self._paginate(
            f"/repositories/{workspace}/{repo_slug}/pipelines/{pipeline_uuid}/steps",
            max_results=max_results,
        )

    def get_pipeline_step(
        self,
        workspace: str,
        repo_slug: str,
        pipeline_uuid: str,
        step_uuid: str,
    ) -> dict:
        """Fetch a single pipeline step by UUID."""
        return self._request(  # type: ignore[no-any-return]
            "GET",
            f"/repositories/{workspace}/{repo_slug}/pipelines/{pipeline_uuid}/steps/{step_uuid}",
        )

    def get_pipeline_step_log(
        self,
        workspace: str,
        repo_slug: str,
        pipeline_uuid: str,
        step_uuid: str,
        log_uuid: str,
    ) -> str:
        """Fetch the raw log for a pipeline step."""
        return self._request(  # type: ignore[no-any-return]
            "GET",
            f"/repositories/{workspace}/{repo_slug}/pipelines/{pipeline_uuid}/steps/{step_uuid}/logs/{log_uuid}",
            raw=True,
        )

    def list_environments(
        self,
        workspace: str,
        repo_slug: str,
        max_results: int = 50,
    ) -> list[dict]:
        """List repository deployment environments."""
        return self._paginate(
            f"/repositories/{workspace}/{repo_slug}/environments",
            max_results=max_results,
        )

    def get_environment(self, workspace: str, repo_slug: str, environment_uuid: str) -> dict:
        """Fetch a single deployment environment by UUID."""
        return self._request(  # type: ignore[no-any-return]
            "GET",
            f"/repositories/{workspace}/{repo_slug}/environments/{environment_uuid}",
        )

    def list_deployments(
        self,
        workspace: str,
        repo_slug: str,
        max_results: int = 50,
    ) -> list[dict]:
        """List repository deployments."""
        return self._paginate(
            f"/repositories/{workspace}/{repo_slug}/deployments",
            max_results=max_results,
        )

    def get_deployment(self, workspace: str, repo_slug: str, deployment_uuid: str) -> dict:
        """Fetch a single deployment by UUID."""
        return self._request(  # type: ignore[no-any-return]
            "GET",
            f"/repositories/{workspace}/{repo_slug}/deployments/{deployment_uuid}",
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
    def test_connection(self, workspace: str) -> tuple[bool, str | None]:
        """Test connectivity and credentials with an actionable failure reason."""
        url = self._build_url(f"/repositories/{workspace}", {"pagelen": "1"})
        req = urllib.request.Request(url, headers=self._headers, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=60):
                pass
            return True, None
        except urllib.error.HTTPError as e:
            hint = self._http_error_hint(e.code, f"/repositories/{workspace}")
            if e.code == 401:
                return False, f"REST auth rejected the token.{hint}"
            if e.code == 403:
                return (
                    False,
                    f"REST auth succeeded, but access to workspace '{workspace}' was denied.{hint}",
                )
            return False, f"HTTP {e.code} while contacting workspace '{workspace}'."
        except urllib.error.URLError as e:
            return False, f"Network error while contacting Bitbucket: {e.reason}"
