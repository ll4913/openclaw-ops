# Gateway-Down Delivery: Bot Token Extraction & Raw Curl Pattern

Absorbed from `gateway-down-delivery-deadlock` (consolidated 2026-05-29).

## The Non-Problem

There is NO true deadlock. When the OpenClaw gateway is unresponsive:
- `openclaw status` / `openclaw message send` / `openclaw agent` ALL hang — CLI routes through gateway
- Raw Telegram Bot API via `curl` ALWAYS works — bypasses gateway entirely

## Workaround Hierarchy

1. **If status = `ok`**: Produce final response; Hermes cron auto-delivers.
2. **If warning/error AND `openclaw_status` passed**: Use `openclaw message send --channel telegram --target ...`
3. **If `openclaw_status` FAILED**: Produce full alert as final response text (Hermes cron auto-delivers). No bypass needed.
4. **For automated/deterministic delivery when gateway is down**: Extract bot token from `~/.openclaw/openclaw.json` and use raw curl.

## Bot Token Location

**There is NO `TELEGRAM_BOT_TOKEN` env var** in OpenClaw cron environments.

Tokens live in: `~/.openclaw/openclaw.json → channels.telegram.accounts.<account_name>.botToken`

Available accounts: `default`, `solbi`, `solcotton`, `mailbot`, `engineer`, `tenderbot`, `legal`, `hrbot`, `opsbot`, `bubot`, `productbot`, `finbot`, `fashionbot`, `sc-engineer`.

Use `default` account for general alerts.

## Raw Curl Pattern

```python
import json, pathlib, subprocess

# Extract token
config = json.loads((pathlib.Path.home() / '.openclaw/openclaw.json').read_text())
token = config['channels']['telegram']['accounts']['default']['botToken']

# Send message
subprocess.run([
    'curl', '-s', '-X', 'POST',
    f'https://api.telegram.org/bot{token}/sendMessage',
    '-H', 'Content-Type: application/json',
    '-d', json.dumps({
        'chat_id': '<TARGET_CHAT_ID>',
        'text': '<ALERT_TEXT>',
        'parse_mode': 'Markdown'
    })
], capture_output=True, timeout=10)
```

## Key Rules

- Never attempt `openclaw message send` when gateway is down — wastes minutes
- `send_message` tool does NOT exist in cron context
- The bot token is NOT in env vars — always parse from openclaw.json
- Mask tokens in logs (replace with `***` after first 8 chars)
