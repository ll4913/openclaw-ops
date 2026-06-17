# Session Lifecycle Management & TCC Workaround

## 3-Layer Session Maintenance

### Layer 1: OpenClaw Built-in (automatic)
```json
"session": { "maintenance": { "mode": "enforce", "pruneAfter": "30d", "maxEntries": 500 } }
```
Prunes index entries only. Does NOT delete .jsonl trajectory files.

### Layer 2: External Volume Archive (daily 04:00, launchd)
- Script: `~/.openclaw/scripts/archive-acp-sessions.mjs` (Node.js)
- LaunchAgent: `com.solm.archive-acp-sessions`
- Target: `/Volumes/Extreme Pro/OpenClawBackups/acp-sessions/`
- Archives >7d inactive sessions per agent as .tar.gz, verifies, deletes source
- **Must be Node.js** — bash has TCC permission issues (see below)

### Layer 3: Artifact Cleanup
```bash
openclaw sessions cleanup --all-agents --dry-run --json  # preview
openclaw sessions cleanup --all-agents --enforce          # execute
```
Removes unreferenced artifacts (orphan tool outputs, attachments). Typically 10-50 MB/run.

## Health Targets
- <5000 .jsonl files total
- <20 files >5MB
- <10 GB `~/.openclaw/agents/`

## macOS TCC + Launchd + External Volumes

**Pitfall:** macOS TCC blocks `/bin/bash` and `/usr/bin/python3` from writing to external volumes under LaunchAgent context. `/opt/homebrew/bin/node` works because it has Full Disk Access.

| Context | Write to /Volumes/ |
|---------|-------------------|
| Interactive shell (bash) | ✅ |
| LaunchAgent (/bin/bash) | ❌ Operation not permitted |
| LaunchAgent (/opt/homebrew/bin/node) | ✅ |

**Fix:** Rewrite launchd scripts needing external volume access in Node.js (.mjs). Update plist:
```xml
<key>ProgramArguments</key>
<array>
  <string>/opt/homebrew/bin/node</string>
  <string>/path/to/script.mjs</string>
</array>
<key>EnvironmentVariables</key>
<dict>
  <key>HOME</key><string>/Users/lianglin</string>
  <key>PATH</key><string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
</dict>
```

**Diagnostic:** `launchctl submit -l test -- /bin/bash -c 'echo x > "/Volumes/Drive/.test"'`

## ACP Process Reaper

Script: `~/.openclaw/workspace/scripts/acp_reaper.py`
Cron: Hermes job `953c1f637370`, every 6h

7 phases: CPU bombs (>80%) → stale Claude (>24h) → orphaned bridges (>12h) → stale worktrees (>24h) → orphaned MCP → duplicate LSP → dead leases.

Protected: active ACP leases, Claude Desktop, gateway, current Hermes LSP (<2h).

## Vitest Watch-Mode Guard

PreToolUse hook at `~/.claude/hooks/pre-tool-use-hook.sh` blocks bare `vitest` (without `run` subcommand). Bare vitest enters watch mode → infinite loop → 100% CPU. Also enforced via CRITICAL rule in `~/openclaw/AGENTS.md`.

Test patterns:
- `vitest file.test.ts` → BLOCK
- `vitest run file.test.ts` → PASS
- `pnpm test` → PASS
- `node scripts/run-vitest.mjs` → PASS

## 2026-06-12 Archive Results

Fixed archive script from bash v2 → Node.js v3. Cleared 13 days of backlog:
- 11,205 items archived across 21 agents
- 612 MB freed from local disk
- Session files: 12,194 → 3,756 (-69%)
- Large files (>5MB): 58 → 12 (-79%)
