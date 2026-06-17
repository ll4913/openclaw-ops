#!/usr/bin/env python3
"""
ACP/Claude Process Reaper — automated zombie cleanup.

Kills:
  1. Runaway test/QMD processes (vitest, bun qmd stuck in loops, >80% CPU for >5min)
  2. Stale standalone Claude CLI sessions (>24h, NOT ACP-managed)
  3. Orphaned Claude remote bridge servers (>12h, no active parent)
  4. Stale MC worktree node processes (>24h)
  5. Dead ACP lease entries
  6. Stuck MC guard hook loops (>80% CPU)

Preserves:
  - Active ACP sessions (leases in process-leases.json)
  - Claude Desktop app processes
  - OpenClaw gateway (pid in launchd)
  - Current Hermes LSP (fresh <2h)
  - Active worktree processes (<24h)

Usage:
  python3 acp_reaper.py              # dry-run by default
  python3 acp_reaper.py --execute    # actually kill
  python3 acp_reaper.py --json       # machine-readable output
"""

import subprocess, json, os, sys, re, time
from pathlib import Path
from datetime import datetime

DRY_RUN = '--execute' not in sys.argv
JSON_OUT = '--json' in sys.argv

home = Path.home()
LEASE_FILE = home / '.openclaw/acpx/process-leases.json'
REPORT = {'ts': datetime.now().isoformat(), 'dry_run': DRY_RUN, 'killed': [], 'cleaned_leases': [], 'cpu_bombs': [], 'summary': {}}

def etime_to_seconds(etime_str):
    """Convert ps etime format to seconds: DD-HH:MM:SS or HH:MM:SS or MM:SS"""
    etime_str = etime_str.strip()
    days = 0
    if '-' in etime_str:
        parts = etime_str.split('-', 1)
        days = int(parts[0])
        etime_str = parts[1]
    parts = etime_str.split(':')
    if len(parts) == 3:
        h, m, s = int(parts[0]), int(parts[1]), int(parts[2])
    elif len(parts) == 2:
        h, m, s = 0, int(parts[0]), int(parts[1])
    else:
        h, m, s = 0, 0, int(parts[0])
    return days * 86400 + h * 3600 + m * 60 + s

def get_all_procs():
    """Get all processes with pid, ppid, cpu, etime, command."""
    result = subprocess.run(
        ['ps', '-eo', 'pid,ppid,%cpu,etime,command'],
        capture_output=True, text=True, timeout=10
    )
    procs = []
    for line in result.stdout.strip().split('\n')[1:]:
        parts = line.strip().split(None, 4)
        if len(parts) < 5:
            continue
        pid, ppid, cpu, etime, cmd = parts
        try:
            procs.append({
                'pid': int(pid),
                'ppid': int(ppid),
                'cpu': float(cpu),
                'etime_s': etime_to_seconds(etime),
                'etime_raw': etime,
                'cmd': cmd,
            })
        except (ValueError, IndexError):
            continue
    return procs

def get_active_acp_pids():
    """Get PIDs from active ACP leases."""
    pids = set()
    if LEASE_FILE.exists():
        try:
            data = json.loads(LEASE_FILE.read_text())
            for lease in data.get('leases', []):
                pid = lease.get('rootPid')
                if pid:
                    try:
                        os.kill(pid, 0)
                        pids.add(pid)
                    except (ProcessLookupError, PermissionError):
                        pass
        except (json.JSONDecodeError, KeyError):
            pass
    return pids

def get_gateway_pid():
    """Get the OpenClaw gateway PID."""
    result = subprocess.run(['pgrep', '-f', 'openclaw.*gateway.*port'], capture_output=True, text=True, timeout=5)
    pids = set()
    for line in result.stdout.strip().split('\n'):
        if line.strip():
            try:
                pids.add(int(line.strip()))
            except ValueError:
                pass
    return pids

def get_children(pid, all_procs):
    """Get all descendant PIDs of a given process."""
    children = set()
    for p in all_procs:
        if p['ppid'] == pid and p['pid'] != pid:
            children.add(p['pid'])
            children.update(get_children(p['pid'], all_procs))
    return children

