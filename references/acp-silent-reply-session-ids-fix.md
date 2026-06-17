# ACP Silent Reply Bug — "Session ids resolved" Eats Agent Replies

**Date**: 2026-05-29
**Severity**: HIGH — users see diagnostic instead of agent's real reply
**Fix**: Cherry-pick PR #87820 (commits `4cd4df307a` + `2985116cd3`)

## Symptom

User sends message to ACP-spawned bot (e.g., Finance Bot / Claude). Bot replies with:
```
⚙️ Session ids resolved.
acpx session id: aebaf87e-dc5a-4b29-b613-8852a49c0c87
acpx record id: agent:claude:acp:e5d89a92-50c8-410b-af5f-1cb032727957
```
But NO actual agent response. User's question is "eaten."

## Root Cause

`src/auto-reply/reply/dispatch-acp.ts`, lines 280-311:

1. **Streaming produces no "visible text"**: Codex/ACP responses flow through streaming but don't set `hasDeliveredVisibleText()` to true.
2. **Text fallback skipped** (lines 280-282):
   ```typescript
   const shouldDeliverTextFallback =
     !finalMediaDelivered &&
     !params.delivery.hasDeliveredFinalReply() &&
     (!params.delivery.hasDeliveredVisibleText() || params.delivery.hasFailedVisibleTextDelivery());
   ```
   When streaming worked but produced no visible text, `shouldDeliverTextFallback` is true but `accumulatedVisibleBlockText` is empty.
3. **Diagnostic message sent as `final`** (lines 292-311):
   ```typescript
   if (params.shouldEmitResolvedIdentityNotice) {
     const delivered = await params.delivery.deliver("final", {
       text: prefixSystemMessage(["Session ids resolved.", ...resolvedDetails].join("\n")),
     });
   }
   ```
   This fires because `shouldEmitResolvedIdentityNotice` is true for new sessions (identity went from pending → resolved).

## Trigger Conditions

All three must be true:
1. `shouldEmitResolvedIdentityNotice` = true (new session, first turn, identity just resolved)
2. ACP streaming produced no visible text
3. `suppressUserDelivery` is false

## Fix: `maybeDeliverSessionStoreFinalFallback`

PR #87820 adds this function that runs BEFORE the diagnostic message:

```typescript
async function maybeDeliverSessionStoreFinalFallback(params) {
  // Skip if already delivered something
  if (params.delivery.hasDeliveredFinalReply() ||
      params.delivery.hasDeliveredVisibleText() ||
      params.delivery.getAccumulatedFinalText().trim() ||
      params.delivery.getAccumulatedBlockText().trim()) {
    return false;
  }
  // Read agent's actual reply from session store
  const text = await extractLatestAcpAssistantTextFromSessionStores(params);
  if (text.trim()) {
    return await params.delivery.deliver("final", { text });
  }
  return false;
}
```

It reads the agent's reply from:
1. `readAcpSessionEntry()` — the OpenClaw session store
2. `readAcpxRuntimeSessionRecord()` — the ACPX runtime session JSON at `~/.openclaw/workspace/state/sessions/{recordId}.json`

## Cherry-Pick Procedure

```bash
cd ~/openclaw

# Cherry-pick both commits
git cherry-pick 4cd4df307a 2985116cd3 --no-edit

# Resolve test conflicts (use --theirs for test files)
git checkout --theirs src/auto-reply/reply/dispatch-acp.test.ts
git add src/auto-reply/reply/dispatch-acp.test.ts

# Continue with bypass if default checkout guard is active
DEFAULT_CHECKOUT_ALLOW_COMMIT=1 git cherry-pick --continue --no-edit

# Build (build:plugin-sdk:dts may fail but runtime JS build succeeds)
pnpm build 2>&1 | tail -20

# Verify fix is in dist
grep -c "maybeDeliverSessionStoreFinalFallback" dist/dispatch-acp-*.js
# Should show 2 (definition + call site)

# Restart gateway
launchctl kickstart -k gui/$(id -u)/ai.openclaw.gateway
sleep 15
```

## Verification

After restart, send a message to the ACP-spawned bot. Expected:
- Agent's actual reply appears first
- `⚙️ Session ids resolved` may appear after (harmless diagnostic)
- OR neither appears (if session identity was already resolved from previous turn)

## Related

- `src/auto-reply/reply/dispatch-acp.ts` — main dispatch logic
- `src/auto-reply/reply/dispatch-acp.test.ts` — tests (conflicts on cherry-pick, use --theirs)
- `src/shared/` — shared constants added by the PR
- PR #87820: `feat(auto-reply): disallow silent replies in direct conversations with ACP session fallback`
