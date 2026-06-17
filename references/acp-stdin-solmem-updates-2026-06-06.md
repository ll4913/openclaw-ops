# ACP Codex stdin Closure + SolMem Maintenance Updates (2026-06-06)

## ACP Codex stdin Closure Bug

**Symptom:** Long-running ACP Codex sessions (2+ hours) suddenly stop responding mid-task. Agent appears active (PID alive, `closed: false`) but produces no further output or tool calls.

**Root cause:** `codex_core::tools::router` loses its stdin pipe:
```
ERROR codex_core::tools::router: error=write_stdin failed: stdin is closed 
for this session; rerun exec_command with tty=true to keep stdin open
```

**Where to find the error:** `~/.openclaw/acpx/codex-acp-wrapper.stderr.<lease-id>.log`

**Impact:** Agent abandons mid-task without user-visible error. Work may be partially done in a worktree but never committed or delivered.

**Real case (2026-06-06):** SolBI's ACP Codex was implementing "BU Revenue by Business Model" view. It created a worktree, ran GitNexus impact checks, started editing `page.tsx` (176 lines of diff), then stdin closed at 18:49 UTC. Session showed `closed: false`, PID 81513 still alive. User saw "not available yet" because partial work was never committed.

**Diagnosis:**
```bash
# Check stderr log for stdin closure
cat ~/.openclaw/acpx/codex-acp-wrapper.stderr.<lease-id>.log | grep stdin

# Check session state — closed:false + live PID can still be dead
cat ~/.openclaw/workspace/state/sessions/agent%3Acodex%3Aacp%3A<id>.json | python3 -c "
import sys, json; d=json.load(sys.stdin)
print(f'Closed: {d.get(\"closed\")}')
print(f'Last used: {d.get(\"last_used_at\")}')
print(f'Messages: {len(d.get(\"messages\",[]))}')"

# Check worktree for uncommitted partial work
cd /private/tmp/mc-<task>-<timestamp>/ && git status --short
```

**Workaround:** Kill the stuck ACP process and re-spawn with a fresh session. Break long tasks into smaller ACP sessions to stay under the ~2h threshold. No upstream fix exists for the stdin closure.

**Pitfall:** Don't trust `closed: false` as proof of a healthy session. Always check the last message content and worktree state when investigating "agent didn't complete the task."

---

## SolMem Nightly Pipeline — Correct Script Path

The Hermes cron `OC→Hermes P0 SolMem nightly pipeline` (job `442faa40a734`) was misconfigured after OpenClaw→Hermes migration. The prompt referenced a non-existent `solmem_nightly_pipeline_safe.py`.

**Correct script:** `~/.openclaw/workspace/scripts/nightly_maintenance_safe.py`

This script runs 7 SolBrain quality gates:
1. `recent_solmem_gbrain_sync.py` — sync new SolMem entries to GBrain
2. `solmem_entry_source_gate.py` — validate source/title/AAAK coverage
3. `solmem_source_hygiene_queue.py` — queue missing-source fixes
4. `solmem_inbox_drain_queue.py` — promote/archive stale inbox files
5. `solmem_kg_isolated_dry_run.py` — detect KG gaps
6. `gbrain_freshness_canary.py` — verify GBrain search freshness
7. `gbrain_search_rank_canary.py` — verify search ranking quality

Also handles: tmp cleanup (known prefixes >7d), config backup, disk monitoring.

---

## SolMem Auto-Commit Batch Mode

The SolMem auto-commit launchd service (`com.solm.solmem-auto-commit`) was producing ~77 commits/day with 30-second debounce.

**Changes made (2026-06-06):**

1. **Debounce: 30s → 1800s (30 min)** — `DEBOUNCE_SECS=1800` in `solmem-auto-commit.sh`. Expected: 77 → 24-48 commits/day.

2. **changelog.jsonl** — Per-file entries with category classification:
   ```json
   {"ts":"2026-06-05T14:00:00Z","action":"auto-commit","category":"lesson","file":"lessons/xxx.md","label":"solmem"}
   ```
   Categories: lesson, decision, concept, entity, audit, inbox, meeting, knowledge, config, infrastructure, other.

3. **Category-aware commit messages** — Messages now include summary: `[lesson:2, decision:1]`

**Reload after changes:**
```bash
launchctl kickstart -k gui/$(id -u)/com.solm.solmem-auto-commit
```

---

## "Canary Passed but Feature Missing" Diagnostic

When users report features not visible despite canary passing:

1. **Verify server is serving latest release:**
   ```bash
   readlink ~/Projects/mission-control/.mc-current  # should point to latest release
   cat .mc-releases/$(basename $(readlink .mc-current))/release.json
   ```

2. **Check server CWD matches:**
   ```bash
   lsof -p <server-pid> | grep cwd
   ```

3. **Verify feature commit is in origin/main:**
   ```bash
   git branch -r --contains <commit>
   git log --all --oneline --grep="<feature keyword>"
   ```

4. **Check if feature was actually implemented:**
   ```bash
   grep -rn "<feature keyword>" app/ components/ --include="*.tsx"
   ```

**Root cause is usually one of:**
- Feature commit not merged to origin/main (still on branch)
- Agent only did partial work (e.g., removed a column instead of adding a view)
- ACP session crashed mid-implementation (see stdin closure bug above)
- Data export not refreshed (JSON file lacks new fields)
