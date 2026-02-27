import subprocess
import json
import sys
sys.path.append("/easyclaw")
from core import OPENCLAW_BIN
from core.write_engine import run_cli

key = "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"
provider = "openrouter"

print("1. Running paste-token directly...")
cmd = [OPENCLAW_BIN, "models", "auth", "paste-token", "--provider", provider, "--profile-id", provider]
p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
stdout, stderr = p.communicate(input=key + "\n")
print(f"STDOUT: {stdout}")
print(f"STDERR: {stderr}")

print("2. Dumping all config")
out, err, code = run_cli(["config", "get"])
print(f"Global Config: {out}")
