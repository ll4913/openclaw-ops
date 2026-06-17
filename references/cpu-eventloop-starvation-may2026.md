# OpenClaw CPU 100% + Event Loop Starvation — May 2026 Case Study

## Incident Summary

**Date:** 2026-05-28 evening
**Duration:** ~2 hours of investigation and remediation
**Impact:** Main Telegram bot completely unresponsive, all 15 bots affected

## Symptoms

- Gateway CPU at 100-121% sustained
- Liveness warnings: `eventLoopDelayP99Ms=34275.9` (34 seconds!)
- `eventLoopUtilization=1` (fully saturated)
- Telegram bots showing "connected" but not responding
- `fetch timeout reached; aborting operation` on all network calls
- 81-second silent gaps in gateway logs (zero output)

## Four Root Causes Identified

### Root Cause 1: Provider Auth Storm (17 providers → 10)

**Before:** 17 providers configured, including 7 unused ones (mlx-gemma4, mlx-ling, mlx-qwen, mlx-sol, moonshot, openai, xai). Each provider requires synchronous HTTP validation during startup.

**Auth timing:**
- With 17 providers: 98.9 seconds
- With 10 providers: 16.2 seconds (83% reduction)

**Critical discovery:** `openclaw.json` does NOT support `"enabled": false` on providers. Setting it causes startup failure:
```
Gateway failed to start: Invalid config at ~/.openclaw/openclaw.json.
models.providers.xai: Unrecognized key: "enabled"
```

**Fix:** Delete unused providers entirely from `openclaw.json`.

### Root Cause 2: Native Module Duplication (142 → 83 threads)

`clipboard.darwin-universal.node` loaded from TWO paths:
1. `/Users/lianglin/openclaw/node_modules/@mariozechner/clipboard-darwin-universal/` (2.7MB)
2. `/Users/lianglin/.openclaw/npm/node_modules/@mariozechner/clipboard-darwin-universal/` (4.1MB, different version!)

Each load spawns ~10 tokio runtime workers + ~10 V8 WorkerThreads. Total: ~40 extra threads.

**Dependency chain:** `@earendil-works/pi-coding-agent` → `@mariozechner/clipboard` → `@mariozechner/clipboard-darwin-universal`

The second path comes from OpenClaw's plugin npm cache (`~/.openclaw/npm/node_modules/`).

**Fix:** `rm -rf ~/.openclaw/npm/node_modules/@mariozechner/clipboard-darwin-universal/`

**Thread reduction:** 142 → 83 (42% reduction)

### Root Cause 3: Memory Pressure V8 GC Storms

RSS hit 1.6-1.9GB, exceeding the 1.5GB threshold:
```
memory pressure: level=warning reason=rss_threshold
rssBytes=1676197888 heapUsedBytes=534942160 thresholdBytes=1610612736
```

V8 forced into frequent Scavenge GC cycles, each stalling the event loop.

**Fix:** Reduce bootstrap sizes in `openclaw.json`:
```json
{
  "agents": {
    "defaults": {
      "bootstrapMaxChars": 4000,       // was 8000
      "bootstrapTotalMaxChars": 15000   // was 26000
    }
  }
}
```

**Result:** RSS dropped from 1.6GB to 777MB (51% reduction), no more memory pressure warnings.

### Root Cause 4: LCM + Context Engine Synchronous Blocking

81-second silent gaps in logs caused by:
- LCM plugin performing SQLite full-text search and context assembly (58 context items)
- Context Engine building 1M token budget context
- Tool Policy scanning 45+ tools with allow/deny lists

All synchronous on the main thread.

**Fix — Two parts:**

A. LCM database optimization:
```bash
sqlite3 ~/.openclaw/lcm.db "VACUUM;"
sqlite3 ~/.openclaw/lcm.db "ANALYZE;"
```

B. Tighter context pruning:
```json
{
  "contextPruning": {
    "mode": "cache-ttl",
    "ttl": "30m",            // was "1h"
    "keepLastAssistants": 8,  // was 10
    "softTrimRatio": 0.25     // was 0.3
  }
}
```

**Result:** Silent gaps eliminated, event loop P99 stays under 500ms.

## Combined Before/After Metrics

| Metric | Before | After | Improvement |
|--------|--------|-------|-------------|
| Auth pre-warming | 99s | 16s | ↓ 83% |
| Event loop P99 | 34,276ms | 556ms | ↓ 98% |
| Thread count | 142 | 83 | ↓ 42% |
| RSS memory | 1.6GB | 777MB | ↓ 51% |
| CPU (idle) | 100% | 1-5% | ↓ 95% |
| Liveness warnings | Frequent | None | ✅ Eliminated |

## Diagnostic Methodology

### Step 1: macOS `sample` profiling
```bash
sample $(pgrep -f 'openclaw.*gateway') 3 -file /tmp/oc-cpu-sample.txt
```
Revealed: 142 threads, mostly idle WorkerThreads and tokio-runtime-workers from clipboard module.

### Step 2: Timeline gap analysis
Parsed JSON logs to find time gaps between entries, identifying 81-second silent periods.

### Step 3: Memory pressure correlation
Cross-referenced `memory pressure` warnings with GC activity in CPU profiles.

### Step 4: Auth timing isolation
Compared `provider auth state pre-warmed in Xms eventLoopMax=Yms` across multiple restarts.

### Step 5: Native module inventory
```bash
vmmap -w <PID> | grep '\.node$'
```
Found duplicate clipboard module loads from two different paths.

## Disk Cleanup (Side Discovery)

`~/.openclaw/` was 63GB. After cleanup: 14GB (49GB freed):
- pipeline/failed/: 15GB
- agents.bak.20260528/: 15GB
- tmp/mc-release-*: 9.6GB
- media/inbound/ (>3 days): 5.4GB
- browser/: 1.6GB
- sandboxes/: 383MB
- logs + trajectory files: ~120MB

## Key Takeaways

1. **Always check for duplicate native modules** when thread count exceeds 100
2. **Never use `enabled: false` on providers** — delete them instead
3. **Monitor `eventLoopMax` in auth pre-warming logs** — it's the canary for event loop health
4. **LCM database needs periodic VACUUM** — it's SQLite, fragmentation is real
5. **Memory threshold warnings precede GC storms** — act on them proactively
6. **`launchctl stop` doesn't work** on stuck gateways — always `pkill -9`
