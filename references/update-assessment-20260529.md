# OpenClaw Update Assessment - Session 2026-05-29

## Context
User requested update check for OpenClaw installation at `~/.openclaw/`. System has heavy customization including ACP implementations and custom agent modifications.

## Current State
- **Version**: 2026.5.24 (commit 56eb23dda4)
- **Branch**: main-upstream
- **Uncommitted changes**: 7 files modified
- **Custom modifications**: ACP implementations, agent customizations

## Available Update
- **Target version**: 2026.5.27
- **Commits behind**: 1,247 commits
- **Files changed**: 3,849 files (203K additions, 59K deletions)
- **ACP files changed**: 23 files
- **Agent files changed**: 437 files

## Conflict Risk Assessment
Files with conflict risk:
- ⚠️ `src/auto-reply/reply/reply-dispatcher.ts` (changed in 2026.5.27)
- ⚠️ `src/infra/outbound/payloads.test.ts` (changed in 2026.5.27)

Safe files (not changed upstream):
- ✅ `extensions/telegram/src/bot/delivery.test.ts`
- ✅ `src/auto-reply/reply/reply-flow.test.ts`
- ✅ `src/infra/outbound/payloads.ts`
- ✅ `src/shared/silent-reply-policy.ts`

## Risk Matrix
| Factor | Value | Risk Level |
|--------|-------|------------|
| Commits | 1,247 | **High** (>500) |
| Files changed | 3,849 | **High** (>3000) |
| Local conflicts | 2 | **Medium** (1-2) |
| ACP changes | 23 | **Medium** (10-50) |
| Agent changes | 437 | **High** (>300) |

**Overall Risk**: HIGH

## Recommendation
**Option A: Wait** (recommended)
- Current version is stable and functional
- High risk of conflicts in critical systems (ACP, agents)
- Large update scope requires significant testing time
- Wait for next minor release or until customizations are stabilized

**If updating later**:
1. Create comprehensive backup (already done: `/Users/lianglin/.openclaw/backups/openclaw-pre-update-20260529-002032/`)
2. Use staged approach (feature branch)
3. Resolve conflicts manually
4. Test ACP and agent systems thoroughly
5. Have rollback plan ready

## Key Discoveries

### models.providers Structure
Provider configurations live under `models.providers` as a dict, NOT `providers.entries`:
```json
{
  "models": {
    "providers": {
      "anthropic": { "baseUrl": "...", "apiKey": "...", "models": [...] },
      "gemini": { ... }
    }
  }
}
```

**Common issue**: `google` and `gemini` often duplicate (same API key and URL). Remove `google` if `gemini` exists.

### Hardcoded Thresholds
Some thresholds cannot be configured:
- RSS warning: 1536 MB (hardcoded in src/logging/diagnostic-memory.ts)
- RSS critical: 3072 MB (hardcoded)
- LCM compaction: No manual trigger API exists

These produce warnings only — no functional impact on high-RAM systems.

### Update Assessment Commands
```bash
# Check current state
git status --short
openclaw --version

# Compare versions
git fetch origin --tags
git log --oneline HEAD..<latest-tag> | wc -l

# Check conflicts
for file in $(git status --short | grep "^ M" | awk '{print $2}'); do
  git diff --name-only HEAD..<latest-tag> | grep -c "^$file$"
done

# Check ACP/Agent changes
git diff --name-only HEAD..<latest-tag> | grep -i acp | wc -l
git diff --name-only HEAD..<latest-tag> | grep -E "^src/agents/" | wc -l
```

## Backup Location
```
/Users/lianglin/.openclaw/backups/openclaw-pre-update-20260529-002032/
├── openclaw-repo.bundle (1.1GB - full git bundle)
├── openclaw.json.backup (80KB - config backup)
├── staged.patch (empty)
└── uncommitted.patch (13KB - local changes)
```

## User Decision
**Wait** - User agreed to postpone update due to:
- Stable current operation
- High customization level
- Significant conflict risk
- Large update scope

## Lessons Learned
1. **Always assess before updating** - Use the risk matrix to make informed decisions
2. **Heavy customization = higher risk** - Custom ACP/agent work increases update complexity
3. **Stable systems don't need updates** - If it works, don't fix it unless necessary
4. **Backup first** - Always create comprehensive backups before considering updates
5. **Document discoveries** - models.providers structure and hardcoded thresholds are non-obvious
