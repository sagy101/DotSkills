# Prompt Patterns for Codex Sub-Agent

Templates and examples for constructing effective prompts when delegating tasks to Codex CLI via the wrapper.

## Prompt Structure Template

Every prompt should include the relevant sections from this template:

```
[GOAL]
{One clear sentence describing what to accomplish}

[CONTEXT]
{Background information the sub-agent needs:
- What has been done so far
- Why this approach was chosen
- Any relevant conversation history (summarized)}

[FILES]
{Specific file paths to focus on:
- /path/to/relevant/file.ts — description of relevance
- /path/to/another/file.ts — description}

[CONSTRAINTS]
{What NOT to do:
- Do not modify files outside of X
- Follow existing code style
- Do not add new dependencies
- Maximum scope: only files in src/components/}

[ACCEPTANCE CRITERIA]
{How to verify success:
- All tests pass after changes
- No new linting errors
- Specific behavior is observable}

[VALIDATION COMMANDS]
{Commands to run after making changes:
- npm test
- npm run lint}

[OUTPUT]
{What to return:
- A summary of changes made
- List of files modified
- Any issues encountered
- Recommendations for follow-up}
```

## Section Priority by Task Type

Not all sections are needed for every task. Include based on priority:

| Task Type | Required Sections | Optional Sections |
|---|---|---|
| Implementation | GOAL, FILES, CONSTRAINTS, OUTPUT | CONTEXT, ACCEPTANCE CRITERIA, VALIDATION |
| Code Review | GOAL, FILES, CONSTRAINTS, OUTPUT | CONTEXT |
| Analysis | GOAL, FILES, OUTPUT | CONTEXT, CONSTRAINTS |
| Debugging | GOAL, FILES, ERROR (verbatim), OUTPUT | CONTEXT, VALIDATION |
| Refactoring | GOAL, FILES, CONSTRAINTS, VALIDATION, OUTPUT | CONTEXT, ACCEPTANCE CRITERIA |
| Test Generation | GOAL, FILES, CONSTRAINTS, ACCEPTANCE CRITERIA, OUTPUT | CONTEXT |
| Search/Explain | GOAL, FILES, OUTPUT | — |

## Token Budget

Each sub-agent invocation costs ~5-50K tokens in system overhead. Budget your prompt accordingly:

| Task Type | Target Prompt Size | Trim Priority (keep first) |
|---|---|---|
| Simple search/analysis | < 500 tokens | Goal > Files > Constraints |
| Implementation | 500-2000 tokens | Goal > Constraints > Context > Files |
| Review | 500-1500 tokens | Goal > Files > Constraints > Output format |
| Debug | 500-2000 tokens | Goal > Error message > Files > Context |

When the prompt is too long: drop optional context first, then examples, then reduce the file list to the most critical paths.

## Examples

### Implementation

```
[GOAL]
Add input validation to the user registration endpoint.

[CONTEXT]
The Express.js API at src/routes/auth.ts has a POST /register endpoint that
currently accepts any input without validation. We use Zod for validation
elsewhere in the project (see src/schemas/profile.ts for the pattern).

[FILES]
- src/routes/auth.ts — the endpoint to modify
- src/schemas/profile.ts — reference for Zod validation pattern
- src/types/user.ts — User type definition

[CONSTRAINTS]
- Use Zod for validation (already a project dependency)
- Follow the pattern in profile.ts
- Return 400 with validation errors on invalid input
- Do not modify any other endpoints
- Do not add new dependencies

[OUTPUT]
- Summary of changes made
- The Zod schema you created
- Any edge cases you considered
```

### Code Review

```
[GOAL]
Review the authentication middleware for security vulnerabilities and correctness.

[CONTEXT]
This middleware was recently refactored from session-based to JWT-based auth.
The refactor touched 3 files. We need to verify there are no security gaps.

[FILES]
- src/middleware/auth.ts — the main middleware (REVIEW FOCUS)
- src/utils/jwt.ts — JWT utility functions
- src/routes/protected.ts — routes using the middleware

[CONSTRAINTS]
- This is a review only — do NOT modify any files
- Focus on: token validation, expiry handling, error responses, header parsing
- Check for OWASP top 10 relevant issues

[OUTPUT]
For each finding:
- Severity: critical / high / medium / low
- File and line number
- Description of the issue
- Suggested fix
- Confidence: high / medium / low
```

