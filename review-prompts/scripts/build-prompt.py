#!/usr/bin/env python3
"""
Assembles a complete review prompt from _shared.md + a specific prompt file.

Usage:
    python scripts/build-prompt.py <review-type> [--output <file>]

Examples:
    python scripts/build-prompt.py security           # prints to stdout
    python scripts/build-prompt.py code-review -o /tmp/prompt.md  # writes to file

The assembled prompt has sections in this order:
    1. # Review Type + ## Role    (from prompts/<type>.md)
    2. ## Process                  (from prompts/_shared.md)
    3. ## Checklist                (from prompts/<type>.md)
    4. ## Output Format            (from prompts/_shared.md)
    5. ## Constraints              (from prompts/_shared.md)
"""

import argparse
import sys
from pathlib import Path


def extract_section(lines, heading):
    """Extract a ## section from lines: from the heading to the next ## or EOF."""
    result = []
    capturing = False
    for line in lines:
        if line.rstrip() == heading:
            capturing = True
            result.append(line)
            continue
        if capturing and line.startswith("## "):
            break
        if capturing:
            result.append(line)
    return result


def extract_up_to(lines, heading):
    """Extract everything from start up to (but not including) a ## heading."""
    result = []
    for line in lines:
        if line.rstrip() == heading:
            break
        result.append(line)
    return result


def extract_from(lines, heading):
    """Extract from a ## heading to end of file."""
    result = []
    capturing = False
    for line in lines:
        if line.rstrip() == heading:
            capturing = True
        if capturing:
            result.append(line)
    return result


def list_types(prompts_dir):
    """List available review types."""
    types = []
    for f in sorted(prompts_dir.glob("*.md")):
        if f.name.startswith("_"):
            continue
        types.append(f.stem)
    return types


def build_prompt(prompts_dir, review_type):
    """Assemble the complete prompt."""
    available = list_types(prompts_dir)
    if review_type not in available:
        print(f"Error: Unknown review type: {review_type}", file=sys.stderr)
        print(f"Available types: {', '.join(available)}", file=sys.stderr)
        sys.exit(1)

    specific_file = prompts_dir / f"{review_type}.md"
    shared_file = prompts_dir / "_shared.md"

    if not shared_file.exists():
        print(f"Error: Shared file not found: {shared_file}", file=sys.stderr)
        sys.exit(1)

    specific_lines = specific_file.read_text(encoding="utf-8").splitlines(keepends=True)
    shared_lines = shared_file.read_text(encoding="utf-8").splitlines(keepends=True)

    role = extract_up_to(specific_lines, "## Checklist")
    process = extract_section(shared_lines, "## Process")
    checklist = extract_from(specific_lines, "## Checklist")
    output_fmt = extract_section(shared_lines, "## Output Format")
    constraints = extract_section(shared_lines, "## Constraints")

    missing = []
    if not role:
        missing.append("Role (content before ## Checklist)")
    if not process:
        missing.append("## Process (in _shared.md)")
    if not checklist:
        missing.append("## Checklist")
    if not output_fmt:
        missing.append("## Output Format (in _shared.md)")
    if not constraints:
        missing.append("## Constraints (in _shared.md)")
    if missing:
        print(f"Error: Missing required sections in {review_type}:", file=sys.stderr)
        for m in missing:
            print(f"  - {m}", file=sys.stderr)
        sys.exit(1)

    parts = []
    parts.extend(role)
    parts.extend(process)
    parts.append("\n")
    parts.extend(checklist)
    parts.append("\n")
    parts.extend(output_fmt)
    parts.append("\n")
    parts.extend(constraints)

    return "".join(parts)


def main():
    parser = argparse.ArgumentParser(
        description="Assemble a complete review prompt from shared + specific parts."
    )
    parser.add_argument(
        "review_type",
        nargs="?",
        help="Review type (e.g. security, code-review, performance)",
    )
    parser.add_argument(
        "-o", "--output",
        help="Write assembled prompt to a file instead of stdout",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List available review types",
    )
    args = parser.parse_args()

    script_dir = Path(__file__).resolve().parent
    prompts_dir = script_dir.parent / "prompts"

    if args.list:
        for t in list_types(prompts_dir):
            print(t)
        return

    if not args.review_type:
        parser.error("review_type is required (use --list to see available types)")

    result = build_prompt(prompts_dir, args.review_type)

    if args.output:
        out_path = Path(args.output)
        out_path.write_text(result, encoding="utf-8")
        print(out_path)
    else:
        print(result, end="")


if __name__ == "__main__":
    main()
