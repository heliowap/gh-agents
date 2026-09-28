#!/usr/bin/env bash
# Troca o provedor do CI de um repo com um comando: define CI_RUNNER,
# CI_RUNNER_4 e CI_RUNNER_8 (padrão, 4 e 8 vCPU) com os rótulos do provedor.
# O workflow do repo lê `vars.CI_RUNNER_<n> || vars.CI_RUNNER || '<hospedado>'`
# por job; esta tabela é o único lugar que conhece os rótulos de cada provedor.
# Idempotente; termina mostrando as variáveis como ficaram.
# Uso: ci-provider.sh <owner>/<repo> <github|depot|ubicloud|vps>
set -euo pipefail

PROVIDERS="github depot ubicloud vps"
[ $# -ge 2 ] || { echo "uso: $0 <owner>/<repo> <$(tr ' ' '|' <<<"$PROVIDERS")>" >&2; exit 1; }
REPO="$1"; PROVIDER="$2"

die() { echo "erro: $*" >&2; exit 1; }
command -v gh >/dev/null || die "'gh' não encontrado no PATH"
gh auth status >/dev/null 2>&1 || die "gh sem auth — rode 'gh auth login' ou exporte GH_TOKEN"

# padrão | 4 vCPU | 8 vCPU. GitHub: runner maior exige configuração da conta,
# então todo tamanho cai no padrão. VPS: um tamanho só (os runners de CI do host).
case "$PROVIDER" in
  github)   sizes=(ubuntu-24.04 ubuntu-24.04 ubuntu-24.04) ;;
  depot)    sizes=(depot-ubuntu-24.04 depot-ubuntu-24.04-4 depot-ubuntu-24.04-8) ;;
  ubicloud) sizes=(ubicloud-standard-2 ubicloud-standard-4 ubicloud-standard-8) ;;
  vps)      sizes=(ci ci ci) ;;
  *) die "provedor '$PROVIDER' desconhecido — use um de: $PROVIDERS" ;;
esac

if [ "$PROVIDER" = vps ]; then
  # sem runner `ci` online os jobs ficariam na fila para sempre
  online="$(gh api "repos/$REPO/actions/runners" \
    --jq '[.runners[] | select(.status == "online" and ([.labels[].name] | index("ci")))] | length')"
  [ "${online:-0}" -gt 0 ] || die "nenhum runner 'ci' online em $REPO — registre com runner/setup-ci-user.sh e RUNNER_ROLE=ci enable-repo.sh (README: CI runners)"
  echo "==> $online runner(s) 'ci' online em $REPO"
fi

echo "==> $REPO: CI no provedor $PROVIDER"
gh variable set CI_RUNNER   --repo "$REPO" --body "${sizes[0]}"
gh variable set CI_RUNNER_4 --repo "$REPO" --body "${sizes[1]}"
gh variable set CI_RUNNER_8 --repo "$REPO" --body "${sizes[2]}"

echo "==> verificação"
got="$(gh variable list --repo "$REPO" | awk -F'\t' '$1 ~ /^CI_RUNNER(_4|_8)?$/ {print $1 "=" $2}' | sort)"
echo "$got"
want="$(printf 'CI_RUNNER=%s\nCI_RUNNER_4=%s\nCI_RUNNER_8=%s\n' "${sizes[@]}" | sort)"
[ "$got" = "$want" ] || die "variáveis não ficaram como esperado"
