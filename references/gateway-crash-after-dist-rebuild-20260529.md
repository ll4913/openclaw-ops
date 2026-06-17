# Gateway Crash After Dist Rebuild — 2026-05-29 Incident

## Symptom

`/status` command in Telegram produces no response. Gateway logs show repeated errors at 500ms intervals:

```
[telegram] [diag] spooled update XXXXX failed; keeping for retry: Error in middleware: Cannot find module '/Users/lianglin/openclaw/dist/commands-status-BZrHyBJ5.js' imported from /Users/lianglin/openclaw/dist/get-reply-B8BX7-SK.js
```

Gateway CPU at 34% (normally <10%).

## Root Cause Chain

1. Gateway process (PID 91571) started at 05:00 using old `dist/` chunks
2. At 08:28, `pnpm build` rebuilt `dist/` — chunk file hashes changed (`commands-status-BZrHyBJ5.js` → `commands-status-CgztqLcb.js`)
3. Old gateway process tries to import old chunk hash → `ERR_MODULE_NOT_FOUND`
4. Two spooled Telegram updates enter retry loop (every 500ms)
5. CPU spikes to 34% from constant retries

## Why It Doesn't Self-Heal

The old gateway process will never find the old chunk files — they've been deleted by the new build. The retry loop is infinite.

## Fix

```bash
# 1. Kill old gateway
pkill -9 -f 'openclaw/dist/index.js'
sleep 2

# 2. Start new gateway (use background terminal)
cd ~/openclaw
# terminal(background=true): node dist/index.js gateway --port 18789
```

## Secondary Failure: Config Schema Migration

After restarting, gateway may fail with a config validation error:

```
Gateway failed to start: Invalid config at /Users/lianglin/.openclaw/openclaw.json.
agents.list.5: Unrecognized key: "embeddedPi"
```

New builds tighten config schemas. In v2026.5.27, `embeddedPi` was renamed to `embeddedAgent`.

### Fix

```python
import json
with open('$HOME/.openclaw/openclaw.json') as f:
    cfg = json.load(f)
for a in cfg.get('agents', {}).get('list', []):
    if 'embeddedPi' in a:
        a['embeddedAgent'] = a.pop('embeddedPi')
defaults = cfg.get('agents', {}).get('defaults', {})
if 'embeddedPi' in defaults:
    defaults['embeddedAgent'] = defaults.pop('embeddedPi')
with open('$HOME/.openclaw/openclaw.json', 'w') as f:
    json.dump(cfg, f, indent=2, ensure_ascii=False)
    f.write('\n')
```

Or run `openclaw doctor --fix` which handles known migrations automatically.

## Diagnostic Quick Reference

```bash
# Check for the retry storm pattern
tail -100 ~/Library/Logs/openclaw/gateway.log | grep "Cannot find module" | head -5

# Check gateway process age vs dist build time
ps -p $(pgrep -f 'openclaw/dist/index.js' | head -1) -o pid,etime
stat -f "%Sm" ~/openclaw/dist/index.js

# If process etime > time since last build → mismatch confirmed
```

## Prevention

- After any `pnpm build` or dist modification, always restart the gateway
- The launchd service (`ai.openclaw.gateway`) should auto-restart, but if the service was started manually, it won't
- Consider adding a post-build hook: `launchctl kickstart -k gui/$(id -u)/ai.openclaw.gateway`
