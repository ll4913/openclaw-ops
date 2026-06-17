# ACP Session Leak & Multi-User Worktree Isolation

Case study: 2026-05-29 — finbot ACP Claude session leaking `⚙️ Session ids resolved` diagnostic text into Telegram chat, root cause: 10 `mc-claude`-labeled sessions + incomplete per-agent `auth-profiles.json`.

## Symptom

Telegram chat shows bot replying with:
```
⚙️ Session ids resolved.
acpx session id: aebaf87e-dc5a-4b29-b613-8852a49c0c87
acpx record id: agent:claude:acp:e5d89a92-50c8-410b-af5f-1cb032727957
```

Plus `auth-profile-failure` re-warm cycles every 10-20 min in gateway logs, and silent turn failures after image/attachment delivery.

## Two Root Causes

### 1. Duplicate session labels → `sessions.resolve` ambiguity

Every `/acp spawn claude --mode persistent --bind here --cwd X --label mc-claude` creates a **new** session. The label is just metadata — it does NOT enforce uniqueness.

```bash
# Inspect
python3 -c "
import json
d = json.load(open('$HOME/.openclaw/agents/claude/sessions/sessions.json'))
by_label = {}
for k, v in d.items():
    L = v.get('label', '')
    by_label.setdefault(L, []).append((k, v.get('acp', {}).get('state')))
for L, entries in by_label.items():
    if len(entries) > 1:
        print(f'{L}: {len(entries)} sessions')
        for k, s in entries:
            print(f'  {k[:60]} state={s}')
"
```

Gateway then fails to resolve:
```
[ws] ⇄ res ✗ sessions.resolve errorCode=INVALID_REQUEST
    errorMessage=Multiple sessions found with label: mc-claude
    (agent:claude:acp:474d57b3..., agent:claude:acp:886dc19c...)
```

Agent retries, randomly picks one, leaks the diagnostic line into chat.

**Fix**: Keep only the newest session with the label, dispose the rest.

```bash
python3 << 'PY'
import json, shutil, datetime
path = '$HOME/.openclaw/agents/claude/sessions/sessions.json'
shutil.copy(path, f'{path}.bak-dedup-{datetime.datetime.now().strftime("%Y%m%d-%H%M%S")}')
d = json.load(open(path))
TARGET = 'mc-claude'  # or 'mc-claude-<accountId>' for multi-user
hits = [(k, v) for k, v in d.items() if v.get('label') == TARGET]
hits.sort(key=lambda x: x[1].get('updatedAt', 0), reverse=True)
keep, drop = hits[0], hits[1:]
print(f'KEEP: {keep[0]}')
print(f'DROP: {len(drop)}')
for k, _ in drop:
    del d[k]
json.dump(d, open(path, 'w'), indent=2)
PY
```

### 2. Per-agent `auth-profiles.json` incomplete

Each agent has its own `auth-profiles.json` under `~/.openclaw/agents/<agent>/agent/`. Finbot had only `xai:default` but its model config was:
```json
{ "primary": "openai/gpt-5.5", "fallbacks": ["xai/grok-4.3", "zai/glm-5.1", "anthropic/claude-sonnet-4-6"] }
```

Missing `openai-codex:*` and `anthropic:default` → gateway logs `provider auth state re-warmed (auth-profile-failure)` every time a turn is attempted.

**Fix**: Merge from `main` agent (which has the complete set):

```bash
python3 << 'PY'
import json, shutil, datetime
finbot_ap = '$HOME/.openclaw/agents/finbot/agent/auth-profiles.json'
main_ap   = '$HOME/.openclaw/agents/main/agent/auth-profiles.json'
ts = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
shutil.copy(finbot_ap, f'{finbot_ap}.bak.before-merge-{ts}')
fb = json.load(open(finbot_ap))
mn = json.load(open(main_ap))
merged = dict(fb.get('profiles', {}))
for k in ['openai-codex:llin@sol-m.com', 'openai-codex:lianglin4913@gmail.com',
          'anthropic:default', 'moonshot:default']:
    if k in mn['profiles'] and k not in merged:
        merged[k] = mn['profiles'][k]
fb['profiles'] = merged
json.dump(fb, open(finbot_ap, 'w'), indent=2)
# Also fix auth-state.json lastGood to point at a profile that actually exists
as_path = finbot_ap.replace('auth-profiles.json', 'auth-state.json')
as_ = json.load(open(as_path))
as_.setdefault('lastGood', {})['openai-codex'] = 'openai-codex:llin@sol-m.com'
as_.setdefault('order', {}).setdefault('anthropic', ['anthropic:default'])
json.dump(as_, open(as_path, 'w'), indent=2)
PY
```

**Pitfall**: `auth-state.json` has `lastGood.openai-codex: "openai-codex:default"` — that profile name doesn't exist in `auth-profiles.json`. Point it at an actual profile (`openai-codex:llin@sol-m.com`).

## Multi-User Isolation Pattern

When multiple Telegram users (e.g., `llin4913`, `zhangsan`) share the same bot, `/acp spawn --label mc-claude` causes cross-user label collisions AND main-checkout pollution (all users share one CWD).

### Per-user naming convention

| Dimension | Single-user | Multi-user |
|-----------|-------------|------------|
| Label | `mc-claude` | `mc-claude-<accountId>` |
| Worktree | `~/Projects/mc-worktrees/claude/` | `~/Projects/mc-worktrees/mc-claude-<accountId>/` |
| Branch | `claude/work` | `claude/<accountId>` |

