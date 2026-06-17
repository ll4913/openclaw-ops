# Dashboard Refresh Coordinator Worktree — PBI Env Fix (2026-06-01)

## Problem

All scheduled dashboard refreshes (`dashboard-refresh-scheduled.sh`) failed with:
```
ERROR: missing PBI env; expected .env.local or PBI_TENANT_ID/PBI_CLIENT_ID/PBI_CLIENT_SECRET
```

## Root Cause Chain

1. `dashboard-refresh-scheduled.sh` creates a clean **coordinator worktree** at `/private/tmp/mc-dashboard-scheduled-<region>-*` based on `origin/main`
2. The worktree runs `dashboard-data-auto-publish.sh` → `dashboard-refresh-worktree.sh`
3. `dashboard-refresh-worktree.sh:81` uses `git rev-parse --show-toplevel` → `$repo_root` points to the temp worktree
4. `load_env()` (line 153) looks for `$repo_root/.env.local` — but `.env.local` is **gitignored**, not copied by `git worktree add`
5. launchd environment also lacks PBI variables → check fails → exit 1

**Introduced**: commit `e70806e1` (2026-05-29) — `fix(dashboard): run scheduled refresh from clean coordinator`. The coordinator worktree pattern was added but env propagation was missed.

## Fix Applied

In `run_from_coordinator()`, before `run_publisher "$coord"`:
```bash
if [[ -f "$REPO/.env.local" ]]; then
  set -a
  source "$REPO/.env.local"
  set +a
fi
```

This sources PBI credentials from the original repo into the shell environment, so `load_env()` passes via env vars even without `.env.local` in the worktree.

## Concurrent Fix

Forecast refresh (`com.solm.forecast-refresh.plist`) and LATAM both scheduled at 09:00 caused lock file collision:
```
ERROR: another dashboard data publish appears to be running
```

**Fix**: Changed forecast schedule from 09:00 → 09:15 in `com.solm.forecast-refresh.plist`, reloaded LaunchAgent.

## LaunchAgent Schedule (post-fix)

| Time | Region |
|------|--------|
| 08:00 | HQ |
| 08:15 | APAC |
| 08:30 | NACA |
| 08:45 | EMEA |
| 09:00 | LATAM |
| 09:15 | Forecast (1st & 15th) |
| 14:00–15:00 | Same pattern PM |

## Verification

```bash
# Dry run (skips PBI queries)
bash scripts/dashboard-refresh-scheduled.sh --region naca --dry-run
tail -10 ~/.openclaw/logs/mc-dashboard-refresh.log

# Real run
bash scripts/dashboard-refresh-scheduled.sh --region forecast
# Check log for: PBI queries OK, scenarios generated, candidate committed, merge completed
```

## Lesson

When introducing coordinator worktrees that need secrets/credentials:
- `.env.local` and other gitignored files don't propagate
- Source them from the original repo into the shell environment before entering the worktree
- Check for lock file collisions when scheduling concurrent LaunchAgent jobs
