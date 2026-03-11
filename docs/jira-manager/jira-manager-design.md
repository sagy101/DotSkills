# Jira Manager Skill — Design Document

> This document covers **why** this skill exists and the **key decisions** an implementer or reviewer needs to understand.

---

## Why This Skill Exists

Managing Jira tickets from an AI coding agent is common but fragile: agents hallucinate field names, guess at valid statuses, miss required fields, and produce broken markup. Most integrations are hardcoded to one project's workflow.

This skill gives **any SKILL.md-compatible agent** reliable Jira CRUD by combining **field discovery** (learn the project's actual schema) with **generic flags** (`--set`, `--filter`) that work across any Jira Cloud instance. The agent doesn't need to know the project's custom fields upfront — it discovers them.

---

## Capabilities

| Capability | Description |
|---|---|
| **Create tickets** | Single or bulk creation from markdown/JSON source files with dependency ordering |
| **Update tickets** | Modify fields, status, sprint, priority, assignee, attachments, comments, and issue links on existing issues |
| **Bulk update** | Update multiple tickets by explicit list, board, JQL, or field filter |
| **Fetch tickets** | Query by key, JQL, field filter, parent, or Agile board (table/detail/JSON output) |
| **Delete tickets** | Remove issues with dry-run preview and confirmation gate |
| **Diff** | Compare local ticket definitions against live Jira state |
| **Validate estimates** | Check that sub-ticket story point sums match parent estimates |
| **Field discovery** | Auto-discover statuses, priorities, components, versions, sprints, and custom fields |
| **Status transitions** | Move issues through workflow states via Jira's transition engine |
| **Markup conversion** | Automatic Markdown ↔ Jira wiki markup conversion for descriptions |
| **Link rewriting** | Convert relative markdown links to git browse URLs in ticket descriptions |
| **Comments** | Add comments to issues via `--comment` flag during update |
| **Issue links** | Create typed links between issues (Blocks, Duplicate, Relates, etc.) via `--link` flag |
| **Board/sprint ops** | List Agile boards, fetch board issues, move issues between sprints |

---

## Key Design Decisions

**1. Discovery-first architecture** — Before creating or updating tickets, the agent runs `discover_fields.py --all --apply` to learn the project's statuses, priorities, components, versions, sprints, and custom fields. This populates `field_catalog` in `.jira.json`, which all other scripts reference. No hardcoded field IDs or status names.

**2. Generic `--set` and `--filter` flags** — Named flags cover common fields (`--status`, `--priority`, `--sprint`), but any field can be set or filtered via `--set "field=value"` and `--filter field=value`. This means the skill works with custom fields (story points, team, environment, etc.) without needing per-field flag definitions.

**3. Manifest-driven idempotency** — `.jira-manifest.json` maps local definitions (markdown sections or JSON entries) to Jira issue keys. Bulk create skips already-created tickets. Diff compares local definitions against live Jira state. This prevents duplicate creation on retry and enables incremental sync.

**4. Dependency-ordered creation** — Epics before stories, stories before subtasks. This mirrors Jira's hierarchy constraints: a subtask can't be created without a parent key, and a story's epic link needs the epic to exist. On failure, the skill stops immediately rather than creating orphaned issues.

**5. Status transitions via the Jira workflow engine** — Updating status isn't a simple field write — Jira requires finding the correct transition ID. The skill queries available transitions for the issue and matches by target status name. If no direct transition exists (e.g., can't go from "To Do" to "Done" without passing through "In Progress"), the error message says so rather than silently failing.

**6. Markdown ↔ Jira markup conversion** — Jira Cloud's REST API accepts Jira wiki markup, not markdown. The skill auto-converts descriptions during create/update (markdown → Jira markup) and during fetch/diff (Jira markup → markdown). `--no-convert` skips this for users who write Jira markup directly.

**7. Link rewriting for traceability** — `--rewrite-links` converts relative markdown links in descriptions to full git browse URLs (e.g., `./src/auth.ts` → `https://github.com/org/repo/blob/main/src/auth.ts`). This gives Jira readers clickable links to source code without requiring Jira-GitHub integrations.

**8. Credentials via environment variables** — `.jira.json` stores env var *names*, not values. Pre-flight confirms they're set without printing them. Optional `.env` file support via the `env_file` config key (path-traversal protected — must resolve inside the project root). Environment variable names are validated against `[A-Za-z_][A-Za-z0-9_]*` to prevent shell injection in credential hints. Shell-specific hints are generated for zsh, bash, fish, PowerShell, and cmd.

**9. Dynamically discovered issue link types** — Link types (Blocks, Duplicate, Cloners, Relates, etc.) are fetched at runtime from `GET /rest/api/2/issueLinkType`, not hardcoded. The `--link` flag accepts the link type name, its inward label (e.g., "is blocked by"), or its outward label (e.g., "blocks") and resolves against the live list. Direction is automatically swapped when an inward label is used: `--link "is blocked by:API-456"` creates the link with API-456 as the blocker.

**10. Virtual environment isolation** — `setup_env.py` creates `.venv/` inside the skill directory (e.g., `jira-manager/.venv/`). The agent invokes scripts using the absolute path to the venv Python interpreter (e.g., `/path/to/jira-manager/.venv/bin/python`) — no shell activation required. This keeps the skill self-contained and works identically whether installed in the repo or synced to `~/.codeium/windsurf/skills/`.

