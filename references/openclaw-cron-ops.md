# OpenClaw Cron Operations

## Health Check Pattern (p1p2)

Cron jobs like `p1p2_ops_safe.py` output JSON with `status`: `ok`, `warning`, or `error`.

```bash
python3 ~/.openclaw/workspace/scripts/p1p2_ops_safe.py <task-name>
```

Parse stdout as JSON. Status determines action:
- **ok**: Silent. Final response: `OK report_path=<path>`. No Telegram.
- **warning/error**: Send Telegram alert to the target specified in the cron definition.

## Telegram Alert Delivery

Use `hermes send` (no gateway or LLM loop required):

```bash
hermes send --to telegram:<chat_id_or_handle> --subject "[<TAG>]" "<message>"
```

Or via stdin:
```bash
echo "<message>" | hermes send --to telegram:<chat_id_or_handle>
```

Chat target format from cron definitions: `telegram:8524721791` — pass exactly that to `--to`.

### Alert template

```bash
hermes send --to telegram:<chat_id> \
  --subject "[<TASK>]" \
  "⚠️ <TASK>: WARNING
<failed_step_summaries>

Passed: <passed_steps>
Report: <report_path>"
```

### Pitfalls

- Keep messages <= 2500 chars for cron alerts (Telegram limit is 4096 but leave margin).
- Never print secrets (API keys, tokens, passwords).
- In cron jobs, `hermes send` may emit "Skipped send_message" — put alert in final response instead.
- `hermes send --to telegram:<chat_id>` is preferred. `openclaw message send` is more complex.
- Cron auto-delivers agent's final response. If status is `ok`, respond with `OK report_path=<path>`.
- Always include failed step names, counts/ages, and report path in alerts.

## Report Location

Reports land in `~/.openclaw/cron/reports/`. Filenames: `<task>-<YYYYMMDD>-<HHMMSS>.json`.

## Cron Schedule Management

```bash
openclaw cron list        # List all scheduled tasks
openclaw cron show <id>   # Show task details
openclaw cron rm <id>     # Remove a task
```

## Common Tasks

1. Run a health check: `python3 ~/.openclaw/workspace/scripts/p1p2_ops_safe.py <name>`
2. Parse results: `| python3 -c "import sys,json; print(json.dumps(json.load(sys.stdin),indent=2))"`
3. Review report: `cat ~/.openclaw/cron/reports/<filename>.json`
4. Send alert: See Telegram section above.
