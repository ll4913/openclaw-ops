# Codex Desktop Proxy Bypass — PBI/Microsoft Auth Fix

**Confirmed**: 2026-06-12 — fixed MC dashboard showing dashes for orders/inventory

## Symptom

- MC dashboard NEW ORDERS and INVENTORY sections show dashes (-) for all current data
- Only Prev Month values display (historical data from snapshot, not live PBI queries)
- `mc-stderr.log` has millions of `[timeout] qXXX exceeded 45s` entries (66MB)
- PBI Python script fails: `ConnectionResetError(54, 'Connection reset by peer')` against `login.microsoftonline.com`
- Direct `curl` to Microsoft works fine (200), but via system proxy fails (000/timeout)
- Eventually MC frontend crashes with "Application error: a client-side exception has occurred"

## Root Cause

Codex Desktop (the app, not CLI) installs a system HTTP proxy:
- **Proxy**: `127.0.0.1:3067`
- **Bypass list**: EMPTY (the bug)

All HTTPS traffic routes through the Codex proxy, which doesn't properly handle connections to `login.microsoftonline.com`. The Python `requests` library and Node.js `fetch` both pick up the system proxy settings.

## Diagnosis

```bash
# Check proxy config
networksetup -getwebproxy Wi-Fi        # Shows 127.0.0.1:3067
networksetup -getproxybypassdomains Wi-Fi  # EMPTY = problem

# Test connectivity
curl --noproxy '*' -s -o /dev/null -w "Direct: %{http_code} %{time_total}s\n" --max-time 5 \
  "https://login.microsoftonline.com/common/discovery/v2.0/keys"
curl -s -o /dev/null -w "Via proxy: %{http_code} %{time_total}s\n" --max-time 5 \
  "https://login.microsoftonline.com/common/discovery/v2.0/keys"
# Direct=200 (1.7s), Via-proxy=000 (5s timeout) → proxy is blocking
```

## Fix

```bash
networksetup -setproxybypassdomains Wi-Fi \
  "login.microsoftonline.com" \
  "*.microsoftonline.com" \
  "*.microsoft.com" \
  "login.live.com" \
  "*.azure.com" \
  "*.powerbi.com" \
  "*.analysis.windows.net" \
  "localhost" \
  "127.0.0.1" \
  "*.local"
```

Then restart MC to clear accumulated timed-out queries:
```bash
launchctl kickstart -k gui/$(id -u)/com.solm.mission-control
# Wait 5s, then verify:
curl -s --max-time 10 "http://localhost:3000/api/health"
```

## Symptom Cascade

1. Proxy blocks `login.microsoftonline.com` → TLS connection reset (54)
2. PBI OAuth token fetch fails → `requests.exceptions.ConnectionError`
3. MC `runQuery` calls timeout after 45s each → hundreds of `[timeout]` in stderr
4. stderr log accumulates ~1.7M timeout entries (66MB file)
5. Dashboard API returns empty arrays (`inventoryByRegion: []`)
6. Frontend shows dashes (-) for all current data
7. Eventually JS crashes → "Application error: a client-side exception has occurred"

## Prevention

The bypass list should be set once and persists across reboots. If Codex Desktop is reinstalled or updated, verify the bypass list hasn't been reset:
```bash
networksetup -getproxybypassdomains Wi-Fi
```

## MC Restart Procedure

```bash
# LaunchAgent: com.solm.mission-control
# Ports: gzip-proxy :3000 → next-server :3001
# Release: ~/.mc-releases/<timestamp>/

launchctl kickstart -k gui/$(id -u)/com.solm.mission-control
sleep 5
curl -s --max-time 10 "http://localhost:3000/api/health"
lsof -i :3000 -i :3001 -P -n | grep LISTEN
```
