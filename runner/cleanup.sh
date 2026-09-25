#!/usr/bin/env bash
# Apaga _work de runners cuja unit está inativa há >7 dias. Roda diariamente
# via gh-agents-cleanup.timer (sucessor do factory-disk-cleanup).
set -euo pipefail

# shellcheck disable=SC1091 # lib.sh sits next to this script by convention
source "$(dirname "$0")/lib.sh"

[ -d "$RUNNERS_DIR" ] || exit 0
for dir in "$RUNNERS_DIR"/*/*/; do
  [ -d "$dir/_work" ] || continue
  unit="$(unit_for "${dir%/}")"
  active="unknown"
  [ -n "$unit" ] && active="$(systemctl is-active "$unit" 2>/dev/null || echo inactive)"
  if [ "$active" = "inactive" ] || [ "$active" = "failed" ]; then
    if [ -n "$(find "$dir/_work" -maxdepth 0 -mtime +7 2>/dev/null)" ]; then
      echo "==> removendo $dir/_work (unit ${unit:-desconhecida} $active, >7d)"
      rm -rf "$dir/_work"
    fi
  fi
done
echo "==> cleanup concluído"
