# Operational Maintenance Improvements (2026-06-12 Evening)

## Log Rotation Automation

**Problem**: `mc-git-guard.log` grew to 3.9GB, `solmem-auto-commit.log` 44MB, `cleanup-mcp-zombies.log` 37MB — no rotation was in place.

**Solution**: `~/.openclaw/scripts/rotate-logs.sh` + `com.solm.rotate-logs` launchd (daily 03:00)

Script rotates any `.log`/`.jsonl` in `~/.openclaw/logs/` and `/tmp/openclaw/`:
- Keeps last 5MB of each log
- Archives older portion as `.gz`
- Auto-deletes archives older than 30 days

**Results after first run**:
- `mc-git-guard.log`: 3.9 GB → 10 MB
- `openclaw-2026-06-11.log`: 19 MB → 5 MB  
- `openclaw-2026-06-12.log`: 21 MB → 5 MB
- Total `~/.openclaw/logs/`: ~4 GB → 37 MB

## Proxy Bypass Persistence

**Problem**: `networksetup -setproxybypassdomains` may reset on network changes or Codex Desktop updates.

**Solution**: `~/.openclaw/scripts/ensure-proxy-bypass.sh` + `com.solm.ensure-proxy-bypass` launchd
- Runs at boot (`RunAtLoad: true`) + every hour (`StartInterval: 3600`)
- Checks all 10 required Microsoft domains
- Adds any missing ones
- Silent when all domains present

## Session Index Orphan Cleanup

**Command**: `openclaw sessions cleanup --all-agents --enforce --fix-missing`

**What it does**: Removes entries from `sessions.json` that point to `.jsonl` files that no longer exist (e.g., after archive script deleted them).

**2026-06-12 results**: 63 orphan refs cleaned across 15 agents. Eliminated persistent ENOENT errors from gateway logs.

**Pitfall**: Without `--fix-missing`, cleanup only removes unreferenced artifacts and old sessions. Orphan index entries (where the file is gone but the index still points to it) require this flag.

## /tmp Worktree Cleanup

**Scale found**: 165 old `/tmp/mc-*` worktrees + 12 old `/private/tmp/openclaw-*` worktrees.

Cleanup pattern:
```bash
# Remove worktrees older than today
for d in /tmp/mc-*; do
  [ -d "$d" ] || continue
  mdate=$(stat -f "%Sm" -t "%Y-%m-%d" "$d")
  [ "$mdate" != "$(date +%Y-%m-%d)" ] && rm -rf "$d"
done
```

**Note**: Many `/tmp/mc-default-checkout-pollution-protect-*` dirs accumulate — these are 0-byte protection markers from the checkout guard hooks. Safe to delete.

## Codex Sessions: Cannot Archive Active Files

**Finding**: The 783MB May 19 Codex session was actively being written to by Codex process (PID 41839). `lsof +D ~/.codex/sessions/` showed it open for writing. The archive script's mtime check sees "modified today" because Codex keeps appending.

**Rule**: Don't try to archive sessions that `lsof` shows as actively open. Check with:
```bash
lsof +D ~/.codex/sessions/ | grep -c "\.jsonl"
```

## Session Count vs Performance

**Question**: Does 5000 session files slow down agents?

**Answer**: No. OpenClaw uses lazy loading — only reads the specific session's `.jsonl` when that session is activated. The `sessions.json` index contains only metadata (key, timestamp, token count), not full transcripts. Query performance: ~1.1s for 57 main-agent sessions.

**The real performance risk** is individual session file size (>10MB), not count. The gateway loads the full `.jsonl` into memory when resuming a session.

## Disk Usage After Full Maintenance (2026-06-12)

| Component | Before | After | Saved |
|-----------|--------|-------|-------|
| Session archive → external drive | 12,194 files local | 3,756 files | 2.5 GB |
| /tmp worktrees | ~180 dirs | 40 dirs | ~7.2 GB |
| ~/.openclaw/logs/ | 4 GB | 37 MB | ~4 GB |
| ~/.openclaw/tmp/ | 4 GB | 3.4 GB | ~600 MB |
| Unreferenced artifacts | - | - | 40 MB |
| **Total** | | | **~14.3 GB** |
