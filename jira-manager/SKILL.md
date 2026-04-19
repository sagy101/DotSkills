---
name: jira-manager
description: >
  Jira ticket management — create, update, fetch, delete, transition, comment, link, and bulk-operate
  on Jira issues. Fetch by key, JQL, filter, board, or sprint. Discover fields, statuses, priorities.
  Use when the user mentions Jira tickets, sprints, epics, stories, backlogs, or board operations.
license: MIT
metadata:
  author: sagy101
  version: "2.1"
compatibility: >
  Python 3.10+. Jira Cloud REST API v2 + Agile REST API v1.0.
  Requires an API token with issue read/write permissions.
---

# Jira Manager

**Shorthand used below:** `$PY` = `<skill_dir>/.venv/bin/python`, `$S` = `<skill_dir>/scripts`

## Pre-flight (run once per session)

Run the preflight script before any other operation:

```bash
python3 <skill_dir>/scripts/jira_preflight.py
```

It validates the entire environment in a single pass:
1. **Python 3.10+** is available
2. **Virtual environment** exists and dependencies are installed (`markdown`, `markdownify`)
3. **Config file** (`.jira.json`) is found and has required fields (`jira_url`, `project_key`)
4. **Credentials** — env vars are set (never prints values)
5. **Connectivity** — API is reachable, credentials are valid
6. **Field discovery** — warns if `field_mappings` or `issue_types` are empty

If the venv or dependencies are missing, the preflight tells you to run:

```bash
python3 <skill_dir>/scripts/jira_setup_env.py
```

To skip the connectivity check (e.g. on repeated calls):

```bash
python3 <skill_dir>/scripts/jira_preflight.py --skip-connectivity
```

## Fetch tickets

```bash
# Single ticket
$PY $S/fetch_tickets.py --key PROJ-101 --format detail

# Multiple tickets by key
$PY $S/fetch_tickets.py --keys PROJ-101,PROJ-102,PROJ-103 --format table

# JQL search
$PY $S/fetch_tickets.py --jql "project=PROJ AND type=Story" --format table

# Filter (builds JQL automatically — quote values with parens in shell)
$PY $S/fetch_tickets.py --filter 'assignee=currentUser()' 'status=In Progress'

# Children of epic or story
$PY $S/fetch_tickets.py --children-of PROJ-100

# Board (active sprint only by default; add --board-all for everything)
$PY $S/fetch_tickets.py --board-id 123
$PY $S/fetch_tickets.py --board-id 123 --filter 'assignee=currentUser()'

# List boards
$PY $S/fetch_tickets.py --boards
```

Formats: `table` (default — shows key, type, SP, priority, status, sprint, summary), `detail`, `json`.
Options: `--max-results N` (default 50), `--no-convert` (skip markup conversion).

**Filter values that are JQL functions** (e.g. `currentUser()`, `now()`, `startOfDay()`) are passed through unquoted. Plain values are auto-quoted.

**Shell quoting**: Always single-quote filter values containing parentheses (e.g. `'assignee=currentUser()'`) to prevent shell expansion.

## Create tickets

```bash
# Story under an epic
$PY $S/create_ticket.py --type story --summary "Title" --description "Desc" \
  --epic PROJ-100 --story-points 2 --priority High

# Subtask under a story
$PY $S/create_ticket.py --type sub-task --summary "Subtask title" --parent PROJ-101

# With assignee (use display name — automatically resolved to accountId on Jira Cloud)
$PY $S/create_ticket.py --type story --summary "Title" --assignee "Jane Smith" --parent PROJ-100

# With extra required fields (use --fields for raw JSON when named flags aren't enough)
$PY $S/create_ticket.py --type bug --summary "Bug title" \
  --fields '{"customfield_29823": {"value": "Dev"}, "customfield_29843": [{"value": "Production"}]}'
```

Create flags: `--type`, `--summary`, `--description`, `--epic`, `--parent`, `--priority`, `--assignee`, `--component` (repeatable), `--fix-version` (repeatable), `--sprint`, `--labels`, `--story-points`, `--attachment` (repeatable), `--fields` (raw JSON for custom fields), `--copy-fields-from ISSUE-KEY` (copy custom fields like QBR/team from an existing issue).

**`--copy-fields-from`**: Fetches all custom fields from the source issue and applies them to the new issue. Only copies `customfield_*` fields that aren't already set by other flags. Automatically skips non-copyable fields (e.g. GreenHopper rank fields) by checking field schema metadata. Useful when your Jira project has required custom fields (e.g. QBR, QBR Theme) that vary per team/project — just point at a sibling issue instead of hunting for field IDs.

**Create order**: epics → stories → subtasks. On failure, stop — do not continue with dependents.

If create fails with a 400 error, the script auto-diagnoses the missing field. **Always follow the auto-diagnosis output:**
- Fields marked **★ Recommended** are on the create screen with allowed values — use the `Fix:` line verbatim.
- Fields marked **"not on create screen"** cannot be set during creation — skip them.
- If multiple matches appear, the recommended one is almost always correct. Do NOT try non-settable fields first.
- You can also run `$PY $S/discover_fields.py --fields-for-type <type>` manually to explore available fields.

