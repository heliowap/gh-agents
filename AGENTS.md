---
name: gh-agents-conventions
description: Conventions and invariants of the gh-agents repository. Entry point loaded always; detailed conventions live in docs/conventions/ and are read only when the task touches them.
---

# gh-agents

Reusable GitHub Actions workflow that runs OpenCode agents (review, `/oc`
fix, ci-doctor) on caller repos, plus the scripts that install self-hosted
runners and the runtime image the jobs use. Public repo; other repositories
trust it.

What the product is, for whom, and the principles behind visible behaviour →
`PRODUCT.md`. Read it before changing anything a repo owner or the panel
user can see.

## Invariants: never break these

1. **No secrets, no private topology.** The repo is public; secrets arrive at
   run time via `secrets: inherit`, never stored or echoed.
2. **External actions pinned by full SHA** with a version comment; callers
   pin gh-agents by tag (`@v1`), moved only on deliberate release.
3. **Self-hosted runners serve private repos only** — `enable-*.sh` checks
   visibility and refuses public ones.
4. **No bot triggers a bot.** Comment gates require `user.type != 'Bot'` and
   `author_association` ∈ OWNER/MEMBER/COLLABORATOR. Reviewers comment; only
   humans merge.
5. **Caller repos keep autonomy** — the workflow works with zero repo-side
   config; the caller's `opencode.json` / `.agents/skills/` wins over the
   defaults here.
6. **The runner switch stays a switch** — `vars.AGENT_RUNNER` then the input
   default; never a hardcoded label.
7. **Fleet scripts are idempotent and self-verifying** — running twice
   converges; every script ends proving the state it claims.

## Pointers — read only what the task touches

| Task | Read |
|---|---|
| commit or pull request | `docs/conventions/commits.md` |
| `.github/workflows/**` | `docs/conventions/workflows.md` |
| `runner/**`, `runtime/**` | `docs/conventions/fleet.md` |
| `agents/**`, `skills/**` | `docs/conventions/agents-skills.md` |
| `.agents/skills/**` (maintainer runbooks) | `docs/conventions/maintainer-skills.md` |
| README, `docs/**`, comments | `docs/conventions/prose.md` |
| writing code or tests | `docs/conventions/testing.md` (TDD, seams, complexity budget) |
| designing an interface or module | `docs/conventions/design.md` (deep modules) |
| declaring done, opening a PR | `docs/conventions/dod.md` (per-type DoD, feedback loops) |
| visible behaviour, UI text, scope calls | `PRODUCT.md` |
| why a decision exists | `docs/specs/` |

## Before calling a change done

```bash
actionlint .github/workflows/*.yml
shellcheck runner/*.sh
```

`agents/opencode.json` validates against the opencode schema. The full DoD
per change type — and which feedback loop a red check belongs to — lives in
`docs/conventions/dod.md`. A check that applies and could not run is a
failure, never a skip.
