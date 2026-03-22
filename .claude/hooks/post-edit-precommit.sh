#!/usr/bin/env bash
# Post-edit hook: run pre-commit on the file Claude just edited/created.
# Exits with pre-commit's exit code so linting failures are visible to Claude.
FILE_PATH=$(jq -r '.tool_input.file_path // empty' < /dev/stdin)
if [ -n "$FILE_PATH" ] && [ -f "$FILE_PATH" ]; then
    pre-commit run --files "$FILE_PATH" 2>&1
fi
