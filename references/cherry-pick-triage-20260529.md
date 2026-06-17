# Cherry-Pick Triage Session — v2026.5.27 (2026-05-29)

## Context

After upgrading OpenClaw to v2026.5.27, we had 9 local branches + 5 stashes from ~v2026.5.18-5.22 era patches. The upstream release covered many of the issues these patches addressed. This documents the systematic triage process and results.

## Branch Inventory

| Branch | Commits | Files | Base Version | Content |
|--------|---------|-------|--------------|---------|
| `main-upstream` | 0 | — | v2026.4.19 | Old upstream snapshot |
| `codex/openclaw-event-loop-degraded` | 134 | 252 | v2026.5.22β | Event-loop pressure relief + diagnostics |
| `codex/acp-telegram-resilience-20260525` | 127 | 244 | v2026.5.22β | ACP delivery stalls, agent yield points, compaction budgets |
| `codex/openclaw-agent-stability-20260525` | 105 | 155 | v2026.5.22β | Long turn stabilization, Telegram preview sanitize |
| `local/acp-enhancements-20260520` | 148 | 297 | v2026.5.22β | Kitchen-sink superset of above |
| `local/main-telegram-fixes-20260529` | 14 | 21 | v2026.5.18 | Draft stream, progress visibility, delivery receipts |
| `fix/telegram-acp-visible-watchdog` | 1 | 9 | v2026.5.18 | ACP visible progress enforcement (+411 lines dispatch-acp.ts) |
| `codex/openclaw-acp-bound-labels-20260520` | 1 | 3 | v2026.5.20 | ACP status labels from bound sessions |
| `codex/openclaw-acp-status-output-20260520` | 2 | 4 | v2026.5.20 | ACP status output simplification |
| `feat/silent-reply-disallow` | 3 | 9 | v2026.5.27 | Silent reply disallow + ACP session fallback (rebased to main) |
| `backup/*` (2 branches) | — | — | various | Historical backups |

## Triage Results

### 🗑️ Discarded (5 items)

