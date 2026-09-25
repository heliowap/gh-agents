# gh-agents v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the approved Spec A into the working `heliowap/gh-agents` repo: reusable `agents.yml` workflow (review/fix/ci-doctor), default agents + fallback skills, runtime image, fleet scripts, caller template, README, repo CI — verified by lint, unit tests, docker build and an e2e run on a scratch repo.

**Architecture:** One public repo. A reusable workflow checked out by caller repos; callers keep their own `opencode.json`/`.agents/skills/` and a seed step copies this repo's defaults only where the caller is missing them. Jobs run on `vars.AGENT_RUNNER || inputs.runs-on`, in a container image published to ghcr by `build-runtime.yml`. Fleet scripts run on `intrador-tech-vps` as user `gh-agents`.

**Tech Stack:** GitHub Actions YAML, bash (`set -euo pipefail`), python3 + pytest, bats, Dockerfile (ubuntu:24.04 + node22 + gh + git + python3 + opencode), `anomalyco/opencode/github` action pinned by SHA.

**Spec:** `docs/specs/2026-09-24-gh-agents-design.md` — read it; the plan argues from it.

## Global Constraints

Copied from the spec and `docs/conventions/` — every task's requirements implicitly include these:

- Repo is **public**: no secrets, no private topology in any file; PATs live only in the operator's shell.
- External `uses:` actions pinned by **full SHA** with `# vX.Y.Z` trailing comment (convention stricter than spec's "tag pin" — a SHA pin satisfies both).
- Self-hosted runners serve **private repos only**: `enable-*.sh` verifies `visibility` and aborts on public; org runners go into a runner group with `visibility: private`.
- Comment gates require `user.type != 'Bot'` **and** `author_association` ∈ OWNER/MEMBER/COLLABORATOR. No bot triggers a bot.
- `runs-on: ${{ vars.AGENT_RUNNER || inputs.runs-on }}` in every agent job; never a hardcoded label. Default `'self-hosted'`.
- `permissions: contents: read` at workflow top level; jobs ask for more by name; no job gets `actions: write`.
- Every job: `timeout-minutes` + `concurrency` keyed by `event_name` + PR/issue (a comment must never cancel an in-flight review — intrador #1417).
- Untrusted values (comment bodies, workflow_run fields) reach `run:` via `env:`, never `${{ }}` inside the script.
- Caller autonomy: caller's `opencode.json` / `.agents/skills/` wins; a repo with neither works via the seed step.
- Container switch: `container: ${{ inputs.use_container && inputs.runtime_image || '' }}` — empty string = no container (verified: `container: ''` → silent null at runtime; `container: {image: ''}` errors, so use the bare-string form).
- Fleet scripts: `#!/usr/bin/env bash`, `set -euo pipefail`, `--help` on no args, idempotent, `echo "==>"` narration, verification block at the end proving state.
- Commits: Conventional Commits, scope = `review|fix|ci-doctor|fleet|runtime|agents|skills`, no AI attribution (commits.md overrides the default Devin trailer).
- opencode action pin: `anomalyco/opencode/github@3a103fe0aff726a4edc7492f03f7b88195d9e4c9 # v2.0.16`.
- `actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1`.
- Pinned docker actions: `docker/setup-buildx-action@f87e5991a6d7451dcb8d9637bfbc97413f497069 # v4.4.1`, `docker/login-action@dbcb813823bdd20940b903addbd779551569679f # v4.6.0`, `docker/build-push-action@c3c9e263c25d99ce0380d002d59b67737d91b0dc # v7.4.0`.
- Runtime image ref in `agents.yml` default: `ghcr.io/heliowap/gh-agents-runtime:v1` (from `runtime/VERSION`, never `latest`).

## Review Focus

Input classes the spec implies but no task's tests exercise — the five most likely to bite:

1. **`/oc` as substring** (`/ocaml`, `/octocat`) — `contains()` in the job `if:` is a coarse pre-filter; the action's own mention parsing is the real gate. Expectation: at worst a wasted run, never a wrong edit. Documented in README.
2. **Fork PRs** — GitHub withholds secrets from fork runs, so `OPENCODE_API_KEY` arrives empty. Expectation: fail fast with a clear message, not a cryptic auth error → covered by the `Preflight` step in Task 4 and a bats-style assertion is N/A; e2e notes it.
3. **`.gh-agents` path collision** — a caller that already has a `.gh-agents/` directory would collide with the defaults checkout. Expectation: documented in README as a reserved path; seed step is additive and never overwrites caller files.
4. **`AGENT_RUNNER` set to a nonexistent label** — job queues forever; no in-workflow detection exists. Expectation: valid values documented (README + spec); `status.sh` shows runners per scope so the operator can see the gap.
5. **`workflow_run` without an associated PR** (failure on default branch, scheduled run) — must skip silently with a log line, not error. Covered by the `gate` step in Task 4; e2e verifies.

---

### Task 1: Verification tooling + `scripts/review_blocking.py` (TDD)

**Files:**
- Create: `scripts/review_blocking.py`
- Test: `scripts/tests/test_review_blocking.py`
- Create: `scripts/tests/__init__.py` (empty, so pytest resolves the package cleanly)

**Interfaces:**
- Produces: `blocking_count(text: str) -> int | None`; `latest_review(comments: list[dict]) -> dict | None`; CLI `python3 scripts/review_blocking.py [--comments]` reading stdin, printing `{"blocking": N, "block": str, ["url": str]}` and exiting 0 even without a SUMMARY line.
- Consumed by: the `review` job in `agents.yml` (Task 4), invoked as `.gh-agents/scripts/review_blocking.py --comments`.

- [ ] **Step 1: Install local verification tools (missing per DoD = failure, not skip)**

```bash
# actionlint — static binary to ~/.local/bin
mkdir -p ~/.local/bin /tmp/actionlint
curl -fsSL https://github.com/rhysd/actionlint/releases/latest/download/actionlint_linux_amd64.tar.gz -o /tmp/actionlint/a.tgz
tar xzf /tmp/actionlint/a.tgz -C /tmp/actionlint && install /tmp/actionlint/actionlint ~/.local/bin/

# shellcheck — apt if possible, else static binary
sudo apt-get install -y shellcheck || \
  (curl -fsSL https://github.com/koalaman/shellcheck/releases/latest/download/shellcheck-stable.linux.x86_64.tar.xz | tar -xJ -C /tmp && install /tmp/shellcheck-stable/shellcheck ~/.local/bin/)

# bats — via npm if present, else git clone to ~/.local
sudo apt-get install -y bats || npm i -g bats || \
  (git clone --depth 1 https://github.com/bats-core/bats-core /tmp/bats && /tmp/bats/install.sh ~/.local)

# pytest — user pip or venv
python3 -m pip install --user pytest || (python3 -m venv ~/.venv-gh-agents && ~/.venv-gh-agents/bin/pip install pytest)
```

Run: `actionlint --version && shellcheck --version && bats --version && python3 -m pytest --version`
Expected: all four print versions. If any fails, stop and fix — DoD requires them.

- [ ] **Step 2: Write the failing tests**

`scripts/tests/test_review_blocking.py`:

```python
"""Seam: the module's public functions + the CLI contract the workflow parses."""

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from review_blocking import blocking_count, latest_review

SCRIPT = Path(__file__).resolve().parents[1] / "review_blocking.py"


def _comment(login, body, created="2026-09-24T10:00:00Z", url="https://example/c/1"):
    return {"user": {"login": login}, "body": body, "created_at": created, "html_url": url}


def test_blocking_count_reads_summary():
    assert blocking_count("BLOCKING\n- x\nSUMMARY: 2 BLOCKING, 1 WARNING, 0 NIT") == 2


def test_blocking_count_none_without_summary():
    assert blocking_count("looks fine") is None


def test_latest_review_picks_latest_bot_comment_with_summary():
    older = _comment("github-actions[bot]", "SUMMARY: 3 BLOCKING, 0 WARNING, 0 NIT",
                     created="2026-09-24T09:00:00Z")
    newer = _comment("github-actions[bot]", "SUMMARY: 0 BLOCKING, 0 WARNING, 0 NIT",
                     created="2026-09-24T11:00:00Z")
    human = _comment("heliowap", "SUMMARY: 9 BLOCKING, 0 WARNING, 0 NIT",
                     created="2026-09-24T12:00:00Z")
    assert latest_review([newer, human, older]) is newer


def test_latest_review_empty():
    assert latest_review([]) is None
    assert latest_review([_comment("heliowap", "hi")]) is None


def test_cli_comments_outputs_url_and_block():
    body = "BLOCKING\n- foo.py:10 bad\n\nWARNING\n  (nenhum)\n\nSUMMARY: 1 BLOCKING, 0 WARNING, 0 NIT"
    comments = json.dumps([_comment("github-actions[bot]", body, url="https://example/c/9")])
    out = subprocess.run([sys.executable, str(SCRIPT), "--comments"],
                         input=comments, capture_output=True, text=True)
    assert out.returncode == 0
    data = json.loads(out.stdout)
    assert data["blocking"] == 1 and data["url"] == "https://example/c/9"
    assert "foo.py:10" in data["block"]


def test_cli_missing_summary_exits_zero_with_warning():
    out = subprocess.run([sys.executable, str(SCRIPT)],
                         input="no summary here", capture_output=True, text=True)
    assert out.returncode == 0
    assert json.loads(out.stdout)["blocking"] == 0
    assert "SUMMARY" in out.stderr
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python3 -m pytest scripts/tests/ -v`
Expected: FAIL (`ModuleNotFoundError: review_blocking`).

- [ ] **Step 4: Write `scripts/review_blocking.py`**

Generic adaptation of intrador-platform's `scripts/review_blocking.py` — same logic, repo-agnostic docstring:

```python
#!/usr/bin/env python3
"""Read the reviewer's comment (stdin) and emit JSON: BLOCKING count and block.

Usage: python3 scripts/review_blocking.py < comment.md
       python3 scripts/review_blocking.py --comments < comments.json (adds url)
Output: {"blocking": N, "block": "<BLOCKING block text or empty>"}

The count comes from the `SUMMARY: N BLOCKING, ...` line — the reviewer writes
`BLOCKING\n  (none)` when it is zero, so the block cannot serve as the count.
No SUMMARY (off-format review) -> 0 plus a stderr warning; exit is always 0,
the open-issue decision belongs to the YAML (.github/workflows/agents.yml).

`blocking_count` is importable; do not copy the regex into callers.
"""

import argparse
import json
import re
import sys
from datetime import datetime

_SUMMARY = re.compile(r"^SUMMARY:\s*(\d+)\s+BLOCKING", re.MULTILINE)
_BOT_LOGIN = "github-actions[bot]"


def blocking_count(text: str) -> int | None:
    """N from the SUMMARY line; None when the comment has no such line."""
    match = _SUMMARY.search(text)
    return int(match.group(1)) if match else None


def latest_review(comments: list[dict]) -> dict | None:
    """Latest valid-SUMMARY comment from the bot, regardless of page order."""
    return max(
        (c for c in comments
         if c["user"]["login"] == _BOT_LOGIN and blocking_count(c["body"]) is not None),
        key=lambda c: datetime.fromisoformat(c["created_at"]),
        default=None,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--comments", action="store_true",
                        help="stdin: JSON array of comments; includes url in output")
    args = parser.parse_args()
    review = latest_review(json.load(sys.stdin) or []) if args.comments else None
    text = (review or {}).get("body", "") if args.comments else sys.stdin.read()
    blocking = blocking_count(text)
    if blocking is None:
        print("review_blocking: SUMMARY line absent; treating as 0 BLOCKING", file=sys.stderr)
        blocking = 0
    block = re.search(r"^BLOCKING\n(.*?)(?=^\S|\Z)", text, re.MULTILINE | re.DOTALL)
    out = {"blocking": blocking, "block": block.group(1).strip("\n") if block and blocking else ""}
    if args.comments:
        out["url"] = (review or {}).get("html_url", "")
    print(json.dumps(out))
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python3 -m pytest scripts/tests/ -v`
Expected: 6 PASSED.

- [ ] **Step 6: Commit**

```bash
git add scripts/
git commit -m "feat(review): add review_blocking parser for BLOCKING-to-issue step"
```

---

### Task 2: `agents/opencode.json` + generic fallback `skills/`

**Files:**
- Create: `agents/opencode.json`
- Create: `skills/code-review/SKILL.md`, `skills/implement/SKILL.md`, `skills/tdd/SKILL.md`, `skills/diagnosing-bugs/SKILL.md`

**Interfaces:**
- Produces: agents `reviewer`, `fixer`, `ci-doctor` (all `mode: primary`) — the names `agents.yml` passes to the action's `agent:` input and to `opencode run --agent`.
- Produces: skill names `code-review`, `implement`, `tdd`, `diagnosing-bugs` that the agent prompts reference and the seed step copies into `.agents/skills/`.
- Generic rule (agents-skills.md): no project names, no repo-specific paths, nothing wrong inside a stranger's repo.

- [ ] **Step 1: Write `agents/opencode.json`**

```json
{
  "$schema": "https://opencode.ai/config.json",
  "model": "opencode-go/glm-5.3-flash",
  "default_agent": "build",
  "agent": {
    "reviewer": {
      "mode": "primary",
      "description": "Automatic PR review in CI: BLOCKING/WARNING/NIT format, path:line findings, never approves, never edits.",
      "model": "opencode-go/glm-5.3-flash",
      "permission": {
        "edit": "deny",
        "webfetch": "deny",
        "websearch": "deny",
        "bash": {
          "*": "deny",
          "git diff*": "allow",
          "git log*": "allow",
          "git show*": "allow",
          "git rev-parse*": "allow",
          "git merge-base*": "allow",
          "gh pr view*": "allow",
          "gh pr diff*": "allow",
          "gh issue view*": "allow"
        }
      },
      "prompt": "You are the automated reviewer for this pull request. Load the `code-review` skill and apply it: the fixed point is the PR base (merge-base with the target branch); the spec comes from the PR body and the issues it references. Read the repo's AGENTS.md/CONTRIBUTING.md if present. Required output: one comment with BLOCKING, WARNING and NIT sections, `path:line` on every finding, and a final line `SUMMARY: N BLOCKING, N WARNING, N NIT`. Skip files under `docs/` and `*.md` unless they are the subject of the change. Never approve, never request changes formally, never edit files: you comment, a human decides. Write in the language the repo uses for review comments (default: English)."
    },
    "fixer": {
      "mode": "primary",
      "description": "Executes a fix request made via /oc or /opencode comment on a PR or issue. Write-capable by design: the requester asked for a change.",
      "model": "opencode-go/glm-5.3-flash",
      "permission": {
        "webfetch": "deny",
        "websearch": "deny"
      },
      "prompt": "You execute the request in the `/oc` (or `/opencode`) comment. Load the `implement` skill; if the request describes a bug, also load `diagnosing-bugs` and reproduce before fixing; if you add a test, load `tdd`. Follow the repo's AGENTS.md. Smallest diff that satisfies the request: no new abstraction, no new dependency. Run the focused test for what changed before committing. Commit with Conventional Commits referencing the issue or PR. If the request is ambiguous or asks for something the commenter cannot reasonably intend, stop and ask on the PR instead of guessing."
    },
    "ci-doctor": {
      "mode": "primary",
      "description": "Diagnoses a failed workflow run and posts one diagnosis comment on the associated PR. Diagnosis only — fixing is a human decision or an /oc request.",
      "model": "opencode-go/glm-5.3-flash",
      "permission": {
        "edit": "deny",
        "webfetch": "deny",
        "websearch": "deny",
        "bash": {
          "*": "deny",
          "gh run view*": "allow",
          "gh run list*": "allow",
          "gh api*": "allow",
          "gh pr view*": "allow",
          "gh pr comment*": "allow",
          "git log*": "allow",
          "git show*": "allow"
        }
      },
      "prompt": "You diagnose a failed CI run. Your prompt carries the run URL, run id, head SHA and PR number. Run `gh run view <id> --log-failed` (add `--job <id>` or `--log` when needed), find the root cause — not the symptom — and post ONE comment on the PR with `gh pr comment <pr> --body ...`. Comment format: probable cause, the log evidence, the suggested fix. End the comment with the exact HTML-marker line given in your prompt — it is the dedup key. Do not edit code, do not retry the run, do not comment anywhere else. If the failure is a flaky test or infra hiccup with no code cause, say so plainly in the same format."
    }
  }
}
```

- [ ] **Step 2: Write the four generic skills**

`skills/code-review/SKILL.md`:

```markdown
---
name: code-review
description: "Review the changes since a fixed point (commit, branch, tag, or merge-base). Use when the user wants to review a branch, a PR, or work-in-progress changes."
---

Review the diff between `HEAD` and a fixed point the user supplies (a commit
SHA, branch, tag, `main`, `HEAD~5`). If none was given, use the PR base.

## Process

1. Resolve the fixed point: `git merge-base <point> HEAD`, then
   `git diff <point>...HEAD`. A bad ref or empty diff fails here.
2. Find the spec: the PR body, linked issues, or what the user wrote. If the
   repo has documented conventions (`AGENTS.md`, `docs/conventions/`), read
   them before judging.
3. Read the diff plus enough surrounding code to understand each hunk. Judge
   two axes: conformance to the repo's own standards, and faithfulness to the
   spec.
4. Every finding carries `path:line` of the exact line it refers to.

## Output contract

One comment, three sections — write `(none)` under empty ones:

```
BLOCKING
- file.py:10 — what breaks and why it must not merge

WARNING
- file.py:22 — real risk, not fatal

NIT
- file.py:31 — style/clarity

SUMMARY: N BLOCKING, N WARNING, N NIT
```

The `SUMMARY:` line is the last line and is machine-parsed — never omit it.
```

`skills/implement/SKILL.md`:

```markdown
---
name: implement
description: "Implement a piece of work described by the user — a comment request, spec, or ticket. Use when executing a scoped change request."
---

Implement exactly what was asked, in the smallest diff that satisfies it.

- Read the repo's conventions (`AGENTS.md`, CONTRIBUTING) before writing.
- No new abstractions, no new dependencies, no drive-by refactors.
- Use `tdd` where a seam exists: failing test first, then the fix.
- Run the focused test for what changed; run the wider suite once at the end.
- Commit with Conventional Commits, referencing the issue/PR that asked.
- Ambiguous request? Stop and ask instead of guessing.
```

`skills/tdd/SKILL.md`:

```markdown
---
name: tdd
description: "Test-driven development. Use when building features or fixing bugs where a testable seam exists."
---

Red, then green, then refactor — one slice at a time.

1. Pick one seam (a public function, a CLI contract, an endpoint).
2. Write the smallest test that would fail without the change. Run it; see it
   fail for the right reason.
3. Write the minimal implementation that turns it green. Run it.
4. Refactor only while green. Repeat for the next slice.

Expected values come from an independent source of truth — never recompute
them the way the code does. A fix ships with the test that fails without it.
```

`skills/diagnosing-bugs/SKILL.md`:

```markdown
---
name: diagnosing-bugs
description: "Diagnosis loop for bugs and regressions. Use when something is reported broken, throwing, or behaving unexpectedly — before proposing fixes."
---

Diagnose before fixing. A fix without a reproduced root cause is a guess.

1. Reproduce reliably — the smallest input or command that shows the bug.
2. Trace the path from entry point to failure; find where expected and actual
   diverge. Add targeted logging only if tracing stalls.
3. Name the root cause in one sentence before touching code.
4. Fix the cause, not the symptom. Add the regression test that fails without
   the fix (`tdd`).
5. Verify the fix kills the reproduction, not just the test.
```

- [ ] **Step 3: Validate the JSON + schema**

```bash
python3 -c "import json; json.load(open('agents/opencode.json'))"
python3 -m pip install --user check-jsonschema 2>/dev/null || pipx install check-jsonschema
check-jsonschema --schemafile https://opencode.ai/config.json agents/opencode.json
```

Expected: JSON parses; schema check OK. If `check-jsonschema` can't reach the schema, record `NÃO VERIFICADO` and rely on the same check in `lint.yml` (Task 8).

- [ ] **Step 4: Commit**

```bash
git add agents/ skills/
git commit -m "feat(agents): default reviewer/fixer/ci-doctor agents and generic fallback skills"
```

---

### Task 3: `runtime/` image + `build-runtime.yml`

**Files:**
- Create: `runtime/Dockerfile`
- Create: `runtime/VERSION` (contents: `v1`)
- Create: `.github/workflows/build-runtime.yml`

**Interfaces:**
- Produces: image `ghcr.io/heliowap/gh-agents-runtime:<contents of runtime/VERSION>` with `git`, `gh`, `jq`, `python3`, `curl`, `ca-certificates`, `node22`, `opencode` on PATH.
- Consumed by: `agents.yml` input `runtime_image` default `ghcr.io/heliowap/gh-agents-runtime:v1`.

- [ ] **Step 1: Write `runtime/Dockerfile`**

```dockerfile
FROM ubuntu:24.04

# gh-agents job image. Each tool names its consumer:
#   git, gh, jq, curl, ca-certificates — the bash steps (gh api, dedup, checkout deps)
#   python3 — scripts/review_blocking.py
#   node22 — JS actions inside the container (FORCE_JAVASCRIPT_ACTIONS_TO_NODE24)
#   opencode — the ci-doctor job invokes `opencode run` directly
RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates curl git jq python3 xz-utils \
 && rm -rf /var/lib/apt/lists/*

# gh CLI — official apt repo
RUN curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
      -o /usr/share/keyrings/githubcli-archive-keyring.gpg \
 && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
      > /etc/apt/sources.list.d/github-cli.list \
 && apt-get update && apt-get install -y --no-install-recommends gh \
 && rm -rf /var/lib/apt/lists/*

# Node 22 — official tarball (no nodesource)
ARG NODE_VERSION=22.20.0
RUN curl -fsSL "https://nodejs.org/dist/v${NODE_VERSION}/node-v${NODE_VERSION}-linux-x64.tar.xz" \
    | tar -xJ -C /usr/local --strip-components=1

# opencode CLI — installer drops in $HOME/.opencode/bin; expose on PATH
RUN curl -fsSL https://opencode.ai/install | bash \
 && ln -s "$HOME/.opencode/bin/opencode" /usr/local/bin/opencode

CMD ["bash"]
```

Write `runtime/VERSION` with `v1`.

- [ ] **Step 2: Verify NODE_VERSION exists, then build**

```bash
curl -fsSL https://nodejs.org/dist/index.json | python3 -c "import json,sys; print(any(v['version']=='v22.20.0' for v in json.load(sys.stdin)))"
docker build -t gh-agents-runtime:test runtime/
docker run --rm gh-agents-runtime:test sh -c 'git --version && gh --version && python3 --version && node --version && opencode --version'
```

Expected: `True`, image builds, all tools print versions. If `v22.20.0` doesn't exist, pick the newest `22.x` from the index output and update the ARG.

- [ ] **Step 3: Write `.github/workflows/build-runtime.yml`**

```yaml
name: build-runtime

# Builds and pushes ghcr.io/heliowap/gh-agents-runtime from runtime/VERSION.
# The tag is deliberate: bump VERSION to release a new image; workflows never
# reference `latest`.

on:
  push:
    branches: [main]
    paths: [runtime/**]
  workflow_dispatch:

permissions:
  contents: read
  packages: write

jobs:
  build:
    runs-on: ubuntu-latest
    timeout-minutes: 30
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
      - id: v
        run: echo "tag=$(cat runtime/VERSION)" >> "$GITHUB_OUTPUT"
      - uses: docker/setup-buildx-action@f87e5991a6d7451dcb8d9637bfbc97413f497069 # v4.4.1
      - uses: docker/login-action@dbcb813823bdd20940b903addbd779551569679f # v4.6.0
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - uses: docker/build-push-action@c3c9e263c25d99ce0380d002d59b67737d91b0dc # v7.4.0
        with:
          context: runtime/
          push: true
          tags: ghcr.io/heliowap/gh-agents-runtime:${{ steps.v.outputs.tag }}
```

- [ ] **Step 4: Lint and commit**

```bash
actionlint .github/workflows/build-runtime.yml
git add runtime/ .github/workflows/build-runtime.yml
git commit -m "feat(runtime): job container image and publish workflow"
```

Note: the image is published by CI on merge to `main` (`packages: write` on `GITHUB_TOKEN`) — no operator PAT needed for ghcr.

---

### Task 4: `.github/workflows/agents.yml` — the reusable workflow

**Files:**
- Create: `.github/workflows/agents.yml`
- Modify: `templates/caller-agents.yml` lands in Task 7 (caller-side triggers live there, not here)

**Interfaces:**
- Consumes: `agents/opencode.json` + `skills/` + `scripts/review_blocking.py` via a second checkout of `heliowap/gh-agents` at `inputs.gh_agents_ref` into `.gh-agents/`.
- Produces (the contract callers pin): `uses: heliowap/gh-agents/.github/workflows/agents.yml@v1` with inputs `runs-on`, `model`, `use_container`, `runtime_image`, `gh_agents_ref`, `ci_workflows`; secret `OPENCODE_API_KEY` required.
- Every `with:` agent name (`reviewer`, `fixer`, `ci-doctor`) exists in Task 2's `agents/opencode.json`.

- [ ] **Step 1: Write `.github/workflows/agents.yml`**

```yaml
name: gh-agents

# Reusable workflow: automatic PR review, `/oc` fix on comments, CI-failure
# diagnosis. Called via `uses: heliowap/gh-agents/.github/workflows/agents.yml@v1`
# with `secrets: inherit`. What this workflow is NOT:
#   - a merge gate. The reviewer comments; the human decides.
#   - CI auto-fix. ci-doctor diagnoses; fixing is a human decision or `/oc`.
#
# Agents/skills resolution: the caller's checkout is primary (`opencode.json`,
# `.agents/skills/`); the "seed" step copies this repo's defaults only where
# the caller has none. Untrusted values reach `run:` via `env:`, never ${{ }}.

on:
  workflow_call:
    inputs:
      runs-on:
        description: "Runner label fallback; the caller's vars.AGENT_RUNNER wins."
        type: string
        default: "self-hosted"
      model:
        description: "OpenCode model for all agents."
        type: string
        default: "opencode-go/glm-5.3-flash"
      use_container:
        description: "Run jobs in the gh-agents-runtime image. false = host (repos whose tests need Docker; less isolation)."
        type: boolean
        default: true
      runtime_image:
        description: "Job image when use_container=true."
        type: string
        default: "ghcr.io/heliowap/gh-agents-runtime:v1"
      gh_agents_ref:
        description: "Ref for the gh-agents defaults checkout (agents/skills/scripts)."
        type: string
        default: "v1"
      ci_workflows:
        description: "Comma-separated workflow names ci-doctor watches. Empty = all."
        type: string
        default: ""
    secrets:
      OPENCODE_API_KEY:
        required: true

permissions:
  contents: read

# One run per (event, target): comments get their own group so a comment never
# cancels an in-flight review (intrador #1417).
concurrency:
  group: gh-agents-${{ github.event_name }}-${{ github.event.pull_request.number || github.event.issue.number || github.event.workflow_run.id || github.ref }}
  cancel-in-progress: true

env:
  FORCE_JAVASCRIPT_ACTIONS_TO_NODE24: true

jobs:
  review:
    name: Review (${{ inputs.model }})
    # pull_request only; a draft is not a review request (ready_for_review fires later).
    if: github.event_name == 'pull_request' && github.event.pull_request.draft == false
    runs-on: ${{ vars.AGENT_RUNNER || inputs.runs-on }}
    container: ${{ inputs.use_container && inputs.runtime_image || '' }}
    timeout-minutes: 20
    permissions:
      contents: read
      pull-requests: write
      issues: write
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          fetch-depth: 0
          # the action fetches `origin <branch>` itself; credentials must persist
          persist-credentials: true
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          repository: heliowap/gh-agents
          ref: ${{ inputs.gh_agents_ref }}
          path: .gh-agents
          persist-credentials: false
      - name: Seed opencode.json and fallback skills
        # caller's own files always win; a repo with nothing still works
        run: |
          set -euo pipefail
          [ -f opencode.json ] || cp .gh-agents/agents/opencode.json opencode.json
          for s in .gh-agents/skills/*/; do
            name="$(basename "$s")"
            if [ ! -d ".agents/skills/$name" ]; then
              mkdir -p .agents/skills
              cp -r "$s" ".agents/skills/$name"
            fi
          done
      - name: Preflight OPENCODE_API_KEY
        # fork PRs and missing secrets arrive as empty — fail with a readable error
        run: |
          if [ -z "${OPENCODE_API_KEY:-}" ]; then
            echo "::error::OPENCODE_API_KEY is empty — set the repo secret (README onboarding step 2) or check fork-PR secret withholding"
            exit 1
          fi
        env:
          OPENCODE_API_KEY: ${{ secrets.OPENCODE_API_KEY }}
      - id: review
        uses: anomalyco/opencode/github@3a103fe0aff726a4edc7492f03f7b88195d9e4c9 # v2.0.16
        env:
          OPENCODE_API_KEY: ${{ secrets.OPENCODE_API_KEY }}
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        with:
          model: ${{ inputs.model }}
          agent: reviewer
          use_github_token: true
          share: false
      # BLOCKING becomes a `review-blocking` issue; WARNING/NIT do not. One
      # issue per PR (key `PR #N` in title); a closed one reopens on new
      # BLOCKING. Only when the action succeeded — a failed review has no SUMMARY.
      - name: BLOCKING becomes a review-blocking issue
        if: steps.review.outcome == 'success'
        env:
          GH_TOKEN: ${{ github.token }}
          PR: ${{ github.event.pull_request.number }}
          SHA: ${{ github.event.pull_request.head.sha }}
        run: |
          set -euo pipefail
          out="$(gh api --paginate "repos/${GITHUB_REPOSITORY}/issues/${PR}/comments?per_page=100" \
            | jq -s add | python3 .gh-agents/scripts/review_blocking.py --comments)"
          blocking="$(jq -r .blocking <<<"$out")"
          if [ "$blocking" = "0" ]; then
            echo "no BLOCKING on PR #${PR} (or no SUMMARY line — see stderr above)"
            exit 0
          fi
          body="$(printf 'Automatic review of PR #%s (SHA `%s`) ended with %s BLOCKING.\n\n- Comment: %s\n\n```\nBLOCKING\n%s\n```\n\nTriage: `/oc <request>` here, or close if not pertinent.\n' \
            "$PR" "$SHA" "$blocking" "$(jq -r .url <<<"$out")" "$(jq -r .block <<<"$out")")"
          # workflows that use a label guarantee the label
          gh label create review-blocking --color B60205 \
            --description "Automatic review reported BLOCKING" --force >/dev/null
          # client-side filter, not --search: the Search API lags and a
          # `synchronize` right after creation would open a duplicate
          existing="$(gh api --paginate "repos/${GITHUB_REPOSITORY}/issues?state=all&labels=review-blocking&per_page=100" \
            | jq -s --arg pr "PR #${PR} " 'add | map(select(.pull_request == null and (.title | contains($pr)))) | .[0] // {}')"
          number="$(jq -r '.number // empty' <<<"$existing")"
          if [ -n "$number" ]; then
            [ "$(jq -r .state <<<"$existing")" = "closed" ] && gh issue reopen "$number"
            gh issue comment "$number" --body "$body"
            echo "issue #${number} updated"
            exit 0
          fi
          gh issue create --label review-blocking \
            --title "review-blocking: PR #${PR} with BLOCKING in review" \
            --body "$body"

  fix:
    name: Fix (/oc)
    # Comments are untrusted input: only OWNER/MEMBER/COLLABORATOR, never a bot
    # (a bot triggering the fixer would be a bot-triggered bot).
    if: >-
      (github.event_name == 'issue_comment' || github.event_name == 'pull_request_review_comment')
      && github.event.comment.user.type != 'Bot'
      && contains(fromJSON('["OWNER","MEMBER","COLLABORATOR"]'), github.event.comment.author_association)
      && (contains(github.event.comment.body, '/oc') || contains(github.event.comment.body, '/opencode'))
    runs-on: ${{ vars.AGENT_RUNNER || inputs.runs-on }}
    container: ${{ inputs.use_container && inputs.runtime_image || '' }}
    timeout-minutes: 30
    permissions:
      contents: write
      pull-requests: write
      issues: write
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          fetch-depth: 0
          persist-credentials: true
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          repository: heliowap/gh-agents
          ref: ${{ inputs.gh_agents_ref }}
          path: .gh-agents
          persist-credentials: false
      - name: Seed opencode.json and fallback skills
        run: |
          set -euo pipefail
          [ -f opencode.json ] || cp .gh-agents/agents/opencode.json opencode.json
          for s in .gh-agents/skills/*/; do
            name="$(basename "$s")"
            if [ ! -d ".agents/skills/$name" ]; then
              mkdir -p .agents/skills
              cp -r "$s" ".agents/skills/$name"
            fi
          done
      - name: Preflight OPENCODE_API_KEY
        run: |
          if [ -z "${OPENCODE_API_KEY:-}" ]; then
            echo "::error::OPENCODE_API_KEY is empty — set the repo secret (README onboarding step 2)"
            exit 1
          fi
        env:
          OPENCODE_API_KEY: ${{ secrets.OPENCODE_API_KEY }}
      - uses: anomalyco/opencode/github@3a103fe0aff726a4edc7492f03f7b88195d9e4c9 # v2.0.16
        env:
          OPENCODE_API_KEY: ${{ secrets.OPENCODE_API_KEY }}
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        with:
          model: ${{ inputs.model }}
          agent: fixer
          use_github_token: true
          share: false

  ci-doctor:
    name: CI doctor
    # failed workflow_run; empty ci_workflows watches all (regra: diagnose-only,
    # never fix — fixing is /oc or human).
    if: >-
      github.event_name == 'workflow_run'
      && github.event.workflow_run.conclusion == 'failure'
      && (inputs.ci_workflows == '' || contains(inputs.ci_workflows, github.event.workflow_run.name))
    runs-on: ${{ vars.AGENT_RUNNER || inputs.runs-on }}
    container: ${{ inputs.use_container && inputs.runtime_image || '' }}
    timeout-minutes: 20
    permissions:
      actions: read
      contents: read
      pull-requests: write
      issues: write
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          fetch-depth: 0
          persist-credentials: true
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          repository: heliowap/gh-agents
          ref: ${{ inputs.gh_agents_ref }}
          path: .gh-agents
          persist-credentials: false
      - name: Seed opencode.json and fallback skills
        run: |
          set -euo pipefail
          [ -f opencode.json ] || cp .gh-agents/agents/opencode.json opencode.json
          for s in .gh-agents/skills/*/; do
            name="$(basename "$s")"
            if [ ! -d ".agents/skills/$name" ]; then
              mkdir -p .agents/skills
              cp -r "$s" ".agents/skills/$name"
            fi
          done
      - name: Preflight OPENCODE_API_KEY
        run: |
          if [ -z "${OPENCODE_API_KEY:-}" ]; then
            echo "::error::OPENCODE_API_KEY is empty — set the repo secret (README onboarding step 2)"
            exit 1
          fi
        env:
          OPENCODE_API_KEY: ${{ secrets.OPENCODE_API_KEY }}
      # Dedup is deterministic, not LLM-decided: one diagnosis per (run, sha),
      # keyed by the <!-- ci-doctor:<sha> --> marker the agent must append.
      - name: Resolve PR and dedup
        id: gate
        env:
          GH_TOKEN: ${{ github.token }}
          RUN_ID: ${{ github.event.workflow_run.id }}
          HEAD_SHA: ${{ github.event.workflow_run.head_sha }}
        run: |
          set -euo pipefail
          pr="$(gh api "repos/${GITHUB_REPOSITORY}/actions/runs/${RUN_ID}" \
                --jq '.pull_requests[0].number // empty')"
          if [ -z "$pr" ]; then
            echo "run ${RUN_ID} has no associated PR; ci-doctor skips silently"
            echo "skip=true" >> "$GITHUB_OUTPUT"
            exit 0
          fi
          dup="$(gh api --paginate "repos/${GITHUB_REPOSITORY}/issues/${pr}/comments?per_page=100" \
            | jq -s --arg m "<!-- ci-doctor:${HEAD_SHA} -->" \
              'add | map(select(.body | contains($m))) | length')"
          if [ "$dup" != "0" ]; then
            echo "diagnosis for ${HEAD_SHA} already posted on PR #${pr}"
            echo "skip=true" >> "$GITHUB_OUTPUT"
            exit 0
          fi
          { echo "pr=${pr}"; echo "skip=false"; } >> "$GITHUB_OUTPUT"
      - name: Ensure opencode CLI
        # the runtime image already carries it; host mode installs on demand
        if: steps.gate.outputs.skip == 'false'
        run: |
          command -v opencode >/dev/null || {
            curl -fsSL https://opencode.ai/install | bash
            echo "$HOME/.opencode/bin" >> "$GITHUB_PATH"
          }
      - name: Diagnose failed run
        if: steps.gate.outputs.skip == 'false'
        env:
          OPENCODE_API_KEY: ${{ secrets.OPENCODE_API_KEY }}
          GH_TOKEN: ${{ github.token }}
          MODEL: ${{ inputs.model }}
          RUN_ID: ${{ github.event.workflow_run.id }}
          RUN_NAME: ${{ github.event.workflow_run.name }}
          RUN_URL: ${{ github.event.workflow_run.html_url }}
          HEAD_SHA: ${{ github.event.workflow_run.head_sha }}
          PR: ${{ steps.gate.outputs.pr }}
        run: |
          set -euo pipefail
          prompt="$(printf 'Workflow run %s ("%s") failed at SHA %s. Diagnose it: run `gh run view %s --log-failed`, find the root cause, and post ONE comment on PR #%s with `gh pr comment %s --body ...`. Format: probable cause, the log evidence, the suggested fix. End the comment with this exact line: <!-- ci-doctor:%s -->. Do not edit code; diagnosis only.' \
            "$RUN_URL" "$RUN_NAME" "$HEAD_SHA" "$RUN_ID" "$PR" "$PR" "$HEAD_SHA")"
          opencode run --model "$MODEL" --agent ci-doctor "$prompt"
```

- [ ] **Step 2: Verify `opencode run` flags against the real CLI**

```bash
command -v opencode || (curl -fsSL https://opencode.ai/install | bash && export PATH="$HOME/.opencode/bin:$PATH")
opencode run --help
```

Expected: `--model` and `--agent` flags exist. If names differ (e.g. positional agent or `-m`), fix the `Diagnose failed run` step accordingly and note it.

- [ ] **Step 3: actionlint + commit**

```bash
actionlint .github/workflows/agents.yml
git add .github/workflows/agents.yml
git commit -m "feat: reusable agents workflow (review, /oc fix, ci-doctor)"
```

Expected: actionlint clean. Note: actionlint may warn about `vars` in `runs-on` or `container` expression shape on old versions — a current version understands both; do not weaken the pins to silence an outdated linter.

---

### Task 5: `runner/lib.sh` + `enable-repo.sh` + `enable-org.sh` (bats)

**Files:**
- Create: `runner/lib.sh`
- Create: `runner/enable-repo.sh`
- Create: `runner/enable-org.sh`
- Test: `runner/tests/enable.bats`

**Interfaces:**
- `lib.sh` (sourced, not executed): `die`, `need`, `scope_repo <owner/repo> → owner--repo`, `scope_org <org> → org--<org>`, `require_private_repo <owner/repo>` (aborts on non-private), `repo_registration_token`, `repo_removal_token`, `org_registration_token`, `org_removal_token`, `ensure_private_runner_group <org>` (idempotent; prints group id), `latest_runner_version`, `runner_dir <scope> <n>`, `unit_for <dir>` (queries systemctl, never invents). Honors `GH_AGENTS_HOME` (default `/home/gh-agents`) so tests can redirect.
- Consumed by: disable/status/cleanup in Task 6.

- [ ] **Step 1: Write the failing bats tests**

`runner/tests/enable.bats` — stubs `gh`, `curl`, `tar`, `sudo`, `systemctl` on PATH:

```bash
#!/usr/bin/env bats

setup() {
  TEST_HOME="$(mktemp -d)"
  export GH_AGENTS_HOME="$TEST_HOME"
  STUB="$TEST_HOME/bin"; mkdir -p "$STUB"
  export PATH="$STUB:$PATH"
  REPO_ROOT="$(cd "$BATS_TEST_DIRNAME/../.." && pwd)"

  cat > "$STUB/gh" <<'EOF'
#!/usr/bin/env bash
# stub: records calls; answers the API shapes the scripts use
echo "$@" >> "$GH_CALLS"
case "$*" in
  *"repos/"*"/actions/runners/registration-token"*) echo '{"token":"REGTOK"}' ;;
  *"orgs/"*"/actions/runners/registration-token"*) echo '{"token":"ORGTOK"}' ;;
  *"repos/"*"/actions/runners"*) echo '{"runners":[]}' ;;
  *"runner-groups"*"POST"*|*"-X POST"*"runner-groups"*) echo '{"id":7}' ;;
  *"runner-groups"*) echo '{"runner_groups":[{"id":7,"name":"gh-agents","visibility":"private"}]}' ;;
  *"repos/actions/runner/releases/latest"*) echo '{"tag_name":"v2.320.0"}' ;;
  *"repos/"*) echo '{"visibility":"private"}' ;;
  *"auth status"*) exit 0 ;;
  *) echo '{}' ;;
