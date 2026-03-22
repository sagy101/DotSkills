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
import os
import platform
import re
import shutil
import stat
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
    "jetbrains": {
        "name": "JetBrains",
        "user_dir": ".jetbrains/skills",
        "project_dir": ".idea/skills",
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
# Claude Code PreToolUse hook — auto-approve read-only skill commands
# ---------------------------------------------------------------------------

_HOOK_SCRIPT = "approve-read-commands.sh"
_HOOK_DATA = "read-commands.json"
_HOOK_COMMAND_PROJECT = "$CLAUDE_PROJECT_DIR/.claude/hooks/" + _HOOK_SCRIPT
_HOOK_COMMAND_USER = "$HOME/.claude/hooks/" + _HOOK_SCRIPT

# Both variants for detection (so we can find and replace stale entries)
_HOOK_COMMANDS = {_HOOK_COMMAND_PROJECT, _HOOK_COMMAND_USER}


def _hook_command_for_level(label: str) -> str:
    """Return the correct hook command path for user vs project level."""
    return _HOOK_COMMAND_USER if label == "user" else _HOOK_COMMAND_PROJECT


def _make_pretool_entry(command: str) -> dict:
    """Build a PreToolUse hook entry for the given command."""
    return {
        "matcher": "Bash",
        "hooks": [{"type": "command", "command": command}],
    }


def _has_hook_entry(entries: list[dict], command: str) -> bool:
    """Check if a PreToolUse entry with the given command already exists."""
    for entry in entries:
        for hook in entry.get("hooks", []):
            if hook.get("command") == command:
                return True
    return False


def _has_any_hook_entry(entries: list[dict]) -> str | None:
    """Check if any approve-read-commands hook variant exists. Returns the command if found."""
    for entry in entries:
        for hook in entry.get("hooks", []):
            cmd: str = hook.get("command", "")
            if cmd in _HOOK_COMMANDS:
                return cmd
    return None


def _copy_hook_files(source: Path, hooks_dir: Path, dry_run: bool) -> None:
    """Copy the hook script and data file to the target hooks directory."""
    src_hooks = source / ".claude" / "hooks"
    for filename in (_HOOK_SCRIPT, _HOOK_DATA):
        src = src_hooks / filename
        if not src.is_file():
            print(f"    WARNING: {src} not found, skipping")
            continue
        dest = hooks_dir / filename
        if dry_run:
            print(f"    [dry-run] {src} -> {dest}")
            continue
        hooks_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        if filename.endswith(".sh"):
            dest.chmod(dest.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        print(f"    {filename} -> {dest}")


def _update_settings_json(settings_path: Path, label: str, dry_run: bool) -> bool:
    """Add PreToolUse hook entry to a settings.json file. Returns True if modified."""
    data: dict = {}
    if settings_path.is_file():
        data = json.loads(settings_path.read_text(encoding="utf-8"))

    hooks = data.setdefault("hooks", {})
    pretool = hooks.setdefault("PreToolUse", [])

    correct_command = _hook_command_for_level(label)

    # Check if the correct entry already exists
    if _has_hook_entry(pretool, correct_command):
        print(f"    PreToolUse hook already present in {settings_path}")
        return False

    # Check if a stale entry with the wrong path variant exists and replace it
    stale_command = _has_any_hook_entry(pretool)
    if stale_command and stale_command != correct_command:
        for entry in pretool:
            for hook in entry.get("hooks", []):
                if hook.get("command") == stale_command:
                    if dry_run:
                        print(f"    [dry-run] Would update hook path in {settings_path}")
                        return False
                    hook["command"] = correct_command
                    settings_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
                    print(f"    Updated hook path in {settings_path}")
                    return True

    if dry_run:
        print(f"    [dry-run] Would add PreToolUse hook to {settings_path}")
        return False

    pretool.append(_make_pretool_entry(correct_command))
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(f"    Added PreToolUse hook to {settings_path}")
    return True


def update_claude_hooks(
    source: Path,
    detected_ides: dict[str, dict[str, str | Path | None]],
    dry_run: bool = False,
) -> None:
    """Install read-command auto-approval hook for Claude Code.

    Updates settings.json and copies hook files to every Claude Code target
    path (user-level and/or project-level) that was detected for this sync.
    """
    ide = detected_ides.get("claude")
    if not ide:
        return

    print("\n  Claude Code: installing read-command auto-approval hook")

    for label, tp in _iter_ide_paths(ide):
        # tp is the skills dir (e.g. ~/.claude/skills or <project>/.claude/skills)
        # settings.json and hooks/ live one level up from the skills dir
        claude_dir = tp.parent  # .claude/
        settings_path = claude_dir / "settings.json"
        hooks_dir = claude_dir / "hooks"

        print(f"\n    {label}: {claude_dir}")
        _copy_hook_files(source, hooks_dir, dry_run)
        _update_settings_json(settings_path, label, dry_run)


# ---------------------------------------------------------------------------
# Shared helpers for IDE auto-approval handlers
# ---------------------------------------------------------------------------


def _load_read_patterns(source: Path) -> list[dict]:
    """Load read command patterns from the source repo's read-commands.json."""
    patterns_file = source / ".claude" / "hooks" / "read-commands.json"
    if not patterns_file.is_file():
        print(f"  WARNING: {patterns_file} not found, skipping auto-approval setup")
        return []
    return json.loads(patterns_file.read_text(encoding="utf-8"))  # type: ignore[no-any-return]


def _iter_ide_paths(
    ide: dict[str, str | Path | None],
) -> list[tuple[str, Path]]:
    """Yield (label, resolved_path) for each configured IDE target (user/project)."""
    result = []
    for label in ("user", "project"):
        target = ide.get(f"{label}_path")
        if not target:
            continue
        result.append((label, Path(target) if not isinstance(target, Path) else target))
    return result


# ---------------------------------------------------------------------------
# Gemini CLI — TOML policy file for auto-approval
# ---------------------------------------------------------------------------

_GEMINI_POLICY_FILE = "dotskills-read-commands.toml"

_GEMINI_POLICY_HEADER = (
    "# Auto-generated by DotSkills skill-sync\n"
    "# Read-only skill commands — safe to auto-approve\n"
    "# Re-run skill-sync to update. Do not edit manually.\n\n"
)


def _pattern_to_gemini_regex(pattern: str) -> str:
    """Convert a read-commands.json glob pattern to a Gemini CLI regex.

    Handles four pattern forms:
      */scripts/script.py *             → simple (any args)
      */scripts/script.py               → no args
      */scripts/script.py subcmd *      → subcommand-based
      */scripts/script.py --flag val *  → flag-based (match flag anywhere)
    """
    p = pattern[2:] if pattern.startswith("*/") else pattern
    parts = p.split()
    script = parts[0]

    # Escape regex specials in the script path
    script_re = re.sub(r"([.+?{}()|\\[\]^$])", r"\\\1", script)

    if len(parts) == 1:
        # No-args: match script at end of line
        return f".*/{script_re}$"

    if parts[-1] != "*":
        # Unusual pattern — escape and convert * to .*
        full_re = re.sub(r"([.+?{}()|\\[\]^$])", r"\\\1", p).replace("*", ".*")
        return f".*{full_re}"

    middle = parts[1:-1]  # everything between script and trailing *
    if not middle:
        # Simple: script with any args
        return f".*/{script_re}(\\s|$)"

    middle_str = " ".join(middle)
    if middle[0].startswith("--"):
        # Flag-based: match flag anywhere after script
        flag_re = re.sub(r"([.+?{}()|\\[\]^$])", r"\\\1", middle_str)
        return f".*/{script_re}\\s.*{flag_re}(\\s|$)"
    # Subcommand: match subcommand right after script
    sub_re = re.sub(r"([.+?{}()|\\[\]^$])", r"\\\1", middle_str)
    return f".*/{script_re}\\s+{sub_re}(\\s|$)"


def _generate_gemini_policy(patterns: list[dict]) -> str:
    """Generate TOML policy content from read command patterns.

    Uses the Gemini CLI policy engine schema:
    https://github.com/google-gemini/gemini-cli/blob/main/docs/reference/policy-engine.md
    """
    lines = [_GEMINI_POLICY_HEADER]
    for entry in patterns:
        skill = entry["skill"]
        pat = entry["pattern"]
        script_name = pat.split("/")[-1].split(" ")[0]
        regex = _pattern_to_gemini_regex(pat)
        lines.append(f"# {skill}: {script_name}")
        lines.append("[[rule]]")
        lines.append(f"commandRegex = '{regex}'")
        lines.append('decision = "allow"')
        lines.append("priority = 100")
        lines.append("")
    return "\n".join(lines)


def update_gemini_approval(
    source: Path,
    detected_ides: dict[str, dict[str, str | Path | None]],
    dry_run: bool = False,
) -> None:
    """Install read-command auto-approval policy for Gemini CLI.

    Generates a TOML policy file at .gemini/policies/ containing regex rules
    for all read-only commands. Idempotent: skips if file content matches.
    """
    ide = detected_ides.get("gemini")
    if not ide:
        return

    read_patterns = _load_read_patterns(source)
    if not read_patterns:
        return

    content = _generate_gemini_policy(read_patterns)
    print("\n  Gemini CLI: installing read-command auto-approval policy")

    for label, tp in _iter_ide_paths(ide):
        gemini_dir = tp.parent  # .gemini/
        policy_dir = gemini_dir / "policies"
        policy_file = policy_dir / _GEMINI_POLICY_FILE

        if policy_file.is_file():
            existing = policy_file.read_text(encoding="utf-8")
            if existing == content:
                print(f"    {label}: policy already up to date at {policy_file}")
                continue

        if dry_run:
            print(f"    [dry-run] Would write {policy_file} ({len(read_patterns)} rules)")
            continue

        policy_dir.mkdir(parents=True, exist_ok=True)
        policy_file.write_text(content, encoding="utf-8")
        print(f"    {label}: wrote {policy_file} ({len(read_patterns)} rules)")


# ---------------------------------------------------------------------------
# Windsurf — windsurf.cascadeCommandsAllowList in settings.json
# ---------------------------------------------------------------------------


def _windsurf_user_settings_path() -> Path:
    """Resolve the Windsurf user settings.json path (OS-specific)."""
    system = platform.system()
    home = Path.home()
    if system == "Darwin":
        return home / "Library" / "Application Support" / "Windsurf" / "User" / "settings.json"
    if system == "Windows":
        appdata = Path(os.environ.get("APPDATA", str(home / "AppData" / "Roaming")))
        return appdata / "Windsurf" / "User" / "settings.json"
    # Linux
    return home / ".config" / "Windsurf" / "User" / "settings.json"


def _patterns_to_windsurf_prefixes(
    patterns: list[dict], skills_dir: Path
) -> tuple[list[str], list[str]]:
    """Convert read-command patterns to Windsurf command prefixes.

    Returns (safe_prefixes, skipped_patterns).
    Skips flag-based dual-mode patterns where prefix matching cannot
    safely distinguish read from write invocations.
    """
    prefixes = []
    skipped = []
    for entry in patterns:
        pat = entry["pattern"]
        skill = entry["skill"]

        if not pat.startswith("*/"):
            continue
        suffix = pat[2:]
        parts = suffix.split()
        script_rel = parts[0]
        interpreter = "bash" if script_rel.endswith(".sh") else "python3"
        script_path = skills_dir / skill / script_rel

        if len(parts) == 1:
            # No-args (setup scripts) — exact command
            prefixes.append(f"{interpreter} {script_path}")
        elif len(parts) == 2 and parts[1] == "*":
            # Simple — script with any args
            prefixes.append(f"{interpreter} {script_path}")
        elif len(parts) >= 3 and parts[1].startswith("--"):
            # Flag-based dual-mode — unsafe for prefix matching
            skipped.append(pat)
        else:
            # Subcommand (e.g. "pods *") — include subcommand in prefix
            subcommand = parts[1]
            prefixes.append(f"{interpreter} {script_path} {subcommand}")

    return prefixes, skipped


def _update_windsurf_settings(settings_path: Path, prefixes: set[str], dry_run: bool) -> bool:
    """Merge command prefixes into Windsurf settings.json. Returns True if modified."""
    data: dict = {}
    if settings_path.is_file():
        try:
            data = json.loads(settings_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            data = {}

    existing = set(data.get("windsurf.cascadeCommandsAllowList", []))
    new_prefixes = prefixes - existing

    if not new_prefixes:
        print(f"    All {len(prefixes)} prefixes already present in {settings_path}")
        return False

    if dry_run:
        print(f"    [dry-run] Would add {len(new_prefixes)} command prefixes to {settings_path}")
        return False

    merged = sorted(existing | prefixes)
    data["windsurf.cascadeCommandsAllowList"] = merged
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(f"    Added {len(new_prefixes)} prefixes ({len(merged)} total) to {settings_path}")
    return True


def update_windsurf_approval(
    source: Path,
    detected_ides: dict[str, dict[str, str | Path | None]],
    dry_run: bool = False,
) -> None:
    """Install read-command auto-approval for Windsurf.

    Merges command prefixes into Windsurf's windsurf.cascadeCommandsAllowList in its
    user-level settings.json. Additive: never removes existing entries.
    """
    ide = detected_ides.get("windsurf")
    if not ide:
        return

    read_patterns = _load_read_patterns(source)
    if not read_patterns:
        return

    print("\n  Windsurf: installing read-command auto-approval")

    all_prefixes: set[str] = set()
    all_skipped: list[str] = []

    for _label, sp in _iter_ide_paths(ide):
        prefixes, skipped = _patterns_to_windsurf_prefixes(read_patterns, sp)
        all_prefixes.update(prefixes)
        if not all_skipped:
            all_skipped = skipped

    if not all_prefixes:
        return

    settings_path = _windsurf_user_settings_path()
    _update_windsurf_settings(settings_path, all_prefixes, dry_run)

    if all_skipped:
        print(f"    NOTE: {len(all_skipped)} flag-based patterns skipped (prefix matching unsafe)")
        print("    See docs/read-command-whitelist.md for manual configuration")


# ---------------------------------------------------------------------------
# Cursor / Codex — info-only (no clean auto-approval mechanism)
# ---------------------------------------------------------------------------


def _print_cursor_info() -> None:
    """Print info about Cursor auto-approval limitations."""
    print("\n  Cursor: auto-approval requires manual setup")
    print("    Enable YOLO mode in Settings > Features, then add command prefixes")
    print("    to the allowlist. See docs/read-command-whitelist.md for the list.")
    print("    NOTE: Cursor's allowlist has known bypass issues (CVE-2026-22708).")
    print("    Programmatic configuration is not supported due to storage instability.")


def _print_codex_info() -> None:
    """Print info about Codex auto-approval limitations."""
    print("\n  Codex CLI: auto-approval not supported")
    print("    Codex uses a coarse-grained approval_policy in config.toml")
    print("    (on-request | never) with no per-command allowlist.")
    print('    Set approval_policy = "on-request" in ~/.codex/config.toml for')
    print("    the closest equivalent.")


def _print_jetbrains_info() -> None:
    """Print info about JetBrains auto-approval status."""
    print("\n  JetBrains: auto-approval not yet supported")
    print("    Skills are synced to ~/.jetbrains/skills/ (user) and .idea/skills/ (project).")
    print("    Auto-approval depends on the AI plugin used (Claude Code, Windsurf, etc.).")
    print("    See docs/read-command-whitelist.md for the command list.")


# ---------------------------------------------------------------------------
# Read approval dispatcher
# ---------------------------------------------------------------------------


def update_read_approvals(
    source: Path,
    detected_ides: dict[str, dict[str, str | Path | None]],
    targets: list[str],
    dry_run: bool = False,
) -> None:
    """Update read-command auto-approval for all target IDEs."""
    if "claude" in targets:
        update_claude_hooks(source, detected_ides, dry_run)
    if "gemini" in targets:
        update_gemini_approval(source, detected_ides, dry_run)
    if "windsurf" in targets:
        update_windsurf_approval(source, detected_ides, dry_run)
    if "cursor" in targets and "cursor" in detected_ides:
        _print_cursor_info()
    if "codex" in targets and "codex" in detected_ides:
        _print_codex_info()
    if "jetbrains" in targets and "jetbrains" in detected_ides:
        _print_jetbrains_info()


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
        help="Comma-separated IDE targets: windsurf,claude,cursor,codex,jetbrains or 'all' (default: all detected)",
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

    update_read_approvals(source, detected, targets, dry_run=args.dry_run)

    _print_summary(stats, len(skills), args.dry_run)


if __name__ == "__main__":
    main()
