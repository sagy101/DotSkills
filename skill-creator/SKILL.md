---
name: skill-creator
description: >
  Create polished, generic Agent Skills (SKILL.md + scripts + references) from use-case-specific
  scripts or code. Use when the user wants to turn a working script into a reusable skill,
  create a new skill from scratch, refactor an existing skill, or generate a SKILL.md following
  prompt engineering and Agent Skills specification best practices. Handles analysis of source
  scripts, generalization of hardcoded values into configuration, creation of directory structures,
  writing of SKILL.md with proper frontmatter, workflow sections, pre-flight checks, and
  supporting reference documents.
license: MIT
metadata:
  author: sagy101
  version: "1.0"
compatibility: >
  Requires Python 3.10+ and PyYAML (`pip install PyYAML`) for the skill-creator scripts.
---

# Skill Creator

Turn use-case-specific scripts into polished, generic Agent Skills following the Agent Skills specification, prompt engineering best practices, and proven patterns.

## Design philosophy

**Max capability, max simplicity.** The overall guideline: prefer a simpler agent surface over simpler scripts. When logic can live in a script, it should — scripts are deterministic, testable, and debuggable, while agent steps are fragile decision points. This is a balance, not a dogma: don't write overly complex scripts to avoid trivial agent decisions. But when in doubt, push complexity into scripts and keep the agent workflow as a short, linear sequence of script calls.

Every additional agent step is a place to fall. Every script is a place to land.

## When to use this skill

Use this skill when the user wants to:
- Convert a working script into a reusable, generic Agent Skill
- Create a new Agent Skill from scratch (with or without existing code)
- Refactor or improve an existing SKILL.md
- Generate proper SKILL.md frontmatter and body content
- Apply prompt engineering best practices to skill instructions

## Workflow

Always follow this sequence. Never skip the analysis or plan steps.

### Step 1 — Gather input

Determine what the user is starting from:

#### Path A — Existing script(s)

Read and analyze the code to understand purpose, inputs, outputs, dependencies, hardcoded values, and external API calls.

For existing scripts, identify:
1. **Purpose**: What does the script do? What problem does it solve?
2. **Hardcoded values**: URLs, project keys, credentials, paths, field names — these become config
3. **Dependencies**: Python packages, CLI tools, APIs, environment variables
4. **Input/output**: What does it take in? What does it produce?
5. **Side effects**: Does it create/modify/delete external resources? (These need approval gates)
6. **Error modes**: What can go wrong? How does it fail?

Keep a mental map of every function and data flow in the original script. You will need this in Step 5 to verify nothing was lost during generalization.

#### Path B — Idea or user prompt (no initial script)

When the user describes what they want but has no existing code, gather enough detail to design the skill from scratch:

1. **What tool/service/API does it interact with?** — Get the API docs URL if possible
2. **What operations should it support?** — CRUD? Sync? Diff? Export? Validate?
3. **What inputs does it need?** — Files, CLI args, config fields, credentials
4. **What outputs does it produce?** — Terminal output, files, API mutations
5. **What are the failure modes?** — Auth errors, rate limits, missing data
6. **What is the target audience?** — Solo dev, team, CI/CD pipeline

If the user's description is vague, ask clarifying questions. Do not proceed to Step 2 until you can answer all 6 questions above. Propose a concrete scope and get confirmation before designing.

#### Path C — Existing skill to refactor

Read the current SKILL.md and all supporting files. Identify gaps against the mandatory sections and best practices checklist in Step 3.

### Step 2 — Design the skill architecture

Plan the full skill directory structure. Follow this pattern (proven in production skills):

```
skill-name/
├── SKILL.md                    # Required — skill definition
├── scripts/                    # Executable scripts the agent runs (Python, Bash, Node, etc.)
│   ├── setup_env.sh            # Optional: Setup script (if needed)
│   ├── config_loader.py        # Optional: Config handling (language-specific)
│   └── <operation>.<ext>       # One script per operation
├── references/                 # Detailed docs loaded on demand
│   ├── CONFIG.md               # Config file schema
│   └── <domain-specific>.md    # Format specs, field mappings, etc.
└── assets/                     # Templates, default configs, schemas
    └── default-config.yaml     # Shipped defaults users can copy
```

