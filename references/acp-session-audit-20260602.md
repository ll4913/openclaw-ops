# ACP Session Audit & External Drive Archival (2026-06-02)

## Context

OpenClaw ACP sessions accumulate in `~/.openclaw/workspace/state/sessions/`. As of 2026-06-02, observed 268 sessions totaling 374MB. Codex sessions are the largest (67MB for a single active session).

## Audit Commands

```bash
# Total session count and size
echo "Total: $(ls ~/.openclaw/workspace/state/sessions/*.json 2>/dev/null | wc -l)"
du -sh ~/.openclaw/workspace/state/sessions/

# Breakdown by type
cd ~/.openclaw/workspace/state/sessions/
echo -n "Claude ACP: "; ls agent*claude*acp*.json 2>/dev/null | wc -l
echo -n "Codex ACP: "; ls agent*codex*acp*.json 2>/dev/null | wc -l
echo -n "Cursor ACP: "; ls agent*cursor*acp*.json 2>/dev/null | wc -l

# Oneshot vs persistent (Claude only)
echo -n "Oneshot: "; ls agent*claude*acp*oneshot*.json 2>/dev/null | wc -l
echo -n "Persistent: "; ls agent*claude*acp*.json 2>/dev/null | grep -v oneshot | wc -l

# Age distribution
echo -n "Last 24h: "; find . -name "*acp*.json" -mtime 0 | wc -l
echo -n "1-7 days: "; find . -name "*acp*.json" -mtime +0 -mtime -7 | wc -l
echo -n "7-30 days: "; find . -name "*acp*.json" -mtime +7 -mtime -30 | wc -l
echo -n ">30 days: "; find . -name "*acp*.json" -mtime +30 | wc -l

# Active sessions (last 1 hour)
find . -name "*acp*.json" -mmin -60 | while read f; do
  basename "$f" | python3 -c "import sys,urllib.parse; print('  ' + urllib.parse.unquote(sys.stdin.read().strip().replace('.json','')))"
done

# Largest sessions
ls -lhS *acp*.json 2>/dev/null | head -10
```

## Archival to External Drive

Archive >24h sessions to `/Volumes/Extreme Pro/openclaw-acp-archive/YYYY-MM-DD/`:

```bash
ARCHIVE_DIR="/Volumes/Extreme Pro/openclaw-acp-archive/$(date +%Y-%m-%d)"
mkdir -p "$ARCHIVE_DIR"

# Copy all ACP sessions >24h
find ~/.openclaw/workspace/state/sessions/ -name "*acp*.json" -mtime +0 \
  -exec cp {} "$ARCHIVE_DIR/" \;

echo "Archived $(ls "$ARCHIVE_DIR" | wc -l) sessions"
du -sh "$ARCHIVE_DIR"
```

## Cleanup (Delete Inactive >24h Sessions)

Safety: `-mtime +0` (>24h) and `-mmin -60` (active in last hour) are mutually exclusive, so all >24h sessions are guaranteed inactive.

```bash
find ~/.openclaw/workspace/state/sessions/ -name "*acp*.json" -mtime +0 -delete
```

## Observed Data (2026-06-02 Baseline)

| Type | Count | Notes |
|------|-------|-------|
| Claude ACP | 157 | 89 persistent + 68 oneshot |
| Codex ACP | 77 | All persistent, largest files |
| Cursor ACP | 34 | All persistent |
| Copilot ACP | 0 | Not configured |

- >1MB sessions: 39 files, 338MB (91% of total disk)
- <10KB sessions: 112 files (empty shells / failed sessions)
- Codex top session: 67MB (active ACP session)
- After cleanup (>24h archived+deleted): 268 → 30 sessions, 374MB → 101MB
