---
name: bitbucket-manager
description: >
  Create, update, get, list, merge, decline, and comment on Bitbucket Cloud pull requests.
  Add, edit, delete, resolve, and reopen PR comments. View Bitbucket PR diffs, build checks,
  commit/branch pipeline status, pipeline steps/logs, environments, deployments, extract
  linked Jira issues from PRs, and list workspace repositories.
  Use when the user wants to manage Bitbucket PRs, view PR build checks, or browse repos.
  Pure Python stdlib — zero pip dependencies.
license: MIT
metadata:
  author: sagy101
  version: "1.0"
compatibility: >
  Python 3.10+. Bitbucket Cloud REST API v2.
  Requires a Bitbucket API token created with scopes
  (plain no-scope Atlassian tokens will fail for Bitbucket REST API access).
---

# Bitbucket Manager

Manage Bitbucket Cloud pull requests, build statuses, and repositories from the command line.

## When to use this skill

Use when the user wants to:
- **Create** a pull request from a feature branch
- **Update** PR title, description, reviewers, or destination branch
- **Get** PR details including reviewers and approval status
- **List** PRs filtered by state, author, or branch
- **Merge** a PR (with precondition checks)
- **Decline** a PR
- **Comment** on a PR (general or inline file-level comments)
- **Edit** an existing PR comment
- **Delete** one or more PR comments
- **Resolve** one or more PR comments in bulk
- **Reopen** resolved inline comment threads by ID
- **View comments** on one or more PRs (threaded view with filters)
- **View PR diffs** as raw text or compact summaries
- **View and run pipelines** plus inspect steps and step logs
- **View deployment environments and deployments**
- **View** Bitbucket PR build checks or commit/branch pipeline status
- **Extract** Jira issue keys linked to a PR
- **List** repositories in a workspace

## Prerequisites

1. **Config**: `.bitbucket.json` in project root and/or `~/.bitbucket.json` for global defaults (see [CONFIG.md](references/CONFIG.md))
2. **Credentials**:
   - recommended path: one personal Bitbucket API token with scopes via `BITBUCKET_EMAIL` + `BITBUCKET_TOKEN` and `credentials.auth_mode: "basic"` (default)
   - fallback path: per-repo repository access tokens configured in `repo_tokens` only if the personal-token path is unavailable in your org
   - compatibility path: a direct bearer token via `credentials.auth_mode: "bearer"` if you intentionally want that mode

Bitbucket token setup is important:
- Use **Create API token with scopes**, not the plain **Create API token** button
- Choose **Bitbucket** as the app when prompted
- Recommended minimal scopes for this skill:
  - `Repositories: Read`
  - `Pull requests: Read`
  - `Pipelines: Read`
  - `Workspace: Read`
  - `Pull requests: Write`
- `Repositories: Write` is not required for normal PR, comment, checks, and pipeline-read workflows in this skill.

If you use a plain no-scope Atlassian token, Bitbucket REST calls will fail with `401 Unauthorized` even if SSH git access works.

No pip install or venv needed — all scripts use Python stdlib only.

Config is auto-discovered — scripts search CWD upward, then `~/.bitbucket.json`. If both exist, they are deep-merged (project-level wins). No `--config` flag needed.

If no config is found anywhere, help the user create one. For users with one Bitbucket workspace, a global `~/.bitbucket.json` covers the shared settings:

```json
{
  "workspace": "<your-workspace>",
  "credentials": {
    "auth_mode": "basic",
    "email_env": "BITBUCKET_EMAIL",
    "token_env": "BITBUCKET_TOKEN"
  },
  "repo_tokens": {
    "<your-workspace>/<repo>": {
      "token_env": "MY_REPO_BITBUCKET_TOKEN"
    }
  }
}
```

Then a minimal per-project `.bitbucket.json` only needs optional overrides:
```json
{
  "default_reviewers": ["user1-uuid", "user2-uuid"],
  "default_destination": "master"
}
```

## Pre-flight checks

Run the preflight script before any other operation:

```bash
# Inside the target repo
python3 <skill_dir>/scripts/bb_preflight.py

# From a parent or different repo
python3 <skill_dir>/scripts/bb_preflight.py --repo <repo_slug>
```

This checks Python version, config file, credentials, repo auto-detection, and API connectivity in one pass. Each check prints `[PASS]`, `[FAIL]`, or `[WARN]` with actionable fix instructions. Exit code 0 = all checks passed, 1 = at least one failed.

