---
name: onboarding-a-repo
description: Use when enabling gh-agents on a repository — adding the caller workflow, setting OPENCODE_API_KEY, choosing a runner backend, or verifying a repo end-to-end.
---

# Onboarding a repo

## Overview

Enabling a repo means: runners cover it, the secret exists, and a ~20-line
caller workflow pins `heliowap/gh-agents/.github/workflows/agents.yml` by
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
3. Caller workflow at `.github/workflows/agents.yml` in the target repo:

```yaml
name: agents
on:
  pull_request:
    types: [opened, synchronize, reopened, ready_for_review]
    branches: [<default-branch>]   # caller's choice — never assumed
    paths-ignore: ['docs/**', '**/*.md']
  issue_comment:
    types: [created]
  pull_request_review_comment:
    types: [created]
  workflow_run:
    types: [completed]
    workflows: ['ci']    # required key — list the CI workflows to watch

permissions:
  contents: read

jobs:
  agents:
    # The caller job's permissions are the CEILING for the called workflow's
    # GITHUB_TOKEN — grant the union of what review/fix/ci-doctor need.
    permissions:
      contents: write
      pull-requests: write
      issues: write
      actions: read
    uses: heliowap/gh-agents/.github/workflows/agents.yml@v1
    secrets: inherit
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
