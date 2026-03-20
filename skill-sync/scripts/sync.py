#!/usr/bin/env python3
"""
skill-sync — Sync Agent Skills to IDE skill directories.

Discovers skills (directories containing SKILL.md) from a source repo and
copies them to the user-level and/or project-level skill directories of
supported IDEs (Windsurf, Claude Code, Cursor, Codex).

OS-agnostic: uses pathlib throughout, works on macOS, Linux, and Windows.

Usage:
    python sync.py --source ~/dotskills --level user --targets all
    python sync.py --source ~/dotskills --level project --project /my/proj
    python sync.py --source ~/dotskills --level both --project /my/proj
    python sync.py --detect  # Just print detected IDEs and paths
"""

import argparse
import fnmatch
import json
import platform
import shutil
import sys
from pathlib import Path
from typing import TypedDict

# ---------------------------------------------------------------------------
# IDE definitions
# ---------------------------------------------------------------------------

IDES = {
    "windsurf": {
        "name": "Windsurf",
        "user_dir": ".codeium/windsurf/skills",
        "project_dir": ".windsurf/skills",
    },
    "claude": {
        "name": "Claude Code",
        "user_dir": ".claude/skills",
        "project_dir": ".claude/skills",
    },
    "cursor": {
        "name": "Cursor",
        "user_dir": ".cursor/skills",
        "project_dir": ".cursor/skills",
    },
    "codex": {
        "name": "Codex",
        "user_dir": ".codex/skills",
        "project_dir": ".codex/skills",
    },
    "gemini": {
        "name": "Gemini CLI",
        "user_dir": ".gemini/skills",
        "project_dir": ".gemini/skills",
    },
    "antigravity": {
        "name": "Antigravity",
        "user_dir": ".gemini/antigravity/skills",
        "project_dir": ".agent/skills",
    },
}

# Minimal always-excluded (even without .skillignore)
_ALWAYS_EXCLUDE = {".git"}


def load_skillignore(source: Path) -> list[str]:
    """Load ignore patterns from .skillignore file.

    Supports glob patterns (e.g. *-venv/, *.pyc, __pycache__/).
    Lines starting with # are comments. Trailing slashes are stripped.
    """
    ignorefile = source / ".skillignore"
    if not ignorefile.is_file():
        return []
    patterns = []
    for line in ignorefile.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        patterns.append(line.rstrip("/"))
    return patterns


def _matches_ignore(name: str, patterns: list[str]) -> bool:
    """Check if a file/directory name matches any ignore pattern."""
    if name in _ALWAYS_EXCLUDE:
        return True
    return any(fnmatch.fnmatch(name, p) for p in patterns)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def discover_skills(source: Path, patterns: list[str]) -> list[Path]:
    """Find all skill directories (containing SKILL.md) under source."""
    skills = []
    for child in sorted(source.iterdir()):
        if not child.is_dir():
            continue
        if child.name.startswith(".") or _matches_ignore(child.name, patterns):
            continue
        if (child / "SKILL.md").exists():
            skills.append(child)
    return skills


def _resolve_ide_paths(
    info: dict[str, str],
    level: str,
    home: Path,
    project: Path | None,
) -> dict[str, str | Path | None] | None:
    """Resolve user/project paths for a single IDE entry. Returns None if not detected."""
    user_path = home / info["user_dir"]
    user_ok = user_path.parent.exists() and level in ("user", "both")

    project_path = (project / info["project_dir"]) if project else None
    project_ok = (
        project_path is not None and project_path.parent.exists() and level in ("project", "both")
    )

    if not user_ok and not project_ok:
        return None

    return {
        "name": info["name"],
        "user_path": user_path if user_ok else None,
        "project_path": project_path if project_ok else None,
    }


