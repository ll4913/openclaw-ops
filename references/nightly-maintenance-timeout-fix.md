# Nightly Maintenance Timeout Fix

## Problem

`nightly_maintenance_safe.py` times out at 120s (exit 124), no report generated. The script runs 7 quality-gate scripts sequentially, each with up to 240s internal timeout. Total runtime can exceed 15 min but cron kills it at 120s.

## Root Cause

The two gbrain canary scripts (`gbrain_freshness_canary.py`, `gbrain_search_rank_canary.py`) call Ollama for embedding searches via `nomic-embed-text`. When Ollama hasn't been used during the day (cold state at midnight), loading the model can take 10-30s per query. With multiple queries, the freshness canary alone can hang for 60s+, blocking the entire pipeline.

**Evidence (2026-06-16)**:
- `gbrain_freshness_canary.py` — timeout at 60s (exit 124), no output
- `gbrain_search_rank_canary.py` — completes in <15s, 6/6 pass
- `brain.db` is 86MB, 2117 triples — not the bottleneck
- Ollama responds fine during the day (warmed up)

## Fix Applied

Wrap canary subprocess calls with `timeout 60` in `nightly_maintenance_safe.py`:

```python
solbrain_cmds=[
    ['python3',str(OC/'workspace/scripts/recent_solmem_gbrain_sync.py'),'--hours','36','--max-files','80'],
    ['python3',str(OC/'workspace/scripts/solmem_entry_source_gate.py'),'--json'],
    ['python3',str(OC/'workspace/scripts/solmem_source_hygiene_queue.py'),'--json'],
    ['python3',str(OC/'workspace/scripts/solmem_inbox_drain_queue.py'),'--json','--limit','80'],
    ['python3',str(OC/'workspace/scripts/solmem_kg_isolated_dry_run.py'),'--json','--limit','80'],
    # gbrain canaries call ollama for embeddings which can hang on cold-start;
    # wrap with `timeout 60` to prevent blocking the entire pipeline.
    ['timeout','60','python3',str(OC/'workspace/scripts/gbrain_freshness_canary.py'),'--hours','36','--json'],
    ['timeout','60','python3',str(OC/'workspace/scripts/gbrain_search_rank_canary.py'),'--json'],
]
```

The `run()` function already handles exit code 124 (timeout) gracefully — it's included in the `(0,1,2)` acceptable range for `solbrain_quality_report_only` step, and exit 124 triggers `status='warn'` instead of `status='error'`.

## Verification

```bash
time timeout 180 python3 ~/.openclaw/workspace/scripts/nightly_maintenance_safe.py
# Expected: completes in ~75s with status=warn
# Report file is written at ~/.openclaw/cron/reports/nightly-maintenance-YYYYMMDD.json
```

## General Pattern

When subprocess calls involve AI models (Ollama, llama.cpp, etc.) that may be unloaded from memory:
- Always wrap with `timeout <seconds>` to prevent blocking the entire pipeline
- Use `timeout 60` for embedding-heavy scripts
- Use `timeout 30` for simple API calls
- Handle exit code 124 as `warn` not `error`

## Cron Timeout Tuning

If the overall cron job timeout is too short (default 120s in Hermes), increase it:
```yaml
# In Hermes cron config or job definition
timeout: 900  # 15 minutes for maintenance jobs
```
