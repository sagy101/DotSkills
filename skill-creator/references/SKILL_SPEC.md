# Agent Skills Specification Reference

Summary of the Agent Skills open standard from [agentskills.io/specification](https://agentskills.io/specification).

## Directory structure

```
skill-name/
└── SKILL.md          # Required
```

Optional additional directories:

```
skill-name/
├── SKILL.md          # Required
├── scripts/          # Executable code the agent can run
├── references/       # Detailed technical docs loaded on demand
└── assets/           # Templates, images, data files, schemas
```

## SKILL.md format

### Frontmatter (required)

```yaml
---
name: skill-name
description: >
  A description of what this skill does and when to use it.
  Include action verbs and domain keywords for agent matching.
license: MIT
metadata:
  author: org-or-user
  version: "1.0"
compatibility: >
  Runtime requirements (Python 3.10+, Node.js, etc.)
---
```

#### Field rules

| Field | Required | Constraints |
|---|---|---|
| `name` | Yes | 1-64 chars, lowercase alphanumeric + hyphens, must match parent directory name, no leading/trailing/consecutive hyphens |
| `description` | Yes | 1-1024 chars, describe what the skill does AND when to use it, include trigger keywords |
| `license` | No | Short license name or reference to LICENSE file |
| `compatibility` | No | 1-500 chars, only if specific environment requirements exist |
| `metadata` | No | Map of string keys to string values for additional properties |
| `allowed-tools` | No | Space-delimited list of pre-approved tools (experimental) |

#### Name validation examples

- `pdf-processing` — valid
- `data-analysis` — valid
- `code-review` — valid
- `PDF-Processing` — invalid (uppercase)
- `-pdf` — invalid (leading hyphen)
- `pdf--processing` — invalid (consecutive hyphens)

### Body content

The body follows the frontmatter and contains markdown instructions. Recommended sections:

1. Step-by-step instructions
2. Examples of inputs and outputs
3. Common edge cases

## Progressive disclosure

Agents load skills in three stages:

1. **Metadata** (~100 tokens): `name` and `description` fields loaded at startup for all skills
2. **Instructions** (< 5000 tokens recommended): Full SKILL.md body loaded when skill is activated
3. **Resources** (as needed): Files in `scripts/`, `references/`, `assets/` loaded only when required

This means the `description` field is critical — it determines whether the agent activates the skill at all.

## File references

Reference supporting files from SKILL.md using relative paths:

```markdown
See [the config reference](references/CONFIG.md) for the full schema.
Run the setup script: `python3 <skill_dir>/scripts/setup_env.py`
```

## Optional directories

### scripts/

- Be self-contained or clearly document dependencies
- Include helpful error messages
- Handle edge cases gracefully

### references/

- `CONFIG.md` — Detailed config schema reference
- `FORMAT.md` — Input/output format specifications
- Domain-specific files (field mappings, plan formats, etc.)

### assets/

- Templates (document templates, configuration templates)
- Images (diagrams, examples)
- Data files (lookup tables, schemas, default configs)

## Skill scopes (Windsurf-specific)

| Scope | Location | Availability |
|---|---|---|
| Workspace | `.windsurf/skills/<name>/` | Current project only |
| Global | `~/.codeium/windsurf/skills/<name>/` | All projects |
| Agent Skills standard | `.agents/skills/<name>/` | Cross-agent portable |

## Validation

Use the `skills-ref` CLI to validate a skill:

```bash
skills-ref validate ./my-skill
```

Checks: frontmatter present and valid, name matches directory, description within length limits.
