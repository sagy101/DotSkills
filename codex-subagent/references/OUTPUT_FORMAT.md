# Codex Sub-Agent Output Format

How to interpret and process the output from Codex CLI sub-agent delegations.

## Output Capture Method

The wrapper captures the sub-agent's final message to a file automatically.

## Reading the Result

After the wrapper completes:
1. Read the result file path from the wrapper's **stdout** (first line)
2. Read the result file contents via your file read tool
3. Clean up the temp directory after reading

## Result File Contents

The result file contains Codex's final agent message as plain text. The format depends on what was asked:

### For Implementation Tasks
Typically contains:
- Summary of changes made
- List of files created/modified
- Any issues encountered
- Validation results (if requested)

### For Review Tasks
Typically contains:
- Findings organized by severity or category
- File and line references
- Suggested fixes
- Overall assessment

### For Analysis Tasks
Typically contains:
- Analysis results
- Data flow descriptions
- File references
- Recommendations

### For Structured Output Tasks
When `--output-schema` is used, the result file contains valid JSON matching the provided schema. Parse it with a JSON parser and validate against the schema.

## Result Validation

Before processing the result, the host agent must validate:

| Check | How | On Failure |
|---|---|---|
| File exists | Check file system | Treat as failure; retry once |
| File non-empty | Check file size > 0 | Treat as failure; retry once |
| File < 1MB | Check file size | Truncate or treat as anomaly |
| Valid JSON (structured only) | Parse with JSON parser | Retry with clarified format instruction |

## Exit Code + Output Matrix

| Exit Code | Output File | Interpretation |
|---|---|---|
| 0 | Exists, non-empty | Success — read and process |
| 0 | Missing or empty | Anomaly — retry once, then report |
| 1 | Exists | Partial result — may still be useful, check contents |
| 1 | Missing | Complete failure — check stderr for details |
| 2 | — | Wrapper policy rejection — check stderr for guidance |
| 124 | May exist | Timeout — check for partial results |
| 127 | — | Codex not installed |
| 143 | May exist | Terminated — check for partial results |

## Worktree Output

When `--collision medium` is used, the wrapper also outputs:
```
/tmp/codex-abc123/result.txt
WORKTREE_BRANCH=codex-work-abc123
WORKTREE_DIR=/tmp/codex-wt-codex-work-abc123
```

The host agent should:
1. Parse `WORKTREE_BRANCH` and `WORKTREE_DIR` from stdout
2. Review changes: `git diff HEAD..<WORKTREE_BRANCH>`
3. If approved: `git merge <WORKTREE_BRANCH>`
4. Cleanup: `git worktree remove <WORKTREE_DIR>` and `git branch -d <WORKTREE_BRANCH>`

## Cleanup

The wrapper does NOT auto-delete temp files — the host agent is responsible for cleanup after reading the result:
- `rm -rf <result-dir>` (the parent directory of the result file)
- For worktrees: also run `git worktree remove` and `git branch -d`
