from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from core import config, run_cli_json
from core.executor import safe_exec_json
from core.search_adapters import (
    ADAPTER_SPECS,
    OFFICIAL_SEARCH_SOURCES,
    load_search_adapters,
    search_with_unified_failover,
    set_fallback_sources,
    set_primary_source,
    update_provider as update_search_adapter_provider,
)
from tui.inventory import get_official_provider_options, refresh_official_model_pool
from tui.routing import (
    RECOMMENDED_CONTROL_PLANE_CAPABILITIES,
    clear_agent_model_policy,
    get_default_model,
    get_fallbacks,
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


def verify_token(x_claw_token: str = Header(...)) -> str:
    if x_claw_token != WEB_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid Security Token")
    return x_claw_token


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
    if p and not fb:
        return p
    return {"primary": p or None, "fallbacks": fb}


def _get_agents() -> List[Dict[str, Any]]:
    config.reload()
    agents = config.data.get("agents", {}).get("list", [])
    return agents if isinstance(agents, list) else []


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
    for k in keys[:-1]:
        if not isinstance(cur.get(k), dict):
            cur[k] = {}
        cur = cur[k]
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
    for k in keys[:-1]:
        if not isinstance(cur, dict) or k not in cur:
            return True
        cur = cur[k]
    if isinstance(cur, dict):
        cur.pop(keys[-1], None)
    ok = config.save()
    if ok:
        config.reload()
    return ok


def _provider_inventory_rows() -> List[Dict[str, Any]]:
    profiles_by_provider = config.get_profiles_by_provider()
    models_by_provider = config.get_models_by_provider()
    providers_cfg = config.data.get("models", {}).get("providers", {})

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
            }
        )
    return rows


def _state_payload() -> Dict[str, Any]:
    config.reload()

    default_model = get_default_model() or ""
    fallback_models = get_fallbacks() or []
    spawn_primary, spawn_fallbacks = get_spawn_model_policy()
    agent_overrides = list_agent_model_override_details()

    search_cfg = config.data.get("tools", {}).get("web", {}).get("search", {})
    search_provider = str(search_cfg.get("provider", "") or "")
    official_supported = get_official_search_providers()
    official_configured = list_configured_official_search_providers(official_supported)
    adapter_cfg = load_search_adapters()

    defaults_sub = config.data.get("agents", {}).get("defaults", {}).get("subagents", {}) or {}
    global_sub_max = defaults_sub.get("maxConcurrent", 8)

    return {
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
            "rows": _provider_inventory_rows(),
        },
        "dispatch": {
            "globalMaxConcurrent": global_sub_max,
        },
        "search": {
            "defaultProvider": search_provider,
            "officialSupported": official_supported,
            "officialConfigured": official_configured,
            "officialSpecs": OFFICIAL_SEARCH_SPECS,
            "adapterConfig": adapter_cfg,
            "availableUnifiedSources": OFFICIAL_SEARCH_SOURCES + [f"adapter:{k}" for k in ADAPTER_SPECS.keys()],
        },
        "modelCatalog": config.get_all_models_flat(),
        "officialProviderOptions": get_official_provider_options(),
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


@app.get("/", response_class=HTMLResponse)
async def serve_dashboard(request: Request):
    _ = request  # 保留 request 参数，便于后续扩展
    index_path = BASE_DIR / "templates" / "index.html"
    if not index_path.exists():
        raise HTTPException(status_code=500, detail="index.html not found")
    return HTMLResponse(index_path.read_text(encoding="utf-8"))


@app.get("/api/state", dependencies=[Depends(verify_token)])
async def get_state():
    return _state_payload()


@app.get("/api/health", dependencies=[Depends(verify_token)])
async def get_health_status():
    ok, data = safe_exec_json(["status"])
    if not ok:
        raise HTTPException(status_code=500, detail=data.get("error", "Unknown error"))
    return data


@app.post("/api/models/global", dependencies=[Depends(verify_token)])
async def set_global_model_policy(body: GlobalModelPolicyIn):
    ok = _set_global_model_policy(body.primary, body.fallbacks)
    if not ok:
        raise HTTPException(status_code=500, detail="保存全局模型策略失败")
    return {"ok": True, "state": _state_payload()}


@app.post("/api/models/agent", dependencies=[Depends(verify_token)])
async def set_agent_model_policy_api(body: AgentModelPolicyIn):
    ok = set_agent_model_policy(body.agentId, body.primary, ",".join(body.fallbacks))
    if not ok:
        raise HTTPException(status_code=400, detail="设置 Agent 模型策略失败")
    return {"ok": True, "state": _state_payload()}


@app.delete("/api/models/agent/{agent_id}", dependencies=[Depends(verify_token)])
async def clear_agent_model_policy_api(agent_id: str):
    ok = clear_agent_model_policy(agent_id)
    if not ok:
        raise HTTPException(status_code=400, detail="清除 Agent 模型策略失败")
    return {"ok": True, "state": _state_payload()}


