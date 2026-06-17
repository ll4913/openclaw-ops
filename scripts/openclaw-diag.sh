#!/bin/bash
# OpenClaw Gateway Diagnostic Script
# Usage: bash openclaw-diag.sh [output_file]
#
# This script collects comprehensive diagnostic information about OpenClaw Gateway
# performance and health. Run when experiencing high CPU, slow response, or crashes.

set -e

OUTPUT_FILE="${1:-/tmp/openclaw-diag-$(date +%Y%m%d-%H%M%S).txt}"

echo "OpenClaw Gateway Diagnostic Report" | tee "$OUTPUT_FILE"
echo "Generated: $(date)" | tee -a "$OUTPUT_FILE"
echo "========================================" | tee -a "$OUTPUT_FILE"
echo "" | tee -a "$OUTPUT_FILE"

# 1. Process Information
echo "1. PROCESS INFORMATION" | tee -a "$OUTPUT_FILE"
echo "----------------------" | tee -a "$OUTPUT_FILE"
GATEWAY_PID=$(pgrep -f "node.*openclaw.*gateway" | head -1)

if [ -z "$GATEWAY_PID" ]; then
    echo "ERROR: OpenClaw Gateway not running!" | tee -a "$OUTPUT_FILE"
    exit 1
fi

echo "Gateway PID: $GATEWAY_PID" | tee -a "$OUTPUT_FILE"
ps -p "$GATEWAY_PID" -o pid,ppid,etime,%cpu,%mem,rss,vsz,command | tee -a "$OUTPUT_FILE"
echo "" | tee -a "$OUTPUT_FILE"

# 2. Thread Count
echo "2. THREAD ANALYSIS" | tee -a "$OUTPUT_FILE"
echo "------------------" | tee -a "$OUTPUT_FILE"
THREAD_COUNT=$(ps -M "$GATEWAY_PID" | wc -l | tr -d ' ')
echo "Total threads: $THREAD_COUNT" | tee -a "$OUTPUT_FILE"

if [ "$THREAD_COUNT" -gt 120 ]; then
    echo "⚠️  WARNING: High thread count (>120). Possible native module duplication." | tee -a "$OUTPUT_FILE"
fi

echo "" | tee -a "$OUTPUT_FILE"
echo "Thread types:" | tee -a "$OUTPUT_FILE"
ps -M "$GATEWAY_PID" | awk '{print $NF}' | sort | uniq -c | sort -rn | head -10 | tee -a "$OUTPUT_FILE"
echo "" | tee -a "$OUTPUT_FILE"

# 3. Provider Auth Performance
echo "3. PROVIDER AUTH PERFORMANCE" | tee -a "$OUTPUT_FILE"
echo "----------------------------" | tee -a "$OUTPUT_FILE"
AUTH_LOG=$(grep "provider auth state pre-warmed" /tmp/openclaw/openclaw-*.log 2>/dev/null | tail -1)

if [ -n "$AUTH_LOG" ]; then
    echo "Latest auth log:" | tee -a "$OUTPUT_FILE"
    echo "$AUTH_LOG" | tee -a "$OUTPUT_FILE"
    
    AUTH_TIME=$(echo "$AUTH_LOG" | grep -o 'in [0-9]*ms' | grep -o '[0-9]*')
    echo "" | tee -a "$OUTPUT_FILE"
    echo "Auth time: ${AUTH_TIME}ms" | tee -a "$OUTPUT_FILE"
    
    if [ "$AUTH_TIME" -gt 60000 ]; then
        echo "⚠️  WARNING: Auth time >60s. Too many providers configured." | tee -a "$OUTPUT_FILE"
    elif [ "$AUTH_TIME" -gt 30000 ]; then
        echo "⚠️  CAUTION: Auth time >30s. Consider removing unused providers." | tee -a "$OUTPUT_FILE"
    else
        echo "✓ Auth time is healthy" | tee -a "$OUTPUT_FILE"
    fi
else
    echo "No auth logs found" | tee -a "$OUTPUT_FILE"
fi
echo "" | tee -a "$OUTPUT_FILE"

# 4. Liveness Warnings
echo "4. LIVENESS WARNINGS" | tee -a "$OUTPUT_FILE"
echo "--------------------" | tee -a "$OUTPUT_FILE"
LIVENESS_COUNT=$(grep -c "liveness warning" /tmp/openclaw/openclaw-*.log 2>/dev/null || echo "0")
echo "Total liveness warnings: $LIVENESS_COUNT" | tee -a "$OUTPUT_FILE"

