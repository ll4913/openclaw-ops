# OpenClaw Hooks Debugging Playbook

Absorbed from `openclaw-hooks-debugging` (consolidated 2026-05-29).

## Quick Symptom → Action

```
1. Hooks backing up, CPU high?
   → openclaw hooks list        # Status: ready/disabled
   → tail -30 ~/.openclaw/logs/hook-reaper.log
   → Count PID ages: if many >600s, hooks stalled

2. Specific hook failing?
   → tail -100 ~/.openclaw/logs/gbrain-ingest.log
   → Search for error=ENOENT, error=timeout, error=invalid

3. File ENOENT errors but files exist?
   → Async race condition (hook fires before file write completes)
   → Check handler for resolveExistingSource() fallback logic

4. DECISION: Can you quickly fix the handler code?
   → YES: Patch handler.js, restart gateway
   → NO: Disable hook, stabilize system, defer fix
```

## Phase 1: Confirm Hook Queue Status

```bash
cd ~/.openclaw && openclaw hooks list
tail -50 ~/.openclaw/logs/hook-reaper.log
grep 'kill PID=' ~/.openclaw/logs/hook-reaper.log | wc -l
ps aux | grep -E 'hook|gbrain|ingest' | grep -v grep
```

Red flag: Many PIDs with `etime > 10:00` → hook handler did not exit cleanly.

## Phase 2: Diagnose Failing Hook

```bash
openclaw hooks info gbrain-auto-ingest
cat ~/.openclaw/hooks/gbrain-auto-ingest/handler.js | head -50
tail -100 ~/.openclaw/logs/gbrain-ingest.log | grep -E '^(2026|ok|fail|skip)'
```

### Error Distribution
```bash
grep 'error=' ~/.openclaw/logs/gbrain-ingest.log | sed 's/.*error=//' | sed 's/ .*//' | sort | uniq -c
```

## Common Pitfalls

### A: File format mismatch (ENOENT)
Handler expects `.jsonl` but OpenClaw writes `.trajectory.jsonl`. Fix: handler must try multiple formats (`.jsonl`, `.trajectory.jsonl`, `.trajectory-path.json`, `.reset.*`).

### B: Gbrain command failure
File found but `gbrain ingest` fails. Check permissions, increase `timeoutMs` in hook config:
```bash
openclaw config set hooks.internal.entries.gbrain-auto-ingest.timeoutMs 60000
```

### C: Hook hangs (doesn't exit)
Handler completes but process never reaped. Fix: add explicit timeout and `process.exit()` to handler.

## Phase 3: Emergency Disable

```bash
openclaw hooks disable gbrain-auto-ingest
pkill -9 -f 'openclaw-hook-server'
pkill -9 -f 'gbrain.*ingest'
tail -f ~/.openclaw/logs/hook-reaper.log  # Should stop after ~30s
```

### Re-enable after fix:
```bash
openclaw hooks enable gbrain-auto-ingest
launchctl kickstart -k gui/$(id -u)/ai.openclaw.gateway
```

## Handler Code Review Checklist

- [ ] Event validation: Filters for correct events?
- [ ] File resolution: Tries multiple formats before failing?
- [ ] Error handling: Catches and logs errors properly?
- [ ] Timeout: Has timeout to prevent hanging?
- [ ] Process cleanup: Exits cleanly?
- [ ] Logging: Logs with context (sessionId, file, stage)?
- [ ] Fallback chain: Gracefully skips on failure?
- [ ] Race conditions: Handles concurrent file writes?

## Verification After Fix

- [ ] `openclaw hooks list` shows correct status
- [ ] No hanging processes (`ps aux | grep hook` empty)
- [ ] Reaper cleaning up (no more kill lines)
- [ ] CPU/memory normal
- [ ] `openclaw health --timeout 10000` passes
- [ ] No error spam in gateway logs
