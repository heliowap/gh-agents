---
name: gh-agents-conventions
description: Conventions and invariants of the gh-agents repository. Use before writing or reviewing anything here - a workflow in .github/workflows/, a fleet script in runner/, an agent definition or prompt in agents/ or skills/, the runtime image, a commit message, a pull request, or docs prose.
---

# gh-agents conventions

gh-agents is a public repository that other repositories trust: its reusable
workflow runs OpenCode agents (review, `/oc` fix, ci-doctor) on caller repos,
and its scripts install self-hosted runners on a real server. Rules here are
stricter about safety and supply chain than about taste. Design decisions
live in `docs/specs/`; this file is the short version of how things are done,
to apply while working. When a spec and this file disagree, the spec wins and
this file should be fixed.

There is no formatter and no linter in the conventional sense. The style is
kept by reading the file around an edit and matching it. `actionlint` and
`shellcheck` catch mechanics, not judgment.

## Invariants: never break these

1. **The repository contains no secrets and no private topology.** It is
   public; treat every line as published. Secrets reach the workflow at run
   time through `secrets: inherit` from the caller — never stored, never
   echoed, never in a comment. Registration tokens are short-lived and fetched
   by the fleet scripts at run time.
2. **External actions are pinned by full commit SHA** with the version in a
   trailing comment (`uses: actions/checkout@<sha> # v6`). Callers pin
   gh-agents itself by tag (`@v1`); the floating major tag moves only on a
   deliberate release.
3. **Self-hosted runners serve private repositories only.** `enable-*.sh`
   must check repo visibility and refuse a public repo. A runner registered
   to a public repo is a remote-code-execution offer to every fork.
4. **No bot triggers a bot.** Every comment gate requires
   `user.type != 'Bot'` plus `author_association` in OWNER/MEMBER/COLLABORATOR.
   The reviewer comments; it never approves, never requests changes, never
   edits. Review is advisory — a human merges.
5. **Caller repos keep autonomy.** The reusable workflow works with zero
   repo-side configuration, and a caller's own `opencode.json` /
   `.agents/skills/` always wins over the defaults shipped here. A change
   that requires editing every caller is a breaking change.
6. **The runner switch stays a switch.** `runs-on` resolves through
   `vars.AGENT_RUNNER` then the workflow input default. Never hardcode a
   fleet label where a variable can carry it; the dashboard operates the
   variables, not the YAML.
7. **Fleet scripts are idempotent and verify themselves.** Running
   `enable-repo.sh` twice converges to the same state. Every script ends by
   checking the state it claims to have produced, the way
   `remove-factory-review.sh` did.

## Commits and pull request titles

Conventional Commits. Callers pin `@v1`-style tags, so releases are
deliberate: a maintainer tags after merge, there is no release automation yet.

```
<type>[(scope)][!]: <what changes for callers or operators, imperative, lower case, no full stop>
```

- `feat` = callers can do something new or must do something differently.
- `fix` = something wrong is now right. `perf` = same behaviour, cheaper.
- `docs`, `test`, `refactor`, `build`, `ci`, `chore` = no release.
- `!` when callers must change something (renamed input, dropped job).
  Breaking changes to `agents.yml` inputs also bump the floating major tag.
- Scope names the part: `review`, `fix`, `ci-doctor`, `fleet`, `runtime`,
  `agents`, `skills`.

The subject is written for a repo owner enabling the service, not a reader of
the diff: `fix: keep comment triggers from cancelling an in-flight review`,
not `fix: change concurrency group`. Pick the type by what the caller
notices, not by which file changed. The body says why when the diff does not.

No tool or AI attribution in commits or pull requests: no `Co-Authored-By`
trailers, no "Generated with" lines.

## Workflows (`.github/workflows/`)

- `permissions: contents: read` at the top; each job asks for more, by name.
  No job gets `actions: write`.
