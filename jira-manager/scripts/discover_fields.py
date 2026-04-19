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
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from jira_client import JiraClient
from jira_config_loader import JiraConfig, add_config_arg, find_config, load_config

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


def _match_by_name(all_fields: list[dict[str, Any]], mappings: dict[str, str]) -> None:
    """Pass 1: match fields by name (high confidence)."""
    for field_info in all_fields:
        fid = field_info.get("id", "")
        fname = field_info.get("name", "")
        for friendly_name, patterns in KNOWN_FIELDS.items():
            if friendly_name not in mappings and fname in patterns:
                mappings[friendly_name] = fid
                break


def _match_by_schema(all_fields: list[dict[str, Any]], mappings: dict[str, str]) -> None:
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


def discover_fields(client: JiraClient) -> dict[str, str]:
    """Discover custom field mappings.

    Uses a two-pass strategy: first match by field name (high confidence),
    then fall back to schema type match only for fields not yet resolved.
    This prevents mapping story_points to a random float custom field.
    """
    all_fields = client.get_fields()
    mappings: dict[str, str] = {}
    _match_by_name(all_fields, mappings)
    _match_by_schema(all_fields, mappings)
    return mappings


def discover_issue_types(client: JiraClient) -> dict[str, str]:
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


def discover_create_meta(client: JiraClient) -> dict[str, dict[str, Any]]:
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
                        required.append({"id": fid, "name": finfo.get("name", fid)})
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


