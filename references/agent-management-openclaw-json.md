# OpenClaw Agent Management — Add/Remove Agents

## Config Location

`~/.openclaw/openclaw.json` → `agents.list[]` (array of agent objects)

## Agent Object Structure

```json
{
  "id": "agent-id",
  "name": "Display Name",
  "workspace": "/Users/lianglin/.openclaw/workspace-agentid",
  "model": {
    "primary": "provider/model-id",
    "fallbacks": ["provider2/model2"]
  },
  "tools": { "profile": "coding", "alsoAllow": [...], "deny": [...] },
  "subagents": { "allowAgents": ["engineer", "solbi"] },
  "skills": ["skill-name", ...],
  "memorySearch": { "enabled": true, ... }
}
```

## Removing an Agent

### Pre-removal checks

```bash
# 1. Check subagent references (other agents may reference this one)
python3 -c "
import json
with open('$HOME/.openclaw/openclaw.json') as f:
    cfg = json.load(f)
to_delete = {'agent-id'}
for a in cfg['agents']['list']:
    subs = a.get('subagents', {}).get('allowAgents', [])
    for ref in subs:
        if ref in to_delete:
            print(f'{a[\"id\"]} references {ref}')
"

# 2. Check workspace path — is it shared with another agent?
# If workspace is the same as 'main' or 'advisor', DO NOT delete the directory.

# 3. Check LaunchAgents / crontab references
grep -rl "agent-id\|workspace-agentid" ~/Library/LaunchAgents/ 2>/dev/null
crontab -l 2>/dev/null | grep -i "agent-id"
```

### Removal steps

```python
import json, shutil
with open('$HOME/.openclaw/openclaw.json') as f:
    cfg = json.load(f)

cfg['agents']['list'] = [a for a in cfg['agents']['list'] if a.get('id') != 'agent-id']

with open('$HOME/.openclaw/openclaw.json', 'w') as f:
    json.dump(cfg, f, indent=2, ensure_ascii=False)
    f.write('\n')
```

```bash
# Delete dedicated workspace ONLY (not shared!)
rm -rf ~/.openclaw/workspace-agentid

# Restart gateway
launchctl kickstart -k gui/$(id -u)/ai.openclaw.gateway
```

## Model Switching (Telegram Commands)

```
/model dashscope/qwen3.7-max          # Switch model (session-only)
/model anthropic/claude-sonnet-4-6     # Switch back to default
/models                                # Show available models with buttons
```

- Session-only: `/reset` or new session returns to agent default
- No natural language support (Chinese "切换到千问" does NOT work)
- Provider format: `<provider>/<model-id>`

## Audit: Which Agents Use a Specific Model

```bash
python3 -c "
import json
with open('$HOME/.openclaw/openclaw.json') as f:
    cfg = json.load(f)
defaults = cfg['agents'].get('defaults', {}).get('model', {}).get('primary', '')
for a in cfg['agents']['list']:
    model = a.get('model', {}).get('primary', '(inherits default)')
    if model == '(inherits default)':
        model = defaults + ' ← inherited'
    print(f'  {a[\"id\"]:15s} {a.get(\"name\",\"\"):15s} {model}')
"
```
