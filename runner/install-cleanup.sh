#!/usr/bin/env bash
# Instala o timer diário de limpeza da fleet. Idempotente. Precisa de sudo.
# Uso: install-cleanup.sh
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"

echo "==> instalando units gh-agents-cleanup"
sudo install -m 0644 "$HERE/systemd/gh-agents-cleanup.service" /etc/systemd/system/
sudo install -m 0644 "$HERE/systemd/gh-agents-cleanup.timer" /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now gh-agents-cleanup.timer

echo "==> verificação"
systemctl list-timers gh-agents-cleanup.timer --no-legend