def _discover_statuses(client: JiraClient) -> dict[str, Any]:
    """Discover all statuses available in the project, grouped by issue type."""
    catalog_entry: dict[str, Any] = {
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
        catalog_entry["values"] = dict(sorted(seen.items()))
    except Exception as e:
        print(f"  WARNING: Could not discover statuses: {e}", file=sys.stderr)
    return catalog_entry


def _discover_priorities(client: JiraClient) -> dict[str, Any]:
    """Discover all priorities."""
    catalog_entry: dict[str, Any] = {
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


def _discover_resolutions(client: JiraClient) -> dict[str, Any]:
    """Discover all resolutions."""
    catalog_entry: dict[str, Any] = {
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


def _discover_components(client: JiraClient) -> dict[str, Any]:
    """Discover all project components."""
    catalog_entry: dict[str, Any] = {
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


def _discover_versions(client: JiraClient) -> dict[str, Any]:
    """Discover all project versions (fix versions / affects versions)."""
    catalog_entry: dict[str, Any] = {
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


def _discover_all_fields(client: JiraClient) -> dict[str, dict[str, Any]]:
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


def _discover_sprints(client: JiraClient) -> dict[str, Any]:
    """Discover sprints via the Agile REST API (boards → sprints)."""
    catalog_entry: dict[str, Any] = {
        "id": "sprint",
        "name": "Sprint",
        "type": "sprint",
        "note": "Use --sprint flag on update_ticket.py or move_issues_to_sprint in jira_client.",
        "values": {},
    }
    try:
        boards = client.get_boards()
        if not boards:
            return catalog_entry
        for board in boards:
            bid = board["id"]
            try:
                sprints = client.get_sprints(bid, state="active,future")
            except Exception:
                continue
            for s in sprints:
                key = _normalize_key(s["name"])
                catalog_entry["values"][key] = {
                    "id": s["id"],
                    "name": s["name"],
                    "state": s.get("state", ""),
                    "board_id": bid,
                }
    except Exception as e:
        print(f"  WARNING: Could not discover sprints: {e}", file=sys.stderr)
    return catalog_entry


_NONE_FOUND = "    (none found)"

# Each tuple: (label, catalog_key, discover_fn)
_CATALOG_DISCOVERERS = [
    ("statuses", "status", _discover_statuses),
    ("priorities", "priority", _discover_priorities),
    ("resolutions", "resolution", _discover_resolutions),
    ("components", "components", _discover_components),
    ("versions", "fix_versions", _discover_versions),
    ("sprints (Agile API)", "sprint", _discover_sprints),
]


def discover_full_catalog(client: JiraClient, verbose: bool = False) -> dict[str, Any]:
    """Run full discovery: fields, statuses, priorities, components, versions, resolutions, sprints."""
    catalog = {}

    for label, catalog_key, discover_fn in _CATALOG_DISCOVERERS:
        print(f"  Discovering {label} ...")
        entry = discover_fn(client)
        if entry["values"]:
            catalog[catalog_key] = entry
            print(f"    Found {len(entry['values'])} {label}")
        else:
            print(_NONE_FOUND)

    if verbose:
        print("  Discovering all fields (system + custom) ...")
        fields_index = _discover_all_fields(client)
        catalog["_fields_index"] = fields_index
        custom_count = sum(1 for v in fields_index.values() if v.get("custom"))
        system_count = len(fields_index) - custom_count
        print(f"    Found {system_count} system + {custom_count} custom fields")

    return catalog


def _run_basic_discovery(
    client: JiraClient, verbose: bool
) -> tuple[dict[str, str], dict[str, str], dict[str, dict[str, Any]]]:
    """Run basic field and issue type discovery. Returns (field_mappings, issue_types, create_meta)."""
    print("Discovering custom fields ...")
    field_mappings = discover_fields(client)
    for name, fid in field_mappings.items():
        print(f"  {name}: {fid}")
    if not field_mappings:
        print("  (no well-known custom fields found)")

    print("\nDiscovering issue types ...")
    issue_types = discover_issue_types(client)
    for name, tid in sorted(issue_types.items()):
        print(f"  {name}: {tid}")
    if not issue_types:
        print("  (no issue types found)")

    print("\nDiscovering required fields per issue type ...")
    create_meta = discover_create_meta(client)
    for type_name, info in sorted(create_meta.items()):
        required = [f"{f['name']} ({f['id']})" for f in info["required_fields"]]
        print(f"  {type_name} (id={info['id']}): {', '.join(required)}")
    if not create_meta:
        print("  (createmeta not available)")

    if verbose and create_meta:
        print("\nDetailed required fields per issue type:")
        for type_name, info in sorted(create_meta.items()):
            print(f"  {type_name}:")
            for f in info["required_fields"]:
                print(f"    - {f['name']} ({f['id']})")

    return field_mappings, issue_types, create_meta


def _print_suggestion(suggestion: dict[str, Any]) -> None:
    """Print the suggestion block, excluding verbose _fields_index and create_meta."""
    display = dict(suggestion)
    if "field_catalog" in display:
        display["field_catalog"] = {
            k: v for k, v in display["field_catalog"].items() if k != "_fields_index"
        }
    display.pop("create_meta", None)
    print("\n--- Suggested .jira.json additions ---")
    print(json.dumps(display, indent=2))


def _run_transitions(client: JiraClient, issue_key: str) -> None:
    """List available workflow transitions for an issue."""
    try:
        transitions = client.get_transitions(issue_key)
    except Exception as e:
        print(f"ERROR: Could not fetch transitions for {issue_key}: {e}", file=sys.stderr)
        sys.exit(1)

    if not transitions:
        print(f"No transitions available for {issue_key}.")
        return

    print(f"Available transitions for {issue_key} ({len(transitions)} found):\n")
    print(f"  {'ID':<8} {'Name':<30} {'Target Status'}")
    print(f"  {'---':<8} {'---':<30} {'---'}")
    for t in transitions:
        tid = t.get("id", "")
        tname = t.get("name", "")
        to_status = t.get("to", {}).get("name", "")
        print(f"  {tid:<8} {tname:<30} {to_status}")


def _run_search(client: JiraClient, query: str) -> None:
    """Search all Jira fields by name substring (case-insensitive)."""
    all_fields = client.get_fields()
    query_lower = query.lower()
    matches = [f for f in all_fields if query_lower in f.get("name", "").lower()]
    if not matches:
        print(f"No fields matching '{query}'.")
        return
    print(f"Fields matching '{query}' ({len(matches)} found):\n")
    for f in sorted(matches, key=lambda x: x.get("name", "")):
        fid = f.get("id", "")
        fname = f.get("name", "")
        custom = "custom" if f.get("custom") else "system"
        schema_type = f.get("schema", {}).get("type", "")
        print(f"  {fname} ({fid})  [{custom}, {schema_type}]")


def _run_fields_for_type(client: JiraClient, config: JiraConfig, type_name: str) -> None:
    """List all available fields (with allowed values) for a given issue type."""
    type_id = None
    normalized = type_name.lower().replace(" ", "_")
    for name, tid in config.issue_types.items():
        if name == normalized:
            type_id = tid
            break
    if not type_id:
        print(
            f"ERROR: Unknown issue type '{type_name}'. "
            f"Known types: {', '.join(sorted(config.issue_types.keys()))}",
            file=sys.stderr,
        )
        print("Run discover_fields.py --apply to refresh issue types.", file=sys.stderr)
        sys.exit(1)

    print(f"Fields available for '{type_name}' (type id={type_id}):\n")
    try:
        fields = client.get_create_meta_for_type(type_id)
    except Exception as e:
        print(f"ERROR: Could not fetch fields for type: {e}", file=sys.stderr)
        sys.exit(1)

    for f in sorted(fields, key=lambda x: x.get("name", "")):
        fkey = f.get("key", f.get("fieldId", ""))
        fname = f.get("name", "")
        required = " [REQUIRED]" if f.get("required") else ""
        allowed = f.get("allowedValues", [])
        print(f"  {fname} ({fkey}){required}")
        if allowed:
            for v in allowed[:20]:
                val = v.get("value") or v.get("name") or v.get("key", "")
                vid = v.get("id", "")
                print(f"    - {val} (id: {vid})")
            if len(allowed) > 20:
                print(f"    ... and {len(allowed) - 20} more")


def main() -> None:
    parser = argparse.ArgumentParser(description="Discover Jira project metadata")
    add_config_arg(parser)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Update .jira.json with discovered values",
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="Show all discovered fields")
    parser.add_argument(
        "--all",
        action="store_true",
        help="Full discovery: statuses, priorities, components, versions, "
        "resolutions, and all fields. Saves to field_catalog in config.",
    )
    parser.add_argument(
        "--transitions",
        metavar="ISSUE_KEY",
        help="List available workflow transitions for an issue (e.g. --transitions PROJ-101)",
    )
    parser.add_argument(
        "--search",
        metavar="NAME",
        help="Search all Jira fields by name substring (case-insensitive)",
    )
    parser.add_argument(
        "--fields-for-type",
        metavar="TYPE",
        help="List all available fields and allowed values for an issue type "
        "(e.g. epic, story, bug)",
    )
    args = parser.parse_args()

    config = load_config(args.config)
    client = JiraClient(config)

    print("Testing connection ...")
    if not client.test_connection():
        print("ERROR: Could not connect to Jira. Check credentials and URL.")
        sys.exit(1)
    print("Connection OK.\n")

    if args.transitions:
        _run_transitions(client, args.transitions)
        return

    if args.search:
        _run_search(client, args.search)
        return

    if args.fields_for_type:
        _run_fields_for_type(client, config, args.fields_for_type)
        return

    field_mappings, issue_types, create_meta = _run_basic_discovery(client, args.verbose)

    field_catalog = {}
    if args.all:
        print("\nFull field catalog discovery ...")
        field_catalog = discover_full_catalog(client, verbose=args.verbose)

    suggestion: dict[str, Any] = {}
    if field_mappings:
        suggestion["field_mappings"] = field_mappings
    if issue_types:
        suggestion["issue_types"] = issue_types
    if create_meta:
        suggestion["create_meta"] = create_meta
    if field_catalog:
        suggestion["field_catalog"] = field_catalog

    if suggestion:
        _print_suggestion(suggestion)

    if args.apply:
        config_file = Path(args.config) if args.config else find_config()
        _apply_suggestion(config_file, suggestion)

    print("\nDone.")


def _apply_suggestion(config_path: Path, suggestion: dict[str, Any]) -> None:
    """Write discovered mappings into .jira.json."""
    if not suggestion:
        print("\nNothing to apply.")
        return
    raw = json.loads(config_path.read_text(encoding="utf-8"))

    for key in ("field_mappings", "issue_types", "create_meta"):
        if key in suggestion:
            existing = raw.get(key, {})
            existing.update(suggestion[key])
            raw[key] = existing

    if "field_catalog" in suggestion:
        existing_catalog = raw.get("field_catalog", {})
        existing_catalog.update(suggestion["field_catalog"])
        raw["field_catalog"] = existing_catalog

    config_path.write_text(json.dumps(raw, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"\nUpdated {config_path}")


if __name__ == "__main__":
    main()
