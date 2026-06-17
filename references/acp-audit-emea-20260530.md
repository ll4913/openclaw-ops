# ACP Audit: Session Metadata Loss, OAuth SSRF, Lossless-Claw Quarantine (2026-05-30)

Audit of Solm engineer bot ACP agent performance in SOLM EMEA group (`-1003797037995`).

## ACP Spawn Event

- **User:** Giulio Falconi (`@gfalconi`, ID `8458656555`)
- **Time:** ~14:51 UTC (22:51 Beijing)
- **Command:** `/acp spawn claude --mode persistent --thread here --label mc-claude-gfalconi`
- **Session:** `agent:claude:acp:d1fce510-4a21-4058-b4fa-10574f853c0a`
- **Model:** Upgraded to `anthropic/claude-opus-4-8`

## Task: IFU PDF vs Excel Comparison

- 196 fields across 14 languages (13 European + Arabic)
- **Results:** 155 full matches, 27 partial matches, 14 significant differences
- **Output:** `IFU_PDF_vs_Excel_Report.xlsx` + `IFU_Highlighted_Differences.pdf`
- **Duration:** ~24 minutes (15:02 → 15:26 UTC)

## Issues Found

### 1. Anthropic API Timeout → Fallback to GLM
- 15:31 UTC: `claude-sonnet-4-6` returned `fetch failed` (0 tokens)
- Fallback to `zai/glm-5.1` successfully delivered response
- 67,134 input tokens consumed before failure

### 2. ACP Session Metadata Loss
- Session line 132: `ACP_SESSION_INIT_FAILED: ACP metadata is missing`
- Session became stale — needs `/acp spawn` to recreate
- This is the SAME error seen across multiple agents (5/22–5/30)

### 3. OAuth SSRF Blocking
- `OAuth token refresh failed for openai-codex: Blocked: resolves to private/internal/special-use IP address`
- DNS: `auth.openai.com` → `198.18.1.18` (fake-IP proxy)
- SSRF guard in `src/infra/net/ssrf.ts:360` blocks RFC 2544 range
- OAuth flow (`extensions/openai/openai-codex-oauth-flow.runtime.ts:196`) does NOT pass SSRF policy

### 4. Network Errors
- `FailoverError: LLM request failed: network connection error` (10.4s timeout)
- Polling spool error: `ENOENT` on ingress-spool-engineer file rename (5/29)

### 5. Transcript Reconciliation Warnings
- `afterTurn: transcript reconcile did not cover the transcript frontier`
- lossless-claw plugin skipping persistence for EMEA sessions
- Root cause: per-process quarantine after first error (see pitfall in SKILL.md)

## ACP Session Lifecycle — Metadata Write vs Loss

| Phase | Action | Metadata Effect |
|-------|--------|----------------|
| `/acp spawn` | `initializeSession()` | **Writes** full ACP meta |
| Turn execution | `runTurn()` → `ensureRuntimeHandle()` | **Updates** identity, state |
| Idle eviction | `evictIdleRuntimeHandles()` | In-memory only; metadata persists |
| Gateway restart | Process exits/restarts | Metadata **survives** (on disk) |
| **Maintenance pass** | `pruneStaleEntries()` / `capEntryCount()` | **DELETES** entire entry |
| Session reset | `closeSession({ clearMeta })` | **DELETES** `.acp` field |
| Store corruption | Empty/corrupt JSON read | **ALL metadata lost** |

## Key Code Locations

- `dist/manager-DOtDzZd5.js:23` — `resolveMissingMetaError()` error origin
- `dist/manager-DOtDzZd5.js:855-880` — `resolveSession()` where metadata absence detected
- `dist/store-load-CDlBvYZm.js:1198-1217` — Load-time maintenance pruning (primary suspect)
- `dist/store-kCn2DU7g.js:881-895` — `preserveExistingAcpMetadata` guard
- `extensions/openai/openai-codex-oauth-flow.runtime.ts:196` — OAuth without SSRF policy
- `src/infra/net/ssrf.ts:360` — `BLOCKED_RESOLVED_IP_MESSAGE` constant
- `src/context-engine/registry.ts:810-846` — Quarantine mechanism

## Codex OAuth Dual-Account Status (2026-05-30)

| Account | Status | Expiry | Notes |
|---------|--------|--------|-------|
| `llin@sol-m.com` | ✅ Active | 2026-06-07 (7d remaining) | Current `lastGood` profile, Codex CLI auth |
| `lianglin4913@gmail.com` | ❌ Expired | N/A | No accessToken, no refreshToken, expiresAt=0 |

**Recovery order:** Fix OAuth SSRF bug first → then re-authenticate `lianglin4913@gmail.com` via `codex login`.

**Codex CLI auth file:** `~/.codex/auth.json` — contains `id_token`, `access_token`, `refresh_token`, `account_id` under `tokens` key. JWT exp/iat can be decoded from the base64url payload.
