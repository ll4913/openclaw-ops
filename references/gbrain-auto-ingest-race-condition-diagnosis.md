# GBrain Auto-Ingest Race Condition Diagnosis

## Case Study: 2026-05-16 to 2026-05-27 Hook Queue Starvation

### Symptoms
- gbrain-ingest.log showed 50+ `fail action=... error=ENOENT` entries from 2026-05-16 onwards
- Hook reaper showed many PID kills with `etime=05:00–10:00` (processes lived 5–10 minutes)
- System CPU high, hooks queuing indefinitely

### False Lead: File Format Mismatch

**Initial hypothesis**: Handler expects `.jsonl` but OpenClaw now writes `.trajectory.jsonl`.

**Evidence**:
```
Failed to find: /opsbot/sessions/16456050-d9cf-4e78-a868-1cce93d6160b.jsonl
But file exists: /opsbot/sessions/16456050-d9cf-4e78-a868-1cce93d6160b.trajectory.jsonl ✓
```

**Status**: PARTIALLY CORRECT but misleading. Files existed, but handler logic appeared sound.

### Actual Root Cause: Race Condition + Handler Resilience

#### The Competitive Condition

1. **Session `/new` event fires** (timestamp T0)
2. **Hook handler is invoked immediately** (async, non-blocking)
3. **Handler calls `fs.stat(sessionFile)`** (T0 + ~5–50ms)
4. **At T0, the `.jsonl` file is still being written** (async write in progress)
5. **fs.stat() returns ENOENT** (file not created yet)
6. **Error logged as "fail"** (line 192 in handler.js)
7. **~500–1000ms later**, the file write completes → file now exists on disk

#### Why Handler Didn't Fail Completely

The handler includes `resolveExistingSource()` with fallback logic:

```javascript
async function resolveExistingSource(sessionFile) {
  // 1. Try primary .jsonl
  if (await pathExists(sessionFile)) {
    return { path: sessionFile, kind: "primary" };
  }
  
  // 2. Fallback: Try .trajectory.jsonl
  const trajectoryFile = `${base}.trajectory.jsonl`;
  if (await pathExists(trajectoryFile)) {
    return { path: trajectoryFile, kind: "trajectory" };  // ✅ FOUND HERE
  }
  
  // 3. Fallback: Try pointer file
  // 4. Fallback: Try reset archives
  // → Returns null if all fail
}
```

**So why the "fail" log?**

The "fail" log from line 192 occurs in the **resolve stage error handler**:

```javascript
try {
  source = await resolveExistingSource(sessionFile);  // Can throw
} catch (error) {
  await appendLog(logPath, `fail ... stage=resolve error=${error.message}`);
  return;  // Exits early
}
```

**Critical distinction**: Early catch/throw in the `try` block doesn't mean the entire handler failed. Later log entries may show "ok" for the same session if a retry occurred or if the later session's file was ready.

### Verification

**Test Case**: Session ID `16456050-d9cf-4e78-a868-1cce93d6160b`

```bash
# What gbrain-ingest.log says
$ grep "16456050" ~/.openclaw/logs/gbrain-ingest.log | head -1
2026-05-16T18:58:15.264Z fail action=new session=agent:opsbot:... error=ENOENT

# What actually exists on disk
$ ls -la ~/.openclaw/agents/opsbot/sessions/ | grep 16456050
16456050-d9cf-4e78-a868-1cce93d6160b.trajectory-path.json  (251B)
16456050-d9cf-4e78-a868-1cce93d6160b.trajectory.jsonl      (821K)

# Time gap (8.5 hours between error and file creation)
$ stat ~/.openclaw/agents/opsbot/sessions/16456050*.trajectory.jsonl | grep Modify
Modify: 2026-05-17 02:27:54

# Did the handler eventually succeed for this session?
$ grep "16456050.*ok" ~/.openclaw/logs/gbrain-ingest.log
(No match - once failed, was never retried)
```

### Why Logs Show "ENOENT" but Code Looks Correct

1. **Early error capture**: The `fail` log at line 192 fires if `resolveExistingSource()` **throws**
2. **resolveExistingSource() doesn't throw**: It returns `null` if no file found
3. **So when does line 192 fire?** If `fs.stat()` inside `resolveExistingSource()` throws something OTHER than ENOENT (e.g., permission error, I/O error)
4. **Interpretation**: The "ENOENT" in logs might be a **misleading legacy label** or **caught inside `resolveExistingSource()` but misreported**

The handler.js code at lines 54–64:

```javascript
async function pathExists(filePath) {
  try {
    await fs.stat(filePath);
    return true;
  } catch (err) {
    if (err?.code === "ENOENT") {
      return false;  // Suppress ENOENT, return false (not throw)
    }
    throw err;  // Re-throw OTHER errors (permission, I/O, etc.)
  }
}
```

**If `fs.stat()` throws non-ENOENT** (e.g., permission denied), then `pathExists()` throws, then `resolveExistingSource()` throws, then the handler catches it at line 192 and logs "fail".

### Why Hooks Still Queued Despite "Resilient" Code

Three possible reasons:

1. **Subsequent session events continued firing** faster than reaper could clean up old processes
2. **Some sessions had NO file in ANY fallback format** (truly missing) → legitimate skip, but handler didn't exit cleanly
3. **Gbrain `ingest` or `put` commands were failing** even after file was found (permissions, DB lock, timeout)

### Diagnostic Pattern for Future Race Conditions

**When you see "ENOENT" failures in a handler log:**

1. **Check timestamps**: Is time gap between error and file creation minutes (race condition) or hours (file truly missing)?
2. **Verify fallback chain**: Does the handler try multiple file formats?
3. **Correlate with outcomes**: Look for both "fail" AND "ok" entries for the same sessionId in the log. If both exist, the "fail" was a transient error.
4. **Check if files exist now**: Do the files exist on disk TODAY?
   ```bash
   SESSION_ID="16456050-d9cf-4e78-a868-1cce93d6160b"
   find ~/.openclaw/agents -name "*${SESSION_ID}*" | wc -l
   # If > 0, files exist; "fail" was likely transient race condition
   ```

### Remediation (Applied 2026-05-28)

**Immediate**: Disabled `gbrain-auto-ingest` hook to stop queue from growing

```bash
openclaw hooks disable gbrain-auto-ingest
```

**Short-term monitoring**: Allowed reaper to drain stalled processes over 24–48 hours

**Long-term fix** (deferred): Either:
1. Add explicit retry logic in handler (wait + retry on ENOENT)
2. Or batch ingest events to reduce concurrency and let file writes complete before hook fires
3. Or add async file write awareness (hook waits for `sessionFile` to be marked "ready" before triggering)

### Key Takeaways

| Finding | Implication |  
|---------|-------------|  
| Handler has correct fallback logic | Code is not buggy; resilience is there |  
| "Fail" logs don't always mean handler failed | Check for later "ok" entries or verify file existence |  
| Competitive race on async file I/O | Very common in event-driven systems |  
| ~8-hour gap between error and file | NOT a race condition (file was legitimately missing at event time) |  
| Reaper cleaned up stalled processes | System stabilized once hook was disabled |  

### References

- `handler.js` lines 54–64: `pathExists()` function (ENOENT suppression)
- `handler.js` lines 66–110: `resolveExistingSource()` fallback chain
- `handler.js` lines 189–205: File resolution and error handling
- GBrain ingest log: `~/.openclaw/logs/gbrain-ingest.log` (106 lines in this incident)
- Hook reaper log: `~/.openclaw/logs/hook-reaper.log` (38+ kill lines)
