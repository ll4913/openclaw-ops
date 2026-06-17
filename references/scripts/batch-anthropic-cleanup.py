#!/usr/bin/env python3
"""Batch cleanup of invalid Anthropic profiles across all OpenClaw agents.

Removes all anthropic:* profiles except anthropic:default from every agent's
auth-profiles.json. Creates backups before modifying.

Usage:
    python3 batch-anthropic-cleanup.py [--dry-run]

Discovered 2026-05-29: 68 invalid profiles across 16 agents, all causing
event loop blocking via auth re-warm cycles (162s each).
"""
import json
import os
import glob
import shutil
import sys
from datetime import datetime

DRY_RUN = "--dry-run" in sys.argv
AGENTS_DIR = os.path.expanduser("~/.openclaw/agents")
BACKUP_TS = datetime.now().strftime("%Y%m%d-%H%M%S")
KEEP_PROFILES = {"anthropic:default"}

results = []
total_removed = 0

for auth_file in sorted(glob.glob(f"{AGENTS_DIR}/*/agent/auth-profiles.json")):
    agent = auth_file.split("/agents/")[1].split("/")[0]

    try:
        with open(auth_file) as f:
            data = json.load(f)
    except Exception as e:
        results.append(f"  ⚠️  {agent}: read error: {e}")
        continue

    profiles = data.get("profiles", {})
    removed = []
    kept = []

    for name in list(profiles.keys()):
        if not isinstance(profiles[name], dict):
            continue
        if "anthropic" not in name:
            continue
        if name in KEEP_PROFILES:
            kept.append(name)
            continue
        removed.append(name)

    if not removed:
        results.append(f"  ⏭️  {agent}: clean")
        continue

    if DRY_RUN:
        results.append(f"  🔍 {agent}: would remove {len(removed)} profiles: {', '.join(removed)}")
        total_removed += len(removed)
        continue

    # Backup
    backup_path = f"{auth_file}.bak.{BACKUP_TS}"
    shutil.copy2(auth_file, backup_path)

    # Remove invalid profiles
    for name in removed:
        del profiles[name]

    data["profiles"] = profiles
    with open(auth_file, "w") as f:
        json.dump(data, f, indent=2)

    total_removed += len(removed)
    results.append(f"  ✅ {agent}: removed {len(removed)}, kept {kept or ['none']}")

print(f"=== Anthropic Profile Batch Cleanup ({'DRY RUN' if DRY_RUN else 'LIVE'}) ===\n")
for r in results:
    print(r)

agents_cleaned = sum(1 for r in results if "removed" in r or "would remove" in r)
print(f"\nTotal: {agents_cleaned} agents × profiles = {total_removed} invalid profiles")

if DRY_RUN:
    print("\nRun without --dry-run to apply changes.")
    print("Then: openclaw gateway restart")
