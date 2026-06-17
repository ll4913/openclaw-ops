# Anthropic Auth Profile Cleanup — 2026-05-29

## Context

After updating OpenClaw from v2026.5.24 to v2026.5.27, event loop pressure persisted:
- `eventLoopDelayMaxMs` up to 22,112ms
- `auth profile failure state updated` appearing frequently
- `provider auth state re-warmed (auth-profile-failure) in 162375ms`
- Telegram fetch timeouts during re-warm

## Discovery

`~/.openclaw/agents/main/agent/auth-profiles.json` contained **8 Anthropic profiles**:

| # | Profile | Type | API Key Prefix | Curl Test |
|---|---------|------|----------------|-----------|
| 2 | accountA | OAuth token | sk-ant...IO8G | ❌ authentication_error |
| 3 | accountB | OAuth token | sk-ant...CZbg | ❌ authentication_error |
| 4 | accountC | OAuth token | sk-ant...Fp-e | ❌ authentication_error |
| 5 | mgdaclaude | OAuth token | sk-ant...LMSS | ❌ authentication_error |
| 6 | claudeteam | OAuth token | sk-ant...TitT | ❌ authentication_error |
| **7** | **default** | **API key** | **sk-ant...1PNO** | **✅ OK** |
| 8 | lianglin4913 | OAuth token | sk-ant...Q8Z2 | ❌ authentication_error |
| 9 | ll4913 | OAuth token | sk-ant...90Jz | ❌ authentication_error |

**7 out of 8 profiles were invalid.** Only `anthropic:default` had a valid API key.

## Error Chain Detail

```
1. OpenClaw gateway selects auth profile by dict insertion order
2. Tries accountA (invalid) → Anthropic returns 401
3. Node.js HTTP/2 connection reset → reports as ECONNRESET (not 401!)
4. "[model-fetch] error provider=anthropic causeCode=ECONNRESET message=fetch failed"
5. This triggers "auth profile failure state updated"
6. Gateway enters full auth re-warm cycle: tests ALL profiles sequentially
7. Re-warm takes 14-162 seconds (blocking event loop)
8. During re-warm: Telegram API fetches timeout, all agents stall
9. Finally failover to openai/gpt-5.5 or zai/glm-5.1
```

**Key insight**: The error reports as `ECONNRESET`, not `401 authentication_error`. This is because Anthropic's HTTP/2 implementation sends a GOAWAY frame on auth failure, which Node.js interprets as a connection reset.

## Fix Applied

```bash
# Backup
cp ~/.openclaw/agents/main/agent/auth-profiles.json \
   ~/.openclaw/agents/main/agent/auth-profiles.json.bak.20260529-010522

# Python script to remove 7 invalid profiles
python3 << 'EOF'
import json
with open('/Users/lianglin/.openclaw/agents/main/agent/auth-profiles.json') as f:
    data = json.load(f)
profiles = data.get('profiles', {})
invalid = ['anthropic:accountA', 'anthropic:accountB', 'anthropic:accountC',
           'anthropic:mgdaclaude', 'anthropic:claudeteam',
           'anthropic:lianglin4913', 'anthropic:ll4913']
for name in invalid:
    profiles.pop(name, None)
data['profiles'] = profiles
with open('/Users/lianglin/.openclaw/agents/main/agent/auth-profiles.json', 'w') as f:
    json.dump(data, f, indent=2)
EOF

# Restart
openclaw gateway restart
```

## Results

| Metric | Before | After |
|--------|--------|-------|
| Anthropic profiles | 8 (7 invalid) | 1 (valid) |
| Auth preheat | 15-162s | 13s |
| eventLoopMax | 22,112ms | 130ms |
| auth-profile-failure re-warm | Frequent (162s cycles) | Not observed |
| Telegram fetch timeouts | Multiple per session | Zero |

## Diagnostic Script

Reusable script for validating all Anthropic auth profiles:

```python
import json, subprocess

with open(f'{__import__("os").path.expanduser("~")}/.openclaw/agents/main/agent/auth-profiles.json') as f:
    data = json.load(f)

profiles = data.get('profiles', {})
for name, profile in profiles.items():
    if 'anthropic' not in name:
        continue
    if not isinstance(profile, dict):
        continue
    key = profile.get('apiKey') or profile.get('token') or profile.get('key')
    if not key:
        continue
    result = subprocess.run([
        'curl', '-s', '--connect-timeout', '5', '--max-time', '8',
        'https://api.anthropic.com/v1/messages',
        '-H', 'Content-Type: application/json',
        '-H', f'x-api-key: {key}',
        '-H', 'anthropic-version: 2023-06-01',
        '-d', '{"model":"claude-sonnet-4-6","max_tokens":5,"messages":[{"role":"user","content":"hi"}]}'
    ], capture_output=True, text=True)
    try:
        resp = json.loads(result.stdout)
        if resp.get('type') == 'message':
            print(f'✅ {name}: VALID')
        else:
            print(f'❌ {name}: {resp.get("error", {}).get("message", "unknown")}')
    except:
        print(f'❌ {name}: {result.stdout[:80]}')
```

## Lessons Learned

1. **ECONNRESET can mask authentication errors** — don't assume network issues, check auth profiles first
2. **Dict insertion order matters** — the first valid profile wins, but all invalid ones before it cause wasted attempts
3. **Auth re-warm is the real killer** — not the failed requests themselves, but the 162s re-warm cycle that blocks the entire event loop
4. **Profile count > 3 should trigger immediate audit** — more profiles = more attack surface for this pattern
5. **OAuth tokens expire silently** — they accumulate in auth-profiles.json without being cleaned up