if [ "$LIVENESS_COUNT" -gt 0 ]; then
    echo "" | tee -a "$OUTPUT_FILE"
    echo "Recent warnings:" | tee -a "$OUTPUT_FILE"
    grep "liveness warning" /tmp/openclaw/openclaw-*.log 2>/dev/null | tail -5 | tee -a "$OUTPUT_FILE"
    
    echo "" | tee -a "$OUTPUT_FILE"
    echo "Latest event loop delay:" | tee -a "$OUTPUT_FILE"
    grep "eventLoopDelayP99Ms" /tmp/openclaw/openclaw-*.log 2>/dev/null | tail -1 | grep -o 'eventLoopDelayP99Ms=[0-9.]*' | tee -a "$OUTPUT_FILE"
else
    echo "✓ No liveness warnings" | tee -a "$OUTPUT_FILE"
fi
echo "" | tee -a "$OUTPUT_FILE"

# 5. Provider Configuration
echo "5. PROVIDER CONFIGURATION" | tee -a "$OUTPUT_FILE"
echo "-------------------------" | tee -a "$OUTPUT_FILE"
CONFIG_FILE="$HOME/.openclaw/openclaw.json"

if [ -f "$CONFIG_FILE" ]; then
    PROVIDER_COUNT=$(jq '.models.providers | length' "$CONFIG_FILE" 2>/dev/null || echo "unknown")
    echo "Total providers: $PROVIDER_COUNT" | tee -a "$OUTPUT_FILE"
    
    if [ "$PROVIDER_COUNT" != "unknown" ] && [ "$PROVIDER_COUNT" -gt 15 ]; then
        echo "⚠️  WARNING: Many providers configured (>$PROVIDER_COUNT). Consider removing unused ones." | tee -a "$OUTPUT_FILE"
    fi
    
    echo "" | tee -a "$OUTPUT_FILE"
    echo "Provider list:" | tee -a "$OUTPUT_FILE"
    jq -r '.models.providers | to_entries[] | "  - \(.key): \(.value.baseUrl // "no URL")"' "$CONFIG_FILE" 2>/dev/null | tee -a "$OUTPUT_FILE"
else
    echo "Config file not found: $CONFIG_FILE" | tee -a "$OUTPUT_FILE"
fi
echo "" | tee -a "$OUTPUT_FILE"

# 6. Native Module Analysis
echo "6. NATIVE MODULE ANALYSIS" | tee -a "$OUTPUT_FILE"
echo "-------------------------" | tee -a "$OUTPUT_FILE"
echo "Loaded .node modules:" | tee -a "$OUTPUT_FILE"
vmmap -w "$GATEWAY_PID" 2>/dev/null | grep "\.node$" | awk '{print $NF}' | sort -u | tee -a "$OUTPUT_FILE"

echo "" | tee -a "$OUTPUT_FILE"
echo "Checking for duplicates:" | tee -a "$OUTPUT_FILE"
CLIPBOARD_PATHS=$(vmmap -w "$GATEWAY_PID" 2>/dev/null | grep "clipboard.*\.node$" | awk '{print $NF}' | sort -u | wc -l | tr -d ' ')

if [ "$CLIPBOARD_PATHS" -gt 1 ]; then
    echo "⚠️  WARNING: Multiple clipboard modules loaded ($CLIPBOARD_PATHS paths)" | tee -a "$OUTPUT_FILE"
    vmmap -w "$GATEWAY_PID" 2>/dev/null | grep "clipboard.*\.node$" | awk '{print "  " $NF}' | sort -u | tee -a "$OUTPUT_FILE"
else
    echo "✓ No duplicate clipboard modules" | tee -a "$OUTPUT_FILE"
fi
echo "" | tee -a "$OUTPUT_FILE"

# 7. Memory Usage
echo "7. MEMORY USAGE" | tee -a "$OUTPUT_FILE"
echo "---------------" | tee -a "$OUTPUT_FILE"
ps -p "$GATEWAY_PID" -o rss,vsz | tee -a "$OUTPUT_FILE"

echo "" | tee -a "$OUTPUT_FILE"
echo "Memory pressure warnings:" | tee -a "$OUTPUT_FILE"
MEM_PRESSURE=$(grep -c "memory pressure" /tmp/openclaw/openclaw-*.log 2>/dev/null || echo "0")
echo "Total: $MEM_PRESSURE" | tee -a "$OUTPUT_FILE"

if [ "$MEM_PRESSURE" -gt 0 ]; then
    echo "" | tee -a "$OUTPUT_FILE"
    echo "Latest:" | tee -a "$OUTPUT_FILE"
    grep "memory pressure" /tmp/openclaw/openclaw-*.log 2>/dev/null | tail -1 | tee -a "$OUTPUT_FILE"
fi
echo "" | tee -a "$OUTPUT_FILE"

# 8. Session Locks
echo "8. SESSION LOCKS" | tee -a "$OUTPUT_FILE"
echo "----------------" | tee -a "$OUTPUT_FILE"
LOCK_COUNT=$(find "$HOME/.openclaw" -name "*.lock" 2>/dev/null | wc -l | tr -d ' ')
echo "Lock files found: $LOCK_COUNT" | tee -a "$OUTPUT_FILE"

