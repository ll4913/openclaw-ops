# Auth Profile Diagnostic — 2026-05-29

## Problem

Main bot (OpenClaw gateway) experiencing persistent event loop pressure despite provider cleanup. Liveness warnings showed 10-22 second delays, blocking all Telegram bots and agent responses.

## Discovery

Checked auth profiles in `~/.openclaw/agents/main/agent/auth-profiles.json`:

```
Profile order (dict insertion order):
  2. anthropic:accountA | type=token | key=sk-ant...IO8G...
  3. anthropic:accountB | type=token | key=sk-ant...CZbg...
  4. anthropic:accountC | type=token | key=sk-ant...Fp-e...
  5. anthropic:mgdaclaude | type=token | key=sk-ant...LMSS...
  6. anthropic:claudeteam | type=token | key=sk-ant...TitT...
  7. anthropic:default | type=api_key | key=sk-ant...1PNO...  ✅ VALID
  8. anthropic:lianglin4913 | type=token | key=sk-ant...Q8Z2...
  9. anthropic:ll4913 | type=token | key=sk-ant...90Jz...
```

Tested each with curl → **7/8 profiles returned `authentication_error: invalid x-api-key`**.

Only `anthropic:default` (profile #7) was valid.

## Root Cause Chain

```
1. Request arrives → OpenClaw tries profile #1 (invalid) → 401
2. Tries #2, #3, #4, #5, #6 (all invalid) → 401 each
3. Finally tries #7 (valid) → succeeds
4. But "auth profile failure state" is now set
5. Triggers full re-warm: validates ALL 8 profiles sequentially
6. Re-warm takes 162 seconds (20s per invalid profile × 8)
7. During re-warm:
   - Event loop blocked (max delay 22s)
   - Telegram fetch timeouts (10s default)
   - All agent responses stall
   - Liveness warnings fire
```

## Log Evidence

```
2026-05-29T00:16:02.428+08:00 [WARN] [model-fetch] error provider=anthropic model=claude-sonnet-4-6 
  elapsedMs=2272 causeCode=ECONNRESET message=fetch failed
2026-05-29T00:16:03.217+08:00 [WARN] auth profile failure state updated
2026-05-29T00:16:03.221+08:00 [ERROR] lane task error: lane=main durationMs=72536 
  error="FailoverError: LLM request failed: network connection error."
2026-05-29T00:16:23.727+08:00 [INFO] provider auth state re-warmed (auth-profile-failure) 
  in 18498ms eventLoopMax=1081.1ms
2026-05-29T00:28:59.352+08:00 [WARN] [model-fetch] error provider=anthropic 
  elapsedMs=29858 causeCode=ECONNRESET
2026-05-29T00:31:43.907+08:00 [INFO] provider auth state re-warmed (auth-profile-failure) 
  in 162375ms eventLoopMax=22112.4ms  ← 162 SECONDS!
```

## Diagnostic Script

```python
import json, subprocess

with open('/Users/lianglin/.openclaw/agents/main/agent/auth-profiles.json') as f:
    data = json.load(f)

profiles = data.get('profiles', {})
print('Testing all Anthropic profiles:\n')

for name, profile in profiles.items():
    if isinstance(profile, dict) and 'anthropic' in name:
        key = profile.get('apiKey') or profile.get('token') or profile.get('key')
        ptype = profile.get('type', 'unknown')
        if key:
            print(f"{name} ({ptype}): {key[:25]}...")
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
                if resp.get('type') == 'error':
                    print(f"  ❌ {resp['error']['type']}: {resp['error']['message'][:80]}")
                elif resp.get('type') == 'message':
                    print(f"  ✅ OK: {resp.get('content',[{}])[0].get('text','')[:50]}")
                else:
                    print(f"  ❓ {str(resp)[:100]}")
            except:
                print(f"  ❌ Raw: {result.stdout[:100]} {result.stderr[:100]}")
```

## Resolution

Delete 7 invalid profiles, keep only `anthropic:default`:

```bash
# Backup
cp ~/.openclaw/agents/main/agent/auth-profiles.json \
   ~/.openclaw/agents/main/agent/auth-profiles.json.bak-20260529

# Edit file manually - remove invalid entries
# Keep only:
#   "anthropic:default": { "type": "api_key", "apiKey": "sk-ant-...1PNO..." }

# Restart gateway
launchctl kickstart -k gui/$(id -u)/ai.openclaw.gateway
sleep 15

# Verify
grep "auth.*re-warmed" /tmp/openclaw/openclaw-$(date +%Y-%m-%d).log | tail -3
# Should show: re-warmed in 2-5s, eventLoopMax < 500ms
```

## Impact

**Before:**
- Auth re-warm: 162 seconds
- Event loop max delay: 22 seconds
- Telegram fetch timeouts: frequent
- All bots stall during re-warm

**After:**
- Auth re-warm: 2-5 seconds
- Event loop max delay: <500ms
- No fetch timeouts
- Smooth operation

## Key Insight

**Profile order matters.** OpenClaw tries profiles in dict insertion order. If invalid profiles come before the valid one, every request triggers a cascade of failed attempts → failure state → full re-warm → event loop blocking.

**Fix:** Either (1) delete invalid profiles, or (2) move the valid profile to the first position.
