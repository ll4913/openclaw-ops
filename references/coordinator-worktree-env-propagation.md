# Coordinator Worktree Env Propagation Pitfall

## Pattern

When automation creates a clean `git worktree` from `origin/main` (coordinator worktree pattern), **gitignored files like `.env.local` are NOT copied**. Any script that depends on these files will fail with "missing credentials" errors.

## MC Dashboard Refresh Case (2026-06-01)

`scripts/dashboard-refresh-scheduled.sh` creates a coordinator worktree:
```bash
git worktree add "$coord" -b "$branch" origin/main
```

Then `scripts/dashboard-refresh-worktree.sh` → `load_env()` looks for `$repo_root/.env.local` — but `$repo_root` now points to the temporary worktree (`/private/tmp/mc-dashboard-scheduled-*`), which doesn't have `.env.local`.

**Error**: `ERROR: missing PBI env; expected .env.local or PBI_TENANT_ID/PBI_CLIENT_ID/PBI_CLIENT_SECRET in the environment`

**Fix** (commit `dbe518e0`): Source `.env.local` from the original repo before running publisher:
```bash
# In run_from_coordinator(), before run_publisher:
if [[ -f "$REPO/.env.local" ]]; then
  set -a
  source "$REPO/.env.local"
  set +a
fi
```

## General Rule

Any automation that:
1. Creates a `git worktree add` from a clean branch
2. Runs scripts that source `$repo_root/.env.local` or similar gitignored config
3. Does NOT explicitly propagate env from the original checkout

...will fail. Always source env from the original repo (`$REPO`), not from `$repo_root` (which resolves to the worktree).

## LaunchAgent Schedule Conflicts

When multiple LaunchAgents fire at the same time and share a lock file (e.g., `dashboard-data-auto-publish.lock.d`), the second one fails with:
```
ERROR: another dashboard data publish appears to be running
```

**Fix**: Stagger LaunchAgent `StartCalendarInterval` by 15 minutes. Example: forecast moved from 09:00 to 09:15 to avoid collision with latam at 09:00.

Reload after plist change:
```bash
launchctl unload ~/Library/LaunchAgents/com.solm.forecast-refresh.plist
launchctl load ~/Library/LaunchAgents/com.solm.forecast-refresh.plist
```
