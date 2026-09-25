---
name: implement
description: "Implement a piece of work described by the user — a comment request, spec, or ticket. Use when executing a scoped change request."
---

Implement exactly what was asked, in the smallest diff that satisfies it.

- Read the repo's conventions (`AGENTS.md`, CONTRIBUTING) before writing.
- No new abstractions, no new dependencies, no drive-by refactors.
- Use `tdd` where a seam exists: failing test first, then the fix.
- Run the focused test for what changed; run the wider suite once at the end.
- Commit with Conventional Commits, referencing the issue/PR that asked.
- Ambiguous request? Stop and ask instead of guessing.