esac
EOF
  cat > "$STUB/curl" <<'EOF'
#!/usr/bin/env bash
# writes an empty tarball where -o says; otherwise /dev/null output
while [ $# -gt 0 ]; do case "$1" in -o) echo x > "$2"; shift 2;; *) shift;; esac; done
EOF
  cat > "$STUB/tar" <<'EOF'
#!/usr/bin/env bash
mkdir -p ./extracted && touch ./extracted/.keep
EOF
  cat > "$STUB/sudo" <<'EOF'
#!/usr/bin/env bash
exec "$@"
EOF
  cat > "$STUB/systemctl" <<'EOF'
#!/usr/bin/env bash
exit 0
EOF
  chmod +x "$STUB"/*
  export GH_CALLS="$TEST_HOME/gh-calls"; : > "$GH_CALLS"

  # config.sh/svc.sh appear where the runner would be extracted:
  mkdir -p "$TEST_HOME/fakebin"
}

teardown() { rm -rf "$TEST_HOME"; }

@test "enable-repo refuses a public repo" {
  cat > "$STUB/gh" <<'EOF'
#!/usr/bin/env bash
case "$*" in *"repos/"*"/actions/runners"*) echo '{"runners":[]}';; *"repos/"*) echo '{"visibility":"public"}';; *) echo '{}';; esac
EOF
  chmod +x "$STUB/gh"
  run "$REPO_ROOT/runner/enable-repo.sh" owner/pub
  [ "$status" -ne 0 ]
  [[ "$output" == *"public"* ]]
}

@test "enable-repo prints usage without args" {
  run "$REPO_ROOT/runner/enable-repo.sh"
  [ "$status" -ne 0 ]
  [[ "$output" == *"uso"* || "$output" == *"usage"* ]]
}

@test "scope names follow owner--repo / org--org" {
  source "$REPO_ROOT/runner/lib.sh"
  [ "$(scope_repo owner/repo)" = "owner--repo" ]
  [ "$(scope_org intrador)" = "org--intrador" ]
}

@test "enable-repo is idempotent on a configured runner" {
  scope="owner--repo"; mkdir -p "$GH_AGENTS_HOME/runners/$scope/1" "$GH_AGENTS_HOME/runners/$scope/2"
  touch "$GH_AGENTS_HOME/runners/$scope/1/.runner" "$GH_AGENTS_HOME/runners/$scope/2/.runner"
  run "$REPO_ROOT/runner/enable-repo.sh" owner/repo 2
  [ "$status" -eq 0 ]
  [[ "$output" == *"já configurado"* || "$output" == *"already"* ]]
}
```

- [ ] **Step 2: Run to verify failure**

Run: `bats runner/tests/enable.bats`
Expected: FAIL (scripts don't exist).

- [ ] **Step 3: Write `runner/lib.sh`**

```bash
#!/usr/bin/env bash
# Shared helpers for the fleet scripts. Source this; do not execute it.
# GH_AGENTS_HOME is overridable for tests; production default is the fleet user.

GH_AGENTS_HOME="${GH_AGENTS_HOME:-/home/gh-agents}"
RUNNERS_DIR="$GH_AGENTS_HOME/runners"

die() { echo "erro: $*" >&2; exit 1; }

need() { command -v "$1" >/dev/null || die "'$1' não encontrado no PATH"; }

scope_repo() { echo "${1%%/*}--${1##*/}"; }   # owner/repo -> owner--repo
scope_org()  { echo "org--$1"; }

