"""DataSource for model lists (official/custom)."""
import json
import urllib.request
import urllib.error
from typing import Any, List, Dict, Tuple
import os

from . import run_cli
from .agent_runtime import resolve_agent_runtime_paths

MODELS_JSON_PATH = os.environ.get(
    "OPENCLAW_MODELS_JSON",
    resolve_agent_runtime_paths("main", os.environ.get("OPENCLAW_CONFIG_PATH", "/root/.openclaw/openclaw.json"))["models_json"],
)




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
        # 自定义端点返回 "vendor/model" 时，也要归属到当前 provider。
        if not str(key).startswith(f"{provider}/"):
            key = f"{provider}/{key}"
        out.append({
            "key": key,
            "name": m.get("name") or m.get("id") or key,
            "raw": m,
        })
    return out


def get_official_models(provider: str) -> List[Dict]:
    # 优先实时查询 CLI，避免被本地缓存的 models.json（例如仅含 openrouter/auto）误导
    stdout, stderr, code = run_cli(["models", "list", "--all", "--provider", provider, "--json"])
    if code == 0 and stdout:
        try:
            data = json.loads(stdout)
            models = _normalize_models(data.get("models", []), provider)
            if models:
                return models
        except Exception:
            pass

    # fallback 到 models.json（离线/CLI 失败场景）
    models = _load_models_json_provider(provider)
    if models:
        return _normalize_models(models, provider)
    return []


def get_custom_models(provider: str, base_url: str, api_key: str = "") -> List[Dict]:
    base = base_url.rstrip("/")
    if base.endswith("/v1"):
        models_url = base + "/models"
    else:
        models_url = base + "/v1/models"

    req = urllib.request.Request(models_url)
    # 部分网关/WAF 会拦截无 User-Agent 的请求（返回 403/1010）。
    req.add_header("User-Agent", "clawpanel-model-discovery/1.0")
    req.add_header("Accept", "application/json")
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


def _build_endpoint(base_url: str, suffix: str) -> str:
    base = (base_url or "").strip().rstrip("/")
    if base.endswith("/v1"):
        return f"{base}{suffix}"
    return f"{base}/v1{suffix}"


def _http_json_post(url: str, payload: Dict[str, Any], headers: Dict[str, str], timeout: int = 12) -> Tuple[bool, str]:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
    )
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "application/json")
    req.add_header("User-Agent", "clawpanel-responses-probe/1.0")
    for k, v in (headers or {}).items():
        if v:
            req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            _ = resp.read()
        return True, ""
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            raw = e.read().decode("utf-8", errors="ignore").strip()
            detail = raw[:280]
        except Exception:
            detail = ""
        if detail:
            return False, f"HTTP {e.code}: {detail}"
        return False, f"HTTP {e.code}: {e.reason}"
    except Exception as e:
        return False, str(e)


def _discover_probe_model(base_url: str, api_key: str = "") -> str:
    models_url = _build_endpoint(base_url, "/models")
    req = urllib.request.Request(models_url)
    req.add_header("User-Agent", "clawpanel-responses-probe/1.0")
    req.add_header("Accept", "application/json")
    if api_key:
        req.add_header("Authorization", f"Bearer {api_key}")
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="ignore"))
        for row in data.get("data", []) if isinstance(data, dict) else []:
            if not isinstance(row, dict):
                continue
            mid = str(row.get("id") or row.get("name") or "").strip()
            if mid:
                return mid
    except Exception:
        return ""
    return ""


def probe_openai_responses_input_mode(base_url: str, api_key: str = "", model: str = "") -> Dict[str, Any]:
    """
    Probe whether /v1/responses accepts string input, array input, or both.

    Returns:
      {
        "detectedMode": "array|string|both|none",
        "stringOk": bool,
        "arrayOk": bool,
        "stringError": str,
        "arrayError": str,
        "model": str,
        "endpoint": str,
      }
    """
    base = (base_url or "").strip()
    if not base:
        return {
            "detectedMode": "none",
            "stringOk": False,
            "arrayOk": False,
            "stringError": "baseUrl is required",
            "arrayError": "baseUrl is required",
            "model": "",
            "endpoint": "",
        }

    model_id = (model or "").strip() or _discover_probe_model(base, api_key=api_key)
    endpoint = _build_endpoint(base, "/responses")
    if not model_id:
        return {
            "detectedMode": "none",
            "stringOk": False,
            "arrayOk": False,
            "stringError": "unable to resolve probe model",
            "arrayError": "unable to resolve probe model",
            "model": "",
            "endpoint": endpoint,
        }

    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    string_payload = {
        "model": model_id,
        "input": "ping",
        "max_output_tokens": 16,
    }
    array_payload = {
        "model": model_id,
        "input": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": "ping",
                    }
                ],
            }
        ],
        "max_output_tokens": 16,
    }

    string_ok, string_err = _http_json_post(endpoint, string_payload, headers, timeout=12)
    array_ok, array_err = _http_json_post(endpoint, array_payload, headers, timeout=12)

    detected = "none"
    if string_ok and array_ok:
        detected = "both"
    elif array_ok:
        detected = "array"
    elif string_ok:
        detected = "string"

    return {
        "detectedMode": detected,
        "stringOk": bool(string_ok),
        "arrayOk": bool(array_ok),
        "stringError": str(string_err or ""),
        "arrayError": str(array_err or ""),
        "model": model_id,
        "endpoint": endpoint,
    }
