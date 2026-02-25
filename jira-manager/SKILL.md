---
name: jira-manager
description: >
  Create, update, fetch, delete, diff, and validate Jira tickets from structured markdown or JSON sources.
  Use when the user asks to create Jira tickets, update existing issues, bulk-create stories and subtasks
  from a spec, compare local definitions against live Jira state, validate that sub-ticket estimates
  sum to parent estimates, change ticket status, set priority/assignee/components, or rewrite markdown
  links to git browse URLs in ticket descriptions. Supports full field discovery with --all flag to
  discover statuses, priorities, components, versions, resolutions, and all custom fields. Any
  discovered field can be set by friendly name using the --set flag.
  Handles epics, stories, subtasks, bugs, tasks, custom fields, story points, status transitions,
  and link rewriting.
license: MIT
metadata:
  author: sagy101
  version: "1.1"
compatibility: >
  Requires Python 3.10+. Works with Jira Cloud (Atlassian REST API v2).
  Requires an API token with issue read/write permissions.
---

# Jira Manager

Create, update, fetch, delete, diff, and validate Jira tickets with automatic field discovery, status transitions, link rewriting, and estimation validation.

## When to use this skill

Use this skill when the user wants to:
- Create one or more Jira tickets (stories, subtasks, bugs, tasks)
- Bulk-create tickets from a markdown or JSON spec file
- Update fields on existing Jira issues
- Fetch and display Jira issues (by key, JQL, or parent relationship)
- Delete Jira issues (with confirmation)
- Diff local ticket definitions against live Jira state
- Validate that sub-ticket estimates sum to their parent's estimate
- Discover custom field IDs and issue types for a Jira project
- Change ticket status (workflow transitions)
- Set any discovered field by friendly name (priority, components, fix versions, etc.)

## Prerequisites

Before running any operation, ensure:

1. A **project config file** exists at `.jira.json` in the project root (see [CONFIG.md](references/CONFIG.md) for format)
2. **Credentials** are available as environment variables (names configured in `.jira.json`)
3. Python dependencies are installed via the setup script

If `.jira.json` does not exist, help the user create one by asking for:
- Jira base URL (e.g. `https://mycompany.atlassian.net`)
- Project key (e.g. `API`)
- Environment variable names for credentials (default: `JIRA_EMAIL`, `JIRA_TOKEN`)
- Path to `.env` file if they use one

## Configuration

The project must contain a `.jira.json` file. See [references/CONFIG.md](references/CONFIG.md) for the full schema. Minimal example:

```json
{
  "jira_url": "https://mycompany.atlassian.net",
  "project_key": "API",
  "credentials": {
    "username_env": "JIRA_EMAIL",
    "token_env": "JIRA_TOKEN"
  },
  "env_file": ".env"
}
```

## Pre-flight checks

Before running ANY script, perform these checks proactively.

### Check 1 — Python environment

Verify Python 3.10+ is available:

```bash
python3 --version
```

Check if the virtual environment exists and has dependencies:

```bash
.jira-venv/bin/python -c "import markdown; import markdownify; print('OK')"
```

If missing, run the setup script:

```bash
python3 <skill_dir>/scripts/setup_env.py
```

After setup, all script commands use the venv Python:

```bash
.jira-venv/bin/python <skill_dir>/scripts/create_ticket.py ...
```

### Check 2 — Configuration file

Look for `.jira.json` in the project root. If missing, do NOT proceed — help the user create one interactively.

### Check 3 — Credentials

Confirm credential environment variables are set:

```bash
python3 -c "import os; print('email:', 'SET' if os.environ.get('JIRA_EMAIL') else 'MISSING'); print('token:', 'SET' if os.environ.get('JIRA_TOKEN') else 'MISSING')"
```

Substitute actual env var names from `.jira.json`. If credentials load from a `.env` file, check that the file exists and contains the expected keys (without printing values).

### Check 4 — Field discovery (first run)

If `field_mappings` or `issue_types` are empty in `.jira.json`, run discovery:

```bash
.jira-venv/bin/python <skill_dir>/scripts/discover_fields.py --config .jira.json --apply
```

This auto-detects custom field IDs (epic link, story points, sprint) and available issue types.

For full field discovery (statuses, priorities, components, versions, resolutions):

```bash
.jira-venv/bin/python <skill_dir>/scripts/discover_fields.py --config .jira.json --all --apply
```

This populates the `field_catalog` in `.jira.json`, enabling the `--set` flag and named field flags
(`--status`, `--priority`, etc.) to resolve values by friendly name.

## Workflow

Always follow this sequence. Never skip pre-flight checks or the plan step.

### Step 1 — Validate configuration

Run pre-flight checks above. Confirm all required fields are present and credentials are set.

### Step 2 — Determine operation

Identify what the user wants from one of these operations:
- **Create**: single ticket or bulk from source file
- **Update**: modify fields on existing tickets
- **Fetch**: retrieve and display tickets
- **Delete**: remove tickets (requires confirmation)
- **Diff**: compare local spec against live Jira
- **Validate estimates**: check sub-ticket sums match parents