runner_dir() { echo "$RUNNERS_DIR/$1/$2"; }

# Self-hosted on a public repo is RCE for every fork — refuse before any work.
require_private_repo() {
  local vis
  vis="$(gh api "repos/$1" --jq .visibility)" || die "repo $1 não encontrado"
  [ "$vis" = "private" ] || die "repo $1 é '$vis' — runner self-hosted exige repo privado"
}

repo_registration_token() { gh api -X POST "repos/$1/actions/runners/registration-token" --jq .token; }
repo_removal_token()      { gh api -X POST "repos/$1/actions/runners/remove-token" --jq .token; }
org_registration_token()  { gh api -X POST "orgs/$1/actions/runners/registration-token" --jq .token; }
org_removal_token()       { gh api -X POST "orgs/$1/actions/runners/remove-token" --jq .token; }

latest_runner_version() {
  gh api repos/actions/runner/releases/latest --jq '.tag_name | ltrimstr("v")'
}

# Org runners see whatever the group allows; the gh-agents group is private-only.
# Idempotent: returns the existing group's id when already there.
ensure_private_runner_group() {
  local org="$1" id
  id="$(gh api "orgs/$org/actions/runner-groups" \
        --jq '.runner_groups[] | select(.name=="gh-agents") | .id' | head -1)"
  if [ -z "$id" ]; then
    id="$(gh api -X POST "orgs/$org/actions/runner-groups" \
          -f name=gh-agents -F visibility=private --jq .id)"
  fi
  [ -n "$id" ] || die "não consegui garantir o runner group gh-agents em $org"
  echo "$id"
}