### Analysis / Data Flow Mapping

```
[GOAL]
Map the data flow from API request to database write for the order creation endpoint.

[FILES]
- src/routes/orders.ts — entry point
- src/services/order.ts — business logic
- src/models/order.ts — database model

[OUTPUT]
- Step-by-step data flow with file:line references
- Any transformations applied to the data
- Validation points
- Error handling gaps
```

### Debugging

```
[GOAL]
Find and fix the cause of this error in the payment processing flow.

[ERROR]
TypeError: Cannot read properties of undefined (reading 'amount')
    at processPayment (src/services/payment.ts:47:23)
    at async handleCheckout (src/routes/checkout.ts:31:5)

[FILES]
- src/services/payment.ts:47 — where the error occurs
- src/routes/checkout.ts:31 — where it's called from
- src/types/order.ts — Order type definition

[CONTEXT]
This happens when a user checks out with an empty cart. The order object
exists but the items array is empty, so total calculation returns undefined.

[CONSTRAINTS]
- Fix the root cause, not just the symptom
- Add a guard/validation for empty carts
- Do not change the Order type definition

[VALIDATION COMMANDS]
- npm test -- --grep "payment"
- npm test -- --grep "checkout"

[OUTPUT]
- Root cause explanation
- Fix applied with file:line references
- Test results after fix
```

### Refactoring

```
[GOAL]
Extract the email sending logic from UserService into a dedicated EmailService.

[FILES]
- src/services/user.ts — contains email logic to extract (lines 120-180)
- src/services/ — where new EmailService should be created
- src/tests/user.test.ts — tests that need updating

[CONTEXT]
UserService has grown too large (800+ lines). Email sending (welcome, reset,
notification) should be its own service. The project uses dependency injection
via tsyringe.

[CONSTRAINTS]
- Preserve all existing behavior
- Update all imports and DI registrations
- Update tests to use the new service
- Follow existing service patterns (see src/services/auth.ts for reference)

[VALIDATION COMMANDS]
- npm test
- npm run build

[OUTPUT]
- List of files created/modified
- Summary of the extraction
- Any decisions made about shared types/interfaces
```

### Test Generation

```
[GOAL]
Write comprehensive unit tests for the OrderService.calculateTotal method.

[FILES]
- src/services/order.ts:calculateTotal — the method to test
- src/tests/services/ — where test file should go
- src/tests/services/auth.test.ts — reference for test patterns

[CONSTRAINTS]
- Use Jest with the existing project configuration
- Follow the pattern in auth.test.ts (describe/it blocks, factory helpers)
- Cover: normal cases, empty input, single item, discounts, tax calculation,
  currency rounding, maximum values, negative quantities
- Mock external dependencies (database, payment gateway)

[ACCEPTANCE CRITERIA]
- All new tests pass
- No existing tests broken
- Coverage for calculateTotal reaches 90%+

[OUTPUT]
- Test file created
- Number of test cases and what they cover
- Any edge cases discovered during test writing
```

### Python Migration

```
[GOAL]
Migrate the data processing module from synchronous to async using asyncio.

[FILES]
- src/processors/data_processor.py — main module to migrate
- src/processors/base.py — base class (needs async interface)
- tests/test_data_processor.py — tests to update

[CONTEXT]
The module processes large datasets sequentially. We need async for parallel
I/O when fetching data from multiple sources. The project uses Python 3.12
with asyncio and aiohttp for HTTP.

[CONSTRAINTS]
- Maintain backward compatibility with sync callers (add async versions, keep sync wrappers)
- Use asyncio.gather for parallel operations
- Do not change the public API signatures (add async_ prefixed alternatives)
- Follow existing async patterns in src/connectors/async_db.py

[VALIDATION COMMANDS]
- python -m pytest tests/test_data_processor.py -v
- python -m mypy src/processors/

[OUTPUT]
- Files modified with summary of changes
- New async API surface
- Performance considerations
```
