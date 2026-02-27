"""
扩展搜索源适配层（Zhipu / Serper / Tavily）
提供配置持久化、连通测试与统一结果格式转换。
"""
import json
import os
import time
from typing import Dict, List, Tuple
from urllib import request, error
from urllib.parse import quote


DEFAULT_SEARCH_ADAPTERS_PATH = os.environ.get(
    "OPENCLAW_SEARCH_ADAPTERS_PATH",
    "/root/.openclaw/easyclaw/search_adapters.json",
)

ADAPTER_SPECS: Dict[str, Dict] = {
    "zhipu": {
        "label": "智谱 Web Search",
        "envKeys": ["ZHIPU_API_KEY"],
        # 允许用户改成文档中的最新 endpoint
        "defaultBaseUrl": "https://open.bigmodel.cn/api/paas/v4/web_search",
    },
    "serper": {
        "label": "Serper",
        "envKeys": ["SERPER_API_KEY"],
        "defaultBaseUrl": "https://google.serper.dev/search",
    },
    "tavily": {
        "label": "Tavily",
        "envKeys": ["TAVILY_API_KEY"],
        "defaultBaseUrl": "https://api.tavily.com/search",
    },
}

_COOLDOWN_UNTIL: Dict[str, float] = {}
_SOURCE_COOLDOWN_UNTIL: Dict[str, float] = {}
OFFICIAL_SEARCH_SOURCES = ["official:brave", "official:perplexity", "official:grok", "official:gemini", "official:kimi"]
DEFAULT_OPENCLAW_CONFIG_PATH = os.environ.get("OPENCLAW_CONFIG_PATH", "/root/.openclaw/openclaw.json")


def clear_failover_runtime_state():
    """清理内存态（测试/调试用）"""
    _COOLDOWN_UNTIL.clear()
    _SOURCE_COOLDOWN_UNTIL.clear()


def _default_config() -> Dict:
    providers = {}
    for pid, spec in ADAPTER_SPECS.items():
        providers[pid] = {
            "enabled": False,
            "apiKey": "",
            "baseUrl": spec.get("defaultBaseUrl", ""),
            "model": "",
            "topK": 5,
        }
    return {
        "active": "",
        "primary": "",
        "fallbacks": [],
        "primarySource": "",
        "fallbackSources": [],
        "activeSource": "",
        "providers": providers,
    }


def _ensure_parent_dir(path: str):
    parent = os.path.dirname(path)
    if parent and not os.path.exists(parent):
        os.makedirs(parent, exist_ok=True)


def load_search_adapters(path: str = DEFAULT_SEARCH_ADAPTERS_PATH) -> Dict:
    if not os.path.exists(path):
        cfg = _default_config()
        save_search_adapters(cfg, path=path)
        return cfg
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError("invalid config")
    except Exception:
        data = _default_config()
        save_search_adapters(data, path=path)
        return data

    merged = _default_config()
    merged["active"] = str(data.get("active", "") or "")
    merged["primary"] = str(data.get("primary", "") or merged["active"] or "")
    merged["activeSource"] = str(data.get("activeSource", "") or "")
    merged["primarySource"] = str(data.get("primarySource", "") or "")
    raw_source_fallbacks = data.get("fallbackSources", [])
    merged["fallbackSources"] = []
    if isinstance(raw_source_fallbacks, list):
        for item in raw_source_fallbacks:
            sid = str(item or "").strip().lower()
            if sid and sid not in merged["fallbackSources"]:
                merged["fallbackSources"].append(sid)
    raw_fallbacks = data.get("fallbacks", [])
    merged["fallbacks"] = []
    if isinstance(raw_fallbacks, list):
        for item in raw_fallbacks:
            pid = str(item or "").strip().lower()
            if pid in ADAPTER_SPECS and pid not in merged["fallbacks"]:
                merged["fallbacks"].append(pid)
    providers = data.get("providers", {}) if isinstance(data.get("providers"), dict) else {}
    for pid in merged["providers"]:
        src = providers.get(pid, {}) if isinstance(providers.get(pid), dict) else {}
        dst = merged["providers"][pid]
        dst["enabled"] = bool(src.get("enabled", dst["enabled"]))
        dst["apiKey"] = str(src.get("apiKey", dst["apiKey"]) or "")
        dst["baseUrl"] = str(src.get("baseUrl", dst["baseUrl"]) or "")
        dst["model"] = str(src.get("model", dst["model"]) or "")
        try:
            dst["topK"] = max(1, min(20, int(src.get("topK", dst["topK"]))))
        except Exception:
            pass
    return merged