# Unit names are whatever svc.sh generated — query, never invent.
unit_for() {
  local name
  name="$(basename "$(dirname "$1")")--$(basename "$1")" 2>/dev/null || true
  systemctl list-units --all --no-legend 'actions.runner.*' 2>/dev/null \
    | awk '{print $1}' | grep -F "$name" | head -1
}
```

- [ ] **Step 4: Write `runner/enable-repo.sh`**

```bash
#!/usr/bin/env bash
# Registra N runners de repo (label `agents`) para owner/repo.
# Idempotente: um dir com .runner já configurado é pulado.
# Uso: enable-repo.sh <owner>/<repo> [N=2]
set -euo pipefail

[ $# -ge 1 ] || { echo "uso: $0 <owner>/<repo> [N=2]" >&2; exit 1; }
REPO="$1"; N="${2:-2}"

source "$(dirname "$0")/lib.sh"
need gh; need curl; need tar
gh auth status >/dev/null 2>&1 || die "gh sem auth — rode 'gh auth login' ou exporte GH_TOKEN"

echo "==> verificando visibilidade de $REPO"
require_private_repo "$REPO"

SCOPE="$(scope_repo "$REPO")"
VERSION="$(latest_runner_version)"
echo "==> $N runner(s) para $REPO em $RUNNERS_DIR/$SCOPE (actions-runner $VERSION)"

mkdir -p "$RUNNERS_DIR/$SCOPE"
for i in $(seq 1 "$N"); do
  dir="$(runner_dir "$SCOPE" "$i")"
  if [ -f "$dir/.runner" ]; then
    echo "==> runner $i já configurado em $dir — pulando"
    continue
  fi
  echo "==> configurando runner $i em $dir"
  mkdir -p "$dir"
  (
    cd "$dir"
    tgz="actions-runner-linux-x64-${VERSION}.tar.gz"
    [ -f "$tgz" ] || curl -fsSL -o "$tgz" \
      "https://github.com/actions/runner/releases/download/v${VERSION}/${tgz}"
    tar xzf "$tgz"
    token="$(repo_registration_token "$REPO")"
    ./config.sh --unattended \
      --url "https://github.com/$REPO" \
      --token "$token" \
      --name "${SCOPE}-${i}" \
      --labels agents \
      --work _work \
      --replace
    sudo ./svc.sh install "$USER"
    sudo ./svc.sh start
  )
done

echo "==> verificação"
gh api "repos/$REPO/actions/runners" \
  --jq --arg s "$SCOPE" '.runners[] | select(.name | startswith($s)) | "\(.name)\t\(.status)"'
systemctl list-units 'actions.runner.*' --no-legend 2>/dev/null | grep -F "$SCOPE" || true
```

- [ ] **Step 5: Write `runner/enable-org.sh`**

```bash
#!/usr/bin/env bash
# Registra N runners de ORG no runner group `gh-agents` (visibility: private —
# grupo garante que só repos privados do org chegam aos runners).
# Uso: enable-org.sh <org> [N=2]   (PAT precisa de admin:org)
set -euo pipefail

[ $# -ge 1 ] || { echo "uso: $0 <org> [N=2]" >&2; exit 1; }
ORG="$1"; N="${2:-2}"

source "$(dirname "$0")/lib.sh"
need gh; need curl; need tar
gh auth status >/dev/null 2>&1 || die "gh sem auth — PAT com admin:org necessário"

echo "==> garantindo runner group gh-agents (private) em $ORG"
GROUP_ID="$(ensure_private_runner_group "$ORG")"

SCOPE="$(scope_org "$ORG")"
VERSION="$(latest_runner_version)"
echo "==> $N runner(s) para org $ORG em $RUNNERS_DIR/$SCOPE (group $GROUP_ID)"

mkdir -p "$RUNNERS_DIR/$SCOPE"
for i in $(seq 1 "$N"); do
  dir="$(runner_dir "$SCOPE" "$i")"
  if [ -f "$dir/.runner" ]; then
    echo "==> runner $i já configurado em $dir — pulando"
    continue
  fi
  echo "==> configurando runner $i em $dir"
  mkdir -p "$dir"
  (
    cd "$dir"
    tgz="actions-runner-linux-x64-${VERSION}.tar.gz"
    [ -f "$tgz" ] || curl -fsSL -o "$tgz" \
      "https://github.com/actions/runner/releases/download/v${VERSION}/${tgz}"
    tar xzf "$tgz"
    token="$(org_registration_token "$ORG")"
    ./config.sh --unattended \
      --url "https://github.com/$ORG" \
      --token "$token" \
      --name "${SCOPE}-${i}" \
      --labels agents \
      --runnergroup "$GROUP_ID" \
      --work _work \
      --replace
    sudo ./svc.sh install "$USER"
    sudo ./svc.sh start
  )
done

echo "==> verificação"
gh api "orgs/$ORG/actions/runners" \
  --jq --arg s "$SCOPE" '.runners[] | select(.name | startswith($s)) | "\(.name)\t\(.status)"'
```

- [ ] **Step 6: Run bats — expect pass; shellcheck — expect clean**

```bash
bats runner/tests/enable.bats
shellcheck runner/lib.sh runner/enable-repo.sh runner/enable-org.sh
```

Fix whatever is red. If a stub shape fights the real API, adjust the stub — the scripts' `gh api` calls above match the documented endpoints.

- [ ] **Step 7: Commit**

```bash
git add runner/
git commit -m "feat(fleet): repo/org runner enable scripts with private-only gates"
```

---

### Task 6: `disable-*.sh`, `status.sh`, `cleanup.sh` + systemd timer (bats)

**Files:**
- Create: `runner/disable-repo.sh`, `runner/disable-org.sh`, `runner/status.sh`, `runner/cleanup.sh`, `runner/install-cleanup.sh`
- Create: `runner/systemd/gh-agents-cleanup.service`, `runner/systemd/gh-agents-cleanup.timer`
- Test: `runner/tests/lifecycle.bats`

**Interfaces:**
- Consumes: `lib.sh` from Task 5 (`scope_repo`, `scope_org`, removal tokens, `unit_for`, `RUNNERS_DIR`).
- Produces: `disable-*.sh` order = stop unit → uninstall unit → `config.sh remove --token` → remove dir; `cleanup.sh` removes `_work` of runners whose unit is inactive for >7d; `install-cleanup.sh` (needs sudo) installs+enables the daily timer.

- [ ] **Step 1: Write the failing bats tests**

`runner/tests/lifecycle.bats` — same stub strategy as `enable.bats`; key cases:

```bash
#!/usr/bin/env bats

setup() {
  TEST_HOME="$(mktemp -d)"
  export GH_AGENTS_HOME="$TEST_HOME"
  STUB="$TEST_HOME/bin"; mkdir -p "$STUB"; export PATH="$STUB:$PATH"
  REPO_ROOT="$(cd "$BATS_TEST_DIRNAME/../.." && pwd)"
  export CALLS="$TEST_HOME/calls"; : > "$CALLS"
  for b in gh sudo systemctl find; do
    cat > "$STUB/$b" <<EOF
#!/usr/bin/env bash
echo "$b \$*" >> "$CALLS"
case "\$*" in
  *"remove-token"*) echo '{"token":"RMTOK"}' ;;
  *"runners"*) echo '{"runners":[]}' ;;
  *"repos/"*) echo '{"visibility":"private"}' ;;
  *"is-active"*) echo "inactive"; exit 3 ;;
  *"list-units"*) echo "actions.runner.o-r.own--rep-1.service loaded inactive dead" ;;
  *) exit 0 ;;
