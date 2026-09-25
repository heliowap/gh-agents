#!/usr/bin/env bash
# Remove runners de repo: para/desinstala units, desregistra no GitHub, remove dirs.
# Uso: disable-repo.sh <owner>/<repo>
set -euo pipefail

[ $# -ge 1 ] || { echo "uso: $0 <owner>/<repo>" >&2; exit 1; }
REPO="$1"

# shellcheck disable=SC1091 # lib.sh sits next to this script by convention
source "$(dirname "$0")/lib.sh"
need gh
gh auth status >/dev/null 2>&1 || die "gh sem auth"

SCOPE="$(scope_repo "$REPO")"
BASE="$RUNNERS_DIR/$SCOPE"
[ -d "$BASE" ] || { echo "==> nada a remover: $BASE não existe"; exit 0; }

for dir in "$BASE"/*/; do
  [ -d "$dir" ] || continue
  echo "==> removendo runner em $dir"
  (
    cd "$dir"
    # ordem do fleet.md: desregistro → units → diretório
    if [ -f ./.runner ]; then
      token="$(repo_removal_token "$REPO")"
      ./config.sh remove --token "$token"
    fi
    if [ -f ./svc.sh ]; then
      sudo ./svc.sh stop || true
      sudo ./svc.sh uninstall || true
    fi
  )
  rm -rf "$dir"
done
rmdir "$BASE" 2>/dev/null || true

echo "==> verificação"
# shellcheck disable=SC2016 # $s is a jq variable (--arg), not shell
gh api "repos/$REPO/actions/runners" \
  | jq -r --arg s "$SCOPE" '[.runners[] | select(.name | startswith($s))] | length as $n | "runners restantes: \($n)"'
