# OpenClaw Daily Ops Runbook

Used by **Cursor Automation** and manual daily reviews. Read this file first — not the full SKILL.md.

**Repo scripts dir:** `scripts/` (relative to this repo checkout)  
**Runtime home:** `~/.openclaw`

---

## Rules

1. **Report-first by default.** Do not restart gateway, edit config, or kill processes unless a P0 condition is met and the runbook explicitly allows auto-fix.
2. **Scripts before deep dives.** Run Tier 1 commands; only open `references/` when symptoms match.
3. **Layer A is already automated.** Watchdog, heal, nightly maintenance, and log rotation run via LaunchAgent/cron — do not duplicate them here unless verifying they ran.

---

## Tier 1 — Daily diagnostics (read-only)

Run all sections; collect output for the report.

### 1. Gateway health

```bash
openclaw --version
openclaw gateway status 2>/dev/null || true
curl -sf http://127.0.0.1:18789/health | python3 -m json.tool 2>/dev/null || echo "HEALTH_CHECK_FAILED"
launchctl print "gui/$(id -u)/ai.openclaw.gateway" 2>/dev/null | grep -E 'runs|last exit|state' || true
```

**P0 if:** health check fails, `runs` count jumped since yesterday (>3 restarts in 24h), or gateway process missing.

### 2. SIGTERM / config churn (ACP P0)

```bash
grep -c 'SIGTERM' ~/.openclaw/logs/gateway.log 2>/dev/null || echo 0
grep 'config.write' ~/.openclaw/logs/config-audit.jsonl 2>/dev/null | tail -5
tail -5 ~/.openclaw/logs/heal-incidents.jsonl 2>/dev/null || true
```

**P0 if:** many SIGTERM entries in last 24h while ACP sessions active.  
**Reference:** `references/acp-turn-timeout-root-causes-2026-06-16.md`

### 3. Dependency health check

```bash
bash scripts/health-check.sh --verbose 2>&1 | tail -40
```

**P1 if:** any target FAIL (not transient uptime-after-restart).

### 4. ACP / lease health

```bash
grep 'reaped\|open-but-dead' ~/.openclaw/logs/acp-lease-reaper.log 2>/dev/null | tail -15
bash scripts/session-monitor.sh 2>&1 | tail -30
```

**P1 if:** frequent `open-but-dead` Claude sessions or session-monitor incidents.

### 5. Disk & logs (quick)

```bash
du -sh ~/.openclaw/logs ~/.openclaw/agents ~/.openclaw/lcm.db 2>/dev/null
find ~/.openclaw/logs -type f -size +100M 2>/dev/null | head -5
```

**P2 if:** logs dir >2GB or single log >500MB.

### 6. Nightly maintenance report

```bash
ls -t ~/.openclaw/cron/reports/nightly-maintenance-*.json 2>/dev/null | head -1 | xargs cat 2>/dev/null | python3 -m json.tool 2>/dev/null | head -40
```

**P1 if:** latest report missing, status=error, or exit 124 without warn handling.  
**Reference:** `references/nightly-maintenance-timeout-fix.md`

---

## Tier 2 — Weekly (or when Tier 1 shows P1+)

```bash
bash scripts/daily-digest.sh --hours 168
bash scripts/security-scan.sh 2>&1 | tail -30
python3 scripts/acp_reaper.py --dry-run 2>/dev/null || true
openclaw doctor 2>&1 | tail -20
```

---

## Tier 3 — Deep maintenance (monthly / on incident)

Full audit: Hermes `openclaw-system-maintenance` Phase 0–8.  
Sync latest references first:

```bash
bash scripts/sync-from-hermes.sh
```

Upstream / rollback branch audit: `references/acp-upstream-reconciliation.md`

---

## Symptom router

| Symptom | Reference |
|---------|-----------|
| ACP turn timeout / transport failure | `references/acp-turn-timeout-root-causes-2026-06-16.md` |
| Production branch diverged from upstream | `references/acp-upstream-reconciliation.md` |
| Nightly maintenance exit 124 | `references/nightly-maintenance-timeout-fix.md` |
| Provider won't delete / ghost in /models | `references/provider-three-layer-cleanup.md` |
| Gateway 100% CPU / event loop degraded | `references/cpu-eventloop-starvation-may2026.md` |
| Exec approval loops | `docs/troubleshooting.md` + SKILL.md § Exec Approvals |
| Telegram / channel delivery | `docs/channel-setup.md`, `references/telegram-delivery.md` |
| SIGTERM storms | `references/sigterm-diagnostic-playbook.md` |

---

## Report format (required output)

```markdown
## OpenClaw Daily Ops — YYYY-MM-DD

### Summary
One paragraph: overall status OK / WARN / P0

### Tier 1 results
- Gateway: ...
- SIGTERM/config: ...
- Health-check: ...
- ACP/leases: ...
- Disk/logs: ...
- Nightly report: ...

### Classification
| Priority | Items |
|----------|-------|
| P0 | ... |
| P1 | ... |
| P2 | ... |

### Recommended actions
1. ...

### Auto-fix applied
None (default) | list commands run
```

---

## Allowed auto-fix (P0 only)

Only when gateway is down AND heal is safe:

```bash
bash scripts/heal.sh
openclaw gateway restart
sleep 6
curl -sf http://127.0.0.1:18789/health
```

Do **not** run `openclaw config set` during an active ACP conversation window.
