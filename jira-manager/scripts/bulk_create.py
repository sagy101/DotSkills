#!/usr/bin/env python3
"""
Batch-create Jira tickets from a structured markdown or JSON source file.

Supports idempotent resume via .jira-manifest.json — already-created tickets
are skipped. Creates in dependency order: epics -> stories -> subtasks.

Markdown source format:
    # Epic: My Epic Title
    Epic description here.
    Estimation: 15 days

    ## Story 1: Foundation
    Story description.
    Estimation: 2 days

    ### Subtask 1.1: Setup Environment
    Subtask description.
    Estimation: 0.5 days

JSON source format:
    {
      "epic": { "summary": "...", "description": "...", "story_points": 15 },
      "stories": [
        {
          "id": 1, "summary": "...", "description": "...", "story_points": 2,
          "subtasks": [
            { "id": "1.1", "summary": "...", "description": "...", "story_points": 0.5 }
          ]
        }
      ]
    }

Usage:
    python bulk_create.py --config .jira.json --source tickets.md --epic API-8291
    python bulk_create.py --config .jira.json --source tickets.json --epic API-8291
    python bulk_create.py --config .jira.json --source tickets.md --epic API-8291 --dry-run
    python bulk_create.py --config .jira.json --source tickets.md --epic API-8291 --rewrite-links
"""

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config_loader import add_config_arg, load_config, load_manifest, save_manifest
from field_resolver import resolve_issue_type
from jira_client import JiraClient
from link_rewriter import rewrite_links_to_git
from markup_converter import md_to_jira_markup


def _flush_section(current_lines, section, epic, story, subtask):
    """Assign accumulated lines to the current section's description."""
    desc = "\n".join(current_lines).strip()
    if section == "subtask" and subtask:
        subtask["description"] = desc
    elif section == "story" and story:
        story["description"] = desc
    elif section == "epic" and epic:
        epic["description"] = desc


def parse_markdown_source(text, pattern):
    """Parse structured markdown into epic/stories/subtasks hierarchy."""
    result = {"epic": None, "stories": []}
    story = None
    subtask = None
    section = None
    lines_buf = []

    for line in text.splitlines():
        epic_match = re.match(r"^#\s+(?:Epic:\s*)?(.+)$", line)
        if epic_match and not line.startswith("##"):
            _flush_section(lines_buf, section, result.get("epic"), story, subtask)
            lines_buf = []
            result["epic"] = {"summary": epic_match.group(1).strip()}
            section = "epic"
            continue

        story_match = re.match(r"^##\s+(?:Story\s+)?(\d+):\s*(.+)$", line)
        if story_match:
            _flush_section(lines_buf, section, result.get("epic"), story, subtask)
            lines_buf = []
            story = {
                "id": int(story_match.group(1)),
                "summary": story_match.group(2).strip(),
                "subtasks": [],
            }
            result["stories"].append(story)
            subtask = None
            section = "story"
            continue

        subtask_match = re.match(r"^###\s+(?:Subtask\s+)?(\d+\.\d+):\s*(.+)$", line)
        if subtask_match:
            _flush_section(lines_buf, section, result.get("epic"), story, subtask)
            lines_buf = []
            subtask = {
                "id": subtask_match.group(1),
                "summary": subtask_match.group(2).strip(),
            }
            if story:
                story["subtasks"].append(subtask)
            section = "subtask"
            continue

        if line.lstrip().startswith("#"):
            print(f"WARNING: Malformed header ignored: {line.strip()}", file=sys.stderr)

        lines_buf.append(line)

    _flush_section(lines_buf, section, result.get("epic"), story, subtask)
    _extract_points(result, pattern)
    return result


def _extract_estimation(item, pattern):
    """Extract story points from an item's description if it matches the pattern."""
    desc = item.get("description", "")
    if desc:
        match = re.search(pattern, desc)
        if match:
            item["story_points"] = float(match.group(1))


def _extract_points(data, pattern):
    """Extract story points from Estimation lines in descriptions."""
    if data.get("epic"):
        _extract_estimation(data["epic"], pattern)

    for story in data.get("stories", []):
        _extract_estimation(story, pattern)
        for subtask in story.get("subtasks", []):
            _extract_estimation(subtask, pattern)


