#!/bin/bash
# Bulk cleanup invalid auth profiles across ALL OpenClaw agents.
# Usage: bash oc-auth-profile-cleanup.sh [provider] [keep_profile]
#   provider: defaults to "anthropic"
#   keep_profile: defaults to "anthropic:default"
#
# This script:
# 1. Backs up each agent's auth-profiles.json
# 2. Removes all profiles matching the provider EXCEPT the keep_profile
# 3. Reports what was removed
#
# Safe to run multiple times — idempotent, skips agents with no matching profiles.

set -euo pipefail

PROVIDER="${1:-anthropic}"
KEEP="${2:-${PROVIDER}:default}"
AGENTS_DIR="$HOME/.openclaw/agents"
BACKUP_SUFFIX=".bak.auth-cleanup-$(date +%Y%m%d-%H%M%S)"
DRY_RUN="${DRY_RUN:-false}"

echo "=== Cross-Agent Auth Profile Cleanup ==="
echo "Provider: $PROVIDER"
echo "Keep: $KEEP"
echo "Dry run: $DRY_RUN"
echo ""

total_removed=0
agents_touched=0

for profile_file in "$AGENTS_DIR"/*/agent/auth-profiles.json; do
    [ -f "$profile_file" ] || continue
    agent=$(echo "$profile_file" | sed "s|.*/agents/||; s|/agent/.*||")

    result=$(python3 -c "
import json, sys

with open('$profile_file') as f:
    data = json.load(f)

profiles = data.get('profiles', {})
keep = '$KEEP'
provider = '$PROVIDER'

to_remove = []
for name, profile in list(profiles.items()):
    if not isinstance(profile, dict):
        continue
    if name == keep:
        continue
    p_provider = profile.get('provider', '')
    if provider in name or provider in p_provider:
        to_remove.append(name)

if not to_remove:
    sys.exit(0)

for name in to_remove:
    del profiles[name]

data['profiles'] = profiles

if '$DRY_RUN' == 'true':
    for name in to_remove:
        print(f'  [DRY] Would remove: {name}')
else:
    # Backup
    import shutil
    shutil.copy2('$profile_file', '$profile_file$BACKUP_SUFFIX')
    with open('$profile_file', 'w') as f:
        json.dump(data, f, indent=2)
    for name in to_remove:
        print(f'  Removed: {name}')

print(f'COUNT={len(to_remove)}')
" 2>/dev/null)

    count=$(echo "$result" | grep "^COUNT=" | cut -d= -f2)
    if [ -n "$count" ] && [ "$count" -gt 0 ]; then
        echo "[$agent] ($count profiles)"
        echo "$result" | grep -v "^COUNT="
        total_removed=$((total_removed + count))
        agents_touched=$((agents_touched + 1))
    fi
done

echo ""
echo "=== Summary ==="
echo "Agents touched: $agents_touched"
echo "Profiles removed: $total_removed"
if [ "$DRY_RUN" = "true" ]; then
    echo "(Dry run — no files modified. Re-run without DRY_RUN=true to apply.)"
else
    echo "Backups created with suffix: $BACKUP_SUFFIX"
fi
