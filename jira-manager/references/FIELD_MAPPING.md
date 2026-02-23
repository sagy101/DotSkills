# Field Mapping Reference

Jira custom field IDs vary between instances. The jira-manager skill uses a `field_mappings` config block to abstract friendly names from instance-specific IDs.

## How it works

1. You configure `.jira.json` with friendly names mapping to Jira field IDs
2. Scripts use `config.get_field_id("epic_link")` to resolve the actual field ID
3. If a field isn't mapped, the script warns and skips that field

## Auto-discovery

Run the discovery script to auto-detect field mappings:

```bash
.jira-venv/bin/python <skill_dir>/scripts/discover_fields.py --config .jira.json --apply
```

The script calls `GET /rest/api/2/field` and matches known field names/schemas:

| Friendly Name | Detected By |
|---|---|
| `epic_link` | Name "Epic Link" or schema `com.pyxis.greenhopper.jira:gh-epic-link` |
| `epic_name` | Name "Epic Name" or schema `com.pyxis.greenhopper.jira:gh-epic-label` |
| `story_points` | Name "Story Points" / "Story point estimate" or float schema |
| `sprint` | Name "Sprint" or schema `com.pyxis.greenhopper.jira:gh-sprint` |

Use `--verbose` to see all fields and required fields per issue type:

```bash
.jira-venv/bin/python <skill_dir>/scripts/discover_fields.py --config .jira.json --verbose
```

## Manual configuration

If auto-discovery doesn't find your fields, you can configure them manually. Find the field ID by:

1. Opening a Jira issue in your browser
2. Appending `?expand=names` to the REST API call
3. Or using the Jira admin panel under Custom Fields

Then add to `.jira.json`:

```json
{
  "field_mappings": {
    "epic_link": "customfield_10632",
    "story_points": "customfield_10133",
    "my_custom_field": "customfield_12345"
  }
}
```

## Issue type mapping

Issue type IDs also vary. The discovery script detects available types:

```json
{
  "issue_types": {
    "epic": "10000",
    "story": "28",
    "sub-task": "10102",
    "bug": "10004",
    "task": "10001"
  }
}
```

Scripts resolve types by checking `issue_types` first (by lowercase name), then fall back to using the type name directly (e.g. `{"name": "Story"}`).

## Common field IDs

These are typical values, but **always verify with discover_fields.py** for your instance:

| Field | Typical ID | Notes |
|---|---|---|
| Epic Link | `customfield_10632` | Links story to epic |
| Story Points | `customfield_10133` | Numeric estimation field |
| Sprint | `customfield_10430` | Agile sprint assignment |
| Epic Name | `customfield_10631` | Name displayed on epic |

## Extending field support

The discovery script detects a fixed set of well-known fields. To add detection for additional fields:

1. Edit `discover_fields.py` `KNOWN_FIELDS` dict
2. Add the friendly name and the Jira field name / schema patterns to match
3. The `--apply` flag will include newly detected fields in `.jira.json`
