# Source File Format

Ticket definitions can be provided as **Markdown** or **JSON** files. Both formats support the same hierarchy: Epic -> Stories -> Subtasks.

## Markdown Format

Uses heading levels to define hierarchy. This is the primary format for agent interaction.

```markdown
# Epic: My Epic Title
Epic description here. Can be multiple paragraphs.

Estimation: 15 days

## Story 1: Foundation & Infrastructure
Story description here.

References:
- [Design doc](plan/design.md)
- [Architecture](plan/architecture.md)

Estimation: 2 days

### Subtask 1.1: Set Up Python Environment
Subtask description.

Estimation: 0.5 days

### Subtask 1.2: Build Generator Framework
Another subtask description.

Estimation: 0.5 days

## Story 2: Evaluation Framework
Second story description.

Estimation: 2 days

### Subtask 2.1: Set Up Langfuse
Subtask description.

Estimation: 0.5 days
```

### Heading rules

| Heading | Meaning | ID |
|---|---|---|
| `# Epic: Title` or `# Title` | Epic definition | — |
| `## Story N: Title` or `## N: Title` | Story with numeric ID N | N (integer) |
| `### Subtask N.M: Title` or `### N.M: Title` | Subtask with dotted ID | N.M (string) |

### Estimation extraction

Story points are extracted from `Estimation: X days` lines in descriptions. The regex pattern is configurable via `estimation_pattern` in `.jira.json`.

Default pattern: `Estimation:\s*([\d.]+)\s*days?`

Examples:
- `Estimation: 2 days` -> 2.0 SP
- `Estimation: 0.5 day` -> 0.5 SP
- `Estimation: 3.5 days` -> 3.5 SP

### Link rewriting

When `--rewrite-links` is used, relative markdown links in descriptions are converted to full git browse URLs:

- `[doc](plan/design.md)` -> `[doc](https://bitbucket.org/org/repo/src/main/plan/design.md)`

The git remote URL and branch are resolved from `.jira.json` config (or auto-detected from git).

## JSON Format

For programmatic use or precise control over all fields.

```json
{
  "epic": {
    "summary": "My Epic Title",
    "description": "Epic description",
    "story_points": 15
  },
  "stories": [
    {
      "id": 1,
      "summary": "Foundation & Infrastructure",
      "description": "Story description",
      "story_points": 2,
      "subtasks": [
        {
          "id": "1.1",
          "summary": "Set Up Python Environment",
          "description": "Subtask description",
          "story_points": 0.5
        },
        {
          "id": "1.2",
          "summary": "Build Generator Framework",
          "description": "Another subtask",
          "story_points": 0.5
        }
      ]
    },
    {
      "id": 2,
      "summary": "Evaluation Framework",
      "description": "Second story",
      "story_points": 2,
      "subtasks": [
        {
          "id": "2.1",
          "summary": "Set Up Langfuse",
          "description": "Subtask description",
          "story_points": 0.5
        }
      ]
    }
  ]
}
```

### JSON field reference

| Field | Required | Type | Description |
|---|---|---|---|
| `epic.summary` | Yes | string | Epic title |
| `epic.description` | No | string | Epic description |
| `epic.story_points` | No | number | Epic-level estimation |
| `stories[].id` | Yes | integer | Story numeric ID (used in manifest) |
| `stories[].summary` | Yes | string | Story title |
| `stories[].description` | No | string | Story description |
| `stories[].story_points` | No | number | Story estimation |
| `stories[].subtasks[].id` | Yes | string | Dotted subtask ID (e.g. "1.1") |
| `stories[].subtasks[].summary` | Yes | string | Subtask title |
| `stories[].subtasks[].description` | No | string | Subtask description |
| `stories[].subtasks[].story_points` | No | number | Subtask estimation |
