# Provider Three-Layer Cleanup

OpenClaw merges model provider config from **three layers**. Deleting only layer 1–2 leaves ghost providers in `/models`.

| Layer | Path | Description |
|-------|------|-------------|
| 1. Global | `~/.openclaw/openclaw.json` → `models.providers.<name>` | Shared by all agents |
| 2. Per-agent | `~/.openclaw/agents/<id>/agent/models.json` → `providers.<name>` | One file per agent |
| 3. Alias keys | `~/.openclaw/openclaw.json` → `agents.defaults.models.<provider>/<model>` | Key contains provider name → gateway infers provider exists |

## Full removal procedure

Replace `PROVIDER_NAME` with the provider id.

```bash
# Layer 1: global providers
python3 -c "
import json
p = '$HOME/.openclaw/openclaw.json'
with open(p) as f: d = json.load(f)
removed = d.get('models',{}).get('providers',{}).pop('PROVIDER_NAME', None)
open(p,'w').write(json.dumps(d,indent=2,ensure_ascii=False)+'\n')
print('layer1 removed:', removed is not None)
"

# Layer 2: all agent models.json
python3 -c "
import json, glob, os
home = os.path.expanduser('~/.openclaw/agents')
for p in glob.glob(home + '/*/agent/models.json'):
    d = json.load(open(p))
    if d.get('providers',{}).pop('PROVIDER_NAME', None):
        open(p,'w').write(json.dumps(d,indent=2,ensure_ascii=False)+'\n')
        print('layer2 cleaned:', p)
"

# Layer 3: alias keys (critical)
python3 -c "
import json, os
p = os.path.expanduser('~/.openclaw/openclaw.json')
with open(p) as f: d = json.load(f)
models = d.get('agents',{}).get('defaults',{}).get('models',{})
keys = [k for k in list(models) if 'PROVIDER_NAME' in k]
for k in keys: del models[k]; print('layer3 deleted alias:', k)
open(p,'w').write(json.dumps(d,indent=2,ensure_ascii=False)+'\n')
"

openclaw gateway restart
sleep 6
grep -c "PROVIDER_NAME" ~/.openclaw/openclaw.json  # expect 0
```

## MLX local server startup order

Gateway probes provider ports at startup:

1. Stop MLX server
2. `openclaw gateway restart`
3. Start MLX server
4. Wait ~40s for model load
5. `openclaw gateway restart` again

## Gateway restart note

`openclaw gateway restart` may surface `missing tool result` in the agent session — normal during restart. Verify with:

```bash
curl -s http://127.0.0.1:18789/health | python3 -c "import sys,json;print(json.load(sys.stdin).get('status'))"
```
