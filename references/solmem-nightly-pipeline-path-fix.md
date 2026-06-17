# SolMem Nightly Pipeline — Cron Migration Path Fix

## Problem

Cron job `OC→Hermes P0 SolMem nightly pipeline` (job ID `442faa40a734`, schedule `0 2 * * *`) fails with:
```
file_not_found: solmem_nightly_pipeline_safe.py does not exist
```

## Root Cause

When migrating OpenClaw cron jobs to Hermes scheduler, the prompt was set to run `solmem_nightly_pipeline_safe.py` — a script that was never created. The actual nightly maintenance script is `nightly_maintenance_safe.py`.

## Fix (Applied 2026-06-05)

Updated cron job prompt to:
```
python3 ~/.openclaw/workspace/scripts/nightly_maintenance_safe.py
```

The script handles: tmp cleanup, config backup, and 7 SolBrain quality gates (gbrain sync, source hygiene, inbox drain, KG dry run, freshness canary, search rank canary, entry source gate).

## Key Scripts Reference

| Script | Schedule | Purpose |
|--------|----------|---------|
| `nightly_maintenance_safe.py` | daily 02:00 | Full nightly pipeline |
| `p1p2_ops_safe.py` | various | P1/P2 health checks |
| `solmem_health_check.py` | Mon 06:00 | Weekly L1+L2+L3 |
| `solmem_doctor.py` | Mon 06:30 | Weekly L4 diagnostic |
| `mc_weekly_retro_safe.py` | Sat 05:00 | MC retrospective |

## Pattern

When migrating cron jobs between schedulers:
1. `ls -la <script-path>` — verify the script exists before updating the prompt
2. Run the script manually once to confirm it works
3. Update the cron prompt with the exact command
4. Trigger a manual run to verify the cron integration