def pid_alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False

def kill_proc(pid, reason, signal='-TERM'):
    if pid_alive(pid):
        if not DRY_RUN:
            try:
                if signal == '-KILL':
                    os.kill(pid, 9)
                else:
                    os.kill(pid, 15)
            except (ProcessLookupError, PermissionError):
                pass
        REPORT['killed'].append({'pid': pid, 'reason': reason, 'signal': signal})
        return True
    return False

def main():
    all_procs = get_all_procs()
    active_acp_pids = get_active_acp_pids()
    gateway_pids = get_gateway_pid()
    
    protected_pids = set(active_acp_pids | gateway_pids)
    for pid in active_acp_pids:
        protected_pids.update(get_children(pid, all_procs))
    
    # Also protect Claude Desktop app
    for p in all_procs:
        if 'Claude.app' in p['cmd'] or 'Claude Helper' in p['cmd']:
            protected_pids.add(p['pid'])
    
    # Phase 1: CPU bombs (>80% CPU, known patterns)
    for p in all_procs:
        if p['pid'] in protected_pids:
            continue
        if p['cpu'] < 80:
            continue
        
        cmd = p['cmd']
        reason = None
        
        if 'vitest' in cmd and ('acpx' in cmd or 'test.ts' in cmd):
            reason = f"vitest loop ({p['cpu']}% CPU, age {p['etime_raw']})"
        elif 'bun' in cmd and 'qmd' in cmd and p['cpu'] > 90:
            reason = f"QMD bun loop ({p['cpu']}% CPU, age {p['etime_raw']})"
        elif 'default-checkout-cwd-guard' in cmd and p['cpu'] > 90:
            reason = f"MC guard hook loop ({p['cpu']}% CPU, age {p['etime_raw']})"
        elif 'node' in cmd and 'vitest' in cmd and '/tmp/openclaw-' in cmd:
            reason = f"node vitest loop ({p['cpu']}% CPU, age {p['etime_raw']})"
        
        if reason:
            REPORT['cpu_bombs'].append({'pid': p['pid'], 'cpu': p['cpu'], 'reason': reason})
            kill_proc(p['pid'], reason, signal='-KILL')
    
    # Phase 2: Stale standalone Claude (>24h, NOT ACP-managed)
    for p in all_procs:
        if p['pid'] in protected_pids:
            continue
        if p['etime_s'] < 86400:
            continue
        
        cmd = p['cmd']
        
        if re.match(r'^(claude|/opt/homebrew/bin/claude)', cmd) and 'stream-json' not in cmd and 'Claude.app' not in cmd:
            reason = f"stale standalone Claude (age {p['etime_raw']})"
            children = get_children(p['pid'], all_procs)
            kill_proc(p['pid'], reason)
            for cpid in children:
                if cpid not in protected_pids:
                    kill_proc(cpid, f"child of {reason}")
    
    # Phase 3: Orphaned remote bridges (>12h)
    for p in all_procs:
        if p['pid'] in protected_pids:
            continue
        if p['etime_s'] < 43200:
            continue
        
        cmd = p['cmd']
        
        if '.claude/remote/srv' in cmd and '/server' in cmd:
            reason = f"stale remote bridge (age {p['etime_raw']})"
            kill_proc(p['pid'], reason)
            if p['ppid'] and p['ppid'] not in protected_pids:
                parent_cmd = next((pp['cmd'] for pp in all_procs if pp['pid'] == p['ppid']), '')
                if '/usr/bin/login' in parent_cmd:
                    kill_proc(p['ppid'], f"login parent of {reason}")
        elif '/usr/bin/login' in cmd and '.claude/remote' in cmd and p['etime_s'] > 43200:
            children = get_children(p['pid'], all_procs)
            if not any(pid_alive(c) for c in children):
                reason = f"orphaned login for remote bridge (age {p['etime_raw']})"
                kill_proc(p['pid'], reason)
    
    # Phase 4: Stale worktree processes (>24h)
    for p in all_procs:
        if p['pid'] in protected_pids:
            continue
        if p['etime_s'] < 86400:
            continue
        
        cmd = p['cmd']
        
        if 'node' in cmd and '/private/tmp/mc-' in cmd:
            kill_proc(p['pid'], f"stale MC worktree process (age {p['etime_raw']})")
        elif 'node' in cmd and '/private/tmp/openclaw-' in cmd:
            kill_proc(p['pid'], f"stale openclaw worktree process (age {p['etime_raw']})")
    
    # Phase 5: Orphaned MCP servers (parent dead)
    for p in all_procs:
        if p['pid'] in protected_pids:
            continue
        cmd = p['cmd']
        if 'episodic-memory' in cmd and 'mcp-server' in cmd:
            if not pid_alive(p['ppid']):
                kill_proc(p['pid'], f"orphaned MCP server (parent {p['ppid']} dead)")
    
    # Phase 6: Stale LSP servers (>24h, multiple copies)
    lsp_procs = [p for p in all_procs if 'hermes/lsp' in p.get('cmd', '') and p['etime_s'] > 86400 and p['pid'] not in protected_pids]
    if len(lsp_procs) > 4:
        lsp_procs.sort(key=lambda p: p['etime_s'], reverse=True)
        for p in lsp_procs[4:]:
            kill_proc(p['pid'], f"stale duplicate LSP server (age {p['etime_raw']})")
    
    # Phase 7: Dead ACP leases
    if LEASE_FILE.exists():
        try:
            data = json.loads(LEASE_FILE.read_text())
            original_count = len(data.get('leases', []))
            active_leases = []
            for lease in data.get('leases', []):
                pid = lease.get('rootPid')
                if pid and pid_alive(pid):
                    active_leases.append(lease)
                else:
                    REPORT['cleaned_leases'].append({
                        'lease_id': lease.get('leaseId', '?')[:8],
                        'pid': pid,
                        'session': lease.get('sessionKey', '?'),
                    })
            if not DRY_RUN and len(active_leases) < original_count:
                data['leases'] = active_leases
                LEASE_FILE.write_text(json.dumps(data, indent=2))
        except (json.JSONDecodeError, KeyError):
            pass
    
    # Summary
    REPORT['summary'] = {
        'total_killed': len(REPORT['killed']),
        'cpu_bombs_defused': len(REPORT['cpu_bombs']),
        'leases_cleaned': len(REPORT['cleaned_leases']),
        'protected_pids': len(protected_pids),
    }
    
    if JSON_OUT:
        print(json.dumps(REPORT, ensure_ascii=False))
    else:
        mode = "🔍 DRY-RUN" if DRY_RUN else "🔪 EXECUTE"
        print(f"\n{mode} — ACP Reaper Report")
        print(f"{'='*50}")
        
        if REPORT['cpu_bombs']:
            print(f"\n🔥 CPU bombs defused: {len(REPORT['cpu_bombs'])}")
            for b in REPORT['cpu_bombs']:
                print(f"  PID {b['pid']} | {b['cpu']}% CPU | {b['reason']}")
        
        if REPORT['killed']:
            print(f"\n💀 Processes killed: {len(REPORT['killed'])}")
            for k in REPORT['killed']:
                print(f"  PID {k['pid']} | {k['reason']}")
        
        if REPORT['cleaned_leases']:
            print(f"\n📋 Dead leases cleaned: {len(REPORT['cleaned_leases'])}")
            for l in REPORT['cleaned_leases']:
                print(f"  {l['lease_id']}... | PID {l['pid']} | {l['session']}")
        
        if not REPORT['killed'] and not REPORT['cpu_bombs'] and not REPORT['cleaned_leases']:
            print("\n✅ All clean — nothing to reap.")
        
        s = REPORT['summary']
        print(f"\n📊 Summary: killed={s['total_killed']}, cpu_bombs={s['cpu_bombs_defused']}, leases={s['leases_cleaned']}, protected={s['protected_pids']}")

if __name__ == '__main__':
    main()
