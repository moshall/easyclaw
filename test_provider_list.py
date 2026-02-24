#!/usr/bin/env python3
"""
测试获取服务商列表
"""
import json
import sys
sys.path.insert(0, '/root/.openclaw/software/easyclaw')

from core import run_cli_json, run_cli

print("测试获取服务商列表...")
stdout, stderr, code = run_cli(['models', 'list', '--all', '--json'])
print(f"Exit code: {code}")

if code == 0 and stdout:
    try:
        data = json.loads(stdout)
        models = data.get('models', [])
        print(f"Total models: {len(models)}")
        
        providers = set()
        for m in models:
            key = m.get('key', '')
            if '/' in key:
                provider = key.split('/')[0]
                providers.add(provider)
        
        print(f"Providers found: {sorted(providers)}")
        print(f"Total providers: {len(providers)}")
        
    except Exception as e:
        print(f"Error parsing JSON: {e}")
        print(f"Stdout: {stdout[:1000]}")
else:
    print(f"Error: {stderr}")
