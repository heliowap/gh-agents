# Agents, prompts and skills (`agents/`, `skills/`)

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
  point of the fallback order.
- `opencode.json` validates against the opencode schema; every agent named in
  a workflow `with:` exists in `agents/opencode.json` or the caller's own.
