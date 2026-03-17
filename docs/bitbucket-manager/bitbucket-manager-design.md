# Bitbucket Manager Skill — Design Document

> This document covers **why** this skill exists and the **key decisions** an implementer or reviewer needs to understand.

---

## Why This Skill Exists

Managing Bitbucket PRs from an AI coding agent requires auth setup, API pagination, repo detection, and structured error handling. Without a skill, agents write ad-hoc `curl` commands or inline Python that misses pagination, lacks dry-run previews, and hardcodes workspace/repo values.

This skill gives **any SKILL.md-compatible agent** reliable Bitbucket Cloud PR management through deterministic CLI scripts that handle all the plumbing.

---

## Capabilities

| Capability | Description |
|---|---|
| **Create PR** | Open a pull request with title, description, reviewers, close-source-branch flag |
| **Update PR** | Modify title, description, destination branch, or reviewers with diff preview |
| **Get PR** | Fetch PR details including reviewers with approval status |
| **List PRs** | Filter by state, author, branch; table or JSON output |
| **Merge PR** | Merge with strategy selection and precondition check (approvals, builds, tasks) |
| **Decline PR** | Close a PR without merging |
| **PR comments** | Add general, inline, or threaded reply comments; list comments in threaded view |
| **Resolve/reopen comments** | Resolve or reopen comment threads via dedicated API endpoints |
| **PR checks** | View build/pipeline status checks for a PR |
| **Build status** | View CI status for a specific commit SHA or branch HEAD |
| **Jira extraction** | Scan branch, title, description, and commits for Jira issue keys |
| **List repos** | Browse repositories in a workspace with name filtering |

---

## Key Design Decisions

**1. Zero pip dependencies** — Pure Python stdlib (`urllib`, `json`, `base64`, `argparse`, `subprocess`, `concurrent.futures`). No venv, no setup script, no install step. This eliminates dependency conflicts and makes the skill instantly usable on any system with Python 3.10+.

**2. One script per operation** — Each operation is a standalone CLI script. The agent picks which script to run based on the user's intent. Scripts share `bb_config.py` (config/credential resolution) and `bb_client.py` (HTTP client with pagination). This makes the agent's decision space small and deterministic.

**3. Repo auto-detection from git remote** — Scripts parse `git remote get-url origin` to extract `{workspace}/{repo_slug}` from SSH or HTTPS Bitbucket URLs. The `--repo` flag overrides when auto-detection fails (e.g., non-Bitbucket remotes, multiple remotes).

**4. Config hierarchy mirrors jira-manager/confluence-publisher** — Global `~/.bitbucket.json` → local `.bitbucket.json` → CLI flags. Deep-merge on overlap. This is a proven pattern from the other Atlassian skills in this repo and means users with one workspace only configure once.

**5. Credentials via environment variables** — Never stored in config files, never logged. Config stores only the *names* of the env vars (`email_env`, `token_env`). Missing credentials produce actionable error messages with shell-specific setup commands.

**6. Dry-run for all write operations** — `pr_create`, `pr_update`, `pr_merge`, `pr_decline`, and `pr_comment` all support `--dry-run`. Merge dry-run is particularly useful — it shows approval count, build check results, and open tasks before committing to the merge.

**7. Bitbucket API v2 pagination handled in client** — The `_paginate()` method in `bb_client.py` follows Bitbucket's `next` URL pattern automatically. Individual scripts never deal with pagination logic.

**8. Parallel fetching for enrichment** — The `_parallel_fetch()` helper in `bb_client.py` uses `ThreadPoolExecutor` (max 5 workers) to batch independent API calls. Used by `get_pr_comments()` to fetch resolution status for each root comment in parallel rather than sequentially. Reusable for any future batch operation.

**9. Comments always include resolution status** — The Bitbucket list-comments endpoint does not reliably return resolution details, so `get_pr_comments()` enriches each root comment with an individual GET. Child comments inherit resolution from their parent thread. This ensures the agent always sees `[RESOLVED]` status without extra calls.

---

## Approval Gates

| Action | Approval Required | Mechanism |
|---|---|---|
| **Create PR** | Yes | `--dry-run` shows payload; agent shows plan and waits for approval |
| **Update PR** | Yes | `--dry-run` shows current vs proposed diff |
| **Merge PR** | Yes | `--dry-run` shows merge preconditions (approvals, builds, tasks) |
| **Decline PR** | Yes | `--dry-run` shows PR title and state |
| **Add comment** | Yes | `--dry-run` shows comment preview |
| **Approve PR** | N/A | **Intentionally omitted.** No approve script exists. PR approval is a human-only action — the user must approve PRs directly in Bitbucket. This prevents agents from rubber-stamping their own PRs or approving without genuine code review. |
| **Get/List/Checks** | No | Read-only operations |

---

## Risks at a Glance

| Risk | Severity | Mitigation |
|---|---|---|
| Accidental merge of unreviewed PR | High | `--dry-run` shows preconditions; agent must get user approval |
| Credential exposure in logs | High | Credentials resolved from env vars, never printed; config stores only var names |
| Wrong repo targeted | Medium | Auto-detect from git remote; `--dry-run` shows workspace/repo before action |
| Rate limiting (1000 req/hr) | Low | Pagination uses reasonable page sizes (50); scripts don't retry automatically |

---

## References

- **Bitbucket Cloud REST API v2** — The underlying API for all operations
- **jira-manager** — Sister skill; shares config/credential patterns
- **confluence-publisher** — Sister skill; shares config/credential patterns

## Status

**Stable (v1.2)** — Comments now always include resolution status via parallel-enriched individual fetches. Added `_parallel_fetch()` helper to `bb_client.py` using `concurrent.futures.ThreadPoolExecutor`.
