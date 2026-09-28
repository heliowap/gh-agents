# gh-agents

Reusable GitHub Actions workflow that runs OpenCode agents — PR review on
`/oc review`, `/oc` fix on comments, CI-failure diagnosis — on a self-hosted runner
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

   `openai/…` models run on a ChatGPT Plus/Pro login instead of a key — see
   [ChatGPT login](#chatgpt-login).

3. Copy `templates/caller-agents.yml` to `.github/workflows/agents.yml` in the
   repo. Set `on.pull_request.branches` to the target branch and
   `on.workflow_run.workflows` to the repo's exact CI workflow names.
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

All inputs are optional; the provider key is enough. `secrets: inherit` passes
it only when the caller has the same owner as this repo (`heliowap`); a repo in
another org or account maps it explicitly, or the key arrives empty:

```yaml
    secrets:
      OPENCODE_API_KEY: ${{ secrets.OPENCODE_API_KEY }}
      FIREWORKS_API_KEY: ${{ secrets.FIREWORKS_API_KEY }}
```

| Input | Default | Meaning |
|---|---|---|
| `runs-on` | `self-hosted` | Runner label fallback; the repo's `vars.AGENT_RUNNER` wins. |
| `model` | `opencode-go/glm-5.3-flash` | OpenCode model for all agents: `provider/model`, or `provider/model#variant` to set the reasoning effort (`openai/gpt-6-luna#xhigh`). |
| `model_fallbacks` | empty | Comma-separated `provider/model` fallbacks; every candidate is live-probed and the first that answers is used. |
| `use_container` | `true` | Run jobs in the runtime image; `false` runs on the host. |
| `runtime_image` | `ghcr.io/heliowap/gh-agents-runtime:v1` | Job image when `use_container` is true. |
| `gh_agents_ref` | `v1` | Ref of this repo used for default agents/skills/scripts. |
| `ci_workflows` | empty = all | Comma-separated workflow names ci-doctor watches — it only narrows what the caller's `on.workflow_run.workflows` list already woke; watch-all needs every CI workflow named there. |

Secrets (arrive via `secrets: inherit` or explicit mapping): the preflight
requires the key matching the `model` provider — `OPENCODE_API_KEY` for
`opencode-go/…` (the default), `FIREWORKS_API_KEY` for `fireworks/…`. The
Fireworks provider is declared in the default `agents/opencode.json`
(OpenAI-compatible endpoint, key via `{env:FIREWORKS_API_KEY}`); a caller's
own `opencode.json` can declare others the same way. `openai/…` needs no
secret: the preflight checks for the ChatGPT login below.

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

## ChatGPT login

`openai/…` models can run on a ChatGPT
Plus/Pro subscription instead of an API key. The login lives in one file on
the runner host. It is never a GitHub secret: its refresh token rotates each
time it is used, so a copy in a secret stops working after the first refresh.

1. On the runner host, as the runner user, log in once. Choose OpenAI, then
   `ChatGPT Pro/Plus (headless)`; it prints a code to confirm from a browser on
   another machine:

   ```bash
   sudo -iu gh-agents opencode auth login
   sudo -iu gh-agents opencode auth list      # openai shows as oauth
   ```

2. Point the repo (or the whole org) at that file:

   ```bash
   gh variable set AGENT_OPENCODE_AUTH --repo owner/repo \
     --body /home/gh-agents/.local/share/opencode/auth.json
   ```

3. Set the model in the caller workflow. `#variant` sets the reasoning effort,
   and the `-fast` model id is OpenAI's priority tier (fast mode):

   ```yaml
   with:
     model: openai/gpt-6-luna-fast#xhigh
   ```

With the variable set, each agent job mounts the file into the container,
copies it to where opencode reads it, and writes a refreshed OAuth entry back
to the host after the run. It writes back only when the entry is newer than
the host's, so an older job never undoes a newer refresh. Host-mode jobs
(`use_container: false`) read the file in place.

Limits:

- A GitHub-hosted runner has no shared ChatGPT login file. Without a
  credentialed fallback, preflight fails naming `AGENT_OPENCODE_AUTH`.
- Every repo that sets the variable spends the same ChatGPT account's limits.
- Two jobs that refresh at the same moment can race. Re-run the failed job.
  If the login stays broken, log in again (step 1). When `model_fallbacks`
  includes an API-key model with credentials, a missing login lets the job
  probe that fallback instead.
- The `/oc` fixer and the reviewer run shell commands in the job, so they can
  read the login, just as they can read the provider keys in their
  environment. Enable it only where you already trust the agents with keys.

## What the agents do

- **review** — only on request: comment `/oc review` on a PR. Nothing is
  reviewed on push or when a PR opens. In a private repo any human can ask
  (only people with access can comment there); in a public repo only
  OWNER/MEMBER/COLLABORATOR. Never a bot. It reacts with 👀, then
  posts one comment with BLOCKING/WARNING/NIT sections, `path:line` on every
  finding, ending in `SUMMARY: N BLOCKING, N WARNING, N NIT`. When BLOCKING >
  0, a `review-blocking` issue is opened (one per PR; a closed one reopens).
  Only this run's review counts; with no `SUMMARY` line the step leaves a
  warning instead of guessing zero. The reviewer is read-only and never
  approves — it comments, a human decides. The review runs `opencode run
  --agent reviewer` directly, not the opencode GitHub action, because the
  action refuses anyone without write permission. The session is then
  checked: a review that did not run as `reviewer` fails red. The job holds
  the provider keys, so the agent config that can grant permissions or run
  code (`opencode.json(c)`, `.opencode/`, `.agents/skills/`) is taken from the
  PR's base branch, never from the PR; plugins are off (`--pure`).
- **fix** — on PR comments containing `/oc` or `/opencode` (other than
  `/oc review`), only from OWNER/MEMBER/COLLABORATOR and never from a bot. The substring match is a
  coarse pre-filter (`/ocaml` can queue a wasted run, never a wrong edit); the
  action's own mention parsing is the real gate. It commits to the PR branch;
  commands on ordinary issues do not run by default. Set `allow_issue_fix: true`
  on the caller to accept them; an issue fix checks out and may push to the
  default branch, subject to its branch protection.
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
  `secrets: inherit` or explicit mapping — nothing is stored or echoed.
- External actions are pinned by full commit SHA; callers pin this workflow by
  tag (`@v1`). `main` is protected.
- Self-hosted runners serve private repos only: `enable-*.sh` checks
  visibility and refuses public repos; org runners sit in a private-only
  runner group.
- Comment triggers require a non-bot OWNER/MEMBER/COLLABORATOR — no bot
  triggers a bot. The one exception is `/oc review` in a private repo, open
  to any human; the reviewer only reads and comments, with its config taken
  from the base branch.
- Jobs run in the runtime container by default. `use_container: false` runs on
  the host — use it only for repos whose tests need Docker, knowing the job
  then shares the runner host.
- Permissions are minimal per job; no job has `actions: write`. The operator
  PAT used by `runner/` scripts lives in the operator's shell, never in a
  workflow or secret.
- Fork PRs get no secrets: jobs fail fast on an empty provider key.
- The ChatGPT login stays on the runner host, outside the repo and GitHub
  secrets; only repos with `vars.AGENT_OPENCODE_AUTH` set mount it.

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
| `setup-ci-user.sh [user=gh-ci]` | Prepare the separate CI user with rootless Docker (sudo) |

All are idempotent and end by proving the state they claim.

### CI runners

A repo's regular CI can run on the host too, but never as `gh-agents`: CI runs
PR code directly on the host, and `gh-agents`' home holds every fleet runner's
credentials and the ChatGPT login. CI runners live under a separate user
(`gh-ci`) with its own rootless Docker and no access to that home:

```bash
sudo runner/setup-ci-user.sh            # once; ends proving the isolation
sudo -iu gh-ci env RUNNER_ROLE=ci DOCKER_HOST=unix:///run/user/$(id -u gh-ci)/docker.sock \
  GH_TOKEN="$(gh auth token)" bash -lc '~/gh-agents/runner/enable-repo.sh owner/repo 3'
```

`RUNNER_ROLE=ci` registers runners named `<scope>-ci-<n>` with only the `ci`
label (`--no-default-labels`): they never take the agent runners'
registration, and an agent job asking for `self-hosted` never lands on them.
The repo opts in with `runs-on: ${{ vars.CI_RUNNER || '<hosted label>' }}` and
`gh variable set CI_RUNNER --body ci`. The host has 4 vCPUs shared with the
agents; expect a slower heavy tier than on hosted runners.
