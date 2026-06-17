# Keepalive Watchdog Architecture — 2026-05-29

## Overview

Two LaunchAgent watchdogs keep OAuth tokens fresh for ACP agent dependencies:

| Watchdog | Plist | Script | Frequency |
|----------|-------|--------|-----------|
| Claude OAuth | `com.solm.claude-oauth-keepalive` | `claude-oauth-keepalive.sh` | Every 3600s (1h) |
| OpenAI Codex OAuth | `com.solm.openai-codex-oauth-keepalive` | `openai-codex-oauth-keepalive.sh` | Every 3600s (1h) |

## Claude OAuth Keepalive

**Tests two accounts:**
- **Account A (Keychain)**: Interactive Claude.ai OAuth via `claude auth status` + smoke test
- **Account B (Token)**: Dedicated automation token for pipeline-opus-review.py

**Mechanism:**
1. Checks if recent OK exists (min interval 900s)
2. Runs `claude auth status` for Account A
3. Runs smoke test: `claude -p "Say OPENCLAW_OAUTH_KEEPALIVE_OK"`
4. Tests Account B token via pipeline script
5. Writes state to `~/.openclaw/logs/claude-oauth-keepalive-state.json`
6. Sends Telegram notification on failure (with 3600s suppression)

**Self-healing observed:** Account A had 15 consecutive 401 failures (19:53-20:29), then auto-recovered at 20:46. Claude Code's internal refresh mechanism handled token renewal.

**Smart diagnostics:** The `suggest_fix()` function distinguishes:
- dyld/library breakage → suggests brew reinstall, NOT token re-mint
- auth method mismatch → suggests `claude auth login --claudeai`
- token expired → suggests re-mint
- timeout → suggests network/model check

## OpenAI Codex OAuth Keepalive

**Mechanism:**
1. Runs `codex exec` with smoke test prompt
2. Forces OAuth token refresh path
3. Checks for sentinel `OPENCLAW_CODEX_KEEPALIVE_OK` in output
4. Handles non-zero exit codes (Codex can exit non-zero on child process kill)

**Reliability:** 28+ hours of consecutive OK with zero failures observed.

## Key Files

| File | Purpose |
|------|---------|
| `~/Library/LaunchAgents/com.solm.claude-oauth-keepalive.plist` | LaunchAgent definition |
| `~/Library/LaunchAgents/com.solm.openai-codex-oauth-keepalive.plist` | LaunchAgent definition |
| `~/.openclaw/workspace/scripts/launchd/claude-oauth-keepalive.sh` | Claude watchdog script (~250 lines) |
| `~/.openclaw/workspace/scripts/launchd/openai-codex-oauth-keepalive.sh` | Codex watchdog script (~130 lines) |
| `~/.openclaw/logs/claude-oauth-keepalive.log` | Main Claude log |
| `~/.openclaw/logs/openai-codex-oauth-keepalive.log` | Main Codex log |
| `~/.openclaw/logs/*-keepalive-state.json` | Last known state |
| `~/.claude/.credentials.json` | Claude OAuth tokens (accessToken + refreshToken) |

## Monitoring

```bash
# Check state
cat ~/.openclaw/logs/claude-oauth-keepalive-state.json
cat ~/.openclaw/logs/openai-codex-oauth-keepalive-state.json

# Check recent runs
tail -10 ~/.openclaw/logs/claude-oauth-keepalive.log
tail -10 ~/.openclaw/logs/openai-codex-oauth-keepalive.log

# Check LaunchAgent status
launchctl print gui/$(id -u)/com.solm.claude-oauth-keepalive 2>&1 | grep -E "last exit|runs"
launchctl print gui/$(id -u)/com.solm.openai-codex-oauth-keepalive 2>&1 | grep -E "last exit|runs"
```

## Important Notes

- **Claude OAuth tokens auto-refresh**: The `~/.claude/.credentials.json` accessToken may show "expiring soon" but Claude Code handles refresh internally during the keepalive smoke test.
- **Notification suppression**: Failures within 3600s of each other don't generate duplicate Telegram alerts.
- **Lock files**: Both scripts use `~/.openclaw/run/*.lock` directories to prevent concurrent runs.
- **Clean env**: Claude watchdog strips all `ANTHROPIC_*` and `CLAUDE_*` env vars before testing, ensuring each account uses its own credential path.
