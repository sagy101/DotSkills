# Documentation

Design documents and references for DotSkills.

## Design Documents

Each skill with non-trivial design decisions has a companion design document explaining **why** it exists and the **key decisions** behind it.

| Skill | Design Doc | Status |
|---|---|---|
| [codex-subagent](codex-subagent/codex-subagent-design.md) | Why, capabilities, wrapper architecture, collision confidence, super-review pattern, guardrails | Experimental |
| [confluence-publisher](confluence-publisher/confluence-publisher-design.md) | Why, capabilities, transformation pipeline, link rewriting, Mermaid strategy, surgical edit, module structure | Stable (v3.1) |
| [bitbucket-manager](bitbucket-manager/bitbucket-manager-design.md) | Why, capabilities, zero-dep stdlib design, repo auto-detection, dry-run gates, config hierarchy | Stable (v1.0) |
| [jira-manager](jira-manager/jira-manager-design.md) | Why, capabilities, discovery-first architecture, bulk update scoping, field discovery flow, config discovery | Stable (v1.6) |
| [eks-pod-ops](eks-pod-ops/eks-pod-ops-design.md) | Why, secret redaction pipeline, exec blocklist, sidecar-aware container selection, Rancher Desktop workaround, module structure | Stable (v1.1) |
| [sbt-build-test](sbt-build-test/sbt-build-test-design.md) | Why, four-command agent interface, isolated Ivy home, hybrid discovery, batched SBT evaluation, workspace graph, auto-publish chains | Stable (v10.0) |
| [super-review](super-review/super-review-design.md) | Why, three-layer stack, backend-agnostic orchestration, grading rubric, synthesis workflow, preflight dependency validation | Stable (v1.0) |

## Templates

| Template | Purpose |
|---|---|
| [skill-design-doc-template](templates/skill-design-doc-template.md) | Starting point for new skill design documents |

## Structure

```
docs/
├── README.md                          ← this file
├── bitbucket-manager/
│   └── bitbucket-manager-design.md
├── codex-subagent/
│   ├── codex-subagent-design.md
│   └── codex-flags.md
├── confluence-publisher/
│   └── confluence-publisher-design.md
├── eks-pod-ops/
│   └── eks-pod-ops-design.md
├── jira-manager/
│   └── jira-manager-design.md
├── sbt-build-test/
│   └── sbt-build-test-design.md
├── super-review/
│   └── super-review-design.md
└── templates/
    └── skill-design-doc-template.md
```
