# dotskills

A personal collection of reusable [Agent Skills](https://agentskills.io) for AI coding assistants.

Each skill is a self-contained directory following the [Agent Skills Open Standard](https://agentskills.io/specification) — a `SKILL.md` definition file plus optional scripts, references, and assets.

## Available skills

| Skill | Description |
|---|---|
| [confluence-publisher](./confluence-publisher/) | Publish markdown docs to Confluence Cloud — pages, hierarchy, cross-links, Mermaid diagrams, diff/preview, export, fetch |
| [jira-manager](./jira-manager/) | Create, update, fetch, delete, diff, and validate Jira tickets — bulk create from markdown/JSON, full field catalog discovery (statuses, priorities, components, versions), status transitions, generic `--set` flag for any discovered field, estimation validation, link rewriting |
| [codebase-analyzer](./codebase-analyzer/) | Analyze any codebase for structured metrics — line counts by category, language breakdown, test:code ratio, file-size distribution, TODO tracking, git churn hotspots. Terminal, JSON, and Markdown output |
| [skill-creator](./skill-creator/) | Create polished, generic Agent Skills from use-case-specific scripts or from scratch — prompt engineering best practices, Agent Skills spec compliance, comprehensive verification (compilation, diff review, env/config checks, error handling) |
| [skill-sync](./skill-sync/) | Sync skills from this repo to IDE skill directories (Windsurf, Claude Code, Cursor, Codex, Gemini CLI, Antigravity) — OS-agnostic, user-level or project-level, auto-detects installed IDEs |

## Usage

The easiest way to distribute skills is with **skill-sync**:

```bash
# Detect which IDEs are installed
python3 skill-sync/scripts/sync.py --source . --level both --detect

# Sync all skills to user-level (global) for all detected IDEs
python3 skill-sync/scripts/sync.py --source . --level user --targets all

# Sync to a specific project
python3 skill-sync/scripts/sync.py --source . --level project --project /path/to/project

# Preview first with --dry-run
python3 skill-sync/scripts/sync.py --source . --level user --dry-run
```

Or copy manually:

```bash
cp -r confluence-publisher /path/to/your-project/.agents/skills/
```

Skills are automatically discovered by supported AI tools when placed in the correct directory.

## Compatibility

Skills in this repo follow the [Agent Skills Open Standard](https://agentskills.io/specification) and work with:
- **Windsurf** (`.agents/skills/`)
- **Claude Code** (`.agents/skills/` or `.claude/skills/`)
- **OpenAI Codex** (`.agents/skills/`)
- **VS Code / GitHub Copilot** (`.github/skills/`)
- **Gemini CLI** (`.agents/skills/`)
- **Cursor** (`.agents/skills/`)
- **OpenCode** (`.agents/skills/`)

## Structure

Each skill follows this layout:

```
skill-name/
  SKILL.md              # Required — skill definition (YAML frontmatter + instructions)
  scripts/              # Optional — executable scripts
  references/           # Optional — detailed docs, schemas, templates
  assets/               # Optional — images, data files, templates
```

## Adding a new skill

Use the skill-creator's init script to scaffold a new skill:

```bash
python3 skill-creator/scripts/init_skill.py my-new-skill --path .
```

Or manually:

1. Create a directory named after your skill (lowercase, hyphens only)
2. Add a `SKILL.md` with YAML frontmatter (`name`, `description`) and body instructions
3. Add scripts/references/assets as needed
4. Validate with `python3 skill-creator/scripts/quick_validate.py ./my-new-skill/`
5. Update the table in this README

## License

[MIT License](./LICENSE) — free to use, modify, and redistribute. Attribution required (keep the copyright notice).
