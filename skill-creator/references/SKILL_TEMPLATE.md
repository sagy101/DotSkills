# SKILL.md Template

Copy this template when creating a new skill. Replace all `<placeholders>` with actual values.

```markdown
---
name: <skill-name>
description: >
  <Verb-first description of what this skill does. Include action verbs (create, update, fetch,
  delete, publish, analyze, validate, diff, export) and domain-specific keywords that help agents
  identify when this skill is relevant. Describe BOTH what it does AND when to use it.>
license: MIT
metadata:
  author: <author>
  version: "1.0"
allowed-tools: >
  <List of tools this skill needs. E.g.: read_file, run_command, search_web>
compatibility: >
  <Runtime requirements. E.g.: Requires Python 3.10+, Node.js 18+, or specific CLI tools.
  Works with <Service> API v2. Requires an API token with <specific> permissions.>
---

# <Skill Title>

<One-sentence summary of what this skill does.>

## When to use this skill

Use this skill when the user wants to:
- <Action verb> <what> (e.g., "Create one or more Jira tickets")
- <Action verb> <what> from <source>
- <Action verb> existing <resources>
- <Action verb> <what> against <what> (e.g., "Diff local spec against live state")

## Prerequisites

Before running any operation, ensure:

1. A **project config file** exists at `.<tool-name>.json` in the project root (see [CONFIG.md](references/CONFIG.md) for format)
2. **Credentials** are available as environment variables (names configured in `.<tool-name>.json`)
3. Required runtime dependencies are installed (e.g., via `setup_env` script or package manager)

If `.<tool-name>.json` does not exist, help the user create one by asking for:
- <Service> base URL
- Project key or identifier
- Environment variable names for credentials
- Path to `.env` file if they use one

## Configuration

The project must contain a `.<tool-name>.json` file. See [references/CONFIG.md](references/CONFIG.md) for the full schema. Minimal example:

```json
{
  "<service>_url": "https://example.com",
  "project_key": "<KEY>",
  "credentials": {
    "username_env": "<TOOL>_EMAIL",
    "token_env": "<TOOL>_TOKEN"
  },
  "env_file": ".env"
}
```

## Pre-flight checks

Before running ANY script, perform these checks proactively.

### Check 1 — Runtime environment

Verify the required language runtime and dependencies are available.

**Example (Python):**
```bash
python3 --version
# Check imports
python3 -c "import <key_dependency>; print('OK')"
```

**Example (Node.js):**
```bash
node --version
# Check modules
npm list <key_dependency>
```

If missing, run the setup script (if provided) or instruct the user to install dependencies.

### Check 2 — Configuration file

Look for `.<tool-name>.json` in the project root. If missing, do NOT proceed — help the user create one interactively.

### Check 3 — Credentials

Confirm credential environment variables are set. Do NOT print their values.

```bash
# Example check
python3 -c "import os; print('token:', 'SET' if os.environ.get('<TOOL>_TOKEN') else 'MISSING')"
```

Substitute actual env var names from `.<tool-name>.json`.

### Check 4 — Discovery (first run, if applicable)

If the service has dynamic fields or metadata, run discovery to auto-detect them:

```bash
<runtime_command> <skill_dir>/scripts/discover.<ext> --config .<tool-name>.json --apply
```

## Workflow

Always follow this sequence. Never skip pre-flight checks or the plan step.

### Step 1 — Validate configuration

Run pre-flight checks above. Confirm all required fields are present and credentials are set.

### Step 2 — Determine operation

Identify what the user wants from one of these operations:
- **Create**: <description>
- **Update**: <description>
- **Fetch**: <description>
- **Delete**: <description> (requires confirmation)
- **Diff**: <description>

### Step 3 — Build the action plan

For create, update, and delete operations, present a plan to the user.

**Wait for explicit user approval before proceeding.** If the user asks to change anything, update the plan and present again.

### Step 4 — Execute

Run the appropriate script. See operation-specific instructions below.

### Step 5 — Verify

After create or update operations, offer to:
- Run validation
- Run diff to confirm changes
- Fetch results to display

## Operations

### <Operation 1>

```bash
<runtime_command> <skill_dir>/scripts/<operation1>.<ext> \
  --config .<tool-name>.json \
  --<flag1> <value1> \
  --<flag2> <value2>
```

### <Operation 2>

```bash
<runtime_command> <skill_dir>/scripts/<operation2>.<ext> \
  --config .<tool-name>.json \
  --<flag> <value>
```

## Important rules

1. **Never create, update, or delete without showing the plan first and getting explicit user approval.**
2. **Never print or log credentials.** Only confirm that environment variables are set.
3. **<Operation ordering rule, e.g., "Create in dependency order: parents before children.">**
4. The manifest file (`.<tool-name>-manifest.json`) is auto-maintained by scripts. Do not edit manually.
5. If an operation fails, stop and report the error — do not continue with dependent operations.

## Error handling

| Error | Cause | Fix |
|---|---|---|
| `401 Unauthorized` | Bad credentials | Verify env vars are set and token has correct permissions |
| `404 Not Found` | Wrong ID or key | Check the key exists and config is correct |
| `400 Bad Request` | Missing required field | Run discovery or check config for required fields |

## Troubleshooting

| Problem | Fix |
|---|---|
| `<runtime>: command not found` | Install the required runtime (Python, Node, Go, etc.) |
| `Module/Package missing` | Run the setup script or install dependencies manually |
| Config field not working | Run discovery script to auto-detect field IDs |

## Notes on using this template

- Replace all `<placeholders>` with actual values
- Remove sections that don't apply (e.g., Discovery if the service has no dynamic fields)
- Add operation-specific sections as needed
- The triple backticks in code blocks above are escaped with spaces — remove the spaces in actual use
- Keep the SKILL.md body under ~5000 tokens; move detailed schemas to `references/CONFIG.md`