def save_search_adapters(cfg: Dict, path: str = DEFAULT_SEARCH_ADAPTERS_PATH) -> bool:
    try:
        _ensure_parent_dir(path)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


def set_active_provider(provider_id: str, path: str = DEFAULT_SEARCH_ADAPTERS_PATH) -> bool:
    cfg = load_search_adapters(path=path)
    pid = (provider_id or "").strip().lower()
    if pid and pid not in ADAPTER_SPECS:
        return False
    cfg["active"] = pid
    cfg["primary"] = pid
    return save_search_adapters(cfg, path=path)


def set_primary_provider(provider_id: str, path: str = DEFAULT_SEARCH_ADAPTERS_PATH) -> bool:
    pid = (provider_id or "").strip().lower()
    if pid and pid not in ADAPTER_SPECS:
        return False
    cfg = load_search_adapters(path=path)
    cfg["primary"] = pid
    cfg["active"] = pid
    if pid:
        cfg["primarySource"] = f"adapter:{pid}"
        cfg["activeSource"] = f"adapter:{pid}"
    return save_search_adapters(cfg, path=path)


def set_fallback_providers(provider_ids: List[str], path: str = DEFAULT_SEARCH_ADAPTERS_PATH) -> bool:
    cfg = load_search_adapters(path=path)
    normalized: List[str] = []
    for item in provider_ids or []:
        pid = str(item or "").strip().lower()
        if pid in ADAPTER_SPECS and pid not in normalized:
            normalized.append(pid)
    cfg["fallbacks"] = normalized
    if normalized:
        cfg["fallbackSources"] = [f"adapter:{x}" for x in normalized]
    return save_search_adapters(cfg, path=path)


def set_primary_source(source_id: str, path: str = DEFAULT_SEARCH_ADAPTERS_PATH) -> bool:
    sid = str(source_id or "").strip().lower()
    if sid and not (sid in OFFICIAL_SEARCH_SOURCES or sid.startswith("adapter:")):
        return False
    cfg = load_search_adapters(path=path)
    cfg["primarySource"] = sid
    cfg["activeSource"] = sid
    # 向后兼容 adapter 旧字段
    if sid.startswith("adapter:"):
        pid = sid.split(":", 1)[1]
        cfg["primary"] = pid
        cfg["active"] = pid
    return save_search_adapters(cfg, path=path)


def set_fallback_sources(source_ids: List[str], path: str = DEFAULT_SEARCH_ADAPTERS_PATH) -> bool:
    cfg = load_search_adapters(path=path)
    normalized: List[str] = []
    for item in source_ids or []:
        sid = str(item or "").strip().lower()
        if not sid:
            continue
        if sid in OFFICIAL_SEARCH_SOURCES or sid.startswith("adapter:"):
            if sid not in normalized:
                normalized.append(sid)
    cfg["fallbackSources"] = normalized
    return save_search_adapters(cfg, path=path)


