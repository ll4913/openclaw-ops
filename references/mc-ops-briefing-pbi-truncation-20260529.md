# MC Ops Briefing PBI Query Truncation & Cache Period Mismatch

**Date**: 2026-05-29  
**Symptom**: Ops Briefing dashboard shows missing data — DSO null, AP DPO null, Orders all empty arrays, yesterday inventory by BU empty. No errors in UI, only subtle `errors` field in API response.

## Diagnostic Procedure

### Step 1: Check API Response

```bash
curl -s "http://localhost:3000/api/ops-briefing?tab=ops" -o /tmp/ops.json
python3 -c "
import json
with open('/tmp/ops.json') as f: data = json.load(f)
# Check errors field
print('Errors:', data.get('errors', []))
# Check for empty/null fields
def check(obj, path=''):
    if obj is None: print(f'  NULL: {path}')
    elif isinstance(obj, list) and len(obj) == 0: print(f'  EMPTY: {path}')
    elif isinstance(obj, dict):
        for k, v in obj.items(): check(v, f'{path}.{k}')
check(data)
"
```

### Step 2: Identify Failed Queries

Errors appear as `Q43: Unexpected end of JSON input` — meaning the PBI API returned a truncated response. Map query numbers to DAX files:

| Query | File | Purpose | Affected Fields |
|-------|------|---------|----------------|
| Q43 | `lib/dax-ap-templated.ts` | Top 15 AP vendors + aging | `apTopVendors`, DPO |
| Q46 | `lib/dax-ar-ap.ts` | Rolling 90d revenue by branch | DSO denominator, `arByRegion[].dso` |
| Q60 | `lib/dax-inventory-templated.ts` | Yesterday inventory by BU | `yesterdayInventoryByBU` |

### Step 3: Check Query Cache

Cache file: `~/.openclaw/.../cache/mc-query-cache.json` (location varies by release)

Cache key format: `Q{num}|{periodSig}` where `periodSig` = first 7 chars of `d.mtdStart` (e.g., `2026-05`).

```bash
python3 -c "
import json, glob, os
for cf in glob.glob(os.path.expanduser('~/Projects/mission-control/.mc-releases/*/.cache/mc-query-cache.json')):
    cache = json.load(open(cf))
    for k in sorted(cache.keys()):
        q = k.split('|')[0]
        if q in ['Q43', 'Q46', 'Q60']:
            print(f'{os.path.basename(os.path.dirname(os.path.dirname(cf)))}: {k}')
"
```

### Step 4: Identify Cache Period Mismatch

**Root cause of missing data despite cached results:**

1. Cache contains `Q43|2026-01` (January preloaded data)
2. Current request's `periodSig` = `2026-05` (May MTD)
3. Code loads cache with: `if (k.endsWith('|${periodSig}'))` → filters OUT January entries
4. Query fails → `getQueryCached(43)` looks for `Q43|2026-05` → not found → returns null
5. Result: empty data, no fallback

**The cache has valid data but the period key prevents it from being used as fallback.**

### Fix Options

**Short-term**: Force refresh to populate current period's cache:
```bash
curl "http://localhost:3000/api/ops-briefing?forceRefresh=true"
```

**Medium-term**: Fix `getQueryCached()` to fall back to most recent available period when current period cache is missing:
```typescript
function getQueryCached(queryNum: number): any | null {
  const key = periodKey(queryNum);
  const entry = queryCache[key];
  if (entry && Date.now() - entry.cachedAt < ttlMs) return entry.data;
  if (entry) delete queryCache[key];
  
  // NEW: Fall back to most recent available period
  const prefix = `Q${queryNum}|`;
  const candidates = Object.entries(queryCache)
    .filter(([k]) => k.startsWith(prefix))
    .sort(([, a], [, b]) => b.cachedAt - a.cachedAt);
  if (candidates.length > 0) {
    const [fallbackKey, fallbackEntry] = candidates[0];
    if (Date.now() - fallbackEntry.cachedAt < ttlMs * 4) { // 4x TTL for fallback
      console.log(`Q${queryNum} using fallback cache: ${fallbackKey}`);
      return fallbackEntry.data;
    }
  }
  return null;
}
```

**Long-term**: Investigate why PBI returns truncated JSON for Q43/Q46/Q60 — likely response size exceeds Node.js `http` module buffer limit or PBI gateway timeout.

### Key Code Locations

- **Route**: `app/api/ops-briefing/route.ts`
- **periodKey function**: `const periodSig = d.mtdStart.slice(0, 7); const periodKey = (n) => \`Q${n}|${periodSig}\`;`
- **Cache loading**: `if (k.endsWith(\`|${periodSig}\`)) queryCache[k] = v;`
- **Error collection**: `errors: results.map((r, i) => (r?.__error ? \`Q${i+1}: ${r.__error}\` : null)).filter(Boolean)`
- **Query execution**: `lib/pbi-infra.ts` → `executePBIQuery()` with 15s timeout per query
- **Cache TTL**: `lib/pbi-infra.ts` → `getQueryCacheTtlMs()` — hot queries get shorter TTL, stable queries get longer