**Key design decisions to present to the user:**
- Skill name (lowercase, hyphens, 1-64 chars)
- **Implementation language** (Python, Bash, Node.js, Go, etc.)
- Config file format and name (e.g., `.tool-name.json`)
- Which operations to support
- What needs approval gates vs what is safe to auto-run
- Where to store the skill (global vs workspace vs shared repo)

**Wait for user approval before proceeding to implementation.**

### Step 3 — Write the SKILL.md

Follow the structure and rules in [references/SKILL_SPEC.md](references/SKILL_SPEC.md) and [references/PROMPT_ENGINEERING.md](references/PROMPT_ENGINEERING.md). Use [references/SKILL_TEMPLATE.md](references/SKILL_TEMPLATE.md) as the structural template.

#### Frontmatter rules

```yaml
---
name: skill-name          # Must match directory name, lowercase + hyphens only
description: >            # 1-1024 chars. Include BOTH what it does AND when to use it.
  Verb-first action description. Include trigger keywords that help agents
  identify when this skill is relevant.
license: MIT
metadata:
  author: <author>
  version: "1.0"
allowed-tools: >            # Optional: List of pre-approved tools (experimental)
  read_file run_command
compatibility: >            # Only if specific requirements exist
  Runtime requirements, API versions, OS constraints.
---
```

#### Body structure (mandatory sections)

Write these sections in this exact order:

1. **Title + one-liner** — `# Skill Name` + single sentence summary
2. **When to use this skill** — bullet list of trigger scenarios with action verbs
3. **Prerequisites** — numbered list: config file, credentials, dependencies
4. **Configuration** — minimal config example + link to `references/CONFIG.md`
5. **Pre-flight checks** — a single script call that validates the environment before ANY operation. The script (not the agent) runs all checks and reports results:
   - Check 1: Runtime environment (Language version, dependencies, or tool availability)
   - Check 2: Configuration file exists and is valid
   - Check 3: Credentials are set (never print values, only confirm SET/MISSING)
   - Check 4: Connectivity or discovery (if applicable)

   The agent calls the preflight script once and reads the output — it does not run each check individually. This is a key example of the design philosophy: script absorbs the complexity, agent stays simple.
6. **Workflow** — numbered steps: validate → determine scope → build plan → get approval → execute → verify
7. **Operations** — one subsection per operation with exact CLI commands using `<skill_dir>` placeholder
8. **Important rules** — numbered list of invariants (approval gates, security, ordering)
9. **Error handling** — table with columns: Error | Cause | Fix
10. **Troubleshooting** — table with columns: Problem | Fix

#### Writing quality checklist

Apply these prompt engineering principles (see [references/PROMPT_ENGINEERING.md](references/PROMPT_ENGINEERING.md)):

- [ ] **Be clear and direct** — Write instructions as if for a brilliant new employee with zero context
- [ ] **Use sequential steps** — Numbered lists for ordered procedures, bullets for unordered sets
- [ ] **Say what TO do, not what NOT to do** — Positive instructions are clearer
- [ ] **Include examples** — Show exact CLI commands, config snippets, expected output
- [ ] **Add context/motivation** — Explain WHY a rule exists, not just WHAT it is
- [ ] **Progressive disclosure** — Keep SKILL.md body under ~5000 tokens; put details in `references/`
- [ ] **Trigger keywords in description** — Include domain terms that help agents match the skill
- [ ] **Approval gates** — Any create/update/delete of external resources requires showing a plan and waiting for explicit user approval
- [ ] **Never expose credentials** — Only confirm SET/MISSING status of env vars
- [ ] **Consistent placeholders** — Use `<skill_dir>` for the skill's own directory path

### Step 4 — Write supporting files

#### Config reference (`references/CONFIG.md`)

Document the full schema of the config file:
- Every field with type, default, and description
- Required vs optional fields clearly marked
- A complete example with all fields populated

#### Operation-specific references

For each complex operation, create a reference doc covering:
- Input format specification
- Output format specification
- Edge cases and limitations

#### Scripts

When creating scripts, follow these patterns:

