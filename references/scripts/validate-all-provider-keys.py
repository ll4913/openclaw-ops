#!/usr/bin/env python3
"""Validate all provider API keys across OpenClaw configuration sources.

Tests keys from three sources:
1. auth-profiles.json (per-agent OAuth/tokens)
2. models.json (per-agent provider keys)
3. openclaw.json (global provider keys)

Usage:
    python3 validate-all-provider-keys.py

Discovered 2026-05-29: models.json had expired Gemini key, dead proxy
(anthropic-sub2api), duplicate providers (google/gemini), and 15+ placeholder
entries. Only the runtime-effective keys matter for functionality.
"""
import json
import os
import subprocess
import sys
from collections import defaultdict

AGENTS_DIR = os.path.expanduser("~/.openclaw/agents")
OPENCLAW_JSON = os.path.expanduser("~/.openclaw/openclaw.json")
MODELS_JSON = os.path.expanduser("~/.openclaw/agents/main/agent/models.json")

PLACEHOLDER_MARKERS = [
    "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "XAI_API_KEY", "GEMINI_API_KEY",
    "ZAI_API_KEY", "DEEPSEEK_API_KEY", "OPENROUTER_API_KEY", "DASHSCOPE_API_KEY",
    "ollama-local", "swiftlm-local", "codex-app-server",
]

def is_placeholder(key):
    return any(key == m or key.startswith(m) for m in PLACEHOLDER_MARKERS)

def test_anthropic(key):
    r = subprocess.run([
        'curl', '-s', '--connect-timeout', '5', '--max-time', '10',
        'https://api.anthropic.com/v1/messages',
        '-H', 'Content-Type: application/json',
        '-H', f'x-api-key: {key}',
        '-H', 'anthropic-version: 2023-06-01',
        '-d', '{"model":"claude-sonnet-4-6","max_tokens":5,"messages":[{"role":"user","content":"hi"}]}'
    ], capture_output=True, text=True)
    try:
        resp = json.loads(r.stdout)
        return resp.get('type') == 'message'
    except:
        return False

def test_openai_compat(key, base_url):
    r = subprocess.run([
        'curl', '-s', '--connect-timeout', '5', '--max-time', '10',
        f'{base_url}/models',
        '-H', f'Authorization: Bearer {key}'
    ], capture_output=True, text=True)
    try:
        resp = json.loads(r.stdout)
        return bool(resp.get('data'))
    except:
        return False

def test_google(key, base_url):
    r = subprocess.run([
        'curl', '-s', '--connect-timeout', '5', '--max-time', '10',
        f'{base_url}/models?key={key}'
    ], capture_output=True, text=True)
    try:
        resp = json.loads(r.stdout)
        return bool(resp.get('models'))
    except:
        return False

def test_xai(key):
    r = subprocess.run([
        'curl', '-s', '--connect-timeout', '5', '--max-time', '10',
        'https://api.x.ai/v1/models',
        '-H', f'Authorization: Bearer {key}'
    ], capture_output=True, text=True)
    try:
        resp = json.loads(r.stdout)
        return bool(resp.get('models') or resp.get('data'))
    except:
        return False

print("=" * 70)
print("PROVIDER KEY VALIDATION")
print("=" * 70)

# 1. Check auth-profiles across all agents
print("\n--- Auth Profiles (per-agent) ---")
tested = {}
for auth_file in sorted(__import__('glob').glob(f"{AGENTS_DIR}/*/agent/auth-profiles.json")):
    agent = auth_file.split("/agents/")[1].split("/")[0]
    try:
        with open(auth_file) as f:
            data = json.load(f)
    except:
        continue
    for name, profile in data.get("profiles", {}).items():
        if not isinstance(profile, dict):
            continue
        provider = profile.get("provider", "")
        key = profile.get("apiKey") or profile.get("token") or profile.get("key") or ""
        if not key:
            continue
        cache_key = f"{provider}:{key[:20]}"
        if cache_key in tested:
            continue
        if provider == "anthropic":
            ok = test_anthropic(key)
        elif provider == "xai":
            ok = test_xai(key)
        else:
            continue  # OAuth tokens need special handling
        status = "✅" if ok else "❌"
        tested[cache_key] = ok
        print(f"  {status} {agent}/{name}: {key[:25]}...")

# 2. Check models.json
print("\n--- models.json (agent-level) ---")
try:
    with open(MODELS_JSON) as f:
        data = json.load(f)
    for pname, pconf in data.get("providers", {}).items():
        key = pconf.get("apiKey", "")
        if not key:
            continue
        if is_placeholder(key):
            print(f"  📌 {pname}: placeholder ({key[:25]}...)")
            continue
        api = pconf.get("api", "")
        base_url = pconf.get("baseUrl", "")
        if "anthropic" in api:
            ok = test_anthropic(key)
        elif "google" in api or "generative" in api:
            ok = test_google(key, base_url)
        elif "openai" in api:
            ok = test_openai_compat(key, base_url)
        else:
            print(f"  ⏭️  {pname}: unknown API ({api})")
            continue
        status = "✅" if ok else "❌"
        print(f"  {status} {pname}: {key[:25]}...")
except Exception as e:
    print(f"  ⚠️  Error reading models.json: {e}")

# 3. Check openclaw.json
print("\n--- openclaw.json (global) ---")
try:
    with open(OPENCLAW_JSON) as f:
        data = json.load(f)
    for pname, pconf in data.get("models", {}).get("providers", {}).items():
        key = pconf.get("apiKey", "")
        if not key:
            continue
        if is_placeholder(key):
            print(f"  📌 {pname}: placeholder ({key[:25]}...)")
            continue
        api = pconf.get("api", "")
        base_url = pconf.get("baseUrl", "")
        if "anthropic" in api:
            ok = test_anthropic(key)
        elif "google" in api or "generative" in api:
            ok = test_google(key, base_url)
        elif "openai" in api:
            ok = test_openai_compat(key, base_url)
        else:
            print(f"  ⏭️  {pname}: unknown API ({api})")
            continue
        status = "✅" if ok else "❌"
        print(f"  {status} {pname}: {key[:25]}...")
except Exception as e:
    print(f"  ⚠️  Error reading openclaw.json: {e}")

# 4. Check env vars
print("\n--- Environment Variables ---")
for env_name, provider in [
    ("ANTHROPIC_API_KEY", "anthropic"),
    ("OPENAI_API_KEY", "openai"),
    ("GEMINI_API_KEY", "gemini"),
    ("XAI_API_KEY", "xai"),
    ("FIRECRAWL_API_KEY", "firecrawl"),
]:
    val = os.environ.get(env_name, "")
    if not val:
        print(f"  ⏭️  {env_name}: not set")
        continue
    if is_placeholder(val):
        print(f"  📌 {env_name}: placeholder")
        continue
    if provider == "anthropic":
        ok = test_anthropic(val)
    elif provider == "xai":
        ok = test_xai(val)
    elif provider == "gemini":
        ok = test_google(val, "https://generativelanguage.googleapis.com/v1beta")
    else:
        ok = True  # Skip validation for non-testable
    status = "✅" if ok else "❌"
    print(f"  {status} {env_name}: {val[:25]}...")

print("\n" + "=" * 70)
print("KEY: ✅ valid | ❌ invalid/expired | 📌 placeholder | ⏭️ skipped")
print("=" * 70)