esac
EOF
    chmod +x "$STUB/$b"
  done
  # config.sh/svc.sh stubs live inside each fake runner dir
  mkdir -p "$GH_AGENTS_HOME/runners/own--rep/1"
  for s in config.sh svc.sh; do
    cat > "$GH_AGENTS_HOME/runners/own--rep/1/$s" <<EOF
#!/usr/bin/env bash
echo "$s \$*" >> "$CALLS"
EOF
    chmod +x "$GH_AGENTS_HOME/runners/own--rep/1/$s"
  done
}

teardown() { rm -rf "$TEST_HOME"; }

@test "disable-repo removes registration, then dir" {
  run "$REPO_ROOT/runner/disable-repo.sh" own/rep
  [ "$status" -eq 0 ]
  grep -q "config.sh remove" "$CALLS"
  [ ! -d "$GH_AGENTS_HOME/runners/own--rep/1" ]
}

@test "disable-repo on unknown scope exits cleanly" {
  run "$REPO_ROOT/runner/disable-repo.sh" ghost/repo
  [ "$status" -eq 0 ]
  [[ "$output" == *"nada a remover"* || "$output" == *"nothing"* ]]
}

@test "status.sh lists scopes without crashing on empty fleet" {
  run "$REPO_ROOT/runner/status.sh"
  [ "$status" -eq 0 ]
}
```

Note: `disable-*.sh` must `cd` into the runner dir before `./config.sh remove` — config.sh runs from its own directory.

- [ ] **Step 2: Run to verify failure**

Run: `bats runner/tests/lifecycle.bats`
Expected: FAIL (scripts missing).

- [ ] **Step 3: Write the scripts**

`runner/disable-repo.sh`:

```bash
#!/usr/bin/env bash
# Remove runners de repo: para/desinstala units, desregistra no GitHub, remove dirs.
# Uso: disable-repo.sh <owner>/<repo>
set -euo pipefail

