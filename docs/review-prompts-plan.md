# Review Prompts Skill — Plan

> Works with any AI coding agent or sub-agent system. Pass prompt files to sub-agents to avoid consuming host agent context.

---

## Overview

A library of reusable, focused review prompts for AI coding agents. Each prompt is a `.md` file (~500-2000 tokens) that instructs an agent how to review a specific aspect of code, plans, or other artifacts.

**Two usage modes:**
1. **Standalone**: Any AI agent reads the assembled prompt and uses it directly as review instructions (no sub-agent needed)
2. **With a sub-agent**: Any sub-agent system can use these prompts — pass the assembled `.md` file to the sub-agent to avoid consuming host agent context

The prompts are agent-agnostic `.md` files. Any sub-agent system that accepts a prompt file can use them.

## File Structure

```
review-prompts/
├── SKILL.md                      # Skill definition: descriptions of each type + how to build prompts
├── REFERENCES.md                 # Attribution and licenses for all inspiration sources
├── scripts/
│   └── build-prompt.py           # Assembles complete prompt from _shared.md + type-specific file
└── prompts/
    ├── _shared.md                # Shared sections: Process, Output Format, Constraints
    ├── code-review.md            # Type-specific: Role + Checklist (general code quality)
    ├── security.md               # Type-specific: Role + Checklist (OWASP, injection, auth)
    ├── plan-review.md            # Type-specific: Role + Checklist (plan/design review)
    ├── architecture.md           # Type-specific: Role + Checklist (SOLID, coupling)
    ├── performance.md            # Type-specific: Role + Checklist (N+1, complexity, caching)
    ├── testing.md                # Type-specific: Role + Checklist (coverage, flaky tests)
    ├── prompt-engineering.md     # Type-specific: Role + Checklist (prompt quality)
    ├── typescript.md             # Type-specific: Role + Checklist (TS patterns)
    ├── python.md                 # Type-specific: Role + Checklist (Pythonic patterns)
    ├── java.md                   # Type-specific: Role + Checklist (Java 21+, Spring Boot)
    ├── scala.md                  # Type-specific: Role + Checklist (FP, type classes)
    └── javascript.md             # Type-specific: Role + Checklist (ES2024+, Node.js)
```

## SKILL.md Design

The SKILL.md should be small — it lists each review type with a **short description** (~50 tokens each) so the host agent can pick the right one without reading the full prompt files.

```yaml
---
name: review-prompts
description: >
  Focused review prompts for code, security, plans, architecture, performance,
  testing, prompt engineering, and language-specific reviews. Use standalone or
  pass assembled prompt files to any sub-agent system.
---
```

The body includes:
- A table of available review types with one-line descriptions
- Instructions for building prompts via `build-prompt.py`
- Instructions for standalone use: "Run `build-prompt.py <type>`, read the output, apply to target"
- Instructions for sub-agent use: "Run `build-prompt.py <type> -o <file>`, pass file to sub-agent"
- Note that users can add custom `.md` files (Role + Checklist only) to the `prompts/` directory

## Prompt File Format

Each type-specific `.md` file contains only **Role** and **Checklist** sections. Shared sections (Process, Output Format, Constraints) live in `prompts/_shared.md` and are assembled by `build-prompt.py`.

**Type-specific file** (`prompts/<type>.md`):
```markdown
# Review Type: <Name>

## Role
You are a <focus area> reviewer. Your job is to...

## Checklist
Review the provided code/artifact against these criteria:
- [ ] Criterion 1: description
- [ ] Criterion 2: description
...
```

**Shared file** (`prompts/_shared.md`):
```markdown
## Process
(common pre-review steps)

## Output Format
(structured severity-based finding format)

## Constraints
(severity rubric, actionable-findings-only rules)
```

**Assembled output** (produced by `build-prompt.py`):
```
# Review Type + ## Role → ## Process → ## Checklist → ## Output Format → ## Constraints
```

## Review Types — Detail

