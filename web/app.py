from __future__ import annotations

import json
import os
import re
import glob
import time
import shutil
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from core import (
    DEFAULT_AUTH_PROFILES_PATH,
    DEFAULT_BACKUP_DIR,
    DEFAULT_CONFIG_PATH,
    config,
    get_models_providers,
    run_cli,
    run_cli_json,
    set_models_providers,
)
from core.datasource import get_custom_models
from core.search_adapters import (
    ADAPTER_SPECS,
    OFFICIAL_SEARCH_SOURCES,
    load_search_adapters,
    search_with_unified_failover,
    set_fallback_sources,
    set_primary_source,
    update_provider as update_search_adapter_provider,
)
from core.sandbox import is_sandbox_enabled
from core.write_engine import activate_model, deactivate_model, upsert_provider_api_key
from tui.inventory import (
    API_PROTOCOLS,
    configure_custom_provider_config,
    get_official_provider_options,
    refresh_official_model_pool,
)
from tui.routing import (
    RECOMMENDED_CONTROL_PLANE_CAPABILITIES,
    clear_agent_model_policy,
    get_spawn_model_policy,
    list_agent_model_override_details,
    set_agent_control_plane_whitelist,
    set_agent_model_policy,
    set_spawn_model_policy,
    upsert_main_agent_config,
)
from tui.tools import (
    OFFICIAL_SEARCH_SPECS,
    get_official_search_providers,
    list_configured_official_search_providers,
    set_official_search_api_key,
    set_search_provider,
)


app = FastAPI(title="EasyClaw Web Panel")

BASE_DIR = Path(__file__).resolve().parent
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

WEB_TOKEN = os.environ.get("WEB_API_TOKEN", "default-dev-token")
_CACHE: Dict[str, Dict[str, Any]] = {}
REAL_OPENCLAW_CONFIG_PATH = "/root/.openclaw/openclaw.json"
PROVIDER_DEFAULT_BASE_URLS: Dict[str, str] = {
    "openrouter": "https://openrouter.ai/api/v1",
}
API_PROTOCOL_FALLBACKS: Dict[str, str] = {
    "openai-chat": "openai-completions",
    "anthropic-messages": "anthropic-completions",
}


def verify_token(x_claw_token: str = Header(...)) -> str:
    if x_claw_token != WEB_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid Security Token")
    return x_claw_token


def _cached(key: str, ttl_seconds: float, loader, force: bool = False):
    now = time.time()
    item = _CACHE.get(key)
    if not force and item and (now - float(item.get("ts", 0.0))) < ttl_seconds:
        return item.get("value")
    value = loader()
    _CACHE[key] = {"ts": now, "value": value}
    return value


def _invalidate_cache():
    _CACHE.clear()


def _normalize_provider(provider: str) -> str:
    return str(provider or "").strip().strip("'\"").strip().lower()


def _list_config_backups(limit: int = 20) -> List[Dict[str, Any]]:
    safe_limit = max(1, min(200, int(limit)))
    if not os.path.isdir(DEFAULT_BACKUP_DIR):
        return []

    seen: Dict[str, bool] = {}
    paths: List[str] = []
    patterns = [
        os.path.join(DEFAULT_BACKUP_DIR, "easyclaw_*.json.bak"),
        os.path.join(DEFAULT_BACKUP_DIR, "openclaw_bkp_*.json"),
        os.path.join(DEFAULT_BACKUP_DIR, "*.json.bak"),
    ]
    for pattern in patterns:
        for path in glob.glob(pattern):
            abs_path = os.path.abspath(path)
            if abs_path in seen or not os.path.isfile(abs_path):
                continue
            seen[abs_path] = True
            paths.append(abs_path)

    paths.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    out: List[Dict[str, Any]] = []
    for path in paths[:safe_limit]:
        try:
            stat = os.stat(path)
            out.append(
                {
                    "name": os.path.basename(path),
                    "path": path,
                    "size": int(stat.st_size),
                    "mtime": int(stat.st_mtime),
                }
            )
        except Exception:
            continue
    return out


def _resolve_backup_file_by_name(name: str) -> str:
    target = os.path.basename(str(name or "").strip())
    if not target:
        return ""
    for item in _list_config_backups(limit=500):
        if str(item.get("name", "")).strip() == target:
            return str(item.get("path", "")).strip()
    return ""


def _normalize_dispatch_allow_agents(enabled: bool, allow_agents: List[str]) -> List[str]:
    if not enabled:
        return []
    cleaned: List[str] = []
    for item in (allow_agents or []):
        token = str(item or "").strip()
        if token and token not in cleaned:
            cleaned.append(token)
    if not cleaned:
        # 启用派发但未填白名单时，按“允许所有固定 Agent”处理，避免开关看似无效。
        return ["*"]
    return cleaned


def _extract_oauth_url_and_code(raw: str) -> tuple[str, str]:
    text = str(raw or "")
    url_match = re.search(r"https?://[^\s)]+", text)
    code_match = re.search(r"(?:code|验证码|授权码)\s*[:：]\s*([A-Z0-9-]{4,})", text, flags=re.IGNORECASE)
    if not code_match:
        code_match = re.search(r"\b([A-Z0-9]{4,}(?:-[A-Z0-9]{4,})+)\b", text)
    return (url_match.group(0) if url_match else "", code_match.group(1) if code_match else "")


