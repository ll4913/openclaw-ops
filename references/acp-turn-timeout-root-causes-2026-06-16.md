# ACP Turn Timeout Root Causes — 2026-06-16

Deep investigation of frequent ACP turn timeouts/transport failures. 5 root causes identified.

## Root Cause #1: Gateway SIGTERM Storms → Orphan Kill Chain (P0)

```
config hot-reload / openclaw CLI commands
  → SIGTERM to gateway (PID changes)
    → wrapper ppid watcher detects orphan (1s poll)
      → SIGTERM to Claude process tree
        → ACP turn mid-flight dies
          → transport error: connection_closed
```

**Evidence:**
- `launchctl print gui/$(id -u)/ai.openclaw.gateway` showed `runs = 7` (gateway restarted 7 times)
- config-audit.jsonl recorded multiple `openclaw config set/patch` operations (2026-06-04 through 2026-06-14)
- Claude wrapper code (`~/.openclaw/acpx/claude-agent-acp-wrapper.mjs`) implements orphan detection: every 1 second checks `process.ppid`, if it becomes 1 (init) → SIGTERM child process tree with 1.5s SIGKILL fallback
- Gateway log showed 16 SIGTERM entries on 2026-05-19 alone, multiple within minutes (03:26→03:32→03:37→03:38 = 4 restarts in 12 minutes)

**Impact:** One config modification → gateway restart → ALL in-flight ACP turns fail simultaneously.

**Diagnosis:**
```bash
launchctl print gui/$(id -u)/ai.openclaw.gateway 2>/dev/null | grep -E 'runs|exit timeout'
grep 'SIGTERM' ~/.openclaw/logs/gateway.log | wc -l
grep 'config.write' ~/.openclaw/logs/config-audit.jsonl | wc -l
```

**Mitigation:**
- Batch config changes instead of individual `openclaw config set` calls
- Avoid config changes during active ACP-bound conversations
- Consider implementing graceful drain in gateway (delay SIGTERM processing until active ACP turns complete)

## Root Cause #2: Claude CLI stdin Idle Timeout (~2h)

ACP Claude sessions die after approximately 2 hours of inactivity.

**Evidence:**
- Memory records "stdin closes ~2h"
- Lease reaper log shows periodic 3-lease reaps every 2-3 hours with "open-but-dead" Claude PIDs
- Pattern from 2026-06-15/16:
  ```
  09:07 reap 3 dead (open-but-dead: claude:8504ad57, claude:94a5654a)
  11:07 reap 1 dead
  11:37 reap 3 dead (open-but-dead: claude:1d784100)
  13:07 reap 3 dead (open-but-dead: claude:107e3b39, claude:2003be2e)
  ...next day...
  09:07+1d reap 10 dead (open-but-dead: claude:f8433bdd, claude:090e3eec, claude:2d55c913)
  ```
- `last_agent_disconnect_reason` in session JSON: 3x `connection_close`, 1x `process_exit`

**Impact:** Every ~2 hours, all idle Claude ACP sessions die. Next turn requires full session rebuild (15-30s), often exceeding short parent-task timeouts.

**Diagnosis:**
```bash
grep 'reaped.*dead\|open-but-dead' ~/.openclaw/logs/acp-lease-reaper.log | tail -20
```

**Potential fix:** Add keepalive ping to ACP wrapper — every 30 minutes send a noop to Claude stdin to prevent idle timeout.

## Root Cause #3: ACP Turn Timeout Too Short

**Evidence:** User-reported (2026-06-16 LCM messages):
> "failed 的原因不是代码失败，是我刚才给 Claude ACP 的等待超时设得太短（20 秒），它还在恢复上下文/查 worktree，父任务就先判 timeout 了"

**Timing breakdown:**
1. Resume session (from stale state rebuild): 5-15 seconds
2. Load context/tools: 3-5 seconds  
3. Execute actual task: 10-300 seconds

A 20-second timeout fails during session rebuild alone.