[ $# -ge 1 ] || { echo "uso: $0 <owner>/<repo>" >&2; exit 1; }
REPO="$1"

source "$(dirname "$0")/lib.sh"
need gh
gh auth status >/dev/null 2>&1 || die "gh sem auth"

SCOPE="$(scope_repo "$REPO")"
BASE="$RUNNERS_DIR/$SCOPE"
[ -d "$BASE" ] || { echo "==> nada a remover: $BASE não existe"; exit 0; }

for dir in "$BASE"/*/; do
  [ -d "$dir" ] || continue
  echo "==> removendo runner em $dir"
  (
    cd "$dir"
    if [ -f ./svc.sh ]; then
      sudo ./svc.sh stop || true
      sudo ./svc.sh uninstall || true
    fi
    if [ -f ./.runner ]; then
      token="$(repo_removal_token "$REPO")"
      ./config.sh remove --token "$token"
    fi
  )
  rm -rf "$dir"
done
rmdir "$BASE" 2>/dev/null || true

echo "==> verificação"
gh api "repos/$REPO/actions/runners" \
  --jq --arg s "$SCOPE" '[.runners[] | select(.name | startswith($s))] | length as $n | "runners restantes: \($n)"'
```

`runner/disable-org.sh` — same shape with `scope_org`, `org_removal_token`, `orgs/$ORG/actions/runners`.

`runner/status.sh`:

```bash
#!/usr/bin/env bash
# Estado da fleet: dirs locais, units systemd, runners registrados via API.
# Uso: status.sh
set -euo pipefail

source "$(dirname "$0")/lib.sh"

echo "==> runners locais em $RUNNERS_DIR"
[ -d "$RUNNERS_DIR" ] && find "$RUNNERS_DIR" -mindepth 2 -maxdepth 2 -type d | sort || echo "(nenhum)"

echo "==> units actions.runner.*"
systemctl list-units --all 'actions.runner.*' --no-legend 2>/dev/null || echo "(nenhuma)"

echo "==> runners registrados (por escopo local)"
for scope_dir in "$RUNNERS_DIR"/*/; do
  [ -d "$scope_dir" ] || continue
  scope="$(basename "$scope_dir")"
  case "$scope" in
    org--*) org="${scope#org--}"
      gh api "orgs/$org/actions/runners" --jq --arg s "$scope" \
        '.runners[] | select(.name | startswith($s)) | "\(.name)\t\(.status)"' ;;
    *--*) repo="${scope/--//}"
      gh api "repos/$repo/actions/runners" --jq --arg s "$scope" \
        '.runners[] | select(.name | startswith($s)) | "\(.name)\t\(.status)"' ;;
  esac
