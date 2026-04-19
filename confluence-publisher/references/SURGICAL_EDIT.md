# Surgical Edit & Structural Changes

Detailed usage for `surgical_edit.py`, `replace_element.py`, and `render_mermaid.py`.

## Surgical edit (`surgical_edit.py`)

Apply targeted find/replace edits to a Confluence page's storage HTML without overwriting the entire page. Preserves manual formatting in untouched sections. **No markdown conversion** — operates directly on Confluence storage HTML.

```bash
# Inline single replacement
<skill_dir>/.venv/bin/python <skill_dir>/scripts/surgical_edit.py \
    --page 1079706804 --find "old text" --replace "new text"

# Replace all occurrences (default: first only)
<skill_dir>/.venv/bin/python <skill_dir>/scripts/surgical_edit.py \
    --page 1079706804 --find "old" --replace "new" --replace-all

# Apply multiple replacements from a JSON file
<skill_dir>/.venv/bin/python <skill_dir>/scripts/surgical_edit.py \
    --page 1079706804 --replacements edits.json

# Dry run — show diff without pushing changes
<skill_dir>/.venv/bin/python <skill_dir>/scripts/surgical_edit.py \
    --page 1079706804 --replacements edits.json --dry-run

# Save diff report to file and verify sections survived
<skill_dir>/.venv/bin/python <skill_dir>/scripts/surgical_edit.py \
    --page 1079706804 --replacements edits.json \
    --output /tmp/report.txt \
    --check-sections "Problem Definition,Solution Architecture"
```

Replacements JSON format:
```json
[
    {"find": "old text 1", "replace": "new text 1"},
    {"find": "old text 2", "replace": "new text 2", "replace_all": true}
]
```

The `--page` argument accepts a numeric page ID, a full Confluence URL, or a tiny link.

**Always use `--dry-run` first** to verify the replacements before pushing. The script shows a semantic diff report and section integrity check.

## Large structural changes (`replace_element.py`)

For complex edits like adding a table column or restructuring a section:

```bash
# Extract: save the table after "Implementation Phases" to a file
<skill_dir>/.venv/bin/python <skill_dir>/scripts/replace_element.py \
    --page 1079706804 --heading "Implementation Phases" --element table \
    --output /tmp/table.html

# (modify /tmp/table.html → /tmp/table-new.html)

# Preview changes (always dry-run first)
<skill_dir>/.venv/bin/python <skill_dir>/scripts/replace_element.py \
    --page 1079706804 --old /tmp/table.html --new /tmp/table-new.html --dry-run

# Apply after user approval
<skill_dir>/.venv/bin/python <skill_dir>/scripts/replace_element.py \
    --page 1079706804 --old /tmp/table.html --new /tmp/table-new.html \
    --message "Updated Implementation Phases table"
```

Supported `--element` types: `table`, `ul`, `ol`, `div`, `section` (heading + content until next same-level heading). Use `--nth 2` for the 2nd occurrence after the heading. Preserve existing `ac:local-id` attributes on unchanged elements; new elements don't need them.

**Heading matching** handles HTML entities automatically: `--heading "Testing & Evaluation"` matches `Testing &amp; Evaluation` in the page HTML. No need to escape `&` or other special characters.

### Replace a section from markdown (`--new-md`)

To replace an entire section directly from a markdown file (with automatic mermaid rendering, heading level adjustment, and attachment upload):

```bash
# Replace the "Testing & Evaluation" section from a local markdown file
<skill_dir>/.venv/bin/python <skill_dir>/scripts/replace_element.py \
    --page 1079706804 --heading "Testing & Evaluation" --element section \
    --new-md /tmp/new-testing-section.md --dry-run

# Apply after review
<skill_dir>/.venv/bin/python <skill_dir>/scripts/replace_element.py \
    --page 1079706804 --heading "Testing & Evaluation" --element section \
    --new-md /tmp/new-testing-section.md --message "Updated Testing section"
```

The `--new-md` flag automatically:
- Converts markdown to Confluence storage HTML
- Renders mermaid diagrams to PNG and uploads them as page attachments
- Adjusts heading levels to match the existing section (e.g., if the old section starts with `<h1>`, the markdown `##` headings are shifted to `<h1>`)

### Append a new section to a page

To add new content to a page without replacing any existing section, use `--append-after` or `--append-end`:

```bash
# Append a new section after "Detailed Plan Documents" (dry run first)
<skill_dir>/.venv/bin/python <skill_dir>/scripts/replace_element.py \
    --page 1079706804 --heading "Detailed Plan Documents" \
    --append-after --new-md /tmp/new-section.md --dry-run

# Append at the very end of the page (no --heading needed)
<skill_dir>/.venv/bin/python <skill_dir>/scripts/replace_element.py \
    --page 1079706804 --append-end \
    --new-md /tmp/new-section.md --dry-run

# Apply after reviewing the dry run
<skill_dir>/.venv/bin/python <skill_dir>/scripts/replace_element.py \
    --page 1079706804 --heading "Detailed Plan Documents" \
    --append-after --new-md /tmp/new-section.md \
    --message "Added Future Vision section"
```

Both flags require `--new-md` and automatically:
- Convert markdown to Confluence storage HTML
- Render mermaid diagrams to PNG and upload as attachments
- Adjust heading levels to match the surrounding content

Use `--append-after` when you know which section the new content should follow. Use `--append-end` when the content goes at the very end of the page.

**Always use `--dry-run` first** and check the section integrity report to confirm no existing content was affected.

## Render mermaid code blocks to images (`render_mermaid.py`)

If a page has mermaid code blocks that render as raw text (because they were inserted without PNG rendering), convert them to images:

```bash
# Preview which blocks would be rendered
<skill_dir>/.venv/bin/python <skill_dir>/scripts/render_mermaid.py \
    --page 1079706804 --dry-run

# Render all mermaid blocks to PNG and replace
<skill_dir>/.venv/bin/python <skill_dir>/scripts/render_mermaid.py \
    --page 1079706804

# Custom image width
<skill_dir>/.venv/bin/python <skill_dir>/scripts/render_mermaid.py \
    --page 1079706804 --width 1000
```

The script finds all `<ac:structured-macro ac:name="code">` blocks with language "mermaid", renders each to PNG via `mmdc`, uploads them as page attachments, and replaces the code blocks with `<ac:image>` macros.
