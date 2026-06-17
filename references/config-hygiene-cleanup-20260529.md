# Config Hygiene Cleanup — 2026-05-29

## Background

After fixing the Anthropic auth profile event-loop starvation issue (7/8 invalid profiles across 16 agents), a deep scan revealed extensive config hygiene problems in `models.json` and `openclaw.json`.

## models.json Cleanup (29 → 19 providers)

### Removed

| Provider | Reason |
|----------|--------|
| `anthropic-sub2api` | Dead proxy at http://20.253.144.24:8080 → 405 Not Allowed |
| `google` | Duplicate of gemini (same URL, different expired key) |
| `qwen-portal` | Expired OAuth key, no active service |
| `x-ai` | Duplicate of xai (same service) |
| `swiftlm` | Placeholder key, no local service |
| `local` | Placeholder key `x`, unreachable |
| `qwen` | Placeholder key, dashscope covers same service |
| `openrouter` | Placeholder key `OPENROUTER_API_KEY` |
| `arcee` | Placeholder key, same as openrouter |
| `deepseek` | Placeholder key `DEEPSEEK_API_KEY` |

### Fixed

- **Gemini key**: synced expired `AIzaSyDAbzPhTs...` → valid `AIzaSyDI3ZAI...` from env

### Kept (placeholder but harmless)

These use env vars or auth-profiles at runtime, so the placeholder in models.json is ignored:
- `anthropic` (placeholder `ANTHROPIC_API_KEY`, runtime uses auth-profiles)
- `xai` (placeholder `XAI_API_KEY`, runtime uses auth-profiles/env)
- `openai` (placeholder `OPENAI_API_KEY`, runtime uses env)
- `zai` (placeholder `ZAI_API_KEY`, runtime uses openclaw.json)

## openclaw.json Cleanup

### Dead Tool References Removed

| Tool | From | Reason |
|------|------|--------|
| `firecrawl_search` | global alsoAllow, mcbot | firecrawl plugin disabled |
| `firecrawl_scrape` | global alsoAllow, mcbot | firecrawl plugin disabled |
| `memory_recall` | global alsoAllow, healthbot, mcbot | memory-lancedb plugin disabled |
| `memory_store` | global alsoAllow, healthbot, mcbot | memory-lancedb plugin disabled |
| `pdf` | global alsoAllow, healthbot, mcbot | No plugin provides this tool |

### Dead Plugin Entries Removed

| Plugin | From | Reason |
|--------|------|--------|
| `openrouter` | entries | Config present but not in allow list → startup warning |
| `moonshot` | entries | Config present but not in allow list |
| `deepseek` | entries + allow | No provider config, placeholder key |
| `google` | entries + allow | No provider, duplicate of gemini |
| `qwen` | entries + allow | No provider, dashscope covers it |
| `firecrawl` | allow | Plugin disabled, no config |

### Counts

- `plugins.allow`: 16 → 12
- `plugins.entries`: 17 → 12
- `tools.alsoAllow`: 19 → 14
- `models.json` providers: 29 → 19

## Key Pattern: OpenClaw Key Resolution Order

1. **Environment variable** (highest priority)
2. **auth-profiles.json** (per-agent credential store)
3. **models.json** (fallback, often placeholder)

A provider with a placeholder key in models.json is **functionally harmless** if the real key exists in env or auth-profiles. But it creates noise during audits.

## Key Pattern: Dead Tool References

When a plugin is disabled, its registered tools disappear. But references in `tools.alsoAllow` or per-agent `tools.alsoAllow` persist. OpenClaw logs these as `allowlist contains unknown entries` warnings on every agent startup. Not a functional issue, but adds 4-6 WARN lines per startup cycle.

## Verification

After cleanup:
```bash
# Should show ZERO "unknown entries" warnings
grep "unknown entries" /tmp/openclaw/openclaw-$(date +%Y-%m-%d).log | tail -5

# Should show ZERO "not in allowlist" warnings
grep "not in allowlist" /tmp/openclaw/openclaw-$(date +%Y-%m-%d).log | tail -5

# Auth preheat should be fast (<15s)
grep "pre-warmed" /tmp/openclaw/openclaw-$(date +%Y-%m-%d).log | tail -1
```
