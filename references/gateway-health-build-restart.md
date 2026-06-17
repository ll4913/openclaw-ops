# Gateway-health Build Artifact Recovery

## Symptom
`openclaw gateway status` reports missing `dist/entry.(m)js` or another OpenClaw runtime artifact.

## Recovery Steps (order matters)

1. **Check for transient rebuild window** — files may reappear within seconds of a recent deploy. Retry once.
2. **If files remain missing**, build artifacts from `/Users/lianglin/openclaw`:
   ```bash
   cd /Users/lianglin/openclaw && npm run build
   ```
3. **Restart `ai.openclaw.gateway`**:
   ```bash
   launchctl kickstart gui/$(id -u)/ai.openclaw.gateway
   ```
4. If launchd stuck in `spawn scheduled`: clear stray `openclaw-gateway` helper processes first.
5. **Verify** with:
   ```bash
   openclaw gateway status
   openclaw channels status --timeout 30000
   python3 ~/.openclaw/workspace/scripts/p1p2_ops_safe.py gateway-health
   ```
6. **Do NOT run** `openclaw gateway status --deep --require-rpc` as part of standard verification — it can timeout during warm-up/event-loop pressure even when the wrapper's lightweight status probe is OK.
