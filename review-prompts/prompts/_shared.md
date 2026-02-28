# Shared Review Sections

These sections are assembled into every review prompt by `scripts/build-prompt.py`. Do not use this file directly.

## Process
Before applying the checklist:
1. **Ensure you have the full content** — verify nothing was truncated (terminal output limits, large files, partial diffs). If content appears cut off, request or read the rest before reviewing.
2. **Read surrounding context** — read the full file or document to understand intent before reviewing individual changes
3. **Cross-reference with project patterns** — does the change match existing conventions and style?
4. **Only report high-confidence findings** — every conclusion must be grounded in the actual content, not speculation

## Output Format
Provide findings in this structure:
- **[SEVERITY: Critical/High/Medium/Low]** — [Category]
  - **Location**: [File:Line or Section]
  - **Issue**: [Description]
  - **Impact**: [What could go wrong]
  - **Recommendation**: [How to fix]

Example:
- **[SEVERITY: High]** — Correctness
  - **Location**: src/auth/login.ts:42
  - **Issue**: Password comparison uses `==` instead of constant-time comparison
  - **Impact**: Timing attack could leak password length information
  - **Recommendation**: Use `crypto.timingSafeEqual()` for password comparison

## Constraints
- Organize findings by severity (Critical first, then High, Medium, Low)
- Severity rubric:
  - **Critical**: Data loss, security breach, or system crash in production
  - **High**: Incorrect behavior affecting users or significant security risk
  - **Medium**: Code quality issue increasing maintenance cost or technical debt
  - **Low**: Style, convention, or minor improvement opportunity
- One finding per block — use the structured format above
- If no issues found for a severity level, omit it
- Focus on actionable findings — skip nitpicks unless nothing else is found
