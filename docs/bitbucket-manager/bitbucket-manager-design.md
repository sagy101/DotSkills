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
| **PR comments** | Add general, inline, or threaded reply comments; list comments with threaded display, filters, and multi-PR support |
| **Bulk resolve comments** | Resolve one or more comment threads by explicit ID with rate-limit-safe 1s delay between calls |
| **Reopen comments** | Reopen resolved inline comment threads by explicit ID |
| **Comment filtering** | Filter threads by resolution status, author, file path, and reply presence |
| **PR diff** | Fetch raw diff text or a compact per-file summary for automation |
| **Pipelines** | List, inspect, trigger, and inspect steps/logs for repository pipelines |
| **Environments** | List and inspect repository deployment environments |
| **Deployments** | List and inspect repository deployment records |
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

**10. Shared thread-building module (`bb_threads.py`)** — Thread construction and filtering logic is shared between `pr_comments.py` (display) and `pr_comment.py` (bulk resolve) via a `Thread` dataclass and `build_threads()`/`filter_threads()` functions. This avoids duplicating tree-building logic.

**11. Rate-limit handling** — `bb_client.py._request()` automatically retries HTTP 429 responses with exponential backoff (2s, 4s, 8s — 3 retries max). Bulk resolve operations additionally space calls 1s apart per Atlassian's recommendation for mutative requests. Bitbucket Cloud does not return `Retry-After` headers, so backoff is time-based.

**12. Agent-optimised comment display** — Threaded view uses thread headers with numbering and resolution details (who/when), tree connectors (`+--`, `|`) for replies, and a summary line. Unresolved threads sort first. Filters (`--status`, `--author`, `--file`, `--has-replies`, `--no-replies`) operate at thread level and combine with AND logic. `pr_comment.py` also supports reopening resolved inline comment threads by ID.

**13. Thin workflow scripts for pipelines and deployments** — New Bitbucket CLI entrypoints stay intentionally small: one command each for PR diffs, pipeline listing/getting/running/step listing/log fetch, and environment/deployment listing/getting. This keeps the user-facing interface simple while mapping directly to the REST endpoints.

**14. Basic-first auth with repo-token fallback** — The default path remains personal Bitbucket REST auth using `BITBUCKET_EMAIL` + `BITBUCKET_TOKEN`. If that auth is unavailable or Bitbucket rejects it, shared code may fall back to a repository access token configured for the resolved target repo. This preserves the existing happy path while unblocking orgs where personal scoped Bitbucket tokens are broken or disallowed.

**15. One central config, no per-repo config drift** — Bitbucket auth should stay centrally managed in `~/.bitbucket.json`. The config may include a `repo_tokens` map keyed by `workspace/repo`, so the skill can choose the correct repository token without asking users to duplicate config in every repo checkout.

**16. Repo-scoped bearer support only** — Bearer-token support is intentionally limited to Bitbucket repository access tokens for now. Workspace and project bearer tokens stay out of scope to avoid broadening semantics, endpoint assumptions, and test surface before they are needed.

**17. Existing CLI flags stay stable** — Repo-level scripts already support `--repo` and `--workspace`. The upgrade should preserve those interfaces. Agents inside a target repo can keep omitting `--repo`; agents operating from a parent or nested repo context should use `--repo` explicitly.

**18. Explicit fallback reporting** — If the skill falls back from `basic` auth to a repo token, preflight and user-facing errors should say so clearly. Silent fallback makes debugging harder and weakens trust during live demos.

**19. Target-repo resolution must be shared** — All Bitbucket scripts should resolve the target repo through the same shared code path. That resolver must respect explicit `--repo`, otherwise use the nearest enclosing git repo, and support nested-repo layouts such as `cap-projects` containing `cap-onboarding`.

**20. Workspace-wide actions remain basic-auth-centric** — Operations like listing all repos in a workspace should keep working with personal auth. When only a repo token is available, the skill should fail clearly rather than pretending a repo-scoped token can browse the whole workspace.

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
| Rate limiting (1000 req/hr) | Low | Automatic 429 retry with exponential backoff; bulk resolve uses 1s delay between calls |

---

## Auth Upgrade Design

