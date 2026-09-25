#!/usr/bin/env bash
# Estado da fleet: dirs locais, units systemd, runners registrados via API.
# Uso: status.sh
set -euo pipefail

# shellcheck disable=SC1091 # lib.sh sits next to this script by convention
source "$(dirname "$0")/lib.sh"

echo "==> runners locais em $RUNNERS_DIR"
[ -d "$RUNNERS_DIR" ] && find "$RUNNERS_DIR" -mindepth 2 -maxdepth 2 -type d | sort || echo "(nenhum)"

echo "==> units actions.runner.*"
systemctl --user list-units --all 'actions.runner.*' --no-legend 2>/dev/null || echo "(nenhuma)"

echo "==> runners registrados (por escopo local)"
for scope_dir in "$RUNNERS_DIR"/*/; do
  [ -d "$scope_dir" ] || continue
  scope="$(basename "$scope_dir")"
  case "$scope" in
    org--*) org="${scope#org--}"
      # shellcheck disable=SC2016 # $s is a jq variable (--arg), not shell
      gh api "orgs/$org/actions/runners" \
        | jq -r --arg s "$scope" '.runners[] | select(.name | startswith($s)) | "\(.name)\t\(.status)"' ;;
    *--*) repo="${scope/--//}"
      # shellcheck disable=SC2016 # $s is a jq variable (--arg), not shell
      gh api "repos/$repo/actions/runners" \
        | jq -r --arg s "$scope" '.runners[] | select(.name | startswith($s)) | "\(.name)\t\(.status)"' ;;
  esac
done
