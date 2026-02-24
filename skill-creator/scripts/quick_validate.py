#!/usr/bin/env python3
"""
Quick validation script for skills - minimal version.
No external dependencies required (no PyYAML).
"""

import re
import sys
from pathlib import Path

MAX_SKILL_NAME_LENGTH = 64


def parse_frontmatter_simple(raw_yaml):
    """Parse simple YAML frontmatter without PyYAML.

    Handles flat key: value pairs and multi-line block scalars (>).
    Returns a dict of string keys to string values.
    """
    result = {}
    current_key = None
    current_value_lines = []

    for line in raw_yaml.splitlines():
        # Top-level key: value
        top_match = re.match(r"^([a-z][a-z0-9_-]*)\s*:\s*(.*)", line)
        # Indented continuation line (part of a block scalar or nested map)
        is_continuation = line.startswith(" ") or line.startswith("\t")

        if top_match and not is_continuation:
            # Flush previous key
            if current_key is not None:
                result[current_key] = " ".join(current_value_lines).strip()
            current_key = top_match.group(1)
            value = top_match.group(2).strip()
            # Block scalar indicator — value follows on next lines
            if value in (">", "|", ">-", "|-"):
                current_value_lines = []
            else:
                current_value_lines = [value]
        elif is_continuation and current_key is not None:
            current_value_lines.append(line.strip())

    # Flush last key
    if current_key is not None:
        result[current_key] = " ".join(current_value_lines).strip()

    return result


def parse_frontmatter(skill_path):
    """Parse YAML frontmatter from SKILL.md."""
    skill_md = Path(skill_path) / "SKILL.md"
    if not skill_md.exists():
        return None, None, "SKILL.md not found"

    content = skill_md.read_text()
    if not content.startswith("---"):
        return None, None, "No YAML frontmatter found"

    match = re.match(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
    if not match:
        return None, None, "Invalid frontmatter format"

    frontmatter = parse_frontmatter_simple(match.group(1))
    if not frontmatter:
        return None, None, "Frontmatter is empty"

    # Body is everything after the closing ---
    body = content[match.end():].strip()
    return frontmatter, body, None


def validate_keys(frontmatter):
    """Validate presence of required keys and absence of unknown keys."""
    allowed_properties = {"name", "description", "license", "allowed-tools", "metadata", "compatibility"}
    
    unexpected_keys = set(frontmatter.keys()) - allowed_properties
    if unexpected_keys:
        allowed = ", ".join(sorted(allowed_properties))
        unexpected = ", ".join(sorted(unexpected_keys))
        return (
            False,
            f"Unexpected key(s) in SKILL.md frontmatter: {unexpected}. Allowed properties are: {allowed}",
        )

    if "name" not in frontmatter:
        return False, "Missing 'name' in frontmatter"
    if "description" not in frontmatter:
        return False, "Missing 'description' in frontmatter"
    
    return True, None


def validate_name(name):
    """Validate skill name format."""
    if not isinstance(name, str):
        return False, f"Name must be a string, got {type(name).__name__}"
    
    name = name.strip()
    if not name:
        return False, "Name cannot be empty"

    if not re.match(r"^[a-z0-9-]+$", name):
        return (
            False,
            f"Name '{name}' should be hyphen-case (lowercase letters, digits, and hyphens only)",
        )
    if name.startswith("-") or name.endswith("-") or "--" in name:
        return (
            False,
            f"Name '{name}' cannot start/end with hyphen or contain consecutive hyphens",
        )
    if len(name) > MAX_SKILL_NAME_LENGTH:
        return (
            False,
            f"Name is too long ({len(name)} characters). "
            f"Maximum is {MAX_SKILL_NAME_LENGTH} characters.",
        )
    return True, None


def validate_description(description):
    """Validate description format and length."""
    if not isinstance(description, str):
        return False, f"Description must be a string, got {type(description).__name__}"
    
    description = description.strip()
    if not description:
        return False, "Description cannot be empty"

    if "<" in description or ">" in description:
        return False, "Description cannot contain angle brackets (< or >)"
    if len(description) > 1024:
        return (
            False,
            f"Description is too long ({len(description)} characters). Maximum is 1024 characters.",
        )
    return True, None


def validate_body(body):
    """Validate that the SKILL.md body has basic structure."""
    if not body:
        return False, "SKILL.md body is empty (no content after frontmatter)"

    headings = re.findall(r"^#{1,3}\s+.+", body, re.MULTILINE)
    if not headings:
        return False, "SKILL.md body has no headings (expected at least one # heading)"

    # Check for a title heading (# Title)
    title_match = re.search(r"^#\s+.+", body, re.MULTILINE)
    if not title_match:
        return False, "SKILL.md body is missing a title (expected '# Title' heading)"

    # Check body has meaningful content (not just headings)
    non_heading_lines = [
        line.strip() for line in body.splitlines()
        if line.strip() and not re.match(r"^#{1,6}\s", line)
    ]
    if len(non_heading_lines) < 2:
        return False, "SKILL.md body has no meaningful content beyond headings"

    return True, None


def validate_skill(skill_path):
    """Basic validation of a skill"""
    frontmatter, body, error = parse_frontmatter(skill_path)
    if error:
        return False, error

    valid_keys, error = validate_keys(frontmatter)
    if not valid_keys:
        return False, error

    valid_name, error = validate_name(frontmatter.get("name"))
    if not valid_name:
        return False, error

    valid_desc, error = validate_description(frontmatter.get("description"))
    if not valid_desc:
        return False, error

    valid_body, error = validate_body(body)
    if not valid_body:
        return False, error

    return True, "Skill is valid!"


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python3 quick_validate.py <skill_directory>")
        sys.exit(1)

    valid, message = validate_skill(sys.argv[1])
    print(message)
    sys.exit(0 if valid else 1)
