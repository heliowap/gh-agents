#!/usr/bin/env bash
# Registra N runners de repo (label `agents`) para owner/repo.
# Idempotente: um dir com .runner já configurado é pulado.
# Uso: enable-repo.sh <owner>/<repo> [N=2]
set -euo pipefail

[ $# -ge 1 ] || { echo "uso: $0 <owner>/<repo> [N=2]" >&2; exit 1; }
REPO="$1"; N="${2:-2}"

# shellcheck disable=SC1091 # lib.sh sits next to this script by convention
source "$(dirname "$0")/lib.sh"
need gh; need curl; need tar
gh auth status >/dev/null 2>&1 || die "gh sem auth — rode 'gh auth login' ou exporte GH_TOKEN"

echo "==> verificando visibilidade de $REPO"
require_private_repo "$REPO"

SCOPE="$(scope_repo "$REPO")"
VERSION="$(latest_runner_version)"
echo "==> $N runner(s) para $REPO em $RUNNERS_DIR/$SCOPE (actions-runner $VERSION)"

mkdir -p "$RUNNERS_DIR/$SCOPE"
for i in $(seq 1 "$N"); do
  dir="$(runner_dir "$SCOPE" "$i")"
  if [ -f "$dir/.runner" ]; then
    echo "==> runner $i já configurado em $dir — pulando"
    continue
  fi
  echo "==> configurando runner $i em $dir"
  mkdir -p "$dir"
  (
    cd "$dir"
    tgz="actions-runner-linux-x64-${VERSION}.tar.gz"
    [ -f "$tgz" ] || curl -fsSL -o "$tgz" \
      "https://github.com/actions/runner/releases/download/v${VERSION}/${tgz}"
    tar xzf "$tgz"
    token="$(repo_registration_token "$REPO")"
    ./config.sh --unattended \
      --url "https://github.com/$REPO" \
      --token "$token" \
      --name "${SCOPE}-${i}" \
      --labels agents \
      --work _work \
      --replace
    install_user_unit "$dir" "${SCOPE}-${i}"
  )
done

echo "==> verificação"
# shellcheck disable=SC2016 # $s is a jq variable (--arg), not shell
gh api "repos/$REPO/actions/runners" \
  | jq -r --arg s "$SCOPE" '.runners[] | select(.name | startswith($s)) | "\(.name)\t\(.status)"'
systemctl list-units 'actions.runner.*' --no-legend 2>/dev/null | grep -F "$SCOPE" || true
