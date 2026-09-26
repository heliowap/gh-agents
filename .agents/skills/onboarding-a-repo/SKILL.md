---
name: onboarding-a-repo
description: Use when enabling gh-agents on a repository — adding the caller workflow, setting OPENCODE_API_KEY, choosing a runner backend, or verifying a repo end-to-end.
---

# Onboarding a repo

## Overview

Enabling a repo means: runners cover it, the secret exists, and a caller
workflow pins `heliowap/gh-agents/.github/workflows/agents.yml` by
tag. The repo keeps autonomy — everything below the caller file is optional.

## Checklist

1. Runners: on `intrador-tech-vps` as the `gh-agents` user (`ssh
   intrador-tech-vps`, then `sudo -iu gh-agents`), run
   `runner/enable-repo.sh owner/repo 2` (see operating-runner-fleet) — or
   the repo is already covered by an org-runner; check first with
   `gh api repos/{owner}/{repo}/actions/runners` and `runner/status.sh`.
   Private repos only.
2. Secret: `gh secret set OPENCODE_API_KEY --repo owner/repo -b "$KEY"`
   (or omit `-b` for an interactive prompt).
3. Copy this repo's `templates/caller-agents.yml` to the target repo's
   `.github/workflows/agents.yml`. Keep its caller-side comment gate and
   concurrency group: without them, unrelated comments can cancel a fixer or
   an in-flight review. Set `pull_request.branches` to the target branch and
   `workflow_run.workflows` to the exact CI workflow names. The caller job's
   permissions are the ceiling for the reusable workflow's token; keep the
   template's `actions: read`, `contents: write`, `pull-requests: write`, and
   `issues: write` grants.

   `secrets: inherit` only reaches a reusable workflow of the same owner. A
   repo outside `heliowap` (e.g. an org repo) maps each key explicitly, or the
   preflight fails with an empty key:

```yaml
    secrets:
      OPENCODE_API_KEY: ${{ secrets.OPENCODE_API_KEY }}
      FIREWORKS_API_KEY: ${{ secrets.FIREWORKS_API_KEY }}
```

4. Optional per-repo config:
   - `gh variable set AGENT_RUNNER --repo owner/repo -b ubuntu-latest` —
     overrides the central `inputs.runs-on` default (`'self-hosted'`). Set
     only to move a repo *off* the fleet; self-hosted needs no variable.
   - Convert CI workflows to the switch once:
     `runs-on: ${{ vars.CI_RUNNER || 'ubuntu-latest' }}`, then the backend
     is a repo variable.
   - Repo-local `opencode.json` / `.agents/skills/` — wins over the
     gh-agents defaults.
   - Valid `runs-on` values: `self-hosted`, `ubuntu-latest`,
     `depot-ubuntu-24.04[-4|-8]`, `ubicloud-standard-2`.
5. Optional: install the `gh-agents-ops` GitHub App for dashboard-driven
   switching (spec B).

## Verify end-to-end

Open a test PR → the `review` job runs on the expected backend (check the
runner name in `gh run view --log`) → comment `/oc` → fixer commits → break
CI → ci-doctor comments a diagnosis → flip `vars.AGENT_RUNNER` → the next
job lands on a different backend.

## Common mistakes

- Enabling a public repo — the scripts refuse; if somehow registered, remove
  it immediately.
- Pinning `@main` or a branch instead of the `@v1` tag.
- Setting `AGENT_RUNNER` on a repo whose workflow hardcodes `runs-on:` —
  the switch only exists where the `vars.X || default` pattern does.
