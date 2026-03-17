---
name: bitbucket-manager
description: >
  Create, update, get, list, merge, decline, and comment on Bitbucket Cloud pull requests.
  View build/pipeline status checks, extract linked Jira issues from PRs, and list workspace
  repositories. Use when the user wants to manage Bitbucket PRs, check CI status, or browse
  repos. Pure Python stdlib — zero pip dependencies.
license: MIT
metadata:
  author: sagy101
  version: "1.0"
compatibility: >
  Python 3.10+. Bitbucket Cloud REST API v2.
  Requires an app password with repository and pull request read/write permissions.
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
- **Resolve** one or more PR comments in bulk
- **View comments** on one or more PRs (threaded view with filters)
- **Check** build/pipeline status for a PR or commit
- **Extract** Jira issue keys linked to a PR
- **List** repositories in a workspace

## Prerequisites

1. **Config**: `.bitbucket.json` in project root and/or `~/.bitbucket.json` for global defaults (see [CONFIG.md](references/CONFIG.md))
2. **Credentials**: `BITBUCKET_EMAIL` and `BITBUCKET_TOKEN` (app password) exported in shell profile or in a `.env` file

No pip install or venv needed — all scripts use Python stdlib only.

Config is auto-discovered — scripts search CWD upward, then `~/.bitbucket.json`. If both exist, they are deep-merged (project-level wins). No `--config` flag needed.

If no config is found anywhere, help the user create one. For users with one Bitbucket workspace, a global `~/.bitbucket.json` covers the shared settings:

```json
{
  "workspace": "<your-workspace>",
  "credentials": {
    "email_env": "BITBUCKET_EMAIL",
    "token_env": "BITBUCKET_TOKEN"
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
python3 <skill_dir>/scripts/bb_preflight.py
```

This checks Python version, config file, credentials, repo auto-detection, and API connectivity in one pass. Each check prints `[PASS]`, `[FAIL]`, or `[WARN]` with actionable fix instructions. Exit code 0 = all checks passed, 1 = at least one failed.

Skip the connectivity check (faster, offline-safe):

```bash
python3 <skill_dir>/scripts/bb_preflight.py --skip-connectivity
```

If any check fails, fix the issue and re-run before proceeding.

## Workflow

1. **Pre-flight** — run checks above
2. **Determine operation** — create / update / get / list / merge / decline / comment / checks
3. **Plan** — for create, update, merge, decline: show plan and **wait for user approval**
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

# Resolve a single comment (no --body needed)
python3 <skill_dir>/scripts/pr_comment.py --pr 42 --resolve 769609697

# Resolve multiple comments at once (1s delay between calls for rate-limit safety)
python3 <skill_dir>/scripts/pr_comment.py --pr 42 --resolve 769609697 769609700 769609705

# Dry run (works with single or bulk resolve)
python3 <skill_dir>/scripts/pr_comment.py --pr 42 --resolve 769609697 769609700 --dry-run

# Dry run for posting
python3 <skill_dir>/scripts/pr_comment.py --pr 42 --body "LGTM" --dry-run
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
3. **Never create, update, merge, or decline without plan + explicit user approval.** Use `--dry-run` for write operations.
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
| `401 Unauthorized` | Bad credentials | Verify `BITBUCKET_EMAIL` and `BITBUCKET_TOKEN` env vars. Token must be an app password, not account password |
| `403 Forbidden` | Insufficient permissions | App password needs repository and PR read/write scopes |
| `403` on resolve | Tried to resolve a general comment | Only inline (diff) comments can be resolved. General PR comments cannot be resolved via the API |
| `404 Not Found` | Wrong workspace, repo slug, or PR ID | Verify config `workspace` and run `repo_list.py` to check |
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
| App password vs OAuth token confusion | This skill uses app passwords (Basic auth). Create one at Bitbucket Settings > App passwords |
