# Prompt Engineering Best Practices for Codex Sub-Agent

Best practices for writing effective prompts when delegating tasks to sub-agents via the wrapper.

## Structure & Clarity

1. **Be specific and explicit** — Codex works best with clear, unambiguous instructions. "Fix the bug" is bad; "Fix the null pointer exception in `UserService.getProfile()` at line 42 of `src/services/user.ts`" is good.

2. **Use delimiters** — Separate sections with clear markers (`[GOAL]`, `[CONTEXT]`, `---`, XML tags).

3. **Provide examples** — When the output format matters, show an example of what you want. Especially important for structured outputs.

4. **Order matters** — Put the most important instructions first. Earlier instructions have stronger influence.

5. **One task per delegation** — Sub-agents work best on focused, single-purpose tasks. Split complex work into multiple delegations.

## Context & Grounding

6. **Reference specific files by absolute path** — Codex will read them itself. Don't paste large file contents into the prompt unless the file is very short.

7. **Describe the codebase context** — Architecture, frameworks, patterns in use. Codex starts fresh and has zero context about prior work.

8. **State assumptions explicitly** — "Assume TypeScript strict mode", "The project uses ESM imports", "Tests use Jest".

9. **Include error messages verbatim** — When debugging, paste the exact error. The sub-agent cannot guess what the error was.

## Behavioral Control

10. **Specify what NOT to do** — Explicit exclusions prevent scope creep: "Do NOT modify test files", "Do NOT add inline comments", "Do NOT reformat unchanged code".

11. **Set scope boundaries** — "Only modify files in `src/auth/`". This prevents scope creep and file conflicts with other agents.

12. **Request validation** — "After making changes, run `npm test` and report results." The sub-agent can run commands in write mode.

13. **Control verbosity** — "Respond in 3-5 bullet points" or "Provide a detailed walkthrough". Codex defaults to concise.

## Output Control

14. **Use `--output-schema`** for structured data — Forces Codex to return valid JSON matching your schema.

15. **Request file references** — "Include absolute file paths and line numbers for all findings." This makes results actionable.

16. **Ask for confidence levels** — "Rate your confidence (high/medium/low) for each finding." Helps the host agent prioritize.

## Context Inclusion Decision Matrix

| Content Type | Include in Prompt? | Rationale |
|---|---|---|
| Exact error message/stack trace | Yes, inline | Codex needs the verbatim error |
| Small code snippet (< 30 lines) | Yes, inline | Faster than file read |
| Full file contents | No, provide path | Codex reads it; saves prompt tokens |
| Conversation history | No, summarize key decisions | Too many tokens, loses focus |
| Architecture/framework info | Yes, 1-2 sentences | Codex has no prior context |
| Diff of recent changes | Yes if small; path if large | Critical for review tasks |

## Anti-Patterns to Avoid

- **Don't send entire conversation history** — too many tokens, confuses focus
- **Don't ask multiple unrelated questions** — split into separate invocations
- **Don't rely on Codex knowing host agent's state** — it doesn't
- **Don't use vague language** like "improve the code" — be specific about what to improve
- **Don't set contradictory constraints** (e.g., "be thorough" + "respond in 3 bullets")
- **Don't skip validation commands** — always ask Codex to verify its own work
- **Don't forget failure fallback** — instruct what to do if the primary approach fails

## Token Budget Rubric

Each sub-agent invocation costs ~5-50K tokens in system overhead before your prompt is processed:

| Task Type | Target Prompt Size | Trim Priority (keep first) |
|---|---|---|
| Simple search/analysis | < 500 tokens | Goal > Files > Constraints |
| Implementation | 500-2000 tokens | Goal > Constraints > Context > Files |
| Review | 500-1500 tokens | Goal > Files > Constraints > Output format |
| Debug | 500-2000 tokens | Goal > Error message > Files > Context |

Trim order when prompt is too long: drop optional context first, then examples, then reduce file list to most critical.
