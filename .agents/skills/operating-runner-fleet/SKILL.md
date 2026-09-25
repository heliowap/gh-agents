---
name: operating-runner-fleet
description: Use when enabling, disabling, resizing, or inspecting self-hosted Actions runners on intrador-tech-vps — registering a repo or org, checking runner status, cleaning up, decommissioning.
---

# Operating the runner fleet

## Overview

Runners live on `intrador-tech-vps` under the dedicated `gh-agents` system
user (member of `docker`). They serve **private repos only** — a runner on a
public repo is remote code execution for every fork. Scripts live in
`runner/` of this repo, checked out at `/home/gh-agents/gh-agents` on the
host. Authoring rules: `docs/conventions/fleet.md`.

## Layout

| Thing | Where |
|---|---|
| Runner instances | `/home/gh-agents/runners/<escopo>/<n>/` |
| Scope name `<escopo>` | `org--<org>` or `<owner>--<repo>` |
| Units | user services `actions.runner.<name>.service` (`systemctl --user`; needs `loginctl enable-linger gh-agents` once) |
| Hygiene | `gh-agents-cleanup.timer` — daily, deletes `_work` of runners idle >7d |
| Sizing | N=2 per scope (jobs are I/O-bound on the LLM API) |

## Operations

```bash
# run as the gh-agents user on intrador-tech-vps
runner/enable-repo.sh <owner>/<repo> [N=2]   # repo-level runners
runner/enable-org.sh  <org> [N=2]            # org runners (PAT admin:org)
runner/disable-repo.sh <owner>/<repo>        # unregister → uninstall → remove dir
runner/disable-org.sh  <org>
runner/status.sh                             # units + runners via API
```

- Scripts are idempotent: re-running converges. Every run ends by *proving*
  state (units active, runner registered) — read that block, don't assume.
- `enable-*.sh` checks `visibility` and refuses public repos. If it doesn't
  refuse, stop — that's a bug, not a pass.
- Registration tokens are fetched via `gh api` (or `GH_TOKEN`), used, and
  discarded. PAT lives only in the operator's local shell — never in a
  workflow, secret, or the gh-agents repo.
- Labels: `agents` plus the self-hosted/linux/x64 defaults. Repo-level
  runners only see their own repo.

## Decommissioning (`factory-ci-*`)

Stop processes → `config.sh remove` (unregisters on GitHub) → remove
`/home/helio/actions-runner/` → remove `remove-factory-review.sh`. The old
runners have no unit files and do not survive reboot — do not "reuse" them.

## Verify

`runner/status.sh` plus `gh api repos/{o}/{r}/actions/runners` — registered,
idle, correct labels. Shellcheck + run-twice convergence before calling a
script change done (see verifying-changes).
