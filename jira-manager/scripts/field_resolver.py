"""
Shared field resolution logic for jira-manager create and update scripts.

Provides:
- Catalog value lookup (priority, status, components, etc.)
- Generic --set field resolution
- Named field flag resolution (priority, assignee, component, fix-version)
- Story points, labels, description building
- Status transition resolution
- Argparse helpers for shared flags
- Attachment upload helper
"""

import json
import sys
from pathlib import Path

from link_rewriter import rewrite_links_to_git
from markup_converter import md_to_jira_markup


# ------------------------------------------------------------------
# Normalization
# ------------------------------------------------------------------

def normalize_key(name: str) -> str:
    """Normalize a display name to a lowercase snake_case key."""
    return name.strip().lower().replace(" ", "_").replace("-", "_")


# ------------------------------------------------------------------
# Catalog resolution
# ------------------------------------------------------------------

def resolve_catalog_value(config, catalog_key, user_value):
    """Look up a user-provided value in the field_catalog.

    Tries exact key match, then normalized match, then name match.
    Returns the catalog entry dict (with 'id' and 'name') or None.
    """
    catalog = config.field_catalog.get(catalog_key, {})
    values = catalog.get("values", {})
    if not values:
        return None

    normalized = normalize_key(user_value)

    # Exact key match
    if normalized in values:
        return values[normalized]

    # Match by 'name' field (case-insensitive)
    lower_val = user_value.strip().lower()
    for entry in values.values():
        if entry.get("name", "").lower() == lower_val:
            return entry

    return None


# ------------------------------------------------------------------
# --set field resolution
# ------------------------------------------------------------------

# Field types that take an object with 'name' key
_NAME_OBJECT_TYPES = {"priority", "resolution"}
# Field types that take an array of objects with 'id' or 'name' key
_ARRAY_OBJECT_TYPES = {"component", "version"}
# Catalog keys whose Jira field ID is an array field
_ARRAY_CATALOG_KEYS = {"components", "fix_versions"}


def _resolve_from_catalog(config, normalized, field_value, entry):
    """Resolve a field value using a top-level catalog entry.

    Returns (jira_field_id, jira_value, status_value) or None if not applicable.
    """
    catalog_type = entry.get("type", "")
    jira_field_id = entry.get("id", normalized)

    if catalog_type == "status":
        return None, None, field_value

    resolved = resolve_catalog_value(config, normalized, field_value)

    if catalog_type in _NAME_OBJECT_TYPES:
        name = resolved["name"] if resolved else field_value
        return jira_field_id, {"name": name}, None

    if catalog_type in _ARRAY_OBJECT_TYPES or normalized in _ARRAY_CATALOG_KEYS:
        if resolved:
            return jira_field_id, [{"id": resolved["id"]}], None
        return jira_field_id, [{"name": field_value}], None

    if resolved:
        return jira_field_id, {"id": resolved["id"]}, None
    return jira_field_id, field_value, None


def _resolve_from_fallbacks(config, normalized, field_name, field_value):
    """Try field_mappings, _fields_index, then use field_name as-is."""
    mapped_id = config.get_field_id(normalized)
    if mapped_id:
        try:
            return mapped_id, float(field_value), None
        except (ValueError, TypeError):
            return mapped_id, field_value, None

    fields_index = config.field_catalog.get("_fields_index", {})
    if normalized in fields_index:
        return fields_index[normalized]["id"], field_value, None

    return field_name, field_value, None


def resolve_set_field(config, field_name, field_value):
    """Resolve a --set field_name=value pair into a (jira_field_id, jira_value, status_value) tuple.

    Resolution order:
    1. Look up field_name in field_catalog (statuses, priorities, etc.)
    2. Look up field_name in field_mappings (well-known custom fields)
    3. Look up field_name in field_catalog._fields_index (all fields)
    4. Use field_name as-is (assume it is already a Jira field ID)

    Returns (jira_field_id, jira_value, None) for normal fields.
    Returns (None, None, status_value) when the field is 'status' (needs transition).
    """
    normalized = normalize_key(field_name)
    catalog = config.field_catalog

    if normalized in catalog:
        return _resolve_from_catalog(config, normalized, field_value, catalog[normalized])

    return _resolve_from_fallbacks(config, normalized, field_name, field_value)


# ------------------------------------------------------------------
# Named field helpers
# ------------------------------------------------------------------

