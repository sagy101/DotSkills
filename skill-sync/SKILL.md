---
name: skill-sync
description: >
  Sync Agent Skills from a central source repository to IDE skill directories
  (Windsurf, Claude Code, Cursor, Codex, Gemini CLI, Antigravity). Use when the
  user wants to install, sync, or distribute skills across their coding tools.
license: MIT
metadata:
  author: sagy101
  version: "1.0"
compatibility: >
  Requires Python 3.10+. Works on macOS, Linux, and Windows.
---

# Skill Sync

Sync Agent Skills from a central source repo to IDE skill directories.

## When to use this skill

Use this skill when the user wants to:
- Sync skills to their IDEs (Windsurf, Claude Code, Cursor, Codex)
- Install skills globally (user-level) or into a specific project
- Check which IDEs are detected on their machine

## Workflow

### Step 1 — Detect IDEs

Run detection first to show the user what's available:

```bash
python <skill_dir>/scripts/sync.py --source <source_repo> --level both --detect
```

Present the results to the user, showing:
- Which IDEs were detected and their paths
- The OS and home directory

### Step 2 — Ask the user

Ask the user with these questions, showing the detected defaults:

1. **Sync level**: User-level (global), project-level, or both?
   - Default: **user** (skills available in all projects)
   - Show the detected user-level paths for each IDE

2. **If project-level or both**: Which project directory?
   - Default: **current working directory** (`<cwd>`)
   - Show the path so the user can confirm or change it

3. **Which IDEs** to sync to?
   - Default: **all detected** — list them by name with their keys
   - The user can pick a subset (e.g. "just windsurf and claude")

### Step 3 — Dry run (recommended)

Run a dry run first to show what will happen:

```bash
python <skill_dir>/scripts/sync.py \
  --source <source_repo> \
  --level <user|project|both> \
  [--project <path>] \
  --targets <comma_separated_or_all> \
  --dry-run
```

### Step 4 — Execute

After user confirms the dry-run output:

```bash
python <skill_dir>/scripts/sync.py \
  --source <source_repo> \
  --level <user|project|both> \
  [--project <path>] \
  --targets <comma_separated_or_all>
```

### Step 5 — Report

Show the summary: how many skills synced, to which IDEs, file counts.

## Supported IDEs

| IDE | Key | User-level path | Project-level path |
|---|---|---|---|
| Windsurf | `windsurf` | `~/.codeium/windsurf/skills/` | `<project>/.windsurf/skills/` |
| Claude Code | `claude` | `~/.claude/skills/` | `<project>/.claude/skills/` |
| Cursor | `cursor` | `~/.cursor/skills/` | `<project>/.cursor/skills/` |
| Codex | `codex` | `~/.codex/skills/` | `<project>/.codex/skills/` |
| Gemini CLI | `gemini` | `~/.gemini/skills/` | `<project>/.gemini/skills/` |
| Antigravity | `antigravity` | `~/.gemini/antigravity/skills/` | `<project>/.agent/skills/` |

## CLI reference

```
python <skill_dir>/scripts/sync.py \
  --source <path>           # Source repo containing skill folders
  --level <user|project|both>  # Where to sync (default: user)
  --project <path>          # Project dir (default: cwd, only for project/both)
  --targets <list|all>      # IDE targets: windsurf,claude,cursor,codex,gemini,antigravity or all
  --dry-run                 # Preview without copying
  --detect                  # Just print detected IDEs and exit
```

## Important rules

1. **Always run --detect first** to show the user their detected IDEs and paths.
2. **Always confirm with the user** before syncing (show dry-run or plan).
3. Hidden directories, `__pycache__`, `.git`, and `.pyc` files are excluded.
5. Existing skill directories at the target are replaced (full overwrite per skill).
