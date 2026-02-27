import sys
import subprocess
import json

sys.path.append("/easyclaw")
from core import OPENCLAW_BIN, get_models_providers
from core.write_engine import run_cli

print("--- Testing OpenRouter in Docker ---")

key = "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"
provider = "openrouter"

print(f"1. Binding API key via {OPENCLAW_BIN} paste-token")
cmd = [OPENCLAW_BIN, "models", "auth", "paste-token", "--provider", provider, "--profile-id", provider]
p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
stdout, stderr = p.communicate(input=key + "\n")
print("STDOUT:", stdout.strip())
if stderr.strip():
    print("STDERR:", stderr.strip())

print("\n2. Checking OpenRouter config in core using get_models_providers()")
cfg = get_models_providers()
or_cfg = cfg.get(provider, {})
print("Config:", json.dumps(or_cfg, indent=2, ensure_ascii=False))

print("\n3. Testing CLI model sync for OpenRouter")
# Let's directly call our auto_discover_models logic using the real CLI if needed, or using Python tui logic.
# Wait, auto_discover_models requires `console.print`, let's mock rich to avoid TUI interaction breaking terminal
# We can just import and run it
try:
    from tui.inventory import auto_discover_models
    import builtins
    
    # Mock 'pause_enter' so it doesn't block
    import tui.inventory
    tui.inventory.pause_enter = lambda: None
    
    # Also mock 'Prompt.ask' if it gets called, though it shouldn't if auto_discover works
    
    print("\nCalling auto_discover_models('openrouter')...")
    auto_discover_models("openrouter")
    
    print("\n4. Checking config after auto discover")
    cfg2 = get_models_providers()
    or_cfg2 = cfg2.get(provider, {})
    models = or_cfg2.get("models", [])
    print(f"Total models discovered: {len(models)}")
    if models:
        print(f"Top 5 models: {[m['id'] for m in models[:5]]}")
        
    print("\n5. Checking CLI 'openclaw models list'")
    out, err, code = run_cli(["models", "list", "openrouter"])
    if out:
        lines = out.strip().split('\n')
        print(f"CLI stdout (first 5 lines):")
        for line in lines[:5]:
            print(f"  {line}")
    if err:
        print(f"CLI stderr: {err.strip()}")
        
except Exception as e:
    print(f"Exception during auto discover: {e}")

