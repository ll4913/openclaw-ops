---
name: openclaw-ops
version: "2.0.0"
description: |
  Unified OpenClaw daily ops orchestrator: health checks, self-healing scripts,
  symptom routing to deep maintenance references, and Cursor Automation runbook.
  Use for gateway triage, ACP issues, provider config, cron, sessions, and security.
---

# OpenClaw Ops (Unified Orchestrator)

Single entry point for OpenClaw operational maintenance. Combines **executable automation** (this repo's `scripts/`) with **deep playbooks** (`references/`, synced from Hermes `openclaw-system-maintenance`).

Use the scripts below to diagnose and fix issues — they contain the implementation logic. Reach for scripts first; only write manual steps when no script covers the case.

## Start here

| Task | Read first |
|------|------------|
| **Daily / Automation run** | [daily-runbook.md](daily-runbook.md) |
| **One-shot heal** | `bash scripts/heal.sh` |
| **Install watchdog** | `bash scripts/watchdog-install.sh` |
| **Sync latest incident refs** | `bash scripts/sync-from-hermes.sh` |
| **CLI / channels / security** | [docs/](docs/) |

---

## Architecture: two layers

### Layer A — Deterministic (LaunchAgent / cron, no agent)

Already scheduled on this host:

- `scripts/watchdog.sh` — HTTP health, restart, escalate
- `scripts/heal.sh` — auth, exec approvals, crons, stuck sessions
- `~/.openclaw/workspace/scripts/nightly_maintenance_safe.py` — nightly quality gates
- `~/.openclaw/scripts/rotate-logs.sh` — log rotation

### Layer B — Intelligent review (Cursor Automation / manual)

Follow [daily-runbook.md](daily-runbook.md): run Tier 1 diagnostics, classify P0/P1/P2, open `references/` only when symptoms match.

---

## Self-healing scripts

| Script | Purpose |
|--------|---------|
| `scripts/heal.sh` | One-shot fix: gateway, auth, exec approvals, crons, sessions |
| `scripts/watchdog.sh` | Every 5 min: health ping, restart, 3-tier escalation |
| `scripts/watchdog-install.sh` | Install macOS LaunchAgent |
| `scripts/health-check.sh` | URL/process checks (`~/.openclaw/health-targets.conf`) |
| `scripts/session-monitor.sh` | Behavioral checks on live session JSONL |
| `scripts/session-search.sh` | Full-text session search (redacts secrets) |
| `scripts/session-resume.sh` | Compaction-first session resume markdown |
| `scripts/daily-digest.sh` | Incident / activity / cost summary |
| `scripts/security-scan.sh` | Config hardening score + credential scan |
| `scripts/skill-audit.sh` | Pre-install skill security vetting |
| `scripts/check-update.sh` | Post-upgrade config triage (`--fix`) |
| `scripts/fix-cli-backend.sh` | Fix `claude-cli` subprocess backend key |
| `scripts/acp_reaper.py` | ACP lease cleanup (from Hermes sync) |
| `scripts/openclaw-diag.sh` | Gateway runtime diagnostics |
| `scripts/sync-from-hermes.sh` | Pull references + Hermes scripts into this repo |

Quick setup:

```bash
bash scripts/heal.sh
bash scripts/watchdog-install.sh
bash scripts/health-check.sh --verbose
```

---

## Fix priority (health-check mode)

1. Auth — blocks all agents
2. Exec approvals — empty allowlists shadow `*` wildcard
3. Auto-disabled crons
4. Stuck sessions
5. Config errors

See [docs/troubleshooting.md](docs/troubleshooting.md) for exec approvals (two layers: allowlist + policy).

---

## Symptom router

| Symptom | Reference |
|---------|-----------|
| ACP turn timeout / transport error | [references/acp-turn-timeout-root-causes-2026-06-16.md](references/acp-turn-timeout-root-causes-2026-06-16.md) |
| Upstream / rollback branch divergence | [references/acp-upstream-reconciliation.md](references/acp-upstream-reconciliation.md) |
| Nightly maintenance timeout (124) | [references/nightly-maintenance-timeout-fix.md](references/nightly-maintenance-timeout-fix.md) |
| Provider ghost / won't delete | [references/provider-three-layer-cleanup.md](references/provider-three-layer-cleanup.md) |
| Gateway CPU / event loop degraded | [references/cpu-eventloop-starvation-may2026.md](references/cpu-eventloop-starvation-may2026.md) |
| SIGTERM storms | [references/sigterm-diagnostic-playbook.md](references/sigterm-diagnostic-playbook.md) |
| Default checkout pollution | [references/default-checkout-pollution-20260529.md](references/default-checkout-pollution-20260529.md) |
| Telegram / gateway-down delivery | [references/telegram-delivery.md](references/telegram-delivery.md) |
| Version update / cherry-pick triage | [references/cherry-pick-triage-20260529.md](references/cherry-pick-triage-20260529.md) |
| Log / session / disk maintenance | [references/ops-maintenance-improvements-20260612.md](references/ops-maintenance-improvements-20260612.md) |

Full Hermes playbook (Phase 0–13): `~/.hermes/skills/devops/openclaw-system-maintenance/SKILL.md` — sync refs via `scripts/sync-from-hermes.sh`.

---

## Reference documentation

- [docs/cli-reference.md](docs/cli-reference.md)
- [docs/troubleshooting.md](docs/troubleshooting.md)
- [docs/channel-setup.md](docs/channel-setup.md)
- [docs/security-guide.md](docs/security-guide.md)
- [https://docs.openclaw.ai](https://docs.openclaw.ai)

---

## Key paths

| Path | Purpose |
|------|---------|
| `~/.openclaw/openclaw.json` | Main config |
| `~/.openclaw/agents/<id>/` | Agent state, sessions |
| `~/.openclaw/logs/` | Gateway, watchdog, heal incidents |
| `~/.openclaw/cron/reports/` | Nightly maintenance JSON reports |
| `~/.openclaw/logs/heal-incidents.jsonl` | Heal run history |
| `~/.openclaw/logs/acp-lease-reaper.log` | ACP lease reaper |

---

## Absorbed knowledge index

### From openclaw-ops (scripts + docs)

Gateway watchdog, heal pipeline, session monitoring, security scan, CLI backend fix.

### From Hermes openclaw-system-maintenance (references/, sync)

- **2026-06-16:** [acp-turn-timeout-root-causes](references/acp-turn-timeout-root-causes-2026-06-16.md), [acp-upstream-reconciliation](references/acp-upstream-reconciliation.md), [nightly-maintenance-timeout-fix](references/nightly-maintenance-timeout-fix.md)
- **2026-06-12:** [ops-maintenance-improvements](references/ops-maintenance-improvements-20260612.md), ACP reaper, phased zombie cleanup
- **2026-05-29:** models.json hygiene, default checkout, cherry-pick triage, gateway crash after dist rebuild
- **Earlier:** CPU/event-loop case studies, SIGTERM playbook, memory architecture, keepalive watchdogs

Run `bash scripts/sync-from-hermes.sh` after Hermes skill updates.

---

## When helping users

1. Check version — v2026.2.12+ required for security fixes
2. **Daily ops:** [daily-runbook.md](daily-runbook.md) — report-first
3. **P0 only:** `heal.sh` / gateway restart — avoid config changes during active ACP turns
4. **Deep issues:** symptom router → `references/`
5. Verify after changes: `openclaw status --all`, `curl health`

Note if gateway restart is needed. Summarize in three buckets: **broken**, **fixed**, **needs manual action**.
