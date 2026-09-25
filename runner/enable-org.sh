#!/usr/bin/env bash
# Registra N runners de ORG no runner group `gh-agents` (visibility: private —
# grupo garante que só repos privados do org chegam aos runners).
# Uso: enable-org.sh <org> [N=2]   (PAT precisa de admin:org)
set -euo pipefail

[ $# -ge 1 ] || { echo "uso: $0 <org> [N=2]" >&2; exit 1; }
ORG="$1"; N="${2:-2}"

# shellcheck disable=SC1091 # lib.sh sits next to this script by convention
source "$(dirname "$0")/lib.sh"
need gh; need curl; need tar
gh auth status >/dev/null 2>&1 || die "gh sem auth — PAT com admin:org necessário"

echo "==> garantindo runner group gh-agents (private) em $ORG"
GROUP_ID="$(ensure_private_runner_group "$ORG")"

SCOPE="$(scope_org "$ORG")"
VERSION="$(latest_runner_version)"
echo "==> $N runner(s) para org $ORG em $RUNNERS_DIR/$SCOPE (group $GROUP_ID)"

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
    token="$(org_registration_token "$ORG")"
    ./config.sh --unattended \
      --url "https://github.com/$ORG" \
      --token "$token" \
      --name "${SCOPE}-${i}" \
      --labels agents \
      --runnergroup "$GROUP_ID" \
      --work _work \
      --replace
    sudo ./svc.sh install "$USER"
    sudo ./svc.sh start
  )
done

echo "==> verificação"
# shellcheck disable=SC2016 # $s is a jq variable (--arg), not shell
gh api "orgs/$ORG/actions/runners" \
  | jq -r --arg s "$SCOPE" '.runners[] | select(.name | startswith($s)) | "\(.name)\t\(.status)"'
