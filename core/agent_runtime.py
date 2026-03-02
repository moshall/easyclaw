import os
from copy import deepcopy
from typing import Any, Dict, List, Optional


ACCESS_MODE_LABELS: Dict[str, str] = {
    "none": "不访问工作区",
    "ro": "只读自己的工作区",
    "rw": "读写自己的工作区",
}

ACCESS_MODE_HELP: Dict[str, str] = {
    "none": "不挂载真实 workspace。推荐：纯协调、消息中转、最小数据接触场景。仅在启用 sandbox 时才是硬隔离。",
    "ro": "只读挂载自己的 workspace，不能写入。推荐：代码审查、资料检索、风险分析。仅在启用 sandbox 时才是硬隔离。",
    "rw": "读写挂载自己的 workspace。推荐：日常编码、改文档、修配置、多人协作。",
}

CAPABILITY_PRESET_LABELS: Dict[str, str] = {
    "full-access": "完全开放",
    "readonly-analysis": "只读分析",
    "safe-exec": "安全执行",
    "workspace-collab": "工作区协作",
    "messaging": "通讯协调",
}

CAPABILITY_PRESET_HELP: Dict[str, str] = {
    "full-access": "关闭沙箱限制，工具能力全开。适合主 Agent、高信任维护 Agent、需要跨目录处理事务的场景。",
    "readonly-analysis": "保留沙箱，只允许读取和分析，禁止写入和执行。适合审查、检索、复盘。",
    "safe-exec": "保留沙箱，允许执行命令，但不允许写文件。适合环境探测、日志排障、只读诊断。",
    "workspace-collab": "保留沙箱，允许读写自己的 workspace。适合编码、改文档、修本 Agent 目录内配置。",
    "messaging": "偏消息协调与任务分发，不提供完整编码能力。适合调度、中控、路由类 Agent。",
}

CAPABILITY_PRESETS: Dict[str, Dict[str, Any]] = {
    "full-access": {
        "sandbox": {"mode": "off", "scope": "agent"},
        "tools": {"profile": "full"},
    },
    "readonly-analysis": {
        "sandbox": {"mode": "all", "scope": "agent"},
        "tools": {
            "profile": "minimal",
            "deny": ["write", "edit", "apply_patch", "exec", "process"],
        },
    },
    "safe-exec": {
        "sandbox": {"mode": "all", "scope": "agent"},
        "tools": {
            "profile": "coding",
            "deny": ["write", "edit", "apply_patch"],
        },
    },
    "workspace-collab": {
        "sandbox": {"mode": "all", "scope": "agent"},
        "tools": {"profile": "coding"},
    },
    "messaging": {
        "sandbox": {"mode": "off", "scope": "agent"},
        "tools": {"profile": "messaging"},
    },
}

TOOLS_PROFILE_TO_PRESET = {
    "full": "full-access",
    "minimal": "readonly-analysis",
    "messaging": "messaging",
}


def openclaw_root_from_config(config_path: Optional[str]) -> str:
    path = str(config_path or "").strip()
    if not path:
        return "/root/.openclaw"
    return os.path.dirname(path) or "/root/.openclaw"


def resolve_agent_runtime_paths(agent_id: str, config_path: Optional[str] = None) -> Dict[str, str]:
    aid = str(agent_id or "main").strip() or "main"
    root = openclaw_root_from_config(config_path)
    agent_dir = os.path.join(root, "agents", aid, "agent")
    workspace_name = "workspace" if aid == "main" else f"workspace-{aid}"
    return {
        "root": root,
        "agent_dir": agent_dir,
        "sessions_dir": os.path.join(root, "agents", aid, "sessions"),
        "auth_profiles": os.path.join(agent_dir, "auth-profiles.json"),
        "models_json": os.path.join(agent_dir, "models.json"),
        "workspace": os.path.join(root, workspace_name),
    }


def build_agent_access_profile(
    access_mode: str,
    capability_preset: str,
    custom_allow: Optional[List[str]] = None,
    custom_deny: Optional[List[str]] = None,
) -> Dict[str, Any]:
    mode = str(access_mode or "rw").strip().lower()
    if mode not in ACCESS_MODE_LABELS:
        mode = "rw"

    preset = str(capability_preset or "workspace-collab").strip().lower()
    base = deepcopy(CAPABILITY_PRESETS.get(preset, CAPABILITY_PRESETS["workspace-collab"]))
    base["sandbox"]["workspaceAccess"] = mode

    tools = base.setdefault("tools", {})
    if custom_allow is not None:
        tools["allow"] = _dedupe_tokens(custom_allow)
    if custom_deny is not None:
        tools["deny"] = _dedupe_tokens(custom_deny)

    return base


def apply_agent_access_profile(
    agent_entry: Dict[str, Any],
    access_mode: str,
    capability_preset: str,
    custom_allow: Optional[List[str]] = None,
    custom_deny: Optional[List[str]] = None,
) -> Dict[str, Any]:
    profile = build_agent_access_profile(access_mode, capability_preset, custom_allow, custom_deny)
    agent_entry.pop("security", None)
    agent_entry["sandbox"] = profile["sandbox"]
    agent_entry["tools"] = profile["tools"]
    return agent_entry


def extract_agent_access_profile(agent_entry: Dict[str, Any]) -> Dict[str, Any]:
    sandbox = agent_entry.get("sandbox") if isinstance(agent_entry.get("sandbox"), dict) else {}
    tools = agent_entry.get("tools") if isinstance(agent_entry.get("tools"), dict) else {}
    access_mode = str(sandbox.get("workspaceAccess", "rw") or "rw").strip().lower()
    if access_mode not in ACCESS_MODE_LABELS:
        access_mode = "rw"

    profile = str(tools.get("profile", "") or "").strip().lower()
    capability_preset = TOOLS_PROFILE_TO_PRESET.get(profile, "")
    deny = _dedupe_tokens(tools.get("deny", []))

    if not capability_preset:
        if profile == "coding":
            capability_preset = "safe-exec" if any(x in deny for x in ["write", "edit", "apply_patch"]) else "workspace-collab"
        else:
            capability_preset = "workspace-collab"

    return {
        "access_mode": access_mode,
        "access_label": ACCESS_MODE_LABELS.get(access_mode, ACCESS_MODE_LABELS["rw"]),
        "capability_preset": capability_preset,
        "capability_label": CAPABILITY_PRESET_LABELS.get(capability_preset, CAPABILITY_PRESET_LABELS["workspace-collab"]),
        "sandbox": deepcopy(sandbox),
        "tools": deepcopy(tools),
    }


def _dedupe_tokens(values: Any) -> List[str]:
    out: List[str] = []
    if not isinstance(values, list):
        return out
    for item in values:
        token = str(item or "").strip()
        if token and token not in out:
            out.append(token)
    return out