### Step 3 — Build the action plan

For create, update, and delete operations, present a plan to the user (see [references/TICKET_PLAN_FORMAT.md](references/TICKET_PLAN_FORMAT.md)).

**Wait for explicit user approval before proceeding.** If the user asks to change anything, update the plan and present again.

### Step 4 — Execute

Run the appropriate script. See operation-specific instructions below.

### Step 5 — Verify

After create or update operations, offer to:
- Run estimation validation: `validate_estimates.py`
- Run diff to confirm changes: `diff_tickets.py`
- Fetch created tickets to display: `fetch_tickets.py`

## Operations

### Create a single ticket

```bash
.jira-venv/bin/python <skill_dir>/scripts/create_ticket.py \
  --config .jira.json \
  --type story \
  --summary "My Story Title" \
  --description "Description text" \
  --epic API-8291 \
  --story-points 2 \
  --priority "High" \
  --status "In Progress" \
  --rewrite-links \
  --attachment screenshot.png \
  --attachment design.pdf
```

For subtasks, use `--type subtask --parent API-8301` instead of `--epic`.
The `--attachment` flag can be repeated to attach multiple files.

Additional field flags:
- `--priority "High"` — set priority (resolved from field_catalog)
- `--status "In Progress"` — transition to status after creation
- `--assignee "user@example.com"` — set assignee
- `--component "Backend"` — add component (can be repeated)
- `--fix-version "1.0"` — add fix version (can be repeated)
- `--set "field=value"` — set any discovered field by name (can be repeated)

### Bulk create from source file

Parse a structured markdown or JSON file (see [references/SOURCE_FORMAT.md](references/SOURCE_FORMAT.md)) and create all tickets in dependency order:

```bash
.jira-venv/bin/python <skill_dir>/scripts/bulk_create.py \
  --config .jira.json \
  --source tickets.md \
  --epic API-8291 \
  --rewrite-links \
  --dry-run
```

Remove `--dry-run` after reviewing the plan. Already-created tickets (tracked in `.jira-manifest.json`) are skipped automatically.

### Update existing tickets

```bash
.jira-venv/bin/python <skill_dir>/scripts/update_ticket.py \
  --config .jira.json \
  --key API-8301 \
  --summary "Updated Title" \
  --story-points 3 \
  --rewrite-links

# Change status (uses workflow transitions API)
.jira-venv/bin/python <skill_dir>/scripts/update_ticket.py \
  --config .jira.json \
  --key API-8301 \
  --status "In Progress"

# Set priority and assignee
.jira-venv/bin/python <skill_dir>/scripts/update_ticket.py \
  --config .jira.json \
  --key API-8301 \
  --priority "High" \
  --assignee "user@example.com"

# Set any field by friendly name
.jira-venv/bin/python <skill_dir>/scripts/update_ticket.py \
  --config .jira.json \
  --key API-8301 \
  --set "priority=High" \
  --set "components=Backend" \
  --set "story_points=5"

# Attach files to an existing ticket (no field changes required)
.jira-venv/bin/python <skill_dir>/scripts/update_ticket.py \
  --config .jira.json \
  --key API-8301 \
  --attachment report.pdf
```

The `--set` flag resolves field names and values through the `field_catalog` in `.jira.json`.
Run `discover_fields.py --all --apply` first to populate the catalog.

Available named flags: `--status`, `--priority`, `--assignee`, `--component`, `--fix-version`, `--labels`, `--story-points`.

### Fetch tickets

```bash
# Single ticket
.jira-venv/bin/python <skill_dir>/scripts/fetch_tickets.py \
  --config .jira.json --key API-8301 --format detail

# JQL search
.jira-venv/bin/python <skill_dir>/scripts/fetch_tickets.py \
  --config .jira.json --jql "project=API AND type=Story" --format table

# Children of epic or story
.jira-venv/bin/python <skill_dir>/scripts/fetch_tickets.py \
  --config .jira.json --children-of API-8291
```

### Delete tickets

Always show what will be deleted first:

```bash
# Preview
.jira-venv/bin/python <skill_dir>/scripts/delete_ticket.py \
  --config .jira.json --key API-8310 --dry-run

# Execute (requires --confirm)
.jira-venv/bin/python <skill_dir>/scripts/delete_ticket.py \
  --config .jira.json --key API-8310 --confirm
```

**Never delete without explicit user approval.**

### Diff local vs Jira

Compare manifest entries or source file against live Jira state:

```bash
# Diff manifest entries
.jira-venv/bin/python <skill_dir>/scripts/diff_tickets.py \
  --config .jira.json --manifest

# Diff source file
.jira-venv/bin/python <skill_dir>/scripts/diff_tickets.py \
  --config .jira.json --source tickets.md

# Summary only
.jira-venv/bin/python <skill_dir>/scripts/diff_tickets.py \
  --config .jira.json --manifest --summary
```

Exit code 1 means changes detected (informational, not an error).

### Validate estimates

Check that sub-ticket story points sum to parent story points:

```bash
# Validate epic (live Jira)
.jira-venv/bin/python <skill_dir>/scripts/validate_estimates.py \
  --config .jira.json --epic API-8291

# Validate single story (live Jira)
.jira-venv/bin/python <skill_dir>/scripts/validate_estimates.py \
  --config .jira.json --story API-8301

# Validate from source file (pre-creation)
.jira-venv/bin/python <skill_dir>/scripts/validate_estimates.py \
  --config .jira.json --source tickets.md

# Validate from manifest
.jira-venv/bin/python <skill_dir>/scripts/validate_estimates.py \
  --config .jira.json --manifest
```

### Discover fields

Auto-detect custom field IDs and issue types:

```bash
# Show discovered fields
.jira-venv/bin/python <skill_dir>/scripts/discover_fields.py \
  --config .jira.json --verbose

# Apply to config
.jira-venv/bin/python <skill_dir>/scripts/discover_fields.py \
  --config .jira.json --apply

# Full discovery: statuses, priorities, components, versions, resolutions
.jira-venv/bin/python <skill_dir>/scripts/discover_fields.py \
  --config .jira.json --all --apply

# Full discovery with all fields index (system + custom)
.jira-venv/bin/python <skill_dir>/scripts/discover_fields.py \
  --config .jira.json --all --verbose --apply
```

The `--all` flag discovers:
- **Statuses** — all workflow statuses in the project (e.g. Backlog, In Progress, Done)
- **Priorities** — all priority levels (e.g. Highest, High, Medium, Low, Lowest)
- **Resolutions** — all resolution types (e.g. Done, Won't Do, Duplicate)
- **Components** — all project components
- **Versions** — all project versions (fix versions)
- **Fields index** (with `--verbose`) — all system + custom fields with IDs

Discovered values are stored in `field_catalog` in `.jira.json` and used by the `--set` flag
and named field flags (`--status`, `--priority`, etc.) on create and update scripts.

### Markup conversion

Descriptions are automatically converted between Markdown and Jira wiki markup:

- **Creating/updating** tickets: Markdown descriptions are converted to Jira wiki markup before sending to the API
- **Fetching** tickets (detail format): Jira wiki markup descriptions are converted back to Markdown for display

Supported conversions: headings, bold, italic, strikethrough, code blocks, inline code, links, images, tables, lists (ordered/unordered with nesting), blockquotes, horizontal rules, panels, noformat blocks.

To skip conversion, pass `--no-convert` to any create, update, or fetch script.

The converter can also be used standalone:

```bash
# Markdown to Jira wiki markup
.jira-venv/bin/python <skill_dir>/scripts/markup_converter.py \
  --direction md2jira --file description.md

# Jira wiki markup to Markdown
.jira-venv/bin/python <skill_dir>/scripts/markup_converter.py \
  --direction jira2md --file description.jira
```

### Rewrite links

Convert relative markdown links to git browse URLs (or reverse):

```bash
.jira-venv/bin/python <skill_dir>/scripts/link_rewriter.py \
  --config .jira.json --direction to-git --file description.md
```

This is called automatically when `--rewrite-links` is passed to create or update scripts.

## Important rules

1. **Never create, update, or delete without showing the plan first and getting explicit user approval.**
2. **Never print or log credentials.** Only confirm that environment variables are set.
3. **Create in dependency order**: epics before stories, stories before subtasks.
4. The manifest file (`.jira-manifest.json`) is auto-maintained by scripts. Do not edit manually.
5. If a create fails, stop and report the error — do not continue with dependent tickets.
6. After bulk create, offer to run estimation validation automatically.
7. Link rewriting is best-effort: if git remote cannot be resolved, links are left as-is.

## Error handling

| Error | Cause | Fix |
|---|---|---|
| `401 Unauthorized` | Bad credentials | Verify env vars are set and token has issue write access |
| `404 Not Found` | Wrong issue key or project | Check key exists and project_key is correct in config |
| `400 Bad Request` | Missing required field | Run `discover_fields.py --verbose` to see required fields |
| `Field not configured` | Missing field_mappings entry | Run `discover_fields.py --apply` to auto-detect |
| `No transition found` | Status not reachable from current state | Check available transitions — some statuses require intermediate steps |
| `createmeta not available` | Jira instance restriction | Configure `field_mappings` and `issue_types` manually |

## Troubleshooting

| Problem | Fix |
|---|---|
| `python3: command not found` | macOS: `brew install python3` / Linux: `apt install python3` |
| `ModuleNotFoundError: markdown` | Run `python3 <skill_dir>/scripts/setup_env.py` |
| Story points not setting | Run `discover_fields.py --apply` to detect the field ID |
| Epic link not working | Run `discover_fields.py --apply` to detect the field ID |
| Links not rewriting | Check `git_remote` in config or ensure you're in a git repo |
| Manifest out of sync | Delete `.jira-manifest.json` and re-create with `bulk_create.py` |
| Status change not working | Run `discover_fields.py --all --apply` and check available transitions |
| `--set` field not resolving | Run `discover_fields.py --all --verbose --apply` to populate field catalog |
