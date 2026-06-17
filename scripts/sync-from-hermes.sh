#!/usr/bin/env bash
# Sync deep-maintenance references and Hermes scripts into openclaw-ops (runtime copy).
set -euo pipefail

HERMES="${HERMES_SKILLS:-$HOME/.hermes/skills/devops/openclaw-system-maintenance}"
OPS_DIR="$(cd "$(dirname "$0")/.." && pwd)"

if [[ ! -d "$HERMES" ]]; then
  echo "ERROR: Hermes skill not found at $HERMES" >&2
  echo "Set HERMES_SKILLS to override." >&2
  exit 1
fi

mkdir -p "$OPS_DIR/references" "$OPS_DIR/references/scripts" "$OPS_DIR/scripts"

echo "Sync references from $HERMES/references/"
rsync -a --delete \
  --exclude 'provider-three-layer-cleanup.md' \
  "$HERMES/references/" "$OPS_DIR/references/"

HERMES_SCRIPTS=(
  acp_reaper.py
  zombie-process-reaper.py
  openclaw-diag.sh
  oc-auth-profile-cleanup.sh
  oc-session-archive.sh
  log-rotation.sh
)

for f in "${HERMES_SCRIPTS[@]}"; do
  if [[ -f "$HERMES/scripts/$f" ]]; then
    cp "$HERMES/scripts/$f" "$OPS_DIR/scripts/$f"
    chmod +x "$OPS_DIR/scripts/$f" 2>/dev/null || true
    echo "  copied scripts/$f"
  fi
done

if [[ -d "$HERMES/references/scripts" ]]; then
  rsync -a "$HERMES/references/scripts/" "$OPS_DIR/references/scripts/"
  echo "  synced references/scripts/"
fi

echo "Done. Canonical ops repo: $OPS_DIR"
