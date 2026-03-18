"""
Low-level Jenkins REST API client.

Pure stdlib (urllib + json + base64). Zero pip dependencies.
"""

import base64
import json
import os
import socket
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, cast

from jenkins_config import JenkinsConfig, resolve_credentials, url_encode_branch

_DEBUG = os.environ.get("JENKINS_DEBUG", "").lower() in ("1", "true", "yes")

# Jenkins job class names
_FOLDER_CLASSES = {
    "jenkins.branch.OrganizationFolder",
    "com.cloudbees.hudson.plugins.folder.Folder",
    "hudson.model.Hudson",
}
_MULTIBRANCH_CLASSES = {
    "org.jenkinsci.plugins.workflow.multibranch.WorkflowMultiBranchProject",
}
_JOB_CLASSES = {
    "org.jenkinsci.plugins.workflow.job.WorkflowJob",
    "hudson.model.FreeStyleProject",
}

# Color-to-status mapping
COLOR_STATUS = {
    "blue": "SUCCESS",
    "red": "FAILURE",
    "yellow": "UNSTABLE",
    "blue_anime": "BUILDING",
    "red_anime": "BUILDING",
    "yellow_anime": "BUILDING",
    "grey_anime": "BUILDING",
    "notbuilt": "NOT_BUILT",
    "notbuilt_anime": "BUILDING",
    "disabled": "DISABLED",
    "aborted": "ABORTED",
    "aborted_anime": "BUILDING",
    "grey": "PENDING",
}


def color_to_status(color: str | None) -> str:
    """Map Jenkins color string to human-readable status."""
    if not color:
        return "UNKNOWN"
    return COLOR_STATUS.get(color, color.upper())


