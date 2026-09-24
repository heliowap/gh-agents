# Maintainer skills (`.agents/skills/`)

Runbooks for agents working **on** this repo — fleet ops, repo onboarding,
releases, the DoD loop. They are a different artifact from `skills/`, which
ships generic fallbacks into caller checkouts: maintainer skills name real
hosts, paths and repos and must never reach a caller.

## Layout

- Canonical copy: `.agents/skills/<name>/SKILL.md` — versioned.
- Per-harness discovery: symlinks, not copies —
  `.claude/skills/<name>`, `.cursor/skills/<name>`,
  `.opencode/skills/<name>` → `../../.agents/skills/<name>`.
- `.gitignore` tracks everything in those skills dirs except `impeccable`
  (locally installed tooling). New skills need no `.gitignore` edit.

## Adding a skill

```bash
mkdir .agents/skills/<name>          # write SKILL.md
for d in .claude .cursor .opencode; do
  ln -s ../../.agents/skills/<name> "$d/skills/<name>"
done
git add .agents/skills/<name> .{claude,cursor,opencode}/skills/<name>
```

## Writing rules

Same shape as the caller-facing skills, minus the anonymity rule: frontmatter
`name` + `description: Use when …` (triggers only, no workflow summary),
concise bodies, tables over prose. Commands must be runnable as written —
they name real hosts and paths on purpose.