- **Scripts absorb complexity, not the agent** — if logic can live in a script, it must. The agent should call scripts with simple CLI args, not reason through multi-step logic inline. More scripts with thin agent glue > fewer scripts with thick agent reasoning.
- **One script per operation** — keep scripts focused and single-purpose
- **Shared config loader** — centralize config parsing and credential resolution
- **Setup script** — bootstrap environment (e.g., venv for Python, npm install for Node)
- **CLI interface** — every script uses standard flag parsing (e.g., `argparse`, `minimist`)
- **Path handling** — scripts must handle execution from any working directory (use absolute paths or self-discovery)
- **Structured exit codes** — 0 success, 1 operation error, 2 config error
- **Helpful error messages** — tell the user what went wrong AND how to fix it
- **`--dry-run`** flag — for any destructive operation, support preview mode

### Step 5 — Verify the skill

This is the most critical step. Run ALL of the following verification checks before presenting the skill to the user. Do not skip any check. Report results as a checklist.

#### Check 5.1 — Best practices compliance

Review the generated SKILL.md against both the prompt engineering and Agent Skills best practices:

- [ ] Frontmatter `name` matches directory name (lowercase, hyphens only)
- [ ] Frontmatter `description` is 1-1024 chars with action verbs and domain trigger keywords
- [ ] All 10 mandatory body sections are present (title, when-to-use, prerequisites, configuration, pre-flight checks, workflow, operations, important rules, error handling, troubleshooting)
- [ ] Instructions are clear and direct — written for an agent with zero prior context
- [ ] Sequential procedures use numbered steps; unordered sets use bullets
- [ ] Instructions say what TO do (positive), not what NOT to do (negative)
- [ ] Examples show exact CLI commands with realistic arguments
- [ ] Context/motivation is provided for important rules (explains WHY)
- [ ] Progressive disclosure is applied — SKILL.md body is concise; detail is in `references/`
- [ ] `<skill_dir>` placeholder is used consistently for the skill's own directory

#### Check 5.2 — Environment and configuration verification

Confirm the generated skill properly guides the agent through environment setup:

- [ ] Pre-flight checks section exists with numbered checks
- [ ] Check for runtime environment (language version, dependencies, tool availability)
- [ ] Check for configuration file existence with interactive creation guidance if missing
- [ ] Check for credentials (confirms SET/MISSING status of env vars without printing values)
- [ ] Config file schema is fully documented in `references/CONFIG.md` (every field: type, default, required/optional, description)
- [ ] Minimal config example is in the SKILL.md body
- [ ] If the tool has discoverable metadata (custom fields, issue types, etc.), a discovery check is included
- [ ] Setup script (if needed) creates necessary environment (venv, node_modules, etc.)

#### Check 5.3 — Error handling quality

Verify the skill gives the agent enough information to diagnose and fix problems:

- [ ] Error handling table exists with columns: Error | Cause | Fix
- [ ] Troubleshooting table exists with columns: Problem | Fix
- [ ] Common API errors are covered (401, 403, 404, 400, 429, 500)
- [ ] Common environment errors are covered (missing language runtime, missing dependencies, missing config)
- [ ] Every script produces actionable error messages (what went wrong + how to fix it)
- [ ] Scripts use structured exit codes (0 = success, 1 = operation error, 2 = config error)
- [ ] Destructive operations support `--dry-run` for safe preview

#### Check 5.4 — Compilation and testing

Verify all generated code is valid and functional:

- [ ] **Validation Tool**: Run `skills-ref validate <skill-dir>` if available
- [ ] **Syntax Check**: Run appropriate syntax check for the language:
  - Python: `python3 -m py_compile <file>`
  - Bash: `bash -n <file>`
  - Node.js: `node --check <file>`
- [ ] Verify all internal imports/references resolve
- [ ] Verify every `[text](references/FILE.md)` link in SKILL.md targets an existing file
- [ ] Verify every script has a standard entry point (e.g., `if __name__ == "__main__":` or equivalent)
- [ ] If the skill has a dependency file (requirements.txt, package.json), verify it lists all imports
- [ ] Run a `--help` check on each script: `<runtime> <script> --help` should print usage without errors

Present results as:
```
✓ skills-ref      — Passed validation
✓ config_loader   — compiles, imports resolve, --help OK
✓ create_item     — compiles, imports resolve, --help OK
```

