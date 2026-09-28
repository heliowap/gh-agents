#!/usr/bin/env bash
# Prepara o usuário dos runners de CI (padrão gh-ci), separado do gh-agents:
# Docker rootless próprio e nenhum acesso ao home do gh-agents (credenciais dos
# runners da fleet, login ChatGPT). CI roda código de PR direto no host; no
# grupo `docker` isso valeria root, então este usuário nunca entra nele.
# Idempotente; termina provando o isolamento. Roda como root.
# Uso: sudo runner/setup-ci-user.sh [usuário=gh-ci]
set -euo pipefail

die() { echo "erro: $*" >&2; exit 1; }
[ "$(id -u)" -eq 0 ] || { echo "uso: sudo $0 [usuário=gh-ci]" >&2; exit 1; }
U="${1:-gh-ci}"
[ "$U" != gh-agents ] || die "o usuário de CI não pode ser o gh-agents"

echo "==> pacotes: uidmap, slirp4netns, dbus-user-session, gh"
missing=()
for p in uidmap slirp4netns dbus-user-session; do
  dpkg -s "$p" >/dev/null 2>&1 || missing+=("$p")
done
if ! [ -x /usr/bin/gh ]; then
  curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
    -o /usr/share/keyrings/githubcli-archive-keyring.gpg
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
    > /etc/apt/sources.list.d/github-cli.list
  missing+=(gh)
fi
if [ ${#missing[@]} -gt 0 ]; then
  apt-get update -qq && apt-get install -y -qq "${missing[@]}"
fi
command -v dockerd-rootless-setuptool.sh >/dev/null \
  || die "dockerd-rootless-setuptool.sh ausente — instale docker-ce-rootless-extras"

echo "==> usuário $U"
id "$U" >/dev/null 2>&1 || useradd -m -s /bin/bash "$U"
chmod 750 "/home/$U"
# useradd costuma alocar; se não alocou, a próxima faixa livre de 65536
for f in /etc/subuid /etc/subgid; do
  grep -q "^$U:" "$f" && continue
  start="$(awk -F: '{e=$2+$3; if (e>m) m=e} END {print (m>100000 ? m : 100000)}' "$f")"
  flag=--add-subuids; [ "$f" = /etc/subgid ] && flag=--add-subgids
  usermod "$flag" "${start}-$((start + 65535))" "$U"
done
# grupo docker = root no host; o CI usa o Docker rootless do próprio usuário
if id -nG "$U" | tr ' ' '\n' | grep -qx docker; then gpasswd -d "$U" docker; fi

echo "==> AppArmor: rootlesskit precisa de userns (Ubuntu 24.04 restringe)"
if [ "$(sysctl -n kernel.apparmor_restrict_unprivileged_userns 2>/dev/null || echo 0)" = 1 ] \
   && ! grep -rqs '"*/usr/bin/rootlesskit"*' /etc/apparmor.d/; then
  cat > /etc/apparmor.d/usr.bin.rootlesskit <<'EOF'
abi <abi/4.0>,
include <tunables/global>

"/usr/bin/rootlesskit" flags=(unconfined) {
  userns,

  include if exists <local/usr.bin.rootlesskit>
}
EOF
  systemctl reload apparmor
fi

echo "==> linger e sessão systemd de $U"
loginctl enable-linger "$U"
uid="$(id -u "$U")"
for _ in $(seq 1 30); do [ -S "/run/user/$uid/bus" ] && break; sleep 1; done
[ -S "/run/user/$uid/bus" ] || die "systemd --user de $U não subiu (/run/user/$uid/bus)"
as_user() { sudo -iu "$U" env XDG_RUNTIME_DIR="/run/user/$uid" "$@"; }

echo "==> Docker rootless de $U"
if ! as_user systemctl --user is-active --quiet docker; then
  as_user dockerd-rootless-setuptool.sh install
fi
as_user systemctl --user enable --now docker >/dev/null

echo "==> checkout do gh-agents em /home/$U/gh-agents"
if [ -d "/home/$U/gh-agents/.git" ]; then
  as_user git -C "/home/$U/gh-agents" pull -q --ff-only
else
  as_user git clone -q https://github.com/heliowap/gh-agents "/home/$U/gh-agents"
fi

echo "==> verificação"
docker_host="unix:///run/user/$uid/docker.sock"
as_user env DOCKER_HOST="$docker_host" docker info --format '{{.SecurityOptions}}' \
  | grep -q rootless || die "o Docker de $U não é rootless"
echo "docker de $U: rootless ($docker_host)"
for secret in /home/gh-agents/.local/share/opencode/auth.json /home/gh-agents/runners; do
  if sudo -u "$U" test -r "$secret"; then die "$U lê $secret — isolamento quebrado"; fi
done
echo "$U não lê o home do gh-agents (login ChatGPT, credenciais dos runners)"
echo "próximo passo (runners de CI, rótulo 'ci'):"
echo "  sudo -iu $U env RUNNER_ROLE=ci DOCKER_HOST=$docker_host GH_TOKEN=\"\$(gh auth token)\" bash -lc '~/gh-agents/runner/enable-repo.sh <owner>/<repo> [N]'"
