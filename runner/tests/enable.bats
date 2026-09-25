#!/usr/bin/env bats

setup() {
  TEST_HOME="$(mktemp -d)"
  export GH_AGENTS_HOME="$TEST_HOME"
  export GH_AGENTS_UNIT_DIR="$TEST_HOME/units"
  STUB="$TEST_HOME/bin"; mkdir -p "$STUB"
  export PATH="$STUB:$PATH"
  REPO_ROOT="$(cd "$BATS_TEST_DIRNAME/../.." && pwd)"

  cat > "$STUB/gh" <<'EOF'
#!/usr/bin/env bash
# stub: records calls; answers the API shapes the scripts use; honors --jq
echo "$@" >> "$GH_CALLS"
jqexpr=""; prev=""
for a in "$@"; do [ "$prev" = "--jq" ] && jqexpr="$a"; prev="$a"; done
case "$*" in
  *"repos/"*"/actions/runners/registration-token"*) json='{"token":"REGTOK"}' ;;
  *"orgs/"*"/actions/runners/registration-token"*) json='{"token":"ORGTOK"}' ;;
  *"repos/"*"/actions/runners"*) json='{"runners":[]}' ;;
  *"runner-groups"*"POST"*|*"-X POST"*"runner-groups"*) json='{"id":7}' ;;
  *"runner-groups"*) json='{"runner_groups":[{"id":7,"name":"gh-agents","visibility":"private"}]}' ;;
  *"repos/actions/runner/releases/latest"*) json='{"tag_name":"v2.320.0"}' ;;
  *"repos/"*) json='{"visibility":"private"}' ;;
  *"auth status"*) exit 0 ;;
  *) json='{}' ;;
esac
if [ -n "$jqexpr" ]; then echo "$json" | jq -r "$jqexpr"; else echo "$json"; fi
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
jqexpr=""; prev=""
for a in "$@"; do [ "$prev" = "--jq" ] && jqexpr="$a"; prev="$a"; done
case "$*" in
  *"repos/"*"/actions/runners"*) json='{"runners":[]}' ;;
  *"repos/"*) json='{"visibility":"public"}' ;;
  *) json='{}' ;;
esac
if [ -n "$jqexpr" ]; then echo "$json" | jq -r "$jqexpr"; else echo "$json"; fi
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

@test "enable-repo refuses when a legacy system unit holds the runner" {
  scope="owner--repo"; d="$GH_AGENTS_HOME/runners/$scope/1"
  mkdir -p "$d/bin"; touch "$d/.runner" "$d/bin/runsvc.sh"
  echo "actions.runner.owner-repo.owner--repo-1.service" > "$d/.service"
  cat > "$STUB/systemctl" <<'EOF'
#!/usr/bin/env bash
# system bus still knows the legacy unit; user bus stays empty
case "$*" in *--user*) exit 0 ;; *) echo "actions.runner.owner-repo.owner--repo-1.service loaded active running"; exit 0 ;; esac
EOF
  chmod +x "$STUB/systemctl"
  run "$REPO_ROOT/runner/enable-repo.sh" owner/repo 1
  [ "$status" -ne 0 ]
  [[ "$output" == *"legada"* || "$output" == *"legacy"* ]]
  [[ "$output" == *"svc.sh"* ]]
}

@test "enable-repo is idempotent on a configured runner" {
  scope="owner--repo"
  for n in 1 2; do
    mkdir -p "$GH_AGENTS_HOME/runners/$scope/$n/bin"
    touch "$GH_AGENTS_HOME/runners/$scope/$n/.runner" "$GH_AGENTS_HOME/runners/$scope/$n/bin/runsvc.sh"
  done
  run "$REPO_ROOT/runner/enable-repo.sh" owner/repo 2
  [ "$status" -eq 0 ]
  [[ "$output" == *"já configurado"* || "$output" == *"already"* ]]
}
