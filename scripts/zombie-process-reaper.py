#!/usr/bin/env python3
"""Zombie process reaper for OpenClaw gateway child processes.

Detects orphan processes (parent PID = 1) that belong to OpenClaw's
ecosystem (codex app-server, gbrain serve, solmem-mcp) and kills them.
Also detects excessive duplicate processes even if not orphaned.

Silent when clean. Outputs report only when issues found.

Usage in Hermes cron:
  cronjob action=create name=zombie-process-reaper schedule='every 30m'
    prompt='python3 ~/.hermes/scripts/zombie-process-reaper.py'
"""

import os, subprocess, json
from datetime import datetime

REPORT_DIR = os.path.expanduser("~/.openclaw/cron/reports")

PATTERNS = [
    ("codex app-server", "codex app-server.*stdio"),
    ("gbrain serve", "gbrain serve"),
    ("solmem-mcp", "solmem-mcp.*dist/index"),
]

MAX_INSTANCES = {
    "codex app-server": 6,
    "gbrain serve": 3,
    "solmem-mcp": 3,
}


def run(args):
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=10)
        return r.stdout.strip()
    except Exception:
        return ""


def get_processes(pattern):
    output = run(["pgrep", "-f", pattern])
    if not output:
        return []
    procs = []
    for pid_str in output.split("\n"):
        pid_str = pid_str.strip()
        if not pid_str:
            continue
        try:
            pid = int(pid_str)
            info = run(["ps", "-p", str(pid), "-o", "ppid=,pcpu=,rss="])
            if info:
                parts = info.split()
                ppid = int(parts[0]) if parts else 0
                cpu = float(parts[1]) if len(parts) > 1 else 0
                rss = int(parts[2]) if len(parts) > 2 else 0
                procs.append({"pid": pid, "ppid": ppid, "cpu": cpu, "rss": rss})
        except (ValueError, IndexError):
            continue
    return procs


def main():
    killed = []

    for name, pattern in PATTERNS:
        procs = get_processes(pattern)
        max_allowed = MAX_INSTANCES.get(name, 3)

        # Kill orphans (parent PID = 1)
        orphans = [p for p in procs if p["ppid"] == 1]
        for p in orphans:
            try:
                os.kill(p["pid"], 9)
                killed.append({"name": name, "pid": p["pid"], "reason": "orphan"})
            except OSError:
                pass

        # Kill excess (oldest first)
        remaining = [p for p in procs if p["pid"] not in [k["pid"] for k in killed]]
        if len(remaining) > max_allowed:
            remaining.sort(key=lambda p: p["pid"])
            for p in remaining[:len(remaining) - max_allowed]:
                try:
                    os.kill(p["pid"], 9)
                    killed.append({"name": name, "pid": p["pid"], "reason": "excess"})
                except OSError:
                    pass

    if not killed:
        return  # Silent when clean

    os.makedirs(REPORT_DIR, exist_ok=True)
    report = {
        "timestamp": datetime.now().isoformat(),
        "killed": len(killed),
        "details": killed,
    }
    with open(os.path.join(REPORT_DIR, "zombie-reaper.json"), "w") as f:
        json.dump(report, f, indent=2)

    print(f"Zombie Reaper: killed {len(killed)} orphan process(es)")
    for k in killed:
        print(f"  - {k['name']} PID={k['pid']} reason={k['reason']}")


if __name__ == "__main__":
    main()
