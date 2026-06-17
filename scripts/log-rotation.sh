#!/bin/bash
# OpenClaw + Hermes log rotation — run weekly via cron
# Keeps last 2000 lines of each log, removes rotated archives > 7 days

set -euo pipefail

echo "[$(date)] Log rotation starting..."

# OpenClaw logs
for f in ~/.openclaw/logs/*.log; do
  [ -f "$f" ] || continue
  LINES=$(wc -l < "$f" 2>/dev/null || echo 0)
  if [ "$LINES" -gt 5000 ]; then
    tail -2000 "$f" > "${f}.rotated" && mv "${f}.rotated" "$f"
    echo "  Truncated $(basename $f): $LINES → 2000 lines"
  fi
done

# Hermes logs
for f in ~/.hermes/logs/*.log; do
  [ -f "$f" ] || continue
  LINES=$(wc -l < "$f" 2>/dev/null || echo 0)
  if [ "$LINES" -gt 5000 ]; then
    tail -2000 "$f" > "${f}.rotated" && mv "${f}.rotated" "$f"
    echo "  Truncated $(basename $f): $LINES → 2000 lines"
  fi
done

# Clean old rotated logs
find ~/.openclaw/logs/ -name "*.log.*" -mtime +7 -delete 2>/dev/null
find ~/.hermes/logs/ -name "*.log.*" -mtime +7 -delete 2>/dev/null

# Clean cron reports and runs > 14 days
find ~/.openclaw/cron/reports -type f -mtime +14 -delete 2>/dev/null
find ~/.openclaw/cron/runs -type f -mtime +14 -delete 2>/dev/null

# Clean tmp dirs in workspaces > 3 days
find ~/.openclaw/workspace*/tmp -type f -mtime +3 -delete 2>/dev/null
find ~/.openclaw/workspace*/tmp-* -type f -mtime +3 -delete 2>/dev/null

# Clean old Codex ACP sessions > 14 days
find ~/.openclaw/workspace/state/sessions/ -name "*.json" -mtime +14 -delete 2>/dev/null

echo "[$(date)] Done."