def detect_ides(level: str, project: Path | None = None) -> dict[str, dict[str, str | Path | None]]:
    """Detect which IDEs have skill directories present.

    Returns a dict of ide_key -> {name, user_path, project_path}.
    A path is included if the parent directory exists (e.g. ~/.codeium/windsurf/).
    """
    home = Path.home()
    detected = {}
    for key, info in IDES.items():
        result = _resolve_ide_paths(info, level, home, project)
        if result:
            detected[key] = result
    return detected


def copy_skill(
    skill_dir: Path, target_dir: Path, patterns: list[str], dry_run: bool = False
) -> int:
    """Copy a single skill directory to target, returning files copied."""
    dest = target_dir / skill_dir.name
    if dry_run:
        print(f"    [dry-run] {skill_dir.name}/ -> {dest}")
        return 0

    if dest.exists():
        shutil.rmtree(dest)

    def _ignore(directory: str, contents: list[str]) -> set[str]:
        return {item for item in contents if _matches_ignore(item, patterns)}

    shutil.copytree(skill_dir, dest, ignore=_ignore)
    return sum(1 for _ in dest.rglob("*") if _.is_file())


def _sync_to_target(
    target_path: Path,
    label: str,
    ide_name: str,
    skills: list[Path],
    patterns: list[str],
    dry_run: bool,
) -> tuple[int, int]:
    """Sync all skills to a single target path. Returns (synced_count, file_count)."""
    print(f"\n  {ide_name} ({label}): {target_path}")
    if not dry_run:
        target_path.mkdir(parents=True, exist_ok=True)

    synced, files = 0, 0
    for skill in skills:
        n = copy_skill(skill, target_path, patterns, dry_run=dry_run)
        synced += 1
        files += n
        if not dry_run:
            print(f"    {skill.name}/ ({n} files)")
    return synced, files


class _SyncStats(TypedDict):
    name: str
    synced: int
    files: int
    paths: list[str]


def sync_skills(
    skills: list[Path],
    detected_ides: dict[str, dict[str, str | Path | None]],
    targets: list[str],
    patterns: list[str],
    dry_run: bool = False,
) -> dict[str, _SyncStats]:
    """Sync skills to all target IDE directories. Returns summary stats."""
    stats: dict[str, _SyncStats] = {}
    for ide_key in targets:
        if ide_key not in detected_ides:
            continue
        ide = detected_ides[ide_key]
        stats[ide_key] = {"name": str(ide["name"]), "synced": 0, "files": 0, "paths": []}

        for label in ("user", "project"):
            target_path = ide.get(f"{label}_path")
            if not target_path:
                continue
            tp = Path(target_path) if not isinstance(target_path, Path) else target_path
            s, f = _sync_to_target(tp, label, str(ide["name"]), skills, patterns, dry_run)
            stats[ide_key]["synced"] += s
            stats[ide_key]["files"] += f
            stats[ide_key]["paths"].append(str(target_path))

    return stats


# ---------------------------------------------------------------------------
# Settings sync — whitelist config for Claude Code and Windsurf
# ---------------------------------------------------------------------------

# PermissionRequest hook entry to inject into Claude Code settings.json
_CLAUDE_HOOK_ENTRY = {
    "matcher": "Bash",
    "hooks": [
        {
            "type": "command",
            "command": "$CLAUDE_PROJECT_DIR/.claude/hooks/command-whitelist.sh",
        }
    ],
}


