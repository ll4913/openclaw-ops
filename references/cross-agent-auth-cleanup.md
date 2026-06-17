# Cross-Agent Auth Profile Cleanup — 2026-05-29

## Problem

After cleaning 7 invalid Anthropic profiles from the `main` agent, the same profiles existed across **16 agents** (68 invalid profiles total). Each agent has its own `auth-profiles.json` at `~/.openclaw/agents/<agent>/agent/auth-profiles.json`.

## Batch Cleanup Script

```python
import json, os, glob, shutil
from datetime import datetime

agents_dir = os.path.expanduser("~/.openclaw/agents")
backup_ts = datetime.now().strftime("%Y%m%d-%H%M%S")
results = []

for auth_file in sorted(glob.glob(f"{agents_dir}/*/agent/auth-profiles.json")):
    agent = auth_file.split("/agents/")[1].split("/")[0]
    
    with open(auth_file) as f:
        data = json.load(f)
    
    profiles = data.get("profiles", {})
    removed = []
    kept = []
    
    for name in list(profiles.keys()):
        if not isinstance(profiles[name], dict):
            continue
        if "anthropic" not in name:
            continue
        if name == "anthropic:default":
            kept.append(name)
            continue
        removed.append(name)
        del profiles[name]
    
    if removed:
        backup_path = f"{auth_file}.bak.{backup_ts}"
        shutil.copy2(auth_file, backup_path)
        data["profiles"] = profiles
        with open(auth_file, "w") as f:
            json.dump(data, f, indent=2)
        results.append(f"  ✅ {agent}: removed {len(removed)}, kept {kept or ['none']}")
    else:
        results.append(f"  ⏭️  {agent}: clean")

for r in results:
    print(r)
```

## Verification After Cleanup

```bash
# Count remaining invalid profiles (should be 0)
total=0
for f in ~/.openclaw/agents/*/agent/auth-profiles.json; do
    count=$(python3 -c "
import json
with open('$f') as fh:
    d=json.load(fh)
print(len([n for n in d.get('profiles',{}) if isinstance(d['profiles'][n], dict) and 'anthropic' in n and n != 'anthropic:default']))
")
    [ "$count" -gt "0" ] && echo "$f: $count" && total=$((total + count))
done
echo "Total: $total"

# Restart and verify
openclaw gateway restart
sleep 15
grep "eventLoopMax" /tmp/openclaw/openclaw-$(date +%Y-%m-%d).log | tail -3
grep "auth-profile-failure" /tmp/openclaw/openclaw-$(date +%Y-%m-%d).log | tail -3
```

## Impact Observed

| Metric | Before (all agents) | After |
|--------|---------------------|-------|
| Invalid profiles | 68 across 16 agents | 0 |
| Auth preheat | 14-162s | 13-15s |
| eventLoopMax | 22,112ms | 130-183ms |
| auth-profile-failure | Frequent | Zero |

## Key Insight

The main agent cleanup was necessary but not sufficient. Other agents with the same invalid profiles would independently trigger auth re-warm cycles. The gateway shares a single Node event loop, so ANY agent's auth failure blocks ALL agents. Always clean ALL agents, not just the one exhibiting symptoms.
