# Workflows (`.github/workflows/`)

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
- External actions are pinned by full commit SHA with the version in a
  trailing comment: `uses: actions/checkout@<sha> # v6`.