def update_provider(provider_id: str, updates: Dict, path: str = DEFAULT_SEARCH_ADAPTERS_PATH) -> bool:
    pid = (provider_id or "").strip().lower()
    if pid not in ADAPTER_SPECS:
        return False
    cfg = load_search_adapters(path=path)
    p = cfg["providers"].get(pid, {})
    if "enabled" in updates:
        p["enabled"] = bool(updates.get("enabled"))
    if "apiKey" in updates:
        p["apiKey"] = str(updates.get("apiKey") or "")
    if "baseUrl" in updates:
        p["baseUrl"] = str(updates.get("baseUrl") or p.get("baseUrl") or "")
    if "model" in updates:
        p["model"] = str(updates.get("model") or "")
    if "topK" in updates:
        try:
            p["topK"] = max(1, min(20, int(updates.get("topK"))))
        except Exception:
            pass
    if "cooldownSeconds" in updates:
        try:
            p["cooldownSeconds"] = max(5, min(3600, int(updates.get("cooldownSeconds"))))
        except Exception:
            pass
    cfg["providers"][pid] = p
    return save_search_adapters(cfg, path=path)


def _json_post(url: str, body: Dict, headers: Dict, timeout: int = 20) -> Dict:
    req = request.Request(
        url=url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", **(headers or {})},
        method="POST",
    )
    with request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8", errors="ignore")
        try:
            return json.loads(raw)
        except Exception:
            return {"_raw": raw}


def _json_get(url: str, headers: Dict, timeout: int = 20) -> Dict:
    req = request.Request(url=url, headers=headers or {}, method="GET")
    with request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8", errors="ignore")
        try:
            return json.loads(raw)
        except Exception:
            return {"_raw": raw}


def _normalize_serper(payload: Dict) -> List[Dict]:
    out: List[Dict] = []
    for item in payload.get("organic", []) or []:
        out.append(
            {
                "title": item.get("title", "") or "",
                "url": item.get("link", "") or "",
                "snippet": item.get("snippet", "") or "",
                "source": "serper",
            }
        )
    return [x for x in out if x["url"]]


def _normalize_tavily(payload: Dict) -> List[Dict]:
    out: List[Dict] = []
    for item in payload.get("results", []) or []:
        out.append(
            {
                "title": item.get("title", "") or "",
                "url": item.get("url", "") or "",
                "snippet": item.get("content", "") or "",
                "source": "tavily",
            }
        )
    return [x for x in out if x["url"]]


def _normalize_zhipu(payload: Dict) -> List[Dict]:
    out: List[Dict] = []
    candidates = payload.get("search_result")
    if not isinstance(candidates, list):
        candidates = payload.get("results")
    if not isinstance(candidates, list):
        candidates = payload.get("data", []) if isinstance(payload.get("data"), list) else []
    for item in candidates:
        if not isinstance(item, dict):
            continue
        out.append(
            {
                "title": item.get("title", "") or "",
                "url": item.get("url", "") or item.get("link", "") or "",
                "snippet": item.get("content", "") or item.get("snippet", "") or "",
                "source": "zhipu",
            }
        )
    return [x for x in out if x["url"]]


def _normalize_brave(payload: Dict) -> List[Dict]:
    out: List[Dict] = []
    web = payload.get("web", {}) if isinstance(payload.get("web"), dict) else {}
    for item in web.get("results", []) or []:
        if not isinstance(item, dict):
            continue
        out.append(
            {
                "title": item.get("title", "") or "",
                "url": item.get("url", "") or "",
                "snippet": item.get("description", "") or "",
                "source": "official:brave",
            }
        )
    return [x for x in out if x["url"]]


