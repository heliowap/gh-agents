# Workflows (`.github/workflows/`)

- `permissions: contents: read` at the top; each job asks for more, by name.
  No job gets `actions: write`.
- Every job has `timeout-minutes` and a `concurrency` group keyed by the
  PR/issue number only — keying by `event_name` too would put a `/oc`
  comment in a different group and let it race the in-flight review it
  followed (intrador #1417). `cancel-in-progress: false` queues the newer
  run instead of killing the one in flight; a queued run is still replaced
  by newer arrivals, so stale pending runs clean themselves up.
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