def _sync_claude_settings(source: Path, target_claude_dir: Path, dry_run: bool) -> bool:
    """Merge the command-whitelist hook into a Claude Code settings.json.

    Copies the hook script and injects the PermissionRequest entry into
    settings.json without overwriting any existing keys.
    Returns True if changes were made (or would be made in dry-run).
    """
    hook_src = source / ".claude" / "hooks" / "command-whitelist.sh"
    if not hook_src.is_file():
        print(f"    [warn] hook script not found: {hook_src}")
        return False

    hook_dst = target_claude_dir / "hooks" / "command-whitelist.sh"
    settings_dst = target_claude_dir / "settings.json"

    if dry_run:
        print(f"    [dry-run] copy {hook_src.name} -> {hook_dst}")
        print(f"    [dry-run] merge PermissionRequest hook -> {settings_dst}")
        return True

    # Copy hook script
    hook_dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(hook_src, hook_dst)
    hook_dst.chmod(0o755)

    # Merge hook entry into settings.json
    settings: dict = {}
    if settings_dst.is_file():
        try:
            settings = json.loads(settings_dst.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass

    hooks = settings.setdefault("hooks", {})
    existing = hooks.setdefault("PermissionRequest", [])

    # Only add if not already present (match on hook command path)
    already_present = any(
        any(
            h.get("command", "").endswith("command-whitelist.sh")
            for h in entry.get("hooks", [])
        )
        for entry in existing
    )
    if not already_present:
        existing.insert(0, _CLAUDE_HOOK_ENTRY)

    target_claude_dir.mkdir(parents=True, exist_ok=True)
    settings_dst.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
    print(f"    command-whitelist.sh + PermissionRequest hook -> {target_claude_dir}")
    return True


def _sync_windsurf_rules(source: Path, target_project: Path, dry_run: bool) -> bool:
    """Copy .windsurf/rules/ from source into the target project directory.

    Returns True if changes were made (or would be made in dry-run).
    """
    rules_src = source / ".windsurf" / "rules"
    if not rules_src.is_dir():
        print(f"    [warn] Windsurf rules not found: {rules_src}")
        return False

    rules_dst = target_project / ".windsurf" / "rules"

    if dry_run:
        files = list(rules_src.rglob("*.md"))
        for f in files:
            print(f"    [dry-run] copy {f.name} -> {rules_dst / f.name}")
        return bool(files)

    rules_dst.mkdir(parents=True, exist_ok=True)
    copied = 0
    for f in rules_src.rglob("*.md"):
        shutil.copy2(f, rules_dst / f.name)
        copied += 1
    print(f"    {copied} rule file(s) -> {rules_dst}")
    return copied > 0


def sync_settings(
    source: Path,
    detected_ides: dict[str, dict[str, str | Path | None]],
    targets: list[str],
    project: Path | None,
    dry_run: bool = False,
) -> None:
    """Sync whitelist config files to target IDEs."""
    print(f"\n{'[DRY RUN] ' if dry_run else ''}Syncing settings:")
    any_action = False

    if "claude" in targets and "claude" in detected_ides:
        ide = detected_ides["claude"]
        for label in ("user", "project"):
            target_path = ide.get(f"{label}_path")
            if not target_path:
                continue
            tp = Path(target_path) if not isinstance(target_path, Path) else target_path
            # settings.json lives one level up from the skills dir
            claude_dir = tp.parent
            print(f"\n  Claude Code ({label}): {claude_dir}")
            any_action |= _sync_claude_settings(source, claude_dir, dry_run)

    if "windsurf" in targets and "windsurf" in detected_ides:
        ide = detected_ides["windsurf"]
        # Windsurf rules are project-level only
        project_path = ide.get("project_path")
        if project_path and project:
            print(f"\n  Windsurf (project): {project / '.windsurf'}")
            any_action |= _sync_windsurf_rules(source, project, dry_run)
        elif not project:
            print("  Windsurf: skipped (--sync-settings for Windsurf rules requires --level project)")

    if not any_action:
        print("  (nothing to sync)")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync Agent Skills to IDE skill directories")
    parser.add_argument(
        "--source",
        required=True,
        help="Source directory containing skill folders (e.g. ~/CascadeProjects/dotskills)",
    )
    parser.add_argument(
        "--level",
        choices=["user", "project", "both"],
        default="user",
        help="Sync to user-level, project-level, or both (default: user)",
    )
    parser.add_argument(
        "--project",
        help="Project directory for project-level sync (default: cwd)",
    )
    parser.add_argument(
        "--targets",
        default="all",
        help="Comma-separated IDE targets: windsurf,claude,cursor,codex or 'all' (default: all detected)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be synced without copying",
    )
    parser.add_argument(
        "--detect",
        action="store_true",
        help="Only detect and print installed IDEs, then exit",
    )
    parser.add_argument(
        "--sync-settings",
        action="store_true",
        help=(
            "Also sync command-whitelist config to target IDEs "
            "(Claude Code: hook script + settings.json merge; Windsurf: rules/*.md)"
        ),
    )
    return parser.parse_args()


def _resolve_args(args: argparse.Namespace) -> tuple[Path, Path | None]:
    """Validate and resolve source and project paths from CLI args."""
    source = Path(args.source).expanduser().resolve()
    if not source.is_dir():
        print(f"ERROR: Source directory not found: {source}")
        sys.exit(1)

    project = None
    if args.level in ("project", "both"):
        project = Path(args.project).expanduser().resolve() if args.project else Path.cwd()
        if not project.is_dir():
            print(f"ERROR: Project directory not found: {project}")
            sys.exit(1)

    return source, project


def _print_detection(
    detected: dict[str, dict[str, str | Path | None]],
    source: Path,
    project: Path | None,
    level: str,
) -> None:
    """Print detected IDE info and exit."""
    print(f"OS: {platform.system()} ({platform.machine()})")
    print(f"Home: {Path.home()}")
    print(f"Source: {source}")
    if project:
        print(f"Project: {project}")
    print(f"\nDetected IDEs ({level}-level):")
    if not detected:
        print("  (none)")
    for key, info in detected.items():
        paths = []
        if info.get("user_path"):
            paths.append(f"user={info['user_path']}")
        if info.get("project_path"):
            paths.append(f"project={info['project_path']}")
        print(f"  {info['name']:15s} [{key}]  {', '.join(paths)}")


def _resolve_targets(
    args_targets: str, detected: dict[str, dict[str, str | Path | None]]
) -> list[str]:
    """Resolve target IDE keys from CLI arg, filtering to detected only."""
    if args_targets == "all":
        return list(detected.keys())
    requested = [t.strip() for t in args_targets.split(",")]
    missing = [t for t in requested if t not in detected]
    if missing:
        print(f"WARNING: IDEs not detected, skipping: {', '.join(missing)}")
    return [t for t in requested if t in detected]


def _print_summary(stats: dict[str, _SyncStats], skills_count: int, dry_run: bool) -> None:
    """Print sync summary."""
    ide_count = len(stats)
    total_files = sum(s["files"] for s in stats.values())
    prefix = "[DRY RUN] " if dry_run else ""
    print(
        f"\n{prefix}Done: {skills_count} skill(s) synced to {ide_count} IDE(s), {total_files} files copied"
    )
    for s in stats.values():
        for p in s["paths"]:
            print(f"  {s['name']}: {p}")


def main() -> None:
    args = parse_args()
    source, project = _resolve_args(args)
    detected = detect_ides(args.level, project)

    if args.detect:
        _print_detection(detected, source, project, args.level)
        sys.exit(0)

    targets = _resolve_targets(args.targets, detected)
    if not targets:
        print("ERROR: No target IDEs detected. Install an IDE first or check --level.")
        sys.exit(1)

    patterns = load_skillignore(source)
    skills = discover_skills(source, patterns)
    if not skills:
        print(f"ERROR: No skills found in {source}")
        sys.exit(1)

    action = "[DRY RUN] " if args.dry_run else ""
    print(f"{action}Syncing {len(skills)} skill(s) from {source}")
    print(f"  Skills: {', '.join(s.name for s in skills)}")
    print(f"  Level: {args.level}")
    print(f"  Targets: {', '.join(targets)}")
    if patterns:
        print(f"  Ignore: {len(patterns)} patterns from .skillignore")
    if project:
        print(f"  Project: {project}")

    stats = sync_skills(skills, detected, targets, patterns, dry_run=args.dry_run)
    _print_summary(stats, len(skills), args.dry_run)

    if args.sync_settings:
        sync_settings(source, detected, targets, project, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
