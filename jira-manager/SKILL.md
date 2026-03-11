---
name: jira-manager
description: >
  Create, update, fetch, delete, diff, and validate Jira tickets from structured markdown or JSON sources. Supports full field discovery (statuses, priorities, components, versions, sprints, custom fields), generic --set and --filter flags, Agile board/sprint operations (list boards, fetch board issues, bulk update by board/JQL/filter/ticket list), status transitions, comments, issue links (blockers, duplicates, etc.), markdown/Jira markup conversion, and link rewriting. Works with any Jira Cloud instance.
license: MIT
metadata:
  author: sagy101
  version: "1.5"
compatibility: >
  Python 3.10+. Jira Cloud REST API v2 + Agile REST API v1.0.
  Requires an API token with issue read/write permissions.
---

# Jira Manager

CRUD for Jira tickets with field discovery, sprint management, status transitions, comments, issue links, link rewriting, and estimation validation.

## When to use this skill

Use when the user wants to:
- **Create** tickets (single or bulk from markdown/JSON spec)
- **Update** fields, status, sprint, attachments, comments, or issue links on existing issues
- **Fetch** issues by key, JQL, filters (assignee, status, etc.), or parent
- **Delete** issues (with confirmation)
- **Diff** local definitions against live Jira
- **Validate** sub-ticket estimate sums against parents
- **Discover** fields, issue types, statuses, priorities, components, versions, sprints
- **List boards** or move issues to sprints (Agile API)

## Prerequisites

1. **Config**: `.jira.json` in project root and/or `~/.jira.json` for global defaults (see [CONFIG.md](references/CONFIG.md))
2. **Credentials**: `JIRA_EMAIL` and `JIRA_TOKEN` exported in shell profile (recommended) or in a `.env` file
3. **Python deps**: installed via `setup_env.py` (shared venv in skill dir)

Config is auto-discovered — scripts search CWD upward, then `~/.jira.json`. If both exist, they are deep-merged (project-level wins). No `--config` flag needed.

If no config is found anywhere, help the user create one. For users with one Atlassian instance, a global `~/.jira.json` covers the shared settings:

```json
{
  "jira_url": "https://mycompany.atlassian.net",
  "credentials": { "username_env": "JIRA_EMAIL", "token_env": "JIRA_TOKEN" }
}
```

Then a minimal per-project `.jira.json` only needs:
```json
{
  "project_key": "PROJ"
}
```

## Pre-flight checks

1. **Python env** — verify shared venv exists: `<skill_dir>/.venv/bin/python -c "import markdown; print('OK')"`. If missing: `python3 <skill_dir>/scripts/setup_env.py`
2. **Config** — `.jira.json` must exist in project root or `~/.jira.json` for global defaults. Scripts auto-discover; no `--config` flag needed.
3. **Credentials** — confirm env vars are set (substitute names from `.jira.json`). Never print values. If missing, advise the user to set them globally in their shell profile:
   - **zsh** (macOS default): `echo 'export JIRA_TOKEN="<value>"' >> ~/.zshrc && source ~/.zshrc`
   - **bash**: `echo 'export JIRA_TOKEN="<value>"' >> ~/.bashrc && source ~/.bashrc`
   - **fish**: `set -Ux JIRA_TOKEN '<value>'`
4. **Field discovery** — if `field_mappings` or `issue_types` are empty:
```bash
<skill_dir>/.venv/bin/python <skill_dir>/scripts/discover_fields.py --all --apply
```
This populates `field_catalog` (statuses, priorities, components, versions, sprints), enabling `--set`, `--status`, `--priority`, `--sprint`, etc.

## Workflow

1. **Pre-flight** — run checks above
2. **Determine operation** — create / update / fetch / delete / diff / validate
3. **Plan** — for create, update, delete: show plan and **wait for user approval**
4. **Execute** — run the appropriate script
5. **Verify** — offer to validate estimates, diff, or fetch results

## Operations

### Create a single ticket

```bash
<skill_dir>/.venv/bin/python <skill_dir>/scripts/create_ticket.py \
  --type story --summary "Title" \
  --description "Desc" --epic PROJ-100 --story-points 2 \
  --priority "High" --status "In Progress" --sprint "Sprint 42" \
  --rewrite-links --attachment screenshot.png
```

