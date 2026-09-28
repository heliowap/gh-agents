#!/usr/bin/env bats
# Seam: runner/ci-provider.sh <owner>/<repo> <provider> → repo variables set + exit code.

setup() {
  TEST_HOME="$(mktemp -d)"
  STUB="$TEST_HOME/bin"; mkdir -p "$STUB"; export PATH="$STUB:$PATH"
  REPO_ROOT="$(cd "$BATS_TEST_DIRNAME/../.." && pwd)"
  export GH_CALLS="$TEST_HOME/gh-calls"; : > "$GH_CALLS"
  export VARS="$TEST_HOME/vars"; : > "$VARS"
  export CI_RUNNERS_ONLINE=1
  cat > "$STUB/gh" <<'EOS'
#!/usr/bin/env bash
# stub: variable set/list backed by a file; runners answer per CI_RUNNERS_ONLINE
echo "$*" >> "$GH_CALLS"
jqexpr=""; prev=""
for a in "$@"; do [ "$prev" = "--jq" ] && jqexpr="$a"; prev="$a"; done
case "$1 $2" in
  "auth status") exit 0 ;;
  "variable set") name="$3"; shift 3
    while [ $# -gt 0 ]; do case "$1" in --body) body="$2"; shift 2;; *) shift;; esac; done
    grep -v "^$name	" "$VARS" > "$VARS.tmp" || true; mv "$VARS.tmp" "$VARS"
    printf '%s\t%s\n' "$name" "$body" >> "$VARS"; exit 0 ;;
  "variable list") cat "$VARS"; exit 0 ;;
esac
case "$*" in
  *"/actions/runners"*)
    if [ "$CI_RUNNERS_ONLINE" = 1 ]; then
      json='{"runners":[{"name":"o--r-ci-1","status":"online","labels":[{"name":"ci"}]},{"name":"o--r-1","status":"online","labels":[{"name":"self-hosted"},{"name":"agents"}]}]}'
    else
      json='{"runners":[{"name":"o--r-1","status":"online","labels":[{"name":"self-hosted"},{"name":"agents"}]}]}'
    fi ;;
  *) json='{}' ;;
esac
if [ -n "$jqexpr" ]; then echo "$json" | jq -r "$jqexpr"; else echo "$json"; fi
EOS
  chmod +x "$STUB/gh"
}

teardown() { rm -rf "$TEST_HOME"; }

var() { awk -F'\t' -v n="$1" '$1 == n {print $2}' "$VARS"; }

@test "depot sets the three sizes to Depot labels" {
  run "$REPO_ROOT/runner/ci-provider.sh" o/r depot
  [ "$status" -eq 0 ]
  [ "$(var CI_RUNNER)" = "depot-ubuntu-24.04" ]
  [ "$(var CI_RUNNER_4)" = "depot-ubuntu-24.04-4" ]
  [ "$(var CI_RUNNER_8)" = "depot-ubuntu-24.04-8" ]
}

@test "ubicloud and github map every size" {
  run "$REPO_ROOT/runner/ci-provider.sh" o/r ubicloud
  [ "$status" -eq 0 ]
  [ "$(var CI_RUNNER)" = "ubicloud-standard-2" ]
  [ "$(var CI_RUNNER_8)" = "ubicloud-standard-8" ]
  run "$REPO_ROOT/runner/ci-provider.sh" o/r github
  [ "$status" -eq 0 ]
  [ "$(var CI_RUNNER)" = "ubuntu-24.04" ]
  [ "$(var CI_RUNNER_4)" = "ubuntu-24.04" ]
}

@test "vps sends every size to the ci runners when they are online" {
  run "$REPO_ROOT/runner/ci-provider.sh" o/r vps
  [ "$status" -eq 0 ]
  [ "$(var CI_RUNNER)" = "ci" ] && [ "$(var CI_RUNNER_8)" = "ci" ]
}

@test "vps refuses without an online ci runner and changes nothing" {
  export CI_RUNNERS_ONLINE=0
  printf 'CI_RUNNER\tdepot-ubuntu-24.04\n' > "$VARS"
  run "$REPO_ROOT/runner/ci-provider.sh" o/r vps
  [ "$status" -ne 0 ]
  [[ "$output" == *"setup-ci-user.sh"* ]]
  [ "$(var CI_RUNNER)" = "depot-ubuntu-24.04" ]
}

@test "an unknown provider is refused with the list of providers" {
  run "$REPO_ROOT/runner/ci-provider.sh" o/r circleci
  [ "$status" -ne 0 ]
  [[ "$output" == *"depot"* && "$output" == *"ubicloud"* && "$output" == *"vps"* ]]
  ! grep -q "variable set" "$GH_CALLS"
}

@test "prints usage without args" {
  run "$REPO_ROOT/runner/ci-provider.sh"
  [ "$status" -ne 0 ]
  [[ "$output" == *"uso"* ]]
}