| Item | Reason |
|------|--------|
| `main-upstream` | Fully absorbed into local main |
| `codex/openclaw-event-loop-degraded` | Core issues (#86123, #86816, gateway caching) fixed in v5.27 |
| `stash@{2}` (ACP watchdog WIP) | Evolved into `fix/telegram-acp-visible-watchdog` |
| `stash@{3}` (gateway startup) | v5.27 restructured gateway startup entirely |
| `stash@{4}` (canvas hash) | Trivial, 1-line change |

### ✅ Successfully Cherry-Picked (2 fixes)

| Commit | Source | Files | What it does |
|--------|--------|-------|--------------|
| `88eaf1d` fix(tasks): reconcile completed deferred maintenance | acp-telegram-resilience | 2 (+142/-6) | Prevents stale task registry accumulation |
| `8124835` fix(acp): dedupe concurrent delivery mirrors | agent-stability | 2 (+43) | Prevents duplicate transcript entries |

### ❌ Cherry-Pick Aborted (6 attempts)

| Commit | Reason |
|--------|--------|
| `8f7b8907` transcript byte compaction | **v5.27 already has `shouldCompactByTranscriptBytes`** with better implementation |
| `4985c06b` stalled ACP ingress claim recovery | `transport-errors.ts` deleted in v5.27, architecture changed |
| `d4707e1e` cursor binding labels aligned | `dispatch-acp.ts` conflicts with `feat/silent-reply-disallow` (+400 lines) |
| `7a0152d2` stagger channel startup | Gateway restructured in v5.27 |
| `75736ec2` long turn stabilization | 4 file conflicts (MCP runtime, model diagnostics) |
| `5a6d9d27` low-level delivery mirrors | Depends on already-picked concurrent mirrors commit |

### 🟢 Kept (5 branches — after coordination decision)

| Branch | Reason |
|--------|--------|
| `local/main-telegram-fixes-20260529` | Latest Telegram delivery mechanics, not in v5.27 |
| `codex/openclaw-acp-bound-labels-20260520` | Small, independent, clean |
| `codex/openclaw-acp-status-output-20260520` | Builds on bound-labels |
| `local/acp-enhancements-20260520` | Reference source (superset) |
| `feat/silent-reply-disallow` | Rebased to main, PR #87820 open |

### 🗑️ Discarded After Coordination (1 branch)

| Branch | Reason |
|--------|--------|
| `fix/telegram-acp-visible-watchdog` | Deleted — see "Coordination Decision" below |

### Coordination Decision: Watchdog vs Silent-Reply

Two patches solved the same symptom (ACP turn completes but user sees no output):

| | Watchdog (deleted) | Silent-Reply (kept, PR #87820) |
|---|---|---|
| **Strategy** | Proactive — full event tracker during turn (411 lines in dispatch-acp.ts) | Reactive — read session store after turn (153 lines) |
| **Code** | `AcpBoundTurnTracker` (complete/fail/onEvent lifecycle) | `maybeDeliverSessionStoreFinalFallback` (disk read fallback) |
| **Base version** | v2026.5.18 (May 15) | Current main (rebases cleanly) |

**Decision**: Keep silent-reply, delete watchdog. Reasons:
1. v2026.5.27 session lock fixes (#86123, #86816) eliminated the root cause (sessions going stale/deadlocked), drastically reducing the scenario where watchdog is needed
2. Watchdog based on 14-day-old code would have 400+ line conflicts rebasing to current main
3. Silent-reply's reactive approach is simpler, smaller, and already tested in PR #87820
4. If silent-reply proves insufficient, the watchdog's `AcpBoundTurnTracker` design can be referenced for a clean re-implementation

**General principle**: When upstream fixes the root cause, prefer the lighter defensive patch over the heavier proactive monitor.

### Stashes Kept (2)

| Stash | Content | Status |
|-------|---------|--------|
| `stash@{0}` pre-upgrade | Telegram group-auth, anthropic transport stream | Pending review |
| `stash@{1}` auto-stash | Subagent announce, heartbeat typing | Pending review |

## Key Findings

1. **v5.27 went deeper than expected** — Gateway, session transcript, and agent runner were all restructured. Most patches from v2026.5.22 era either conflict or are already covered.

2. **Small surgical patches win** — The 2 successful cherry-picks were both ≤3 file changes. The 100+ commit branches had near-zero cherry-pick success rate.

3. **Session lock fixes in v5.27 likely resolve "SolBI stale session"** — Two key fixes:
   - `#86123`: Session event queue self-wait deadlock (extension hooks during event processing)
   - `#86816`: Timeout abort not releasing session write lock
   - Together these explain the pattern of sessions going permanently stale after timeout

4. **`dispatch-acp.ts` is the conflict hotspot** — Three things touch it: `fix/telegram-acp-visible-watchdog` (+411 lines), `feat/silent-reply-disallow` (+153 lines), and `cursor binding labels` (+72 lines). These need a coordinated merge strategy.

5. **Transcript byte compaction already in v5.27** — `shouldCompactByTranscriptBytes` with `resolveMaxActiveTranscriptBytes` and fallback to `transcriptSizeSnapshot` is present in HEAD. No cherry-pick needed.

---

## Second-Round Deep Audit (2026-05-29, later session)

### Branch Subset Analysis

Used `git log A --oneline --not B` to determine containment:

| Branch | Unique vs superset | Verdict |
|--------|-------------------|---------|
| `codex/openclaw-agent-stability` (105) | **0 unique** vs `acp-telegram-resilience` — 100% subset | 🗑️ Deleted |
| `codex/acp-telegram-resilience` (127) | **0 unique** vs `acp-enhancements` — 100% subset | 🗑️ Deleted |
| `backup/pre-v2026.5.22-local-acp` (29) | **0 unique** vs `acp-enhancements` — 100% subset | 🗑️ Deleted |
| `codex/openclaw-acp-bound-labels` (1) | Clean cherry-pick | ✅ Picked, deleted |
| `codex/openclaw-acp-status-output` (2) | Clean cherry-pick (superset of bound-labels) | ✅ Picked, deleted |
| `local/main-telegram-fixes` (14) | 12/14 conflict, 2 clean | ✅ 2 picked, rest kept for manual port |

### Additional Cherry-Picks (Round 2)

| Commit | Source | What |
|--------|--------|------|
| `223fc58` fix: prefer bound ACP labels | acp-status-output | ACP status prefers bound session labels |
| `18b760a` fix: simplify ACP status output | acp-status-output | Simplifies runtime-options output format |
| `204347a` fix(telegram): avoid repeated progress placeholders | telegram-fixes | Deduplicates progress messages |
| `068bc02` fix(telegram): retain nonmonotonic stream drafts | telegram-fixes | Keeps drafts that shrink during editing |

### `local/acp-enhancements-20260520` — 21 Unique Commits

The canonical superset branch. 21 commits unique to it (not in any other branch):

**Still needed (not in v5.27):**
- `fix(acp): keep final failures visible` — ACP failure visibility in Telegram
- `fix(acp): recover stuck turns and improve visible status` — Turn recovery
- `fix(acp): make long turns visibly recoverable` — Long turn UX
- `fix(acp): force visible fallback for silent aborted turns` — Silent abort prevention
- `fix(acp): refresh progress on long-turn heartbeats` — Heartbeat progress
- `fix(acp): correlate bound session delivery` — Delivery correlation
- `fix(acp): include Telegram upload paths in bound turns` — Upload path tracking
- `feat(gateway): add heavy task admission control` — Load shedding
- `feat(integrations): redirect MC ACP spawn cwd to isolated worktree` — MC integration
- `fix(gateway): coalesce chat history bursts` — Chat history optimization
- `fix(gateway): gate heavy embedded runs under load` — Load gating
- `fix(gateway): reduce startup and agent event-loop pressure` — Startup optimization

**Potentially conflicting with v5.27:**
- `fix(acp): keep cursor binding labels aligned` — touches dispatch-acp.ts
- `fix(acp): fail closed on MC cwd redirect errors` — MC-specific
- `fix(cli): load config for routed gateway health` — CLI changes
- `fix(skills): seed snapshot version from skill-tree mtime across restarts` — Skills infra

### Final Branch State (After Both Rounds)

| Branch | Status |
|--------|--------|
| `feat/silent-reply-disallow` | 🟢 Active — PR #87820 |
| `local/acp-enhancements-20260520` | 🟢 Kept — 21 unique commits reference |
| `local/main-telegram-fixes-20260529` | 🟡 Kept — 12 conflicting commits for manual port |
| `backup/openclaw-main-before-sync-20260515-093658` | 🟡 1 commit to evaluate |
| `stash@{0}` pre-upgrade | 🟡 Pending review |
| `stash@{1}` auto-stash | 🟡 Likely droppable |

### Total Impact

- **Branches**: 11 → 6 (5 deleted)
- **Stashes**: 5 → 2 (3 dropped)
- **Cherry-picked commits**: 6 (2 round-1 + 4 round-2)
- **Worktrees cleaned**: 1 (openclaw-cherry-pick)