For subtasks: `--type subtask --parent PROJ-101` instead of `--epic`.

Field flags: `--priority`, `--status`, `--assignee`, `--component` (repeatable), `--fix-version` (repeatable), `--sprint`, `--labels`, `--story-points`, `--set "field=value"` (repeatable), `--attachment` (repeatable).

### Bulk create from source file

See [SOURCE_FORMAT.md](references/SOURCE_FORMAT.md) for markdown/JSON format.

```bash
<skill_dir>/.venv/bin/python <skill_dir>/scripts/bulk_create.py \
  --source tickets.md --epic PROJ-100 --rewrite-links --dry-run
```

Remove `--dry-run` after review. Already-created tickets (`.jira-manifest.json`) are skipped.

### Bulk update tickets

Update multiple tickets by list, board, JQL, or filter.

```bash
# List of tickets
<skill_dir>/.venv/bin/python <skill_dir>/scripts/bulk_update.py \
  --tickets "PROJ-1,PROJ-2" --status "Done"

# Board active sprint (default — only active sprint issues)
<skill_dir>/.venv/bin/python <skill_dir>/scripts/bulk_update.py \
  --board-id 123 --sprint "Sprint 5"

# Board all issues (--board-all skips active sprint filter)
<skill_dir>/.venv/bin/python <skill_dir>/scripts/bulk_update.py \
  --board-id 123 --board-all --status "Done"

# Filter query
<skill_dir>/.venv/bin/python <skill_dir>/scripts/bulk_update.py \
  --filter status="In Progress" --assignee "me"

# JQL query
<skill_dir>/.venv/bin/python <skill_dir>/scripts/bulk_update.py \
  --jql "project=PROJ AND priority=High" --priority "Medium"
```

Requires `--confirm` to execute (defaults to dry-run preview).

### Update existing tickets

```bash
# Update fields
<skill_dir>/.venv/bin/python <skill_dir>/scripts/update_ticket.py \
  --key PROJ-101 --summary "New Title" --story-points 3

# Status transition, sprint, priority, assignee
<skill_dir>/.venv/bin/python <skill_dir>/scripts/update_ticket.py \
  --key PROJ-101 --status "In Progress" \
  --sprint "Sprint 42" --priority "High" --assignee "user@example.com"

# Generic field by name, attachments
<skill_dir>/.venv/bin/python <skill_dir>/scripts/update_ticket.py \
  --key PROJ-101 --set "components=Backend" --attachment report.pdf

# Add a comment
<skill_dir>/.venv/bin/python <skill_dir>/scripts/update_ticket.py \
  --key PROJ-101 --comment "Completed code review."

# Add an issue link (blocker)
<skill_dir>/.venv/bin/python <skill_dir>/scripts/update_ticket.py \
  --key PROJ-101 --link "Blocks:PROJ-200"

# Add a reverse link ("is blocked by" swaps direction automatically)
<skill_dir>/.venv/bin/python <skill_dir>/scripts/update_ticket.py \
  --key PROJ-101 --link "is blocked by:PROJ-50"

# Multiple links + comment in one call
<skill_dir>/.venv/bin/python <skill_dir>/scripts/update_ticket.py \
  --key PROJ-101 --link "Blocks:PROJ-200" --link "Duplicate:PROJ-300" \
  --comment "Linking related issues."
```

Named flags: `--status`, `--priority`, `--assignee`, `--component`, `--fix-version`, `--sprint`, `--labels`, `--story-points`, `--set "field=value"`, `--attachment`, `--comment`, `--link` (repeatable).

### Fetch tickets

