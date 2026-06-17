# API Key Comprehensive Audit — 2026-05-29

## The Multi-Source Key Problem

OpenClaw resolves API keys from multiple sources with a priority chain:
1. `auth-profiles.json` (per-agent, highest priority)
2. `models.json` (per-agent agent config)
3. `openclaw.json` (global config)
4. Environment variables (shell/service-env)

A key can be **invalid in models.json** but **valid at runtime** because the runtime resolves from a different source. This makes naive "test all keys" audits misleading.

## Audit Technique

### Step 1: Identify effective runtime keys
```bash
openclaw models status 2>&1 | grep "effective="
```
This shows what OpenClaw ACTUALLY uses at runtime.

### Step 2: Test each effective key
```python
import json, os, subprocess

# Parse effective key info from openclaw models status output
# Then test each with a real API call appropriate to the provider's API type
```

### Step 3: Cross-reference with all sources
For each provider, check keys in ALL locations:
- `~/.openclaw/agents/*/agent/auth-profiles.json`
- `~/.openclaw/agents/main/agent/models.json`
- `~/.openclaw/openclaw.json` (under `models.providers`)
- Service env: `~/.openclaw/service-env/ai.openclaw.gateway.env`
- Shell env: `$OPENAI_API_KEY`, `$ANTHROPIC_API_KEY`, etc.

## Findings from 2026-05-29 Audit

| Provider | Source | Status | Notes |
|----------|--------|--------|-------|
| Anthropic | auth-profiles (main) | ✅ Valid | After cleanup, only `anthropic:default` |
| Anthropic | auth-profiles (16 agents) | ✅ Valid | After batch cleanup |
| OpenAI Codex | auth-profiles (OAuth) | ✅ Valid | 2 accounts, 40h + 10d remaining |
| xAI | auth-profiles + env | ✅ Valid | 2 keys, both working |
| Dashscope | models.json | ✅ Valid | 247 models |
| Moonshot | auth-profiles | ✅ Valid | 9 models |
| Gemini | models.json | ❌ Expired | But runtime uses env key (valid) |
| Gemini | env (`$GEMINI_API_KEY`) | ✅ Valid | 50 models |
| Gemini | openclaw.json | ✅ Valid | Same as env |
| zai | openclaw.json | ✅ Valid | Runtime resolves here |
| zai | models.json | 📌 Placeholder | `ZAI_API_KEY` — not a real key |
| google | models.json | ❌ Invalid | Duplicate of gemini, placeholder |
| anthropic-sub2api | models.json | ❌ Dead | Proxy at IP:8080 returns 405 |
| openai | models.json | 📌 Placeholder | `OPENAI_API_KEY` — not real |
| deepseek | models.json | 📌 Placeholder | `DEEPSEEK_API_KEY` — not real |
| openrouter | models.json | 📌 Placeholder | `OPENROUTER_API_KEY` — not real |

## Placeholder Keys in models.json

models.json contains ~15 placeholder keys like `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, etc. These are config templates — runtime overrides from env/auth-profiles replace them. **Not a bug, but a hygiene concern.**

## Config Hygiene Issues (non-blocking)

1. **Gemini models.json key expired** — Runtime uses env key, so no functional impact
2. **anthropic-sub2api proxy dead** — `http://20.253.144.24:8080` returns 405. Was used as fallback historically.
3. **google provider duplicates gemini** — Same URL, different (invalid) placeholder key
4. **15+ placeholder keys** — Clutter but no runtime impact

## Recommended Cleanup (low priority)

```bash
# 1. Sync Gemini key in models.json to match env
# 2. Remove anthropic-sub2api from models.json
# 3. Remove duplicate google provider
# 4. (Optional) Remove placeholder keys
```

## Diagnostic Script Pattern

```python
import json, os, glob

# 1. Collect all keys per provider across all sources
# 2. Identify effective runtime source via `openclaw models status`
# 3. Test effective keys with real API calls
# 4. Report: source, key prefix, validity, agents using it
```

This audit took ~10 minutes and revealed that the Anthropic profile issue was the ONLY provider with runtime-impacting invalid credentials. All other issues were config hygiene.
