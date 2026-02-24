"""WriteEngine - strong consistency writes with read-back verification."""
import json
from typing import Dict, Any, Tuple

from . import run_cli, run_cli_json, config


def _is_dry_run() -> bool:
    import os
    return os.environ.get("EASYCLAW_DRY_RUN", "0") == "1"


def is_dry_run() -> bool:
    return _is_dry_run()


def _path_for_model(key: str) -> str:
    return f'agents.defaults.models["{key}"]'


def clean_quoted_model_keys() -> Tuple[bool, str]:
    """修复带引号的模型键："provider/model" -> provider/model"""
    config.reload()
    models = config.data.get("agents", {}).get("defaults", {}).get("models", {}) or {}
    bad_keys = [k for k in models.keys() if k.startswith('"') and k.endswith('"')]
    if not bad_keys:
        return True, ""

    # 直接修改配置文件，避免 CLI 卡住
    for k in bad_keys:
        fixed = k.strip('"')
        models[fixed] = models.get(k, {})
        if k in models:
            del models[k]

    # 写入并校验
    config.save()
    config.reload()
    models = config.data.get("agents", {}).get("defaults", {}).get("models", {}) or {}
    if any(k.startswith('"') and k.endswith('"') for k in models.keys()):
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
    stdout, stderr, code = run_cli(["config", "set", "models.providers", payload, "--json"])
    if code != 0:
        return False, stderr or stdout or "config set failed"

    # read-back verify
    result = run_cli_json(["config", "get", "models.providers"])
    if "error" in result:
        return False, result.get("error", "read-back failed")
    return True, ""


def activate_model(key: str) -> Tuple[bool, str]:
    if _is_dry_run():
        return True, "(dry-run)"

    path = _path_for_model(key)
    stdout, stderr, code = run_cli(["config", "set", path, "{}", "--json"])
    if code != 0:
        return False, stderr or stdout or "config set failed"

    models = _read_models()
    if key not in models:
        return False, "read-back failed: model not found"
    return True, ""


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
