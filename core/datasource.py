"""DataSource for model lists (official/custom)."""
import json
import urllib.request
import urllib.error
from typing import List, Dict
import os

from . import run_cli

MODELS_JSON_PATH = os.environ.get("OPENCLAW_MODELS_JSON", "/root/.openclaw/agents/main/agent/models.json")




def _ensure_models_json():
    if os.path.exists(MODELS_JSON_PATH):
        return
    # trigger OpenClaw to generate models.json
    run_cli(["models", "status", "--json"])
    run_cli(["models", "list", "--all", "--json"])


def _load_models_json_provider(provider: str) -> List[Dict]:
    _ensure_models_json()
    if not os.path.exists(MODELS_JSON_PATH):
        return []
    try:
        with open(MODELS_JSON_PATH, "r") as f:
            data = json.load(f)
        prov = data.get("providers", {}).get(provider) or data.get("providers", {}).get(provider.lower())
        if not prov:
            return []
        models = prov.get("models", []) or []
        return models
    except Exception:
        return []

def _normalize_models(models: List[Dict], provider: str) -> List[Dict]:
    out = []
    for m in models:
        key = m.get("key") or m.get("id") or m.get("name")
        if not key:
            continue
        if "/" not in key:
            key = f"{provider}/{key}"
        out.append({
            "key": key,
            "name": m.get("name") or m.get("id") or key,
            "raw": m,
        })
    return out


def get_official_models(provider: str) -> List[Dict]:
    # 优先读 models.json（官方链路）
    models = _load_models_json_provider(provider)
    if models:
        return _normalize_models(models, provider)
    # fallback to CLI
    stdout, stderr, code = run_cli(["models", "list", "--all", "--provider", provider, "--json"])
    if code != 0 or not stdout:
        return []
    data = json.loads(stdout)
    return _normalize_models(data.get("models", []), provider)


def get_custom_models(provider: str, base_url: str, api_key: str = "") -> List[Dict]:
    base = base_url.rstrip("/")
    if base.endswith("/v1"):
        models_url = base + "/models"
    else:
        models_url = base + "/v1/models"

    req = urllib.request.Request(models_url)
    if api_key:
        req.add_header("Authorization", f"Bearer {api_key}")

    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read().decode())

    models = []
    for m in data.get("data", []):
        model_id = m.get("id") or m.get("name")
        if model_id:
            models.append({"key": model_id, "name": model_id})

    return _normalize_models(models, provider)
