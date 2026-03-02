# Documentation

Design documents and references for DotSkills.

## Design Documents

Each skill with non-trivial design decisions has a companion design document explaining **why** it exists and the **key decisions** behind it.

| Skill | Design Doc | Status |
|---|---|---|
| [codex-subagent](codex-subagent/codex-subagent-design.md) | Why, capabilities, wrapper architecture, collision confidence, super-review pattern, guardrails | Experimental |
| [confluence-publisher](confluence-publisher/confluence-publisher-design.md) | Why, capabilities, transformation pipeline, link rewriting, Mermaid strategy, surgical edit | Stable (v3.0) |
| [jira-manager](jira-manager/jira-manager-design.md) | Why, capabilities, discovery-first architecture, bulk update scoping, field discovery flow | Stable (v1.4) |

## Templates

| Template | Purpose |
|---|---|
| [skill-design-doc-template](templates/skill-design-doc-template.md) | Starting point for new skill design documents |

## Structure

```
docs/
├── README.md                          ← this file
├── codex-subagent/
│   ├── codex-subagent-design.md
│   └── codex-flags.md
├── confluence-publisher/
│   └── confluence-publisher-design.md
├── jira-manager/
│   └── jira-manager-design.md
└── templates/
    └── skill-design-doc-template.md
```