def _read_json_file(path: str) -> Dict[str, Any]:
    try:
        if not os.path.exists(path):
            return {}
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _seed_agents_from_real_config_if_needed() -> List[Dict[str, Any]]:
    # 在 sandbox 模式下，若隔离配置缺失 agents.list，则尝试从真实配置导入，
    # 保障 Web 端 Agent/派发页面可回显且可操作。
    if not is_sandbox_enabled():
        return []
    real = _read_json_file(REAL_OPENCLAW_CONFIG_PATH)
    real_agents = real.get("agents", {}).get("list", [])
    if not isinstance(real_agents, list) or not real_agents:
        return []

    agents_root = config.data.setdefault("agents", {})
    agents_root["list"] = deepcopy(real_agents)

    real_defaults = real.get("agents", {}).get("defaults", {})
    if isinstance(real_defaults, dict):
        defaults = agents_root.setdefault("defaults", {})
        if isinstance(defaults, dict):
            if not str(defaults.get("workspace", "") or "").strip():
                ws = str(real_defaults.get("workspace", "") or "").strip()
                if ws:
                    defaults["workspace"] = ws
            if not isinstance(defaults.get("subagents"), dict) and isinstance(real_defaults.get("subagents"), dict):
                defaults["subagents"] = deepcopy(real_defaults.get("subagents"))

    config.save()
    config.reload()
    seeded = config.data.get("agents", {}).get("list", [])
    return seeded if isinstance(seeded, list) else []


def _extract_model_cfg(model_cfg: Any) -> tuple[str, List[str]]:
    if isinstance(model_cfg, str):
        val = model_cfg.strip()
        return (val, []) if val else ("", [])
    if isinstance(model_cfg, dict):
        primary = str(model_cfg.get("primary", "") or "").strip()
        raw = model_cfg.get("fallbacks", [])
        fallbacks: List[str] = []
        if isinstance(raw, list):
            for item in raw:
                x = str(item or "").strip()
                if x:
                    fallbacks.append(x)
        return primary, fallbacks
    return "", []


def _build_model_cfg(primary: str, fallbacks: List[str]) -> Any:
    p = (primary or "").strip()
    fb = [str(x).strip() for x in (fallbacks or []) if str(x).strip()]
    if not p and not fb:
        return None
    # OpenClaw 新版本期望 agents.defaults.model 为对象结构，避免写成字符串导致校验报错。
    return {"primary": p, "fallbacks": fb}


def _get_agents() -> List[Dict[str, Any]]:
    config.reload()
    agents = config.data.get("agents", {}).get("list", [])
    if isinstance(agents, list) and agents:
        return agents
    seeded = _seed_agents_from_real_config_if_needed()
    return seeded if seeded else (agents if isinstance(agents, list) else [])


def _agent_by_id(agent_id: str) -> Dict[str, Any]:
    for row in _get_agents():
        if isinstance(row, dict) and str(row.get("id", "")) == agent_id:
            return row
    return {}


def _agent_security(agent: Dict[str, Any]) -> Dict[str, Any]:
    sec = agent.get("security") if isinstance(agent.get("security"), dict) else {}
    return {
        "workspaceOnly": sec.get("workspaceScope") == "workspace-only",
        "controlPlaneCapabilities": sec.get("controlPlaneCapabilities", []) if isinstance(sec.get("controlPlaneCapabilities", []), list) else [],
    }


def _agent_subagents(agent: Dict[str, Any]) -> Dict[str, Any]:
    sub = agent.get("subagents") if isinstance(agent.get("subagents"), dict) else {}
    allow_agents = sub.get("allowAgents") if isinstance(sub.get("allowAgents"), list) else []
    max_concurrent = sub.get("maxConcurrent") if isinstance(sub.get("maxConcurrent"), int) else None
    return {
        "allowAgents": allow_agents,
        "enabled": len(allow_agents) > 0,
        "maxConcurrent": max_concurrent,
    }


def _serialize_agents() -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for agent in _get_agents():
        if not isinstance(agent, dict):
            continue
        aid = str(agent.get("id", "") or "").strip()
        if not aid:
            continue
        sec = _agent_security(agent)
        sub = _agent_subagents(agent)
        primary, fallbacks = _extract_model_cfg(agent.get("model"))
        out.append(
            {
                "id": aid,
                "workspace": str(agent.get("workspace", "") or "").strip(),
                "security": sec,
                "subagents": sub,
                "model": {
                    "primary": primary,
                    "fallbacks": fallbacks,
                    "overridden": bool(primary or fallbacks),
                },
            }
        )
    return out


def _set_global_model_policy(primary: str, fallbacks: List[str]) -> bool:
    config.reload()
    agents = config.data.setdefault("agents", {})
    defaults = agents.setdefault("defaults", {})
    model_cfg = _build_model_cfg(primary, fallbacks)
    if model_cfg is None:
        defaults.pop("model", None)
    else:
        defaults["model"] = model_cfg
    ok = config.save()
    if ok:
        config.reload()
    return ok