def _load_openclaw_search_config() -> Dict:
    try:
        with open(DEFAULT_OPENCLAW_CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        return cfg.get("tools", {}).get("web", {}).get("search", {}) or {}
    except Exception:
        return {}


def _official_brave_api_key() -> str:
    search_cfg = _load_openclaw_search_config()
    key = str(search_cfg.get("apiKey", "") or "").strip()
    if key:
        return key
    return str(os.environ.get("BRAVE_API_KEY", "")).strip()


def search_with_official_source(source_id: str, query: str, count: int = 5) -> List[Dict]:
    sid = str(source_id or "").strip().lower()
    if sid != "official:brave":
        raise RuntimeError(f"unsupported official source for failover: {sid}")
    key = _official_brave_api_key()
    if not key:
        raise RuntimeError("official:brave missing api key")
    c = max(1, min(10, int(count or 5)))
    url = f"https://api.search.brave.com/res/v1/web/search?q={quote(query)}&count={c}"
    payload = _json_get(
        url,
        {"Accept": "application/json", "X-Subscription-Token": key},
    )
    return _normalize_brave(payload)


def search_with_provider(provider_id: str, query: str, count: int = 5, path: str = DEFAULT_SEARCH_ADAPTERS_PATH) -> List[Dict]:
    pid = (provider_id or "").strip().lower()
    if pid not in ADAPTER_SPECS:
        raise ValueError(f"unsupported provider: {provider_id}")
    cfg = load_search_adapters(path=path)
    provider = cfg.get("providers", {}).get(pid, {})
    api_key = str(provider.get("apiKey", "") or "")
    base_url = str(provider.get("baseUrl", "") or "")
    model = str(provider.get("model", "") or "")
    top_k = int(provider.get("topK", count or 5) or 5)
    top_k = max(1, min(20, top_k))
    if count and isinstance(count, int):
        top_k = max(1, min(20, count))
    if not api_key:
        raise ValueError("missing api key")
    if not base_url:
        raise ValueError("missing base url")

    if pid == "serper":
        payload = _json_post(
            base_url,
            {"q": query, "num": top_k},
            {"X-API-KEY": api_key},
        )
        return _normalize_serper(payload)
    if pid == "tavily":
        payload = _json_post(
            base_url,
            {"query": query, "max_results": top_k, "api_key": api_key},
            {"Authorization": f"Bearer {api_key}"},
        )
        return _normalize_tavily(payload)
    # zhipu: 采用通用 body，必要字段可通过 baseUrl/上游兼容处理
    body = {"search_query": query, "count": top_k}
    if model:
        body["model"] = model
    # 智谱 web_search 文档里的默认引擎参数
    body["search_engine"] = "search_std"
    payload = _json_post(
        base_url,
        body,
        {"Authorization": f"Bearer {api_key}"},
    )
    return _normalize_zhipu(payload)


def _is_rate_limit_error(exc: Exception) -> bool:
    text = str(exc).lower()
    patterns = ["429", "rate limit", "too many requests", "quota", "限流", "配额"]
    return any(p in text for p in patterns)


def _provider_cooldown_seconds(provider_cfg: Dict) -> int:
    try:
        v = int(provider_cfg.get("cooldownSeconds", 60) or 60)
    except Exception:
        v = 60
    return max(5, min(3600, v))


def _provider_chain(cfg: Dict) -> List[str]:
    primary = str(cfg.get("primary", "") or cfg.get("active", "") or "").strip().lower()
    fallbacks = cfg.get("fallbacks", []) if isinstance(cfg.get("fallbacks"), list) else []
    chain: List[str] = []
    if primary in ADAPTER_SPECS:
        chain.append(primary)
    for item in fallbacks:
        pid = str(item or "").strip().lower()
        if pid in ADAPTER_SPECS and pid not in chain:
            chain.append(pid)
    return chain


def _source_chain(cfg: Dict) -> List[str]:
    primary = str(cfg.get("primarySource", "") or "").strip().lower()
    if not primary:
        legacy = str(cfg.get("primary", "") or cfg.get("active", "") or "").strip().lower()
        if legacy:
            primary = f"adapter:{legacy}"
    fallbacks = cfg.get("fallbackSources", []) if isinstance(cfg.get("fallbackSources"), list) else []
    if not fallbacks:
        legacy_fb = cfg.get("fallbacks", []) if isinstance(cfg.get("fallbacks"), list) else []
        fallbacks = [f"adapter:{str(x).strip().lower()}" for x in legacy_fb if str(x).strip()]
    chain: List[str] = []
    if primary:
        chain.append(primary)
    for sid in fallbacks:
        norm = str(sid or "").strip().lower()
        if norm and norm not in chain:
            chain.append(norm)
    return chain


def search_with_failover(query: str, count: int = 5, path: str = DEFAULT_SEARCH_ADAPTERS_PATH) -> List[Dict]:
    cfg = load_search_adapters(path=path)
    providers_cfg = cfg.get("providers", {}) if isinstance(cfg.get("providers"), dict) else {}
    chain = _provider_chain(cfg)
    if not chain:
        raise RuntimeError("no primary/fallback provider configured")

    errors: List[str] = []
    now = time.time()
    for pid in chain:
        p_cfg = providers_cfg.get(pid, {}) if isinstance(providers_cfg.get(pid), dict) else {}
        if not bool(p_cfg.get("enabled")):
            errors.append(f"{pid}:disabled")
            continue
        if not str(p_cfg.get("apiKey", "") or "").strip():
            errors.append(f"{pid}:missing-key")
            continue
        cooldown_until = _COOLDOWN_UNTIL.get(pid, 0.0)
        if cooldown_until > now:
            errors.append(f"{pid}:cooldown")
            continue
        try:
            results = search_with_provider(pid, query=query, count=count, path=path)
            cfg["active"] = pid
            save_search_adapters(cfg, path=path)
            return results
        except Exception as e:
            if _is_rate_limit_error(e):
                _COOLDOWN_UNTIL[pid] = time.time() + _provider_cooldown_seconds(p_cfg)
            errors.append(f"{pid}:{str(e)}")
            continue
    raise RuntimeError("all providers failed: " + " | ".join(errors))


def _source_cooldown_seconds(cfg: Dict, source_id: str) -> int:
    sid = str(source_id or "").strip().lower()
    if sid.startswith("adapter:"):
        pid = sid.split(":", 1)[1]
        providers = cfg.get("providers", {}) if isinstance(cfg.get("providers"), dict) else {}
        p_cfg = providers.get(pid, {}) if isinstance(providers.get(pid), dict) else {}
        return _provider_cooldown_seconds(p_cfg)
    return 60


def search_with_unified_failover(query: str, count: int = 5, path: str = DEFAULT_SEARCH_ADAPTERS_PATH) -> List[Dict]:
    cfg = load_search_adapters(path=path)
    chain = _source_chain(cfg)
    if not chain:
        raise RuntimeError("no primary/fallback source configured")
    errors: List[str] = []
    now = time.time()
    for sid in chain:
        cool_until = _SOURCE_COOLDOWN_UNTIL.get(sid, 0.0)
        if cool_until > now:
            errors.append(f"{sid}:cooldown")
            continue
        try:
            if sid.startswith("adapter:"):
                pid = sid.split(":", 1)[1]
                results = search_with_provider(pid, query=query, count=count, path=path)
                cfg["active"] = pid
                cfg["activeSource"] = sid
                save_search_adapters(cfg, path=path)
                return results
            if sid.startswith("official:"):
                results = search_with_official_source(sid, query=query, count=count)
                cfg["activeSource"] = sid
                save_search_adapters(cfg, path=path)
                return results
            raise RuntimeError("invalid source")
        except Exception as e:
            if _is_rate_limit_error(e):
                _SOURCE_COOLDOWN_UNTIL[sid] = time.time() + _source_cooldown_seconds(cfg, sid)
            errors.append(f"{sid}:{e}")
    raise RuntimeError("all sources failed: " + " | ".join(errors))


def test_provider_connection(provider_id: str, path: str = DEFAULT_SEARCH_ADAPTERS_PATH) -> Tuple[bool, str]:
    try:
        results = search_with_provider(provider_id, query="OpenClaw", count=3, path=path)
        return True, f"ok ({len(results)} results)"
    except error.HTTPError as e:
        return False, f"http {e.code}"
    except error.URLError as e:
        return False, f"network error: {e.reason}"
    except Exception as e:
        return False, str(e)