If connectivity fails with a `401`, check the token type before anything else:
- a no-scope Atlassian token is not enough for Bitbucket REST
- the preferred setup is one Bitbucket personal API token created with scopes, used with `BITBUCKET_EMAIL`
- `BITBUCKET_EMAIL` must match the Atlassian account that created the token
- recommended minimum scopes are `Repositories: Read`, `Pull requests: Read`, `Pipelines: Read`, `Workspace: Read`, and `Pull requests: Write`
- if that personal-token path is unavailable or Bitbucket still rejects it, configure a repository token in `repo_tokens` for the target `workspace/repo`
- direct `auth_mode: "bearer"` remains available for compatibility, but `repo_tokens` is only a fallback model

Skip the connectivity check (faster, offline-safe):

```bash
python3 <skill_dir>/scripts/bb_preflight.py --skip-connectivity
```

If any check fails, fix the issue and re-run before proceeding.

When operating from a parent or nested repo context, pass `--repo <repo_slug>` so the shared auth resolver validates and selects auth for the intended target repo rather than the nearest enclosing repo.

## Workflow

1. **Pre-flight** — run checks above
2. **Determine operation** — create / update / get / list / merge / decline / comment / edit / delete / checks
3. **Plan** — for create, update, merge, decline, edit, delete: show plan and **wait for user approval**
4. **Execute** — run the appropriate script
5. **Verify** — offer to get PR details or list checks after write operations

## Operations

### Create a pull request

```bash
python3 <skill_dir>/scripts/pr_create.py \
  --title "Add login page" --source feature/login --destination main \
  --description "Implements the login page" --reviewers "uuid1,uuid2" \
  --close-source-branch --dry-run
```

Remove `--dry-run` after review. Omit `--destination` to use the config default. Omit `--reviewers` to use config `default_reviewers`.

### Update a pull request

```bash
python3 <skill_dir>/scripts/pr_update.py \
  --pr 42 --title "New Title" --description "Updated description" --dry-run
```

Flags: `--title`, `--description`, `--destination`, `--reviewers`. At least one required.

### Get PR details

```bash
python3 <skill_dir>/scripts/pr_get.py --pr 42
python3 <skill_dir>/scripts/pr_get.py --pr 42 --format json
```

Shows title, state, author, branch, reviewers with approval status.

### List pull requests

```bash
python3 <skill_dir>/scripts/pr_list.py --state OPEN
python3 <skill_dir>/scripts/pr_list.py --state MERGED --author "jane" --max-results 20
python3 <skill_dir>/scripts/pr_list.py --branch feature/login --format json
```

States: `OPEN`, `MERGED`, `DECLINED`, `SUPERSEDED`.

### Merge a pull request

```bash
python3 <skill_dir>/scripts/pr_merge.py --pr 42 --dry-run
python3 <skill_dir>/scripts/pr_merge.py --pr 42 --strategy squash --close-source-branch
```

Strategies: `merge_commit` (default), `squash`, `fast_forward`. `--dry-run` shows merge preconditions: approvals, build checks, open tasks.

### Decline a pull request

```bash
python3 <skill_dir>/scripts/pr_decline.py --pr 42 --dry-run
python3 <skill_dir>/scripts/pr_decline.py --pr 42
```

### Add a comment

```bash
# General comment
python3 <skill_dir>/scripts/pr_comment.py --pr 42 --body "Looks good!"

# Inline comment on a file
python3 <skill_dir>/scripts/pr_comment.py --pr 42 --body "Fix this" --file src/app.py --line 25

# Threaded reply to an existing comment
python3 <skill_dir>/scripts/pr_comment.py --pr 42 --body "Fixed in latest push." --parent-id 769609697

# Dry run for posting
python3 <skill_dir>/scripts/pr_comment.py --pr 42 --body "LGTM" --dry-run
```

### Edit a comment

```bash
# Edit an existing comment (requires --body with new text)
python3 <skill_dir>/scripts/pr_comment.py --pr 42 --edit 769609697 --body "Updated review comment"

# Dry run
python3 <skill_dir>/scripts/pr_comment.py --pr 42 --edit 769609697 --body "Updated text" --dry-run
```

### Delete comments

```bash
# Delete a single comment
python3 <skill_dir>/scripts/pr_comment.py --pr 42 --delete 769609697

# Delete multiple comments (1s delay between calls for rate-limit safety)
python3 <skill_dir>/scripts/pr_comment.py --pr 42 --delete 769609697 769609700 769609705

# Dry run
python3 <skill_dir>/scripts/pr_comment.py --pr 42 --delete 769609697 769609700 --dry-run
```

### Resolve comments

