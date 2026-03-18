# dotskills

A personal collection of reusable [Agent Skills](https://agentskills.io) for AI coding assistants.

Each skill is a self-contained directory following the [Agent Skills Open Standard](https://agentskills.io/specification) — a `SKILL.md` definition file plus optional scripts, references, and assets.

## Available skills

### Development Tools

| Skill | Description |
|---|---|
| [codex-subagent](./codex-subagent/) | Delegate coding tasks to OpenAI Codex CLI as a sub-agent — parallel work, fresh context, second opinions. Python safety wrapper, collision confidence, guardrails. POSIX-only. See [design](./docs/codex-subagent/codex-subagent-design.md). |
| [super-review](./super-review/) | Run parallel multi-perspective code reviews using sub-agents — synthesize, de-duplicate, grade, and present unified findings. Backend-agnostic (works with codex-subagent, Claude Code, or any sub-agent executor). See [design](./docs/super-review/super-review-design.md). |
| [review-prompts](./review-prompts/) | Reusable review prompt library — code review, security, plan review, architecture, performance, testing, prompt engineering, and language-specific prompts. Works standalone or as a file injection to sub-agents. |

### Productivity / Integration

| Skill | Description |
|---|---|
| [bitbucket-manager](./bitbucket-manager/) | Manage Bitbucket Cloud PRs — create, update, merge, decline, comment, list. Build/pipeline status checks, Jira issue extraction, repo listing. Zero pip deps (pure stdlib). See [design](./docs/bitbucket-manager/bitbucket-manager-design.md). |
| [confluence-publisher](./confluence-publisher/) | Publish markdown docs to Confluence Cloud — pages, hierarchy, cross-links, Mermaid diagrams, diff/preview, export, fetch. Surgical HTML edits (find/replace without overwriting formatting), version diff, version history, page revert |
| [jira-manager](./jira-manager/) | Create, update, fetch, delete, diff, and validate Jira tickets — bulk create from markdown/JSON, bulk update (list, board, JQL), full field catalog discovery (statuses, priorities, components, versions), status transitions, generic `--set` and `--filter` flags for any discovered field, estimation validation, link rewriting |
| [jenkins-manager](./jenkins-manager/) | Check Jenkins CI/CD build status, view console logs, trigger builds, view build changesets, check queue status, list jobs/folders. Auto-discovers job from git remote. Secret redaction on all log output. Zero pip deps (pure stdlib). See [design](./docs/jenkins-manager/jenkins-manager-design.md). |
| [eks-pod-ops](./eks-pod-ops/) | Read pod logs, list/describe pods, exec into containers, and restart deployments on EKS clusters. Automatic secret redaction (tokens, keys, passwords, JWTs), exec blocklist (blocks bare `env`/`printenv`, secret file reads), sidecar-aware container selection, Rancher Desktop kubectl workaround. Zero pip deps (pure stdlib) |

### Meta / Tooling

| Skill | Description |
|---|---|
| [skill-creator](./skill-creator/) | Create polished, generic Agent Skills from use-case-specific scripts or from scratch — prompt engineering best practices, Agent Skills spec compliance, comprehensive verification (compilation, diff review, env/config checks, error handling) |
| [skill-sync](./skill-sync/) | Sync skills from this repo to IDE skill directories (Windsurf, Claude Code, Cursor, Codex, Gemini CLI, Antigravity) — OS-agnostic, user-level or project-level, auto-detects installed IDEs |
| [codebase-analyzer](./codebase-analyzer/) | Analyze any codebase for structured metrics — line counts by category, language breakdown, test:code ratio, file-size distribution, TODO tracking, git churn hotspots. Terminal, JSON, and Markdown output |

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
cp -r <skill-name> /path/to/your-project/<ide-skills-dir>/
```

Skills are automatically discovered by supported AI tools when placed in the correct directory.

## Compatibility

Skills in this repo follow the [Agent Skills Open Standard](https://agentskills.io/specification) and work with:
- **Windsurf** (`.windsurf/skills/`)
- **Claude Code** (`.claude/skills/`)
- **Cursor** (`.cursor/skills/`)
- **OpenAI Codex** (`.codex/skills/`)
- **Gemini CLI** (`.gemini/skills/`)
- **Antigravity** (`.agent/skills/`)

## Tests

Tests live in `tests/` at the repo root, organized by skill:

```
tests/
  codex-subagent/
    test_run_codex.py    # 83 tests — safety parsing, flag scanning, arg building
  eks-pod-ops/
    test_eks_redaction.py  # 49 tests — secret redaction patterns, exec blocklist
    test_eks_config.py     #  9 tests — config loading, env resolution, kubeconfig paths
    test_pods.py         #  6 tests — container selection, pod parsing, sidecar skipping
  jenkins-manager/
    test_jenkins_config.py      # 30 tests — repo parsing, branch encoding, deep merge, job/branch resolution
    test_jenkins_redaction.py   # 33 tests — secret redaction patterns, Jenkins log false positives
    test_client.py              # 20 tests — color-status mapping, API path construction
```

Run with pytest:

```bash
python3 -m pytest tests/ -v
```

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
