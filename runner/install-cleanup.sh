#!/usr/bin/env bash
# Instala o timer diário de limpeza da fleet como user service. Idempotente.
# Uso: install-cleanup.sh   (rode como o usuário da fleet; exige linger ativo)
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
# shellcheck disable=SC1091 # lib.sh sits next to this script by convention
source "$HERE/lib.sh"

echo "==> instalando units gh-agents-cleanup em $UNIT_DIR"
mkdir -p "$UNIT_DIR"
install -m 0644 "$HERE/systemd/gh-agents-cleanup.service" "$UNIT_DIR/"
install -m 0644 "$HERE/systemd/gh-agents-cleanup.timer" "$UNIT_DIR/"
systemctl --user daemon-reload
systemctl --user enable --now gh-agents-cleanup.timer

echo "==> verificação"
systemctl --user list-timers gh-agents-cleanup.timer --no-legend
