#!/usr/bin/env python3
"""
Compare local ticket source spec against live Jira state.

Detects drift between local definitions and actual Jira tickets.
Compares: summary, description, story points.

Usage:
    python diff_tickets.py --config .jira.json --source tickets.md
    python diff_tickets.py --config .jira.json --manifest
    python diff_tickets.py --config .jira.json --manifest --summary
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config_loader import add_config_arg, load_config, load_manifest
from jira_client import JiraClient
from link_rewriter import rewrite_links_to_git
from markup_converter import md_to_jira_markup


def _normalize_text(text):
    """Normalize text for comparison (strip trailing whitespace, normalize newlines)."""
    if not text:
        return ""
    lines = text.replace("\r\n", "\n").splitlines()
    return "\n".join(line.rstrip() for line in lines).strip()


def _sp_differs(local_sp, remote_sp):
    """Check if story points differ, treating None vs a number as a difference."""
    if local_sp is None and remote_sp is None:
        return False
    if local_sp is None or remote_sp is None:
        return True
    return abs(float(local_sp) - float(remote_sp)) > 0.01


def _collect_manifest_entries(manifest):
    """Gather all stories and subtasks from the manifest into a flat list."""
    entries = []
    for category in ("stories", "subtasks"):
        for mid, mdata in sorted(manifest.get(category, {}).items()):
            entries.append((category, mid, mdata))
    return entries


def _diff_manifest_entry(client, mdata, mid, sp_field):
    """Diff a single manifest entry against live Jira. Returns a result dict."""
    key = mdata.get("key")
    if not key:
        return None

    fetch_fields = ["summary", "description"]
    if sp_field:
        fetch_fields.append(sp_field)

    try:
        issue = client.get_issue(key, fields=fetch_fields)
    except Exception:
        return {"id": mid, "key": key, "status": "NOT_FOUND"}

    fields = issue.get("fields", {})
    diffs = []

    local_summary = mdata.get("summary", "")
    remote_summary = fields.get("summary", "")
    if local_summary != remote_summary:
        diffs.append(("summary", local_summary, remote_summary))

    # Description: only compare if the manifest entry actually stores one
    if "description" in mdata:
        local_desc = _normalize_text(mdata.get("description", ""))
        remote_desc = _normalize_text(fields.get("description", ""))
        if local_desc != remote_desc:
            diffs.append(("description", local_desc[:200], remote_desc[:200]))

    if sp_field:
        local_sp = mdata.get("story_points")
        remote_sp = fields.get(sp_field)
        if _sp_differs(local_sp, remote_sp):
            diffs.append(("story_points", str(local_sp), str(remote_sp)))

    if diffs:
        return {"id": mid, "key": key, "status": "CHANGED", "diffs": diffs}
    return {"id": mid, "key": key, "status": "UNCHANGED"}


def diff_from_manifest(config, client):
    """Compare manifest entries against live Jira."""
    manifest = load_manifest(config)
    if not manifest:
        print("ERROR: No manifest found.")
        sys.exit(1)

    sp_field = config.get_field_id("story_points")
    results = []
    changed = 0
    unchanged = 0

    for _category, mid, mdata in _collect_manifest_entries(manifest):
        result = _diff_manifest_entry(client, mdata, mid, sp_field)
        if result is None:
            continue
        results.append(result)
        if result["status"] in ("CHANGED", "NOT_FOUND"):
            changed += 1
        else:
            unchanged += 1

    return results, changed, unchanged


def _diff_single_ticket(client, ticket_id, ticket_data, manifest_data, sp_field, config):
    """Diff a single ticket (story or subtask) against live Jira."""
    if not manifest_data:
        return {"id": ticket_id, "key": None, "status": "NEW"}

    key = manifest_data["key"]
    fetch_fields = ["summary", "description"]
    if sp_field:
        fetch_fields.append(sp_field)

    try:
        issue = client.get_issue(key, fields=fetch_fields)
    except Exception:
        return {"id": ticket_id, "key": key, "status": "NOT_FOUND"}

    fields = issue.get("fields", {})
    diffs = _compare_fields(ticket_data, fields, sp_field, config)

    if diffs:
        return {"id": ticket_id, "key": key, "status": "CHANGED", "diffs": diffs}
    return {"id": ticket_id, "key": key, "status": "UNCHANGED"}


def diff_from_source(config, client, source_path):
    """Compare source file entries against live Jira tickets."""
    from bulk_create import load_source

    data = load_source(source_path, config)
    manifest = load_manifest(config)
    sp_field = config.get_field_id("story_points")
    results = []
    changed = 0
    unchanged = 0

    for story in data.get("stories", []):
        sid = str(story["id"])
        mdata = manifest.get("stories", {}).get(sid)
        result = _diff_single_ticket(
            client, f"S{sid}", story, mdata, sp_field, config
        )
        results.append(result)
        if result["status"] in ("CHANGED", "NOT_FOUND", "NEW"):
            changed += 1
        else:
            unchanged += 1

        for subtask in story.get("subtasks", []):
            stid = str(subtask["id"])
            st_mdata = manifest.get("subtasks", {}).get(stid)
            st_result = _diff_single_ticket(
                client, stid, subtask, st_mdata, sp_field, config
            )
            results.append(st_result)
            if st_result["status"] in ("CHANGED", "NOT_FOUND", "NEW"):
                changed += 1
            else:
                unchanged += 1

    return results, changed, unchanged


def _compare_fields(local, remote_fields, sp_field, config):
    """Compare local ticket data against remote Jira fields."""
    diffs = []

    # Summary
    local_summary = local.get("summary", "")
    remote_summary = remote_fields.get("summary", "")
    if local_summary != remote_summary:
        diffs.append(("summary", local_summary, remote_summary))

    # Description — convert local markdown to Jira markup for fair comparison
    local_desc_raw = local.get("description", "")
    local_desc = _normalize_text(md_to_jira_markup(local_desc_raw) if local_desc_raw else "")
    local_desc_rewritten = _normalize_text(
        md_to_jira_markup(rewrite_links_to_git(local_desc_raw, config)) if local_desc_raw else ""
    )
    remote_desc = _normalize_text(remote_fields.get("description", ""))
    if local_desc != remote_desc and local_desc_rewritten != remote_desc:
        diffs.append(("description", local_desc[:200], remote_desc[:200]))

    # Story points
    if sp_field:
        local_sp = local.get("story_points")
        remote_sp = remote_fields.get(sp_field)
        if _sp_differs(local_sp, remote_sp):
            diffs.append(("story_points", str(local_sp), str(remote_sp)))

    return diffs


def format_report(results, changed, unchanged, summary_only=False):
    """Format diff results."""
    lines = []
    lines.append("")
    lines.append("=" * 70)
    lines.append("  JIRA DIFF REPORT")
    lines.append("=" * 70)
    lines.append(f"  {'ID':<10} {'Key':<14} {'Status':<12} Details")
    lines.append("-" * 70)

    for r in results:
        key = r.get("key") or "(new)"
        status = r["status"]
        detail = ""
        if r.get("diffs") and not summary_only:
            fields_changed = [d[0] for d in r["diffs"]]
            detail = f"changed: {', '.join(fields_changed)}"
        lines.append(f"  {r['id']:<10} {key:<14} {status:<12} {detail}")

        if not summary_only and r.get("diffs"):
            for field_name, local_val, remote_val in r["diffs"]:
                lines.append(f"    {field_name}:")
                lines.append(f"      local:  {local_val[:60]}")
                lines.append(f"      remote: {remote_val[:60]}")

    lines.append("-" * 70)
    lines.append(f"  Changed: {changed}  |  Unchanged: {unchanged}  |  Total: {changed + unchanged}")
    lines.append("=" * 70)
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Diff local vs Jira tickets")
    add_config_arg(parser)

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--manifest", action="store_true", help="Diff manifest entries against Jira")
    group.add_argument("--source", help="Diff source file against Jira")

    parser.add_argument("--epic", help="Epic key (currently unused, reserved for future filtering)")
    parser.add_argument(
        "--summary", action="store_true", help="Show counts only, no field details"
    )
    parser.add_argument("--json", action="store_true", help="Output raw JSON")
    args = parser.parse_args()

    config = load_config(args.config)
    client = JiraClient(config)

    if args.manifest:
        results, changed, unchanged = diff_from_manifest(config, client)
    elif args.source:
        results, changed, unchanged = diff_from_source(config, client, args.source)

    if args.json:
        print(json.dumps({"results": results, "changed": changed, "unchanged": unchanged}, indent=2))
    else:
        report = format_report(results, changed, unchanged, args.summary)
        print(report)

    # Exit code 1 if changes detected (like diff command)
    sys.exit(1 if changed > 0 else 0)


if __name__ == "__main__":
    main()