def parse_json_source(text):
    """Parse JSON source into the same format as markdown parser."""
    return json.loads(text)


def load_source(source_path, config):
    """Load and parse a source file (markdown or JSON).

    Resolves relative paths against config.source_root if the path
    does not exist as-is.
    """
    path = Path(source_path)
    if not path.exists():
        path = config.source_root / source_path
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        return parse_json_source(text)
    return parse_markdown_source(text, config.estimation_pattern)


def _get_plan_row(item_id, item_sp, category, manifest):
    """Format a single plan row for story or subtask."""
    exists_entry = manifest.get(category, {}).get(item_id)
    
    action = "SKIP" if exists_entry else "CREATE"
    marker = f"[{exists_entry['key']}]" if exists_entry else ""
    sp = item_sp if item_sp is not None else "?"
    
    return action, sp, marker, bool(exists_entry)


def print_plan(data, epic_key, manifest):
    """Display the creation plan table."""
    lines = []
    lines.append("")
    lines.append("=" * 70)
    lines.append("  JIRA TICKET CREATION PLAN")
    lines.append("=" * 70)
    lines.append(f"  Epic: {epic_key}")
    lines.append("-" * 70)
    lines.append(f"  {'#':<6} {'Action':<8} {'SP':>5}  Summary")
    lines.append("-" * 70)

    creates = 0
    skips = 0

    for story in data.get("stories", []):
        sid = str(story["id"])
        action, sp, marker, exists = _get_plan_row(
            sid, story.get("story_points"), "stories", manifest
        )
        
        lines.append(f"  S{sid:<5} {action:<8} {sp:>5}  {story['summary']} {marker}")
        if exists:
            skips += 1
        else:
            creates += 1

        for subtask in story.get("subtasks", []):
            stid = str(subtask["id"])
            action, sp, marker, exists = _get_plan_row(
                stid, subtask.get("story_points"), "subtasks", manifest
            )
            
            lines.append(
                f"    {stid:<5} {action:<8} {sp:>5}  {subtask['summary']} {marker}"
            )
            if exists:
                skips += 1
            else:
                creates += 1

    lines.append("-" * 70)
    lines.append(f"  Creates: {creates}  |  Skips: {skips}  |  Total: {creates + skips}")
    lines.append("=" * 70)
    return "\n".join(lines)


def _build_issue_fields(config, item, type_name, epic_key=None, parent_key=None, rewrite_links=False, no_convert=False):
    """Build the Jira fields dict for a story or subtask."""
    fields = {
        "project": {"key": config.project_key},
        "summary": item["summary"],
        "issuetype": resolve_issue_type(config, type_name),
    }

    description = item.get("description", "")
    if rewrite_links and description:
        description = rewrite_links_to_git(description, config)
    if description and not no_convert:
        description = md_to_jira_markup(description)
    if description:
        fields["description"] = description

    if epic_key:
        epic_field = config.get_field_id("epic_link")
        if epic_field:
            fields[epic_field] = epic_key

    if parent_key:
        fields["parent"] = {"key": parent_key}

    sp_field = config.get_field_id("story_points")
    if sp_field and item.get("story_points") is not None:
        fields[sp_field] = item["story_points"]

    return fields


def _save_to_manifest(config, manifest, category, item_id, entry):
    """Save a created ticket to the manifest."""
    if category not in manifest:
        manifest[category] = {}
    manifest[category][item_id] = entry
    save_manifest(config, manifest)


def _create_story(story, sid, epic_key, config, client, manifest, rewrite_links, dry_run, no_convert=False):
    """Create a single story. Returns (story_key, created_bool)."""
    if manifest.get("stories", {}).get(sid):
        story_key = manifest["stories"][sid]["key"]
        print(f"  SKIP Story {sid}: already exists as {story_key}")
        return story_key, False

    fields = _build_issue_fields(
        config, story, "story", epic_key=epic_key, rewrite_links=rewrite_links, no_convert=no_convert
    )

    if dry_run:
        print(f"  DRY RUN — would create Story {sid}: {story['summary']}")
        return "DRY-RUN", True

    try:
        result = client.create_issue(fields)
    except Exception:
        print(f"FAILED to create Story {sid}")
        sys.exit(1)

    story_key = result["key"]
    print(f"  Created Story {sid}: {story_key} — {story['summary']}")

    entry = {"key": story_key, "summary": story["summary"]}
    if story.get("story_points") is not None:
        entry["story_points"] = story["story_points"]
    _save_to_manifest(config, manifest, "stories", sid, entry)
    return story_key, True


