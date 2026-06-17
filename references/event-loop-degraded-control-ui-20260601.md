# Gateway Event Loop Degraded — Control UI Assets Case (2026-06-01)

## Symptom

`openclaw status` reports:
```
Gateway event loop degraded: reasons=event_loop_delay,event_loop_utilization,cpu eventLoopDelayMaxMs=33236 eventLoopUtilization=0.974 cpuCoreRatio=0.995
```

Gateway process at 100%+ CPU, Telegram bots unresponsive.

## Deep Root Cause Chain

### 1. Why `dist/control-ui/` is missing: tsdown build race

`scripts/tsdown-build.mjs` recursively deletes the ENTIRE `dist/` directory on every `pnpm build`:

```javascript
// scripts/tsdown-build.mjs line 32:
const TSDOWN_OUTPUT_ROOTS = ["dist", "dist-runtime"];

// line 70:
fsImpl.rmSync(rootPath, { force: true, recursive: true });
```

Build order in `scripts/build-all.mjs`:
```
Step 1:  plugins:assets:build
Step 2:  tsdown          ← DELETES dist/ recursively, rebuilds TypeScript
Step 3:  check-cli-bootstrap-imports
  ...
Step 14: ui:build        ← Builds Control UI to dist/control-ui/ (LAST)
```

**If build is interrupted after tsdown but before ui:build** (process killed, timeout, CPU contention, gateway restart):
- `.buildstamp` exists (written by step 5)
- `dist/control-ui/` does NOT exist (step 14 never ran)
- `dist/telegram-ingress-worker.runtime.js` and `dist/proxy-fetch-*.js` also missing during race

### 2. The auto-build trigger

`src/infra/control-ui-assets.ts` → `ensureControlUiAssetsBuilt()`:
- Detects `dist/control-ui/index.html` missing
- Spawns `node scripts/ui.js build` (Vite + Rollup) with 10-minute timeout
- Build is CPU-intensive, runs in Gateway process

`src/gateway/server-control-ui-root.ts` → `resolveGatewayControlUiRootState()`:
- Calls `resolveControlUiRootSync()` first
- If null, calls `ensureControlUiAssetsBuilt()` → triggers auto-build
- Auto-build saturates event loop

### 3. The degradation loop

```
pnpm build starts → tsdown deletes dist/ → gateway reads missing modules
→ Telegram polling fails (Cannot find module telegram-ingress-worker.runtime.js)
→ Gateway may crash/restart → KeepAlive restarts
→ New gateway detects dist/control-ui/ missing → triggers vite build
→ CPU spikes to 147% → event loop delay 33s → degraded warning
→ If another pnpm build starts → cycle repeats
```

Evidence from 2026-06-01 logs:
```
12:02:59 Cannot find module dist/telegram-ingress-worker.runtime.js
12:03:00 Cannot find module dist/proxy-fetch-Bj5aUO3d.js
12:00:00 [gateway] Control UI assets missing; building (ui:build)...
```

### 4. Why `ui/node_modules/` is sparse

`ui/node_modules/` only contains `marked` (hoisted from pnpm workspace). Vite and dompurify exist in root `node_modules/` via hoisting. The auto-build runs `pnpm install` first (`scripts/ui.js` checks `depsInstalled()`), which may stall if pnpm is slow.

## Monitoring Thresholds

From `src/gateway/server/event-loop-health.ts`:

| Constant | Value | Meaning |
|----------|-------|---------|
| `EVENT_LOOP_DELAY_WARN_MS` | 1000ms | P99 or max delay > 1s |
| `EVENT_LOOP_UTILIZATION_WARN` | 0.95 | ELU > 95% |
| `CPU_CORE_RATIO_WARN` | 0.9 | CPU time / wall time > 90% |

## Diagnostic Commands

```bash
# Check if control-ui exists
ls ~/openclaw/dist/control-ui/index.html 2>/dev/null

# Count auto-build triggers
grep -c "Control UI assets missing" ~/Library/Logs/openclaw/gateway.log

# Check for build race (missing dist modules)
grep "Cannot find module.*dist/" ~/Library/Logs/openclaw/gateway.log | tail -10

# Check buildstamp vs control-ui existence
cat ~/openclaw/dist/.buildstamp 2>/dev/null
ls ~/openclaw/dist/control-ui/index.html 2>/dev/null

# LaunchAgent env (service-env wrapper)
cat ~/.openclaw/service-env/ai.openclaw.gateway.env | grep PATH

# Fix: one-time build
cd ~/openclaw && pnpm ui:build
```

## Long-Term Fix

`cleanTsdownOutputRoots()` should exclude `dist/control-ui/` from recursive deletion. Only clean TypeScript compilation output directories, not Vite-built assets. This prevents the build race where `.buildstamp` exists but `dist/control-ui/` doesn't.

## Historical Data

- **First observed**: 2026-05-26 16:39 (manual recovery snapshot)
- **Auto-build count**: 54 times between 2026-05-28 and 2026-06-01
- **Peak degradation**: eventLoopDelayMaxMs=33236 (33 seconds), cpuCoreRatio=0.995
- **Root cause confirmed**: tsdown `rmSync(dist/, {recursive: true})` + ui:build as last build step
