---
name: code-review
description: "Review the changes since a fixed point (commit, branch, tag, or merge-base). Use when the user wants to review a branch, a PR, or work-in-progress changes."
---

Review the diff between `HEAD` and a fixed point the user supplies (a commit
SHA, branch, tag, `main`, `HEAD~5`). If none was given, use the PR base.

## Process

1. Resolve the fixed point: `git merge-base <point> HEAD`, then
   `git diff <point>...HEAD`. A bad ref or empty diff fails here.
2. Find the spec: the PR body, linked issues, or what the user wrote. If the
   repo has documented conventions (`AGENTS.md`, `docs/conventions/`), read
   them before judging.
3. Read the diff plus enough surrounding code to understand each hunk. Judge
   two axes: conformance to the repo's own standards, and faithfulness to the
   spec.
4. Every finding carries `path:line` of the exact line it refers to.

## Output contract

One comment, three sections — write `(none)` under empty ones:

```
BLOCKING
- file.py:10 — what breaks and why it must not merge

WARNING
- file.py:22 — real risk, not fatal

NIT
- file.py:31 — style/clarity

SUMMARY: N BLOCKING, N WARNING, N NIT
```

The `SUMMARY:` line is the last line and is machine-parsed — never omit it.
