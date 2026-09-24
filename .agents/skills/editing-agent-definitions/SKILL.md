---
name: editing-agent-definitions
description: Use when creating or modifying agents in agents/opencode.json, editing agent prompts, or adding fallback skills under skills/ for caller repos.
---

# Editing agent definitions

## Overview

`agents/opencode.json` and `skills/` are the *defaults* shipped to caller
repos — a caller's own `opencode.json` / `.agents/skills/` always wins.
Everything here must be correct inside a stranger's repository. Rules:
`docs/conventions/agents-skills.md`.

## Agents (`agents/opencode.json`)

- Deny-by-default permissions. Review-type agents enumerate allowed bash
  patterns (`git diff*`, `gh pr view*`) and deny `edit`, `webfetch`,
  `websearch`. Write-capable agents (fixer) justify it in the description.
- The default fleet: `reviewer` (read-only, emits BLOCKING/WARNING/NIT),
  `fixer` (`/oc` — bash + edit), `ci-doctor` (diagnosis only; fixes go
  through `/oc`).
- Every agent named in a workflow `with:` must exist here or in the caller's
  own `opencode.json`.
- Validate: `jq empty agents/opencode.json` locally; full schema validation
  runs in CI.

## Prompts are behaviour-shaping code

- A prompt ends with the output contract a later step parses — e.g.
  `SUMMARY: <b> BLOCKING, <w> WARNING, <n> NIT` and findings as
  `path:linha`. Changing the contract breaks the parsing step.
- Changing a prompt requires evidence: a run log showing the failure the
  change fixes — not a style preference. PR carries before/after logs.

## Fallback skills (`skills/`)

- Generic only: no project names, no repo-specific paths, nothing wrong
  inside a stranger's repo. Tailored skills belong in the repo's own
  `.agents/skills/` — that is the point of the fallback order.
- Resolution order: caller checkout first (`opencode.json`,
  `.agents/skills/`); a workflow step copies these defaults only when the
  caller has none.

## Common mistakes

- Editing the `SUMMARY:` format without updating the parsing post-step in
  the same change.
- Adding a capability "just in case" to a review agent — permissions widen
  only with a justification in the description.
- Shipping a skill mentioning `intrador`, `heliowap`, or local paths —
  fallback skills stay anonymous.