### Problem Statement

Some Atlassian orgs currently cannot create working personal Bitbucket scoped tokens because the Atlassian token UI has an expiry-date bug. In those environments, the existing Bitbucket skill fails at REST auth even though the agent workflow and repo access are otherwise valid.

The skill therefore needs a backward-compatible fallback path that:

- preserves current behavior for users whose personal Bitbucket API token already works
- supports repository access tokens without changing every script interface
- works from nested-repo and parent-repo layouts
- keeps failures actionable for agents and humans

### Config Model

The upgraded central config should support:

```json
{
  "workspace": "firelayers",
  "credentials": {
    "auth_mode": "basic",
    "email_env": "BITBUCKET_EMAIL",
    "token_env": "BITBUCKET_TOKEN"
  },
  "repo_tokens": {
    "firelayers/cap-onboarding": {
      "token_env": "BITBUCKET_CAP_ONBOARDING_TOKEN"
    },
    "firelayers/dotskills": {
      "token_env": "BITBUCKET_DOTSKILLS_TOKEN"
    }
  }
}
```

Rules:

- `credentials` remains the default personal-auth configuration.
- `repo_tokens` is optional and keyed by canonical `workspace/repo`.
- Each `repo_tokens` entry represents a Bitbucket repository access token only.
- Existing configs without `repo_tokens` remain valid.

### Auth Selection Rules

For every repo-scoped command:

1. Resolve the target repo:
   - explicit `--repo` wins
   - otherwise use the nearest enclosing git repo
2. Attempt default `basic` auth if it is configured
3. If `basic` auth is missing or Bitbucket rejects it, look up `workspace/repo` in `repo_tokens`
4. If a repo token exists, retry with bearer auth and report that fallback happened
5. If no repo token exists, fail with an actionable message instructing the agent to ask the human to configure auth for that repo

This model keeps the default behavior unchanged for current users while making fallback deterministic.

### Repo Resolution Rules

The skill must handle nested repo layouts and parent-repo working directories safely.

- If the agent is inside `~/cap-projects/cap-onboarding`, the target repo is `cap-onboarding`.
- If the agent is inside `~/cap-projects` and does not pass `--repo`, the target repo is `cap-projects`.
- If the agent is inside `~/cap-projects` but intends to operate on `cap-onboarding`, it should pass `--repo cap-onboarding`, and shared resolution code should target that child repo.

The resolver should not recursively guess a repo when no explicit target is available and multiple candidates could exist.

### Preflight Behavior

Preflight should validate the exact auth path that would be used for the resolved target repo.

- If `basic` auth succeeds, report that
- If `basic` auth fails and a repo token succeeds, report the fallback explicitly
- If neither works, report whether the failure was:
  - missing `basic` credentials
  - `basic` rejected by Bitbucket
  - missing repo-token mapping
  - missing repo-token environment variable
  - repo-token auth rejection

Preflight should validate one target repo at a time, not every repo in a directory tree.

### Out Of Scope

This upgrade intentionally does not include:

- workspace bearer tokens
- project bearer tokens
- storing repo hierarchies in config
- automatic multi-repo scans that silently change the target repo
- breaking CLI compatibility for existing scripts

### Documentation Impact

The implementation must update:

- `bitbucket-manager/SKILL.md`
- `bitbucket-manager/references/CONFIG.md`
- this design document
- any user-facing guidance that currently assumes “create a personal scoped API token” is always the answer

### Testing Impact

The implementation must preserve all existing basic-auth behavior and add coverage for:

- `repo_tokens` config parsing
- target repo resolution with and without `--repo`
- bearer fallback after rejected `basic` auth
- actionable errors when a repo token is missing for a target repo
- clear behavior for workspace-level commands under repo-token-only conditions

---

## References

- **Bitbucket Cloud REST API v2** — The underlying API for all operations
- **jira-manager** — Sister skill; shares config/credential patterns
- **confluence-publisher** — Sister skill; shares config/credential patterns

## Status

**Stable with planned auth upgrade** — Current PR/comment/pipeline functionality remains stable. A backward-compatible auth-resolution upgrade is planned to add repository-token fallback without regressing existing personal-token users.
