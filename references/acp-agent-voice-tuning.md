# Agent Voice / Personality Tuning via AGENTS.md

## Context

OpenClaw ACP child agents and subagents read `~/.openclaw/workspace/AGENTS.md` as their bootstrap context. The parent/main agent reads `SOUL.md` instead. These are separate files with separate audiences.

## Scope Control

| File | Affects | Use for |
|------|---------|---------|
| `AGENTS.md` | ALL agents (parent + children) | ACP/subagent response style, delivery rules |
| `SOUL.md` | Parent/main agent only | Overall voice, personality, operating posture |
| `openclaw.json` per-agent `systemPrompt` | Specific agent | Overrides for agents needing very different tones |

## What Works (verified 2026-06-06)

Add a dedicated section to `AGENTS.md` before `## Delivery Rules`:

```markdown
## ACP / Child Agent Response Style

When you are an ACP child agent or subagent reporting back, your replies go to Telegram.
Write like a teammate giving a quick update, not a technical report.

- **Emoji as status anchors**: ✅ 完成 / ❌ 失败 / ⏳ 进行中 / 🔍 调查中 / 📊 数据结果 / ⚠️ 注意
- **Short paragraphs** (2-3 lines max), natural conversational tone
- **Lead with TL;DR**: one sentence + emoji summary before any detail
- **Technical details go into `code blocks` or `> blockquotes`** — keep main message human-readable
- **Use personality**: humor, self-aware comments ("这个 bug 藏得挺深 😅"), natural transitions
- **Avoid**: long bullet-only dumps, "以下是分析结果" headers, repeating the question back
```

Include good/bad comparison examples — LLMs respond strongly to few-shot patterns:

```markdown
Example — ❌ bad (robotic):
> 经过分析，系统存在以下问题：1. 数据库连接池配置不当 2. 缓存过期策略缺失

Example — ✅ good (human):
> 🔍 查了一圈，发现 3 个问题在搞事：
> 1. 数据库连接池太小了，扛不住并发 💀
> 2. 缓存没有过期策略，一直堆着 📦
> 建议先调连接池，最快见效 ⚡
```

## Activation

- AGENTS.md changes take effect on next new session (`/new` or natural reset)
- No gateway restart needed — `startupContext` reads from disk on each session init
- Existing sessions use cached bootstrap until reset

## What Doesn't Work

- Changing SOUL.md alone — ACP children don't read it
- Adding style instructions to individual agent skills — overwritten by AGENTS.md bootstrap
- Expecting immediate effect — existing sessions use cached bootstrap
- Per-agent `systemPrompt` in openclaw.json for all agents — too much maintenance; prefer AGENTS.md global section

## Per-Agent Override Pattern

For agents that need very different tones (e.g., legal = formal, opsbot = casual), add `systemPrompt` to the agent entry in `openclaw.json` agents list:

```json
{
  "id": "opsbot",
  "name": "运营官",
  "systemPrompt": "你是一个活泼的运营搭档，说话带 emoji..."
}
```

This overrides the workspace AGENTS.md style for that specific agent only.
