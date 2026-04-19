#!/usr/bin/env python3
"""
Create a single Jira issue.

Supports named flags for common fields (--status, --priority, --assignee,
--component, --fix-version) and a generic --set flag for ANY discovered field.
Status is applied as a post-create transition.

Usage:
    python create_ticket.py --config .jira.json --type story --summary "My Story" --description "Details"
    python create_ticket.py --config .jira.json --type subtask --summary "Sub" --parent API-123
    python create_ticket.py --config .jira.json --type story --summary "S" --epic API-100 --story-points 3
    python create_ticket.py --config .jira.json --type story --summary "S" --status "In Progress"
    python create_ticket.py --config .jira.json --type story --summary "S" --set "priority=High"
    python create_ticket.py --config .jira.json --type story --summary "S" --description-file desc.md --rewrite-links
    python create_ticket.py --config .jira.json --type epic --summary "S" --copy-fields-from PROJ-100
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from field_resolver import (
    add_common_field_args,
    apply_extra_fields,
    apply_named_fields,
    apply_set_pairs,
    resolve_description_with_images,
    resolve_issue_type,
    resolve_sprint_id,
    validate_required_fields,
)
from jira_client import JiraAPIError, JiraClient
from jira_config_loader import JiraConfig, add_config_arg, load_config, load_manifest, save_manifest
from workflow_ops import handle_status_transition, upload_attachments


def _copy_custom_fields(
    fields: dict[str, Any],
    source_key: str,
    client: JiraClient,
    issue_type_id: str | None,
) -> None:
    """Copy custom fields from an existing issue into the fields dict.

    Only copies ``customfield_*`` fields that are on the target issue type's
    create screen (fetched via ``get_create_meta_for_type``).  Fields not on
    the screen are skipped automatically — no hardcoded skip lists needed.
    """
    screen_field_ids: set[str] | None = None
    if issue_type_id:
        try:
            meta_fields = client.get_create_meta_for_type(issue_type_id)
            screen_field_ids = {f.get("key", f.get("fieldId", "")) for f in meta_fields}
        except Exception:
            pass  # If createmeta fails, fall back to copying nothing

    source = client.get_issue(source_key)
    source_fields = source.get("fields", {})
    copied = []
    skipped = []
    for fid, value in source_fields.items():
        if fid in fields:
            continue
        if not fid.startswith("customfield_") or value is None:
            continue
        if screen_field_ids is not None and fid not in screen_field_ids:
            skipped.append(fid)
            continue
        fields[fid] = value
        copied.append(fid)
    if skipped:
        print(f"  Skipped {len(skipped)} fields not on create screen")
    if copied:
        print(f"  Copied {len(copied)} custom fields from {source_key}: {', '.join(copied)}")


def _extract_field_candidates(error_detail: str) -> list[str]:
    """Extract candidate field names from a Jira 400 error message."""
    candidates = [
        m.group(1).strip()
        for m in re.finditer(r"(?i)(?:fill out|provide|set)\s+([^.\"]+)", error_detail)
    ]
    candidates.extend(
        m.group(1).strip()
        for m in re.finditer(r"[\"']([^\"']+)[\"']\s+(?:is required|cannot be empty)", error_detail)
    )
    try:
        parsed = json.loads(error_detail)
        if isinstance(parsed, dict):
            candidates.extend(parsed.keys())
    except (json.JSONDecodeError, TypeError):
        pass
    return candidates


def _print_allowed_values(allowed: list[dict[str, Any]]) -> None:
    """Print a truncated list of allowed values for a field."""
    print("    Allowed values:", file=sys.stderr)
    for v in allowed[:10]:
        val = v.get("value") or v.get("name") or v.get("key", "")
        print(f"      - {val}", file=sys.stderr)
    if len(allowed) > 10:
        print(f"      ... and {len(allowed) - 10} more", file=sys.stderr)


def _print_field_fix_hint(fid: str, client: JiraClient, issue_type_id: str | None) -> None:
    """Print allowed values and a --fields fix hint for a single field."""
    if not issue_type_id:
        print(f'    Fix: add --fields \'{{"{fid}": {{"value": "<value>"}}}}\'', file=sys.stderr)
        return
    try:
        type_fields = client.get_create_meta_for_type(issue_type_id)
    except Exception:
        return
    for tf in type_fields:
        tf_key = tf.get("key", tf.get("fieldId", ""))
        if tf_key != fid:
            continue
        allowed = tf.get("allowedValues", [])
        if allowed:
            _print_allowed_values(allowed)
        example_val = '{"value": "<pick one>"}' if allowed else '"<value>"'
        print(f"    Fix: add --fields '{{\"{fid}\": {example_val}}}'", file=sys.stderr)
        break


def _check_field_on_screen(
    fid: str, client: JiraClient, issue_type_id: str | None
) -> tuple[bool, list[dict]]:
    """Check if a field is on the create screen and return its allowed values.

    Returns (is_on_screen, allowed_values).
    """
    if not issue_type_id:
        return False, []
    try:
        type_fields = client.get_create_meta_for_type(issue_type_id)
    except Exception:
        return False, []
    for tf in type_fields:
        tf_key = tf.get("key", tf.get("fieldId", ""))
        if tf_key == fid:
            return True, tf.get("allowedValues", [])
    return False, []


def _suggest_fix_for_field_error(
    error_detail: str,
    client: JiraClient,
    issue_type_id: str | None,
) -> None:
    """When create fails with a 400, try to identify the missing field and suggest a fix.

    Sorts matches so actionable fields (on the create screen with allowed values)
    appear first, and non-actionable fields are flagged with a warning.
    """
    candidates = _extract_field_candidates(error_detail)
    if not candidates:
        return

    all_fields = client.get_fields()

    actionable: list[tuple[dict, bool, list]] = []
    non_actionable: list[dict] = []

    for candidate in candidates:
        candidate_lower = candidate.lower()
        matches = [f for f in all_fields if candidate_lower in f.get("name", "").lower()]
        if not matches:
            non_actionable.append({"name": candidate, "id": "?"})
            continue
        for mf in matches:
            on_screen, allowed = _check_field_on_screen(mf["id"], client, issue_type_id)
            if on_screen:
                actionable.append((mf, on_screen, allowed))
            else:
                non_actionable.append(mf)

    print("\n--- Auto-diagnosis ---", file=sys.stderr)

    for mf, _on_screen, allowed in actionable:
        marker = " ★ Recommended" if allowed else ""
        print(f"  {mf['name']} ({mf['id']}){marker}", file=sys.stderr)
        _print_field_fix_hint(mf["id"], client, issue_type_id)

    for mf in non_actionable:
        fid = mf.get("id", "?")
        if fid == "?":
            print(f"  Could not find a field matching '{mf['name']}'.", file=sys.stderr)
        else:
            print(
                f"  {mf['name']} ({fid}) — not on create screen, likely not settable",
                file=sys.stderr,
            )

    print("---", file=sys.stderr)


def _add_epic_link(fields: dict[str, Any], args: argparse.Namespace, config: JiraConfig) -> None:
    """Add epic link field if --epic was provided."""
    if not args.epic:
        return
    epic_field = config.get_field_id("epic_link")
    if epic_field:
        fields[epic_field] = args.epic
    else:
        print(
            "WARNING: epic_link field not configured. Run discover_fields.py --apply to detect it.",
            file=sys.stderr,
        )


def build_fields(
    args: argparse.Namespace, config: JiraConfig, client: Any = None
) -> tuple[dict[str, Any], str | None, list[str]]:
    """Build the Jira fields dict from CLI arguments.

    Returns (fields_dict, status_value_or_None, description_image_paths).
    """
    fields = {
        "project": {"key": config.project_key},
        "summary": args.summary,
    }

    fields["issuetype"] = resolve_issue_type(config, args.type)

    # Description — also extracts local image paths for auto-attachment
    orig_desc = args.description
    if not args.description and not args.description_file:
        args.description = ""
    description, image_paths = resolve_description_with_images(args, config)
    args.description = orig_desc
    if description:
        fields["description"] = description

    # Parent (for subtasks)
    if args.parent:
        fields["parent"] = {"key": args.parent}

    _add_epic_link(fields, args, config)
    apply_named_fields(fields, args, config, client=client)
    status_from_set = apply_set_pairs(fields, args, config)
    apply_extra_fields(fields, args)

    return fields, status_from_set, image_paths


def _handle_post_create_sprint(
    args: argparse.Namespace, config: JiraConfig, client: JiraClient, key: str
) -> None:
    """Move the newly created issue to a sprint if --sprint was provided."""
    effective_sprint = getattr(args, "sprint", None)
    if not effective_sprint:
        return
    sprint_id, sprint_name = resolve_sprint_id(config, effective_sprint)
    if sprint_id is not None:
        try:
            client.move_issues_to_sprint(sprint_id, [key])
            print(f"  Moved {key} to sprint: {sprint_name} (id={sprint_id})")
        except Exception:
            print(f"  WARNING: Failed to move {key} to sprint {sprint_name}", file=sys.stderr)


def _update_manifest(config: JiraConfig, args: argparse.Namespace, key: str) -> None:
    """Update the manifest file with the newly created ticket."""
    manifest = load_manifest(config)
    category = "subtasks" if args.parent else "stories"
    if category not in manifest:
        manifest[category] = {}
    entry = {"key": key, "summary": args.summary}
    if args.story_points is not None:
        entry["story_points"] = args.story_points
    if args.parent:
        entry["parent_key"] = args.parent
    manifest[category][args.manifest_id] = entry
    save_manifest(config, manifest)
    print(f"  Manifest updated: {category}/{args.manifest_id} = {key}")


def _print_missing_fields_and_exit(missing: list[dict[str, str]], issue_type: str) -> None:
    """Print missing required fields and exit."""
    print(f"ERROR: Missing required fields for issue type '{issue_type}':", file=sys.stderr)
    for mf in missing:
        fid = mf["id"]
        fname = mf["name"]
        hint = f'--set "{fname}=<value>"'
        print(f"  - {fname} ({fid})  → {hint}", file=sys.stderr)
    print("\nRun discover_fields.py --apply to refresh required fields.", file=sys.stderr)
    sys.exit(1)


def _handle_dry_run(
    fields: dict[str, Any], effective_status: str | None, attachments: list[str] | None
) -> None:
    """Print dry-run preview and return."""
    print("DRY RUN — would create issue with fields:")
    print(json.dumps(fields, indent=2))
    if effective_status:
        print(f"DRY RUN — would transition to status: {effective_status}")
    if attachments:
        print(f"Attachments: {', '.join(attachments)}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a Jira issue")
    add_config_arg(parser)
    parser.add_argument(
        "--type",
        required=True,
        help="Issue type: story, subtask, bug, task, epic, or custom name",
    )
    parser.add_argument("--summary", required=True, help="Issue summary/title")
    parser.add_argument("--parent", help="Parent issue key (for subtasks)")
    parser.add_argument("--epic", help="Epic key to link to")
    parser.add_argument(
        "--copy-fields-from",
        metavar="ISSUE_KEY",
        help="Copy custom fields (e.g. QBR, team) from an existing issue. "
        "Only copies fields not already set via other flags.",
    )
    parser.add_argument(
        "--manifest-id",
        help="ID to track this ticket in the manifest (e.g. '1' for story 1, '1.1' for subtask)",
    )
    add_common_field_args(parser)
    args = parser.parse_args()

    config = load_config(args.config)
    client = JiraClient(config)
    fields, status_from_set, desc_image_paths = build_fields(args, config, client=client)
    effective_status = args.status or status_from_set

    missing = validate_required_fields(config, args.type, fields)
    if missing:
        _print_missing_fields_and_exit(missing, args.type)

    # Copy custom fields from a source issue (before dry-run so it shows in preview)
    if args.copy_fields_from:
        issue_type_id = fields.get("issuetype", {}).get("id")
        _copy_custom_fields(fields, args.copy_fields_from, client, issue_type_id)

    if args.dry_run:
        all_attachments = args.attachment + desc_image_paths
        _handle_dry_run(fields, effective_status, all_attachments)
        return

    try:
        result = client.create_issue(fields)
    except JiraAPIError as e:
        if e.status_code == 400:
            issue_type_id = fields.get("issuetype", {}).get("id")
            _suggest_fix_for_field_error(e.detail, client, issue_type_id)
        sys.exit(1)
    except Exception:
        sys.exit(1)

    key = result["key"]
    print(f"Created {key}: {args.summary}")
    print(f"  {client.browse_url(key)}")

    # Post-create transition
    if effective_status:
        handle_status_transition(client, key, effective_status, config, warn_only=True)

    _handle_post_create_sprint(args, config, client, key)

    if args.manifest_id:
        _update_manifest(config, args, key)

    upload_attachments(client, key, desc_image_paths + args.attachment)

    # Output JSON for script chaining
    print(json.dumps({"key": key, "self": result.get("self", "")}))


if __name__ == "__main__":
    main()