def resolve_description(args, config):
    """Resolve and transform the description from CLI args.

    For create: defaults to empty string (returns None if empty).
    For update: returns None if neither --description nor --description-file given.
    """
    description = args.description
    if args.description_file:
        description = Path(args.description_file).read_text(encoding="utf-8")
    if description is None:
        return None
    if args.rewrite_links and description:
        description = rewrite_links_to_git(description, config)
    if description and not args.no_convert:
        description = md_to_jira_markup(description)
    return description


def apply_story_points(fields, args, config):
    """Add story_points to fields dict if provided."""
    if args.story_points is None:
        return
    sp_field = config.get_field_id("story_points")
    if sp_field:
        fields[sp_field] = args.story_points
    else:
        print(
            "WARNING: story_points field not configured. "
            "Run discover_fields.py --apply to detect it.",
            file=sys.stderr,
        )


def apply_labels(fields, args):
    """Add labels to fields dict if provided."""
    if args.labels:
        fields["labels"] = [l.strip() for l in args.labels.split(",")]


def apply_priority(fields, args, config):
    """Add priority to fields dict if provided."""
    if not args.priority:
        return
    resolved = resolve_catalog_value(config, "priority", args.priority)
    if resolved:
        fields["priority"] = {"name": resolved["name"]}
    else:
        fields["priority"] = {"name": args.priority}


def apply_assignee(fields, args):
    """Add assignee to fields dict if provided."""
    if args.assignee:
        fields["assignee"] = {"name": args.assignee}


def apply_components(fields, args, config):
    """Add components to fields dict if provided."""
    if not args.component:
        return
    components = []
    for comp_name in args.component:
        resolved = resolve_catalog_value(config, "components", comp_name)
        if resolved:
            components.append({"id": resolved["id"]})
        else:
            components.append({"name": comp_name})
    fields["components"] = components


def apply_fix_versions(fields, args, config):
    """Add fix versions to fields dict if provided."""
    if not args.fix_version:
        return
    versions = []
    for ver_name in args.fix_version:
        resolved = resolve_catalog_value(config, "fix_versions", ver_name)
        if resolved:
            versions.append({"id": resolved["id"]})
        else:
            versions.append({"name": ver_name})
    fields["fixVersions"] = versions


def resolve_sprint_id(config, sprint_value):
    """Resolve a sprint name or ID to a numeric sprint ID.

    Checks the field_catalog sprint values first, then tries int parse.
    Returns (sprint_id, sprint_name) or (None, None) if unresolvable.
    """
    resolved = resolve_catalog_value(config, "sprint", sprint_value)
    if resolved:
        return resolved["id"], resolved["name"]
    try:
        return int(sprint_value), sprint_value
    except (ValueError, TypeError):
        return None, None


def apply_named_fields(fields, args, config):
    """Apply all named field flags (priority, assignee, component, fix-version,
    story-points, labels) to the fields dict.

    Note: --sprint is NOT applied here because it uses the Agile API
    (move_issues_to_sprint), not the standard fields API. The caller
    must handle it separately after issue creation/update."""
    apply_story_points(fields, args, config)
    apply_labels(fields, args)
    apply_priority(fields, args, config)
    apply_assignee(fields, args)
    apply_components(fields, args, config)
    apply_fix_versions(fields, args, config)


def apply_set_pairs(fields, args, config):
    """Process --set pairs and apply to fields dict.

    Returns the status value if --set "status=..." was used, else None.
    """
    status_from_set = None
    if not args.set:
        return status_from_set

    for pair in args.set:
        if "=" not in pair:
            print(
                f"ERROR: --set value must be 'field=value', got: {pair}",
                file=sys.stderr,
            )
            sys.exit(1)
        fname, _, fval = pair.partition("=")
        jira_id, jira_val, status_val = resolve_set_field(
            config, fname.strip(), fval.strip()
        )
        if status_val is not None:
            status_from_set = status_val
        elif jira_id is not None:
            fields[jira_id] = jira_val

    return status_from_set


def apply_extra_fields(fields, args):
    """Merge --fields JSON into fields dict if provided."""
    if args.fields:
        extra = json.loads(args.fields)
        fields.update(extra)


# ------------------------------------------------------------------
# Transition resolution
# ------------------------------------------------------------------