```bash
# Resolve a single comment (no --body needed)
python3 <skill_dir>/scripts/pr_comment.py --pr 42 --resolve 769609697

# Resolve multiple comments at once (1s delay between calls for rate-limit safety)
python3 <skill_dir>/scripts/pr_comment.py --pr 42 --resolve 769609697 769609700 769609705

# Dry run
python3 <skill_dir>/scripts/pr_comment.py --pr 42 --resolve 769609697 769609700 --dry-run
```

### Reopen resolved comments

```bash
# Reopen a single resolved inline comment thread
python3 <skill_dir>/scripts/pr_comment.py --pr 42 --unresolve 769609697

# Reopen multiple threads
python3 <skill_dir>/scripts/pr_comment.py --pr 42 --unresolve 769609697 769609700

# Dry run
python3 <skill_dir>/scripts/pr_comment.py --pr 42 --unresolve 769609697 --dry-run
```

### Show a PR diff

```bash
python3 <skill_dir>/scripts/pr_diff.py --pr 42
python3 <skill_dir>/scripts/pr_diff.py --pr 42 --format summary
python3 <skill_dir>/scripts/pr_diff.py --pr 42 --format json
```

### List comments

```bash
# Single PR — threaded view with resolution status, tree connectors
python3 <skill_dir>/scripts/pr_comments.py --pr 42

# Multiple PRs in one call (same repo)
python3 <skill_dir>/scripts/pr_comments.py --pr 42 43 44

# Filter: only unresolved threads
python3 <skill_dir>/scripts/pr_comments.py --pr 42 --status unresolved

# Filter: by author (substring match, case-insensitive)
python3 <skill_dir>/scripts/pr_comments.py --pr 42 --author "Alice"

# Filter: inline comments on a specific file
python3 <skill_dir>/scripts/pr_comments.py --pr 42 --file "src/app.py"

# Filter: threads with discussion (has replies)
python3 <skill_dir>/scripts/pr_comments.py --pr 42 --has-replies

# Filter: standalone comments (no replies)
python3 <skill_dir>/scripts/pr_comments.py --pr 42 --no-replies

# Combine filters (AND logic)
python3 <skill_dir>/scripts/pr_comments.py --pr 42 --status unresolved --has-replies

# JSON output
python3 <skill_dir>/scripts/pr_comments.py --pr 42 --format json
```

Shows threaded view with thread headers (numbering, resolution status with who/when), tree connectors (`+--`, `|`) for replies, and summary line. Unresolved threads are listed first.

### Check build status for a PR

```bash
python3 <skill_dir>/scripts/pr_checks.py --pr 42
python3 <skill_dir>/scripts/pr_checks.py --pr 42 --format json
```

### List pipelines

```bash
python3 <skill_dir>/scripts/pipeline_list.py
python3 <skill_dir>/scripts/pipeline_list.py --max-results 200
python3 <skill_dir>/scripts/pipeline_list.py --format json
python3 <skill_dir>/scripts/pipeline_get.py --pipeline "{pipeline-uuid}"
python3 <skill_dir>/scripts/pipeline_get.py --pipeline "{pipeline-uuid}" --format json
python3 <skill_dir>/scripts/pipeline_run.py --branch main --selector "Deploy to production"
python3 <skill_dir>/scripts/pipeline_run.py --branch main --selector "Deploy to production" --dry-run
python3 <skill_dir>/scripts/pipeline_steps.py --pipeline "{pipeline-uuid}" --max-results 100
python3 <skill_dir>/scripts/pipeline_step_get.py --pipeline "{pipeline-uuid}" --step "{step-uuid}"
python3 <skill_dir>/scripts/pipeline_log.py --pipeline "{pipeline-uuid}" --step "{step-uuid}" --log "{log-uuid}"
```

### List environments and deployments

```bash
python3 <skill_dir>/scripts/environment_list.py
python3 <skill_dir>/scripts/environment_list.py --max-results 200
python3 <skill_dir>/scripts/environment_get.py --environment "{environment-uuid}"
python3 <skill_dir>/scripts/deployment_list.py
python3 <skill_dir>/scripts/deployment_list.py --max-results 200
python3 <skill_dir>/scripts/deployment_get.py --deployment "{deployment-uuid}"
```

### Check build status for a commit or branch

```bash
python3 <skill_dir>/scripts/build_status.py --commit abc123def
python3 <skill_dir>/scripts/build_status.py --branch main
```

### Extract Jira issues from a PR

```bash
python3 <skill_dir>/scripts/pr_jira.py --pr 42
python3 <skill_dir>/scripts/pr_jira.py --pr 42 --format json
```

Scans branch name, PR title, description, and commit messages for Jira-style keys (e.g. `PROJ-123`).

### List repositories