def _set_workspace_restriction(agent_id: str, workspace_only: bool) -> bool:
    target = _agent_by_id(agent_id)
    if not target:
        return False
    workspace = str(target.get("workspace", "") or "").strip()
    if not workspace:
        return False

    model_primary, model_fallbacks = _extract_model_cfg(target.get("model"))
    sub = target.get("subagents") if isinstance(target.get("subagents"), dict) else {}
    allow_agents = sub.get("allowAgents") if isinstance(sub.get("allowAgents"), list) else []
    sub_model_primary, sub_model_fallbacks = _extract_model_cfg(sub.get("model"))
    sec = _agent_security(target)

    return upsert_main_agent_config(
        agent_id=agent_id,
        workspace_path=workspace,
        model_primary=model_primary,
        model_fallbacks_csv=",".join(model_fallbacks),
        allow_agents=allow_agents,
        sub_model_primary=sub_model_primary,
        sub_model_fallbacks_csv=",".join(sub_model_fallbacks),
        workspace_restricted=workspace_only,
        control_plane_capabilities=sec["controlPlaneCapabilities"] if workspace_only else [],
    )


def _set_official_key_in_config(provider: str, api_key: str) -> bool:
    spec = OFFICIAL_SEARCH_SPECS.get(provider, {})
    path = str(spec.get("api_key_path", "") or "")
    if not path:
        return False
    keys = path.split(".")
    config.reload()
    cur = config.data
    for key in keys[:-1]:
        if not isinstance(cur.get(key), dict):
            cur[key] = {}
        cur = cur[key]
    cur[keys[-1]] = api_key
    ok = config.save()
    if ok:
        config.reload()
    return ok


def _clear_official_key_in_config(provider: str) -> bool:
    spec = OFFICIAL_SEARCH_SPECS.get(provider, {})
    path = str(spec.get("api_key_path", "") or "")
    if not path:
        return False
    keys = path.split(".")
    config.reload()
    cur = config.data
    for key in keys[:-1]:
        if not isinstance(cur, dict) or key not in cur:
            return True
        cur = cur[key]
    if isinstance(cur, dict):
        cur.pop(keys[-1], None)
    ok = config.save()
    if ok:
        config.reload()
    return ok


def _provider_inventory_rows_uncached() -> List[Dict[str, Any]]:
    profiles_by_provider = config.get_profiles_by_provider()
    models_by_provider = config.get_models_by_provider()
    providers_cfg = get_models_providers() or {}

    all_providers = set(profiles_by_provider.keys()) | set(models_by_provider.keys()) | set(providers_cfg.keys())
    rows: List[Dict[str, Any]] = []
    for provider in sorted(all_providers):
        profiles = profiles_by_provider.get(provider, [])
        models = models_by_provider.get(provider, [])
        p_cfg = providers_cfg.get(provider, {}) if isinstance(providers_cfg.get(provider), dict) else {}
        key_count = 1 if str(p_cfg.get("apiKey", "") or "").strip() else 0
        rows.append(
            {
                "provider": provider,
                "authCount": len(profiles),
                "keyCount": key_count,
                "modelCount": len(models),
                "api": str(p_cfg.get("api", "") or ""),
                "baseUrl": str(p_cfg.get("baseUrl", "") or ""),
            }
        )
    return rows


def _provider_inventory_rows(force: bool = False) -> List[Dict[str, Any]]:
    return _cached("inventory_rows", 5.0, _provider_inventory_rows_uncached, force=force) or []


def _get_official_provider_options(force: bool = False) -> List[Dict[str, Any]]:
    return _cached("official_provider_options", 60.0, get_official_provider_options, force=force) or []


def _load_all_models_uncached() -> List[Dict[str, Any]]:
    data = run_cli_json(["models", "list", "--all"])
    models = data.get("models", []) if isinstance(data, dict) else []
    if not isinstance(models, list):
        return []

    out: List[Dict[str, Any]] = []
    for row in models:
        if not isinstance(row, dict):
            continue
        key = str(row.get("key", "") or "").strip()
        if not key:
            continue
        provider = key.split("/", 1)[0] if "/" in key else "other"
        out.append(
            {
                "key": key,
                "name": str(row.get("name", "") or key),
                "provider": provider,
                "available": bool(row.get("available", False)),
            }
        )
    return out


def _load_all_models(force: bool = False) -> List[Dict[str, Any]]:
    return _cached("all_models", 20.0, _load_all_models_uncached, force=force) or []


def _load_status_uncached() -> Dict[str, Any]:
    status = run_cli_json(["models", "status"])
    return status if isinstance(status, dict) else {}


def _load_status(force: bool = False) -> Dict[str, Any]:
    return _cached("status", 4.0, _load_status_uncached, force=force) or {}


def _load_usage_uncached() -> Dict[str, Any]:
    stdout, stderr, code = run_cli(["status", "--usage"])
    return {
        "code": code,
        "raw": stdout or "",
        "error": stderr or "",
    }


def _load_usage(force: bool = False) -> Dict[str, Any]:
    return _cached("usage", 20.0, _load_usage_uncached, force=force) or {"code": 0, "raw": "", "error": ""}


