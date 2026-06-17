#!/bin/bash
# Archive OpenClaw session files older than 7 days
# Structure: ~/.openclaw/archive/sessions/YYYY-MM/<agent_name>/*.jsonl
# Only archives, never deletes. Archives preserved for audit/recovery.

set -euo pipefail

ARCHIVE_BASE="$HOME/.openclaw/archive/sessions"
AGENTS_DIR="$HOME/.openclaw/agents"
THRESHOLD=7  # days

echo "[$(date)] Session archive starting (threshold: ${THRESHOLD}d)"

BEFORE_FILES=$(find "$AGENTS_DIR" -name "*.jsonl" 2>/dev/null | wc -l | tr -d ' ')
BEFORE_SIZE=$(du -sh "$AGENTS_DIR" 2>/dev/null | cut -f1)

ARCHIVED=0
for f in $(find "$AGENTS_DIR" -name "*.jsonl" -mtime +${THRESHOLD} 2>/dev/null); do
  AGENT=$(basename "$(dirname "$f")")
  # macOS stat format
  MONTH=$(stat -f "%Sm" -t "%Y-%m" "$f" 2>/dev/null || date -r "$f" "+%Y-%m")
  TARGET="$ARCHIVE_BASE/$MONTH/$AGENT"
  mkdir -p "$TARGET"
  mv "$f" "$TARGET/"
  ARCHIVED=$((ARCHIVED + 1))
done

AFTER_FILES=$(find "$AGENTS_DIR" -name "*.jsonl" 2>/dev/null | wc -l | tr -d ' ')
AFTER_SIZE=$(du -sh "$AGENTS_DIR" 2>/dev/null | cut -f1)

echo "Archived: $ARCHIVED files"
echo "Active sessions: $BEFORE_FILES ($BEFORE_SIZE) → $AFTER_FILES ($AFTER_SIZE)"
echo "[$(date)] Done"
