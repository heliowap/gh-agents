# Commits and pull requests

Conventional Commits. Callers pin `@v1`-style tags, so releases are
deliberate: a maintainer tags after merge; there is no release automation yet.

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