def _build_active_model_rows(status: Dict[str, Any], all_models: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    available_map = {m["key"]: bool(m.get("available", False)) for m in all_models}
    default_model = str(status.get("defaultModel", "") or "")
    allowed = status.get("allowed", []) if isinstance(status.get("allowed", []), list) else []

    rows: List[Dict[str, Any]] = []
    for key in allowed:
        k = str(key or "").strip()
        if not k:
            continue
        rows.append(
            {
                "key": k,
                "provider": k.split("/", 1)[0] if "/" in k else "other",
                "name": k.split("/", 1)[1] if "/" in k else k,
                "isDefault": k == default_model,
                "available": available_map.get(k),
            }
        )
    return rows


def _delete_provider_noninteractive(provider: str) -> Dict[str, Any]:
    provider = _normalize_provider(provider)
    if not provider:
        return {"ok": False, "error": "provider is required"}

    config.reload()
    backup_path = config.backup() or ""

    result = {
        "ok": True,
        "provider": provider,
        "backupPath": backup_path,
        "deletedModels": 0,
        "deletedProfiles": 0,
        "deletedAuthProfiles": 0,
    }

    providers_cfg = get_models_providers() or {}
    if provider in providers_cfg:
        del providers_cfg[provider]
        if not set_models_providers(providers_cfg):
            return {"ok": False, "error": "删除 models.providers 失败", "backupPath": backup_path}

    config.reload()
    models_map = config.data.get("agents", {}).get("defaults", {}).get("models", {})
    if not isinstance(models_map, dict):
        models_map = {}
    to_delete = [k for k in list(models_map.keys()) if str(k).startswith(f"{provider}/")]
    for key in to_delete:
        del models_map[key]
    result["deletedModels"] = len(to_delete)
    config.save()
    config.reload()

    if os.path.exists(DEFAULT_AUTH_PROFILES_PATH):
        try:
            with open(DEFAULT_AUTH_PROFILES_PATH, "r", encoding="utf-8") as f:
                ap = json.load(f)
            profiles = ap.get("profiles", {}) if isinstance(ap.get("profiles"), dict) else {}
            keys = [k for k, v in profiles.items() if isinstance(v, dict) and _normalize_provider(v.get("provider", "")) == provider]
            for key in keys:
                del profiles[key]
            result["deletedProfiles"] = len(keys)
            with open(DEFAULT_AUTH_PROFILES_PATH, "w", encoding="utf-8") as f:
                json.dump(ap, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    try:
        with open(DEFAULT_CONFIG_PATH, "r", encoding="utf-8") as f:
            full = json.load(f)
        auth_profiles = full.get("auth", {}).get("profiles", {}) if isinstance(full.get("auth", {}).get("profiles", {}), dict) else {}
        keys = [k for k, v in auth_profiles.items() if isinstance(v, dict) and _normalize_provider(v.get("provider", "")) == provider]
        for key in keys:
            del auth_profiles[key]
        result["deletedAuthProfiles"] = len(keys)
        with open(DEFAULT_CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(full, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

    config.reload()
    return result


def _state_payload(force: bool = False, include_usage: bool = False) -> Dict[str, Any]:
    config.reload()

    usage = _load_usage(force=force) if include_usage else (_CACHE.get("usage", {}).get("value") or {"code": 0, "raw": "", "error": ""})

    defaults_model = config.data.get("agents", {}).get("defaults", {}).get("model")
    default_model, fallback_models = _extract_model_cfg(defaults_model)
    spawn_primary, spawn_fallbacks = get_spawn_model_policy()
    agent_overrides = list_agent_model_override_details()

    search_cfg = config.data.get("tools", {}).get("web", {}).get("search", {})
    search_provider = str(search_cfg.get("provider", "") or "")
    official_supported = get_official_search_providers()
    official_configured = list_configured_official_search_providers(official_supported)
    adapter_cfg = load_search_adapters()

    defaults_sub = config.data.get("agents", {}).get("defaults", {}).get("subagents", {}) or {}
    global_sub_max = defaults_sub.get("maxConcurrent", 8)

    active_models_cfg = config.data.get("agents", {}).get("defaults", {}).get("models", {})
    if isinstance(active_models_cfg, dict):
        active_keys = [str(k) for k in active_models_cfg.keys() if str(k).strip()]
    else:
        active_keys = []

    return {
        "runtime": {
            "sandboxEnabled": bool(is_sandbox_enabled()),
            "configPath": DEFAULT_CONFIG_PATH,
            "webTokenHint": f"{WEB_TOKEN[:4]}******" if WEB_TOKEN else "(empty)",
        },
        "globalModel": {
            "primary": default_model,
            "fallbacks": fallback_models,
        },
        "agentModelOverrides": agent_overrides,
        "spawnModel": {
            "primary": spawn_primary,
            "fallbacks": spawn_fallbacks,
        },
        "agents": _serialize_agents(),
        "inventory": {
            "rows": _provider_inventory_rows(force=force),
        },
        "dispatch": {
            "globalMaxConcurrent": global_sub_max,
        },
        "health": {
            "status": {},
            "usage": usage,
            "activeModels": [],
        },
        "search": {
            "defaultProvider": search_provider,
            "officialSupported": official_supported,
            "officialConfigured": official_configured,
            "officialSpecs": OFFICIAL_SEARCH_SPECS,
            "adapterConfig": adapter_cfg,
            "availableUnifiedSources": OFFICIAL_SEARCH_SOURCES + [f"adapter:{k}" for k in ADAPTER_SPECS.keys()],
        },
        "modelCatalog": {
            "all": [],
            "providers": [],
            "activeKeys": active_keys,
        },
        "officialProviderOptions": [],
        "providerProtocols": list(API_PROTOCOLS),
    }


class GlobalModelPolicyIn(BaseModel):
    primary: str = ""
    fallbacks: List[str] = Field(default_factory=list)


class AgentModelPolicyIn(BaseModel):
    agentId: str
    primary: str = ""
    fallbacks: List[str] = Field(default_factory=list)


class SpawnModelPolicyIn(BaseModel):
    primary: str = ""
    fallbacks: List[str] = Field(default_factory=list)


class CreateAgentIn(BaseModel):
    agentId: str
    workspace: str
    workspaceOnly: bool = False


class BindWorkspaceIn(BaseModel):
    agentId: str
    workspace: str


class AgentSecurityIn(BaseModel):
    agentId: str
    workspaceOnly: bool


class ControlWhitelistIn(BaseModel):
    agentId: str
    enabled: bool
    capabilities: List[str] = Field(default_factory=list)


class DispatchPolicyIn(BaseModel):
    agentId: str
    enabled: bool
    allowAgents: List[str] = Field(default_factory=list)
    maxConcurrent: Optional[int] = None
    inheritMaxConcurrent: bool = False


class OfficialSearchConfigIn(BaseModel):
    provider: str
    apiKey: str = ""
    activateAsDefault: bool = True


class AdapterSearchConfigIn(BaseModel):
    provider: str
    enabled: bool = True
    apiKey: str = ""
    baseUrl: str = ""
    model: str = ""
    topK: int = 5
    cooldownSeconds: int = 60


class SearchFailoverIn(BaseModel):
    primarySource: str = ""
    fallbackSources: List[str] = Field(default_factory=list)


class SearchTestIn(BaseModel):
    query: str = "OpenClaw"
    count: int = 3


class ProviderApiKeyIn(BaseModel):
    provider: str
    apiKey: str
    baseUrl: str = ""


class CustomProviderIn(BaseModel):
    provider: str
    api: str
    baseUrl: str
    apiKey: str
    discoverModels: bool = True


class DiscoverModelsIn(BaseModel):
    provider: str


class ConfigRollbackIn(BaseModel):
    backupName: str


class OfficialOauthStartIn(BaseModel):
    optionId: str
    provider: str


class ModelToggleIn(BaseModel):
    key: str
    activate: bool = True


@app.get("/", response_class=HTMLResponse)
async def serve_dashboard(request: Request):
    _ = request
    index_path = BASE_DIR / "templates" / "index.html"
    if not index_path.exists():
        raise HTTPException(status_code=500, detail="index.html not found")
    return HTMLResponse(index_path.read_text(encoding="utf-8"))


@app.get("/api/state", dependencies=[Depends(verify_token)])
async def get_state():
    return _state_payload()


@app.get("/api/health", dependencies=[Depends(verify_token)])
async def get_health_status():
    status = _load_status(force=False)
    usage = _load_usage(force=False)
    all_models = _load_all_models(force=False)
    active_models = _build_active_model_rows(status, all_models)
    return {
        "status": status,
        "usage": usage,
        "activeModels": active_models,
    }


@app.post("/api/models/global", dependencies=[Depends(verify_token)])
async def set_global_model_policy(body: GlobalModelPolicyIn):
    ok = _set_global_model_policy(body.primary, body.fallbacks)
    if not ok:
        raise HTTPException(status_code=500, detail="保存全局模型策略失败")
    _invalidate_cache()
    return {"ok": True, "state": _state_payload(force=True)}


@app.post("/api/models/agent", dependencies=[Depends(verify_token)])
async def set_agent_model_policy_api(body: AgentModelPolicyIn):
    ok = set_agent_model_policy(body.agentId, body.primary, ",".join(body.fallbacks))
    if not ok:
        raise HTTPException(status_code=400, detail="设置 Agent 模型策略失败")
    _invalidate_cache()
    return {"ok": True, "state": _state_payload(force=True)}


@app.delete("/api/models/agent/{agent_id}", dependencies=[Depends(verify_token)])
async def clear_agent_model_policy_api(agent_id: str):
    ok = clear_agent_model_policy(agent_id)
    if not ok:
        raise HTTPException(status_code=400, detail="清除 Agent 模型策略失败")
    _invalidate_cache()
    return {"ok": True, "state": _state_payload(force=True)}


@app.post("/api/models/spawn", dependencies=[Depends(verify_token)])
async def set_spawn_model_policy_api(body: SpawnModelPolicyIn):
    ok = set_spawn_model_policy(body.primary, ",".join(body.fallbacks))
    if not ok:
        raise HTTPException(status_code=500, detail="设置 Spawn 模型策略失败")
    _invalidate_cache()
    return {"ok": True, "state": _state_payload(force=True)}


@app.delete("/api/models/spawn", dependencies=[Depends(verify_token)])
async def clear_spawn_model_policy_api():
    ok = set_spawn_model_policy("", "")
    if not ok:
        raise HTTPException(status_code=500, detail="清除 Spawn 模型策略失败")
    _invalidate_cache()
    return {"ok": True, "state": _state_payload(force=True)}


@app.post("/api/models/toggle", dependencies=[Depends(verify_token)])
async def toggle_model_api(body: ModelToggleIn):
    key = str(body.key or "").strip()
    if not key:
        raise HTTPException(status_code=400, detail="model key is required")
    if body.activate:
        ok, err = activate_model(key)
    else:
        ok, err = deactivate_model(key)
    if not ok:
        raise HTTPException(status_code=400, detail=f"模型操作失败: {err}")
    _invalidate_cache()
    return {"ok": True, "state": _state_payload(force=True)}


@app.get("/api/models/catalog", dependencies=[Depends(verify_token)])
async def get_models_catalog_api():
    all_models = _load_all_models(force=False)
    provider_set = sorted(set([m.get("provider", "") for m in all_models if m.get("provider")]))
    config.reload()
    models_cfg = config.data.get("agents", {}).get("defaults", {}).get("models", {})
    if isinstance(models_cfg, dict):
        active_keys = [str(x) for x in models_cfg.keys() if str(x).strip()]
    else:
        active_keys = []
    return {
        "modelCatalog": {
            "all": all_models,
            "providers": provider_set,
            "activeKeys": active_keys,
        }
    }


@app.post("/api/agents", dependencies=[Depends(verify_token)])
async def create_agent_api(body: CreateAgentIn):
    ok = upsert_main_agent_config(
        agent_id=body.agentId,
        workspace_path=body.workspace,
        model_primary="",
        model_fallbacks_csv="",
        allow_agents=[],
        sub_model_primary="",
        sub_model_fallbacks_csv="",
        workspace_restricted=body.workspaceOnly,
        control_plane_capabilities=RECOMMENDED_CONTROL_PLANE_CAPABILITIES if body.workspaceOnly else [],
    )
    if not ok:
        raise HTTPException(status_code=400, detail="创建 Agent 失败，请检查 Agent ID 或 workspace 路径")
    _invalidate_cache()
    return {"ok": True, "state": _state_payload(force=True)}


@app.post("/api/agents/workspace", dependencies=[Depends(verify_token)])
async def bind_workspace_api(body: BindWorkspaceIn):
    target = _agent_by_id(body.agentId)
    if not target:
        raise HTTPException(status_code=404, detail="Agent 不存在")

    model_primary, model_fallbacks = _extract_model_cfg(target.get("model"))
    sub_cfg = target.get("subagents") if isinstance(target.get("subagents"), dict) else {}
    allow_agents = sub_cfg.get("allowAgents") if isinstance(sub_cfg.get("allowAgents"), list) else []
    sub_model_primary, sub_model_fallbacks = _extract_model_cfg(sub_cfg.get("model"))
    sec = _agent_security(target)

    ok = upsert_main_agent_config(
        agent_id=body.agentId,
        workspace_path=body.workspace,
        model_primary=model_primary,
        model_fallbacks_csv=",".join(model_fallbacks),
        allow_agents=allow_agents,
        sub_model_primary=sub_model_primary,
        sub_model_fallbacks_csv=",".join(sub_model_fallbacks),
        workspace_restricted=sec["workspaceOnly"],
        control_plane_capabilities=sec["controlPlaneCapabilities"],
    )
    if not ok:
        raise HTTPException(status_code=400, detail="绑定 workspace 失败")
    _invalidate_cache()
    return {"ok": True, "state": _state_payload(force=True)}


@app.post("/api/agents/security", dependencies=[Depends(verify_token)])
async def set_agent_security_api(body: AgentSecurityIn):
    ok = _set_workspace_restriction(body.agentId, body.workspaceOnly)
    if not ok:
        raise HTTPException(status_code=400, detail="更新访问限制失败")
    _invalidate_cache()
    return {"ok": True, "state": _state_payload(force=True)}


@app.post("/api/agents/whitelist", dependencies=[Depends(verify_token)])
async def set_control_whitelist_api(body: ControlWhitelistIn):
    caps = [x.strip() for x in (body.capabilities or []) if x and x.strip()]
    if body.enabled and not caps:
        caps = list(RECOMMENDED_CONTROL_PLANE_CAPABILITIES)
    ok = set_agent_control_plane_whitelist(body.agentId, body.enabled, caps)
    if not ok:
        raise HTTPException(status_code=400, detail="更新命令白名单失败")
    _invalidate_cache()
    return {"ok": True, "state": _state_payload(force=True)}


@app.post("/api/dispatch", dependencies=[Depends(verify_token)])
async def set_dispatch_policy_api(body: DispatchPolicyIn):
    allow_agents = _normalize_dispatch_allow_agents(body.enabled, body.allowAgents)
    ok = config.update_subagent_for(
        agent_id=body.agentId,
        allow_agents=allow_agents,
        max_concurrent=body.maxConcurrent,
        inherit_max_concurrent=body.inheritMaxConcurrent,
    )
    if not ok:
        raise HTTPException(status_code=400, detail="更新派发策略失败")
    _invalidate_cache()
    return {"ok": True, "state": _state_payload(force=True)}


@app.post("/api/providers/api-key", dependencies=[Depends(verify_token)])
async def upsert_provider_api_key_api(body: ProviderApiKeyIn):
    provider = _normalize_provider(body.provider)
    api_key = str(body.apiKey or "").strip()
    if not provider or not api_key:
        raise HTTPException(status_code=400, detail="provider/apiKey 必填")

    providers_cfg = get_models_providers() or {}
    existing_cfg = providers_cfg.get(provider, {}) if isinstance(providers_cfg.get(provider), dict) else {}
    default_base_url = (body.baseUrl or "").strip() or str(existing_cfg.get("baseUrl", "") or "").strip()
    if not default_base_url:
        default_base_url = PROVIDER_DEFAULT_BASE_URLS.get(provider, "")

    ok, err = upsert_provider_api_key(provider, api_key, default_base_url=default_base_url)
    if not ok:
        raise HTTPException(status_code=400, detail=f"写入服务商 API Key 失败: {err}")

    if body.baseUrl.strip() or default_base_url:
        providers_cfg.setdefault(provider, {})
        providers_cfg[provider]["baseUrl"] = (body.baseUrl or "").strip() or default_base_url
        set_models_providers(providers_cfg)

    _invalidate_cache()
    return {"ok": True, "state": _state_payload(force=True)}


@app.post("/api/providers/custom", dependencies=[Depends(verify_token)])
async def add_custom_provider_api(body: CustomProviderIn):
    provider = _normalize_provider(body.provider)
    if not provider:
        raise HTTPException(status_code=400, detail="provider 必填")

    if body.api not in API_PROTOCOLS:
        raise HTTPException(status_code=400, detail=f"不支持的协议: {body.api}")

    chosen_api = body.api
    ok, err, discovered_count, discover_err = configure_custom_provider_config(
        provider=provider,
        api_proto=chosen_api,
        base_url=body.baseUrl.strip(),
        api_key=body.apiKey.strip(),
        discover_models=bool(body.discoverModels),
    )
    adapted_api: Dict[str, str] = {}
    if (not ok) and err and "Invalid input" in str(err):
        fallback_api = API_PROTOCOL_FALLBACKS.get(chosen_api, "")
        if fallback_api and fallback_api in API_PROTOCOLS and fallback_api != chosen_api:
            ok, err, discovered_count, discover_err = configure_custom_provider_config(
                provider=provider,
                api_proto=fallback_api,
                base_url=body.baseUrl.strip(),
                api_key=body.apiKey.strip(),
                discover_models=bool(body.discoverModels),
            )
            if ok:
                adapted_api = {"from": chosen_api, "to": fallback_api}

    if not ok:
        raise HTTPException(status_code=400, detail=f"添加自定义服务商失败: {err}")

    _invalidate_cache()
    return {
        "ok": True,
        "adaptedApi": adapted_api,
        "discoveredCount": discovered_count,
        "discoverError": discover_err,
        "state": _state_payload(force=True),
    }


@app.post("/api/providers/discover-models", dependencies=[Depends(verify_token)])
async def discover_provider_models_api(body: DiscoverModelsIn):
    provider = _normalize_provider(body.provider)
    providers_cfg = get_models_providers() or {}
    p_cfg = providers_cfg.get(provider, {}) if isinstance(providers_cfg.get(provider), dict) else {}
    base_url = str(p_cfg.get("baseUrl", "") or "").strip()
    api_key = str(p_cfg.get("apiKey", "") or "").strip()

    if not base_url:
        raise HTTPException(status_code=400, detail="该服务商未配置 baseUrl，无法自动发现")

    try:
        discovered = get_custom_models(provider, base_url, api_key)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"自动发现失败: {e}")

    normalized_models = []
    for row in discovered:
        key = (row.get("key") or row.get("id") or row.get("name") or "").strip()
        if not key:
            continue
        model_id = key.split("/", 1)[1] if key.startswith(f"{provider}/") else key
        normalized_models.append({"id": model_id, "name": row.get("name") or model_id})

    providers_cfg.setdefault(provider, {})
    providers_cfg[provider].setdefault("models", [])
    providers_cfg[provider]["models"] = normalized_models
    if not set_models_providers(providers_cfg):
        raise HTTPException(status_code=500, detail="写入发现模型失败")

    _invalidate_cache()
    return {"ok": True, "count": len(normalized_models), "state": _state_payload(force=True)}


@app.delete("/api/providers/{provider}", dependencies=[Depends(verify_token)])
async def delete_provider_api(provider: str):
    result = _delete_provider_noninteractive(provider)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error", "删除服务商失败"))
    _invalidate_cache()
    return {"ok": True, "result": result, "state": _state_payload(force=True)}


@app.get("/api/providers/options", dependencies=[Depends(verify_token)])
async def get_provider_options_api():
    return {"options": _get_official_provider_options(force=False)}


@app.post("/api/providers/oauth/start", dependencies=[Depends(verify_token)])
async def start_provider_oauth_api(body: OfficialOauthStartIn):
    provider = _normalize_provider(body.provider)
    option_id = str(body.optionId or "").strip()
    if not provider:
        raise HTTPException(status_code=400, detail="provider 必填")

    cmd_onboard = [
        "onboard",
        "--non-interactive",
        "--accept-risk",
        "--auth-choice",
        option_id or provider,
        "--skip-channels",
        "--skip-skills",
        "--skip-health",
        "--skip-ui",
        "--no-install-daemon",
        "--json",
    ]
    out1, err1, code1 = run_cli(cmd_onboard)
    raw1 = "\n".join([x for x in [out1, err1] if x]).strip()
    url1, oauth_code1 = _extract_oauth_url_and_code(raw1)

    if url1 or oauth_code1:
        return {
            "ok": True,
            "exitCode": code1,
            "provider": provider,
            "optionId": option_id,
            "oauthUrl": url1,
            "oauthCode": oauth_code1,
            "requiresTty": False,
            "recommendedCommand": "",
            "raw": raw1,
        }

    cmd_login = ["models", "auth", "login", "--provider", provider]
    if option_id and option_id != provider:
        cmd_login.extend(["--method", option_id])
    out2, err2, code2 = run_cli(cmd_login)
    raw2 = "\n".join([x for x in [out2, err2] if x]).strip()
    url2, oauth_code2 = _extract_oauth_url_and_code(raw2)
    raw_all = "\n\n---\n\n".join([x for x in [raw1, raw2] if x]).strip()

    requires_tty = "interactive TTY" in raw_all or "requires a TTY" in raw_all
    recommended_cmd = ""
    if requires_tty:
        recommended_cmd = f"openclaw models auth login --provider {provider}"
        if option_id and option_id != provider:
            recommended_cmd += f" --method {option_id}"

    return {
        "ok": bool(url2 or oauth_code2),
        "exitCode": code2 if code2 is not None else code1,
        "provider": provider,
        "optionId": option_id,
        "oauthUrl": url2,
        "oauthCode": oauth_code2,
        "requiresTty": requires_tty,
        "recommendedCommand": recommended_cmd,
        "raw": raw_all,
    }


@app.post("/api/providers/refresh-model-pool", dependencies=[Depends(verify_token)])
async def refresh_model_pool_api():
    ok, message = refresh_official_model_pool()
    _invalidate_cache()
    return {"ok": ok, "message": message, "state": _state_payload(force=True)}


@app.get("/api/config/backups", dependencies=[Depends(verify_token)])
async def list_config_backups_api(limit: int = 20):
    return {
        "items": _list_config_backups(limit=limit),
        "configPath": DEFAULT_CONFIG_PATH,
        "backupDir": DEFAULT_BACKUP_DIR,
    }


@app.post("/api/config/rollback", dependencies=[Depends(verify_token)])
async def rollback_config_api(body: ConfigRollbackIn):
    backup_path = _resolve_backup_file_by_name(body.backupName)
    if not backup_path:
        raise HTTPException(status_code=404, detail="未找到指定备份文件")
    if not os.path.exists(DEFAULT_CONFIG_PATH):
        raise HTTPException(status_code=500, detail=f"配置文件不存在: {DEFAULT_CONFIG_PATH}")

    pre_backup = config.backup() or ""
    try:
        shutil.copy2(backup_path, DEFAULT_CONFIG_PATH)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"回滚失败: {e}")

    config.reload()
    _invalidate_cache()
    return {
        "ok": True,
        "restored": os.path.basename(backup_path),
        "restoredPath": backup_path,
        "preBackupPath": pre_backup,
        "state": _state_payload(force=True),
    }


@app.post("/api/search/official", dependencies=[Depends(verify_token)])
async def set_official_search_api(body: OfficialSearchConfigIn):
    provider = _normalize_provider(body.provider)
    if provider not in OFFICIAL_SEARCH_SPECS:
        raise HTTPException(status_code=400, detail="不支持的官方搜索服务")

    if body.apiKey.strip():
        ok_key = set_official_search_api_key(provider, body.apiKey.strip())
        if not ok_key:
            ok_key = _set_official_key_in_config(provider, body.apiKey.strip())
        if not ok_key:
            raise HTTPException(status_code=500, detail="写入 API Key 失败")

    if body.activateAsDefault:
        ok = set_search_provider(provider)
        if not ok:
            raise HTTPException(status_code=500, detail="激活默认搜索服务失败")

    _invalidate_cache()
    return {"ok": True, "state": _state_payload(force=True)}


@app.delete("/api/search/official/{provider}", dependencies=[Depends(verify_token)])
async def clear_official_search_api(provider: str):
    pid = _normalize_provider(provider)
    if pid not in OFFICIAL_SEARCH_SPECS:
        raise HTTPException(status_code=400, detail="不支持的官方搜索服务")
    ok = _clear_official_key_in_config(pid)
    if not ok:
        raise HTTPException(status_code=500, detail="清空官方搜索配置失败")
    _invalidate_cache()
    return {"ok": True, "state": _state_payload(force=True)}


@app.post("/api/search/adapter", dependencies=[Depends(verify_token)])
async def set_adapter_search_api(body: AdapterSearchConfigIn):
    pid = _normalize_provider(body.provider)
    if pid not in ADAPTER_SPECS:
        raise HTTPException(status_code=400, detail="不支持的扩展搜索服务")
    ok = update_search_adapter_provider(
        pid,
        {
            "enabled": body.enabled,
            "apiKey": body.apiKey,
            "baseUrl": body.baseUrl,
            "model": body.model,
            "topK": body.topK,
            "cooldownSeconds": body.cooldownSeconds,
        },
    )
    if not ok:
        raise HTTPException(status_code=500, detail="保存扩展搜索配置失败")
    _invalidate_cache()
    return {"ok": True, "state": _state_payload(force=True)}


@app.post("/api/search/failover", dependencies=[Depends(verify_token)])
async def set_search_failover_api(body: SearchFailoverIn):
    primary = str(body.primarySource or "").strip().lower()
    fallbacks = [str(x).strip().lower() for x in (body.fallbackSources or []) if str(x).strip()]

    ok_primary = set_primary_source(primary)
    ok_fallback = set_fallback_sources(fallbacks)
    if not ok_primary or not ok_fallback:
        raise HTTPException(status_code=400, detail="设置主备搜索链失败")

    _invalidate_cache()
    return {"ok": True, "state": _state_payload(force=True)}


@app.post("/api/search/test", dependencies=[Depends(verify_token)])
async def test_search_api(body: SearchTestIn):
    query = (body.query or "").strip() or "OpenClaw"
    count = max(1, min(10, int(body.count or 3)))
    try:
        results = search_with_unified_failover(query, count=count)
        adapter_cfg = load_search_adapters()
        active_source = str(adapter_cfg.get("activeSource", "") or "")
        return {
            "ok": True,
            "activeSource": active_source,
            "count": len(results),
            "results": results,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"搜索演练失败: {e}")


@app.get("/api/openclaw/models/all", dependencies=[Depends(verify_token)])
async def get_openclaw_models_all():
    data = run_cli_json(["models", "list", "--all"])
    if "error" in data:
        raise HTTPException(status_code=500, detail=data.get("error", "读取模型池失败"))
    return data
