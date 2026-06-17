# MC Data Pipeline Failure Patterns (2026-06-12)

## Microsoft Azure AD Proxy Bypass

### Symptom Chain
```
MC dashboard shows dashes (-) for New Orders + Inventory
  → API returns inventoryByRegion: [] (empty)
  → PBI queries timeout (q690, q691... all exceeded 45s)
  → pbi_query.py fails: ConnectionResetError(54, 'Connection reset by peer')
  → login.microsoftonline.com unreachable via system proxy
```

### Root Cause
Codex Desktop sets a system web proxy on `127.0.0.1:3067` with **empty bypass list**. All HTTPS traffic routes through the proxy, which silently drops Microsoft OAuth connections.

### Diagnosis
```bash
# Direct = works, via proxy = timeout
curl --noproxy '*' -s -o /dev/null -w "%{http_code}" "https://login.microsoftonline.com/..."  # 200
curl -s -o /dev/null -w "%{http_code}" "https://login.microsoftonline.com/..."                  # 000
# Check proxy config
networksetup -getwebproxy Wi-Fi       # Server: 127.0.0.1, Port: 3067
networksetup -getproxybypassdomains   # (empty!)
# What's on 3067?
lsof -i :3067 -P -n | grep LISTEN    # codex app-server
```

### Fix
```bash
networksetup -setproxybypassdomains Wi-Fi \
  "login.microsoftonline.com" "*.microsoftonline.com" "*.microsoft.com" \
  "login.live.com" "*.azure.com" "*.powerbi.com" "*.analysis.windows.net" \
  "localhost" "127.0.0.1" "*.local"
# Restart MC to clear accumulated timeouts
launchctl kickstart -k gui/$(id -u)/com.solm.mission-control
```

### Pitfalls
- MC Node.js does NOT read `HTTP_PROXY`/`HTTPS_PROXY` env vars — uses macOS system proxy
- After fix, MC needs restart: accumulated timeout queries (1.7M+ in log) won't clear automatically
- Google/GitHub also timeout through this proxy, but Microsoft is the critical path for PBI data

## MC Client-Side Error After PBI Timeout Storm

### Symptom
`"Application error: a client-side exception has occurred while loading mc.solm.com"`

### Cause
PBI query timeout storm (hundreds of concurrent 45s timeouts) causes Next.js server to accumulate pending promises. Browser requests hit stale server state → React hydration fails.

### Fix
```bash
launchctl kickstart -k gui/$(id -u)/com.solm.mission-control
# Wait 5s, verify health
curl -s "http://localhost:3000/api/health"  # should return healthy
```

## MC Server Architecture

### Ports & Processes
- **Port 3000**: gzip-proxy.mjs (compresses responses for ngrok tunnel)
- **Port 3001**: next-server (actual Next.js app)
- **Port 3100**: PBI MCP server (Power BI query proxy)
- Managed by launchd: `com.solm.mission-control`

### Data Flow
```
Browser → ngrok tunnel → gzip-proxy:3000 → next-server:3001
  → API routes call pbi_query.py or PBI MCP:3100
  → pbi_query.py → Azure AD OAuth → Power BI REST API
```

## mc.solm.com Performance Baseline (2026-06-11)

### Architecture
`User → Cloudflare (LAX) → ngrok tunnel → gzip-proxy:3000 → Next.js:3001`
Source IP: 198.20.0.51 (Charter Communications / ngrok infra)

### Measured Latency
- DNS: 2ms, TLS: 920ms, TTFB: 6.7s (first request), ~2s subsequent
- API health: 1.5-2.2s baseline
- Page load (login): 7.4s to interactive
- Resources: Google Fonts 2.2s, Vercel Analytics 3.0s (0KB!), solm-logo.png 1.9s (404)

### Issues (not yet fixed)
- ngrok tunnel adds ~1.5s overhead per request
- Zero CDN caching (`cache-control: no-store` on everything)
- 404 on solm-logo.png still costs 1.9s through the tunnel
- Cloudflare `cf-cache-status: DYNAMIC` means no edge caching
