# OpenClaw Memory System Architecture

*Verified 2026-05-28*

## Three-Layer System (No Significant Overlap)

| System | Size | Purpose | Content |
|--------|------|---------|---------|
| **SolMem** | 40MB | Knowledge storage | Markdown files: concepts (109), decisions (306), meetings (133), sources (50), projects (39), people (36), signals (40), lessons (87) + kg.sqlite (576KB) |
| **GBrain** | 9.1MB | Knowledge aggregation | SQLite/FTS with 87 pages — nightly reports, operational metadata, aggregated summaries from SolMem |
| **LCM** | 107MB | Conversation management | conversations, messages, message_parts, summaries, context_items, FTS indexes |

## Overlap Analysis

- **SolMem ↔ GBrain**: LOW. SolMem stores raw knowledge; GBrain aggregates and indexes it. GBrain's "Nightly Consolidation" pages are generated from SolMem content but are summaries, not duplicates.
- **GBrain ↔ LCM**: NONE. GBrain handles knowledge pages; LCM handles conversation history.
- **SolMem ↔ LCM**: LOW. LCM summaries may reference SolMem content but are conversation-scoped.

## GBrain DB Schema (`~/.openclaw/brain.db`)

### pages table
```sql
CREATE TABLE pages (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  slug          TEXT NOT NULL UNIQUE,
  type          TEXT NOT NULL,          -- 'audit', 'decision', 'ops', etc.
  title         TEXT NOT NULL,
  compiled_truth TEXT NOT NULL DEFAULT '',  -- full markdown content
  timeline      TEXT NOT NULL DEFAULT '',
  frontmatter   TEXT NOT NULL DEFAULT '{}', -- JSON string
  created_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
  updated_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);
```

### links table
```sql
CREATE TABLE links (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  from_page_id INTEGER NOT NULL REFERENCES pages(id),
  to_page_id   INTEGER NOT NULL REFERENCES pages(id),
  context      TEXT NOT NULL DEFAULT '',
  UNIQUE(from_page_id, to_page_id)
);
```

### tags table
```sql
CREATE TABLE tags (
  id      INTEGER PRIMARY KEY AUTOINCREMENT,
  page_id INTEGER NOT NULL REFERENCES pages(id),
  tag     TEXT NOT NULL,
  UNIQUE(page_id, tag)
);
```

### timeline_entries table
```sql
CREATE TABLE timeline_entries (
  id       INTEGER PRIMARY KEY AUTOINCREMENT,
  page_id  INTEGER NOT NULL REFERENCES pages(id),
  date     TEXT NOT NULL,
  source   TEXT NOT NULL DEFAULT '',
  summary  TEXT NOT NULL,
  detail   TEXT NOT NULL DEFAULT ''
);
```

### FTS Triggers
Pages has automatic FTS triggers (`page_fts`) that index title, compiled_truth, and timeline on insert/update/delete.

## Inserting a Page

```sql
INSERT INTO pages (slug, type, title, compiled_truth, frontmatter) VALUES (
  'my-slug-here',
  'decision',
  'Page Title',
  '# Full markdown content here...',
  '{"date":"2026-05-28","tags":["tag1","tag2"],"author":"hermes"}'
);

-- Then add tags (use page_id from the insert)
INSERT OR IGNORE INTO tags (page_id, tag) VALUES (LAST_INSERT_ROWID(), 'my-tag');

-- Timeline entry
INSERT INTO timeline_entries (page_id, date, source, summary) VALUES
  (LAST_INSERT_ROWID(), '2026-05-28', 'hermes-agent', 'Brief summary');
```

## Deprecated Memory Systems

| System | Status | Action |
|--------|--------|--------|
| **PowerMem** | DELETED (2026-05-28) | Had no actual data, only 163MB of logs |
| **memory-lancedb** | REMOVED from plugins | No LanceDB data existed |
| **memory-powermem.disabled** | DELETED | Disabled extension |

## SolMem kg.sqlite

Tiny knowledge graph: `kg_triples` + `predicate_vocab` tables. 576KB. Not a primary query target.