### Wrapper script: `~/.openclaw/scripts/mc-spawn-claude.sh`

Subcommands: `spawn <acct>` · `cleanup <acct>` · `list` · `status <acct>`

Spawn does:
1. `mkdir -p ~/Projects/mc-worktrees`
2. If worktree exists → warn if dirty, reuse
3. Else `git worktree add -b claude/<acct> <path> origin/main`
4. Dispose any existing sessions with label `mc-claude-<acct>` (via `openclaw sessions --agent claude --label ... --dispose-all`)
5. **Print the Telegram command** — the script does NOT call `openclaw acp spawn` because `--mode persistent --bind here` are Telegram-context flags (they bind to the chat that invoked the command). The CLI `openclaw acp` subcommand doesn't accept them.

```
/acp spawn claude --mode persistent --bind here \
  --cwd /Users/lianglin/Projects/mc-worktrees/mc-claude-llin4913 \
  --label mc-claude-llin4913
```

### Why not call `openclaw acp spawn` from the wrapper?

`openclaw acp` is a bridge command that connects to the running gateway via WebSocket. It accepts `--session`, `--session-label`, `--require-existing`, `--reset-session`, `--url`, `--token`, `--provenance`. The `--mode persistent --bind here --cwd --label` flags are **Telegram slash-command arguments** parsed by the gateway's ACP plugin, not CLI flags. Mixing them up gives `OpenClaw does not recognize option "--mode"`.

The correct workflow is **CLI prepares worktree + cleans sessions, user pastes the /acp command in Telegram**.

### Cleanup subcommand

```bash
mc-spawn-claude.sh cleanup <acct>
```

1. `openclaw sessions --agent claude --label mc-claude-<acct> --dispose-all`
2. Warn if worktree has uncommitted changes or branch not merged to main
3. `git worktree remove --force` + `git branch -D claude/<acct>`

### List subcommand shows state

🟢 clean · 🟡 has commits ahead of main · 🔴 has uncommitted changes

## Verification Checklist After Fix

- [ ] `grep "Multiple sessions found" ~/Library/Logs/openclaw/gateway.log | wc -l` → 0 for the target label
- [ ] `grep "auth-profile-failure" ~/Library/Logs/openclaw/gateway.log | grep "$(date +%Y-%m-%d)" | wc -l` → 0 or decreasing
- [ ] Agent's `auth-profiles.json` has entries for every provider in its `model.primary` + `model.fallbacks`
- [ ] `lastGood` in `auth-state.json` references profile names that actually exist
- [ ] Multi-user bots: each user's spawn uses `label=<prefix>-<accountId>` and a distinct worktree path
- [ ] Gateway log location: `~/Library/Logs/openclaw/gateway.log` (LaunchAgent), NOT `~/.openclaw/logs/gateway.log` (stale)

## Anti-Patterns to Avoid

- **Sharing one label across users**: causes `Multiple sessions found` and cross-user turn hijacking
- **Pointing `--cwd` at the default checkout**: every user's agent writes to `main`, conflicts guaranteed
- **Running `/acp spawn` repeatedly without dispose**: leaks sessions, eventually all spawns fail to resolve
- **Assuming `auth-profiles.json` is shared across agents**: each agent has its own; cleaning `main` doesn't fix `finbot`
- **Assuming `lastGood` profile names match reality**: after profile renames, `lastGood` can point to a deleted profile → silent fallback to wrong credential
- **Using `~` in `--cwd`**: ACP does not expand `~`. Error: `ACP_INVALID_RUNTIME_OPTION: Working directory must be an absolute path. Received "~/Projects/..."`. Always use full path: `--cwd /Users/lianglin/Projects/...`
- **Omitting `--bind here`**: session is created but "unbound" — agent receives messages but can't reply to the chat. Error: `Session is unbound (use /acp spawn ... --bind here to bind this conversation)`. Always include `--bind here` for Telegram.

## Automatic Session Cleanup Cron

Script: `~/.hermes/scripts/acp-session-cleanup.py`
Cron: `acp-session-cleanup` (every 6h, silent when clean)

Disposes:
- All `state=error` sessions (always stale)
- `state=running` with no activity >4h (zombie)
- Duplicate labels — keeps newest, disposes rest

Reports only when issues found; silent otherwise. Manual run: `python3 ~/.hermes/scripts/acp-session-cleanup.py`.

## Agent-Enforced Worktree Isolation (For Telegram-Only Users)

Not all users have terminal access. The agent itself must enforce worktree isolation when spawned on main. Add this rule to `~/.openclaw/workspace/AGENTS.md`:

```markdown
## ACP Spawn Auto-Worktree (Multi-User Isolation)
When spawned via /acp spawn with --cwd pointing to git repo:
1. Check cwd: git branch --show-current
2. If on main/master: create worktree before any code work
3. Announce worktree location to user
4. Never modify main directly
```

**Principle**: Agent-enforced rules > user-enforced rules. AGENTS.md instructions are more reliable than user training, especially for Telegram-only users who cannot create worktrees manually.

## Complete User Command (All Required Flags)

```
/acp spawn claude --mode persistent --bind here --cwd /Users/lianglin/Projects/mission-control --label mc-claude-llin4913
```

Required flags:
- `--mode persistent` — session survives across messages
- `--bind here` — bind session to current chat (REQUIRED for Telegram)
- `--cwd /full/path` — absolute path, no `~`
- `--label mc-claude-<username>` — unique per user
