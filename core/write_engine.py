"""WriteEngine - strong consistency writes with read-back verification."""
import json
from typing import Dict, Any, Tuple

from . import run_cli, run_cli_json, config, get_models_providers, set_models_providers


def _is_dry_run() -> bool:
    import os
    return os.environ.get("EASYCLAW_DRY_RUN", "0") == "1"


def is_dry_run() -> bool:
    return _is_dry_run()


def _path_for_model(key: str) -> str:
    # OpenClaw path parser 会把引号内容作为字面 key 存储，导致出现 "\"provider/model\""。
    # 这里使用 bracket + raw key，确保写入真实键名（例如 openrouter/xxx）。
    return f"agents.defaults.models[{key}]"


def _normalize_model_key(key: str) -> str:
    raw = str(key or "").strip()
    # 去除成对包裹引号（支持重复嵌套）
    while len(raw) >= 2 and raw[0] in ("'", '"') and raw[-1] == raw[0]:
        raw = raw[1:-1].strip()
    # 去除残留单边引号
    raw = raw.lstrip("'\"").rstrip("'\"").strip()
    return raw


def clean_quoted_model_keys() -> Tuple[bool, str]:
    """修复带引号/残留引号的模型键为标准 provider/model 形式。"""
    config.reload()
    models = config.data.get("agents", {}).get("defaults", {}).get("models", {}) or {}
    bad_keys = [k for k in list(models.keys()) if _normalize_model_key(k) != k]
    if not bad_keys:
        return True, ""

    # 直接修改配置文件，避免 CLI 卡住
    for k in bad_keys:
        fixed = _normalize_model_key(k)
        if not fixed:
            continue
        src = models.get(k, {})
        dst = models.get(fixed, {})
        if isinstance(src, dict) and isinstance(dst, dict):
            merged = dict(src)
            merged.update(dst)
            models[fixed] = merged
        else:
            models[fixed] = dst if fixed in models else src
        if k in models:
            del models[k]

    # 写入并校验
    config.save()
    config.reload()
    models = config.data.get("agents", {}).get("defaults", {}).get("models", {}) or {}
    if any(_normalize_model_key(k) != k for k in models.keys()):
        return False, "quoted keys remain after cleanup"
    return True, ""

def _read_models() -> Dict[str, Any]:
    config.reload()
    return config.data.get("agents", {}).get("defaults", {}).get("models", {}) or {}


def set_provider_config(provider: str, cfg: Dict[str, Any]) -> Tuple[bool, str]:
    """Write models.providers and verify."""
    if _is_dry_run():
        return True, "(dry-run)"

    payload = json.dumps(cfg or {})
    stdout, stderr, code = run_cli(["config", "set", "models.providers", payload])
    if code != 0:
        return False, stderr or stdout or "config set failed"

    # read-back verify
    result = run_cli_json(["config", "get", "models.providers"])
    if "error" in result:
        return False, result.get("error", "read-back failed")
    return True, ""


def upsert_provider_api_key(provider: str, api_key: str, default_base_url: str = "") -> Tuple[bool, str]:
    """写入 provider apiKey，并做强一致读回校验。"""
    if not provider:
        return False, "provider is required"
    if not api_key:
        return False, "api_key is required"
    if _is_dry_run():
        return True, "(dry-run)"

    providers_cfg = get_models_providers() or {}
    providers_cfg[provider] = providers_cfg.get(provider, {})
    cfg = providers_cfg[provider]
    if "models" not in cfg or not isinstance(cfg["models"], list):
        cfg["models"] = []
    cfg["apiKey"] = api_key
    if default_base_url and not cfg.get("baseUrl"):
        cfg["baseUrl"] = default_base_url

    if not set_models_providers(providers_cfg):
        return False, "config set failed"

    # read-back verify
    verified = (get_models_providers() or {}).get(provider, {})
    readback_key = str(verified.get("apiKey", "") or "")
    if not readback_key:
        return False, "read-back failed: apiKey missing"
    # OpenClaw 可能返回脱敏值，例如 "__OPENCLAW_REDACTED__"。
    if readback_key != api_key and "REDACTED" not in readback_key.upper():
        return False, "read-back failed: apiKey mismatch"
    if default_base_url and not verified.get("baseUrl"):
        return False, "read-back failed: baseUrl missing"
    return True, ""


def activate_model(key: str) -> Tuple[bool, str]:
    if _is_dry_run():
        return True, "(dry-run)"

    path = _path_for_model(key)
    stdout, stderr, code = run_cli(["config", "set", path, "{}", "--json"])
    if code == 0:
        models = _read_models()
        if key in models:
            return True, ""

    # 兜底：直接编辑配置文件，规避 path 解析边界场景
    try:
        config.reload()
        agents = config.data.setdefault("agents", {})
        defaults = agents.setdefault("defaults", {})
        models = defaults.setdefault("models", {})
        if not isinstance(models, dict):
            defaults["models"] = {}
            models = defaults["models"]
        models[key] = models.get(key, {}) or {}
        config.save()
        config.reload()
        models = config.data.get("agents", {}).get("defaults", {}).get("models", {}) or {}
        if key in models:
            return True, "(added via direct edit)"
    except Exception:
        pass

    if code != 0:
        return False, stderr or stdout or "config set failed"
    return False, "read-back failed: model not found"


def deactivate_model(key: str) -> Tuple[bool, str]:
    if _is_dry_run():
        return True, "(dry-run)"

    path = _path_for_model(key)
    stdout, stderr, code = run_cli(["config", "unset", path])
    if code != 0:
        # 兜底：直接编辑配置文件
        config.reload()
        models = config.data.get("agents", {}).get("defaults", {}).get("models", {}) or {}
        if key in models:
            del models[key]
            config.save()
            config.reload()
            models = config.data.get("agents", {}).get("defaults", {}).get("models", {}) or {}
            if key not in models:
                return True, "(removed via direct edit)"
            return False, "direct edit failed"

        # 如果路径不存在，视为已删除
        if "Config path not found" in (stderr or ""):
            return True, "(already removed)"
        return False, stderr or stdout or "config unset failed"

    models = _read_models()
    if key in models:
        return False, "read-back failed: model still present"
    return True, ""
