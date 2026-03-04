"""
Low-level Jira REST API client for jira-manager skill scripts.

Uses urllib.request (stdlib) so the skill works even without the requests package
installed. Falls back gracefully and provides clear error messages.

Based on the proven API patterns from cap-agent-kit/create_jira_tickets.py.
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
from typing import Any, Dict, List, Optional

from config_loader import JiraConfig, resolve_credentials

_DEBUG = os.environ.get("JIRA_DEBUG", "").lower() in ("1", "true", "yes")


class JiraClient:
    """Thin wrapper around Jira REST API v2."""

    def __init__(self, config: JiraConfig):
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
        data: Optional[dict] = None,
        params: Optional[dict] = None,
    ) -> Any:
        """Execute an HTTP request against the Jira REST API."""
        url = f"{self.base_url}{path}"
        if params:
            qs = "&".join(
                f"{urllib.parse.quote(k)}={urllib.parse.quote(str(v))}"
                for k, v in params.items()
            )
            url = f"{url}?{qs}"

        body = json.dumps(data).encode() if data else None
        req = urllib.request.Request(
            url, data=body, headers=self._headers, method=method
        )

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
                messages = error_json.get("errorMessages", [])
                errors = error_json.get("errors", {})
                detail = "; ".join(messages) if messages else json.dumps(errors)
            except (json.JSONDecodeError, AttributeError):
                detail = error_body[:500] if _DEBUG else "(set JIRA_DEBUG=1 for details)"
            print(f"ERROR {e.code} {method} {path}: {detail}", file=sys.stderr)
            raise
        except urllib.error.URLError as e:
            if isinstance(e.reason, (socket.timeout, TimeoutError)):
                print(f"ERROR: Request timed out (60s) {method} {path}", file=sys.stderr)
            else:
                print(f"ERROR: URL error {method} {path}: {e.reason}", file=sys.stderr)
            raise

    # -----------------------------------------------------------------
    # Issue CRUD
    # -----------------------------------------------------------------
    def create_issue(self, fields: Dict[str, Any]) -> dict:
        """Create a Jira issue. Returns the full creation response including 'key'."""
        return self._request("POST", "/rest/api/2/issue", {"fields": fields})

    def update_issue(self, issue_key: str, fields: Dict[str, Any]) -> dict:
        """Update fields on an existing issue."""
        return self._request(
            "PUT", f"/rest/api/2/issue/{issue_key}", {"fields": fields}
        )

    def get_issue(
        self, issue_key: str, fields: Optional[List[str]] = None
    ) -> dict:
        """Fetch a single issue by key."""
        params = {}
        if fields:
            params["fields"] = ",".join(fields)
        return self._request("GET", f"/rest/api/2/issue/{issue_key}", params=params)

    def delete_issue(self, issue_key: str, delete_subtasks: bool = False) -> dict:
        """Delete an issue by key."""
        params = {}
        if delete_subtasks:
            params["deleteSubtasks"] = "true"
        return self._request(
            "DELETE", f"/rest/api/2/issue/{issue_key}", params=params
        )

    # -----------------------------------------------------------------
    # Attachments
    # -----------------------------------------------------------------
    def add_attachment(self, issue_key: str, file_path: str) -> List[dict]:
        """Attach a file to an issue. Returns the attachment metadata list."""
        fp = Path(file_path)
        if not fp.exists():
            print(f"ERROR: Attachment file not found: {fp}", file=sys.stderr)
            raise FileNotFoundError(f"Attachment not found: {fp}")

        mime_type = mimetypes.guess_type(fp.name)[0] or "application/octet-stream"
        boundary = uuid.uuid4().hex

        file_data = fp.read_bytes()
        body = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="{fp.name}"\r\n'
            f"Content-Type: {mime_type}\r\n\r\n"
        ).encode() + file_data + f"\r\n--{boundary}--\r\n".encode()

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
                return json.loads(raw) if raw else []
        except urllib.error.HTTPError as e:
            error_body = e.read().decode()
            detail = error_body[:500] if _DEBUG else "(set JIRA_DEBUG=1 for details)"
            print(f"ERROR {e.code} attaching {fp.name} to {issue_key}: {detail}", file=sys.stderr)
            raise

    def add_attachments(self, issue_key: str, file_paths: List[str]) -> List[dict]:
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
        fields: Optional[List[str]] = None,
        max_results: int = 50,
        next_page_token: Optional[str] = None,
    ) -> dict:
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
        return self._request("GET", "/rest/api/3/search/jql", params=params)

    def search_jql_all(
        self,
        jql: str,
        fields: Optional[List[str]] = None,
        max_results: int = 0,
    ) -> List[dict]:
        """Fetch issues matching JQL, handling pagination automatically.

        Args:
            max_results: Maximum total issues to return. Set to 0 for no limit
                         (fetches all in batches of 100). Matches get_board_issues contract.
        """
        all_issues: List[dict] = []
        next_page_token = None
        unlimited = max_results == 0
        remaining = max_results if not unlimited else float("inf")
        while remaining > 0:
            page_size = 100 if unlimited else min(int(remaining), 100)
            result = self.search_jql(
                jql, fields=fields, max_results=page_size,
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
        issue_type: Optional[str] = None,
        fields: Optional[List[str]] = None,
    ) -> List[dict]:
        """Fetch all child issues of a parent (epic's stories, story's subtasks)."""
        # Try epic link first, then parent link
        jql_parts = []

        epic_link_field = self.config.get_field_id("epic_link")
        if epic_link_field:
            jql_parts.append(f'"{epic_link_field}" = {parent_key}')

        # Also try the standard parent field for subtasks
        jql_parts.append(f"parent = {parent_key}")

        if issue_type:
            type_filter = f' AND issuetype = "{issue_type}"'
        else:
            type_filter = ""

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
    def get_fields(self) -> List[dict]:
        """Fetch all fields (system + custom) available on this instance."""
        return self._request("GET", "/rest/api/2/field")

    def get_create_meta(
        self, project_key: Optional[str] = None, expand: bool = True
    ) -> dict:
        """Fetch issue creation metadata for the project."""
        pk = project_key or self.config.project_key
        params = {"projectKeys": pk}
        if expand:
            params["expand"] = "projects.issuetypes.fields"
        return self._request("GET", "/rest/api/2/issue/createmeta", params=params)

    def get_transitions(self, issue_key: str) -> List[dict]:
        """Fetch available workflow transitions for an issue."""
        result = self._request(
            "GET", f"/rest/api/2/issue/{issue_key}/transitions"
        )
        return result.get("transitions", [])

    def transition_issue(
        self,
        issue_key: str,
        transition_id: str,
        fields: Optional[Dict[str, Any]] = None,
    ) -> dict:
        """Execute a workflow transition on an issue.

        Args:
            issue_key: The issue key (e.g. API-123)
            transition_id: The transition ID to execute
            fields: Optional fields to set during the transition
        """
        body: Dict[str, Any] = {"transition": {"id": transition_id}}
        if fields:
            body["fields"] = fields
        return self._request(
            "POST", f"/rest/api/2/issue/{issue_key}/transitions", body
        )

    def get_project(self, project_key: Optional[str] = None) -> dict:
        """Fetch project metadata."""
        pk = project_key or self.config.project_key
        return self._request("GET", f"/rest/api/2/project/{pk}")

    def get_statuses_for_project(
        self, project_key: Optional[str] = None
    ) -> List[dict]:
        """Fetch all statuses available in the project."""
        pk = project_key or self.config.project_key
        return self._request("GET", f"/rest/api/2/project/{pk}/statuses")

    def get_priorities(self) -> List[dict]:
        """Fetch all priorities available on this instance."""
        return self._request("GET", "/rest/api/2/priority")

    def get_resolutions(self) -> List[dict]:
        """Fetch all resolutions available on this instance."""
        return self._request("GET", "/rest/api/2/resolution")

    def get_components(
        self, project_key: Optional[str] = None
    ) -> List[dict]:
        """Fetch all components for the project."""
        pk = project_key or self.config.project_key
        return self._request("GET", f"/rest/api/2/project/{pk}/components")

    def get_versions(
        self, project_key: Optional[str] = None
    ) -> List[dict]:
        """Fetch all versions for the project."""
        pk = project_key or self.config.project_key
        return self._request("GET", f"/rest/api/2/project/{pk}/versions")

    # -----------------------------------------------------------------
    # Agile / Sprint
    # -----------------------------------------------------------------
    def get_boards(
        self, project_key: Optional[str] = None
    ) -> List[dict]:
        """Fetch all boards for the project via the Agile REST API."""
        pk = project_key or self.config.project_key
        result = self._request(
            "GET", "/rest/agile/1.0/board",
            params={"projectKeyOrId": pk},
        )
        return result.get("values", [])

    def get_sprints(
        self,
        board_id: int,
        state: Optional[str] = None,
    ) -> List[dict]:
        """Fetch sprints for a board.

        Args:
            board_id: The Agile board ID.
            state: Optional filter: 'active', 'future', 'closed', or comma-separated.
        """
        params: Dict[str, str] = {}
        if state:
            params["state"] = state
        result = self._request(
            "GET", f"/rest/agile/1.0/board/{board_id}/sprint",
            params=params or None,
        )
        return result.get("values", [])

    def get_board_issues(
        self,
        board_id: int,
        jql: Optional[str] = None,
        fields: Optional[List[str]] = None,
        max_results: int = 50,
    ) -> List[dict]:
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
                
            result = self._request(
                "GET", 
                f"/rest/agile/1.0/board/{board_id}/issue",
                params=params
            )
            
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

    def get_issue_sprint(self, issue_key: str) -> Optional[dict]:
        """Fetch the active/future sprint for an issue via the Agile API.

        Returns the sprint dict or None if no sprint is assigned.
        """
        try:
            result = self._request(
                "GET", f"/rest/agile/1.0/issue/{issue_key}",
                params={"fields": "sprint"},
            )
            return result.get("fields", {}).get("sprint")
        except urllib.error.HTTPError:
            return None

    def move_issues_to_sprint(
        self, sprint_id: int, issue_keys: List[str]
    ) -> dict:
        """Move issues into a sprint via the Agile API.

        This is the recommended way to set sprints — more reliable than
        setting the sprint custom field directly.
        """
        return self._request(
            "POST",
            f"/rest/agile/1.0/sprint/{sprint_id}/issue",
            {"issues": issue_keys},
        )

    # -----------------------------------------------------------------
    # Comments
    # -----------------------------------------------------------------
    def add_comment(self, issue_key: str, body: str) -> dict:
        """Add a comment to an issue. Returns the created comment."""
        return self._request(
            "POST",
            f"/rest/api/2/issue/{issue_key}/comment",
            {"body": body},
        )

    def get_comments(self, issue_key: str) -> List[dict]:
        """Fetch all comments on an issue."""
        result = self._request(
            "GET", f"/rest/api/2/issue/{issue_key}/comment"
        )
        return result.get("comments", [])

    # -----------------------------------------------------------------
    # Issue Links
    # -----------------------------------------------------------------
    def get_link_types(self) -> List[dict]:
        """Fetch all available issue link types (e.g. Blocks, Cloners, Duplicate)."""
        result = self._request("GET", "/rest/api/2/issueLinkType")
        return result.get("issueLinkTypes", [])

    def add_issue_link(
        self,
        link_type_name: str,
        inward_key: str,
        outward_key: str,
        comment: Optional[str] = None,
    ) -> dict:
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
        body: Dict[str, Any] = {
            "type": {"name": link_type_name},
            "inwardIssue": {"key": inward_key},
            "outwardIssue": {"key": outward_key},
        }
        if comment:
            body["comment"] = {"body": comment}
        return self._request("POST", "/rest/api/2/issueLink", body)

    def get_issue_links(self, issue_key: str) -> List[dict]:
        """Fetch all links on an issue."""
        issue = self.get_issue(issue_key, fields=["issuelinks"])
        return issue.get("fields", {}).get("issuelinks", [])

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

    def browse_url(self, issue_key: str) -> str:
        """Return the browse URL for an issue."""
        return f"{self.base_url}/browse/{issue_key}"
