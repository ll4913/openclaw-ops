# Gateway Runtime Diagnostics

Absorbed from `openclaw-gateway-ops` (consolidated 2026-05-29).

## Performance Monitoring Thresholds

| Metric | Normal | Warning | Critical |
|--------|--------|---------|----------|
| Auth Pre-warming Time | 10-20s | 30-60s | >60s |
| Event Loop Delay (P99) | <500ms | 1-5s | >10s |
| Thread Count | 80-90 | 100-120 | >120 |
| CPU Usage (idle) | 1-5% | 10-30% | >50% |

## Systematic Troubleshooting Workflow

### Step 1: Gather Baseline
```bash
ps aux | grep openclaw
tail -200 /tmp/openclaw/openclaw-*.log > /tmp/oc-recent.log
openclaw gateway status --deep
```

### Step 2: Identify Pattern
1. Auth storm (slow startup, high CPU)
2. Thread explosion (high thread count)
3. Session locks (startup failures)
4. Memory pressure (V8 GC storms)
5. Event loop starvation (concurrent runs or LCM blocking)

### Step 3: Apply Targeted Fix
See main SKILL.md phases for specific fixes.

### Step 4: Verify Improvement
```bash
grep "provider auth state pre-warmed" /tmp/openclaw/openclaw-*.log | tail -1
ps -M <PID> | wc -l
ps -p <PID> -o %cpu,%mem,etime
top -l 60 -s 5 -stats pid,cpu | grep <PID>
```

### Step 5: Document Results
Record before/after metrics.

## Advanced Diagnostics

### CPU Profiling
```bash
sample <PID> 10 -file /tmp/oc-cpu-sample.txt
grep "^\s*[0-9]" /tmp/oc-cpu-sample.txt | sort -t' ' -k1 -rn | head -20
```

### Memory Analysis
```bash
ps -p <PID> -o rss,vsz,etime
grep "memory pressure" /tmp/openclaw/openclaw-*.log
```

### Network / Provider Connectivity
```bash
curl -w "%{http_code} %{time_total}s\n" https://api.anthropic.com/v1/models
curl -w "%{http_code} %{time_total}s\n" https://api.openai.com/v1/models
```

### Native Module Duplication Detection
```bash
find ~/openclaw ~/.openclaw -name "*.node" -type f | sort
vmmap -w <PID> | grep "\.node$" | awk '{print $NF}' | sort | uniq -c
npm ls @mariozechner/clipboard-darwin-universal
```

## Concurrent Embedded Run Event Loop Starvation

**Symptoms:**
- `liveness warning: reasons=event_loop_delay,event_loop_utilization,cpu`
- `eventLoopDelayP99Ms=22112.4` (22+ seconds)
- Multiple `fetch timeout reached` with `eventLoopDelayHint`
- Telegram API calls timing out

**Root Cause:** Two agents running `embedded_run` concurrently saturate the event loop. Codex streaming notifications processed synchronously.

**Fix:** Update to v2026.5.27+ (concurrent embedded_run scheduling bug fixed).

## LCM + Context Engine Synchronous Blocking

**Symptoms:**
- 30-80 second gaps in gateway logs
- `lcm assemble` operations taking >5s

**Gap Detection Script:**
```bash
cat /tmp/openclaw/openclaw-*.log | python3 -c "
import sys, json
prev_ts = None
for line in sys.stdin:
    try:
        d = json.loads(line.strip())
        ts = d.get('time','')
        if prev_ts and ts[11:19] > prev_ts:
            h1,m1,s1 = prev_ts.split(':')
            h2,m2,s2 = ts[11:19].split(':')
            dt = (int(h2)*3600+int(m2)*60+float(s2)) - (int(h1)*3600+int(m1)*60+float(s1))
            if dt > 5: print(f'  GAP: {dt:.0f}s at {ts[11:19]}')
        prev_ts = ts[11:19]
    except: pass
"
```

## ERR_MODULE_NOT_FOUND During Rolling Restart

After `pnpm build`, dist/ gets new chunk hashes. Running gateway references old filenames. During restart transition: transient `ERR_MODULE_NOT_FOUND` errors. **Harmless** — self-resolves after full restart.

## Provider Categories

**Cloud APIs (need API keys):** Anthropic, OpenAI, OpenRouter, DashScope, DeepSeek, Gemini, xAI
**Local Models (no key needed):** Ollama, MLX variants, Custom endpoints
**Specialized:** Moonshot (Kimi), Z.AI (GLM)

## Session Logs Location

- Main logs: `/tmp/openclaw/openclaw-YYYY-MM-DD.log`
- Stability reports: `~/.openclaw/logs/stability/`
- Session data: `~/.openclaw/agents/*/sessions/`
- Config: `~/.openclaw/openclaw.json`
