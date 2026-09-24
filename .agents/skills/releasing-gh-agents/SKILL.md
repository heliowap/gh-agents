---
name: releasing-gh-agents
description: Use when merging to main, cutting or moving a version tag, or changing agents.yml inputs — anything callers pin or consume.
---

# Releasing gh-agents

## Overview

Callers pin the reusable workflow by tag (`@v1`). A tag move is a deliberate
release act by a maintainer — there is no release automation. Every commit
message is written for a repo owner deciding whether to trust the upgrade,
not for a reader of the diff. Rules: `docs/conventions/commits.md`.

## Commit format (Conventional Commits)

```
<type>[(scope)][!]: <what changes for callers or operators, imperative, lower case, no full stop>
```

| Type | Meaning for callers |
|---|---|
| `feat` | callers can do something new, or must do something differently |
| `fix` | something wrong is now right |
| `perf` | same behaviour, cheaper |
| `docs`, `test`, `refactor`, `build`, `ci`, `chore` | no release impact |

- Scope names the part: `review`, `fix`, `ci-doctor`, `fleet`, `runtime`,
  `agents`, `skills`.
- `!` when callers must act — renamed input, dropped job, changed output
  contract. Breaking changes to `agents.yml` inputs also move the floating
  major tag.
- Pick type by what the caller notices, not which file changed.
  `fix: keep comment triggers from cancelling an in-flight review`, not
  `fix: change concurrency group`.
- No tool or AI attribution: no `Co-Authored-By`, no "Generated with".

## Tagging

```bash
git tag -f v1 <merge-commit>   # floating major, moved deliberately
git push -f origin v1          # only after verification below
```

Before moving a tag:

1. `main` is green on every applicable DoD row (see verifying-changes).
2. The change was exercised on a real caller repo — a tag move on an
   unexercised workflow ships unverified behaviour to every caller at once.
3. Breaking change? Commit carries `!`, callers get told what to change,
   and the floating major tag is the mechanism — never break `v1` silently.

## Common mistakes

- Moving `v1` as part of a feature PR merge "to save a step" — the tag move
  is the release; treat it as one.
- Renaming an input as `fix:` without `!` — every caller's `with:` breaks.
- Attributing commits to tools — the repo's convention is a clean trailer.