done
```

`runner/cleanup.sh`:

```bash
#!/usr/bin/env bash
# Apaga _work de runners cuja unit está inativa há >7 dias. Roda diariamente
# via gh-agents-cleanup.timer (sucessor do factory-disk-cleanup).
set -euo pipefail

source "$(dirname "$0")/lib.sh"

[ -d "$RUNNERS_DIR" ] || exit 0
for dir in "$RUNNERS_DIR"/*/*/; do
  [ -d "$dir/_work" ] || continue
  unit="$(unit_for "${dir%/}")"
  active="unknown"
  [ -n "$unit" ] && active="$(systemctl is-active "$unit" 2>/dev/null || echo inactive)"
  if [ "$active" = "inactive" ] || [ "$active" = "failed" ]; then
    if [ -n "$(find "$dir/_work" -maxdepth 0 -mtime +7 2>/dev/null)" ]; then
      echo "==> removendo $dir/_work (unit ${unit:-desconhecida} $active, >7d)"
      rm -rf "$dir/_work"
    fi
  fi
done
echo "==> cleanup concluído"
```

`runner/systemd/gh-agents-cleanup.service`:

```ini
[Unit]
Description=Remove _work dirs of gh-agents runners idle >7 days

[Service]
Type=oneshot
User=gh-agents
ExecStart=/home/gh-agents/gh-agents/runner/cleanup.sh
```

`runner/systemd/gh-agents-cleanup.timer`:

```ini
[Unit]
Description=Daily gh-agents fleet cleanup

[Timer]
OnCalendar=daily
Persistent=true

[Install]
WantedBy=timers.target
```

`runner/install-cleanup.sh` (runs with sudo; the only script that touches `/etc`):

```bash
#!/usr/bin/env bash
# Instala o timer diário de limpeza da fleet. Idempotente. Precisa de sudo.
# Uso: install-cleanup.sh
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"

echo "==> instalando units gh-agents-cleanup"
sudo install -m 0644 "$HERE/systemd/gh-agents-cleanup.service" /etc/systemd/system/
sudo install -m 0644 "$HERE/systemd/gh-agents-cleanup.timer" /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now gh-agents-cleanup.timer

echo "==> verificação"
systemctl list-timers gh-agents-cleanup.timer --no-legend
```

- [ ] **Step 4: Run bats + shellcheck — expect pass/clean**

```bash
bats runner/tests/
shellcheck runner/*.sh
```

Fix reds. `unit_for`'s name-reconstruction is heuristic — if the test shows it can't match real unit names, prefer matching on the runner dir name suffix (the `--name` we passed to config.sh appears in the unit name).

- [ ] **Step 5: Commit**

```bash
git add runner/
git commit -m "feat(fleet): disable/status scripts and daily _work cleanup timer"
```

---

### Task 7: Caller template + README

**Files:**
- Create: `templates/caller-agents.yml`
- Create: `README.md`

**Interfaces:**
- The caller template is the copy-paste artifact for onboarding step 3 of the spec. Its `permissions:` superset must cover the union of the three jobs' permissions (`actions:read, contents:write, pull-requests:write, issues:write`) — a reusable callee can only use what the caller grants.

- [ ] **Step 1: Write `templates/caller-agents.yml`**

```yaml
name: agents

# Enables gh-agents on this repo: PR review, `/oc` fix, CI diagnosis.
# Onboarding checklist: https://github.com/heliowap/gh-agents#onboarding

on:
  pull_request:
    # set this to the repo's default branch
    branches: [main]
    types: [opened, synchronize, reopened, ready_for_review]
    paths-ignore:
      - 'docs/**'
      - '**/*.md'
  issue_comment:
    types: [created]
  pull_request_review_comment:
    types: [created]
  workflow_run:
    workflows: ['*']   # narrow via the ci_workflows input instead of editing this
    types: [completed]

# The reusable callee can only use what is granted here — this is the union
# of its three jobs' permissions.
permissions:
  actions: read
  contents: write
  pull-requests: write
  issues: write

jobs:
  agents:
    uses: heliowap/gh-agents/.github/workflows/agents.yml@v1
    secrets: inherit
    # with:
    #   runs-on: self-hosted        # default; vars.AGENT_RUNNER overrides per repo
    #   model: opencode-go/glm-5.3-flash
    #   use_container: true         # false = run on host (tests needing Docker)
    #   ci_workflows: 'ci,qe'       # empty = watch all failed runs
```

- [ ] **Step 2: Write `README.md`** (prose.md rules: plain sentences, tables for option/meaning, runnable bash blocks, no marketing)

Sections, in order:

1. **What it is** — 3 sentences from spec §Arquitetura: reusable workflow running OpenCode agents (review, `/oc` fix, ci-doctor) on a self-hosted fleet; enable per repo.
2. **Onboarding** — the spec's 5-step checklist verbatim (enable-runner, `gh secret set OPENCODE_API_KEY`, copy `templates/caller-agents.yml` adjusting `on.pull_request.branches`, optional `vars.AGENT_RUNNER`/`vars.CI_RUNNER`/own `opencode.json`, optional gh-agents-ops App).
3. **Inputs table** — each `workflow_call` input, default, meaning. Include `secrets: inherit` + `OPENCODE_API_KEY` requirement.
4. **Runner switch** — `vars.AGENT_RUNNER` (agents) then input default; `vars.CI_RUNNER` conversion line `runs-on: ${{ vars.CI_RUNNER || 'ubuntu-latest' }}`; valid values table: `self-hosted`, `ubuntu-latest`, `depot-ubuntu-24.04[-4|-8]`, `ubicloud-standard-2`.
5. **What the agents do** — review (BLOCKING/WARNING/NIT + `review-blocking` issue), fix (`/oc` gates: OWNER/MEMBER/COLLABORATOR, non-Bot; substring `/oc` is a coarse pre-filter — the action's mention parsing is authoritative), ci-doctor (diagnosis-only, dedup marker, skips runs without PR).
6. **Security model** — public repo, SHA-pinned actions, private-repos-only fleet, comment gate, minimal per-job permissions, container default (and `use_container: false` caveat), PAT never in workflows.
7. **Reserved paths** — `.gh-agents/` is checked out by the workflow; don't track that dir in a caller repo.
8. **Operating the fleet** — pointer to `runner/` scripts with one-line usage each; `status.sh`; cleanup timer.

- [ ] **Step 3: Lint the template as YAML + commit**

```bash
python3 -c "import yaml,sys; yaml.safe_load(open('templates/caller-agents.yml'))" 2>/dev/null \
  || python3 -c "import json; print('pyyaml ausente — validação via actionlint no CI')"
git add templates/ README.md
git commit -m "docs: caller template and onboarding README"
```

---

### Task 8: Repo CI — `.github/workflows/lint.yml`

**Files:**
- Create: `.github/workflows/lint.yml`

**Interfaces:**
- Produces: the dogfood CI loop (dod.md loop 1 made automatic). Runs on `ubuntu-latest` — this repo is **public**, so it must never use `self-hosted` (spec security rule applies to itself).

- [ ] **Step 1: Write `.github/workflows/lint.yml`**

```yaml
name: lint

