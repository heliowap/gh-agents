# gh-agents

Reusable GitHub Actions workflow that runs OpenCode agents — automatic PR
review, `/oc` fix on comments, CI-failure diagnosis — on a self-hosted runner
fleet. Enabled per repo by adding one caller workflow; no repo-side config is
required beyond a secret.

## Onboarding

1. Register runners for the repo (skip if an org runner already covers it):

   ```bash
   runner/enable-repo.sh owner/repo 2
   ```

2. Give the repo the key for the model's provider:

   ```bash
   gh secret set OPENCODE_API_KEY --repo owner/repo      # opencode-go models (default)
   gh secret set FIREWORKS_API_KEY --repo owner/repo     # fireworks/… models
   ```

3. Copy `templates/caller-agents.yml` to `.github/workflows/agents.yml` in the
   repo and set `on.pull_request.branches` to the repo's default branch.
4. Optional: `gh variable set AGENT_RUNNER --repo owner/repo` to pick a
   backend, `CI_RUNNER` for regular CI, or the repo's own `opencode.json` /
   `.agents/skills/` to override the defaults here.
5. Optional: install the GitHub App `gh-agents-ops` to switch runner backends
   from a panel instead of the CLI.

This repo dogfoods: `.github/workflows/dogfood.yml` calls the local
`agents.yml` via `uses: ./`, so a PR that changes the reusable workflow is
reviewed by the changed version. It runs on `ubuntu-latest` — the repo is
public, and self-hosted runners serve private repos only.

## Inputs

All inputs are optional; `secrets: inherit` plus the provider key is enough.

| Input | Default | Meaning |
|---|---|---|
| `runs-on` | `self-hosted` | Runner label fallback; the repo's `vars.AGENT_RUNNER` wins. |
| `model` | `opencode-go/glm-5.3-flash` | OpenCode model for all agents. |
| `model_fallbacks` | empty | Comma-separated `provider/model` fallbacks; every candidate is live-probed and the first that answers is used. |
| `use_container` | `true` | Run jobs in the runtime image; `false` runs on the host. |
| `runtime_image` | `ghcr.io/heliowap/gh-agents-runtime:v1` | Job image when `use_container` is true. |
| `gh_agents_ref` | `v1` | Ref of this repo used for default agents/skills/scripts. |
| `ci_workflows` | empty = all | Comma-separated workflow names ci-doctor watches. |

Secrets (arrive via `secrets: inherit` or explicit mapping): the preflight
requires the key matching the `model` provider — `OPENCODE_API_KEY` for
`opencode-go/…` (the default), `FIREWORKS_API_KEY` for `fireworks/…`. The
Fireworks provider is declared in the default `agents/opencode.json`
(OpenAI-compatible endpoint, key via `{env:FIREWORKS_API_KEY}`); a caller's
own `opencode.json` can declare others the same way.

## Runner switch

Agent jobs resolve `runs-on` as `vars.AGENT_RUNNER || inputs.runs-on`:

- Fleet-wide default: change the `runs-on` default in `agents.yml` (one edit).
- Per repo: `gh variable set AGENT_RUNNER --value <label> --repo owner/repo`.

Regular CI opts in once per workflow with `runs-on: ${{ vars.CI_RUNNER ||
'ubuntu-latest' }}`; after that the backend is a repo variable too.

Valid labels on this infrastructure:

| Value | Backend |
|---|---|
| `self-hosted` | The gh-agents fleet on `intrador-tech-vps` (private repos only) |
| `ubuntu-latest` | GitHub-hosted |
| `depot-ubuntu-24.04`, `depot-ubuntu-24.04-4`, `depot-ubuntu-24.04-8` | Depot |
| `ubicloud-standard-2` | Ubicloud |

A label with no matching runner leaves the job queued forever — check
`runner/status.sh` before switching.

## What the agents do

- **review** — on non-draft `pull_request` events (docs/`*.md` paths ignored):
  posts one comment with BLOCKING/WARNING/NIT sections, `path:line` on every
  finding, ending in `SUMMARY: N BLOCKING, N WARNING, N NIT`. When BLOCKING >
  0, a `review-blocking` issue is opened (one per PR; a closed one reopens).
  The reviewer is read-only and never approves — it comments, a human decides.
- **fix** — on comments containing `/oc` or `/opencode`, only from
  OWNER/MEMBER/COLLABORATOR and never from a bot. The substring match is a
  coarse pre-filter (`/ocaml` can queue a wasted run, never a wrong edit); the
  action's own mention parsing is the real gate. On a PR it commits to the PR
  branch; on an issue it opens a branch and a PR.
- **ci-doctor** — on `workflow_run` completed with `failure`: finds the
  associated PR, posts one diagnosis (probable cause, log evidence, suggested
  fix) ending in `<!-- ci-doctor:<sha> -->`, which is also the dedup key — one
  diagnosis per (workflow, sha). Runs with no associated PR are skipped
  silently. Diagnosis only; fixing is a human decision or `/oc`.

The caller repo keeps autonomy: its own `opencode.json` and `.agents/skills/`
win; a repo with neither gets this repo's defaults copied in at run time.

## Security model

- This repo is public so cross-owner callers can use it; it contains no
  secrets and no private topology. Provider keys arrive at run time via
  `secrets: inherit` — nothing is stored or echoed.
- External actions are pinned by full commit SHA; callers pin this workflow by
  tag (`@v1`). `main` is protected.
- Self-hosted runners serve private repos only: `enable-*.sh` checks
  visibility and refuses public repos; org runners sit in a private-only
  runner group.
- Comment triggers require a non-bot OWNER/MEMBER/COLLABORATOR — no bot
  triggers a bot.
- Jobs run in the runtime container by default. `use_container: false` runs on
  the host — use it only for repos whose tests need Docker, knowing the job
  then shares the runner host.
- Permissions are minimal per job; no job has `actions: write`. The operator
  PAT used by `runner/` scripts lives in the operator's shell, never in a
  workflow or secret.
- Fork PRs get no secrets: jobs fail fast on an empty provider key.

## Reserved paths

`.gh-agents/` is the checkout this workflow creates inside caller repos for
the default agents/skills/scripts. Do not track a `.gh-agents/` directory in a
caller repo — the name is taken.

## Operating the fleet

Scripts under `runner/` run on `intrador-tech-vps` as user `gh-agents`:

| Script | Use |
|---|---|
| `enable-repo.sh <owner>/<repo> [N=2]` | Register N repo-level runners (label `agents`) |
| `enable-org.sh <org> [N=2]` | Register N org-level runners in the private-only `gh-agents` group |
| `disable-repo.sh <owner>/<repo>` | Stop units, deregister, remove dirs |
| `disable-org.sh <org>` | Same for org runners |
| `status.sh` | Local dirs, systemd units, registered runners per scope |
| `install-cleanup.sh` | Install the daily `_work` cleanup timer (sudo) |

All are idempotent and end by proving the state they claim.
