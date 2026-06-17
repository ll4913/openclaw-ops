# Local Feature Development Pattern: Silent Reply Disallow

Worked example of building a custom feature on top of upstream OpenClaw. The "silent reply disallow" feature intercepts empty/silent model replies in direct conversations and sends a fallback message instead of silently dropping them.

## Architecture Layers

OpenClaw reply delivery flows through three layers. A feature that changes reply behavior typically needs interception at multiple points:

1. **Reply Dispatcher** (`src/auto-reply/reply/reply-dispatcher.ts`) — `enqueue()` decides whether to deliver or drop a reply payload. This is the first interception point.
2. **Outbound Payload Plan** (`src/infra/outbound/payloads.ts`) — `createOutboundPayloadPlan()` builds the delivery plan from raw payloads. Silent payloads are normally filtered out here.
3. **Channel Delivery** (`extensions/telegram/src/bot/delivery.ts`) — Final delivery to Telegram. Tests here verify end-to-end behavior.

## Implementation Pattern

### Step 1: Define Constants in Shared Module

```typescript
// src/shared/silent-reply-policy.ts
export const SILENT_REPLY_DISALLOWED_FALLBACK_TEXT =
  "I received this, but the model returned an empty reply. Please send it again.";
```

**Why shared?** Constants referenced by multiple layers (dispatcher, payloads, tests) must live in `src/shared/` to avoid circular imports.

### Step 2: Intercept at Dispatcher Level

In `reply-dispatcher.ts` `enqueue()`:

```typescript
const shouldSurfaceDisallowedSilent =
  kind === "final" &&
  originalWasExactSilent &&
  resolveSilentReplyPolicy({
    cfg: options.silentReplyContext?.cfg,
    sessionKey: options.silentReplyContext?.sessionKey,
    surface: options.silentReplyContext?.surface,
    conversationType: options.silentReplyContext?.conversationType,
  }) === "disallow";

// If normalized is null (would be dropped) but policy says disallow:
const deliverable =
  shouldSurfaceDisallowedSilent && !normalized
    ? { ...payload, text: SILENT_REPLY_DISALLOWED_FALLBACK_TEXT }
    : normalized;
```

### Step 3: Intercept at Payload Plan Level

In `payloads.ts` `createOutboundPayloadPlanEntry()`:

```typescript
const originalIsSilent = strippedParsed.isSilent && mergedMedia.length === 0;
const shouldSurfaceDisallowedSilent =
  originalIsSilent &&
  resolveSilentReplyPolicy({ ... }) === "disallow";
const parsedText = shouldSurfaceDisallowedSilent
  ? SILENT_REPLY_DISALLOWED_FALLBACK_TEXT
  : (strippedParsed.text ?? "");
```

Add `surfaceIfOnlySilent` flag to plan entries so the plan builder knows which silent entries can serve as fallback when all entries are silent.

### Step 4: Policy Resolution

Use existing `resolveSilentReplyPolicy()` from `src/config/silent-reply.ts`. Default policy:
- **direct** (DM): `"disallow"` (hardcoded) — always surface fallback
- **group/channel**: `"allow"` (configurable) — normal silent behavior
- **internal**: `"allow"` (configurable) — normal silent behavior

## Test Pattern

When changing behavior from "drop" to "surface", rename tests and update assertions:

```typescript
// BEFORE (old behavior: drop silently)
it("drops exact NO_REPLY final payloads for direct sessions", async () => {
  expect(dispatcher.sendFinalReply({ text: SILENT_REPLY_TOKEN })).toBe(false);
  await dispatcher.waitForIdle();
  expect(deliver).not.toHaveBeenCalled();
});

// AFTER (new behavior: surface fallback)
it("surfaces exact NO_REPLY final payloads for direct sessions", async () => {
  expect(dispatcher.sendFinalReply({ text: SILENT_REPLY_TOKEN })).toBe(true);
  await dispatcher.waitForIdle();
  expect(deliver).toHaveBeenCalledTimes(1);
  expect(deliveredText(deliver)).toBe(SILENT_REPLY_DISALLOWED_FALLBACK_TEXT);
});
```

**Key**: Group tests stay unchanged (groups allow silent replies by default).

## Verification

```bash
# All three test files must pass
pnpm test src/auto-reply/reply/reply-flow.test.ts    # 12 tests
pnpm test src/infra/outbound/payloads.test.ts         # 36 tests
pnpm test extensions/telegram/src/bot/delivery.test.ts # 53 tests

# Type check
npx tsc --noEmit

# Build
pnpm build
```

## Files Modified

| File | Change |
|------|--------|
| `src/shared/silent-reply-policy.ts` | Add `SILENT_REPLY_DISALLOWED_FALLBACK_TEXT` constant |
| `src/auto-reply/reply/reply-dispatcher.ts` | Add disallow check in `enqueue()`, create fallback deliverable |
| `src/infra/outbound/payloads.ts` | Add `surfaceIfOnlySilent` flag, intercept in plan builder |
| `src/auto-reply/reply/reply-flow.test.ts` | Update 2 tests: drops → surfaces |
| `src/infra/outbound/payloads.test.ts` | Update 1 test: drops → surfaces |
| `extensions/telegram/src/bot/delivery.test.ts` | Update 2 tests: suppresses → surfaces |

## Lessons Learned

1. **Check upstream before adding constants** — The constant might already exist in a newer version. After updating OpenClaw, verify your additions aren't duplicates.
2. **Multi-point interception is necessary** — Changing behavior at just the dispatcher OR just the payload plan level isn't sufficient. Both paths need the logic because they're used in different code paths.
3. **Test naming matters for code review** — Renaming "drops" to "surfaces" makes the behavior change immediately visible in test output.
4. **Group vs direct policy divergence** — Always test both conversation types to ensure group behavior isn't accidentally changed.