```bash
# Single ticket (detail view)
<skill_dir>/.venv/bin/python <skill_dir>/scripts/fetch_tickets.py \
  --key PROJ-101 --format detail

# JQL search
<skill_dir>/.venv/bin/python <skill_dir>/scripts/fetch_tickets.py \
  --jql "project=PROJ AND type=Story" --format table

# Filter by field values (builds JQL automatically)
<skill_dir>/.venv/bin/python <skill_dir>/scripts/fetch_tickets.py \
  --filter assignee=currentUser() status="In Progress"

# Children of epic or story
<skill_dir>/.venv/bin/python <skill_dir>/scripts/fetch_tickets.py \
  --children-of PROJ-100

# Board issues — active sprint only (default)
<skill_dir>/.venv/bin/python <skill_dir>/scripts/fetch_tickets.py \
  --board-id 123

# Board issues — all (includes backlog, closed, past sprints)
<skill_dir>/.venv/bin/python <skill_dir>/scripts/fetch_tickets.py \
  --board-id 123 --board-all --max-results 200

# Board + filter (active sprint + additional filters)
<skill_dir>/.venv/bin/python <skill_dir>/scripts/fetch_tickets.py \
  --board-id 123 --filter assignee=currentUser()

# List Agile boards
<skill_dir>/.venv/bin/python <skill_dir>/scripts/fetch_tickets.py \
  --boards
```

Board fetch defaults to **active sprint only** (matching the Scrum board UI view). Use `--board-all` to include backlog, closed, and past sprint issues. Results capped at `--max-results` (default 50) with a truncation warning.

Formats: `table` (default, includes sprint column), `detail`, `json`.

### Delete tickets

```bash
<skill_dir>/.venv/bin/python <skill_dir>/scripts/delete_ticket.py \
  --key PROJ-110 --dry-run   # preview first
<skill_dir>/.venv/bin/python <skill_dir>/scripts/delete_ticket.py \
  --key PROJ-110 --confirm    # execute
```

**Never delete without explicit user approval.**

### Diff local vs Jira

```bash
<skill_dir>/.venv/bin/python <skill_dir>/scripts/diff_tickets.py \
  --manifest          # or --source tickets.md
```

Add `--summary` for counts only, `--json` for raw output. Exit code 1 = changes detected.

### Validate estimates

```bash
<skill_dir>/.venv/bin/python <skill_dir>/scripts/validate_estimates.py \
  --epic PROJ-100     # or --story, --source, --manifest
```

### Discover fields

```bash
<skill_dir>/.venv/bin/python <skill_dir>/scripts/discover_fields.py \
  --all --apply          # full discovery + save
<skill_dir>/.venv/bin/python <skill_dir>/scripts/discover_fields.py \
  --all --verbose --apply # include all fields index
```

`--all` discovers: statuses, priorities, resolutions, components, versions, sprints (Agile API). Add `--verbose` for full system+custom fields index.

Required fields per issue type (`create_meta`) are always discovered and saved with `--apply`. Create scripts validate these before calling the API and exit with actionable `--set` hints if any are missing.

### Markup conversion & link rewriting

Descriptions auto-convert between Markdown ↔ Jira wiki markup. Pass `--no-convert` to skip.
Relative markdown links auto-rewrite to git browse URLs when `--rewrite-links` is used.

## Important rules

1. **Never create/update/delete without plan + explicit user approval.**
2. **Never print credentials.** Only confirm env vars are set.
3. **Create in dependency order**: epics → stories → subtasks.
4. `.jira-manifest.json` is auto-maintained. Do not edit manually.
5. On create failure, stop immediately — do not continue with dependents.
6. After bulk create, offer estimation validation.
7. Link rewriting is best-effort.

## Error handling

| Error | Fix |
|---|---|
| `401 Unauthorized` | Verify env vars and token permissions |
| `404 Not Found` | Check issue key and `project_key` in config |
| `400 Bad Request` | Run `discover_fields.py --verbose` for required fields |
| `Field not configured` | Run `discover_fields.py --apply` |
| `Missing required fields` | Supply via `--set "Field=value"` or `--fields`. Run `discover_fields.py --apply` to refresh |
| `No transition found` | Some statuses need intermediate steps |
| Sprint not setting | Run `discover_fields.py --all --apply` or use `--sprint <numeric_id>` |
| `ModuleNotFoundError` | Run `setup_env.py` |
| `--set` not resolving | Run `discover_fields.py --all --verbose --apply` |
| `Unknown link type` | Check available types with `get_link_types()` — common: Blocks, Duplicate, Cloners, Relates |
