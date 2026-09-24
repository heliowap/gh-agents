# Fleet scripts (`runner/`) and runtime image (`runtime/`)

## Shell scripts

- `#!/usr/bin/env bash`, `set -euo pipefail`, `--help` on no arguments.
- Narrate: `echo "==> o que está acontecendo"` antes de cada fase, e um bloco
  de verificação no final que prova o estado (units ativas, runner
  registrado, porta livre) em vez de declará-lo.
- Anything that needs GitHub takes it from `gh` or `GH_TOKEN` in the
  environment; nothing is baked in. Registration tokens are fetched, used,
  and discarded.
- Idempotent: state check first, act only on the gap. `disable-*` removes
  registration, units, and directories, in that order.
- Naming: `<escopo>` is `org--<org>` or `<owner>--<repo>`; directories are
  `/home/gh-agents/runners/<escopo>/<n>`; unit names are whatever `svc.sh`
  generates — scripts query, never invent.
- `enable-*.sh` checks repo visibility and refuses public repos — a runner on
  a public repo is remote code execution for every fork.

## Runtime image

- Base image pinned at least to a major tag; installed tools are the ones the
  agents need (node for the actions runtime, git, gh, python3, curl) — each
  with a line saying who needs it.
- Published as `ghcr.io/heliowap/gh-agents-runtime:<tag>`; workflows
  reference a tag, never `latest`. Adding a tool bumps the tag.
- No credentials, no `GITHUB_TOKEN`, no user home baked in.
