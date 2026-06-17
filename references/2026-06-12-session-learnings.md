# OpenClaw Session Learnings (2026-06-12)

## Vitest Watch-Mode Dead Loop

**Root cause**: Claude Code (ACP agent) in OpenClaw worktrees calls `vitest file.test.ts` without `run` subcommand → vitest enters watch mode → never exits → 97%+ CPU → monitors entire monorepo.

**Why CPU is so high**:
- OpenClaw is a large monorepo with thousands of files
- `--no-maglev` flag disables V8 optimizer (doubles CPU overhead)
- fswatch/auto-commit processes trigger file changes → watch re-runs tests
- `runtime.test.ts` has 51 test cases, each creating/destroying AcpxRuntime

**Three-layer defense (deployed 2026-06-12)**:
1. **CLAUDE.md rules** in `~/openclaw/AGENTS.md` — Commands and Tests sections both have CRITICAL rules forbidding bare vitest
2. **PreToolUse hook** in `~/.claude/hooks/pre-tool-use-hook.sh` — blocks at command level:
   - `vitest file.test.ts` → BLOCK
   - `vitest run file.test.ts` → PASS
   - `pnpm test` → PASS
   - `node scripts/run-vitest.mjs` → PASS
3. **ACP Reaper cron** — kills >80% CPU vitest processes every 6h

**Detection**: When diagnosing 100% CPU, check `ps aux | grep vitest`. It's the #1 cause in OpenClaw environments.

**Correct invocations**:
```bash
pnpm test <file>                           # preferred
vitest run <file>                          # direct
node scripts/run-vitest.mjs <file>         # worktree-safe
```

## System Proxy Bypass Causing MC/PBI Data Pipeline Failure

**Symptom**: MC dashboard New Orders and Inventory showing dashes (-), only historical data visible.

**Root cause chain**:
1. Codex Desktop running system proxy on `127.0.0.1:3067`
2. System proxy bypass list was **empty**
3. `login.microsoftonline.com` routed through proxy → `Connection reset by peer`
4. PBI query script (`pbi_query.py`) failed OAuth token acquisition
5. All DAX queries timed out → 176万 timeout entries in MC logs
6. MC dashboard data empty

**Diagnostic method**:
```bash
# Direct (bypass proxy) — should succeed
curl --noproxy '*' -w "%{http_code}" "https://login.microsoftonline.com/..."
# → 200

# Via proxy — should fail if proxy is broken
curl -x http://127.0.0.1:3067 -w "%{http_code}" "https://login.microsoftonline.com/..."
# → 000

# Check proxy config
networksetup -getwebproxy Wi-Fi       # → 127.0.0.1:3067
networksetup -getproxybypassdomains   # → (empty!)
```

**Fix**:
```bash
networksetup -setproxybypassdomains Wi-Fi \
  "login.microsoftonline.com" "*.microsoftonline.com" "*.microsoft.com" \
  "*.azure.com" "*.powerbi.com" "*.analysis.windows.net" \
  "localhost" "127.0.0.1" "*.local"

# Restart MC to clear timeout queue
launchctl kickstart -k gui/$(id -u)/com.solm.mission-control
```

**Lesson**: System proxy bypass list empty = ALL traffic goes through proxy, including Microsoft OAuth. Always check bypass list when API calls fail with connection errors.

## mc.solm.com Architecture

**Request path**: `User → Cloudflare (LAX) → ngrok tunnel → Next.js "Mission Control" source`

**Key observations (2026-06-12)**:
- DNS: `mc.solm.com` → `198.20.0.51` (Charter/ngrok infrastructure), TTL=1 (proxied)
- Baseline latency: **1.5-2.2 seconds** even for trivial `/api/health` (tunnel overhead)
- Cache headers: `no-store, no-cache` — nothing cached by CF or browser
- Headers reveal: `ngrok-skip-browser-warning`, `x-nextjs-cache: HIT`, `x-powered-by: Next.js`
- Page loads in ~7.4s TTI due to tunnel + no-cache + Google Fonts + Vercel Analytics

**When mc.solm.com is slow/fails**:
1. Check tunnel: `curl -o /dev/null -w "%{time_total}" https://mc.solm.com/api/health` (should be <3s)
2. If >5s: ngrok tunnel may be down — check gateway logs for ngrok errors
3. If API returns empty data: PBI pipeline likely broken (check proxy bypass, OAuth)
4. If client-side error: MC server may be overwhelmed by stale queries — restart via launchctl

## ACP Reaper Script Details

See `scripts/acp_reaper.py` in this skill directory. Key design decisions:
- **Dry-run by default** — requires `--execute` to actually kill
- **Protected PIDs**: active ACP leases, Claude Desktop, gateway
- **7 phases** from aggressive (CPU bombs → SIGKILL) to gentle (lease cleanup)
- **Child process traversal**: kills MCP servers, remote bridges, tmux when parent dies
- **Lease file cleanup**: removes dead entries from `process-leases.json`

## Session Archive Command

```bash
# Full cleanup (all agents, removes unreferenced artifacts >30 days)
openclaw sessions cleanup --all-agents --enforce --json

# Typical output: 6000+ files removed, 40+ MB freed
# Main agent and opsbot are biggest artifact producers
```

**What it does NOT do**: prune session records (.jsonl trajectory files). Those are preserved. Only orphaned tool outputs and intermediate artifacts are removed.

## CGPDFService (macOS System Process)

**What it is**: `/System/Library/Frameworks/CoreGraphics.framework/.../CGPDFService.xpc` — macOS system XPC service for PDF rendering/indexing.

**Why many instances**: Spotlight (`mdworker_shared`) spawns one CGPDFService per PDF being indexed. After bulk file operations (git commits, file moves), Spotlight re-indexes → many CGPDFService processes at 94% CPU each.

**Action**: Usually self-resolving. If persistent, kill the hot ones or temporarily disable Spotlight: `sudo mdutil -i off /` then `sudo mdutil -i on /`.
