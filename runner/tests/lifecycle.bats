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
jqexpr=""; prev=""
for a in "\$@"; do [ "\$prev" = "--jq" ] && jqexpr="\$a"; prev="\$a"; done
case "\$*" in
  *"remove-token"*) json='{"token":"RMTOK"}' ;;
  *"runners"*) json='{"runners":[]}' ;;
  *"repos/"*) json='{"visibility":"private"}' ;;
  *"is-active"*) echo "inactive"; exit 3 ;;
  *"list-units"*) echo "actions.runner.o-r.own--rep-1.service loaded inactive dead" ;;
  *) exit 0 ;;
esac
if [ -n "\$jqexpr" ]; then echo "\$json" | jq -r "\$jqexpr"; else echo "\$json"; fi
EOF
    chmod +x "$STUB/$b"
  done
  # config.sh/svc.sh stubs live inside each fake runner dir; .runner marks it registered
  mkdir -p "$GH_AGENTS_HOME/runners/own--rep/1"
  touch "$GH_AGENTS_HOME/runners/own--rep/1/.runner"
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
  # fleet.md order: registration removal, then units, then dirs
  first_cfg="$(grep -n 'config.sh remove' "$CALLS" | head -1 | cut -d: -f1)"
  first_svc="$(grep -n 'svc.sh' "$CALLS" | head -1 | cut -d: -f1)"
  [ -n "$first_cfg" ] && [ -n "$first_svc" ] && [ "$first_cfg" -lt "$first_svc" ]
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
