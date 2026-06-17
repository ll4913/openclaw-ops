# ACP Session Stdin Closure Investigation (2026-06-06)

## Problem

ACP Codex sessions crash mid-task after 2+ hours. Agent's implementation is left incomplete — uncommitted changes in worktree, no delivery, user sees "not implemented yet" despite canary passing for other changes.

## Symptom

```
2026-06-05T18:49:24.734543Z ERROR codex_core::tools::router: error=write_stdin failed: 
stdin is closed for this session; rerun exec_command with tty=true to keep stdin open
```

## Case Study: BU Revenue Business Model View

**Context**: Xinye asked SolBI bot "where is the view for BU Revenue by business model". Bot correctly answered "not available yet". User then asked bot to implement it.

**What happened**:
1. ACP Codex session started (PID 81513, session `a92e7add-0b8a-4c29-91c7-0f3df068bdd7`)
2. Bot created worktree `/private/tmp/mc-naca-bu-business-model-view-20260606-20260606-0305/`
3. Bot did thorough analysis: read page.tsx, refresh script, GitNexus impact check
4. Bot started editing: added TypeScript interface for `business_model_revenue_scorecard`, toggle state, toggle handlers (176-line diff in `app/naca/page.tsx`)
5. **At message 41/42 (~2.5h in)**: stdin closed during Edit tool call
6. Session stuck: `Closed: False`, no exit, no more messages
7. `refresh_naca_dashboard.py` never edited (0-line diff), no data, no commit, no delivery

## Stdin Pipe Chain Architecture

```
OpenClaw gateway (src/acp/client.ts:144)
  stdio: ["pipe", "pipe", "inherit"]
  ↓ stdin (pipe)
codex-acp-wrapper.mjs (line 208)
  stdio: ["inherit", "inherit", "pipe"]
  ↓ stdin (inherited pipe)
Codex CLI (Rust binary, CODEX_HOME=~/.openclaw/acpx/codex-home/)
  ↓ exec_command tool
Child shell command ← stdin already closed ❌
```

The wrapper inherits stdin from OpenClaw gateway. After 2+ hours of idle or intermittent use, the pipe can close due to OS-level keep-alive timeout, process group changes, or network-level pipe degradation.

## OpenClaw Config Search (No tty Support)

Searched all relevant files — **no tty/pty/keepAlive options exist**:

| File | Searched for | Result |
|------|-------------|--------|
| `src/config/types.acp.ts` | tty, pty, keepAlive, stdin | Only: enabled, dispatch, backend, fallbacks, defaultAgent, allowedAgents, maxConcurrentSessions, stream, runtime |
| `src/acp/client.ts` | tty, pty | Hard-coded `stdio: ["pipe", "pipe", "inherit"]` at line 144 |
| `~/.openclaw/acpx/codex-acp-wrapper.mjs` | tty, pty | Hard-coded `stdio: ["inherit", "inherit", "pipe"]` at line 208 |
| `~/.openclaw/acpx/codex-home/config.toml` | tty | Not present |
| `~/.codex/config.toml` | tty | Not present |

Codex's `tty=true` is a parameter for its internal `exec_command` tool (Rust side), telling it to use PTY for child shell commands. It's not a CLI flag or config option.

## Fix Proposals

### Option A: Wrapper Heartbeat (Recommended Short-Term)

Change `codex-acp-wrapper.mjs`:
```javascript
// Line 208: change from "inherit" to "pipe"
const child = spawn(command, args, {
  detached: process.platform !== "win32",
  env,
  stdio: ["pipe", "inherit", "pipe"],  // was: ["inherit", "inherit", "pipe"]
  windowsHide: true,
});

// Add keep-alive heartbeat
const keepAlive = setInterval(() => {
  if (child.stdin && !child.stdin.destroyed) {
    try { child.stdin.write(""); } catch {}  // empty write keeps pipe alive
  }
}, 30_000);

child.on("close", () => clearInterval(keepAlive));
child.on("exit", () => clearInterval(keepAlive));
```

**Pros**: Simple, no OpenClaw source change, wrapper is user-editable
**Cons**: Doesn't address root cause (why pipe closes)

### Option B: Stdin Close Detection + Logging

Add to wrapper:
```javascript
process.stdin?.on("close", () => {
  writeRedactedStderrLog(`[${new Date().toISOString()}] WARN: parent stdin closed`);
});
child.stdin?.on("close", () => {
  writeRedactedStderrLog(`[${new Date().toISOString()}] WARN: child stdin closed`);
});
```

**Pros**: Diagnostic visibility
**Cons**: Detection only, doesn't fix

### Option C: OpenClaw PR (Long-Term)

Add `tty?: boolean` to `AcpRuntimeConfig` in `src/config/types.acp.ts`:
```typescript
export type AcpRuntimeConfig = {
  ttlMinutes?: number;
  installCommand?: string;
  turnStallTimeoutMs?: number;
  tty?: boolean;  // NEW: use PTY for ACP subprocess stdin
};
```

Then in `src/acp/client.ts`:
```typescript
const useTty = opts.tty ?? false;
const agent = spawn(command, args, {
  stdio: useTty ? ["pipe", "pipe", "inherit"] : ["pipe", "pipe", "inherit"],
  // With tty: use node-pty or similar to allocate PTY
});
```

**Pros**: Proper fix at the right layer
**Cons**: Requires OpenClaw source change, rebuild, deploy

## Workaround (Until Fixed)

Break large ACP tasks into subtasks that each complete within ~90 minutes. The stdin closure appears to be time-correlated (~2h threshold).

```
/acp spawn Sol_BI --cwd ~/Projects/mission-control --label bu-model-step1-data --bind here --mode session
→ Task: "Add business_model_revenue_scorecard to refresh_naca_dashboard.py and refresh data"

/acp spawn Sol_BI --cwd ~/Projects/mission-control --label bu-model-step2-ui --bind here --mode session  
→ Task: "Add business model toggle and rendering to app/naca/page.tsx"

/acp spawn Sol_BI --cwd ~/Projects/mission-control --label bu-model-step3-deliver --bind here --mode session
→ Task: "Commit, verify, and deliver the BU Revenue business model view"
```

## Diagnostic Commands

```bash
# Check if ACP session PID is alive
ps -p <PID> -o pid,etime,command

# Find stdin close errors
grep "write_stdin failed" ~/.openclaw/acpx/codex-acp-wrapper.stderr.*.log

# Check session state
cat ~/.openclaw/workspace/state/sessions/agent%3Acodex%3Aacp%3A<session-id>.json | \
  python3 -c "import sys,json; d=json.load(sys.stdin); msgs=d.get('messages',[]); print(f'Messages: {len(msgs)}, Closed: {d.get(\"closed\")}, Last: {d.get(\"last_used_at\")}')"

# Check worktree for uncommitted work
cd /private/tmp/mc-<slug>-<timestamp>/ && git diff --stat && git status --short
```

## Related

- Error occurs in `codex_core::tools::router` (Rust binary)
- OpenClaw ACP architecture: `src/agents/acp-spawn.ts`, `src/acp/client.ts`
- Wrapper: `~/.openclaw/acpx/codex-acp-wrapper.mjs`
- Session state: `~/.openclaw/workspace/state/sessions/`
