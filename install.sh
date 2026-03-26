#!/usr/bin/env bash
# DotSkills installer — no Node.js or Python required.
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/sagy101/DotSkills/main/install.sh | bash
#   curl -fsSL .../install.sh | bash -s -- --skill jira-manager --skill eks-pod-ops
#   curl -fsSL .../install.sh | bash -s -- --global
#   curl -fsSL .../install.sh | bash -s -- --list
set -euo pipefail

REPO_URL="https://github.com/sagy101/DotSkills.git"

# ── IDE detection table: name|detect_dir|skills_subdir ───────────────────────
IDES=(
  "Claude Code|.claude|.claude/skills"
  "Windsurf|.codeium/windsurf|.codeium/windsurf/skills"
  "Cursor|.cursor|.cursor/skills"
  "Codex|.codex|.codex/skills"
  "Gemini CLI|.gemini|.gemini/skills"
  "Junie|.junie|.junie/skills"
  "Roo Code|.roo|.roo/skills"
)

# ── Parse args ───────────────────────────────────────────────────────────────
SKILLS=()
GLOBAL=false
LIST=false
while [[ $# -gt 0 ]]; do
  case "$1" in
    --skill)   SKILLS+=("$2"); shift 2 ;;
    --global|-g) GLOBAL=true; shift ;;
    --list|-l) LIST=true; shift ;;
    --help|-h)
      echo "Usage: install.sh [--skill <name>]... [--global] [--list]"
      echo ""
      echo "Options:"
      echo "  --skill <name>   Install specific skill(s) (repeatable). Default: all."
      echo "  --global, -g     Install to user-level (~/) directories."
      echo "  --list, -l       List available skills and exit."
      echo "  --help, -h       Show this help."
      exit 0 ;;
    *) echo "Unknown option: $1"; exit 1 ;;
  esac
done

# ── Clone repo to temp dir ───────────────────────────────────────────────────
TMPDIR="$(mktemp -d)"
trap 'rm -rf "$TMPDIR"' EXIT

echo "Cloning DotSkills..."
git clone --depth 1 --quiet "$REPO_URL" "$TMPDIR/dotskills"
SRC="$TMPDIR/dotskills"

# ── Discover available skills (dirs containing SKILL.md) ────────────────────
AVAILABLE=()
for d in "$SRC"/*/; do
  [[ -f "$d/SKILL.md" ]] && AVAILABLE+=("$(basename "$d")")
done

if $LIST; then
  echo "Available skills (${#AVAILABLE[@]}):"
  for s in "${AVAILABLE[@]}"; do echo "  $s"; done
  exit 0
fi

# ── Resolve which skills to install ─────────────────────────────────────────
if [[ ${#SKILLS[@]} -eq 0 ]]; then
  SKILLS=("${AVAILABLE[@]}")
else
  for s in "${SKILLS[@]}"; do
    found=false
    for a in "${AVAILABLE[@]}"; do [[ "$s" == "$a" ]] && found=true && break; done
    if ! $found; then echo "Error: skill '$s' not found. Use --list to see available skills."; exit 1; fi
  done
fi

# ── Detect IDEs ──────────────────────────────────────────────────────────────
DETECTED=()
for entry in "${IDES[@]}"; do
  IFS='|' read -r name detect_dir skills_dir <<< "$entry"
  if $GLOBAL; then
    target="$HOME/$skills_dir"
    [[ -d "$HOME/$detect_dir" ]] && DETECTED+=("$name|$target")
  else
    # Project-level: use current working directory
    target="$(pwd)/$skills_dir"
    DETECTED+=("$name|$target")
  fi
done

if $GLOBAL && [[ ${#DETECTED[@]} -eq 0 ]]; then
  echo "No supported IDEs detected. Install an IDE first, or use --global after setup."
  echo "Checked: ${IDES[*]%%|*}"
  exit 1
fi

# ── Install ──────────────────────────────────────────────────────────────────
echo "Installing ${#SKILLS[@]} skill(s) to ${#DETECTED[@]} IDE(s)..."
echo ""

installed=0
for entry in "${DETECTED[@]}"; do
  IFS='|' read -r ide_name target_dir <<< "$entry"
  echo "  $ide_name → $target_dir"
  for skill in "${SKILLS[@]}"; do
    src_dir="$SRC/$skill"
    dest_dir="$target_dir/$skill"
    mkdir -p "$dest_dir"
    # Copy everything except .git, __pycache__, .venv, node_modules
    rsync -a --quiet \
      --exclude='.git' --exclude='__pycache__' --exclude='.venv' \
      --exclude='*-venv' --exclude='node_modules' --exclude='.mypy_cache' \
      "$src_dir/" "$dest_dir/"
    installed=$((installed + 1))
  done
done

echo ""
echo "Done. Installed ${#SKILLS[@]} skill(s) to ${#DETECTED[@]} IDE(s) ($installed total copies)."
echo ""
echo "Optional: set up auto-approval for read-only commands."
echo "See: https://github.com/sagy101/DotSkills/blob/main/docs/read-command-whitelist.md"