**Config:** `agents.defaults.timeoutSeconds` is 172800 (48h) — this is fine. The problem is per-task timeout overrides being set too aggressively.

## Root Cause #4: Self-Referencing Compaction Loop (LCM Pollution)

**Evidence:** 78 identical messages in LCM over 40 hours (2026-06-12 10:27 to 2026-06-14 02:39):
```sql
SELECT COUNT(*), substr(content, 1, 80) FROM messages 
WHERE content LIKE '%让我查一下 MC 和 PBI bri%';
-- Result: 78 identical messages across 71 conversations
```

**Mechanism:**
```
signal-detector cron (every 30 min)
  → reads main session history
    → finds unfinished assistant message "让我查一下 MC 和 PBI bri..."
      → stores as scan output in LCM
        → next cron run reads that output → stores again
          → infinite self-referencing loop
```

**Impact:** Not directly ACP timeout, but pollutes LCM (549MB lcm.db), inflates message_parts table (324MB), and creates noise in session history that context-engine tries to maintain.

**Fix:** Filter cron's own output from scan targets. Delete the 78 duplicate messages.

## Root Cause #5: Transport Failure Patterns

12 fatal transport text patterns defined in `src/acp/runtime/transport-failure.ts`:

| Pattern | Meaning | Typical trigger |
|---------|---------|----------------|
| `http/2 keepalive ping timed out` | HTTP/2 heartbeat timeout | Anthropic API connection idle |
| `keepalive ping timed out` | Generic keepalive timeout | Same |
| `rst_stream` | HTTP/2 stream reset | Server-side disconnect |
| `goaway` | HTTP/2 GOAWAY | Server requesting connection close |
| `econnreset` | TCP connection reset | Network layer disconnect |
| `epipe` | Pipe write failure | Claude process already exited |
| `err_stream_premature_close` | Stream closed early | Connection drop |
| `und_err_socket` | Socket error | Network issue |
| `socket hang up` | Socket hang | Long idle without data |
| `premature close` | Connection closed early | Various |
| `connection closed/reset/aborted` | Connection terminated | Peer exit |
| `other side closed` | Peer closed connection | Claude process exit |

## Quick Diagnostic Script

```bash
# ACP health dashboard
echo "=== Gateway restarts ==="
launchctl print gui/$(id -u)/ai.openclaw.gateway 2>/dev/null | grep -E 'runs|exit'

echo "=== Dead lease frequency (last 24h) ==="
grep 'reaped' ~/.openclaw/logs/acp-lease-reaper.log | tail -20

echo "=== Open-but-dead sessions ==="
grep 'open-but-dead' ~/.openclaw/logs/acp-lease-reaper.log | grep -v 'none' | tail -5

echo "=== Stuck compaction loops ==="
sqlite3 ~/.openclaw/lcm.db "SELECT substr(content, 1, 80), COUNT(*) as cnt FROM messages GROUP BY substr(content, 1, 80) HAVING cnt > 10 ORDER BY cnt DESC LIMIT 5;"

echo "=== ACP transport error in recent sessions ==="
find ~/.openclaw/workspace/state/sessions -name "*acp*" -mtime -1 -exec grep -l "transport\|keepalive\|econnreset\|premature" {} \;
```

## Error Code Reference

From `src/acp/runtime/errors.ts`:
- `ACP_BACKEND_MISSING` — Backend not found
- `ACP_BACKEND_UNAVAILABLE` — Backend not available
- `ACP_BACKEND_UNSUPPORTED_CONTROL` — Unsupported control plane
- `ACP_DISPATCH_DISABLED` — ACP dispatch disabled
- `ACP_INVALID_RUNTIME_OPTION` — Invalid runtime option
- `ACP_RUNTIME_TRANSPORT_FAILED` — **Transport failure (most common timeout cause)**
- `ACP_SESSION_INIT_FAILED` — Session initialization failed
- `ACP_TURN_FAILED` — Turn execution failed
