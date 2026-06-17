# ACP Process Reaper & Vitest Guard (2026-06-12)

## Automated ACP Process Reaper

### Script & Cron
- **Script**: `~/.openclaw/workspace/scripts/acp_reaper.py`
- **Cron**: Hermes job `ACP Process Reaper` (id: `953c1f637370`), every 6h, silent when clean
- **Usage**: `python3 ~/.openclaw/workspace/scripts/acp_reaper.py` (dry-run) or `--execute`

### 7 Kill Categories
1. **Vitest dead loops** (>80% CPU, `vitest`/`vitest.mjs` with `acpx` or `test.ts`) — SIGKILL
2. **QMD bun dead loops** (>90% CPU, `bun` with `qmd`) — SIGKILL
3. **MC guard hook loops** (>90% CPU, `default-checkout-cwd-guard.sh`) — SIGKILL
4. **Stale standalone Claude** (>24h, NOT ACP-managed, NOT Desktop app) — SIGTERM + children
5. **Orphaned remote bridges** (>12h, `.claude/remote/srv`) — SIGTERM
6. **Stale worktree processes** (>24h, `/private/tmp/mc-*`, `/private/tmp/openclaw-*`) — SIGTERM
7. **Dead ACP leases** (process-leases.json entries with dead PIDs) — cleaned from JSON

### Protection List
Active ACP sessions (from `~/.openclaw/acpx/process-leases.json`), Claude Desktop app, OpenClaw gateway, fresh Hermes LSP (<2h) are **never** killed.

### Process Classification (from session analysis)
A typical system has 47+ claude/acpx-related processes. Breakdown:
- **acp_wrapper_active**: 3 (one per active ACP session) — wrapper.mjs + claude CLI + ACP dist/index.js + MCP server pairs
- **standalone_claude**: bare `claude` processes (interactive sessions) — kill if >24h
- **remote_bridge**: `.claude/remote/srv/*/server` + login parent pairs — kill if >12h
- **claude_desktop**: Claude.app helpers — never kill
- **mcp_server**: episodic-memory + pbi-mcp — kill only if parent dead
- **tmux**: associated with standalone claude — kill with parent

## Vitest Bare Invocation — Root Cause of Recurring CPU Bombs

### The Pattern
```
Claude Code ACP agent in OpenClaw worktree
  → Reads AGENTS.md "run tests to verify"
  → Calls: vitest.mjs extensions/acpx/src/runtime.test.ts --passWithNoTests=false
  → Missing "run" subcommand → vitest enters WATCH MODE
  → Monitors entire monorepo (1000s of files)
  → --no-maglev flag disables V8 optimizer → even higher CPU
  → File changes from fswatch/auto-commit trigger constant re-runs
  → 97-100% CPU forever
```

### Why runtime.test.ts is especially bad
- 51 test cases, each creating/destroying AcpxRuntime instances
- Fake timers with beforeEach/afterEach cleanup
- Retryable test cases that loop on failure

### Three-Layer Defense

**Layer 1: CLAUDE.md rule** (`~/openclaw/AGENTS.md`)
Added CRITICAL notes in Commands section (line ~95) and Tests section (line ~178):
```
- **CRITICAL — no bare vitest invocations.** Never call vitest or vitest.mjs directly without "run".
```

**Layer 2: PreToolUse hook** (`~/.claude/hooks/pre-tool-use-hook.sh`)
Added vitest detection before the dangerous pattern loop:
```bash
if echo "$COMMAND" | grep -qE '(vitest|vitest\.mjs)'; then
    # Skip safe wrappers
    if echo "$COMMAND" | grep -qE 'run-vitest\.mjs|pnpm test|pnpm dev'; then
        : # safe
    elif echo "$COMMAND" | grep -qE '(vitest|vitest\.mjs)\s+run\b'; then
        : # safe, has run subcommand
    else
        # BLOCK — return JSON with decision: block
    fi
fi
```

**Layer 3: ACP Reaper cron** — 6h sweep kills anything that slipped through.

### Pitfall: Worktree Sync
After updating `~/openclaw/AGENTS.md`, copy to active worktrees:
```bash
cp ~/openclaw/AGENTS.md /private/tmp/openclaw-*-worktree/AGENTS.md
```
New worktrees clone from the repo, so they'll get the update on next `git pull`, but existing ones need manual sync.

## CGPDFService — Not Our Problem

macOS system process (`CoreGraphics.framework/XPCServices/CGPDFService.xpc`) spawned by Spotlight (`mdworker_shared`) to index PDF metadata. Multiple instances at ~94% CPU each are normal during Spotlight re-indexing (e.g., after bulk file moves). Self-resolves in minutes. Don't kill unless sustained >10min.
