# ACP/Claude Process Reaper

**Script**: `~/.openclaw/workspace/scripts/acp_reaper.py`
**Cron**: `ACP Process Reaper` (job `953c1f637370`), every 6 hours
**Confirmed**: 2026-06-12 — cleaned 32 zombie processes (47→15), freed 8GB RAM, killed 4 CPU bombs

## What It Kills

| Type | Trigger | Signal |
|---|---|---|
| vitest dead loop | >80% CPU, `vitest` in cmd | SIGKILL |
| QMD bun dead loop | >90% CPU, `bun`+`qmd` | SIGKILL |
| MC guard hook dead loop | >90% CPU, `default-checkout-cwd-guard` | SIGKILL |
| Stale standalone Claude | >24h, not ACP-managed, not Desktop | SIGTERM + children |
| Orphaned remote bridge | >12h, `.claude/remote/srv` | SIGTERM |
| Stale worktree node | >24h, `/private/tmp/mc-*` | SIGTERM |
| Stale duplicate LSP | >24h hermes/lsp, >4 copies | SIGTERM (keep youngest 4) |
| Orphaned MCP server | parent PID dead, `episodic-memory` | SIGTERM |
| Dead ACP lease | rootPid not alive | Clean from process-leases.json |

## Protected Processes (never killed)

- Active ACP sessions from `~/.openclaw/acpx/process-leases.json`
- All children of active ACP sessions (wrapper, claude CLI, MCP servers)
- Claude Desktop app (`Claude.app`, `Claude Helper`)
- OpenClaw gateway (pid from `pgrep -f openclaw.*gateway`)

## Common Zombie Sources

1. **Cursor ACP vitest** — `/private/tmp/openclaw-cursor-acp-transport-recovery/` spawns stuck vitest tests that loop at 100% CPU
2. **Claude CLI orphans** — sessions that lose their parent tmux/ACP wrapper but keep running (found 12-day-old sessions)
3. **MC guard hook loops** — `default-checkout-cwd-guard.sh` enters infinite bash loop when called from wrong cwd
4. **QMD bun SQLite contention** — multiple qmd processes fighting for DB lock spin to 100% CPU
5. **Remote bridge pile-up** — Claude Desktop spawns new bridge servers per connection; old ones (login + server pairs) accumulate if not cleaned

## Usage

```bash
# Dry-run (safe, always test first)
python3 ~/.openclaw/workspace/scripts/acp_reaper.py

# Execute
python3 ~/.openclaw/workspace/scripts/acp_reaper.py --execute

# JSON output (for cron integration)
python3 ~/.openclaw/workspace/scripts/acp_reaper.py --execute --json
```

## Real Session Results (2026-06-12)

Before cleanup: 47 ACP/Claude processes, Load Avg 31+, 247GB RAM used, ~30-56% CPU idle
After cleanup: 15 processes, Load dropping, 239GB RAM (-8GB), 68% CPU idle

Killed:
- 2 vitest bombs (99% CPU each) + 1 QMD bun (97%) + 2 MC guard hooks (100% each) = ~500% CPU freed
- 4 stale standalone Claude sessions (12d, 1d, 4h, 1h) + their MCP children
- 5 stale remote bridges (oldest 2d22h)
- 8 orphaned MCP servers
- 5 stale worktree processes
- Stale LSP/PBI MCP/gitnexus
