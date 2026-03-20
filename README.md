# DotSkills

**Production-grade Agent Skills that close the developer loop — from Jira ticket to merged PR.**

A curated collection of 14 self-contained skills following the [Agent Skills Open Standard](https://agentskills.io/specification).
Works with **Claude Code**, **Windsurf**, **Cursor**, **Codex**, **Gemini CLI**, and **Antigravity**.

## The Developer Loop

Every skill maps to a stage in the developer workflow. The goal: an AI agent that can assist across the entire loop without ever touching secrets or making irreversible changes without approval.

```mermaid
flowchart LR
    Task["Task Definition
    (jira-manager)"]
    Plan["Plan + Code
    (native AI)"]
    Build["Build / Test
    (sbt-build-test
    jenkins-manager)"]
    Debug["Debug
    (eks-pod-ops)"]
    Review["Code Review
    (super-review
    review-prompts)"]
    PR["Pull Request
    (bitbucket-manager)"]
    Docs["Documentation
    (confluence-publisher)"]
    Update["Task Update
    (jira-manager)"]

    Task --> Plan --> Build
    Build --> Debug
    Debug -->|fix| Plan
    Build --> Review --> PR
    PR -->|feedback| Plan
    PR --> Docs --> Update --> Task

    style Task fill:#4a9eff,color:#fff
    style Plan fill:#666,color:#fff
    style Build fill:#ff6d00,color:#fff
    style Debug fill:#ff6d00,color:#fff
    style Review fill:#00c853,color:#fff
    style PR fill:#7c4dff,color:#fff
    style Docs fill:#00bcd4,color:#fff
    style Update fill:#4a9eff,color:#fff
```

## Why DotSkills

**AI agents are great at writing code but bad at integration.** Without guardrails, they write ad-hoc curl commands, miss pagination, hardcode credentials, and skip safety checks on destructive operations.

**Each skill wraps one external system with deterministic CLI scripts.** Scripts absorb the complexity — they handle pagination, retries, error formatting, and output parsing. The agent makes simple, sequential calls. Every additional agent step is a place to fall; every script is a place to land.

**Security is not an afterthought.** Credentials are never stored in config files (only env var *names*). All output passes through secret redaction pipelines. Dangerous commands are blocklisted before execution. Write operations default to dry-run. Destructive actions require explicit user approval. PR approval is intentionally omitted — that is a human-only action.

**Zero or minimal dependencies.** Most skills are pure Python stdlib with no pip install, no venv setup, and no build step. A skill works the moment it is copied into your IDE's skill directory.

## Skills by Stage

### Task Definition

| Skill | What It Does | Links |
|---|---|---|
| [jira-manager](./jira-manager/) | CRUD, bulk ops, JQL, field discovery, transitions | [design](./docs/jira-manager/jira-manager-design.md) |

### Code

| Skill | What It Does | Links |
|---|---|---|
| [codex-subagent](./codex-subagent/) | Delegate tasks to OpenAI Codex CLI — parallel work, fresh context, safety wrapper | [design](./docs/codex-subagent/codex-subagent-design.md) |

### Build / Test

| Skill | What It Does | Links |
|---|---|---|
| [sbt-build-test](./sbt-build-test/) | Multi-repo builds, dependency chains, test parsing | [design](./docs/sbt-build-test/sbt-build-test-design.md) |

### CI/CD

| Skill | What It Does | Links |
|---|---|---|
| [jenkins-manager](./jenkins-manager/) | Build status, logs, triggers, auto-discovery from git | [design](./docs/jenkins-manager/jenkins-manager-design.md) |

### Debug

| Skill | What It Does | Links |
|---|---|---|
| [eks-pod-ops](./eks-pod-ops/) | Pod logs, exec, restarts, secret redaction | [design](./docs/eks-pod-ops/eks-pod-ops-design.md) |

### Code Review

| Skill | What It Does | Links |
|---|---|---|
| [super-review](./super-review/) | Parallel multi-perspective reviews, graded reports | [design](./docs/super-review/super-review-design.md) |
| [review-prompts](./review-prompts/) | 12 review prompt types, standalone or file injection | |

### Pull Request

| Skill | What It Does | Links |
|---|---|---|
| [bitbucket-manager](./bitbucket-manager/) | PR lifecycle, comments, build checks, Jira extraction | [design](./docs/bitbucket-manager/bitbucket-manager-design.md) |

### Documentation

| Skill | What It Does | Links |
|---|---|---|
| [confluence-publisher](./confluence-publisher/) | Markdown to Confluence, hierarchies, Mermaid, surgical edits | [design](./docs/confluence-publisher/confluence-publisher-design.md) |

### Meta / Tooling

| Skill | What It Does |
|---|---|
| [skill-creator](./skill-creator/) | Scaffold new skills from scripts or from scratch, spec compliance verification |
| [skill-sync](./skill-sync/) | Distribute skills to 6 IDEs, OS-agnostic, user or project level |
| [codebase-analyzer](./codebase-analyzer/) | Line counts, language breakdown, test ratios, git churn hotspots |

## Security Principles

- **Credentials via env var names only** — config stores `"token_env": "JIRA_TOKEN"`, never the token itself
- **Automatic secret redaction** — all output passes through regex pipelines (Bearer tokens, AWS keys, JWTs, passwords, high-entropy strings)
- **Exec blocklist** — dangerous commands (`env`, `printenv`, secret file reads) blocked before execution
- **Dry-run by default** — write operations support `--dry-run`; agents preview before acting
- **Approval gates** — destructive operations (merge, decline, delete) require explicit user confirmation
- **No rubber-stamping** — PR approval intentionally omitted; approval is a human-only action
- **Log scrubbing** — Jenkins and EKS log output is redacted before reaching the agent context

## Quick Start

```bash
# Clone
git clone https://github.com/sagy101/DotSkills.git
cd DotSkills

# Detect installed IDEs
python3 skill-sync/scripts/sync.py --source . --level both --detect

# Sync all skills (preview first)
python3 skill-sync/scripts/sync.py --source . --level user --dry-run

# Sync for real
python3 skill-sync/scripts/sync.py --source . --level user --targets all

# Or sync to a specific project
python3 skill-sync/scripts/sync.py --source . --level project --project /path/to/project
```

Or copy manually:

```bash
cp -r <skill-name> /path/to/your-project/<ide-skills-dir>/
```

Skills are automatically discovered by supported AI tools when placed in the correct directory.

## Compatibility

Skills follow the [Agent Skills Open Standard](https://agentskills.io/specification) and work with:

- **Windsurf** (`.windsurf/skills/`)
- **Claude Code** (`.claude/skills/`)
- **Cursor** (`.cursor/skills/`)
- **OpenAI Codex** (`.codex/skills/`)
- **Gemini CLI** (`.gemini/skills/`)
- **Antigravity** (`.agent/skills/`)

## Structure

Each skill follows this layout:

```
skill-name/
  SKILL.md              # Required — skill definition (YAML frontmatter + instructions)
  scripts/              # Optional — executable scripts
  references/           # Optional — detailed docs, schemas, templates
  assets/               # Optional — images, data files, templates
```

Design documents for each skill live in [`docs/`](./docs/).

## Tests

330+ tests across the repo, organized by skill in `tests/`:

```
tests/
  codex-subagent/        # 83 tests — safety parsing, flag scanning, arg building
  eks-pod-ops/           # 64 tests — secret redaction, config loading, pod parsing
  jenkins-manager/       # 83 tests — config, redaction, client, status, ANSI stripping
  jira-manager/          # 70+ tests — config, field resolution, JQL, links, workflows
  sbt-build-test/        # 30 tests — workspace graph, topo sort, dependency graph
  confluence-publisher/  # page utils, element replacement
  bitbucket-manager/     # E2E integration tests
```

```bash
python3 -m pytest tests/ -v
```

## Roadmap

- **Team notification skill** — Slack/Teams integration to notify developers on build results, PR status, and ticket transitions. Exploring [Vercel AI Chat SDK](https://sdk.vercel.ai/) as the foundation.

## Adding a New Skill

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
