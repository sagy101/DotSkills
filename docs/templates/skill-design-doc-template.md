# [Skill Name] — Design Document

> This document covers **why** this skill exists and the **key decisions** an implementer or reviewer needs to understand.

---

## Why This Skill Exists

<!-- 2-3 sentences: What problem does this solve? What's painful without it? -->

This skill gives **any SKILL.md-compatible agent** the ability to [core capability in one phrase].

<!-- Optional subsection if the skill wraps a specific tool and the choice needs justification: -->
<!-- ### Why [Tool] Specifically? -->
<!-- Comparison table or rationale for the underlying tool choice. -->

---

## Capabilities

<!-- Brief table of everything the skill can do. One row per capability. -->

| Capability | Description |
|---|---|
| **[Name]** | [One-line description] |
| **[Name]** | [One-line description] |

---

## Key Design Decisions

<!-- Numbered list. Each entry: bold title + dash + rationale (why this choice, not just what). -->

**1. [Decision title]** — [Why this approach was chosen and what alternatives were rejected or what it prevents.]

**2. [Decision title]** — [Rationale.]

---

## Approval Gates

<!-- Table of every action that touches external state and whether it needs user approval. -->

| Action | Approval Required | Mechanism |
|---|---|---|
| **[Action]** | Yes / No | [How: dry-run, plan table, confirmation flag, etc.] |

---

## Deep Dives

<!--
  This section explains HOW the skill's complex capabilities work in detail.
  Add one subsection (##) per capability that has non-obvious logic worth documenting.
  Skip simple CRUD — only document things a reviewer or contributor would need explained.

  Examples from existing skills:
  - codex-subagent: Decision Tree, Collision Confidence Framework, Super-Review Pattern, Guardrails
  - confluence-publisher: Cross-Page Link Rewriting, Mermaid Diagram Strategy
  - jira-manager: Bulk Update Scoping, Field Discovery Flow

  Each deep dive should cover:
  - What it does (brief)
  - How it works (numbered steps, tables, or flowcharts)
  - Edge cases or fallback behavior
  - How it connects to other parts of the skill
-->

### [Complex Capability Name]

<!-- What it does in one sentence. -->

<!-- How it works — numbered steps, decision table, or flowchart: -->
1. [Step]
2. [Step]
3. [Step]

<!-- Edge cases / fallback behavior: -->
<!-- e.g., "If X is unavailable, the skill falls back to Y — no hard failure." -->

### [Another Complex Capability]

<!-- Repeat pattern. Add as many subsections as needed. -->

---

## Guardrails

<!--
  Optional section — include if the skill has safety controls beyond approval gates.
  Use a table mapping guardrail → who enforces it → default behavior.
  Omit if approval gates already cover all safety concerns.
-->

| Guardrail | Enforced By | Default |
|---|---|---|
| [Guardrail] | [Script / Host agent / SKILL.md] | [Default behavior] |

---

## Risks at a Glance

<!-- Table of risks with severity and mitigation. Order by severity descending. -->

| Risk | Severity | Mitigation |
|---|---|---|
| [Risk] | Critical / High / Medium / Low | [How it's mitigated] |

---

## References

<!-- Links to APIs, libraries, specs, or related skills. -->

- **[Name]** — [What it is and why it's relevant]

## Status

<!-- One line: Experimental / Stable / Deprecated + version + any notable context. -->

**[Status] (v[X.Y])** — [Brief context.]
