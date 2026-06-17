# ACP Upstream Reconciliation Audit

When production runs on a diverged branch (rollback/feature stack) with N unique fixes not in upstream, this procedure audits the full divergence and prepares reconciliation.

## 5-Dimensional Audit Model

Always collect ALL five dimensions before proposing action:

### 1. Git History
```bash
# Count unique commits not in upstream
git log --oneline <branch> --not origin/main | wc -l

# Categorize by type
git log --oneline <branch> --not origin/main | grep -c "^.*fix(acp)"
git log --oneline <branch> --not origin/main | grep -c "^.*fix(telegram)"
git log --oneline <branch> --not origin/main | grep -c "^.*feat"
git log --oneline <branch> --not origin/main | grep -c "^.*docs"

# List with file stats
git log --stat --oneline <branch> --not origin/main
```

### 2. Operational Scripts (Reapers, Archives, Wrappers)
```bash
# Find all ACP-related scripts
find ~/.openclaw/scripts ~/.openclaw/workspace/scripts ~/.hermes/scripts \
  -name '*acp*' -o -name '*reaper*' -o -name '*archive*' -o -name '*wrapper*' \
  -o -name '*zombie*' -o -name '*lease*' 2>/dev/null | sort

# For each: check creation date, purpose, scheduling status
for f in $(find ...); do
  echo "=== $f ==="
  stat -f "%SB" "$f"  # created
  head -5 "$f"        # purpose
done
```

### 3. Launchd Services
```bash
# List all ACP-related plists
launchctl list | grep -i 'acp\|openclaw\|solm'

# For each: check schedule, last exit, PID
for plist in ~/Library/LaunchAgents/com.solm.acp-* ~/Library/LaunchAgents/ai.openclaw.*; do
  echo "=== $(basename $plist) ==="
  plutil -p "$plist" | grep -E 'StartInterval|StartCalendar|LastExit|PID'
done
```

### 4. Source Modifications (Uncommitted)
```bash
git status --short
git diff --stat
```

### 5. Session/Lease Health
```bash
# Check for broken sessions
cat ~/.openclaw/sessions.json | python3 -c "..."
# Check lease table
cat ~/.openclaw/acpx/process-leases.json | python3 -c "..."
```

## Cherry-Pick Conflict Ratio Assessment

**Before committing to a cherry-pick PR strategy**, always calculate the conflict ratio:

```bash
MERGE_BASE=$(git merge-base <our-branch> origin/main)

# Files we changed
OUR_FILES=$(git log --name-only --format="" <our-branch> --not origin/main | sort -u)
OUR_COUNT=$(echo "$OUR_FILES" | wc -l | tr -d ' ')

# Files upstream also changed since merge-base
UPSTREAM_FILES=$(git diff --name-only "$MERGE_BASE" origin/main | sort -u)

# Files in BOTH sets (conflict risk)
CONFLICT_FILES=$(comm -12 <(echo "$OUR_FILES") <(echo "$UPSTREAM_FILES"))
CONFLICT_COUNT=$(echo "$CONFLICT_FILES" | grep -c . || echo 0)

echo "Our files: $OUR_COUNT"
echo "Conflict-risk files: $CONFLICT_COUNT"
echo "Ratio: $CONFLICT_COUNT/$OUR_COUNT"
```

### Decision thresholds

| Conflict Ratio | Strategy |
|---|---|
| <25% | Cherry-pick is viable — proceed commit by commit |
| 25-50% | Cherry-pick with batch `--no-commit` per PR group — resolve conflicts in bulk |
| >50% | **Cherry-pick is impractical.** Consider: squash-merge entire branch, interactive rebase onto main, or accept fork divergence with periodic rebase |
| >75% | The branches have fundamentally diverged. Fork reconciliation requires manual porting of logic, not git operations |

### Why this matters

- 40 commits × 151 files × 79% conflict ratio = ~100+ individual conflict resolutions
- Each conflict resolution requires understanding both upstream intent AND local fix semantics
- At >50% ratio, the cost of cherry-picking exceeds the cost of alternative strategies

## Rollback Branch Divergence Detection

Production may silently run on a diverged branch. Signs:

1. `git log --oneline HEAD --not origin/main` shows N commits
2. Gateway process is running from `dist/` built from the diverged branch
3. `remotes/live/main` (if exists) points to the diverged branch, not origin/main
4. The diverged branch name contains "rollback" or a date suffix

**Risk**: If production is on a rollback branch, switching to `origin/main` loses all N fixes. Always confirm production's actual running branch before any checkout/reset.

## Reaper Inventory Overlap Analysis

When multiple reapers exist with overlapping scope, map them:

| Reaper | Covers | Schedule | Gap |
|---|---|---|---|
| lease-reaper | lease table only | 30min | No process cleanup |
| zombie-reaper | gateway children | cron | No MCP/LSP |
| comprehensive-reaper | all 7 phases | **unscheduled** | None |
| session-gc | session files | profile cron | No process/lease |

**Key finding**: The most comprehensive reaper (7-phase) is often unscheduled. Always check `launchctl list` AND `crontab -l` for each reaper script before assuming it runs.

## Structured Report Format

Present findings as:

```
## P0 — [Issue]
- Evidence: [specific commands/data]
- Impact: [what breaks if not fixed]

## P1 — [Issue]
- Evidence: ...

## P2 — [Issue]
- Evidence: ...

## Action Items Table
| Priority | Action | Impact |
|---|---|---|
| P0 | ... | ... |
```

Always include a timeline showing when each fix was introduced to help trace the evolution.