#### Check 5.5 — Diff review against original scripts (when derived from existing code)

When the skill was created from existing scripts (Path A), perform a systematic review of every difference between the original and generated code:

1. **List every original script** and its corresponding generated script(s)
2. **For each pair**, identify and categorize every material change:

| Change category | Example | Expected? |
|---|---|---|
| **Generalization** | Hardcoded URL → config field lookup | Yes — this is the core purpose |
| **Refactoring** | Monolithic function → smaller helpers | Yes — improves maintainability |
| **Feature addition** | New `--dry-run` flag, new output format | Yes — skill pattern requirement |
| **Feature removal** | Removed a function or capability | Needs justification |
| **Bug fix** | Fixed an error in original logic | Document what was fixed |
| **Behavioral change** | Different default, different order of operations | Needs justification |

3. **Report the diff summary** to the user:
   - Number of original scripts → number of generated scripts
   - List of functions/capabilities preserved, added, and removed
   - For each removed or changed capability, explain WHY
4. **Flag any capability from the original that is missing** in the generated skill — the user must explicitly approve any omission

Present results as:
```
Original: create_jira_tickets.py (823 lines, 1 file)
Generated: 12 scripts (config_loader.py, create_ticket.py, bulk_create.py, ...)

Preserved: ticket creation, subtask creation, description formatting, link rewriting
Added: config-driven fields, discovery, diff, delete, validation, dry-run, fetch
Changed: hardcoded epic/project → config lookup (generalization)
Removed: none
```

#### Check 5.6 — No hardcoded project-specific values

Scan all generated files for leaked specifics:

- [ ] No hardcoded URLs (search for `https://`, `http://`)
- [ ] No hardcoded API keys, tokens, or passwords
- [ ] No hardcoded project keys, space keys, or page IDs
- [ ] No hardcoded usernames or email addresses
- [ ] No hardcoded file paths specific to the original project
- [ ] Config example values use obvious placeholders (e.g., `https://mycompany.atlassian.net`)

### Step 6 — Install the skill

Ask the user where to install:

| Scope | Location | Availability |
|---|---|---|
| **Workspace** | `.windsurf/skills/<name>/` or `.agents/skills/<name>/` | Current project only |
| **Global** | `~/.codeium/windsurf/skills/<name>/` | All projects |
| **Shared repo** | `~/CascadeProjects/<shared-repo-name>/<name>/` | Portable, version-controlled |

For shared repo installs, also update the repo's `README.md` table.

## Generalization patterns

When converting a specific script to a generic skill, apply these transformations:

| Hardcoded element | Generalization |
|---|---|
| API base URL | Config field (`"base_url": "https://..."`) |
| Problem | Fix |
|---|---|
| `<runtime>: command not found` | Install the required runtime (Python, Node, Go, etc.) |
| `Module/Package missing` | Run the setup script or install dependencies manually |
| Config field not working | Run discovery script to auto-detect field IDs |
| File paths | CLI `--path` argument with sensible default (cwd) |
| Output format | CLI `--output` flag (terminal/json/markdown) |
| Hardcoded lists/mappings | Config arrays or reference files |
| Magic numbers | Named config fields with defaults |

## Important rules

1. **Always show the skill plan and get approval before creating files.** Present the directory structure, list of files, and key design decisions.
2. **Never include project-specific values in the skill.** All environment-specific data goes into the config file.
3. **Every destructive operation in the generated skill must have an approval gate.** The generated SKILL.md must instruct the agent to show a plan and wait for user confirmation before create/update/delete.
4. **Follow the Agent Skills specification exactly.** See [references/SKILL_SPEC.md](references/SKILL_SPEC.md).
5. **Apply prompt engineering best practices.** See [references/PROMPT_ENGINEERING.md](references/PROMPT_ENGINEERING.md).
6. **Keep SKILL.md concise.** Use progressive disclosure — put detailed schemas, format specs, and examples in `references/` files.
7. **Test everything.** Compile-check all Python scripts. Verify all internal links resolve.
8. **Mirror proven patterns.** Follow the structural conventions established in existing skills (confluence-publisher, jira-manager, codebase-analyzer) for consistency.
