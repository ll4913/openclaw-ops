# Concurrent Embedded Run Event Loop Starvation — May 2026

## Incident Summary

**Version affected**: v2026.5.24
**Version fixed**: v2026.5.27
**Duration**: ~16 minutes of repeated liveness warnings (00:20–00:36 local time)
**Impact**: All Telegram bot API calls timing out, event loop completely saturated

## Timeline

### 00:14 — First fetch timeout
```
fetch timeout reached; aborting operation
timeoutMs: 10000, elapsedMs: 16362, timerDelayMs: 6362
eventLoopDelayHint: "timer delayed 6362ms, likely event-loop starvation"
url: https://api.telegram.org/bot830885.../getMe
```

### 00:20 — Liveness warning with CPU saturation
```
liveness warning: reasons=event_loop_delay,cpu
interval=31s
eventLoopDelayP99Ms=9143.6
eventLoopDelayMaxMs=19193.1
eventLoopUtilization=0.915
cpuCoreRatio=0.942
work=[active=agent:main:telegram:direct:8524721791(processing/tool_call,q=0,age=9s)]
```

### 00:30 — Full saturation with concurrent embedded runs
```
liveness warning: reasons=event_loop_delay,event_loop_utilization,cpu
interval=38s
eventLoopDelayP99Ms=22112.4
eventLoopDelayMaxMs=22112.4
eventLoopUtilization=1
cpuCoreRatio=1.021
work=[active=agent:main:telegram:direct:8524721791(processing/embedded_run,q=0,
       last=codex_app_server:notification:item/agentMessage/delta)
      |agent:engineer:telegram:direct:8524721791(processing/embedded_run,q=1,age=48s)]
```

Key observation: Two agents (`main` + `engineer`) both in `processing/embedded_run` state simultaneously.

### 00:37 — Post-update restart (v2026.5.27)
```
provider auth state pre-warmed in 15580ms eventLoopMax=193.9ms
```
Event loop max delay drops from 22,112ms to 193.9ms — problem resolved.

## Root Cause

The Codex app server streaming notifications (`item/agentMessage/delta`, `item/commandExecution/outputDelta`) were processed synchronously on the main thread. When two agents ran `embedded_run` concurrently on the same chat, the combined streaming load saturated the event loop:

1. Agent `main` processing `agentMessage/delta` notifications
2. Agent `engineer` processing `embedded_run` with 48s age (stuck waiting for event loop time)
3. All network I/O (including Telegram API calls) starved of CPU time
4. Fetch timers delayed by 6-22 seconds beyond their intended 10s timeout

## Metrics Comparison

| Metric | Before (v2026.5.24) | After (v2026.5.27) |
|--------|---------------------|---------------------|
| eventLoopDelayP99Ms | 22,112ms | <500ms |
| eventLoopUtilization | 1.0 | <0.5 |
| cpuCoreRatio | 1.021 | <0.1 |
| auth preheat eventLoopMax | 22,112ms | 193.9ms |
| fetch timeouts | 6+ per 15 min | 0 |

## Diagnostic Commands That Worked

```bash
# Find the smoking gun — concurrent embedded runs
grep "liveness warning" /tmp/openclaw/openclaw-*.log | grep "embedded_run"

# Check event loop delay trend
grep "eventLoopDelayP99" /tmp/openclaw/openclaw-*.log | tail -10

# Verify fix after update
grep "provider auth state pre-warmed" /tmp/openclaw/openclaw-$(date +%Y-%m-%d).log | tail -1
# Should show eventLoopMax < 500ms
```

## Key Takeaway

When liveness warnings show `eventLoopUtilization=1` AND the work queue contains multiple `embedded_run` entries, the event loop is being saturated by concurrent streaming operations. This is a platform bug, not a configuration issue — update to the latest version.
