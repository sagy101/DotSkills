# dotskills

A personal collection of reusable [Agent Skills](https://agentskills.io) for AI coding assistants.

Each skill is a self-contained directory following the [Agent Skills Open Standard](https://agentskills.io/specification) — a `SKILL.md` definition file plus optional scripts, references, and assets.

## Available skills

| Skill | Description |
|---|---|
| [confluence-publisher](./confluence-publisher/) | Publish markdown docs to Confluence Cloud — pages, hierarchy, cross-links, Mermaid diagrams, diff/preview, export, fetch |

## Usage

Copy any skill directory into your project's `.agents/skills/` (or `.github/skills/`, `.claude/skills/`) folder:

```bash
cp -r confluence-publisher /path/to/your-project/.agents/skills/
```

Or symlink for automatic updates:

```bash
ln -s /path/to/dotskills/confluence-publisher /path/to/your-project/.agents/skills/confluence-publisher
```

Skills are automatically discovered by supported AI tools when placed in the correct directory.

## Compatibility

Skills in this repo work with:
- **Windsurf** (`.agents/skills/`)
- **Claude Code** (`.agents/skills/` or `.claude/skills/`)
- **VS Code / GitHub Copilot** (`.github/skills/`)
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

1. Create a directory named after your skill (lowercase, hyphens only)
2. Add a `SKILL.md` with YAML frontmatter (`name`, `description`) and body instructions
3. Add scripts/references/assets as needed
4. Update the table in this README

## License

[MIT License](./LICENSE) — free to use, modify, and redistribute. Attribution required (keep the copyright notice).