class JenkinsClient:
    """Thin wrapper around Jenkins REST API."""

    def __init__(self, config: JenkinsConfig) -> None:
        self.config = config
        self.base_url = config.base_url
        username, token = resolve_credentials(config)
        creds = base64.b64encode(f"{username}:{token}".encode()).decode()
        self._headers = {
            "Authorization": f"Basic {creds}",
        }
        self._crumb: dict[str, str] | None = None
        self._ssl_context = self._build_ssl_context()

    def _build_ssl_context(self) -> ssl.SSLContext | None:
        """Build SSL context based on config."""
        if not self.config.ssl_verify:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            return ctx
        return None

    # -----------------------------------------------------------------
    # Low-level HTTP
    # -----------------------------------------------------------------
    def _request(
        self,
        method: str,
        path: str,
        params: dict | None = None,
        data: dict | None = None,
        accept_text: bool = False,
        timeout: int = 30,
    ) -> Any:
        """Execute an HTTP request against the Jenkins REST API."""
        url = f"{self.base_url}{path}"
        if params:
            qs = "&".join(
                f"{urllib.parse.quote(str(k))}={urllib.parse.quote(str(v))}"
                for k, v in params.items()
            )
            url = f"{url}?{qs}"

        headers = dict(self._headers)

        # Add CSRF crumb for POST/PUT/DELETE
        if method in ("POST", "PUT", "DELETE"):
            crumb = self._get_crumb()
            if crumb:
                headers[crumb["crumbRequestField"]] = crumb["crumb"]

        if data is not None:
            body = json.dumps(data).encode()
            headers["Content-Type"] = "application/json"
        elif method == "POST":
            body = b""
        else:
            body = None

        req = urllib.request.Request(
            url,
            data=body,
            headers=headers,
            method=method,
        )

        if _DEBUG:
            print(f"DEBUG: {method} {url}", file=sys.stderr)

        try:
            with urllib.request.urlopen(req, timeout=timeout, context=self._ssl_context) as resp:
                if resp.status == 204:
                    return {}
                raw = resp.read().decode()
                if accept_text:
                    return raw
                return json.loads(raw) if raw else {}
        except TimeoutError:
            print(f"ERROR: Request timed out ({timeout}s) {method} {path}", file=sys.stderr)
            raise
        except urllib.error.HTTPError as e:
            error_body = e.read().decode()
            if _DEBUG:
                detail = error_body[:500]
            else:
                detail = f"HTTP {e.code} (set JENKINS_DEBUG=1 for details)"
            print(f"ERROR {e.code} {method} {path}: {detail}", file=sys.stderr)
            raise
        except urllib.error.URLError as e:
            if isinstance(e.reason, socket.timeout | TimeoutError):
                print(f"ERROR: Request timed out ({timeout}s) {method} {path}", file=sys.stderr)
            elif isinstance(e.reason, ssl.SSLCertVerificationError):
                print(
                    f"ERROR: SSL certificate verification failed for {self.base_url}",
                    file=sys.stderr,
                )
                print(
                    "  Fix: Set ssl_verify: false in .jenkins.json, or set SSL_CERT_FILE env var",
                    file=sys.stderr,
                )
            else:
                print(f"ERROR: URL error {method} {path}: {e.reason}", file=sys.stderr)
            raise

    def _api_json(self, path: str, tree: str | None = None, timeout: int = 30) -> dict:
        """GET {path}/api/json with optional tree parameter."""
        params = {}
        if tree:
            params["tree"] = tree
        return cast(dict, self._request("GET", f"{path}/api/json", params=params, timeout=timeout))

    def _get_crumb(self) -> dict[str, str] | None:
        """Fetch CSRF crumb from Jenkins. Cached after first call."""
        if self._crumb is not None:
            return self._crumb
        try:
            result = self._request("GET", "/crumbIssuer/api/json")
            self._crumb = result
            return self._crumb
        except (urllib.error.HTTPError, urllib.error.URLError):
            # Crumb issuer may be disabled
            self._crumb = {}
            return None

    # -----------------------------------------------------------------
    # Folder / Job listing
    # -----------------------------------------------------------------
    def list_top_level_jobs(self) -> list[dict]:
        """List all top-level folders and jobs."""
        result = self._api_json("", tree="jobs[name,_class,url,color]")
        return cast(list[dict], result.get("jobs", []))

    def list_jobs_in_folder(self, folder: str) -> list[dict]:
        """List all jobs inside a folder."""
        encoded_folder = urllib.parse.quote(folder, safe="")
        result = self._api_json(
            f"/job/{encoded_folder}",
            tree="jobs[name,_class,url,color]",
        )
        return cast(list[dict], result.get("jobs", []))

    def list_branches(self, folder: str, job: str) -> list[dict]:
        """List branches in a multibranch pipeline job."""
        encoded_folder = urllib.parse.quote(folder, safe="")
        encoded_job = urllib.parse.quote(job, safe="")
        result = self._api_json(
            f"/job/{encoded_folder}/job/{encoded_job}",
            tree="jobs[name,_class,url,color]",
        )
        return cast(list[dict], result.get("jobs", []))

    # -----------------------------------------------------------------
    # Job discovery
    # -----------------------------------------------------------------
    def find_job(self, repo_name: str) -> tuple[str, str] | None:
        """Search all top-level folders for a job matching repo_name.

        Returns (folder_name, job_name) or None.
        """
        top_level = self.list_top_level_jobs()
        for item in top_level:
            item_class = item.get("_class", "")
            item_name = item.get("name", "")

            # Direct match at top level (standalone job)
            if item_name == repo_name and item_class in _JOB_CLASSES:
                return ("", repo_name)

            # Search inside folders and org folders
            if item_class in _FOLDER_CLASSES | _MULTIBRANCH_CLASSES:
                # If it's a multibranch project matching by name, that's the job
                if item_class in _MULTIBRANCH_CLASSES and item_name == repo_name:
                    return ("", repo_name)

                # Search inside folder
                if item_class in _FOLDER_CLASSES:
                    try:
                        jobs = self.list_jobs_in_folder(item_name)
                        for job in jobs:
                            if job.get("name") == repo_name:
                                return (item_name, repo_name)
                    except (urllib.error.HTTPError, urllib.error.URLError):
                        continue
        return None

    # -----------------------------------------------------------------
    # Build operations
    # -----------------------------------------------------------------
    def _build_job_path(self, folder: str | None, job: str, branch: str | None = None) -> str:
        """Construct the Jenkins API path for a job.

        Handles: folder/job, folder/job/branch, job (no folder), job/branch.
        """
        parts = []
        if folder:
            parts.append(f"/job/{urllib.parse.quote(folder, safe='')}")
        parts.append(f"/job/{urllib.parse.quote(job, safe='')}")
        if branch:
            parts.append(f"/job/{url_encode_branch(branch)}")
        return "".join(parts)

    def get_last_build(
        self, folder: str | None, job: str, branch: str | None = None
    ) -> dict | None:
        """Get the last build for a job (optionally specific branch)."""
        path = self._build_job_path(folder, job, branch)
        try:
            return self._api_json(
                f"{path}/lastBuild",
                tree="number,result,displayName,timestamp,duration,url,building",
            )
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            raise

    def get_build_info(
        self, folder: str | None, job: str, branch: str | None, build_number: int
    ) -> dict | None:
        """Get info for a specific build number."""
        path = self._build_job_path(folder, job, branch)
        try:
            return self._api_json(
                f"{path}/{build_number}",
                tree="number,result,displayName,timestamp,duration,url,building",
            )
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            raise

    def get_build_console(
        self,
        folder: str | None,
        job: str,
        branch: str | None,
        build_number: int | str,
    ) -> str:
        """Get console output for a build. Returns raw text."""
        path = self._build_job_path(folder, job, branch)
        return cast(
            str,
            self._request(
                "GET",
                f"{path}/{build_number}/consoleText",
                accept_text=True,
            ),
        )

    def trigger_build(
        self,
        folder: str | None,
        job: str,
        branch: str | None = None,
        parameters: dict[str, str] | None = None,
    ) -> bool:
        """Trigger a build. Returns True on success."""
        path = self._build_job_path(folder, job, branch)
        if parameters:
            # Parameterized build
            param_list = [{"name": k, "value": v} for k, v in parameters.items()]
            self._request(
                "POST",
                f"{path}/build",
                data={"parameter": param_list},
            )
        else:
            self._request("POST", f"{path}/build")
        return True

    def get_job_info(self, folder: str | None, job: str, branch: str | None = None) -> dict | None:
        """Get job info including health reports and last build details."""
        path = self._build_job_path(folder, job, branch)
        try:
            return self._api_json(
                path,
                tree="name,_class,url,color,healthReport[description,score],"
                "lastBuild[number,result,timestamp,url,building],"
                "lastSuccessfulBuild[number,timestamp],"
                "lastFailedBuild[number,timestamp]",
            )
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            raise

    # -----------------------------------------------------------------
    # Queue
    # -----------------------------------------------------------------
    def get_queue_item(self, queue_id: int) -> dict | None:
        """Get information about a queued item by its ID."""
        try:
            return self._api_json(
                f"/queue/item/{queue_id}",
                tree="id,why,blocked,buildable,stuck,inQueueSince,actions[causes[shortDescription]],"
                "executable[number,url],task[name,url]",
            )
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            raise

    # -----------------------------------------------------------------
    # Change sets
    # -----------------------------------------------------------------
    def get_build_changesets(
        self,
        folder: str | None,
        job: str,
        branch: str | None,
        build_number: int | str,
    ) -> list[dict]:
        """Get change sets (commits) for a specific build."""
        path = self._build_job_path(folder, job, branch)
        try:
            result = self._api_json(
                f"{path}/{build_number}",
                tree="changeSets[items[commitId,timestamp,msg,author[fullName],"
                "affectedPaths],kind]",
            )
            return cast(list[dict], result.get("changeSets", []))
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return []
            raise

    # -----------------------------------------------------------------
    # Connectivity
    # -----------------------------------------------------------------
    def test_connection(self) -> bool:
        """Test connectivity and credentials with a lightweight request."""
        try:
            self._request("GET", "/api/json", params={"tree": "mode"}, timeout=15)
            return True
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError):
            return False