# The repo's own feedback loop: actionlint, shellcheck, bats, pytest,
# opencode.json schema, runtime image build. Runs on ubuntu-latest — this
# repo is public; self-hosted runners are for private repos only.

on:
  pull_request:
  push:
    branches: [main]

permissions:
  contents: read

jobs:
  checks:
    runs-on: ubuntu-latest
    timeout-minutes: 15
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1

      - name: Install tools
        run: |
          set -euo pipefail
          sudo apt-get update -qq && sudo apt-get install -y -qq shellcheck bats
          python3 -m pip install --quiet pytest check-jsonschema
          mkdir -p /tmp/actionlint
          curl -fsSL https://github.com/rhysd/actionlint/releases/latest/download/actionlint_linux_amd64.tar.gz \
            | tar xz -C /tmp/actionlint
          sudo install /tmp/actionlint/actionlint /usr/local/bin/

      - name: actionlint
        run: actionlint .github/workflows/*.yml

      - name: shellcheck
        run: shellcheck runner/*.sh

      - name: bats (fleet scripts)
        run: bats runner/tests/

      - name: pytest (scripts)
        run: python3 -m pytest scripts/tests/ -q

      - name: opencode.json schema
        run: check-jsonschema --schemafile https://opencode.ai/config.json agents/opencode.json

      - name: runtime image builds
        run: docker build runtime/
```

- [ ] **Step 2: actionlint + commit**

```bash
actionlint .github/workflows/lint.yml
git add .github/workflows/lint.yml
git commit -m "ci: lint/test/build loop for the repo itself"
```

---

### Task 9: End-to-end verification on a scratch repo

**Files:** none in this repo — creates `heliowap/gh-agents-e2e` (private) as the caller.

**Interfaces:** exercises the contract callers actually use: `uses: .../agents.yml@<ref>`, `secrets: inherit`, `vars.AGENT_RUNNER`.

Prerequisites that may need the human: `OPENCODE_API_KEY` value (can't be read back from repo secrets — get it from the operator or a local env file), and the `v1` ref must exist (Task 10 tags it; for e2e before tagging, point the caller at `@main` temporarily or push a `v1` tag on the merge commit).

- [ ] **Step 1: Create the scratch caller repo**

```bash
gh repo create heliowap/gh-agents-e2e --private --description "e2e scratch for gh-agents"
git clone https://github.com/heliowap/gh-agents-e2e /tmp/gh-agents-e2e && cd /tmp/gh-agents-e2e
mkdir -p .github/workflows
cp /home/helio/Projetos/gh-agents/templates/caller-agents.yml .github/workflows/agents.yml
# tiny app so the PR has a diff
printf 'print("hello")\n' > app.py
git add -A && git commit -m "init" && git push -u origin main
gh secret set OPENCODE_API_KEY --repo heliowap/gh-agents-e2e   # value from operator/env
gh variable set AGENT_RUNNER --value ubuntu-latest --repo heliowap/gh-agents-e2e  # no self-hosted yet — also tests the switch
```

- [ ] **Step 2: Verify the `review` job**

```bash
cd /tmp/gh-agents-e2e
git checkout -b test-pr && printf 'x = undefined_name\nprint(x)\n' > bug.py
git add bug.py && git commit -m "add bug" && git push -u origin test-pr
gh pr create --title "test review" --body "e2e" --base main
gh run list --repo heliowap/gh-agents-e2e --limit 3
gh run watch --repo heliowap/gh-agents-e2e   # the review run
```

Expected: `Review` job runs on `ubuntu-latest` inside the runtime container, posts a review comment ending in `SUMMARY:` (expect ≥1 BLOCKING for `undefined_name`), and — if BLOCKING>0 — a `review-blocking` issue is created.

- [ ] **Step 3: Verify the `fix` job**

```bash
gh pr comment 1 --repo heliowap/gh-agents-e2e --body "/oc fix the undefined variable in bug.py"
gh run watch --repo heliowap/gh-agents-e2e
git fetch && git log --oneline origin/test-pr -3
```

Expected: `Fix` job runs (commenter is OWNER, non-Bot), commits a fix to `test-pr`. Also verify the gate: a comment without `/oc` triggers no job.

- [ ] **Step 4: Verify `ci-doctor`**

```bash
cat > .github/workflows/broken.yml <<'EOF'
name: broken
on: pull_request
permissions: { contents: read }
jobs: { fail: { runs-on: ubuntu-latest, steps: [{ run: "exit 1" }] } }
EOF
git add .github/workflows/broken.yml && git commit -m "broken ci" && git push
gh run watch --repo heliowap/gh-agents-e2e
gh pr view 1 --repo heliowap/gh-agents-e2e --comments | tail -20
```

Expected: after `broken` fails, `CI doctor` runs and posts ONE comment on the PR ending with `<!-- ci-doctor:<sha> -->`. Re-push the same SHA (`git commit --amend --no-edit` won't change tree → use `git commit --allow-empty` then check dedup only fires for the *new* sha; a second run at the same sha is skipped).

- [ ] **Step 5: Record evidence + cleanup decision**

Paste run links into the eventual PR/commit message. Ask the operator whether to keep `gh-agents-e2e` for regression checks or delete it (`gh repo delete` is destructive — requires explicit confirmation).

---

### Task 10: Rollout — operator steps (needs VPS SSH + tags)

These are **not** executed by the implementing agent; they're the human's runbook. Each line is runnable as written from `intrador-tech-vps` unless noted.

- [ ] **Step 1: Land and tag**

```bash
# merge this branch to main (PR through the repo's own review), then:
git checkout main && git pull
git tag -a v1 -m "v1: review, /oc fix, ci-doctor" && git push origin v1
# build-runtime.yml pushes ghcr.io/heliowap/gh-agents-runtime:v1 on merge

# The new ghcr package is PRIVATE by default and callers pull it with no
# credentials — make it public once, or every container job fails to pull:
#   Repo → Packages → gh-agents-runtime → Package settings → Change visibility → public
# (or: gh api -X PATCH /user/packages/container/gh-agents-runtime -f visibility=public)

# Then re-verify the container path on the scratch repo: flip the caller's
# `use_container` to true (or drop it — true is the default) and open a PR.
# Pre-merge e2e ran with use_container: false because the image didn't exist.
```

- [ ] **Step 2: Provision the fleet user on intrador-tech-vps**

```bash
sudo useradd -m -s /bin/bash gh-agents
sudo usermod -aG docker gh-agents
sudo -u gh-agents git clone https://github.com/heliowap/gh-agents /home/gh-agents/gh-agents
# authenticate gh for the gh-agents user (PAT with repo + admin:org, local shell only)
sudo -u gh-agents gh auth login
```

- [ ] **Step 3: Decommission `factory-ci-*` (spec §Fleet)**

```bash
# as the current owner of the old runners:
for d in /home/helio/actions-runner*/; do
  ( cd "$d" && sudo ./svc.sh stop && sudo ./svc.sh uninstall \
    && ./config.sh remove --token "$(gh api -X POST repos/heliowap/intrador-platform/actions/runners/remove-token --jq .token)" )
done
rm -rf /home/helio/actions-runner*/
# fold remove-factory-review.sh in: delete the stale script alongside
```

Verify: `gh api repos/heliowap/intrador-platform/actions/runners --jq '.runners[].name'` shows no `factory-ci-*`.

- [ ] **Step 4: Install the new fleet + cleanup timer**

```bash
sudo -u gh-agents /home/gh-agents/gh-agents/runner/enable-repo.sh heliowap/intrador-platform 2
sudo /home/gh-agents/gh-agents/runner/install-cleanup.sh
sudo -u gh-agents /home/gh-agents/gh-agents/runner/status.sh
```

Expected: 2 `heliowap--intrador-platform-*` runners online, timer listed.

- [ ] **Step 5: Enable intrador-platform end-to-end (spec §Rollout 3-4)**

```bash
# in intrador-platform: copy templates/caller-agents.yml → .github/workflows/agents.yml,
# set on.pull_request.branches to [dev], keep opencode.yml during transition,
# then verify on a real PR: review on self-hosted runner, /oc commits,
# broken CI → diagnosis comment, AGENT_RUNNER flip moves the job.
```

- [ ] **Step 6: Orgs on demand**

`enable-org.sh intrador 2`, `enable-org.sh All-Medical 2` when the first repo in each org asks for it — not before.

---

## Self-review notes

- **Spec coverage:** review job §66-76 → Task 4 + Task 1; fix §77-83 → Task 4 + Task 2; ci-doctor §85-94 → Task 4 + Task 2; comum §96-104 → Tasks 3-4; runner switch §106-115 → Tasks 4, 7; fleet §117-137 → Tasks 5-6, 10; segurança §139-149 → Tasks 4-6, 7; onboarding §160-167 → Task 7; rollout §169-179 → Tasks 9-10. `ci_auto_fix` stays v2 (input reserved? — spec says reserved for v2; not adding a dead input now, noted for the release notes).
- **Open verification:** `opencode run --agent` flag name (Task 4 Step 2); `vars` in reusable-workflow `runs-on` resolves to caller repo vars (spec §60-63 says verify — Task 9 proves it by exercising `AGENT_RUNNER` on the scratch repo).