def _create_subtask(subtask, stid, story_key, config, client, manifest, rewrite_links, dry_run, no_convert=False):
    """Create a single subtask. Returns True if created, False if skipped."""
    if manifest.get("subtasks", {}).get(stid):
        print(f"    SKIP Subtask {stid}: already exists as {manifest['subtasks'][stid]['key']}")
        return False

    if story_key == "DRY-RUN":
        print(f"    DRY RUN — would create Subtask {stid}: {subtask['summary']}")
        return True

    fields = _build_issue_fields(
        config, subtask, "subtask", parent_key=story_key, rewrite_links=rewrite_links, no_convert=no_convert
    )

    if dry_run:
        print(f"    DRY RUN — would create Subtask {stid}: {subtask['summary']}")
        return True

    try:
        result = client.create_issue(fields)
    except Exception:
        print(f"FAILED to create Subtask {stid}")
        # Return False to indicate skip/failure, but we might want to exit?
        # The prompt said "If a create fails, stop and report the error".
        # So we should exit.
        sys.exit(1)

    st_key = result["key"]
    print(f"    Created Subtask {stid}: {st_key} — {subtask['summary']}")

    entry = {"key": st_key, "summary": subtask["summary"], "parent_key": story_key}
    if subtask.get("story_points") is not None:
        entry["story_points"] = subtask["story_points"]
    _save_to_manifest(config, manifest, "subtasks", stid, entry)
    return True


def execute_plan(data, epic_key, config, client, manifest, rewrite_links, dry_run, no_convert=False):
    """Create all tickets in dependency order."""
    created_count = 0
    skipped_count = 0

    for story in data.get("stories", []):
        sid = str(story["id"])
        story_key, was_created = _create_story(
            story, sid, epic_key, config, client, manifest, rewrite_links, dry_run, no_convert=no_convert
        )
        if was_created:
            created_count += 1
        else:
            skipped_count += 1

        for subtask in story.get("subtasks", []):
            stid = str(subtask["id"])
            was_created = _create_subtask(
                subtask, stid, story_key, config, client, manifest, rewrite_links, dry_run, no_convert=no_convert
            )
            if was_created:
                created_count += 1
            else:
                skipped_count += 1

    return created_count, skipped_count


def main():
    parser = argparse.ArgumentParser(description="Bulk-create Jira tickets")
    add_config_arg(parser)
    parser.add_argument("--source", required=True, help="Source file (.md or .json)")
    parser.add_argument("--epic", required=True, help="Epic key to link stories to")
    parser.add_argument(
        "--rewrite-links",
        action="store_true",
        help="Rewrite relative markdown links to git browse URLs",
    )
    parser.add_argument(
        "--no-convert",
        action="store_true",
        help="Skip Markdown to Jira wiki markup conversion for descriptions",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show plan without creating tickets",
    )
    args = parser.parse_args()

    config = load_config(args.config)
    manifest = load_manifest(config)
    data = load_source(args.source, config)

    # Show plan
    plan = print_plan(data, args.epic, manifest)
    print(plan)

    no_convert = getattr(args, 'no_convert', False)

    if args.dry_run:
        print("\nDRY RUN — no tickets created.")
        execute_plan(
            data, args.epic, config, None, manifest, args.rewrite_links, dry_run=True, no_convert=no_convert
        )
        return

    client = JiraClient(config)

    # Execute
    print("\nCreating tickets ...\n")
    created, skipped = execute_plan(
        data, args.epic, config, client, manifest, args.rewrite_links, dry_run=False, no_convert=no_convert
    )

    print(f"\nDone. Created: {created}, Skipped: {skipped}")
    print(f"Manifest: {config.manifest_file}")
    print(f"Epic: {client.browse_url(args.epic)}")


if __name__ == "__main__":
    main()
