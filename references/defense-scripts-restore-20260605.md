# OpenClaw Defense Scripts Restoration — 2026-06-05

## Problem
All 7 defense scripts + 2 git-hooks were deployed on 2026-05-29 (commit `94127f9`) but only existed on `feat/silent-reply-disallow` branch, never merged to `main`. After upstream rebase/branch cleanup, they were lost from the working tree.

## Discovery
```
# Scripts not in working tree
ls scripts/check-main-clean.sh  → NOT FOUND

# But commits exist on other branches
git log --all --oneline --grep="default-checkout" → found 94127f9
git branch --all --contains 94127f9 → feat/silent-reply-disallow, fork/main
```

## Recovery Method
Extract files directly from historical commits (no cherry-pick — main has diverged 1866 commits):
```bash
# Extract from original commit
git show 94127f9da8:scripts/check-main-clean.sh > scripts/check-main-clean.sh

# For files with bug fixes, extract from the FIXED version
git show 7c0df45:git-hooks/default-checkout-guard > git-hooks/default-checkout-guard
git show 4da576f:git-hooks/post-checkout > git-hooks/post-checkout
```

## Restored Files (9 total, commit `e11309d905`)
| File | Purpose |
|------|---------|
| `scripts/check-main-clean.sh` | Verify checkout is clean/synced |
| `scripts/install-default-checkout-guard-hooks.sh` | Install pre-commit guard |
| `scripts/default-checkout-readonly-fence.mjs` | Lock/unlock checkout |
| `scripts/default-checkout-watchdog.mjs` | Periodic pollution detector |
| `scripts/protect-default-checkout-pollution.mjs` | Evidence preservation |
| `scripts/worktree-start.sh` | Create isolated worktrees |
| `scripts/agent-launcher-cwd-guard.sh` | Block write agents on default |
| `git-hooks/default-checkout-guard` | Pre-commit block on main |
| `git-hooks/post-checkout` | Block switching off main |

## New Additions (2026-06-05)

### Layer 3: Post-commit Quarantine (`git-hooks/post-commit`)
Added a quarantine hook that undoes unauthorized commits on main in the default checkout:
```bash
# Triggers when: branch=main, not worktree, no DEFAULT_CHECKOUT_ALLOW_COMMIT=1
# Action: git reset --mixed HEAD^ (preserves file changes)
# Tested: bypass=1 keeps commit, no bypass triggers reset
```

### `.gitignore` Updates (commit `f37b33b2b7`)
Added to prevent `check-main-clean.sh` from reporting dirty:
```
brain.db
dist.bak-*/
.default-checkout-fence
vpn-check.sh
```

## Architecture Note: No Husky Bypass Issue
OpenClaw uses `core.hooksPath=git-hooks` — git reads hooks directly from `git-hooks/` directory.
Unlike MC (which uses `.husky/_` and bypasses `.git/hooks/`), OpenClaw's hooks are always active.

## Smoke Test Results
- `check-main-clean.sh`: ✅ Runs (reports dirty due to brain.db/dist.bak before .gitignore fix)
- `agent-launcher-cwd-guard.sh --intent read`: ✅ Allows (exit 0)
- `agent-launcher-cwd-guard.sh --intent write`: ✅ Blocks (exit 1)
- Post-commit quarantine: ✅ Tested — `3290e6cf5c` was reset, bypass commit kept
- Node syntax check: ✅ All 3 .mjs files pass

## Push Target
`git push fork main` (fork = `ll4913/openclaw`, origin = upstream no-write)
