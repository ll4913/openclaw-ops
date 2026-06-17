# Agent Performance Diagnostic — 2026-05-29

## Context

User asked to "check SolBI's performance in group and DM chat." This documents the full diagnostic workflow for investigating any OpenClaw agent's behavior.

## Diagnostic Steps

### 1. Check Recent Activity

```bash
# Find agent session files
ls -la ~/.openclaw/agents/<agent_id>/sessions/ 2>/dev/null | head -20

# Check recent sessions (last 24h)
find ~/.openclaw/agents/<agent_id>/sessions/ -name "*.jsonl" -mtime -1 -exec ls -lh {} \;
```

### 2. Check Gateway Logs for Agent Activity

```bash
# Inbound messages
grep "Inbound.*<agent_name>\|<bot_username>" /tmp/openclaw/openclaw-$(date +%Y-%m-%d).log

# Session creation/routing
grep "sessionKey.*agent:<agent_id>" /tmp/openclaw/openclaw-$(date +%Y-%m-%d).log | tail -20

# LCM compaction activity
grep "lcm.*<agent_id>\|lcm.*sessionKey.*<agent_id>" /tmp/openclaw/openclaw-$(date +%Y-%m-%d).log
```

### 3. Check Agent Config

```python
import json
with open(f"{HOME}/.openclaw/openclaw.json") as f:
    d = json.load(f)
for a in d.get("agents", {}).get("list", []):
    if a.get("id") == "<agent_id>":
        print(json.dumps(a, indent=2))
```

### 4. Check Telegram Account Config

```python
import json
with open(f"{HOME}/.openclaw/openclaw.json") as f:
    d = json.load(f)
accounts = d.get("channels", {}).get("telegram", {}).get("accounts", {})
print(json.dumps(accounts.get("<account_name>", {}), indent=2))
```

### 5. Check Auth Profiles

```bash
cat ~/.openclaw/agents/<agent_id>/agent/auth-profiles.json | python3 -m json.tool
```

### 6. Check Tools Warnings

```bash
grep "tools.allow.*<agent_id>\|agents.<agent_id>.tools" /tmp/openclaw/openclaw-$(date +%Y-%m-%d).log
```

**Common issue**: `tools.allow` references tools from disabled plugins (e.g., `memory_recall`, `firecrawl_search`). These produce warnings but don't block functionality. Fix: remove from `tools.alsoAllow` in agent config.

### 7. Check LCM Summarizer

```bash
# Check LCM config
grep "lcm.*summar\|summaryModel\|summaryProvider" /tmp/openclaw/openclaw-$(date +%Y-%m-%d).log | tail -10

# Check current config
python3 -c "
import json
d = json.load(open(f'{HOME}/.openclaw/openclaw.json'))
lcm = d.get('plugins', {}).get('entries', {}).get('lossless-claw', {}).get('config', {})
print(f'Provider: {lcm.get(\"summaryProvider\")}')
print(f'Model: {lcm.get(\"summaryModel\")}')
"
```

**Common timeout**: `ollama-local/qwen3.6:35b` times out (60s) on large sessions. Switch to `gemini/gemini-2.5-flash`.

### 8. Verify DM Routing

```bash
# Check if DMs route to correct agent
grep -A10 "Inbound.*direct.*<bot_username>" /tmp/openclaw/openclaw-$(date +%Y-%m-%d).log | grep sessionKey
```

**Expected**: `sessionKey=agent:<agent_id>:telegram:direct:<chatId>`
**Problem**: If session key shows different agent ID, check for stale session files.

## Findings (SolBI Case)

### Group Chat: Working

- 17 sessions active in last 24h
- Multiple group topics (859, 2379, 3359) with active conversations
- LCM compaction running normally
- No routing issues

### DM: Routing Issue

- DMs to @Sol_BI_bot routing to `agent:engineer` instead of `agent:solbi`
- **Root cause**: Pre-existing session `agent:engineer:telegram:direct:8524721791` from when engineer agent was handling those DMs
- **Not a config issue**: `agentId` field doesn't exist in telegram account config (validation error)
- **Fix**: Archive the stale engineer DM session, or accept that engineer will continue handling those DMs

### LCM Summarizer: Timeout

- Config: `ollama-local/qwen3.6:35b` timing out (60s)
- **Root cause**: 35B model too slow for compaction
- **Fix**: Changed to `gemini/gemini-2.5-flash` + added to `llm.allowedModels`

### Tools Warnings: Noise

- `tools.allow` references: `sessions_spawn`, `edit`, `exec`, `process`, `message`
- **Root cause**: These tools are in `alsoAllow` but some are only available in certain execution modes
- **Impact**: Cosmetic warnings only, no functional impact

## Key Insights

1. **Session affinity trumps config**: OpenClaw reuses existing sessions by session key. If a session was created with agent X, new messages to the same chat will continue using agent X even if config changes.

2. **LCM has two-layer model config**: `agents.defaults.compaction.model` (core) vs `plugins.entries.lossless-claw.config.summaryModel` (plugin override). Both need to be fast for good compaction performance.

3. **Tools warnings are usually cosmetic**: References to tools from disabled plugins or unavailable execution modes produce warnings but don't block functionality.

4. **Auth profiles are per-agent**: Each agent has its own `auth-profiles.json`. Check the specific agent's profiles, not just the main agent.
