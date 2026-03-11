#!/usr/bin/env python3
"""
Validate that sub-ticket story point estimates sum to their parent.

Checks both live Jira data and local source files (pre-creation validation).

Usage:
    python validate_estimates.py --config .jira.json --epic API-8291
    python validate_estimates.py --config .jira.json --story API-8301
    python validate_estimates.py --config .jira.json --source tickets.md
    python validate_estimates.py --config .jira.json --manifest
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config_loader import add_config_arg, load_config, load_manifest, normalize_args
from jira_client import JiraClient


def _get_story_points(fields, sp_field):
    """Extract story points from issue fields."""
    if not sp_field:
        return None
    val = fields.get(sp_field)
    if val is not None:
        return float(val)
    return None


def validate_epic_from_jira(client, config, epic_key):
    """Validate all stories under an epic and their subtasks."""
    sp_field = config.get_field_id("story_points")
    if not sp_field:
        print("ERROR: story_points field not configured in .jira.json")
        print("Run: discover_fields.py --config .jira.json --apply")
        sys.exit(1)

    # Fetch epic
    epic = client.get_issue(epic_key, fields=[sp_field, "summary"])
    epic_sp = _get_story_points(epic.get("fields", {}), sp_field)
    epic_summary = epic.get("fields", {}).get("summary", "?")

    # Fetch stories under epic
    stories = client.get_children(epic_key, fields=[sp_field, "summary", "subtasks"])

    results = []
    total_story_sp = 0.0

    for story in stories:
        story_key = story["key"]
        story_fields = story.get("fields", {})
        story_sp = _get_story_points(story_fields, sp_field)
        story_summary = story_fields.get("summary", "?")

        # Fetch subtasks
        subtasks = client.get_children(story_key, fields=[sp_field, "summary"])
        subtask_sum = sum(
            _get_story_points(st.get("fields", {}), sp_field) or 0
            for st in subtasks
        )

        if story_sp is not None:
            total_story_sp += story_sp

        results.append({
            "key": story_key,
            "summary": story_summary,
            "estimate": story_sp,
            "subtask_sum": subtask_sum,
            "subtask_count": len(subtasks),
            "match": _check_match(story_sp, subtask_sum, len(subtasks)),
        })

    return {
        "epic_key": epic_key,
        "epic_summary": epic_summary,
        "epic_estimate": epic_sp,
        "story_sum": total_story_sp,
        "stories": results,
    }


def validate_story_from_jira(client, config, story_key):
    """Validate subtasks of a single story."""
    sp_field = config.get_field_id("story_points")
    if not sp_field:
        print("ERROR: story_points field not configured in .jira.json")
        sys.exit(1)

    story = client.get_issue(story_key, fields=[sp_field, "summary"])
    story_sp = _get_story_points(story.get("fields", {}), sp_field)
    story_summary = story.get("fields", {}).get("summary", "?")

    subtasks = client.get_children(story_key, fields=[sp_field, "summary"])
    subtask_sum = sum(
        _get_story_points(st.get("fields", {}), sp_field) or 0
        for st in subtasks
    )

    return {
        "epic_key": None,
        "epic_summary": None,
        "epic_estimate": None,
        "story_sum": story_sp or 0,
        "stories": [{
            "key": story_key,
            "summary": story_summary,
            "estimate": story_sp,
            "subtask_sum": subtask_sum,
            "subtask_count": len(subtasks),
            "match": _check_match(story_sp, subtask_sum, len(subtasks)),
        }],
    }


def validate_from_source(source_path, config):
    """Validate estimates from a local source file (pre-creation)."""
    from bulk_create import load_source

    data = load_source(source_path, config)
    results = []
    total_story_sp = 0.0

    for story in data.get("stories", []):
        story_sp = story.get("story_points")
        subtask_sum = sum(
            st.get("story_points") or 0 for st in story.get("subtasks", [])
        )
        if story_sp is not None:
            total_story_sp += story_sp

        results.append({
            "key": f"S{story['id']}",
            "summary": story["summary"],
            "estimate": story_sp,
            "subtask_sum": subtask_sum,
            "subtask_count": len(story.get("subtasks", [])),
            "match": _check_match(story_sp, subtask_sum, len(story.get("subtasks", []))),
        })

    epic = data.get("epic", {}) or {}
    return {
        "epic_key": "SOURCE",
        "epic_summary": epic.get("summary", "?"),
        "epic_estimate": epic.get("story_points"),
        "story_sum": total_story_sp,
        "stories": results,
    }


def validate_from_manifest(config):
    """Validate estimates from the manifest file."""
    manifest = load_manifest(config)
    if not manifest:
        print("ERROR: No manifest found. Run bulk_create.py first.")
        sys.exit(1)

    stories = manifest.get("stories", {})
    subtasks = manifest.get("subtasks", {})
    results = []
    total_story_sp = 0.0

    for sid, sdata in sorted(stories.items()):
        story_sp = sdata.get("story_points")
        story_key = sdata.get("key", f"S{sid}")

        # Find subtasks belonging to this story
        story_subtasks = {
            stid: stdata for stid, stdata in subtasks.items()
            if stid.startswith(f"{sid}.")
        }
        subtask_sum = sum(
            st.get("story_points") or 0 for st in story_subtasks.values()
        )

        if story_sp is not None:
            total_story_sp += story_sp

        results.append({
            "key": story_key,
            "summary": sdata.get("summary", "?"),
            "estimate": story_sp,
            "subtask_sum": subtask_sum,
            "subtask_count": len(story_subtasks),
            "match": _check_match(story_sp, subtask_sum, len(story_subtasks)),
        })

    epic = manifest.get("epic", {})
    return {
        "epic_key": epic.get("key", "?"),
        "epic_summary": epic.get("summary", "?"),
        "epic_estimate": epic.get("story_points"),
        "story_sum": total_story_sp,
        "stories": results,
    }


def _check_match(parent_sp, child_sum, child_count):
    """Determine match status."""
    if child_count == 0:
        return "NO_CHILDREN"
    if parent_sp is None:
        return "NO_ESTIMATE"
    diff = parent_sp - child_sum
    if abs(diff) < 0.01:
        return "MATCH"
    return f"MISMATCH ({diff:+.1f})"


def _format_story_row(story):
    """Format a single story row for the report."""
    est = f"{story['estimate']:.1f}" if story["estimate"] is not None else "?"
    sub = f"{story['subtask_sum']:.1f}"
    ok = "MATCH" in story["match"] and "MIS" not in story["match"]
    marker = "OK" if ok else story["match"]
    is_mismatch = "MISMATCH" in story["match"]
    
    line = f"  {story['key']:<16} {est:>8} {sub:>9} {story['subtask_count']:>6}  {marker}"
    return line, is_mismatch


def format_report(data):
    """Format validation results as a table."""
    lines = []
    lines.append("")
    lines.append("=" * 72)
    lines.append("  ESTIMATION VALIDATION REPORT")
    lines.append("=" * 72)

    if data["epic_key"]:
        lines.append(f"  Epic: {data['epic_key']} — {data['epic_summary']}")
    lines.append("-" * 72)
    lines.append(f"  {'Story':<16} {'Estimate':>8} {'Sub Sum':>9} {'#Subs':>6}  Status")
    lines.append("-" * 72)

    mismatches = 0
    for s in data["stories"]:
        line, is_mismatch = _format_story_row(s)
        lines.append(line)
        if is_mismatch:
            mismatches += 1

    lines.append("-" * 72)

    # Epic-level summary
    if data["epic_estimate"] is not None:
        epic_est = f"{data['epic_estimate']:.1f}"
        story_sum = f"{data['story_sum']:.1f}"
        epic_diff = data["epic_estimate"] - data["story_sum"]
        epic_status = "OK" if abs(epic_diff) < 0.01 else f"MISMATCH ({epic_diff:+.1f})"
        if "MISMATCH" in epic_status:
            mismatches += 1
        lines.append(f"  {'Epic Total':<16} {epic_est:>8} {story_sum:>9}         {epic_status}")
        lines.append("-" * 72)

    if mismatches == 0:
        lines.append("  All estimates are consistent.")
    else:
        lines.append(f"  {mismatches} mismatch(es) found.")

    lines.append("=" * 72)
    return "\n".join(lines), mismatches


def main():
    parser = argparse.ArgumentParser(description="Validate estimation consistency")
    add_config_arg(parser)

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--epic", help="Validate all stories under an epic (live Jira)")
    group.add_argument("--story", help="Validate subtasks of a single story (live Jira)")
    group.add_argument("--source", help="Validate from local source file (.md or .json)")
    group.add_argument(
        "--manifest", action="store_true", help="Validate from .jira-manifest.json"
    )

    parser.add_argument(
        "--json", action="store_true", help="Output raw JSON instead of table"
    )
    args = parser.parse_args(normalize_args())

    config = load_config(args.config)

    if args.epic:
        client = JiraClient(config)
        data = validate_epic_from_jira(client, config, args.epic)
    elif args.story:
        client = JiraClient(config)
        data = validate_story_from_jira(client, config, args.story)
    elif args.source:
        data = validate_from_source(args.source, config)
    elif args.manifest:
        data = validate_from_manifest(config)

    if args.json:
        print(json.dumps(data, indent=2))
    else:
        report, mismatches = format_report(data)
        print(report)
        sys.exit(1 if mismatches > 0 else 0)


if __name__ == "__main__":
    main()