if [ "$LOCK_COUNT" -gt 0 ]; then
    echo "" | tee -a "$OUTPUT_FILE"
    echo "Lock file locations:" | tee -a "$OUTPUT_FILE"
    find "$HOME/.openclaw" -name "*.lock" 2>/dev/null | tee -a "$OUTPUT_FILE"
fi
echo "" | tee -a "$OUTPUT_FILE"

# 9. Recent Errors
echo "9. RECENT ERRORS" | tee -a "$OUTPUT_FILE"
echo "----------------" | tee -a "$OUTPUT_FILE"
echo "Last 10 errors from logs:" | tee -a "$OUTPUT_FILE"
tail -500 /tmp/openclaw/openclaw-*.log 2>/dev/null | grep -i "error\|failed\|timeout" | tail -10 | tee -a "$OUTPUT_FILE"
echo "" | tee -a "$OUTPUT_FILE"

# 10. LaunchAgent Status
echo "10. LAUNCHAGENT STATUS" | tee -a "$OUTPUT_FILE"
echo "----------------------" | tee -a "$OUTPUT_FILE"
launchctl list | grep openclaw | tee -a "$OUTPUT_FILE"
echo "" | tee -a "$OUTPUT_FILE"

# 11. Disk Usage
echo "11. DISK USAGE" | tee -a "$OUTPUT_FILE"
echo "--------------" | tee -a "$OUTPUT_FILE"
echo "OpenClaw directories:" | tee -a "$OUTPUT_FILE"
du -sh "$HOME/.openclaw" "$HOME/openclaw" 2>/dev/null | tee -a "$OUTPUT_FILE"

echo "" | tee -a "$OUTPUT_FILE"
echo "Largest subdirectories:" | tee -a "$OUTPUT_FILE"
du -sh "$HOME/.openclaw"/*/ 2>/dev/null | sort -rh | head -10 | tee -a "$OUTPUT_FILE"
echo "" | tee -a "$OUTPUT_FILE"

# 12. Summary and Recommendations
echo "12. SUMMARY AND RECOMMENDATIONS" | tee -a "$OUTPUT_FILE"
echo "-------------------------------" | tee -a "$OUTPUT_FILE"

ISSUES=0

if [ "$THREAD_COUNT" -gt 120 ]; then
    echo "⚠️  High thread count: Remove duplicate native modules" | tee -a "$OUTPUT_FILE"
    echo "   Run: rm -rf ~/.openclaw/npm/node_modules/@mariozechner/clipboard-darwin-universal/" | tee -a "$OUTPUT_FILE"
    ISSUES=$((ISSUES + 1))
fi

if [ -n "$AUTH_TIME" ] && [ "$AUTH_TIME" -gt 60000 ]; then
    echo "⚠️  Slow auth: Remove unused providers from openclaw.json" | tee -a "$OUTPUT_FILE"
    echo "   Review: jq '.models.providers | keys' ~/.openclaw/openclaw.json" | tee -a "$OUTPUT_FILE"
    ISSUES=$((ISSUES + 1))
fi

if [ "$LIVENESS_COUNT" -gt 10 ]; then
    echo "⚠️  Frequent liveness warnings: Check event loop blocking" | tee -a "$OUTPUT_FILE"
    echo "   Review: grep 'liveness warning' /tmp/openclaw/openclaw-*.log" | tee -a "$OUTPUT_FILE"
    ISSUES=$((ISSUES + 1))
fi

if [ "$LOCK_COUNT" -gt 0 ]; then
    echo "⚠️  Stale lock files: Remove and restart" | tee -a "$OUTPUT_FILE"
    echo "   Run: find ~/.openclaw -name '*.lock' -delete" | tee -a "$OUTPUT_FILE"
    ISSUES=$((ISSUES + 1))
fi

if [ "$ISSUES" -eq 0 ]; then
    echo "✓ No issues detected. OpenClaw Gateway appears healthy." | tee -a "$OUTPUT_FILE"
fi

echo "" | tee -a "$OUTPUT_FILE"
echo "========================================" | tee -a "$OUTPUT_FILE"
echo "Report saved to: $OUTPUT_FILE" | tee -a "$OUTPUT_FILE"
echo "" | tee -a "$OUTPUT_FILE"
echo "Next steps:" | tee -a "$OUTPUT_FILE"
echo "1. Review recommendations above" | tee -a "$OUTPUT_FILE"
echo "2. Apply fixes if issues found" | tee -a "$OUTPUT_FILE"
echo "3. Restart gateway: openclaw gateway restart" | tee -a "$OUTPUT_FILE"
echo "4. Re-run this script to verify improvements" | tee -a "$OUTPUT_FILE"
