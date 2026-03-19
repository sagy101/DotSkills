#!/usr/bin/env bash
# Post-edit hook: run pre-commit on the file Claude just edited/created.
FILE_PATH=$(jq -r '.tool_input.file_path // empty' < /dev/stdin)
[ -n "$FILE_PATH" ] && [ -f "$FILE_PATH" ] && pre-commit run --files "$FILE_PATH" 2>/dev/null
exit 0
