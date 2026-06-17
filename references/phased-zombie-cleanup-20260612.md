# Phased Zombie Process Cleanup Taxonomy

**Discovered:** 2026-06-12 session cleanup (47 → 15 processes)

When process count exceeds 40+, use systematic classification before killing — don't just `pkill -f claude`.

## Phase 1: Runaway CPU Loops (Kill First)

Highest impact, immediate CPU relief:

- **vitest test loops**: `/private/tmp/openclaw-*-acp-transport-recovery/` worktrees running `vitest.mjs` stuck at ~97% CPU each
  ```bash
  ps aux | grep vitest | grep acpx | grep -v grep
  ```

- **QMD bun infinite loops**: `@tobilu/qmd` bun processes in infinite loops at 97%+ CPU
  ```bash
  ps aux | grep -E "bun.*qmd|qmd.*bun" | grep -v grep
  ```

- **MC guard hook loops**: `default-checkout-cwd-guard.sh` bash hooks looping at 100% CPU
  ```bash
  ps aux | grep "default-checkout-cwd-guard" | grep -v grep
  ```

**Action:** `kill -9` these immediately, no grace period needed.

## Phase 2: Stale Standalone Claude Sessions

Sessions >4h old with no active ACP lease:

1. **Check leases first:**
   ```bash
   cat ~/.openclaw/acpx/process-leases.json | python3 -m json.tool
   ```

2. **Identify orphans** (no lease or lease PID dead):
   ```bash
   ps -eo pid,ppid,%cpu,etime,command | grep -E "/opt/homebrew/bin/claude.*stream-json" | \
     grep -v grep | awk '$4 > "04:00:00" {print $1, $5}'
   ```

3. **Kill Claude CLI → wrapper → MCP children → tmux:**
   ```bash
   # Example for PID 18743 (12d old)
   kill -TERM 18743  # Claude CLI
   kill -TERM 22497 22498  # MCP children (episodic-memory)
   kill -TERM 18721  # tmux parent
   ```

## Phase 3: Remote Bridge Servers (>12h old)

Orphaned `~/.claude/remote/srv/*/server` processes from Claude Desktop:

```bash
ps -eo pid,ppid,etime,command | grep ".claude/remote/srv" | grep -v grep
```

**Keep:** Recent ones (<1h) from active Claude Desktop sessions  
**Kill:** Old ones (>12h) — always come in pairs (server + login)

```bash
# Example: 2d22h old
kill -TERM 86185 86186  # server + login pair
```

## Phase 4: Finished Worktree Processes

Node processes in completed MC worktrees:

```bash
ps -eo pid,etime,command | grep "/private/tmp/mc-" | grep -v grep
```

Common stale processes:
- Worktree dev servers (`node_modules/...`)
- Hermes LSP servers (>24h old): `~/.hermes/lsp/bin/*`
- PBI MCP server (`pbi-mcp-server`)
- gitnexus MCP (`gitnexus mcp`)
- gzip-proxy (`caddy-gzip-proxy`)

## Phase 5: ACP Lease Cleanup

After killing processes, clean stale leases:

```python
import json, os
from pathlib import Path

lease_file = Path.home() / '.openclaw/acpx/process-leases.json'
data = json.loads(lease_file.read_text())

active = []
for lease in data['leases']:
    pid = lease['rootPid']
    try:
        os.kill(pid, 0)  # Check if alive
        active.append(lease)
    except ProcessLookupError:
        pass  # Dead, skip

data['leases'] = active
lease_file.write_text(json.dumps(data, indent=2))
```

## Detection & Verification

**Initial scan:**
```bash
ps -eo pid,%cpu,etime,command | grep -E "claude|acpx|vitest|qmd" | \
  grep -v grep | sort -k2 -rn | head -20
```

**Categorized count:**
```bash
ps aux | grep -E "claude|cursor|acpx" | grep -v grep | grep -v Chrome | \
  grep -v "Claude.app" | wc -l
```

**Post-cleanup verification:**
```bash
# System load should drop significantly
top -l 1 -n 0 2>&1 | grep "Load Avg"

# Memory should free up
vm_stat | grep -E "Pages free|Pages inactive"
```

## Pitfalls

- **Don't kill Claude Desktop:** `Claude.app/Contents/*` processes are the GUI app
- **Don't kill active Hermes:** Processes with `hermes` in cmd and <1h age are current sessions
- **Don't kill active ACP:** Check `process-leases.json` before killing Claude CLI processes
- **Don't nuclear-pkill everything:** Phased approach preserves active work

## Expected Results

**Before cleanup:** 47 processes, Load Avg 31+, CPU idle 30-56%  
**After cleanup:** ~15 processes (3 active ACP sessions), Load Avg falling, CPU idle 68%+  
**Memory freed:** ~8GB typical
