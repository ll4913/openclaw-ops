# Hermes Opus 4.8 Thinking API Incompatibility (2026-05-29)

## Symptom

Switching a Hermes profile to `claude-opus-4-8` via Anthropic provider causes every API call to fail with HTTP 400:

```
Error 400: "thinking.type.enabled" is not supported for this model.
Use "thinking.type.adaptive" and "output_config.effort" to control thinking behavior.
→ Fallback activated: claude-opus-4-8 → claude-haiku-4-5
```

The bot appears to work but silently falls back to Haiku 4.5.

## Root Cause

Anthropic changed the thinking API format for Opus 4.8:
- **Old format** (Opus 4.7 and earlier): `thinking.type = "enabled"`
- **New format** (Opus 4.8+): `thinking.type = "adaptive"` + `output_config.effort`

Hermes sends the old format when `reasoning_effort` is set to anything other than `none`. Anthropic rejects it → Hermes falls back.

## Fix

Set `reasoning_effort: none` in the profile's `config.yaml`:

```yaml
agent:
  reasoning_effort: none
```

Then restart the gateway:
```bash
launchctl kickstart -k gui/$(id -u)/ai.hermes.gateway.<profile>
```

## Verification

Check agent.log for the actual model used (not the fallback):
```bash
grep "model=claude-opus-4-8" ~/.hermes/profiles/<profile>/logs/agent.log | tail -3
# Should show: API call #1: model=claude-opus-4-8 provider=anthropic
# Should NOT show: Fallback activated
```

## Impact

- Thinking/reasoning is disabled for that profile
- This is a Hermes SDK compatibility issue — needs upstream fix to support `thinking.type.adaptive`
- Until fixed, any Hermes profile using Opus 4.8 must have `reasoning_effort: none`
