import json
from functools import lru_cache
from typing import List, Dict, Tuple
from core.executor import safe_exec_json

@lru_cache(maxsize=1)
def fetch_official_providers() -> List[Dict]:
    """获取所有支持的模型供应商列表与详情"""
    ok, data = safe_exec_json(["models", "providers", "--json"])
    if ok and isinstance(data, list):
        return data
    elif ok and isinstance(data, dict):
        return data.get("providers", [])
    return []

def get_provider_names() -> List[str]:
    """仅返回供应商名称一览"""
    providers = fetch_official_providers()
    return [p.get("id") or p.get("name") for p in providers if (p.get("id") or p.get("name"))]

def fetch_models_for_provider(provider_id: str) -> List[str]:
    """获取特定供应商下的可选官方模型列表"""
    ok, data = safe_exec_json(["models", "list", provider_id, "--json"])
    if not ok:
        return []
    
    # 兼容处理基于 openclaw 具体返回的 json 结构
    if isinstance(data, list):
        return [m.get("id", "") for m in data]
    return data.get("models", [])
