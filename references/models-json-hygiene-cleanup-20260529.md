# models.json Hygiene Cleanup — 2026-05-29

## Context

After fixing the Anthropic auth-profile-failure issue (Phase 10), a comprehensive
audit of all provider keys revealed configuration hygiene problems in `models.json`.

## Discovery

### Source Resolution Chain

OpenClaw resolves provider keys in this priority order:
1. **auth-profiles.json** (per-agent, highest priority for OAuth/tokens)
2. **models.json** (per-agent provider config)
3. **openclaw.json** (global `models.providers`)
4. **Environment variables** (lowest priority)

The runtime-effective key is shown by `openclaw models status` via the `effective=` field.

### Issues Found

| Issue | Provider | Impact |
|-------|----------|--------|
| Expired key | gemini (models.json) | None (openclaw.json had valid key) |
| Dead proxy | anthropic-sub2api | 405 Not Allowed, caused cron fallback failures |
| Duplicate | google vs gemini | Same URL, different (invalid) key |
| Placeholders | 15+ providers | No impact (runtime uses other sources) |

### Key Insight: models.json ≠ runtime truth

`models.json` can contain stale/expired keys without affecting runtime behavior
because `openclaw models status` shows the **effective** key source. The `effective=`
field tells you exactly which source the runtime uses.

### Cleanup Actions

**Removed (11 entries):**
- `anthropic-sub2api` — dead proxy at http://20.253.144.24:8080
- `google` — duplicate of `gemini` (same URL)
- `qwen-portal`, `swiftlm`, `local`, `x-ai` — stale placeholders
- `qwen` — placeholder, dashscope covers same service
- `openrouter`, `arcee` — placeholder keys
- `deepseek` — placeholder key

**Fixed (1 entry):**
- `gemini` apiKey synced to match valid env key (`AIzaSyDI...0Qrgme5Y`)

**Kept as-is (placeholder keys):**
- `anthropic`, `xai`, `openai`, `zai` — runtime resolves from auth-profiles/env/openclaw.json

### Verification Script

See `references/scripts/validate-all-provider-keys.py` for a comprehensive validator
that tests all keys across all three config sources + environment variables.

### Batch Agent Cleanup Script

See `references/scripts/batch-anthropic-cleanup.py` for cleaning invalid profiles
across all agent directories. Supports `--dry-run`.

### Pitfall: Gateway Restart After models.json Changes

Modifying `models.json` requires a gateway restart. If `dist/` was corrupted or
deleted during the session (e.g., from git checkout switching branches), you'll get
`ERR_MODULE_NOT_FOUND`. Fix: `cd ~/openclaw && pnpm build` then restart.

### Prevention

Run `python3 references/scripts/validate-all-provider-keys.py` periodically to
detect expired keys before they cause cascading failures.