### Bulk create

```bash
$PY $S/bulk_create.py --source tickets.md --epic PROJ-100 --dry-run
```
Remove `--dry-run` after review. See [SOURCE_FORMAT.md](references/SOURCE_FORMAT.md) for format.

## Update tickets

```bash
# Common fields
$PY $S/update_ticket.py --key PROJ-101 --summary "New Title" --story-points 3 --priority High

# Status transition
$PY $S/update_ticket.py --key PROJ-101 --status "In Progress"

# Assign by display name (auto-resolved to accountId on Jira Cloud)
$PY $S/update_ticket.py --key PROJ-101 --assignee "Jane Smith"

# Unassign (empty string = unassign)
$PY $S/update_ticket.py --key PROJ-101 --assignee ""

# Re-parent an issue (set parent to another issue)
$PY $S/update_ticket.py --key PROJ-101 --parent PROJ-200

# Any field by name (updates only — resolves via field_catalog)
$PY $S/update_ticket.py --key PROJ-101 --set "components=Backend"

# Comment, link, attachment (all combinable in one call)
$PY $S/update_ticket.py --key PROJ-101 --comment "Done." \
  --link "Blocks:PROJ-200" --attachment report.pdf
```

Update flags: `--summary`, `--description`, `--status`, `--priority`, `--assignee`, `--parent`, `--component`, `--fix-version`, `--sprint`, `--labels`, `--story-points`, `--set "field=value"` (repeatable), `--fields` (raw JSON), `--comment`, `--link "Type:KEY"` (repeatable), `--attachment` (repeatable), `--dry-run`.

**`--parent`**: Sets the parent issue (e.g. `--parent PROJ-200`). Auto-wraps as `{"key": "..."}` for the API. If the update fails with a hierarchy error, the script auto-diagnoses the issue: shows both issue types' hierarchy levels and suggests what intermediate type to create. Also works via `--set "parent=PROJ-200"`.

### Bulk update

```bash
$PY $S/bulk_update.py --tickets "PROJ-1,PROJ-2" --status Done --confirm
$PY $S/bulk_update.py --board-id 123 --sprint "Sprint 5" --confirm
$PY $S/bulk_update.py --jql "project=PROJ AND priority=High" --priority Medium --confirm
```
Defaults to dry-run preview without `--confirm`.

## Delete tickets

```bash
$PY $S/delete_ticket.py --key PROJ-110 --dry-run    # preview
$PY $S/delete_ticket.py --key PROJ-110 --confirm     # execute
```
**Never delete without explicit user approval.**

## Discover fields

```bash
$PY $S/discover_fields.py --all --apply                # full discovery + save to config
$PY $S/discover_fields.py --search "QBR"               # find a field by name
$PY $S/discover_fields.py --fields-for-type epic        # list all fields + values for a type
```

## Diff & validate

```bash
$PY $S/diff_tickets.py --manifest              # diff local vs Jira
$PY $S/validate_estimates.py --epic PROJ-100   # check sub-ticket estimate sums
```

## Rules

1. **ALWAYS use the provided scripts.** NEVER write inline Python or call the Jira REST API directly.
2. **If a script fails**, debug the invocation (wrong flags, missing config, missing `--apply`). Do NOT abandon scripts and write custom code.
3. **Never create/update/delete without showing the plan and getting user approval.**
4. **Never print credentials.**
5. **`--set` works on both create and update** — resolves field names via `field_catalog`. For fields that `--set` can't resolve, use `--fields '{"customfield_123": "val"}'` (raw JSON).
6. Descriptions auto-convert Markdown ↔ Jira markup. Use `--no-convert` to skip. `--rewrite-links` rewrites relative markdown links to git browse URLs.
7. **Images in descriptions** are auto-attached. Local image references (`![alt](path/to/image.png)`) are detected, the paths are rewritten to basenames for Jira wiki markup (`!image.png!`), and the files are uploaded as attachments after issue creation/update. HTTP/HTTPS URLs are left as-is. For `--description-file`, paths resolve relative to the file's directory; for `--description`, relative to CWD. Works in `create_ticket`, `update_ticket`, and `bulk_create`.
8. **Mermaid diagrams** in descriptions (` ```mermaid ` code blocks) are automatically rendered to PNG and attached. Requires `mmdc` (`npm i -g @mermaid-js/mermaid-cli`) or `npx`. If neither is available the blocks are left as code with a warning.

## Error quick-ref

| Error | Fix |
|---|---|
| `401` | Check env vars and token permissions |
| `404` | Check issue key and `project_key` |
| `Missing required fields` | Script auto-suggests the fix. Or use `--copy-fields-from SIBLING-KEY` to inherit fields. Or run `discover_fields.py --fields-for-type <type>` manually |
| `No transition found` | Some statuses need intermediate steps |
| `ModuleNotFoundError` | Run `jira_setup_env.py` |
| Sprint not setting | Run `discover_fields.py --all --apply` |
