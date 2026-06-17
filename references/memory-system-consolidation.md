# Memory System Consolidation Analysis

**Date**: 2026-05-28  
**Context**: Audit of OpenClaw memory systems to identify overlap and consolidation opportunities.

---

## System Overview

| System | Size | Purpose | Status |
|--------|------|---------|--------|
| **SolMem** | 40MB | Structured knowledge (concepts, decisions, meetings, sources) | ✅ Primary knowledge store |
| **GBrain** | 9.1MB | Knowledge aggregation, nightly reports, FTS search | ✅ Aggregation layer |
| **LCM** | 107MB | Conversation history, summaries, context | ✅ Conversation management |
| **PowerMem** | ~~163MB~~ | (Obsolete) | ❌ Deleted |

---

## Overlap Analysis

### GBrain vs SolMem: LOW overlap

**GBrain** stores:
- 87 pages (mostly operational/meta pages)
- Recent examples: "MemPal SolBrain Drawer drawer_*", "GBrain Nightly Consolidation", "SolMem Source Hygiene Queue"
- Tables: `pages`, `links`, `tags`, `embeddings`, `timeline_entries`
- `raw_data` table: **0 records** (empty)

**SolMem** stores:
- Structured markdown: concepts (109), decisions (306), meetings (133), sources (50), projects (39), people (36), products (23), signals (40), strategy (30), lessons (87), ideas (27)
- `kg.sqlite` (576KB): Knowledge graph with `kg_triples` and `predicate_vocab`

**Relationship**: GBrain **aggregates from** SolMem to generate nightly reports and provides FTS search. Not redundant.

### GBrain vs LCM: NO overlap

- **GBrain**: Knowledge pages (aggregated reports)
- **LCM**: Conversation history (sessions, messages, summaries)

Completely different domains.

### LCM vs SolMem: LOW overlap

- **LCM**: Unstructured conversation history and summaries
- **SolMem**: Structured business knowledge (decisions, concepts, meetings)

Theoretically LCM summaries may reference SolMem content, but not duplicate storage.

---

## Three-Layer Architecture

```
User Conversations
    ↓
LCM (stores history, generates summaries)
    ↓
SolMem (captures decisions, concepts, meetings)
    ↓
GBrain (aggregates, generates nightly reports, provides FTS)
```

## Query Paths

- **Business knowledge** → SolMem (markdown files)
- **Full-text search** → GBrain (SQLite FTS)
- **Conversation history** → LCM (conversations/messages tables)
- **Session context** → LCM (context_items, summaries)

---

## PowerMem Cleanup (2026-05-28)

**Discovery**: PowerMem had no actual data:
- `data/` directory: **0 files** (EMPTY)
- `archive/` directory: **0 files** (EMPTY)
- 163MB was all logs: `stdout.log` (127MB), `server.log.*` (31MB), `stderr.log` (5.6MB)

**Cleanup performed**:
```bash
rm -rf ~/.openclaw/powermem/
rm -rf ~/.openclaw/workspace/skills/super-powermem/
rm -f ~/.openclaw/workspace/scripts/powermem-*
rm -f ~/.openclaw/workspace/scripts/patch-powermem.sh
rm -f ~/.openclaw/workspace/scripts/check-powermem-version.sh
rm -f ~/.openclaw/workspace/memory/2026-04-10-powermem-gemini-debug.md
rm -f ~/.openclaw/workspace/memory/2026-04-09-solmem-powermem.md
rm -f ~/.openclaw/workspace/memory/2026-04-08-powermem-watchdog.md
rm -f ~/.openclaw/workspace/memory/powermem-version.txt
rm -rf ~/.openclaw/workspace/memory/powermem-export/
rm -f ~/Library/LaunchAgents/com.powermem.server.plist.disabled
rm -f ~/Library/LaunchAgents/com.solm.powermem.plist.disabled
rm -f ~/.openclaw/solmem/projects/powermem-watchdog.md
rm -f ~/.openclaw/logs/powermem.log
```

**Savings**: 163MB

---

## Recommendations

1. **Keep all three active systems** (SolMem, GBrain, LCM) — they serve different purposes with minimal overlap
2. **Delete PowerMem** when `data/` and `archive/` are empty (logs only)
3. **Monitor GBrain growth** — currently 9.1MB with 87 pages. Prune old consolidation reports if it exceeds 50MB
4. **Document the architecture** for future audits to avoid confusion

---

## Verification Commands

```bash
# Check system sizes
du -sh ~/.openclaw/solmem/ ~/.openclaw/brain.db ~/.openclaw/lcm.db ~/.openclaw/powermem/ 2>/dev/null

# Check GBrain content
sqlite3 ~/.openclaw/brain.db "SELECT COUNT(*) FROM pages;"
sqlite3 ~/.openclaw/brain.db "SELECT title, created_at FROM pages ORDER BY created_at DESC LIMIT 5;"

# Check LCM content
sqlite3 ~/.openclaw/lcm.db "SELECT COUNT(*) FROM conversations;"
sqlite3 ~/.openclaw/lcm.db "SELECT COUNT(*) FROM summaries;"

# Check PowerMem data
find ~/.openclaw/powermem/data -type f 2>/dev/null | wc -l
find ~/.openclaw/powermem/archive -type f 2>/dev/null | wc -l
```
