# Publish Plan Format

When presenting a publish plan to the user, always use this exact visual format. This ensures consistency across all projects and makes it easy for the user to review and approve.

## Template

```
╔══════════════════════════════════════════════════════════════╗
║                   CONFLUENCE PUBLISH PLAN                    ║
╠══════════════════════════════════════════════════════════════╣
║ Target: <confluence_url>                                     ║
║ Space:  <space_key>                                          ║
║ Root:   "<root_page_title>" (id=<root_page_id>)              ║
╠══════════════════════════════════════════════════════════════╣
║ #  │ Action │ File                    │ Title                 ║
║────┼────────┼─────────────────────────┼───────────────────────║
║  1 │ CREATE │ README.md               │ Project Home          ║
║  2 │ CREATE │ docs/setup.md           │ Setup Guide           ║
║  3 │ UPDATE │ docs/api.md             │ API Reference         ║
╠══════════════════════════════════════════════════════════════╣
║ Creates: 2  │  Updates: 1  │  Skipped: 0  │  Total: 3        ║
╚══════════════════════════════════════════════════════════════╝
```

## Rules

1. Sort entries in publish order (parents before children, then alphabetical within each level)
2. Action is one of: `CREATE`, `UPDATE`, `SKIP`
3. Always show the summary counts at the bottom
4. If any files are being skipped (e.g. unchanged), include them with `SKIP` action
5. After presenting the plan, ask: **"Proceed with this publish plan? (yes / no / edit)"**
6. If the user says "edit", ask what they want to change and present the updated plan again
7. Only proceed after explicit "yes" or equivalent confirmation