def resolve_transition(client, issue_key, target_status, config):
    """Find the transition that leads to the target status.

    Returns (transition_id, transition_name, target_status_name) or None.
    """
    transitions = client.get_transitions(issue_key)
    normalized_target = normalize_key(target_status)

    # Try matching by transition target status name
    for t in transitions:
        to_status = t.get("to", {})
        status_name = to_status.get("name", "")
        if normalize_key(status_name) == normalized_target:
            return t["id"], t["name"], status_name

    # Also try matching by transition name itself
    for t in transitions:
        if normalize_key(t.get("name", "")) == normalized_target:
            to_status = t.get("to", {})
            return t["id"], t["name"], to_status.get("name", t["name"])

    # Try catalog lookup to get the canonical name, then retry
    resolved = resolve_catalog_value(config, "status", target_status)
    if resolved:
        canonical = resolved["name"]
        for t in transitions:
            to_status = t.get("to", {})
            if to_status.get("name", "") == canonical:
                return t["id"], t["name"], canonical

    return None


# ------------------------------------------------------------------
# Issue type resolution
# ------------------------------------------------------------------

def resolve_issue_type(config, type_name):
    """Resolve an issue type name to a Jira field dict ({id: ...} or {name: ...})."""
    type_id = config.get_issue_type_id(type_name)
    if type_id:
        return {"id": type_id}
    return {"name": type_name.capitalize()}


# ------------------------------------------------------------------
# Status transition execution
# ------------------------------------------------------------------

def handle_status_transition(client, issue_key, target_status, config, warn_only=False):
    """Resolve and execute a workflow transition.

    Args:
        warn_only: If True, print a warning instead of exiting on failure.
                   Useful for post-create transitions where the issue already exists.
    """
    result = resolve_transition(client, issue_key, target_status, config)
    if result is None:
        available = client.get_transitions(issue_key)
        names = [t["to"]["name"] for t in available if "to" in t]
        msg = (
            f"No transition found to status '{target_status}' for {issue_key}. "
            f"Available: {', '.join(names) if names else '(none)'}"
        )
        if warn_only:
            print(f"WARNING: {msg}", file=sys.stderr)
            return
        print(f"ERROR: {msg}", file=sys.stderr)
        sys.exit(1)

    transition_id, transition_name, target_name = result
    try:
        client.transition_issue(issue_key, transition_id)
        print(f"  Transitioned {issue_key} -> {target_name} (via '{transition_name}')")
    except Exception:
        if warn_only:
            print(f"  WARNING: Failed to transition {issue_key} to {target_name}", file=sys.stderr)
        else:
            sys.exit(1)


# ------------------------------------------------------------------
# Attachment helper
# ------------------------------------------------------------------

def upload_attachments(client, issue_key, file_paths):
    """Upload attachment files to an issue."""
    for fpath in file_paths:
        try:
            attached = client.add_attachment(issue_key, fpath)
            for a in attached:
                print(f"  Attached: {a.get('filename', fpath)}")
        except Exception:
            print(f"  WARNING: Failed to attach {fpath}", file=sys.stderr)


# ------------------------------------------------------------------
# Argparse helpers
# ------------------------------------------------------------------

def add_common_field_args(parser):
    """Add the shared field-related arguments to an argparse parser."""
    parser.add_argument("--description", help="Description text")
    parser.add_argument("--description-file", help="Read description from file")
    parser.add_argument("--story-points", type=float, help="Story points value")
    parser.add_argument("--labels", help="Comma-separated labels")
    parser.add_argument(
        "--status",
        help="Target status name (e.g. 'In Progress', 'Done'). "
             "Uses workflow transitions.",
    )
    parser.add_argument(
        "--priority",
        help="Priority name (e.g. 'High', 'Medium').",
    )
    parser.add_argument(
        "--assignee",
        help="Assignee username or email",
    )
    parser.add_argument(
        "--component",
        action="append",
        help="Component name (can be repeated for multiple).",
    )
    parser.add_argument(
        "--fix-version",
        action="append",
        help="Fix version name (can be repeated for multiple).",
    )
    parser.add_argument(
        "--sprint",
        help="Sprint name or ID. Resolved from field_catalog if discovered. "
             "Uses Agile API to move the issue into the sprint.",
    )
    parser.add_argument(
        "--set",
        action="append",
        metavar="FIELD=VALUE",
        help="Set any field by friendly name: --set 'priority=High'. "
             "Resolves via field_catalog. Can be repeated.",
    )
    parser.add_argument(
        "--fields", help='Extra fields as JSON: \'{"customfield_123": "val"}\''
    )
    parser.add_argument(
        "--rewrite-links",
        action="store_true",
        help="Rewrite relative markdown links to git browse URLs in description",
    )
    parser.add_argument(
        "--attachment",
        action="append",
        default=[],
        help="File to attach to the issue (can be repeated)",
    )
    parser.add_argument(
        "--no-convert",
        action="store_true",
        help="Skip Markdown to Jira wiki markup conversion for description",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making API calls",
    )
