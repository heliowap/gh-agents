---
name: editing-workflows
description: Use when creating or modifying files under .github/workflows/ — jobs, triggers, permissions, inputs, concurrency, container images, or action pins.
---

# Editing workflows

## Overview

`.github/workflows/agents.yml` is a public reusable workflow that stranger
repos call with `secrets: inherit`. Every line is part of a trust boundary.
Rules live in `docs/conventions/workflows.md`; this is the pre-flight
checklist for changing it.

## Checklist — every item applies unless the diff says why not

- [ ] `permissions: contents: read` at top level; each job widens by name.
      No job gets `actions: write`. Minimum per job: review →
      `contents:read, pull-requests:write, issues:write`; fix → adds
      `contents:write`; ci-doctor → `actions:read` instead of write.
- [ ] Every job has `timeout-minutes` and a `concurrency` group keyed by
      `event_name` + PR/issue number — a comment must never cancel an
      in-flight review (intrador #1417).
- [ ] `runs-on: ${{ vars.AGENT_RUNNER || inputs.runs-on }}` — never a
      hardcoded label. The switch stays a switch.
- [ ] Untrusted values (comment bodies, PR titles, `workflow_run` fields)
      reach `run:` via `env:`, never `${{ }}` inside the script.
- [ ] Comment-trigger `if:` gates on `user.type != 'Bot'` and
      `author_association` ∈ OWNER/MEMBER/COLLABORATOR. No bot triggers a bot.
- [ ] Every `if:` encoding a rule carries a comment naming the rule.
- [ ] External actions pinned by full SHA with a trailing version comment
      (`uses: actions/checkout@<sha> # v6`). The opencode action is pinned
      by tag (`@vX`), never `@latest`.
- [ ] Inputs have descriptions and defaults that work with
      `secrets: inherit` and nothing else. No branch-name assumptions —
      `dev` is the caller's `on.pull_request.branches` choice.
- [ ] Header comment states what the workflow is *not* (not a merge gate).
- [ ] No secrets echoed, no private topology. Secrets arrive only via
      `secrets: inherit` at run time.

## Verify

`actionlint` clean locally, then exercise on a real caller repo before
declaring done — see the verifying-changes skill.

## Common mistakes

- Adding an input to `agents.yml` without noticing it is a breaking contract
  change (see the releasing-gh-agents skill — `!` + major tag).
- Referencing `vars.AGENT_RUNNER` as if it resolved in gh-agents' context —
  it resolves in the *caller's*. Fallback: caller passes `with: runs-on:`.
- `use_container: false` leaks jobs onto the host — keep default `true`,
  document the exception for repos whose tests need Docker.
