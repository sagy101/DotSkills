---
name: review-prompts
description: >
  Review code, security, plans, architecture, performance, testing, prompt engineering, and language-specific quality. Focused .md prompt files for standalone use or delegation to sub-agents. Use when asked to review code, audit security, evaluate a plan, check architecture, assess performance, review tests, or review prompts and AI skill definitions.
license: MIT
metadata:
  author: sagy101
  version: "1.0"
---

# Review Prompts

Reusable `.md` prompt files that instruct an AI agent how to review a specific aspect of code, plans, or other artifacts.

## When to use this skill

Use this skill when the user wants to:
- Review a pull request, commit, or set of code changes
- Audit code for security vulnerabilities
- Evaluate an implementation plan or design document
- Check architecture for SOLID violations or coupling issues
- Assess code for performance bottlenecks
- Review test quality and coverage gaps
- Apply language-specific best practices (TypeScript, Python, Java, Scala, JavaScript)
- Review prompts or AI skill definitions for prompt engineering quality

## Available Review Types

| Type | File | Focus |
|---|---|---|
| **Code Review** | `prompts/code-review.md` | General code quality, logic, style, bugs, DRY, error handling |
| **Security** | `prompts/security.md` | OWASP top 10, injection, auth, secrets, crypto, input validation |
| **Plan Review** | `prompts/plan-review.md` | Structure, logic, completeness, consistency, implementation clarity |
| **Architecture** | `prompts/architecture.md` | SOLID, coupling, cohesion, separation of concerns, extensibility |
| **Performance** | `prompts/performance.md` | N+1 queries, complexity, hot paths, memory, caching, concurrency |
| **Testing** | `prompts/testing.md` | Coverage, edge cases, mocking strategy, flaky tests, integration |
| **TypeScript** | `prompts/typescript.md` | Strict null, generics, type narrowing, module patterns, TS anti-patterns |
| **Python** | `prompts/python.md` | Typing, async/await, idioms, packaging, Pythonic patterns |
| **Java** | `prompts/java.md` | Spring Boot, enterprise patterns, Java 21+, SOLID, JPA/Hibernate |
| **Scala** | `prompts/scala.md` | Functional patterns, implicits, type classes, effect systems, concurrency |
| **JavaScript** | `prompts/javascript.md` | ES2024+, async patterns, closures, Node.js, framework idioms |
| **Prompt Engineering** | `prompts/prompt-engineering.md` | Clarity, structure, examples, output format, constraints, token efficiency |

## Pre-flight checks

Run the preflight script before first use:

```bash
python3 <skill_dir>/scripts/rp_preflight.py
```

This checks Python version, build-prompt.py presence, shared template, prompt files, and a runtime test of `--list` in one pass. Each check prints `[PASS]`, `[FAIL]`, or `[WARN]`. Exit code 0 = all checks passed, 1 = at least one failed.

## Building Prompts

Each review type is stored as a lean `.md` file (Role + Checklist only). Shared sections (Process, Output Format, Constraints) live in `prompts/_shared.md`. A build script assembles the complete prompt with every section in the right place.

**Do not use the raw `.md` files in `prompts/` directly** — they are incomplete (missing Process, Output Format, Constraints). Always use `build-prompt.py` to produce a complete, ready-to-use prompt.

```
python3 scripts/build-prompt.py <type>              # prints to stdout
python3 scripts/build-prompt.py <type> -o <file>    # writes to file
python3 scripts/build-prompt.py --list              # lists available types
```

## Usage

### Standalone
```
1. Run: python3 scripts/build-prompt.py security
2. Read the assembled prompt output
3. Apply its checklist to the target code/plan/artifact
4. Output findings in the structured severity format
```

### With a sub-agent
Build the prompt and pass the output to the sub-agent — the host agent never reads the prompt itself:
```
1. Determine which review type(s) are needed
2. Run: python3 scripts/build-prompt.py <type> -o /tmp/<type>-prompt.md
3. Pass the output file path to the sub-agent along with the review target
4. The sub-agent reads the assembled prompt, applies the checklist, and returns structured findings
5. Synthesize findings from multiple sub-agents if running parallel reviews
```

## Example

Standalone review of a security concern:
```
1. Run: python3 scripts/build-prompt.py security
2. Read the target files: src/auth/login.ts, src/middleware/session.ts
3. Apply the security checklist to these files
4. Output findings in the structured severity format
```

Parallel sub-agent review of a PR:
```
1. Pick review types: code-review (always), security (auth changes detected)
2. Run: python3 scripts/build-prompt.py code-review -o /tmp/cr-prompt.md
3. Run: python3 scripts/build-prompt.py security -o /tmp/sec-prompt.md
4. Launch sub-agent #1 with /tmp/cr-prompt.md + the diff
5. Launch sub-agent #2 with /tmp/sec-prompt.md + the diff
6. Collect both results, de-duplicate, synthesize into unified review
```

## Custom Prompts
To add a custom review type:
1. Create a new `.md` file in the `prompts/` directory with **Role** and **Checklist** sections only (Process, Output Format, and Constraints are assembled from `prompts/_shared.md` by the build script)
2. Add a row to the **Available Review Types** table above with the type name, file path, and a short focus description — this helps the agent pick the right prompt