**11. Required field pre-validation via create_meta** — `discover_fields.py --apply` now always fetches Jira's `createmeta` (required fields per issue type) and persists it in `.jira.json`. Before any create API call, `create_ticket.py` and `bulk_create.py` validate that all required fields are present and exit with actionable `--set` hints if any are missing. This catches errors like "QBR is mandatory for Epics" before hitting the API.

**12. CLI flag normalization for LLM agents** — All scripts pass `sys.argv` through `normalize_args()` before argparse processing. This converts single-dash long flags (`-format`) to double-dash (`--format`) — a frequent LLM mistake. Short flags like `-v` are left untouched. The heuristic: any arg starting with `-` (not `--`) with 3+ characters and not a number gets a second dash prepended.

**13. Config discovery with git root boundary** — `.jira.json` is discovered by walking up from CWD, stopping at the nearest git root to avoid picking up configs from unrelated parent directories. Global config (`~/.jira.json`) is merged underneath project-level config (project wins on conflict). An explicit `--config` flag overrides discovery entirely.

**14. Module structure** — `config_loader.py` handles configuration loading, credential resolution, shell detection, and manifest I/O. All scripts share the same `--config` argument definition via `add_config_arg()` for consistency.

---

## Approval Gates

| Action | Approval Required | Mechanism |
|---|---|---|
| **Create (single or bulk)** | Yes | Plan shown with issue types, summaries, parents |
| **Update (single or bulk)** | Yes | Fields-to-change shown per ticket |
| **Delete** | Yes | `--dry-run` first, then `--confirm` to execute |
| **Status transition** | Yes (via update approval) | Target status shown in update plan |
| **Bulk update (board/JQL)** | Yes | Matched tickets and changes shown first; `--confirm` required |
| **Fetch / diff / validate** | No | Read-only, no side effects |
| **Discover fields** | No | Read-only (writes only to local `.jira.json` with `--apply`) |

---

## Bulk Update Scoping

Bulk updates can target tickets by four methods, each with different risk profiles:

| Method | Flag | Risk | Notes |
|---|---|---|---|
| **Explicit list** | `--tickets "PROJ-1,PROJ-2"` | Low | Exact tickets, no surprises |
| **Board (active sprint)** | `--board-id 123` | Medium | Scoped to active sprint by default |
| **Board (all)** | `--board-id 123 --board-all` | High | Includes backlog, closed, past sprints |
| **Filter** | `--filter status="In Progress"` | Medium | Builds JQL from field=value pairs |
| **Raw JQL** | `--jql "..."` | High | Arbitrary query, could match many issues |

All bulk updates default to **dry-run preview** and require `--confirm` to execute. The preview shows every matched ticket and the changes that would be applied.

---

## Field Discovery Flow

```
1. Agent runs: discover_fields.py --all --apply
2. Script queries Jira REST API for:
   - Issue types (story, bug, subtask, epic, etc.)
   - Statuses and their transition mappings
   - Priorities
   - Resolutions
   - Components
   - Fix versions
   - Sprints (via Agile API)
   - Custom fields (with --verbose)
   - Required fields per issue type (create_meta)
3. Results saved to field_catalog and create_meta in .jira.json
4. All subsequent scripts reference field_catalog for:
   - Validating --status values against available transitions
   - Resolving --priority to Jira's priority IDs
   - Mapping --sprint names to sprint IDs (Agile API)
   - Resolving --set field names to Jira field IDs
5. Create scripts reference create_meta to pre-validate required fields
```

If `field_catalog` is empty or stale, scripts may fail with "field not configured" — the fix is always to re-run discovery with `--apply`.

---

## Risks at a Glance

| Risk | Severity | Mitigation |
|---|---|---|
| Credential leakage | High | Env var indirection; never print values |
| Bulk update hitting wrong tickets | High | Dry-run default; `--confirm` gate; preview shows matched tickets |
| Creating duplicates on retry | Medium | Manifest-based skip; idempotent bulk create |
| Orphaned subtasks | Medium | Dependency-ordered creation; stop on parent failure |
| Invalid status transitions | Medium | Transition query + clear error messages |
| Stale field catalog | Medium | Pre-flight check triggers re-discovery |
| Agent abandoning scripts for inline code | High | SKILL.md rules #1-2 mandate script usage; troubleshooting table documents common mistakes |
| Agent using wrong flag syntax (`-flag` vs `--flag`) | Medium | `normalize_args()` auto-corrects single-dash long flags |
| Markup conversion artifacts | Low | `--no-convert` escape hatch; round-trip tested |
| Raw JQL matching too broadly | High | Dry-run preview; `--confirm` required; max-results cap with warning |

---

## References

- **Jira Cloud REST API v2** — Issue CRUD, transitions, field metadata, search (JQL)
- **Jira Agile REST API v1.0** — Boards, sprints, sprint issue management
- **Jira wiki markup** — Confluence-style markup used in issue descriptions

## Status

**Stable (v1.7)** — Full CRUD, bulk operations, Agile board/sprint support, field discovery, diff/validate, markup conversion, comments, and issue links implemented.
