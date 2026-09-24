# Tests

TDD is the default for code. The `tdd` skill is the reference — load it
before writing the first test of a change. What follows is how its rules map
onto this repo.

## Seams

Tests live at seams — public interfaces — never against internals. Before
writing any test, write down the seams under test and confirm them. One seam,
one failing test, one minimal implementation, repeat: vertical slices, no
bulk test-writing.

Per content type:

| Content | Seam | Check |
|---|---|---|
| Python helpers (e.g. review parsing) | module's public functions | `pytest`, driven through the interface, no internals |
| `runner/*.sh` | the script's CLI (args → exit code + effects) | `bats` when the script has logic worth testing; the self-verification block is the runtime test |
| `.github/workflows/` | the workflow's observable behaviour on a caller repo | `actionlint` locally; e2e on a real test repo before the tag moves |
| `agents/opencode.json` | the file itself | schema validation in CI |
| `skills/*.md` | an agent session that loads it | no unit test — behaviour eval, see `agents-skills.md` |

A fix comes with a test that fails without it. A feature covers each mode it
touches. Expected values come from an independent source of truth — never
recomputed the way the code does.

## Complexity budget

Cyclomatic complexity per function stays **≤ 10**; CRAP score flagged above
~30. Enforced where tooling exists: `ruff --select C901` (mccabe) on Python,
`gocyclo -over 10` on Go. Where no tool exists (bash, YAML), the budget is a
review rule: a function over ~40 lines or a condition you cannot say in one
sentence is a signal to extract, not to comment harder.

The budget exists because agents read and edit this code. Low complexity is
not aesthetics: it is how much of a file a reader — human or model — must
hold in head at once, and how many paths a test must cover. When a rule and
clarity conflict, clarity wins; note it in the PR.
