# P1/P2 Ops Safety Script — Quick Reference

Absorbed from `p1p2-ops-safety` skill (consolidated 2026-06-05).

Safe deterministic wrappers for OpenClaw P1/P2 cron jobs.

## Script

```
~/.openclaw/workspace/scripts/p1p2_ops_safe.py
```

## Usage pattern

```bash
python3 ~/.openclaw/workspace/scripts/p1p2_ops_safe.py <mode> --dry-run  # dry-run (no side effects)
```

Available modes: `system-health`, `solmem-health`, `gateway-health`, `cache-warmup`, `mc-qa`, `qmd-refresh`, `async-memory`, `mc-backup`, `gateway-lifecycle`

## Parsing stdout JSON

**MUST parse stdout as JSON.** The script emits structured output on every run.

```json
{
  "status": "ok|warning|error",
  "mode": "...",
  "report_path": "/Users/lianglin/.openclaw/cron/reports/p1p2-<mode>-<timestamp>.json",
  "steps": [...],
  "duration_s": ...,
  "dry_run": true/false
}
```

## Exit code conventions (CRITICAL)

| exit_code | maps to status | meaning |
|------|-------|---|
| 0    | `ok`      | All steps passed |
| 124  | `warning` | Timeout — parent killed subprocess, NOT a critical error |
| 2    | `warning` | Non-critical failure (e.g., no manifest found) |
| 1    | `error`   | Unexpected/unknown error |

**Key pitfall**: A 120s timeout (exit_code=124) is deliberately classified as `warning`, not `error`. The script wraps subprocess runs in a 120s timeout and returns exit_code=124 which gets mapped to `'warning'` in the calling mode function. **Do not auto-alert on timeout — follow the script's own status field.**

## Delivery rules (cron jobs)

- **status = `ok`**: Do NOT send Telegram. Final response: `OK report_path=<path>`
- **status = `warning` or `error`**: Final response includes ≤2500 chars with mode, status, failed step summaries, and report_path. Hermes cron auto-delivers this to the configured Telegram target via the `deliver` field — **the agent NEVER manually calls Telegram delivery tools** (no `openclaw agent --deliver`, no raw Bot API curl, no `send_message` tool). The system handles delivery.
- **Always write report** to `~/.openclaw/cron/reports/` with filename pattern `p1p2-<mode>-<YYYYMMDD-HHMMSS>.json`

## Delivery Pitfalls

### Hermes cron vs OpenClaw cron delivery
- **Hermes cron**: Auto-delivers final response to Telegram. Just produce the alert text as your final response; Hermes delivers it.
- **OpenClaw cron** (legacy): Used `openclaw agent --deliver --channel telegram`. Only relevant inside OpenClaw ecosystem.
- **Direct delivery via OpenClaw CLI**: `openclaw message send --channel <channel_name> --target <target> --message "text"`. Verified working.
- `send_message` tool does NOT exist in cron context — only available when Hermes gateway is active.

### Cron PATH does not include /opt/homebrew/bin
macOS cron uses minimal PATH (`/usr/bin:/bin`). If a P1/P2 script calls `openclaw` CLI, it fails with `FileNotFoundError`. The `openclaw` binary lives at `/opt/homebrew/bin/openclaw`.

**Fix:** Use absolute path `/opt/homebrew/bin/openclaw` in the script, or add `PATH=/opt/homebrew/bin:/usr/bin:/bin` at the top of the crontab.

**Known affected:** EMEA AR Daily Report (`emea_ar_telegram_report.py:227`).

### Gateway-down delivery deadlock
When the `openclaw_status` step fails (gateway unresponsive), **all subsequent `openclaw message send` commands will ALSO hang/timeout** because the CLI routes through the same gateway process.

**Mitigation**: If `openclaw_status` fails, do NOT attempt `openclaw message send`. Just produce a complete report as your final response (Hermes cron auto-delivers it). For programmatic Telegram delivery when the gateway is down, use raw `curl` to the Telegram Bot API directly. See `telegram-delivery.md` and `gateway-down-delivery-bypass.md`.

## Failed step summary

```json
{
  "steps": [
    {"step": "async_memory", "ok": false, "error": "...", "detail": {"exit_code": 124, "stderr_tail": "timeout"}},
    ...
  ]
}
```

Extract `step` and `error` from any step where `ok == false` for alert content.

## Gateway-health specifics

`gateway-health` should not rely on `openclaw gateway status` alone: a half-hung Gateway may still return HTTP `/health` and pass the lightweight status probe while `channels status` reports event-loop degradation or Telegram transport/RPC instability. Include `openclaw channels status --timeout 30000` in manual verification and prefer wrapper logic that marks `event loop degraded`, connectivity probe failure, or timeout text as `warning`.

If `gateway-health` fails because `openclaw gateway status` reports missing `dist/entry.(m)js` or another runtime artifact, follow `gateway-health-build-restart.md`: first check whether this is a transient rebuild window, retry once, then build artifacts from `/Users/lianglin/openclaw` only if files remain missing.

## Async-memory runtime note

`async-memory` mode requires PTY terminal I/O (Gemini API calls); hangs without PTY in Hermes cron. Keep under OpenClaw cron or use PTY-enabled Hermes session.