```bash
python3 <skill_dir>/scripts/repo_list.py
python3 <skill_dir>/scripts/repo_list.py --name "api" --max-results 100
```

### Common flags (all scripts)

All scripts accept `--repo <slug>` (auto-detected from git remote if omitted), `--workspace <name>` (from config if omitted), and `--config <path>` (auto-discovered if omitted).

## Important rules

1. **ALWAYS use the provided scripts.** Every operation has a dedicated script. Run them via `python3 <skill_dir>/scripts/<script>.py`. NEVER write inline Python to call `BitbucketClient`, `bb_config`, or the Bitbucket REST API directly. The scripts handle auth, config merging, error formatting, repo auto-detection, and pagination.
2. **If a script fails, debug the script invocation** (wrong flags, missing config, missing credentials). Do NOT abandon the scripts and write custom code. Check the error table below and re-run with corrected arguments.
3. **Never create, update, merge, decline, edit, or delete without plan + explicit user approval.** Use `--dry-run` for write operations.
4. **Never print credentials.** Only confirm env vars are set.
5. **Repo slug is auto-detected from git remote.** Override with `--repo` if needed.

## Formatting guidelines

Bitbucket Cloud renders PR descriptions, comments, and commit messages using **Python-Markdown** with these extensions: `codehilite`, `tables`, `def_list`, `del`, `footnotes`, `fenced_code`, `sane_lists`, `abbr`, `toc`, `wikilinks`. Arbitrary HTML (e.g. `<table>`) is **not** supported.

When composing `--description` or `--body` arguments:

- **Use real newlines**, not `\n` escape sequences. Shell `\n` is passed as literal text, not a line break. Use multi-line quoted strings or heredocs instead.
- **Supported syntax**: headings (`#`), bold/italic, bullet/numbered lists, fenced code blocks (` ``` `), tables (`| col |`), links, inline code, strikethrough (`~~text~~`), definition lists.
- **References**: `issue #N`, `pull request #N`, `@username`, short commit hashes are auto-linked.
- **Emoji**: `:emoji_name:` syntax (e.g. `:white_check_mark:`).
- **Not supported**: raw HTML tags, `<details>/<summary>` blocks, image uploads (use markdown image links instead).

## Error handling

| Error | Cause | Fix |
|---|---|---|
| `401 Unauthorized` | Wrong token type, wrong email, expired token, or invalid credentials | Verify `BITBUCKET_EMAIL` and `BITBUCKET_TOKEN`. Prefer one Bitbucket personal API token created via **Create API token with scopes**; plain no-scope Atlassian tokens will fail |
| `403 Forbidden` | Insufficient permissions | Add the missing Bitbucket scopes. Recommended minimum: Repositories Read, Pull requests Read, Pipelines Read, Workspace Read, Pull requests Write |
| `403` on resolve | Tried to resolve a general comment | Only inline (diff) comments can be resolved. General PR comments cannot be resolved via the API |
| `403` on delete | Not the comment author | You can only delete comments you authored |
| `404 Not Found` | Wrong workspace, repo slug, PR ID, or comment ID | Verify config `workspace` and run `repo_list.py` to check |
| `400 Bad Request` | Invalid payload (e.g. bad branch name) | Check branch exists; review `--dry-run` output |
| `409 Conflict` | Merge conflict or PR not mergeable | Resolve conflicts in the source branch first |
| `429 Too Many Requests` | Rate limited | Automatic retry with exponential backoff (2s/4s/8s, 3 retries). If still failing, wait and retry manually. Bitbucket Cloud limit: 1000 req/hr |
| Config not found | No `.bitbucket.json` anywhere | Create `~/.bitbucket.json` with workspace and credentials |
| Repo auto-detect failed | No `origin` remote or not a Bitbucket URL | Provide `--repo <slug>` explicitly |
| `env_file escapes project root` | Relative `env_file` in global config resolves outside `~` | Use an absolute path for `env_file` in global `~/.bitbucket.json` |
| `env_file not found` | Path in config doesn't exist | Check the `env_file` path in config; use absolute path in global config |

## Troubleshooting

| Problem | Fix |
|---|---|
| `python3: command not found` | Install Python 3.10+ |
| Can't detect repo from git remote | Provide `--repo <slug>` explicitly |
| Merge fails with "unresolved merge conflicts" | Resolve conflicts on source branch, push, then retry |
| Wrong workspace detected | Set `workspace` in `.bitbucket.json` or use `--workspace` flag |
| API token vs OAuth token confusion | This skill uses Basic auth with `BITBUCKET_EMAIL` + `BITBUCKET_TOKEN`. Create the token via **Create API token with scopes** in Bitbucket settings |
