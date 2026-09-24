---
name: verifying-changes
description: Use when about to report a change in this repo as done, before committing or opening a PR — covers workflows, runner scripts, runtime image, agents, skills, docs, and code.
---

# Verifying changes

## Overview

"Done" here means the DoD row for the change type is green **with evidence**,
not that the diff looks right. A check that applies and could not run is a
failure — a missing tool counts as red, never as a skip. Say what is missing
instead of declaring done. Full rules: `docs/conventions/dod.md`.

## Local loop (cheapest first, re-run until green)

| Change touched | Run | Green means |
|---|---|---|
| `.github/workflows/*.yml` | `actionlint .github/workflows/*.yml` | clean **and** exercised on a real caller repo (link the run; if not exercised, the PR says so plainly) |
| `runner/*.sh` | `shellcheck runner/*.sh` | clean; script ran twice and converged; its verification-block output is captured |
| `agents/opencode.json` | `jq empty agents/opencode.json` + schema validation (CI) | schema-valid; every agent named in a workflow `with:` exists |
| `runtime/Dockerfile` | `docker build runtime/` | image builds; tag bumped; a job ran on it (run link) |
| Python helpers | `pytest` + `ruff --select C901` | tests pass; complexity ≤ 10 — see `docs/conventions/testing.md` |
| Go | `go test ./...` + `gocyclo -over 10` | same |
| `docs/**` only | re-read the rendered text | every claim verified or marked `NÃO VERIFICADO` — see `docs/conventions/prose.md` |
| `skills/*.md`, agent prompts | a run log showing old failure → new output | behaviour evidence, not style preference |
| dashboard UI (spec B repo) | TestSprite `test run <id> --local <port>` to a verdict | verdict green, or "unverified" declared — never silently skipped |

## DoD evidence per change type

The PR carries the evidence column from `docs/conventions/dod.md`: terminal
output for scripts, a run link for workflows and images, a before/after log
for agent/prompt changes, red→green history for code.

## Escalation

Red output is not interpreted — it is fixed or escalated. Order: local loop →
TestSprite (UI) → this repo's own `agents.yml` review → directed `/oc` →
spec/plan review for large changes. A loop that failed twice on the same
hypothesis goes up one level: the hypothesis is probably wrong, not the
execution. Never let a bot trigger a bot — review does not summon the fixer.

## Common mistakes

- Reporting "done" with only `actionlint` green on a workflow never exercised
  on a caller — say "not exercised" in the PR instead.
- Treating an absent tool (no `shellcheck`, no TestSprite credential) as
  not-applicable. It is a failed check; name it.
- Fixing review findings without re-running the loop that produced them.
