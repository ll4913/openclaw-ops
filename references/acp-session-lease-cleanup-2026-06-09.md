# ACP Session & Lease Cleanup (2026-06-09)

## Architecture
Each OpenClaw ACP session has 3 layers:
1. **Claude Code / Codex process** — the actual AI agent (`claude --output-format stream-json ...`)
2. **OpenClaw wrapper** — `claude-agent-acp-wrapper.mjs` or `codex-acp-wrapper.mjs` (manages lifecycle)
3. **Lease entry** — in `~/.openclaw/acpx/process-leases.json` (tracks PID, session ID, state)

## Problem: Dead Leases Block New Sessions
When Claude Code processes die (killed, crashed, session limit hit), the wrapper and lease can persist:
- Wrapper PID dies → lease `rootPid` no longer exists
- Lease remains `"state": "open"` or `"state": "lost"`
- OpenClaw thinks slot is occupied → new ACP spawns fail with "Internal error" or "session limit"

## Diagnostic Commands

### Check active leases
```bash
python3 -c "
import json, os
d = json.load(open('/Users/lianglin/.openclaw/acpx/process-leases.json'))
for l in d['leases']:
    pid = l['rootPid']
    session = l['sessionKey'].split(':')[-1][:12]
    alive = '✅' if os.path.exists(f'/proc/{pid}') else '💀'
    print(f'{alive} PID {pid} | {l[\"leaseId\"][:8]} | {l[\"state\"]} | {session}')
"
```

### Kill Claude Code processes (but NOT wrappers)
```bash
# Find all Claude Code processes
ps aux | grep "claude.*stream-json\|claude.*--resume" | grep -v grep
# Kill specific PIDs (keeps wrappers alive)
kill <pid1> <pid2>
```

### Kill orphaned wrappers (after Claude Code killed)
```bash
# Find wrapper processes with no matching Claude Code
ps aux | grep "claude-agent-acp-wrapper\|codex-acp-wrapper" | grep -v grep
# Kill by lease ID if you know which session is dead
kill <wrapper-pid>
```

### Clean dead leases from process-leases.json
```bash
python3 -c "
import json, os
path = '/Users/lianglin/.openclaw/acpx/process-leases.json'
d = json.load(open(path))
alive = [l for l in d['leases'] if os.path.exists(f'/proc/{l[\"rootPid\"]}')]
dead = [l for l in d['leases'] if not os.path.exists(f'/proc/{l[\"rootPid\"]}')]
print(f'Keeping {len(alive)} alive, removing {len(dead)} dead')
d['leases'] = alive
with open(path, 'w') as f:
    json.dump(d, f, indent=4)
"
```

### Restart gateway (last resort)
```bash
launchctl kickstart -k gui/$(id -u)/ai.openclaw.gateway
```
⚠️ Gateway restart does NOT automatically clean dead leases. Manual cleanup still needed.

## Claude Code Session Limits
Claude Code has a session limit that resets at a specific time (e.g., "resets 8:10pm Asia/Shanghai"). When hitting this limit:
1. Kill oldest/stale sessions first
2. Wait for reset time if all sessions are active
3. Check error message for exact reset time

## Proper Cleanup Sequence
1. Identify dead leases (Python script above)
2. Kill corresponding Claude Code PIDs (if still running)
3. Kill orphaned wrapper PIDs
4. Clean process-leases.json
5. Restart gateway only if new sessions still fail

## Prevention
- **zombie-process-reaper cron** (every 30m) kills orphaned processes but doesn't clean leases
- Add lease cleanup to reaper: check if `rootPid` exists, remove if not
- Monitor lease count: `wc -l ~/.openclaw/acpx/process-leases.json` — should stay < 20