@app.post("/api/models/spawn", dependencies=[Depends(verify_token)])
async def set_spawn_model_policy_api(body: SpawnModelPolicyIn):
    ok = set_spawn_model_policy(body.primary, ",".join(body.fallbacks))
    if not ok:
        raise HTTPException(status_code=500, detail="设置 Spawn 模型策略失败")
    return {"ok": True, "state": _state_payload()}


@app.delete("/api/models/spawn", dependencies=[Depends(verify_token)])
async def clear_spawn_model_policy_api():
    ok = set_spawn_model_policy("", "")
    if not ok:
        raise HTTPException(status_code=500, detail="清除 Spawn 模型策略失败")
    return {"ok": True, "state": _state_payload()}


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
    return {"ok": True, "state": _state_payload()}


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
    return {"ok": True, "state": _state_payload()}


@app.post("/api/agents/security", dependencies=[Depends(verify_token)])
async def set_agent_security_api(body: AgentSecurityIn):
    ok = _set_workspace_restriction(body.agentId, body.workspaceOnly)
    if not ok:
        raise HTTPException(status_code=400, detail="更新访问限制失败")
    return {"ok": True, "state": _state_payload()}


@app.post("/api/agents/whitelist", dependencies=[Depends(verify_token)])
async def set_control_whitelist_api(body: ControlWhitelistIn):
    caps = [x.strip() for x in (body.capabilities or []) if x and x.strip()]
    if body.enabled and not caps:
        caps = list(RECOMMENDED_CONTROL_PLANE_CAPABILITIES)
    ok = set_agent_control_plane_whitelist(body.agentId, body.enabled, caps)
    if not ok:
        raise HTTPException(status_code=400, detail="更新命令白名单失败")
    return {"ok": True, "state": _state_payload()}


@app.post("/api/dispatch", dependencies=[Depends(verify_token)])
async def set_dispatch_policy_api(body: DispatchPolicyIn):
    allow_agents = body.allowAgents if body.enabled else []
    ok = config.update_subagent_for(
        agent_id=body.agentId,
        allow_agents=allow_agents,
        max_concurrent=body.maxConcurrent,
        inherit_max_concurrent=body.inheritMaxConcurrent,
    )
    if not ok:
        raise HTTPException(status_code=400, detail="更新派发策略失败")
    return {"ok": True, "state": _state_payload()}


@app.get("/api/providers/options", dependencies=[Depends(verify_token)])
async def get_provider_options_api():
    return {"options": get_official_provider_options()}


@app.post("/api/providers/refresh-model-pool", dependencies=[Depends(verify_token)])
async def refresh_model_pool_api():
    ok, message = refresh_official_model_pool()
    return {"ok": ok, "message": message, "state": _state_payload()}


@app.post("/api/search/official", dependencies=[Depends(verify_token)])
async def set_official_search_api(body: OfficialSearchConfigIn):
    provider = (body.provider or "").strip().lower()
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

    return {"ok": True, "state": _state_payload()}


@app.delete("/api/search/official/{provider}", dependencies=[Depends(verify_token)])
async def clear_official_search_api(provider: str):
    pid = (provider or "").strip().lower()
    if pid not in OFFICIAL_SEARCH_SPECS:
        raise HTTPException(status_code=400, detail="不支持的官方搜索服务")
    ok = _clear_official_key_in_config(pid)
    if not ok:
        raise HTTPException(status_code=500, detail="清空官方搜索配置失败")
    return {"ok": True, "state": _state_payload()}


@app.post("/api/search/activate", dependencies=[Depends(verify_token)])
async def activate_default_search_provider(provider: str):
    pid = (provider or "").strip().lower()
    if pid and pid not in OFFICIAL_SEARCH_SPECS:
        raise HTTPException(status_code=400, detail="不支持的默认搜索服务")
    ok = set_search_provider(pid)
    if not ok:
        raise HTTPException(status_code=500, detail="设置默认搜索服务失败")
    return {"ok": True, "state": _state_payload()}


@app.post("/api/search/adapter", dependencies=[Depends(verify_token)])
async def set_adapter_search_api(body: AdapterSearchConfigIn):
    pid = (body.provider or "").strip().lower()
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
    return {"ok": True, "state": _state_payload()}


@app.post("/api/search/failover", dependencies=[Depends(verify_token)])
async def set_search_failover_api(body: SearchFailoverIn):
    primary = (body.primarySource or "").strip().lower()
    fallbacks = [str(x).strip().lower() for x in (body.fallbackSources or []) if str(x).strip()]

    ok_primary = set_primary_source(primary)
    ok_fallback = set_fallback_sources(fallbacks)
    if not ok_primary or not ok_fallback:
        raise HTTPException(status_code=400, detail="设置主备搜索链失败")

    return {"ok": True, "state": _state_payload()}


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
