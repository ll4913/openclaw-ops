# ACP Session Cleanup — Full Chain (2026-06-09)

## Problem

Killing Claude Code / Codex processes alone does NOT fix ACP errors. OpenClaw's ACPX runtime has a 3-layer process tree per session:

```
wrapper (acpx/claude-agent-acp-wrapper.mjs)
  └── claude-agent-acp (node module)
       └── claude (the actual Claude Code CLI)
```

The lease file (`~/.openclaw/acpx/process-leases.json`) tracks which PIDs own which sessions. Killing only the Claude process leaves:
- Dead wrapper processes (still running, stdin closed)
- Stale lease entries (state: "open" but PID is dead)
- OpenClaw thinks all ACP slots are occupied → `ACP_TURN_FAILED: Internal error`

## Cleanup Procedure (4 Steps)

### Step 1: Identify stale processes

```bash
# Check all Claude/Codex processes
ps aux | grep -i "[c]laude.*stream-json\|[c]laude.*--resume\|[c]odex-acp"

# Check lease file
python3 -c "
import json, os
d = json.load(open(os.path.expanduser('~/.openclaw/acpx/process-leases.json')))
for l in d['leases']:
    pid = l['rootPid']
    session = l['sessionKey'].split(':')[-1][:12]
    try:
        os.kill(pid, 0)
        print(f'  ALIVE: PID {pid} | {session}')
    except ProcessLookupError:
        print(f'  DEAD:  PID {pid} | {session}')
"
```

### Step 2: Kill ALL layers (Claude + wrapper)

```bash
# Kill Claude Code processes
kill <pid1> <pid2> ...

# Kill their wrapper processes (check ps output for matching wrapper PIDs)
# Wrappers are: ~/.openclaw/acpx/claude-agent-acp-wrapper.mjs
kill <wrapper_pid1> <wrapper_pid2> ...

# Also kill any orphaned claude-agent-acp node processes
ps aux | grep "[c]laude-agent-acp" | awk '{print $2}' | xargs kill 2>/dev/null
ps aux | grep "[c]odex-acp-wrapper" | awk '{print $2}' | xargs kill 2>/dev/null
```

### Step 3: Clean the lease file

```bash
python3 -c "
import json, os
path = os.path.expanduser('~/.openclaw/acpx/process-leases.json')
d = json.load(open(path))
alive = []
for l in d['leases']:
    try:
        os.kill(l['rootPid'], 0)
        alive.append(l)
    except ProcessLookupError:
        pass
d['leases'] = alive
with open(path, 'w') as f:
    json.dump(d, f, indent=4)
print(f'Cleaned: {len(alive)} alive leases remaining')
"
```

### Step 4: Restart gateway (if ACP still errors)

```bash
launchctl kickstart -k gui/$(id -u)/ai.openclaw.gateway
# Wait for all bots to reconnect (~30s)
sleep 30
tail -5 ~/Library/Logs/openclaw/gateway.log
```

## Diagnostic: Why ACP Fails After Partial Cleanup

| Symptom | Cause | Fix |
|---------|-------|-----|
| `ACP_TURN_FAILED: Internal error` | Dead lease entries still in lease file | Step 3 (clean lease file) |
| `ACP_TURN_FAILED: session limit` | Too many alive sessions | Step 2 (kill stale processes) |
| `ACP_TURN_FAILED: Internal error` after restart | Lease file repopulated from disk with stale entries | Step 3 BEFORE restart |
| Bot not responding after cleanup | Gateway not fully restarted | Wait 30s, check `starting provider` in logs |

## Prevention: Zombie Process Reaper

The `zombie-process-reaper.py` cron (every 30m) kills processes with no stdin pipes. But it doesn't clean the lease file. After reaper runs, manually clean leases (Step 3) if ACP errors appear.

## Quick Reference

```bash
# One-liner: identify dead leases
python3 -c "import json,os; d=json.load(open(os.path.expanduser('~/.openclaw/acpx/process-leases.json'))); [print(f'PID {l[\"rootPid\"]} DEAD') for l in d['leases'] if not (lambda p: (os.kill(p,0),True)[-1])(l['rootPid']) if False]; print(f'Total: {len(d[\"leases\"])} leases')"
# (use the full script in Step 3 instead)
```
