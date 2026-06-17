# SIGTERM Diagnostic Playbook & Zombie Reaper v2

## SIGTERM Storm Root Cause Analysis

When OpenClaw gateway shows frequent SIGTERM entries, follow this diagnostic chain:

### Step 1: Count & Trend
```bash
grep -c "SIGTERM" ~/Library/Logs/openclaw/gateway.log
# Per-day distribution:
grep "SIGTERM" ~/Library/Logs/openclaw/gateway.log | awk -F'T' '{print $1}' | sort | uniq -c | sort -rn
```
Look for convergence (declining counts) vs escalation.

### Step 2: Check LaunchAgent Configuration
```bash
cat ~/Library/LaunchAgents/ai.openclaw.gateway.plist
```
Key fields:
- `KeepAlive: true` — launchd auto-restarts after any exit
- `ExitTimeOut: 20` — if process takes >20s to exit gracefully, launchd sends SIGKILL
- `ThrottleInterval: 10` — minimum seconds between restarts

### Step 3: Identify Restart vs Shutdown
```bash
grep -E "SIGTERM.*(restarting|shutting down)" ~/Library/Logs/openclaw/gateway.log | tail -20
```
- `restarting` = gateway self-restart (config hot-reload or internal)
- `shutting down` = external kill (watchdog, cron, manual)

### Step 4: Config Hot-Reload Storms
```bash
grep -c "config.*change.*reload" ~/Library/Logs/openclaw/gateway.log
```
Each config change triggers full SIGTERM → drain → restart cycle.
**Pitfall:** Frequent config file touches (editor autosave, sync tools) create SIGTERM storms.
**Fix:** Batch config changes; avoid touching config files when not needed.

### Step 5: Memory Pressure Correlation
```bash
grep "memory pressure" ~/Library/Logs/openclaw/gateway.log | tail -10
# Current RSS:
ps aux | grep "openclaw.*gateway" | grep -v grep | awk '{print $6/1024 "MB"}'
```
**Threshold:** 1.5GB RSS triggers `[diagnostics/memory] memory pressure: level=warning`.
**Danger:** RSS spikes to 2.7GB+ can cause launchd ExitTimeOut kill (appears as SIGTERM).
**Action:** If RSS consistently > 1.5GB, investigate heap growth (100MB/hour+ = leak).

### Step 6: Active Task Drain
```bash
grep "draining.*active task" ~/Library/Logs/openclaw/gateway.log | tail -5
```
Shows how many tasks/runs were in flight during each restart. High numbers = risky restarts.

### Step 7: Check External Watchdogs
```bash
# Common external SIGTERM sources:
launchctl list | grep -E "watchdog|restart-monitor|cleanup"
cat ~/Library/LaunchAgents/com.solm.mc-public-watchdog.plist
cat ~/Library/LaunchAgents/com.solm.mc-restart-monitor.plist
```

## Anomaly: AI Text Leaking to Gateway Log

Observed 2026-06-03: LLM-generated literary prose appeared directly in gateway.log stdout.
```
2026-06-03T00:00:47 The SIGTERM arrived at exactly 30 seconds, like a metronome...
```
**Cause:** Agent session output leaked to parent stdout stream (stdout isolation bug).
**Impact:** Cosmetic only, but indicates a process fd inheritance issue.

## Zombie Process Reaper v2 Design

**Script:** `~/.hermes/scripts/zombie-process-reaper.py`
**Cron:** every 30m, `no_agent: true`

### Monitored Processes
| Pattern | Base Max | Dynamic |
|---------|----------|---------|
| `codex app-server` | 10 | + active sessions (CPU>0.5%) |
| `gbrain serve` | 3 | static |
| `solmem-mcp` | 3 | static |

### v2 Improvements over v1
1. **20-min age protection** — parse macOS `etime` format `[[dd-]hh:]mm:ss`, skip young processes
2. **Dynamic threshold** — base + count of actively-serving sessions (CPU>0.5%)
3. **Active session protection** — never kill processes with CPU>0.5% even if over threshold
4. **Graceful kill** — SIGTERM → 5s grace → SIGKILL (was direct SIGKILL)
5. **Desktop isolation** — `/Applications/Codex.app/` and `~/.codex/packages/standalone/` never touched
6. **Self-exclusion** — filter own PID, parent PID, pgrep/python subprocesses

### Kill Logic
Phase 1 (count exceeded, mature only): orphans first → oldest idle → skip active
Phase 2 (global sweep): any mature orphan killed regardless of count
Never kill: young (<20min), Desktop app, active (CPU>0.5%)

### Process Landscape (typical)
7 codex app-server: 5 Desktop (protected), 2 OpenClaw ACP (reapable). 2 < 10 → no action.

### macOS ps Notes
- `etime` format: `[[dd-]hh:]mm:ss` — NOT `etimes` (keyword not available on macOS)
- `ps -p PID -o ppid=,pcpu=,rss=,etime=,command=` — use `split(None, 4)` for command with spaces
- `lstart` gives absolute start time; `etime` gives relative elapsed

## MC Query Timeout Cascade

When MC stderr shows widespread `q* exceeded 20s`:
```
PBI API 429 throttling
  → PBI MCP Server query timeout (20s)
    → MC data queries cascade timeout
      → UI/API pages slow or blank
```
**Check:** `curl -s http://localhost:3100/health` (PBI MCP health endpoint)
**Check:** PBI MCP `LastExitStatus` via `launchctl list com.solm.pbi-mcp-server` (137=OOM/SIGKILL)
**Fix:** Reduce PBI query concurrency or add caching; check PBI API quota/throttling policy.
