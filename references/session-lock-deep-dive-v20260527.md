# v2026.5.27 Session Lock & Codex App-Server Deep Dive

## Root Cause Analysis: "SolBI DM→engineer stale session"

The user reported sessions going permanently stale after agent runs. Investigation of v2026.5.27 PRs revealed two distinct deadlock mechanisms that together explain this pattern.

---

### Deadlock A: Session Event Queue Self-Wait (#86123)

**File**: `src/agents/pi-embedded-runner/run/attempt.session-lock.ts` (+53/-8 lines)

**Scenario**:
1. `_handleAgentEvent` processes an event (e.g., `tool_call`)
2. It calls hooks like `beforeToolCall`
3. Those hooks need the session write lock
4. Acquiring the lock requires first draining the session event queue (`waitForSessionEventQueue`)
5. Since the hook executes *inside* the current queue entry, draining means waiting for *itself*
6. **Instant self-deadlock** — session hangs indefinitely

**Fix**: Introduced `AsyncLocalStorage<SessionEventHookContext>` to track whether the current async chain is inside an active event processing call. New function `waitForSessionEventQueueBeforeHook()` skips the queue drain when `isProcessingAgentEventInCurrentChain(session)` returns true. Detached/external hook work (spawned after the event handler returns) still drains correctly.

**Symptoms**: Agent runs hanging indefinitely when extension hooks (beforeToolCall, afterToolCall, onPayload, onResponse) fired during active event processing. The session appeared "stuck" — no response, no error.

---

### Deadlock B: Timeout Abort Not Releasing Session Write Lock (#86816)

**File**: `src/agents/pi-embedded-runner/run/attempt.session-lock.ts`

**Scenario**:
1. Agent run times out (idle timeout or external abort)
2. Abort handler calls `abortCompaction()` and `abortActiveSession()`
3. **But does NOT release the held session write lock**
4. Lock remains held until `dispose()` runs during cleanup
5. If the cleanup path itself needs to acquire a lock (e.g., for session file fence operations)
6. **Deadlock waiting for the lock it already holds**

**Fix**: Added `releaseHeldLockForAbort()` to the `EmbeddedAttemptSessionLockController` interface. When `isTimeout` is true during abort, fires `releaseHeldLockForAbort()` asynchronously. Uses a drain/waiter system (`heldLockDraining`, `retainedLockUseCount`) to safely coordinate between in-flight locked operations and the abort release.

**Log signature to check**: `"failed to release session lock on timeout abort"` — if this appears, the lock release path failed.

**Symptoms**: Sessions becoming permanently locked/stale after a timeout. Subsequent messages to the same session block waiting for the write lock that was never released.

---

### Codex App-Server Stability Fixes

#### Shared Client Survival (#87375)

**File**: `extensions/codex/src/app-server/thread-lifecycle.ts` (+34/-6)

**Bug**: When a spawned helper run (sub-agent) failed at the `thread/start` RPC, the catch block unconditionally called `clearSharedCodexAppServerClientIfCurrent`, killing the shared app-server process. The *parent* agent also lost its Codex connection.

**Fix**: Introduced `CodexThreadStartRequestError` to distinguish logical thread-start failures (RPC errors from Codex server) from transport/startup failures. Preserves shared client when `params.spawnedBy` is set AND the error is a thread-start request error.

#### Startup Error Classification (#87428)

**File**: `extensions/codex/src/app-server/run-attempt.ts` (+14/-7)

**Bug**: Error catch block cleared shared app-server client on *any* startup error, including transient app-level errors.

**Fix**: `shouldClearSharedClientAfterStartupRace(error)` only clears when the error is specifically a startup timeout or abort message. Transient errors preserve the shared client.

#### Memory Routing Through Tools (#87383)

**File**: `extensions/codex/src/app-server/attempt-context.ts` (+227/-26)

**Bug**: Workspace `memory.md` files were injected directly into system prompt context, consuming tokens even when `memory_search`/`memory_get` tools were available.

**Fix**: When memory tools are available and workspace is canonical (non-sandbox), memory files excluded from bootstrap context injection and surfaced through tool routing instead. `memoryToolRouted` flag tracks this state.

---

### Write/Edit False Failure Warning (#86855)

**File**: `src/agents/pi-tools.host-edit.ts` (+210 lines)

**Bug**: When a write/edit tool completed the disk mutation successfully but the ack reply timed out (e.g., slow Telegram channel), `tool-mutation` recorded `lastToolError.timedOut=true` with a `fileTarget`. The warning policy emitted "⚠️ Write failed" even though the file was already saved correctly.

**Fix**: Suppresses warnings only when `lastToolError.timedOut` is true AND `lastToolError.fileTarget` is defined. Also added write recovery that pre-checks file state and verifies the write actually completed.

---

### Forced Plugin Harness Validation (#74341)

**File**: `src/agents/harness/selection.ts` (+36/-3 lines)

**Bug**: When user forced Codex runtime, harness selection accepted any OpenAI-like provider through a hardcoded bypass without checking if Codex actually supported that provider/model.

**Fix**: Calls `forced.supports({ provider, modelId, requestedRuntime })` before pinning. Falls back to PI harness for CLI runtime aliases. Throws clear error for truly unsupported combinations.

---

## Verification After Upgrade

After deploying v2026.5.27, monitor for:

1. **Stale sessions**: Check logs for `"failed to release session lock on timeout abort"`
2. **Codex disconnections**: Check for unexpected `clearSharedCodexAppServerClient` calls
3. **False write failures**: Check for `"Write failed"` / `"Edit failed"` warnings that shouldn't appear
4. **Session hang patterns**: If agent runs still hang, check if extension hooks fire during event processing (the AsyncLocalStorage fix should prevent this)

Run for several days to confirm the stale session pattern is resolved.
