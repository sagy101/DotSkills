#!/usr/bin/env python3
"""
Auto-detect Jira custom fields, issue types, and project metadata.

Calls the Jira REST API to discover field IDs and issue type IDs,
then outputs a suggested field_mappings + issue_types block for .jira.json.

Usage:
    python discover_fields.py --config .jira.json
    python discover_fields.py --config .jira.json --apply   # update config in-place
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config_loader import load_config
from jira_client import JiraClient


# Well-known custom field name patterns to detect
KNOWN_FIELDS = {
    "epic_link": ["Epic Link", "com.pyxis.greenhopper.jira:gh-epic-link"],
    "epic_name": ["Epic Name", "com.pyxis.greenhopper.jira:gh-epic-label"],
    "story_points": [
        "Story Points",
        "Story point estimate",
        "com.atlassian.jira.plugin.system.customfieldtypes:float",
    ],
    "sprint": ["Sprint", "com.pyxis.greenhopper.jira:gh-sprint"],
}


def _match_by_name(all_fields, mappings):
    """Pass 1: match fields by name (high confidence)."""
    for field_info in all_fields:
        fid = field_info.get("id", "")
        fname = field_info.get("name", "")
        for friendly_name, patterns in KNOWN_FIELDS.items():
            if friendly_name not in mappings and fname in patterns:
                mappings[friendly_name] = fid
                break


def _match_by_schema(all_fields, mappings):
    """Pass 2: fall back to schema type match for unresolved fields."""
    for field_info in all_fields:
        fid = field_info.get("id", "")
        fschema = field_info.get("schema", {}).get("custom", "")
        if not fschema:
            continue
        for friendly_name, patterns in KNOWN_FIELDS.items():
            if friendly_name not in mappings and fschema in patterns:
                fname = field_info.get("name", fid)
                print(
                    f"  WARNING: '{friendly_name}' matched by schema type to "
                    f"'{fname}' ({fid}). Verify this is correct.",
                    file=sys.stderr,
                )
                mappings[friendly_name] = fid
                break


def discover_fields(client: JiraClient) -> dict:
    """Discover custom field mappings.

    Uses a two-pass strategy: first match by field name (high confidence),
    then fall back to schema type match only for fields not yet resolved.
    This prevents mapping story_points to a random float custom field.
    """
    all_fields = client.get_fields()
    mappings = {}
    _match_by_name(all_fields, mappings)
    _match_by_schema(all_fields, mappings)
    return mappings


def discover_issue_types(client: JiraClient) -> dict:
    """Discover available issue types for the project."""
    try:
        project = client.get_project()
        types = {}
        for it in project.get("issueTypes", []):
            name = it["name"].lower().replace(" ", "_")
            types[name] = it["id"]
        return types
    except Exception as e:
        print(f"WARNING: Could not discover issue types: {e}", file=sys.stderr)
        return {}


def discover_create_meta(client: JiraClient) -> dict:
    """Discover required fields per issue type via createmeta."""
    meta = {}
    try:
        result = client.get_create_meta()
        for project in result.get("projects", []):
            for itype in project.get("issuetypes", []):
                type_name = itype["name"].lower().replace(" ", "_")
                required = []
                for fid, finfo in itype.get("fields", {}).items():
                    if finfo.get("required"):
                        required.append(
                            {"id": fid, "name": finfo.get("name", fid)}
                        )
                meta[type_name] = {
                    "id": itype["id"],
                    "required_fields": required,
                }
    except Exception as e:
        print(f"WARNING: createmeta not available: {e}", file=sys.stderr)
    return meta


def main():
    parser = argparse.ArgumentParser(description="Discover Jira project metadata")
    parser.add_argument("--config", required=True, help="Path to .jira.json")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Update .jira.json with discovered values",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Show all discovered fields"
    )
    args = parser.parse_args()

    config = load_config(args.config)
    client = JiraClient(config)

    # Test connection first
    print("Testing connection ...")
    if not client.test_connection():
        print("ERROR: Could not connect to Jira. Check credentials and URL.")
        sys.exit(1)
    print("Connection OK.\n")

    # Discover fields
    print("Discovering custom fields ...")
    field_mappings = discover_fields(client)
    for name, fid in field_mappings.items():
        print(f"  {name}: {fid}")
    if not field_mappings:
        print("  (no well-known custom fields found)")

    # Discover issue types
    print("\nDiscovering issue types ...")
    issue_types = discover_issue_types(client)
    for name, tid in sorted(issue_types.items()):
        print(f"  {name}: {tid}")
    if not issue_types:
        print("  (no issue types found)")

    # Discover create metadata
    if args.verbose:
        print("\nDiscovering required fields per issue type ...")
        meta = discover_create_meta(client)
        for type_name, info in sorted(meta.items()):
            required = [f"{f['name']} ({f['id']})" for f in info["required_fields"]]
            print(f"  {type_name} (id={info['id']}): {', '.join(required)}")

    # Build suggested config block
    suggestion = {}
    if field_mappings:
        suggestion["field_mappings"] = field_mappings
    if issue_types:
        suggestion["issue_types"] = issue_types

    if suggestion:
        print("\n--- Suggested .jira.json additions ---")
        print(json.dumps(suggestion, indent=2))

    # Apply if requested
    if args.apply:
        _apply_suggestion(args.config, suggestion)

    print("\nDone.")


def _apply_suggestion(config_path_str, suggestion):
    """Write discovered mappings into .jira.json."""
    if not suggestion:
        print("\nNothing to apply.")
        return

    config_path = Path(config_path_str)
    raw = json.loads(config_path.read_text(encoding="utf-8"))

    for key in ("field_mappings", "issue_types"):
        if key in suggestion:
            existing = raw.get(key, {})
            existing.update(suggestion[key])
            raw[key] = existing

    config_path.write_text(
        json.dumps(raw, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"\nUpdated {config_path}")


if __name__ == "__main__":
    main()
