#!/usr/bin/env bash
# PreToolUse hook: auto-approve read-only skill commands.
#
# Reads the Bash tool input JSON from stdin, extracts the command,
# and checks it against the read-commands.json pattern list.
# Match → approve (exit 0 with decision JSON). No match → pass through (exit 1).
#
# Safety: rejects commands containing shell operators (;, &&, ||, |, $(), ``)
# to prevent injection of write commands after a whitelisted read command.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PATTERNS_FILE="$SCRIPT_DIR/read-commands.json"

# Read tool input from stdin
INPUT=$(cat)

# Extract the command string from tool_input.command
COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // empty')
[ -z "$COMMAND" ] && exit 1

# Bail if the patterns file is missing
[ -f "$PATTERNS_FILE" ] || exit 1

# --- Safety: reject commands with shell operators ---
# These could chain a whitelisted read command with a dangerous write command.
if echo "$COMMAND" | grep -qE ';|\|\||&&|\||\$\(|`'; then
    exit 1
fi

# --- Build regex list (avoid subshell so exit works) ---
PATTERNS=$(jq -r '.[].pattern' "$PATTERNS_FILE")

while IFS= read -r pat; do
    [ -z "$pat" ] && continue

    # Escape regex-special characters except *, then replace * with .*
    regex=$(echo "$pat" | sed 's/[.[\^$()+{}|]/\\&/g; s/\*/.*/g')

    # --- Flag-based patterns (e.g. "*/page_versions.py --list *") ---
    # For these, match the flag anywhere in the command to handle any flag order.
    if echo "$pat" | grep -qE '\.(py|sh) --'; then
        # Extract script part (before the first --flag)
        script_pat=$(echo "$pat" | sed 's/ --.*$//')
        script_regex=$(echo "$script_pat" | sed 's/[.[\^$()+{}|]/\\&/g; s/\*/.*/g')

        # Extract the flag segment (e.g. "--list", "--mode read-only", "--status")
        flag_segment=$(echo "$pat" | sed 's/^[^-]*\(--[^*]*\).*/\1/' | sed 's/ *$//')

        # Build match: script path matches AND flag appears somewhere in the command
        # Use grep -F -- to prevent flag_segment from being parsed as grep options
        if echo "$COMMAND" | grep -qE "^${script_regex}" && echo "$COMMAND" | grep -qF -- "$flag_segment"; then
            echo '{"decision": "approve"}'
            exit 0
        fi
    fi

    # --- Standard full-string match ---
    if echo "$COMMAND" | grep -qE "^${regex}$"; then
        echo '{"decision": "approve"}'
        exit 0
    fi

    # --- No-args match ---
    # If pattern ends with " *" (becomes " .*" in regex), also match the command
    # with no arguments at all (just the script path).
    case "$regex" in
        *" ."*)
            no_args_regex="${regex% .*}"
            if echo "$COMMAND" | grep -qE "^${no_args_regex}$"; then
                echo '{"decision": "approve"}'
                exit 0
            fi
            ;;
    esac
done <<< "$PATTERNS"

# No match — fall through to normal approval flow
exit 1
