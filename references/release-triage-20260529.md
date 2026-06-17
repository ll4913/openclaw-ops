# OpenClaw 2026.5.27 Release Triage — Impact Analysis

**Date**: 2026-05-29
**User environment**: Telegram + SolBI (16 agents), Codex ACP, LCM/gemini, SolMem→GBrain→LCM pipeline, anthropic:default only

## Triage Method

1. Read release notes from GitHub (`github.com/openclaw/openclaw/releases/tag/v2026.5.27`)
2. Read @openclaw X/Twitter posts for context (use browser, not API — TWITTER_BEARER_TOKEN was 401)
3. Classify each change as HIGH/MEDIUM/LOW relevance based on user's config and known issues
4. Cross-reference with user's known issues (SolBI stale session, ACP dispatch work)

## HIGH Relevance Findings

### Session Lock Deadlocks — SolBI Stale Session Root Cause

**PR #86123 — Session Event Queue Self-Wait Deadlock**
- File: `src/agents/pi-embedded-runner/run/attempt.session-lock.ts`
- Scenario: `_handleAgentEvent` processes event → triggers hook (e.g. `beforeToolCall`) → hook needs session write lock → acquiring lock requires draining event queue → but current event is still processing → **self-deadlock**
- Fix: `AsyncLocalStorage<SessionEventHookContext>` tracks whether current async chain is inside event processing; skips queue drain when `isProcessingAgentEventInCurrentChain()` returns true
- Symptom: Agent runs hang indefinitely, session appears stuck with no response and no error

**PR #86816 — Timeout Abort Lock Release**
- Same file as above
- Scenario: Agent run times out → abort handler calls `abortCompaction()` + `abortActiveSession()` → **does NOT release session write lock** → lock held until `dispose()` → if cleanup path needs lock → deadlock
- Fix: `releaseHeldLockForAbort()` called asynchronously when `isTimeout` is true
- Log signature: `"failed to release session lock on timeout abort"`
- Symptom: Sessions permanently locked/stale after timeout — subsequent messages block forever

**PR #87375 — Shared App-Server Survival (Codex)**
- File: `extensions/codex/src/app-server/thread-lifecycle.ts`
- Scenario: Spawned helper (sub-agent) fails at `thread/start` RPC → catch block unconditionally kills shared app-server → parent agent also loses Codex connection
- Fix: `CodexThreadStartRequestError` distinguishes logical vs transport failures; preserves shared client for spawned helper failures

**PR #87428 — Shared App-Server Startup (Codex)**
- File: `extensions/codex/src/app-server/run-attempt.ts`
- Scenario: Any startup error cleared shared client (too aggressive)
- Fix: `shouldClearSharedClientAfterStartupRace()` only clears on specific startup timeout/abort errors

### Telegram Delivery
**PR #87261** — Telegram sendMessage actions now use durable outbound delivery. Messages survive process restarts.

### Reply/Session Delivery
**PR #87044** — Visible turn admission no longer bounded by hidden cleanup timeouts. Visible fallback delivery keeps latest targets.

## MEDIUM Relevance Findings

### Gateway Performance
- Session reads, plugin metadata fingerprints, auth env snapshots, auto-enabled plugin config — all hot-path cached
- Isolated cron prompt-cache affinity stabilized (benefits cron jobs)

### Memory/Embedding Deprecation
**PR #85269 + #85072** — OpenAI-compatible embedding provider enters core; plugin-specific `registerMemoryEmbeddingProvider` deprecated.
- Deprecation code: `deprecated-memory-embedding-provider-api`
- Warning message: "uses deprecated memory-specific embedding provider API"
- **User not affected**: uses `gemini` + `gemini-embedding-001` (bundled, already migrated)
- For future local Ollama use: `provider: "openai-compatible"`, `model: "nomic-embed-text"`, `remote: { baseUrl: "http://127.0.0.1:11434/v1" }`
- Removal target: 2026-08-21

### Anthropic Model Direct Pass
Bare Anthropic model IDs now resolve directly without full config — simplifies routing for anthropic:default users.

### Claude CLI OAuth Overlay
**PR #87167** — Claude CLI OAuth can overlay PI auth profiles. May interact with user's Claude OAuth keepalive LaunchAgent.

## LOW Relevance

- Security hardening (group prompts, admin approvals, block side-effecting wrappers)
- Pixverse video provider (not used)
- DeepInfra full catalog (user uses Anthropic)
- VLLM thinking params (DS4 uses OpenAI-compatible format)

## Feature Branch Conflict Analysis: feat/silent-reply-disallow vs #87044

**Result: ZERO conflicts.** Confirmed via dry-run merge.

| Dimension | Result |
|-----------|--------|
| File overlap | None — user changes `dispatch-acp.ts`, #87044 changes `reply-turn-admission.ts` |
| Import dependency | None — `dispatch-acp.ts` doesn't import from #87044 files |
| API surface | Different subsystems (admission wait vs delivery fallback) |
| Semantic | #87044 = wait timeout semantics, user = delivery path |
| Only auto-reply conflict | `dispatch.freshness.test.ts` type refinement (`unknown` → `object | void`), trivial |

**Rebase**: Clean rebase onto latest main, zero conflicts. 3 commits rebased successfully.
