#!/usr/bin/env python3
"""
Quick validation script for skills - minimal version.
No external dependencies required (no PyYAML).
"""

import re
import sys
from pathlib import Path

MAX_SKILL_NAME_LENGTH = 64
WARN_BODY_CHARS = 20_000
MAX_BODY_CHARS = 25_000
LARGE_BODY_NO_REFS_CHARS = 10_000


def parse_frontmatter_simple(raw_yaml: str) -> dict[str, str]:
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
            current_value_lines = [] if value in (">", "|", ">-", "|-") else [value]
        elif is_continuation and current_key is not None:
            current_value_lines.append(line.strip())

    # Flush last key
    if current_key is not None:
        result[current_key] = " ".join(current_value_lines).strip()

    return result


def parse_frontmatter(
    skill_path: str | Path,
) -> tuple[dict[str, str] | None, str | None, str | None]:
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
    body = content[match.end() :].strip()
    return frontmatter, body, None


def validate_keys(frontmatter: dict[str, str]) -> tuple[bool, str | None]:
    """Validate presence of required keys and absence of unknown keys."""
    allowed_properties = {
        "name",
        "description",
        "license",
        "allowed-tools",
        "metadata",
        "compatibility",
    }

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


def validate_name(name: str | None, skill_path: Path | None = None) -> tuple[bool, str | None]:
    """Validate skill name format and directory match."""
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

    if skill_path is not None:
        dir_name = Path(skill_path).resolve().name
        if name != dir_name:
            return (
                False,
                f"Name '{name}' does not match directory name '{dir_name}'",
            )

    return True, None


def validate_description(description: str | None) -> tuple[bool, str | None]:
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


def validate_body(body: str | None) -> tuple[bool, str | None]:
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
        line.strip()
        for line in body.splitlines()
        if line.strip() and not re.match(r"^#{1,6}\s", line)
    ]
    if len(non_heading_lines) < 2:
        return False, "SKILL.md body has no meaningful content beyond headings"

    # Check body character count (~4 chars/token, spec recommends < 5000 tokens)
    body_len = len(body)
    if body_len > MAX_BODY_CHARS:
        return (
            False,
            f"SKILL.md body is too long ({body_len:,} chars, ~{body_len // 4:,} tokens). "
            f"Maximum is {MAX_BODY_CHARS:,} chars. "
            f"Move detailed content to references/ files.",
        )

    return True, None


def validate_links(body: str, skill_path: Path) -> tuple[bool, str | None]:
    """Validate that internal markdown links point to existing files."""
    link_pattern = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
    broken = []

    # Strip fenced code blocks and inline code spans
    body_no_code = re.sub(r"^```.*?^```", "", body, flags=re.MULTILINE | re.DOTALL)
    body_no_code = re.sub(r"`[^`]+`", "", body_no_code)

    for _text, target in link_pattern.findall(body_no_code):
        # Skip external URLs and anchors
        if target.startswith(("http://", "https://", "#")):
            continue
        # Skip non-file URI schemes (attachment:, mailto:, etc.)
        if re.match(r"^[a-z]+:", target) and not target.startswith("./"):
            continue
        # Skip placeholder/example paths
        if any(p in target for p in ("path/to/", "example", "<", ">", "skill_dir")):
            continue
        target_path = skill_path / target
        if not target_path.exists():
            broken.append(target)

    if broken:
        listed = ", ".join(broken)
        return False, f"Broken internal link(s): {listed}"

    return True, None


def collect_warnings(body: str, skill_path: Path) -> list[str]:
    """Collect non-fatal warnings."""
    warnings = []
    body_len = len(body)

    if body_len > WARN_BODY_CHARS:
        warnings.append(
            f"SKILL.md body is {body_len:,} chars (~{body_len // 4:,} tokens). "
            f"Recommended max is {WARN_BODY_CHARS:,} chars (~5000 tokens). "
            f"Consider moving content to references/ files."
        )

    has_refs = (skill_path / "references").is_dir()
    has_scripts = (skill_path / "scripts").is_dir()
    if body_len > LARGE_BODY_NO_REFS_CHARS and not has_refs and not has_scripts:
        warnings.append(
            f"SKILL.md body is {body_len:,} chars but has no references/ or scripts/ directory. "
            f"Consider extracting detailed content into supporting files."
        )

    return warnings


def validate_skill(skill_path: str | Path) -> tuple[bool, str]:
    """Basic validation of a skill"""
    skill_path = Path(skill_path)
    frontmatter, body, error = parse_frontmatter(skill_path)
    if error:
        return False, error

    if frontmatter is None:
        return False, "Missing frontmatter"

    valid_keys, msg = validate_keys(frontmatter)
    if not valid_keys:
        assert msg is not None
        return False, msg

    valid_name, msg = validate_name(frontmatter.get("name"), skill_path)
    if not valid_name:
        assert msg is not None
        return False, msg

    valid_desc, msg = validate_description(frontmatter.get("description"))
    if not valid_desc:
        assert msg is not None
        return False, msg

    valid_body, msg = validate_body(body)
    if not valid_body:
        assert msg is not None
        return False, msg

    assert body is not None
    valid_links, msg = validate_links(body, skill_path)
    if not valid_links:
        assert msg is not None
        return False, msg

    warnings = collect_warnings(body, skill_path)
    if warnings:
        return True, "WARNING: " + "; ".join(warnings)

    return True, "Skill is valid!"


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 quick_validate.py <skill_directory_or_file> [...]")
        sys.exit(1)

    failed = False
    for arg in sys.argv[1:]:
        path = Path(arg)
        # If given a file path (e.g. from pre-commit), use its parent directory
        if path.is_file():
            path = path.parent
        valid, message = validate_skill(path)
        print(f"{path}: {message}")
        if not valid:
            failed = True
    sys.exit(1 if failed else 0)
