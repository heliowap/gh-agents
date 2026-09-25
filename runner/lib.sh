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