- Every job has `timeout-minutes` and a `concurrency` group keyed by
  `event_name` plus the PR/issue number — a comment must never cancel an
  in-flight review (intrador #1417).
- Untrusted values (comment bodies, PR titles, workflow_run fields) reach
  `run:` scripts through `env:`, never through `${{ }}` inside the script.
- Every `if:` that encodes a rule carries a comment saying which rule, in the
  file header or inline. The header comment states what the workflow is
  *not*: not a merge gate, not a reviewer of promotion PRs.
- Inputs have descriptions and defaults that make the workflow usable with
  `secrets: inherit` and nothing else.
- A reusable workflow never assumes a branch name: `dev` is the caller's
  `on.pull_request.branches` choice, not ours.

## Fleet scripts (`runner/`)

- `#!/usr/bin/env bash`, `set -euo pipefail`, `--help` on no arguments.
- Narrate: `echo "==> o que está acontecendo"` antes de cada fase, e um bloco
  de verificação no final que prova o estado (units ativas, runner
  registrado, porta livre) em vez de declará-lo.
- Anything that needs GitHub takes it from `gh` or `GH_TOKEN` in the
  environment; nothing is baked in. Tokens de registro são buscados, usados e
  descartados.
- Idempotent: state check first, act only on the gap. `disable-*` removes
  registration, units, and directories, in that order.
- Naming: `<escopo>` é `org--<org>` ou `<owner>--<repo>`; diretórios
  `/home/gh-agents/runners/<escopo>/<n>`; units são as que `svc.sh` gera —
  scripts não inventam nome de unit, consultam.

## Agents, prompts and skills (`agents/`, `skills/`)

- Agent permissions are deny-by-default. Review-type agents enumerate the
  bash patterns they may run (`git diff*`, `gh pr view*`) and deny
  edit/webfetch/websearch. Write-capable agents justify it in their
  description.
- A prompt is behaviour-shaping code, not prose. It ends with the output
  contract the workflow depends on (`SUMMARY: N BLOCKING, ...`) because a
  later step parses it. Changing a prompt requires evidence — a run log
  showing the failure it fixes — not a style preference.
- Skills here are generic fallbacks: no project names, no repo-specific
  paths, nothing that would be wrong inside a stranger's repository. A repo
  that needs tailored skills carries its own `.agents/skills/` — that is the
  whole point of the fallback order.
- `opencode.json` validates against the opencode schema; every agent listed
  in a workflow `with:` exists in `agents/opencode.json` or the caller's own.

## Runtime image (`runtime/`)

- Base image pinned at least to a major tag; tools installed are the ones the
  agents need (node for the actions runtime, git, gh, python3, curl) — each
  with a line saying who needs it.
- The image is published as `ghcr.io/heliowap/gh-agents-runtime:<tag>` and
  workflows reference a tag, never `latest`. Adding a tool bumps the tag.
- No credentials, no `GITHUB_TOKEN`, no user home baked in.

## Docs prose (README, specs, comments)

- Plain, short, declarative sentences for a repo owner deciding whether to
  trust this. Lead with the point.
- Exact about limits and the unverified: "verified on repo-level runners,
  org-level pending" is a sentence worth keeping; rounding a caveat away is a
  bug. `NÃO VERIFICADO` in the text beats a confident guess.
- Tables for symptom/cause/fix and option/meaning shapes. Commands in fenced
  `bash` blocks, runnable as written. Identifiers, flags, paths and variable
  names in backticks.
- No emoji, no marketing adjectives, no "simply"/"just". Sentence-case
  headings. Prose wraps near 100 columns; tables and URLs may run long.
- Português e inglês valem; siga a consistência local do arquivo tocado.
  Specs de design podem ser em português; mensagens voltadas a usuários de
  CI (comentários que os agents postam) seguem o idioma do repo alvo.

## Before calling a change done

```bash
actionlint .github/workflows/*.yml
shellcheck runner/*.sh
opencode validate   # ou: jq contra o schema de agents/opencode.json
```

Workflow behaviour is verified on a real caller repo before the tag moves:
open a test PR, comment `/oc`, break CI. A change that cannot be exercised
says so in the PR description instead of claiming it works.
