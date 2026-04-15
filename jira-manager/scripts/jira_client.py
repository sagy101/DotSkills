"""
Low-level Jira REST API client for jira-manager skill scripts.

Uses urllib.request (stdlib) so the skill works even without the requests package
installed. Falls back gracefully and provides clear error messages.

Based on proven Jira REST API patterns.
"""

import base64
import json
import mimetypes
import os
import socket
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any

from jira_config_loader import JiraConfig, resolve_credentials

_DEBUG = os.environ.get("JIRA_DEBUG", "").lower() in ("1", "true", "yes")


class JiraAPIError(Exception):
    """Wraps a Jira HTTP error with the parsed detail string and status code."""

    def __init__(self, status_code: int, detail: str, original: urllib.error.HTTPError) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail
        self.original = original


class JiraClient:
    """Thin wrapper around Jira REST API v2."""

    def __init__(self, config: JiraConfig) -> None:
        self.config = config
        self.base_url = config.jira_url.rstrip("/")
        if not self.base_url.startswith("https://"):
            print(
                f"ERROR: Jira URL must use HTTPS (got: {self.base_url}). "
                "Basic auth credentials would be sent in plaintext over HTTP.",
                file=sys.stderr,
            )
            sys.exit(1)
        username, token = resolve_credentials(config)
        creds = base64.b64encode(f"{username}:{token}".encode()).decode()
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
        """Execute an HTTP request against the Jira REST API."""
        url = f"{self.base_url}{path}"
        if params:
            qs = "&".join(
                f"{urllib.parse.quote(k)}={urllib.parse.quote(str(v))}" for k, v in params.items()
            )
            url = f"{url}?{qs}"

        body = json.dumps(data).encode() if data else None
        req = urllib.request.Request(url, data=body, headers=self._headers, method=method)

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
                messages = error_json.get("errorMessages", [])
                errors = error_json.get("errors", {})
                detail = "; ".join(messages) if messages else json.dumps(errors)
            except (json.JSONDecodeError, AttributeError):
                detail = error_body[:500] if _DEBUG else "(set JIRA_DEBUG=1 for details)"
            print(f"ERROR {e.code} {method} {path}: {detail}", file=sys.stderr)
            raise JiraAPIError(e.code, detail, e) from e
        except urllib.error.URLError as e:
            if isinstance(e.reason, socket.timeout | TimeoutError):
                print(f"ERROR: Request timed out (60s) {method} {path}", file=sys.stderr)
            else:
                print(f"ERROR: URL error {method} {path}: {e.reason}", file=sys.stderr)
            raise

    # -----------------------------------------------------------------
    # Issue CRUD
    # -----------------------------------------------------------------
    def create_issue(self, fields: dict[str, Any]) -> dict[str, Any]:
        """Create a Jira issue. Returns the full creation response including 'key'."""
        return self._request("POST", "/rest/api/2/issue", {"fields": fields})  # type: ignore[no-any-return]

    def update_issue(self, issue_key: str, fields: dict[str, Any]) -> dict[str, Any]:
        """Update fields on an existing issue."""
        return self._request("PUT", f"/rest/api/2/issue/{issue_key}", {"fields": fields})  # type: ignore[no-any-return]

    def get_issue(self, issue_key: str, fields: list[str] | None = None) -> dict[str, Any]:
        """Fetch a single issue by key."""
        params = {}
        if fields:
            params["fields"] = ",".join(fields)
        return self._request("GET", f"/rest/api/2/issue/{issue_key}", params=params)  # type: ignore[no-any-return]

    def delete_issue(self, issue_key: str, delete_subtasks: bool = False) -> dict[str, Any]:
        """Delete an issue by key."""
        params = {}
        if delete_subtasks:
            params["deleteSubtasks"] = "true"
        return self._request("DELETE", f"/rest/api/2/issue/{issue_key}", params=params)  # type: ignore[no-any-return]

    # -----------------------------------------------------------------
    # Attachments
    # -----------------------------------------------------------------
    def add_attachment(self, issue_key: str, file_path: str) -> list[dict[str, Any]]:
        """Attach a file to an issue. Returns the attachment metadata list."""
        fp = Path(file_path)
        if not fp.exists():
            print(f"ERROR: Attachment file not found: {fp}", file=sys.stderr)
            raise FileNotFoundError(f"Attachment not found: {fp}")

        mime_type = mimetypes.guess_type(fp.name)[0] or "application/octet-stream"
        boundary = uuid.uuid4().hex

        file_data = fp.read_bytes()
        body = (
            (
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="file"; filename="{fp.name}"\r\n'
                f"Content-Type: {mime_type}\r\n\r\n"
            ).encode()
            + file_data
            + f"\r\n--{boundary}--\r\n".encode()
        )

        url = f"{self.base_url}/rest/api/2/issue/{issue_key}/attachments"
        headers = {
            "Authorization": self._headers["Authorization"],
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "X-Atlassian-Token": "no-check",
        }

        req = urllib.request.Request(url, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read().decode()
                return json.loads(raw) if raw else []  # type: ignore[no-any-return]
        except urllib.error.HTTPError as e:
            error_body = e.read().decode()
            detail = error_body[:500] if _DEBUG else "(set JIRA_DEBUG=1 for details)"
            print(f"ERROR {e.code} attaching {fp.name} to {issue_key}: {detail}", file=sys.stderr)
            raise

    def add_attachments(self, issue_key: str, file_paths: list[str]) -> list[dict[str, Any]]:
        """Attach multiple files to an issue. Returns all attachment metadata."""
        results = []
        for fpath in file_paths:
            result = self.add_attachment(issue_key, fpath)
            results.extend(result)
        return results

    # -----------------------------------------------------------------
    # Search
    # -----------------------------------------------------------------
    def search_jql(
        self,
        jql: str,
        fields: list[str] | None = None,
        max_results: int = 50,
        next_page_token: str | None = None,
    ) -> dict[str, Any]:
        """Search issues using JQL (Jira Cloud v3 API).

        Note: The v3 GET /search/jql endpoint returns only issue IDs when
        no fields are requested. Pass fields explicitly or omit to get all
        navigable fields via ``*navigable``.
        """
        params = {
            "jql": jql,
            "maxResults": str(max_results),
        }
        if next_page_token:
            params["nextPageToken"] = next_page_token
        params["fields"] = ",".join(fields) if fields else "*navigable"
        return self._request("GET", "/rest/api/3/search/jql", params=params)  # type: ignore[no-any-return]

    def search_jql_all(
        self,
        jql: str,
        fields: list[str] | None = None,
        max_results: int = 0,
    ) -> list[dict[str, Any]]:
        """Fetch issues matching JQL, handling pagination automatically.

        Args:
            max_results: Maximum total issues to return. Set to 0 for no limit
                         (fetches all in batches of 100). Matches get_board_issues contract.
        """
        all_issues: list[dict[str, Any]] = []
        next_page_token = None
        unlimited = max_results == 0
        remaining = max_results if not unlimited else float("inf")
        while remaining > 0:
            page_size = 100 if unlimited else min(int(remaining), 100)
            result = self.search_jql(
                jql,
                fields=fields,
                max_results=page_size,
                next_page_token=next_page_token,
            )
            issues = result.get("issues", [])
            if not issues:
                break
            all_issues.extend(issues)
            remaining -= len(issues)
            if result.get("isLast", True):
                break
            next_page_token = result.get("nextPageToken")
            if not next_page_token:
                break
        return all_issues

    def get_children(
        self,
        parent_key: str,
        issue_type: str | None = None,
        fields: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch all child issues of a parent (epic's stories, story's subtasks)."""
        # Try epic link first, then parent link
        jql_parts = []

        epic_link_field = self.config.get_field_id("epic_link")
        if epic_link_field:
            jql_parts.append(f'"{epic_link_field}" = {parent_key}')

        # Also try the standard parent field for subtasks
        jql_parts.append(f"parent = {parent_key}")

        type_filter = f' AND issuetype = "{issue_type}"' if issue_type else ""

        all_issues = []
        seen_keys = set()

        for jql_base in jql_parts:
            jql = f"{jql_base}{type_filter} ORDER BY key ASC"
            try:
                # Use search_jql_all to handle pagination
                issues = self.search_jql_all(jql, fields=fields)
                for issue in issues:
                    key = issue["key"]
                    if key not in seen_keys:
                        seen_keys.add(key)
                        all_issues.append(issue)
            except urllib.error.HTTPError:
                continue

        return all_issues

    # -----------------------------------------------------------------
    # Metadata / Discovery
    # -----------------------------------------------------------------
    def get_fields(self) -> list[dict[str, Any]]:
        """Fetch all fields (system + custom) available on this instance."""
        return self._request("GET", "/rest/api/2/field")  # type: ignore[no-any-return]

    def get_create_meta(
        self, project_key: str | None = None, expand: bool = True
    ) -> dict[str, Any]:
        """Fetch issue creation metadata for the project."""
        pk = project_key or self.config.project_key
        params = {"projectKeys": pk}
        if expand:
            params["expand"] = "projects.issuetypes.fields"
        return self._request("GET", "/rest/api/2/issue/createmeta", params=params)  # type: ignore[no-any-return]

    def get_create_meta_for_type(
        self,
        issue_type_id: str,
        project_key: str | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch all available fields for a specific issue type via createmeta.

        Returns a flat list of field dicts (each with key, name, required,
        allowedValues, etc.).  Handles pagination automatically.
        """
        pk = project_key or self.config.project_key
        all_fields: list[dict[str, Any]] = []
        start = 0
        while True:
            result = self._request(
                "GET",
                f"/rest/api/2/issue/createmeta/{pk}/issuetypes/{issue_type_id}",
                params={"startAt": start, "maxResults": 50},
            )
            fields = result.get("fields", result.get("values", []))
            if isinstance(fields, list):
                all_fields.extend(fields)
            else:
                break
            total = result.get("total", len(all_fields))
            start += len(fields)
            if start >= total or not fields:
                break
        return all_fields

    def get_transitions(self, issue_key: str) -> list[dict[str, Any]]:
        """Fetch available workflow transitions for an issue."""
        result = self._request("GET", f"/rest/api/2/issue/{issue_key}/transitions")
        return result.get("transitions", [])  # type: ignore[no-any-return]

    def transition_issue(
        self,
        issue_key: str,
        transition_id: str,
        fields: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Execute a workflow transition on an issue.

        Args:
            issue_key: The issue key (e.g. API-123)
            transition_id: The transition ID to execute
            fields: Optional fields to set during the transition
        """
        body: dict[str, Any] = {"transition": {"id": transition_id}}
        if fields:
            body["fields"] = fields
        return self._request("POST", f"/rest/api/2/issue/{issue_key}/transitions", body)  # type: ignore[no-any-return]

    def get_issue_type_hierarchy(self, project_key: str | None = None) -> list[dict[str, Any]]:
        """Fetch all issue types with hierarchy levels for the project via v3 createmeta.

        Returns a list of dicts: [{"id": ..., "name": ..., "hierarchyLevel": ...}, ...],
        sorted by hierarchyLevel descending (highest first).
        """
        pk = project_key or self.config.project_key
        try:
            result = self._request(
                "GET",
                f"/rest/api/3/issue/createmeta/{pk}/issuetypes",
            )
            types = result.get("issueTypes", result if isinstance(result, list) else [])
            return sorted(types, key=lambda t: t.get("hierarchyLevel", 0), reverse=True)
        except Exception:
            return []

    def get_project(self, project_key: str | None = None) -> dict[str, Any]:
        """Fetch project metadata."""
        pk = project_key or self.config.project_key
        return self._request("GET", f"/rest/api/2/project/{pk}")  # type: ignore[no-any-return]

    def get_statuses_for_project(self, project_key: str | None = None) -> list[dict[str, Any]]:
        """Fetch all statuses available in the project."""
        pk = project_key or self.config.project_key
        return self._request("GET", f"/rest/api/2/project/{pk}/statuses")  # type: ignore[no-any-return]

    def get_priorities(self) -> list[dict[str, Any]]:
        """Fetch all priorities available on this instance."""
        return self._request("GET", "/rest/api/2/priority")  # type: ignore[no-any-return]

    def get_resolutions(self) -> list[dict[str, Any]]:
        """Fetch all resolutions available on this instance."""
        return self._request("GET", "/rest/api/2/resolution")  # type: ignore[no-any-return]

    def get_components(self, project_key: str | None = None) -> list[dict[str, Any]]:
        """Fetch all components for the project."""
        pk = project_key or self.config.project_key
        return self._request("GET", f"/rest/api/2/project/{pk}/components")  # type: ignore[no-any-return]

    def get_versions(self, project_key: str | None = None) -> list[dict[str, Any]]:
        """Fetch all versions for the project."""
        pk = project_key or self.config.project_key
        return self._request("GET", f"/rest/api/2/project/{pk}/versions")  # type: ignore[no-any-return]

    # -----------------------------------------------------------------
    # Agile / Sprint
    # -----------------------------------------------------------------
    def get_boards(self, project_key: str | None = None) -> list[dict[str, Any]]:
        """Fetch all boards for the project via the Agile REST API."""
        pk = project_key or self.config.project_key
        result = self._request(
            "GET",
            "/rest/agile/1.0/board",
            params={"projectKeyOrId": pk},
        )
        return result.get("values", [])  # type: ignore[no-any-return]

    def get_sprints(
        self,
        board_id: int,
        state: str | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch sprints for a board.

        Args:
            board_id: The Agile board ID.
            state: Optional filter: 'active', 'future', 'closed', or comma-separated.
        """
        params: dict[str, str] = {}
        if state:
            params["state"] = state
        result = self._request(
            "GET",
            f"/rest/agile/1.0/board/{board_id}/sprint",
            params=params or None,
        )
        return result.get("values", [])  # type: ignore[no-any-return]

    def get_board_issues(
        self,
        board_id: int,
        jql: str | None = None,
        fields: list[str] | None = None,
        max_results: int = 50,
    ) -> list[dict[str, Any]]:
        """Fetch issues from a board, optionally filtering with JQL.

        Args:
            max_results: Maximum total issues to return. Set to 0 for no limit
                         (fetches all in batches of 50).
        """
        all_issues = []
        start_at = 0
        unlimited = max_results == 0
        remaining = max_results if not unlimited else float("inf")

        field_param = ",".join(fields) if fields else None

        while remaining > 0:
            page_size = 50 if unlimited else min(remaining, 50)
            params = {
                "startAt": str(start_at),
                "maxResults": str(page_size),
            }
            if jql:
                params["jql"] = jql
            if field_param:
                params["fields"] = field_param

            result = self._request("GET", f"/rest/agile/1.0/board/{board_id}/issue", params=params)

            issues = result.get("issues", [])
            if not issues:
                break

            all_issues.extend(issues)
            remaining -= len(issues)

            total = result.get("total", 0)
            if start_at + len(issues) >= total:
                break

            start_at += len(issues)

        return all_issues

    def get_issue_sprint(self, issue_key: str) -> dict[str, Any] | None:
        """Fetch the active/future sprint for an issue via the Agile API.

        Returns the sprint dict or None if no sprint is assigned.
        """
        try:
            result = self._request(
                "GET",
                f"/rest/agile/1.0/issue/{issue_key}",
                params={"fields": "sprint"},
            )
            return result.get("fields", {}).get("sprint")  # type: ignore[no-any-return]
        except urllib.error.HTTPError:
            return None

    def move_issues_to_sprint(self, sprint_id: int, issue_keys: list[str]) -> dict[str, Any]:
        """Move issues into a sprint via the Agile API.

        This is the recommended way to set sprints — more reliable than
        setting the sprint custom field directly.
        """
        return self._request(  # type: ignore[no-any-return]
            "POST",
            f"/rest/agile/1.0/sprint/{sprint_id}/issue",
            {"issues": issue_keys},
        )

    # -----------------------------------------------------------------
    # Comments
    # -----------------------------------------------------------------
    def add_comment(self, issue_key: str, body: str) -> dict[str, Any]:
        """Add a comment to an issue. Returns the created comment."""
        return self._request(  # type: ignore[no-any-return]
            "POST",
            f"/rest/api/2/issue/{issue_key}/comment",
            {"body": body},
        )

    def get_comments(self, issue_key: str) -> list[dict[str, Any]]:
        """Fetch all comments on an issue."""
        result = self._request("GET", f"/rest/api/2/issue/{issue_key}/comment")
        return result.get("comments", [])  # type: ignore[no-any-return]

    # -----------------------------------------------------------------
    # Issue Links
    # -----------------------------------------------------------------
    def get_link_types(self) -> list[dict[str, Any]]:
        """Fetch all available issue link types (e.g. Blocks, Cloners, Duplicate)."""
        result = self._request("GET", "/rest/api/2/issueLinkType")
        return result.get("issueLinkTypes", [])  # type: ignore[no-any-return]

    def add_issue_link(
        self,
        link_type_name: str,
        inward_key: str,
        outward_key: str,
        comment: str | None = None,
    ) -> dict[str, Any]:
        """Create a link between two issues.

        Args:
            link_type_name: The link type name (e.g. "Blocks", "Duplicate",
                "Cloners"). Must match a name from get_link_types().
            inward_key: The inward issue key (e.g. the blocker).
            outward_key: The outward issue key (e.g. the blocked issue).
            comment: Optional comment to add to the link.

        Example: add_issue_link("Blocks", "API-100", "API-200")
            means API-100 blocks API-200.
        """
        body: dict[str, Any] = {
            "type": {"name": link_type_name},
            "inwardIssue": {"key": inward_key},
            "outwardIssue": {"key": outward_key},
        }
        if comment:
            body["comment"] = {"body": comment}
        return self._request("POST", "/rest/api/2/issueLink", body)  # type: ignore[no-any-return]

    def get_issue_links(self, issue_key: str) -> list[dict[str, Any]]:
        """Fetch all links on an issue."""
        issue = self.get_issue(issue_key, fields=["issuelinks"])
        return issue.get("fields", {}).get("issuelinks", [])  # type: ignore[no-any-return]

    # -----------------------------------------------------------------
    # Utility
    # -----------------------------------------------------------------
    def test_connection(self) -> bool:
        """Test connectivity and credentials. Returns True if successful."""
        try:
            self._request("GET", "/rest/api/2/myself")
            return True
        except urllib.error.HTTPError:
            return False

    def search_users(self, query: str) -> list[dict[str, Any]]:
        """Search for users by display name or email. Returns list of user dicts with accountId."""
        result: list[dict[str, Any]] = self._request(
            "GET", f"/rest/api/2/user/search?query={urllib.parse.quote(query)}"
        )
        return result

    def browse_url(self, issue_key: str) -> str:
        """Return the browse URL for an issue."""
        return f"{self.base_url}/browse/{issue_key}"
