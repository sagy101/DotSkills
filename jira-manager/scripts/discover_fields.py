#!/usr/bin/env python3
"""
Auto-detect Jira custom fields, issue types, and project metadata.

Calls the Jira REST API to discover field IDs and issue type IDs,
then outputs a suggested field_mappings + issue_types block for .jira.json.

Modes:
    Basic (default): Discovers well-known custom fields + issue types.
    Full  (--all):   Discovers ALL fields, statuses, priorities, components,
                     versions, resolutions, and allowed values. Stores a
                     comprehensive field_catalog in .jira.json for use by
                     create/update scripts.

Usage:
    python discover_fields.py --config .jira.json
    python discover_fields.py --config .jira.json --apply
    python discover_fields.py --config .jira.json --all --apply
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


# ------------------------------------------------------------------
# Full catalog discovery (--all)
# ------------------------------------------------------------------

def _normalize_key(name: str) -> str:
    """Normalize a display name to a lowercase snake_case key."""
    return name.strip().lower().replace(" ", "_").replace("-", "_")


def _discover_statuses(client: JiraClient) -> dict:
    """Discover all statuses available in the project, grouped by issue type."""
    catalog_entry = {
        "id": "status",
        "name": "Status",
        "type": "status",
        "note": "Status changes require workflow transitions. Use --status flag on update_ticket.py.",
        "values": {},
    }
    try:
        status_data = client.get_statuses_for_project()
        seen = {}
        for itype_block in status_data:
            for status in itype_block.get("statuses", []):
                sid = status["id"]
                sname = status["name"]
                key = _normalize_key(sname)
                if key not in seen:
                    seen[key] = {"id": sid, "name": sname}
        catalog_entry["values"] = {k: v for k, v in sorted(seen.items())}
    except Exception as e:
        print(f"  WARNING: Could not discover statuses: {e}", file=sys.stderr)
    return catalog_entry


def _discover_priorities(client: JiraClient) -> dict:
    """Discover all priorities."""
    catalog_entry = {
        "id": "priority",
        "name": "Priority",
        "type": "priority",
        "values": {},
    }
    try:
        priorities = client.get_priorities()
        for p in priorities:
            key = _normalize_key(p["name"])
            catalog_entry["values"][key] = {"id": p["id"], "name": p["name"]}
    except Exception as e:
        print(f"  WARNING: Could not discover priorities: {e}", file=sys.stderr)
    return catalog_entry


def _discover_resolutions(client: JiraClient) -> dict:
    """Discover all resolutions."""
    catalog_entry = {
        "id": "resolution",
        "name": "Resolution",
        "type": "resolution",
        "values": {},
    }
    try:
        resolutions = client.get_resolutions()
        for r in resolutions:
            key = _normalize_key(r["name"])
            catalog_entry["values"][key] = {"id": r["id"], "name": r["name"]}
    except Exception as e:
        print(f"  WARNING: Could not discover resolutions: {e}", file=sys.stderr)
    return catalog_entry


def _discover_components(client: JiraClient) -> dict:
    """Discover all project components."""
    catalog_entry = {
        "id": "components",
        "name": "Component/s",
        "type": "component",
        "values": {},
    }
    try:
        components = client.get_components()
        for c in components:
            key = _normalize_key(c["name"])
            catalog_entry["values"][key] = {"id": c["id"], "name": c["name"]}
    except Exception as e:
        print(f"  WARNING: Could not discover components: {e}", file=sys.stderr)
    return catalog_entry


def _discover_versions(client: JiraClient) -> dict:
    """Discover all project versions (fix versions / affects versions)."""
    catalog_entry = {
        "id": "fixVersions",
        "name": "Fix Version/s",
        "type": "version",
        "values": {},
    }
    try:
        versions = client.get_versions()
        for v in versions:
            key = _normalize_key(v["name"])
            catalog_entry["values"][key] = {
                "id": v["id"],
                "name": v["name"],
                "released": v.get("released", False),
                "archived": v.get("archived", False),
            }
    except Exception as e:
        print(f"  WARNING: Could not discover versions: {e}", file=sys.stderr)
    return catalog_entry


def _discover_all_fields(client: JiraClient) -> dict:
    """Discover all system + custom fields and build a catalog with allowed values."""
    all_fields = client.get_fields()
    catalog = {}

    for f in all_fields:
        fid = f.get("id", "")
        fname = f.get("name", "")
        custom = f.get("custom", False)
        schema = f.get("schema", {})
        schema_type = schema.get("type", "")
        schema_custom = schema.get("custom", "")

        key = _normalize_key(fname)
        entry = {
            "id": fid,
            "name": fname,
            "custom": custom,
            "schema_type": schema_type,
        }
        if schema_custom:
            entry["schema_custom"] = schema_custom

        catalog[key] = entry

    return catalog


def discover_full_catalog(client: JiraClient, verbose: bool = False) -> dict:
    """Run full discovery: fields, statuses, priorities, components, versions, resolutions."""
    catalog = {}

    # Statuses
    print("  Discovering statuses ...")
    status_entry = _discover_statuses(client)
    if status_entry["values"]:
        catalog["status"] = status_entry
        count = len(status_entry["values"])
        print(f"    Found {count} statuses: {', '.join(status_entry['values'].keys())}")
    else:
        print("    (none found)")

    # Priorities
    print("  Discovering priorities ...")
    priority_entry = _discover_priorities(client)
    if priority_entry["values"]:
        catalog["priority"] = priority_entry
        count = len(priority_entry["values"])
        print(f"    Found {count} priorities: {', '.join(priority_entry['values'].keys())}")
    else:
        print("    (none found)")

    # Resolutions
    print("  Discovering resolutions ...")
    resolution_entry = _discover_resolutions(client)
    if resolution_entry["values"]:
        catalog["resolution"] = resolution_entry
        count = len(resolution_entry["values"])
        print(f"    Found {count} resolutions: {', '.join(resolution_entry['values'].keys())}")
    else:
        print("    (none found)")

    # Components
    print("  Discovering components ...")
    component_entry = _discover_components(client)
    if component_entry["values"]:
        catalog["components"] = component_entry
        count = len(component_entry["values"])
        print(f"    Found {count} components: {', '.join(component_entry['values'].keys())}")
    else:
        print("    (none found)")

    # Versions
    print("  Discovering versions ...")
    version_entry = _discover_versions(client)
    if version_entry["values"]:
        catalog["fix_versions"] = version_entry
        count = len(version_entry["values"])
        active = [k for k, v in version_entry["values"].items() if not v.get("archived")]
        print(f"    Found {count} versions ({len(active)} active)")
    else:
        print("    (none found)")

    # All fields index (for --verbose or for reference)
    if verbose:
        print("  Discovering all fields (system + custom) ...")
        fields_index = _discover_all_fields(client)
        catalog["_fields_index"] = fields_index
        custom_count = sum(1 for v in fields_index.values() if v.get("custom"))
        system_count = len(fields_index) - custom_count
        print(f"    Found {system_count} system + {custom_count} custom fields")

    return catalog


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
    parser.add_argument(
        "--all",
        action="store_true",
        help="Full discovery: statuses, priorities, components, versions, "
             "resolutions, and all fields. Saves to field_catalog in config.",
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

    # Full catalog discovery
    field_catalog = {}
    if args.all:
        print("\nFull field catalog discovery ...")
        field_catalog = discover_full_catalog(client, verbose=args.verbose)

    # Build suggested config block
    suggestion = {}
    if field_mappings:
        suggestion["field_mappings"] = field_mappings
    if issue_types:
        suggestion["issue_types"] = issue_types
    if field_catalog:
        suggestion["field_catalog"] = field_catalog

    if suggestion:
        print("\n--- Suggested .jira.json additions ---")
        # For display, show a compact version (skip _fields_index)
        display = dict(suggestion)
        if "field_catalog" in display:
            display_catalog = {
                k: v for k, v in display["field_catalog"].items()
                if k != "_fields_index"
            }
            display["field_catalog"] = display_catalog
        print(json.dumps(display, indent=2))

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

    if "field_catalog" in suggestion:
        existing_catalog = raw.get("field_catalog", {})
        existing_catalog.update(suggestion["field_catalog"])
        raw["field_catalog"] = existing_catalog

    config_path.write_text(
        json.dumps(raw, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"\nUpdated {config_path}")


if __name__ == "__main__":
    main()