### `code-review.md`
General-purpose code review covering logic correctness, style, naming, DRY, error handling, edge cases, imports, and code organization.
- **Inspired by**: [baz-scm/awesome-reviewers](https://github.com/baz-scm/awesome-reviewers) — 8K+ review prompts distilled from real OSS pull request comments; Windsurf `/review` workflow — 9-category bug-focused review (logic errors, edge cases, null refs, race conditions, security, resource leaks, API contracts, caching, pattern violations); DocScope `review-staged` workflow — 6-category code review with custom criteria support

### `security.md`
OWASP-focused security review: injection attacks (SQL, command, XSS, XXE), authentication/authorization, data exposure, hardcoded secrets, cryptographic issues, input validation, TOCTOU, insecure defaults, supply chain risks.
- **Inspired by**: [anthropics/claude-code-security-review](https://github.com/anthropics/claude-code-security-review) — semantic vulnerability detection with false positive filtering

### `plan-review.md`
Implementation plan and design document review: structural clarity, problem-solution fit, completeness, logical flow, cross-file consistency, alternative consideration, implementation clarity (file paths, functions, dependencies), error handling strategy, testing strategy, edge case identification.
- **Inspired by**: [google/eng-practices](https://github.com/google/eng-practices) — 20K+ stars, Google's engineering practices including design doc and CL review guidelines; [joelparkerhenderson/architecture-decision-record](https://github.com/joelparkerhenderson/architecture-decision-record) — 12K+ stars, ADR templates covering decision review structure, context, consequences, and alternatives; DocScope `plan-review` workflow — 13-step review process covering structural, logic, consistency, architecture, implementation clarity, error handling, security, performance, and testing

### `architecture.md`
Architecture and design review: SOLID principles, coupling/cohesion, fan-in/fan-out, complexity, separation of concerns, single responsibility, scalability, extensibility, API contracts, protocol definitions, data formats.
- **Inspired by**: [mehdihadeli/awesome-software-architecture](https://github.com/mehdihadeli/awesome-software-architecture) — comprehensive curated list of architecture patterns and design resources; [sanyuan0704/code-review-expert](https://github.com/sanyuan0704/code-review-expert) — 2.1K stars, Agent Skill with SOLID and architecture checklists; [joelparkerhenderson/architecture-decision-record](https://github.com/joelparkerhenderson/architecture-decision-record) — 12K+ stars, ADR review structure

### `performance.md`
Performance review: N+1 queries, algorithmic complexity, unnecessary iterations, large object copying, missing memoization, blocking operations, database indexes, connection pools, rate limiting, memory leaks, caching strategy.
- **Inspired by**: [google/eng-practices](https://github.com/google/eng-practices) — 20K+ stars, Google's code review guidelines including performance considerations; [analysis-tools-dev/static-analysis](https://github.com/analysis-tools-dev/static-analysis) — 14K+ stars, curated list of static analysis tools across all languages (performance linters, profilers); DocScope `review-staged` workflow — performance review checklist (N+1 queries, unnecessary iterations, large object copying, missing memoization, blocking operations)

### `testing.md`
Test quality review: coverage gaps, happy path tests, edge case tests, error case tests, mocking strategy, integration test coverage, E2E critical paths, test naming, fixtures, setup/teardown, flaky test detection, regression coverage.
- **Inspired by**: [goldbergyoni/javascript-testing-best-practices](https://github.com/goldbergyoni/javascript-testing-best-practices) — 24K+ stars, comprehensive testing best practices (applicable beyond JS); [TheJambo/awesome-testing](https://github.com/TheJambo/awesome-testing) — curated list of testing resources and best practices

### `typescript.md`
TypeScript-specific review: strict null checks, proper use of generics, type narrowing, discriminated unions, module patterns, `any` avoidance, proper async/await typing, declaration file quality, TS config strictness.
- **Inspired by**: Language-specific reviewers from [awesome-reviewers](https://github.com/baz-scm/awesome-reviewers)

### `python.md`
Python-specific review: type hints, async/await patterns, Pythonic idioms, proper use of dataclasses/pydantic, packaging best practices, import organization, exception hierarchy, context managers, generator patterns.
- **Inspired by**: Language-specific reviewers from [awesome-reviewers](https://github.com/baz-scm/awesome-reviewers)

### `java.md`
Java-specific review: Java 21+ features (records, pattern matching, sealed classes), Spring Boot 3+ patterns, SOLID principles in enterprise context, JPA/Hibernate optimization (N+1, lazy loading, entity graphs), dependency injection, security (Spring Security 6+), concurrency (virtual threads, CompletableFuture).
- **Inspired by**: [google/error-prone](https://github.com/google/error-prone) — 7.1K stars, Google's Java static analysis tool catching common mistakes at compile-time; [spring-projects/spring-boot](https://github.com/spring-projects/spring-boot) — 76K+ stars, official Spring Boot project (best practices in docs and source)

### `scala.md`
Scala-specific review: functional programming patterns, proper use of implicits/givens, type classes, algebraic data types, effect systems (Cats Effect, ZIO), pattern matching exhaustiveness, collection operations, concurrency (Futures, actors), Scala 3 migration patterns.
- **Inspired by**: [scalacenter/scalafix](https://github.com/scalacenter/scalafix) — Scala Center official refactoring and linting tool; [analysis-tools-dev/static-analysis](https://github.com/analysis-tools-dev/static-analysis) — 14K+ stars, comprehensive list including Scala-specific tools (scapegoat, wartremover, scalafix, linter)

### `javascript.md`
JavaScript-specific review: ES2024+ features, async/await patterns, closure pitfalls, prototype chain issues, module patterns (ESM vs CJS), Node.js best practices (error handling, streams, event loop), framework-specific idioms (React hooks, Next.js SSR/SSG), bundling and tree-shaking.
- **Inspired by**: [airbnb/javascript](https://github.com/airbnb/javascript) — 147K+ stars, the definitive JavaScript style guide; [goldbergyoni/nodebestpractices](https://github.com/goldbergyoni/nodebestpractices) — 102K+ stars, comprehensive Node.js best practices

## Implementation Checklist

### Core Files
- [ ] Write `SKILL.md` with review type descriptions and build-prompt.py usage instructions
- [ ] Write `scripts/build-prompt.py` (assembles _shared.md + type-specific prompt)
- [ ] Write `prompts/_shared.md` (Process, Output Format, Constraints)
- [ ] Write `prompts/code-review.md` (Role + Checklist)
- [ ] Write `prompts/security.md`
- [ ] Write `prompts/plan-review.md`
- [ ] Write `prompts/architecture.md`
- [ ] Write `prompts/performance.md`
- [ ] Write `prompts/testing.md`
- [ ] Write `prompts/prompt-engineering.md`
- [ ] Write `prompts/typescript.md`
- [ ] Write `prompts/python.md`
- [ ] Write `prompts/java.md`
- [ ] Write `prompts/scala.md`
- [ ] Write `prompts/javascript.md`
- [ ] Write `REFERENCES.md` with attribution and licenses

### Verification
- [ ] Each type-specific prompt file has Role and Checklist sections only
- [ ] `_shared.md` has Process, Output Format, and Constraints sections
- [ ] `build-prompt.py` assembles complete prompt with all 5 sections in correct order
- [ ] `build-prompt.py` rejects unknown types and validates required sections
- [ ] Each prompt includes severity-ordered output format and actionable-findings constraint
- [ ] SKILL.md descriptions are concise (~50 tokens each)
- [ ] Test standalone usage: run `build-prompt.py <type>`, apply output to sample code
- [ ] Test with a sub-agent system: pass assembled file, verify sub-agent follows checklist
- [ ] Assembled prompt token counts are within 500-2000 token range

## References

All references are from official company sources, major open-source projects (1K+ stars), or the author's own projects.

### Official / Major Company Sources
- [google/eng-practices](https://github.com/google/eng-practices) — 20K+ stars, Google's engineering practices (code review + design doc guidelines)
- [google/error-prone](https://github.com/google/error-prone) — 7.1K stars, Google's Java static analysis tool
- [anthropics/claude-code-security-review](https://github.com/anthropics/claude-code-security-review) — Anthropic's AI-powered security review with semantic vulnerability detection
- [anthropics/skills](https://github.com/anthropics/skills) — Anthropic's official Agent Skills specification
- [spring-projects/spring-boot](https://github.com/spring-projects/spring-boot) — 76K+ stars, official Spring Boot project
- [scalacenter/scalafix](https://github.com/scalacenter/scalafix) — Scala Center official refactoring and linting tool

### Highly Popular Open Source (1K+ stars)
- [airbnb/javascript](https://github.com/airbnb/javascript) — 147K+ stars, the definitive JavaScript style guide
- [goldbergyoni/nodebestpractices](https://github.com/goldbergyoni/nodebestpractices) — 102K+ stars, comprehensive Node.js best practices
- [goldbergyoni/javascript-testing-best-practices](https://github.com/goldbergyoni/javascript-testing-best-practices) — 24K+ stars, comprehensive testing best practices (applicable beyond JS)
- [analysis-tools-dev/static-analysis](https://github.com/analysis-tools-dev/static-analysis) — 14K+ stars, curated list of static analysis tools for all languages
- [joelparkerhenderson/architecture-decision-record](https://github.com/joelparkerhenderson/architecture-decision-record) — 12K+ stars, ADR templates and decision review structure
- [joho/awesome-code-review](https://github.com/joho/awesome-code-review) — 4.9K stars, curated list of code review resources (articles, papers, tools)
- [baz-scm/awesome-reviewers](https://github.com/baz-scm/awesome-reviewers) — ready-to-use review prompts distilled from 8K+ real OSS PR comments
- [mehdihadeli/awesome-software-architecture](https://github.com/mehdihadeli/awesome-software-architecture) — curated list of architecture patterns, principles, and design resources
- [sanyuan0704/code-review-expert](https://github.com/sanyuan0704/code-review-expert) — 2.1K stars, Agent Skill for code review (SOLID, security, performance)
- [TheJambo/awesome-testing](https://github.com/TheJambo/awesome-testing) — 2.1K stars, curated list of testing resources and best practices
- [skillmatic-ai/awesome-agent-skills](https://github.com/skillmatic-ai/awesome-agent-skills) — curated agent skills directory

### Author's Own Projects
- **DocScope** `plan-review` workflow — 13-step implementation plan review (structural, logic, consistency, architecture, implementation clarity, error handling, security, performance, testing, edge cases, documentation)
- **DocScope** `review-staged` workflow — 6-category staged code review (best practices, logic/correctness, consistency, bug detection, performance, security) with custom criteria support
