"""
任务指派 (Routing) 模块 - 全局默认模型、备选链、子 Agent 策略
完全对齐 OpenClaw 官方 CLI 实现
优化版：模型按服务商分组、小贴士、错误提示友好化
"""
import json
import os
import re
import time
from typing import List, Optional
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich.prompt import Prompt, Confirm
from rich import box

from core import (
    OPENCLAW_BIN,
    config,
    get_agent_control_plane_capabilities,
    run_cli,
    run_cli_json,
    set_agent_control_plane_capabilities,
)
from core.agent_runtime import (
    ACCESS_MODE_LABELS,
    CAPABILITY_PRESET_LABELS,
    apply_agent_access_profile,
    extract_agent_access_profile,
    resolve_agent_runtime_paths,
)

console = Console()

from core.utils import safe_input, pause_enter

WORKSPACE_SUFFIX_RE = re.compile(r"^workspace(?:_(\d+))?$")
AGENT_ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*$")
REQUIRED_WORKSPACE_FILES = ["AGENTS.md", "SOUL.md"]
DEFAULT_CONTROL_PLANE_CAPABILITIES = [
    "model.switch",        # /model
    "status.usage.read",   # /status 用量查询
    "skill.usage.read",    # /skill 用量查询
]
RECOMMENDED_CONTROL_PLANE_CAPABILITIES = [
    "model.switch",      # /model
    "status.read",       # /status
    "skill.read",        # /skill
    "session.new",       # /new
    "generation.stop",   # /stop
    "usage.read",        # /usage
    "session.reset",     # /reset
]
_MODEL_STATUS_CACHE = {"ts": 0.0, "default": None, "fallbacks": []}


def _get_agents_list() -> List[dict]:
    agents = config.data.get("agents", {}).get("list", [])
    return agents if isinstance(agents, list) else []


def _main_agents() -> List[dict]:
    return [a for a in _get_agents_list() if isinstance(a, dict) and str(a.get("id", "")).startswith("main")]


def _dispatch_manageable_agents() -> List[dict]:
    """可在派发管理中配置的固定 Agent 列表（优先 main）"""
    agents = [a for a in _get_agents_list() if isinstance(a, dict) and str(a.get("id", "")).strip()]
    if not agents:
        return []
    mains = [a for a in agents if str(a.get("id", "")).startswith("main")]
    others = [a for a in agents if not str(a.get("id", "")).startswith("main")]
    return mains + others


def _is_valid_agent_id(agent_id: str) -> bool:
    return bool(AGENT_ID_RE.match((agent_id or "").strip()))


def _next_main_agent_id() -> str:
    ids = {str(a.get("id", "")) for a in _main_agents()}
    if "main" not in ids:
        return "main"
    idx = 1
    while f"main{idx}" in ids:
        idx += 1
    return f"main{idx}"


def _recommended_main_agent_id() -> str:
    # 优先修复已有但未绑定 workspace 的 main agent
    for a in _main_agents():
        ws = str(a.get("workspace", "") or "").strip()
        if not ws:
            return str(a.get("id", "main") or "main")
    return _next_main_agent_id()


def _default_agent_id_for_form(agents: List[dict]) -> str:
    # 编辑体验优先：已有 agent 时默认定位到第一个（通常是 main）
    if agents:
        first = str(agents[0].get("id", "") or "").strip()
        if first:
            return first
    return _recommended_main_agent_id()


def _agent_by_id(agent_id: str) -> dict:
    return next((a for a in _get_agents_list() if isinstance(a, dict) and str(a.get("id", "")) == agent_id), {})


def _short_workspace(path: str) -> str:
    p = str(path or "").strip()
    if not p:
        return "(未绑定)"
    if len(p) <= 34:
        return p
    return "..." + p[-31:]


def _workspace_health(agent: dict) -> str:
    ws = str(agent.get("workspace", "") or "").strip()
    if not ws:
        return "[yellow]未绑定[/]"
    if not os.path.isdir(ws):
        return "[red]目录不存在[/]"
    missing = [name for name in REQUIRED_WORKSPACE_FILES if not os.path.exists(os.path.join(ws, name))]
    if missing:
        return "[yellow]缺关键文件[/]"
    return "[green]正常[/]"


def _resolve_agent_id_input(ids: List[str], raw: str) -> str:
    val = (raw or "").strip()
    if val in ids:
        return val
    lower_map = {x.lower(): x for x in ids}
    return lower_map.get(val.lower(), "")


def _invalidate_model_status_cache():
    _MODEL_STATUS_CACHE["ts"] = 0.0
    _MODEL_STATUS_CACHE["default"] = None
    _MODEL_STATUS_CACHE["fallbacks"] = []


def _select_agent_id(ids: List[str], title: str = "请选择 Agent", default_id: str = "") -> str:
    """优先编号选择，支持 m 手动输入 ID 兜底"""
    if not ids:
        return ""
    idx_default = ids[0]
    if default_id and default_id in ids:
        idx_default = default_id

    console.print()
    table = Table(box=box.SIMPLE)
    table.add_column("编号", style="cyan", width=6)
    table.add_column("Agent ID", style="bold")
    for i, aid in enumerate(ids, 1):
        table.add_row(str(i), aid)
    console.print(table)
    console.print("[dim]输入编号选择；输入 m 可手动输入 ID；输入 0 取消[/]")
    choices = ["0", "m"] + [str(i) for i in range(1, len(ids) + 1)]
    default_num = str(ids.index(idx_default) + 1)
    pick = Prompt.ask(f"[bold]{title}[/]", choices=choices, default=default_num)
    if pick == "0":
        return ""
    if pick == "m":
        raw = Prompt.ask("[bold]请输入 Agent ID[/]", default=idx_default).strip()
        return _resolve_agent_id_input(ids, raw)
    idx = int(pick) - 1
    if 0 <= idx < len(ids):
        return ids[idx]
    return ""


def _pick_access_mode(default_mode: str = "rw") -> str:
    options = [("1", "none"), ("2", "ro"), ("3", "rw")]
    reverse = {value: key for key, value in options}
    console.print("\n[bold]访问范围:[/]")
    for key, value in options:
        console.print(f"  [cyan]{key}[/] {ACCESS_MODE_LABELS[value]}")
    pick = Prompt.ask("[bold green]>[/]", choices=[x[0] for x in options], default=reverse.get(default_mode, "3"))
    return dict(options).get(pick, "rw")


def _pick_capability_preset(default_preset: str = "workspace-collab") -> str:
    options = [
        ("1", "full-access"),
        ("2", "readonly-analysis"),
        ("3", "safe-exec"),
        ("4", "workspace-collab"),
        ("5", "messaging"),
    ]
    reverse = {value: key for key, value in options}
    console.print("\n[bold]能力级别:[/]")
    for key, value in options:
        console.print(f"  [cyan]{key}[/] {CAPABILITY_PRESET_LABELS[value]}")
    pick = Prompt.ask("[bold green]>[/]", choices=[x[0] for x in options], default=reverse.get(default_preset, "4"))
    return dict(options).get(pick, "workspace-collab")


def _workspace_root_base() -> str:
    defaults = config.data.get("agents", {}).get("defaults", {}) or {}
    base_workspace = str(defaults.get("workspace", "/root/.openclaw/workspace") or "/root/.openclaw/workspace").rstrip("/")
    parent = os.path.dirname(base_workspace) or "/root/.openclaw"
    return parent


def _next_workspace_path(existing_agents: List[dict]) -> str:
    parent = _workspace_root_base()
    used = set()
    for a in existing_agents:
        ws = str(a.get("workspace", "") or "").rstrip("/")
        if not ws:
            continue
        base = os.path.basename(ws)
        m = WORKSPACE_SUFFIX_RE.match(base)
        if m:
            raw = m.group(1)
            used.add(0 if raw is None else int(raw))

    if 0 not in used and not os.path.exists(os.path.join(parent, "workspace")):
        return os.path.join(parent, "workspace")

    idx = 1
    while True:
        if idx not in used:
            candidate = os.path.join(parent, f"workspace_{idx:02d}")
            if not os.path.exists(candidate):
                return candidate
        idx += 1


def _validate_workspace_path(path: str) -> bool:
    p = (path or "").strip().rstrip("/")
    if not p:
        return False
    parent = _workspace_root_base().rstrip("/")
    if not p.startswith(parent + "/"):
        return False
    base = os.path.basename(p)
    # 手动输入轻度放宽：允许 workspace* 命名；自动分配仍使用 workspace/workspace_XX。
    return base.startswith("workspace")


def _validate_existing_workspace(path: str):
    p = (path or "").strip().rstrip("/")
    if not _validate_workspace_path(p):
        return False, "workspace 必须在 /root/.openclaw 下，且名称需以 workspace 开头"
    if not os.path.isdir(p):
        return False, "workspace 目录不存在（仅允许绑定已有目录）"
    missing = [name for name in REQUIRED_WORKSPACE_FILES if not os.path.exists(os.path.join(p, name))]
    if missing:
        return False, f"workspace 缺少必要文件: {', '.join(missing)}"
    return True, ""


def _detect_existing_workspace(existing_agents: List[dict]) -> str:
    parent = _workspace_root_base().rstrip("/")
    if not parent or not os.path.isdir(parent):
        return ""

    used = {
        str(a.get("workspace", "") or "").rstrip("/")
        for a in existing_agents
        if isinstance(a, dict) and str(a.get("workspace", "") or "").strip()
    }

    preferred = os.path.join(parent, "workspace")
    if os.path.isdir(preferred) and preferred.rstrip("/") not in used:
        return preferred

    candidates = []
    for name in sorted(os.listdir(parent)):
        path = os.path.join(parent, name)
        if os.path.isdir(path) and name.startswith("workspace"):
            candidates.append(path.rstrip("/"))

    for candidate in candidates:
        if candidate not in used:
            return candidate
    return ""


def _build_model_config(primary: str, fallbacks_csv: str):
    primary = (primary or "").strip()
    fallbacks = [x.strip() for x in (fallbacks_csv or "").split(",") if x.strip()]
    if not primary and not fallbacks:
        return None
    # OpenClaw 新版本要求 model 使用对象结构。
    return {"primary": primary, "fallbacks": fallbacks}


def _ensure_workspace_scaffold(workspace_path: str, agent_id: str):
    os.makedirs(workspace_path, exist_ok=True)
    # 默认完整模板：核心元信息文件 + 常用目录
    templates = {
        "AGENTS.md": f"# {agent_id} AGENTS\n\n- Scope: {workspace_path}\n- Role: Main agent workspace\n",
        "SOUL.md": f"# {agent_id} SOUL\n\n- Identity: {agent_id}\n- Notes: Fill in persona and principles.\n",
        "TOOLS.md": "# TOOLS\n\n- Document allowed tools, policies and usage notes here.\n",
        "IDENTITY.md": f"# IDENTITY\n\n- Agent ID: {agent_id}\n- Owner: (fill me)\n",
        "USER.md": "# USER\n\n- User preferences and collaboration style.\n",
        "BOOTSTRAP.md": "# BOOTSTRAP\n\n- Startup checklist for this workspace.\n",
        "HEARTBEAT.md": "# HEARTBEAT\n\n- Operational notes and periodic checks.\n",
        "MEMORY.md": "# MEMORY\n\n- Long-term project memory.\n",
        "memory.md": "# memory\n\n- Scratch/short notes.\n",
    }
    for file_name, content in templates.items():
        target = os.path.join(workspace_path, file_name)
        if not os.path.exists(target):
            with open(target, "w", encoding="utf-8") as f:
                f.write(content)

    for folder in ["project", "scripts", "skills", "worktrees", "software"]:
        os.makedirs(os.path.join(workspace_path, folder), exist_ok=True)


def _ensure_agent_runtime_dirs(agent_id: str):
    root = _workspace_root_base().rstrip("/") or "/root/.openclaw"
    agent_root = os.path.join(root, "agents", agent_id)
    os.makedirs(os.path.join(agent_root, "agent"), exist_ok=True)
    os.makedirs(os.path.join(agent_root, "sessions"), exist_ok=True)


def upsert_main_agent_config(
    agent_id: str,
    workspace_path: str,
    model_primary: str = "",
    model_fallbacks_csv: str = "",
    allow_agents: Optional[List[str]] = None,
    sub_model_primary: str = "",
    sub_model_fallbacks_csv: str = "",
    access_mode: str = "rw",
    capability_preset: str = "workspace-collab",
    control_plane_capabilities: Optional[List[str]] = None,
    require_existing: bool = False,
) -> bool:
    if not agent_id:
        return False
    if not _validate_workspace_path(workspace_path):
        return False

    agent_entry = {"id": agent_id, "workspace": workspace_path.rstrip("/")}

    model_cfg = _build_model_config(model_primary, model_fallbacks_csv)
    if model_cfg:
        agent_entry["model"] = model_cfg

    sub_cfg = {}
    if allow_agents is not None:
        sub_cfg["allowAgents"] = allow_agents
    sub_model_cfg = _build_model_config(sub_model_primary, sub_model_fallbacks_csv)
    if sub_model_cfg:
        sub_cfg["model"] = sub_model_cfg
    if sub_cfg:
        agent_entry["subagents"] = sub_cfg

    apply_agent_access_profile(agent_entry, access_mode, capability_preset)

    agents_root = config.data.setdefault("agents", {})
    agents_list = agents_root.get("list")
    if not isinstance(agents_list, list):
        agents_list = []
        agents_root["list"] = agents_list

    replaced = False
    for i, row in enumerate(agents_list):
        if isinstance(row, dict) and row.get("id") == agent_id:
            # 保留未知字段，避免菜单更新时误删未来扩展配置
            merged = dict(row)
            merged["id"] = agent_entry["id"]
            merged["workspace"] = agent_entry["workspace"]

            if "model" in agent_entry:
                merged["model"] = agent_entry["model"]
            else:
                merged.pop("model", None)

            if "subagents" in agent_entry:
                existing_sub = merged.get("subagents") if isinstance(merged.get("subagents"), dict) else {}
                new_sub = dict(existing_sub)
                new_sub.update(agent_entry["subagents"])
                merged["subagents"] = new_sub
            else:
                merged.pop("subagents", None)

            merged.pop("security", None)
            merged["sandbox"] = agent_entry["sandbox"]
            merged["tools"] = agent_entry["tools"]

            agents_list[i] = merged
            replaced = True
            break
    if not replaced and require_existing:
        return False
    if not replaced:
        agents_list.append(agent_entry)

    _ensure_workspace_scaffold(workspace_path, agent_id)
    _ensure_agent_runtime_dirs(agent_id)
    if not config.save():
        return False
    return set_agent_control_plane_capabilities(agent_id, control_plane_capabilities or [])


def _extract_agent_settings(target: dict) -> dict:
    model_primary = ""
    model_fallbacks = ""
    existing_model = target.get("model")
    if isinstance(existing_model, str):
        model_primary = existing_model
    elif isinstance(existing_model, dict):
        model_primary = str(existing_model.get("primary", "") or "")
        model_fallbacks = ",".join(existing_model.get("fallbacks", []) or [])

    sub_cfg = target.get("subagents") if isinstance(target.get("subagents"), dict) else {}
    allow_agents = sub_cfg.get("allowAgents")
    if allow_agents is None:
        allow_agents = []
    sub_model_primary = ""
    sub_model_fallbacks = ""
    existing_sub_model = sub_cfg.get("model")
    if isinstance(existing_sub_model, str):
        sub_model_primary = existing_sub_model
    elif isinstance(existing_sub_model, dict):
        sub_model_primary = str(existing_sub_model.get("primary", "") or "")
        sub_model_fallbacks = ",".join(existing_sub_model.get("fallbacks", []) or [])

    access = extract_agent_access_profile(target)
    control_caps = get_agent_control_plane_capabilities(str(target.get("id", "") or ""))
    workspace_path = str(
        target.get("workspace", "") or resolve_agent_runtime_paths(str(target.get("id", "") or "main"), config.path)["workspace"]
    ).strip()

    return {
        "workspace_path": workspace_path,
        "model_primary": model_primary,
        "model_fallbacks": model_fallbacks,
        "allow_agents": allow_agents,
        "sub_model_primary": sub_model_primary,
        "sub_model_fallbacks": sub_model_fallbacks,
        "access_mode": access["access_mode"],
        "capability_preset": access["capability_preset"],
        "access_label": access["access_label"],
        "capability_label": access["capability_label"],
        "control_caps": control_caps,
    }


def set_agent_control_plane_whitelist(agent_id: str, enabled: bool, capabilities: Optional[List[str]] = None) -> bool:
    target = _agent_by_id(agent_id)
    if not target:
        return False
    settings = _extract_agent_settings(target)
    if not settings["workspace_path"]:
        return False

    caps = capabilities if enabled else []
    caps = [str(x).strip() for x in (caps or []) if str(x).strip()]

    return upsert_main_agent_config(
        agent_id=agent_id,
        workspace_path=settings["workspace_path"],
        model_primary=settings["model_primary"],
        model_fallbacks_csv=settings["model_fallbacks"],
        allow_agents=settings["allow_agents"],
        sub_model_primary=settings["sub_model_primary"],
        sub_model_fallbacks_csv=settings["sub_model_fallbacks"],
        access_mode=settings["access_mode"],
        capability_preset=settings["capability_preset"],
        control_plane_capabilities=caps,
    )


def create_agent_with_official_cli(
    agent_id: str,
    workspace_path: str,
    access_mode: str,
    capability_preset: str,
    control_plane_capabilities: Optional[List[str]] = None,
) -> tuple[bool, str]:
    stdout, stderr, code = run_cli(["agents", "add", agent_id, "--workspace", workspace_path])
    if code != 0:
        return False, stderr or stdout or "openclaw agents add failed"
    config.reload()
    if not _agent_by_id(agent_id):
        return False, "官方 CLI 未写入 Agent，无法继续应用 EasyClaw 附加设置"
    ok = upsert_main_agent_config(
        agent_id=agent_id,
        workspace_path=workspace_path,
        model_primary="",
        model_fallbacks_csv="",
        allow_agents=[],
        sub_model_primary="",
        sub_model_fallbacks_csv="",
        access_mode=access_mode,
        capability_preset=capability_preset,
        control_plane_capabilities=control_plane_capabilities or [],
        require_existing=True,
    )
    if not ok:
        return False, "官方创建成功，但写入访问范围/能力级别失败"
    return True, stdout or "ok"


def set_agent_model_policy(agent_id: str, primary: str, fallbacks_csv: str) -> bool:
    target = _agent_by_id(agent_id)
    if not target:
        return False
    settings = _extract_agent_settings(target)
    if not settings["workspace_path"]:
        return False
    return upsert_main_agent_config(
        agent_id=agent_id,
        workspace_path=settings["workspace_path"],
        model_primary=primary,
        model_fallbacks_csv=fallbacks_csv,
        allow_agents=settings["allow_agents"],
        sub_model_primary=settings["sub_model_primary"],
        sub_model_fallbacks_csv=settings["sub_model_fallbacks"],
        access_mode=settings["access_mode"],
        capability_preset=settings["capability_preset"],
        control_plane_capabilities=settings["control_caps"],
    )


def clear_agent_model_policy(agent_id: str) -> bool:
    return set_agent_model_policy(agent_id, "", "")


def list_agent_model_overrides() -> List[str]:
    """返回已配置独立模型策略的 Agent ID 列表。"""
    config.reload()
    out = []
    for a in _dispatch_manageable_agents():
        settings = _extract_agent_settings(a)
        if settings["model_primary"] or settings["model_fallbacks"]:
            aid = str(a.get("id", "")).strip()
            if aid:
                out.append(aid)
    return out


def list_agent_model_override_details() -> List[dict]:
    """返回已配置独立模型的 Agent 详情（主模型/备选链）。"""
    config.reload()
    out = []
    for a in _dispatch_manageable_agents():
        settings = _extract_agent_settings(a)
        if not (settings["model_primary"] or settings["model_fallbacks"]):
            continue
        aid = str(a.get("id", "")).strip()
        if not aid:
            continue
        fallbacks = [x.strip() for x in str(settings["model_fallbacks"] or "").split(",") if x.strip()]
        out.append({
            "agent_id": aid,
            "primary": str(settings["model_primary"] or "").strip(),
            "fallbacks": fallbacks,
        })
    return out


def get_spawn_model_policy() -> tuple:
    """获取 Spawn Agent 默认模型策略（agents.defaults.subagents.model）。"""
    config.reload()
    sub = config.data.get("agents", {}).get("defaults", {}).get("subagents", {}) or {}
    model_cfg = sub.get("model")
    primary, fallbacks = _extract_model_cfg(model_cfg)
    return primary, fallbacks


def set_spawn_model_policy(primary: str, fallbacks_csv: str) -> bool:
    """设置 Spawn Agent 默认模型策略（为空则清除，回到继承全局）。"""
    config.reload()
    agents = config.data.setdefault("agents", {})
    defaults = agents.setdefault("defaults", {})
    sub = defaults.get("subagents")
    if not isinstance(sub, dict):
        sub = {}
        defaults["subagents"] = sub

    model_cfg = _build_model_config(primary, fallbacks_csv)
    if model_cfg:
        sub["model"] = model_cfg
    else:
        sub.pop("model", None)
    ok = config.save()
    config.reload()
    return ok


def spawn_model_policy_menu():
    while True:
        console.clear()
        console.print(Panel(
            Text("🧬 Spawn Agent 默认模型优先级", style="bold cyan", justify="center"),
            box=box.DOUBLE
        ))
        primary, fallbacks = get_spawn_model_policy()
        console.print()
        console.print("[bold]当前设置:[/]")
        if primary:
            console.print(f"  [yellow]主模型:[/] [green]{primary}[/]")
        else:
            console.print("  [yellow]主模型:[/] [dim](继承全局)[/]")
        if fallbacks:
            console.print(f"  [yellow]备用链:[/] [cyan]{' → '.join(fallbacks)}[/]")
        else:
            console.print("  [yellow]备用链:[/] [dim](继承全局)[/]")
        console.print()
        console.print("[bold]操作:[/]")
        console.print("  [cyan]1[/] 设置/更新 Spawn 默认模型")
        console.print("  [cyan]2[/] 清除 Spawn 覆盖（继承全局）")
        console.print("  [cyan]0[/] 返回")
        console.print()
        choice = Prompt.ask("[bold green]>[/]", choices=["0", "1", "2"], default="0")
        if choice == "0":
            return
        if choice == "2":
            ok = set_spawn_model_policy("", "")
            console.print("\n[green]✅ 已清除 Spawn 模型覆盖[/]" if ok else "\n[bold red]❌ 清除失败[/]")
            pause_enter()
            continue

        p = pick_model_from_catalog(
            title="选择 Spawn Agent 主模型",
            default_model=primary or "",
            allow_empty=True,
        )
        f_csv = pick_fallbacks_from_catalog(
            title="选择 Spawn Agent 备用模型",
            default_csv=",".join(fallbacks),
            exclude_model=p,
        )
        ok = set_spawn_model_policy(p, f_csv)
        console.print("\n[green]✅ 已更新 Spawn 模型优先级[/]" if ok else "\n[bold red]❌ 更新失败[/]")
        pause_enter()


def global_model_policy_menu():
    """全局模型优先级菜单（统一主模型+备用链管理）。"""
    while True:
        console.clear()
        console.print(Panel(
            Text("🌐 全局模型优先级", style="bold cyan", justify="center"),
            box=box.DOUBLE
        ))
        console.print()
        default_model = get_default_model()
        fallbacks = get_fallbacks()
        console.print("[bold]当前全局策略:[/]")
        console.print(f"  [yellow]主模型:[/] [green]{default_model}[/]" if default_model else "  [yellow]主模型:[/] [dim](未设置)[/]")
        if fallbacks:
            console.print(f"  [yellow]备用链:[/] [cyan]{' → '.join(fallbacks)}[/]")
        else:
            console.print("  [yellow]备用链:[/] [dim](未设置)[/]")
        console.print()
        console.print("[bold]操作:[/]")
        console.print("  [cyan]1[/] 设置全局主模型")
        console.print("  [cyan]2[/] 设置全局备用链")
        console.print("  [cyan]0[/] 返回")
        console.print()
        choice = Prompt.ask("[bold green]>[/]", choices=["0", "1", "2"], default="0")
        if choice == "0":
            return
        if choice == "1":
            set_default_model_menu()
        elif choice == "2":
            manage_fallbacks_menu()


def main_agent_settings_menu():
    def workspace_management_menu():
        while True:
            console.clear()
            console.print(Panel(
                Text("🗂️ 工作区管理", style="bold cyan", justify="center"),
                box=box.DOUBLE
            ))
            config.reload()
            agents_local = _dispatch_manageable_agents()
            console.print()
            if not agents_local:
                console.print("[yellow]⚠️ 暂无可绑定的 Agent，请先新增 Agent[/]")
                pause_enter()
                return
            console.print("[bold]操作:[/]")
            console.print("  [cyan]1[/] 手动绑定工作区")
            console.print("  [cyan]2[/] 一键识别并绑定工作区")
            console.print("  [cyan]0[/] 返回")
            console.print()
            op = Prompt.ask("[bold green]>[/]", choices=["0", "1", "2"], default="0")
            if op == "0":
                return

            if op == "1":
                ids = [str(a.get("id", "")) for a in agents_local if str(a.get("id", ""))]
                agent_id = _select_agent_id(ids, title="请选择要绑定工作区的 Agent", default_id=ids[0])
                if not agent_id:
                    console.print("\n[yellow]⚠️ 已取消选择[/]")
                    pause_enter()
                    continue

                target = _agent_by_id(agent_id)
                current_ws = str(target.get("workspace", "") or "").strip()
                default_ws = current_ws if current_ws else os.path.join(_workspace_root_base(), "workspace")
                workspace_path = Prompt.ask("[bold]请输入要绑定的 workspace 绝对路径（必须已存在）[/]", default=default_ws).strip()
                ws_ok, ws_err = _validate_existing_workspace(workspace_path)
                if not ws_ok:
                    console.print(f"\n[bold red]❌ {ws_err}[/]")
                    pause_enter()
                    continue
                settings = _extract_agent_settings(target)

                ok = upsert_main_agent_config(
                    agent_id=agent_id,
                    workspace_path=workspace_path,
                    model_primary=settings["model_primary"],
                    model_fallbacks_csv=settings["model_fallbacks"],
                    allow_agents=settings["allow_agents"],
                    sub_model_primary=settings["sub_model_primary"],
                    sub_model_fallbacks_csv=settings["sub_model_fallbacks"],
                    access_mode=settings["access_mode"],
                    capability_preset=settings["capability_preset"],
                    control_plane_capabilities=settings["control_caps"],
                )
                if ok:
                    config.reload()
                    console.print(f"\n[green]✅ 已完成工作区绑定[/]")
                    console.print(f"  [dim]变更: Agent {agent_id}[/]")
                    console.print(f"  [dim]结果: workspace -> {workspace_path}[/]")
                    console.print("  [dim]生效: 即时生效（无需重启）[/]")
                else:
                    console.print("\n[bold red]❌ 工作区绑定失败[/]")
                pause_enter()
                continue

            if op == "2":
                if len(agents_local) != 1:
                    console.print("\n[yellow]⚠️ 自动探测仅支持当前仅有 1 个 Agent 的场景[/]")
                    console.print("[dim]请使用「1 手动绑定工作区」选择 Agent 和目录[/]")
                    pause_enter()
                    continue
                unbound_agents = [a for a in agents_local if not str(a.get("workspace", "") or "").strip()]
                target_agents = unbound_agents if unbound_agents else agents_local
                if len(target_agents) == 1:
                    agent_id = str(target_agents[0].get("id", "") or "").strip()
                else:
                    ids = [str(a.get("id", "")) for a in target_agents if str(a.get("id", ""))]
                    agent_id = _select_agent_id(ids, title="请选择自动绑定目标 Agent", default_id=ids[0])
                    if not agent_id:
                        console.print("\n[yellow]⚠️ 已取消选择[/]")
                        pause_enter()
                        continue

                workspace_path = _detect_existing_workspace(_get_agents_list())
                if not workspace_path:
                    console.print("\n[yellow]⚠️ 未探测到可绑定的 workspace 目录[/]")
                    console.print(f"  [dim]查找范围: {_workspace_root_base()} 下 workspace* 且未被其他 Agent 使用[/]")
                    pause_enter()
                    continue

                target = _agent_by_id(agent_id)
                settings = _extract_agent_settings(target)

                ok = upsert_main_agent_config(
                    agent_id=agent_id,
                    workspace_path=workspace_path,
                    model_primary=settings["model_primary"],
                    model_fallbacks_csv=settings["model_fallbacks"],
                    allow_agents=settings["allow_agents"],
                    sub_model_primary=settings["sub_model_primary"],
                    sub_model_fallbacks_csv=settings["sub_model_fallbacks"],
                    access_mode=settings["access_mode"],
                    capability_preset=settings["capability_preset"],
                    control_plane_capabilities=settings["control_caps"],
                )
                if ok:
                    config.reload()
                    console.print(f"\n[green]✅ 已完成自动绑定[/]")
                    console.print(f"  [dim]变更: Agent {agent_id}[/]")
                    console.print(f"  [dim]结果: workspace -> {workspace_path}[/]")
                    console.print("  [dim]生效: 即时生效（无需重启）[/]")
                else:
                    console.print("\n[bold red]❌ 自动绑定失败[/]")
                pause_enter()
                continue

    while True:
        console.clear()
        console.print(Panel(
            Text("🧭 Agent 与工作区", style="bold cyan", justify="center"),
            box=box.DOUBLE
        ))
        config.reload()
        agents = _dispatch_manageable_agents()
        console.print()
        if agents:
            table = Table(box=box.SIMPLE)
            table.add_column("Agent", style="cyan")
            table.add_column("工作区", style="bold")
            table.add_column("访问范围", style="yellow")
            table.add_column("能力级别", style="yellow")
            table.add_column("模型策略", style="magenta")
            table.add_column("派发", style="green")
            table.add_column("健康", style="white")
            bound_count = 0
            bad_count = 0
            for a in agents:
                settings = _extract_agent_settings(a)
                model_overridden = bool(settings["model_primary"] or settings["model_fallbacks"])
                allow_agents = settings["allow_agents"] if isinstance(settings["allow_agents"], list) else []
                if not allow_agents:
                    dispatch = "已关闭"
                elif allow_agents == ["*"]:
                    dispatch = "已开启(全部)"
                else:
                    dispatch = f"已开启(仅{len(allow_agents)}个Agent)"
                health = _workspace_health(a)
                if str(a.get("workspace", "") or "").strip():
                    bound_count += 1
                if "目录不存在" in health or "缺关键文件" in health or "未绑定" in health:
                    bad_count += 1
                table.add_row(
                    str(a.get("id", "")),
                    _short_workspace(str(a.get("workspace", "(未绑定)"))),
                    settings["access_label"],
                    settings["capability_label"],
                    "独立模型" if model_overridden else "跟随全局",
                    dispatch,
                    health,
                )
            console.print(table)
            console.print()
            console.print(
                f"[dim]摘要: Agent {len(agents)} | 已绑定工作区 {bound_count} | 异常 {bad_count}[/]"
            )
            unbound = [str(a.get("id", "")) for a in agents if not str(a.get("workspace", "") or "").strip()]
            if unbound:
                console.print()
                console.print(f"[yellow]⚠️ 未绑定 workspace: {', '.join(unbound)}[/]")
        else:
            console.print("[dim]尚未创建 Agent[/]")
        console.print()
        console.print("[bold]操作:[/]")
        console.print("  [cyan]1[/] 新增 Agent")
        console.print("  [cyan]2[/] 工作区管理")
        console.print("  [cyan]3[/] 访问权限与快捷命令放行")
        console.print("  [cyan]0[/] 返回")
        console.print()
        choice = Prompt.ask("[bold green]>[/]", choices=["0", "1", "2", "3"], default="0")
        if choice == "0":
            return
        if choice == "2":
            workspace_management_menu()
            continue
        if choice == "3":
            if not agents:
                console.print("\n[yellow]⚠️ 暂无可设置的 Agent[/]")
                pause_enter()
                continue
            ids = [str(a.get("id", "")) for a in agents if str(a.get("id", ""))]
            if len(ids) == 1:
                agent_id = ids[0]
                console.print(f"\n[dim]已自动选择 Agent: {agent_id}[/]")
            else:
                agent_id = _select_agent_id(ids, title="请选择要编辑白名单的 Agent", default_id=ids[0])
                if not agent_id:
                    console.print("\n[yellow]⚠️ 已取消选择[/]")
                    pause_enter()
                    continue

            target = _agent_by_id(agent_id)
            settings = _extract_agent_settings(target)
            if not settings["workspace_path"]:
                console.print("\n[yellow]⚠️ 该 Agent 尚未绑定 workspace，请先执行绑定/修复[/]")
                pause_enter()
                continue

            current_caps = settings["control_caps"]
            current_str = ", ".join(current_caps) if current_caps else "(关闭)"
            console.print(f"\n[dim]当前访问范围: {settings['access_label']}[/]")
            console.print(f"[dim]当前能力级别: {settings['capability_label']}[/]")
            console.print(f"[dim]当前快捷命令放行: {current_str}[/]")
            console.print("[bold]操作:[/]")
            console.print("  [cyan]1[/] 更新访问范围与能力级别")
            console.print("  [cyan]2[/] 开启推荐快捷命令放行")
            console.print("  [cyan]3[/] 关闭快捷命令放行")
            console.print("  [cyan]4[/] 自定义快捷命令放行")
            console.print("  [cyan]0[/] 返回")
            op = Prompt.ask("[bold green]>[/]", choices=["0", "1", "2", "3", "4"], default="0")
            if op == "0":
                continue
            if op == "1":
                access_mode = _pick_access_mode(settings["access_mode"])
                capability_preset = _pick_capability_preset(settings["capability_preset"])
                ok = upsert_main_agent_config(
                    agent_id=agent_id,
                    workspace_path=settings["workspace_path"],
                    model_primary=settings["model_primary"],
                    model_fallbacks_csv=settings["model_fallbacks"],
                    allow_agents=settings["allow_agents"],
                    sub_model_primary=settings["sub_model_primary"],
                    sub_model_fallbacks_csv=settings["sub_model_fallbacks"],
                    access_mode=access_mode,
                    capability_preset=capability_preset,
                    control_plane_capabilities=current_caps,
                )
                if ok:
                    console.print("\n[green]✅ 已更新访问权限[/]")
                    console.print(f"  [dim]访问范围: {ACCESS_MODE_LABELS[access_mode]}[/]")
                    console.print(f"  [dim]能力级别: {CAPABILITY_PRESET_LABELS[capability_preset]}[/]")
                else:
                    console.print("\n[bold red]❌ 更新失败[/]")
                pause_enter()
                continue
            if op == "2":
                ok = set_agent_control_plane_whitelist(
                    agent_id=agent_id,
                    enabled=True,
                    capabilities=RECOMMENDED_CONTROL_PLANE_CAPABILITIES,
                )
            elif op == "3":
                ok = set_agent_control_plane_whitelist(agent_id=agent_id, enabled=False, capabilities=[])
            else:
                raw = Prompt.ask("[bold]请输入能力列表（逗号分隔）[/]", default="").strip()
                caps = [x.strip() for x in raw.split(",") if x.strip()]
                ok = set_agent_control_plane_whitelist(agent_id=agent_id, enabled=bool(caps), capabilities=caps)

            if ok:
                console.print("\n[green]✅ 已更新快捷命令放行[/]")
                console.print(f"  [dim]变更: Agent {agent_id}[/]")
                console.print("  [dim]结果: controlPlaneCapabilities 已更新[/]")
                console.print("  [dim]生效: 下次会话生效（建议重启 agent 会话）[/]")
            else:
                console.print("\n[bold red]❌ 设置失败[/]")
            pause_enter()
            continue

        default_id = _next_main_agent_id()
        agent_id = Prompt.ask("[bold]新 Agent ID[/]", default=default_id).strip() or default_id
        if _agent_by_id(agent_id):
            console.print(f"\n[bold red]❌ Agent 已存在: {agent_id}[/]")
            console.print("[dim]请改用不同 Agent ID[/]")
            pause_enter()
            continue

        if not _is_valid_agent_id(agent_id):
            console.print("\n[bold red]❌ Agent ID 仅支持英文开头，包含字母/数字/_/-[/]")
            pause_enter()
            continue

        existing = {}
        existing_settings = _extract_agent_settings(existing) if existing else {
            "workspace_path": "",
            "access_mode": "rw",
            "capability_preset": "workspace-collab",
            "access_label": ACCESS_MODE_LABELS["rw"],
            "capability_label": CAPABILITY_PRESET_LABELS["workspace-collab"],
            "control_caps": [],
            "model_primary": "",
            "model_fallbacks": "",
            "allow_agents": [],
            "sub_model_primary": "",
            "sub_model_fallbacks": "",
        }

        default_ws = existing_settings["workspace_path"] or _next_workspace_path(_get_agents_list())
        workspace_path = Prompt.ask("[bold]请输入 workspace 绝对路径[/]", default=default_ws).strip()
        if not _validate_workspace_path(workspace_path):
            console.print("\n[bold red]❌ workspace 必须在 /root/.openclaw 下，且名称需以 workspace 开头[/]")
            pause_enter()
            continue

        access_mode = _pick_access_mode(existing_settings["access_mode"])
        capability_preset = _pick_capability_preset(existing_settings["capability_preset"])
        control_caps = existing_settings["control_caps"]

        ok, detail = create_agent_with_official_cli(
            agent_id=agent_id,
            workspace_path=workspace_path,
            access_mode=access_mode,
            capability_preset=capability_preset,
            control_plane_capabilities=control_caps,
        )
        if ok:
            config.reload()
            console.print(f"\n[green]✅ 已完成官方 Agent 创建[/]")
            console.print(f"  [dim]变更: Agent {agent_id}[/]")
            console.print(f"  [dim]结果: workspace -> {workspace_path}[/]")
            console.print(f"  [dim]访问范围: {ACCESS_MODE_LABELS[access_mode]}[/]")
            console.print(f"  [dim]能力级别: {CAPABILITY_PRESET_LABELS[capability_preset]}[/]")
            console.print("  [dim]生效: 创建已走官方 CLI；附加权限配置即时写入[/]")
        else:
            console.print("\n[bold red]❌ 创建失败[/]")
            console.print(f"  [dim]原因: {detail}[/]")
        pause_enter()


def agent_model_policy_menu():
    while True:
        console.clear()
        console.print(Panel(
            Text("🎯 Agent 模型优先级", style="bold cyan", justify="center"),
            box=box.DOUBLE
        ))
        config.reload()
        agents = _dispatch_manageable_agents()
        if not agents:
            console.print("\n[yellow]⚠️ 暂无可配置的 Agent[/]")
            pause_enter()
            return

        table = Table(box=box.SIMPLE)
        table.add_column("Agent", style="cyan")
        table.add_column("模型策略", style="bold")
        for a in agents:
            settings = _extract_agent_settings(a)
            if settings["model_primary"] or settings["model_fallbacks"]:
                val = settings["model_primary"] or "(仅备选)"
                if settings["model_fallbacks"]:
                    val = f"{val} | {' -> '.join([x for x in settings['model_fallbacks'].split(',') if x])}"
                table.add_row(str(a.get("id", "")), f"[green]覆盖[/] {val}")
            else:
                table.add_row(str(a.get("id", "")), "[dim]继承全局[/]")
        console.print()
        console.print(table)
        console.print()
        console.print("[bold]操作:[/]")
        console.print("  [cyan]1[/] 设置/更新 Agent 覆盖策略")
        console.print("  [cyan]2[/] 清除 Agent 覆盖（继承全局）")
        console.print("  [cyan]0[/] 返回")
        console.print()
        choice = Prompt.ask("[bold green]>[/]", choices=["0", "1", "2"], default="0")
        if choice == "0":
            return

        ids = [str(a.get("id", "")) for a in agents if str(a.get("id", ""))]
        agent_id = _select_agent_id(ids, title="请选择 Agent", default_id=ids[0])
        if not agent_id:
            console.print("\n[yellow]⚠️ 已取消选择[/]")
            pause_enter()
            continue

        target = _agent_by_id(agent_id)
        settings = _extract_agent_settings(target)
        if not settings["workspace_path"]:
            console.print("\n[yellow]⚠️ 该 Agent 未绑定 workspace，无法设置覆盖策略[/]")
            pause_enter()
            continue

        if choice == "2":
            ok = clear_agent_model_policy(agent_id)
            console.print("\n[green]✅ 已清除 Agent 覆盖策略[/]" if ok else "\n[bold red]❌ 清除失败[/]")
            pause_enter()
            continue

        primary = pick_model_from_catalog(
            title="选择 Agent 主模型",
            default_model=settings["model_primary"],
            allow_empty=True,
        )
        fallbacks = pick_fallbacks_from_catalog(
            title="选择 Agent 备选模型",
            default_csv=settings["model_fallbacks"],
            exclude_model=primary,
        )
        ok = set_agent_model_policy(agent_id, primary, fallbacks)
        console.print("\n[green]✅ 已更新 Agent 模型覆盖策略[/]" if ok else "\n[bold red]❌ 更新失败[/]")
        pause_enter()

def menu_routing():
    """任务指派主菜单"""
    while True:
        console.clear()
        console.print()
        console.print("[bold cyan]========== 🤖 任务指派 (Routing) ==========[/]")
        console.print()
        
        # 小贴士
        console.print(Panel(
            Text("💡 在这里设置你的默认模型和备选链，OpenClaw 会自动切换", 
                 style="dim", justify="center"),
            box=box.ROUNDED,
            border_style="blue"
        ))
        
        # 获取当前状态
        with console.status("[yellow]⏳ 正在获取当前状态...[/]"):
            default_model = get_default_model()
            fallbacks = get_fallbacks()
            sub_status = config.get_subagent_status()
        
        # 显示当前配置
        console.print()
        console.print(Panel(
            Text("当前配置", style="bold", justify="center"),
            box=box.DOUBLE
        ))
        
        console.print()
        if default_model:
            console.print(f"  [bold]🌟 首选模型:[/] [green]{default_model}[/]")
        else:
            console.print(f"  [bold]🌟 首选模型:[/] [yellow](未设置)[/]")
        
        if fallbacks:
            console.print(f"  [bold]🔄 备选链:[/] [cyan]{' → '.join(fallbacks)}[/]")
        else:
            console.print(f"  [bold]🔄 备选链:[/] [dim](未设置)[/]")
        
        sub_str = "[green]✅ 已启用[/]" if sub_status["enabled"] else "[red]❌ 已禁用[/]"
        console.print(f"  [bold]👥 子 Agent:[/] {sub_str} (并发上限: {sub_status['maxConcurrent']})")
        
        console.print()
        console.print("[bold]操作:[/]")
        console.print("  [cyan]1[/] 设置首选模型")
        console.print("  [cyan]2[/] 管理备选链")
        console.print("  [cyan]3[/] Agent派发管理")
        console.print("  [cyan]4[/] 主 Agent 管理")
        console.print("  [cyan]0[/] 返回")
        console.print()
        
        # 接受大小写
        choice = Prompt.ask("[bold green]>[/]", default="0").strip().lower()
        while choice not in ["0", "1", "2", "3", "4"]:
            choice = Prompt.ask("[bold green]>[/]", default="0").strip().lower()
        
        if choice == "0":
            break
        elif choice == "1":
            set_default_model_menu()
        elif choice == "2":
            manage_fallbacks_menu()
        elif choice == "3":
            subagent_settings_menu()
        elif choice == "4":
            main_agent_settings_menu()


def get_default_model() -> Optional[str]:
    """获取当前默认模型（优先本地配置，缺失时降级 CLI）"""
    default_model, _ = _get_model_status()
    return default_model


def get_fallbacks() -> List[str]:
    """获取当前备选链（优先本地配置，缺失时降级 CLI）"""
    _, fallbacks = _get_model_status()
    return fallbacks


def _extract_model_cfg(model_cfg) -> tuple:
    """解析模型配置，返回 (primary, fallbacks)"""
    if isinstance(model_cfg, str):
        return model_cfg.strip() or None, []
    if isinstance(model_cfg, dict):
        primary = str(model_cfg.get("primary", "") or "").strip() or None
        raw = model_cfg.get("fallbacks", [])
        fallbacks = [str(x).strip() for x in raw if str(x).strip()] if isinstance(raw, list) else []
        return primary, fallbacks
    return None, []


def _get_model_status() -> tuple:
    """读取首页模型状态，优先本地配置（毫秒级），必要时降级 CLI"""
    now = time.time()
    if now - float(_MODEL_STATUS_CACHE.get("ts", 0.0)) < 2.0:
        return _MODEL_STATUS_CACHE.get("default"), list(_MODEL_STATUS_CACHE.get("fallbacks", []))

    try:
        config.reload()
        defaults_model = config.get("agents.defaults.model", None)
        if defaults_model is not None:
            primary, fallbacks = _extract_model_cfg(defaults_model)
            _MODEL_STATUS_CACHE.update({"ts": now, "default": primary, "fallbacks": fallbacks})
            return primary, fallbacks

        for a in config.get("agents.list", []) or []:
            if isinstance(a, dict) and a.get("id") == "main":
                primary, fallbacks = _extract_model_cfg(a.get("model"))
                _MODEL_STATUS_CACHE.update({"ts": now, "default": primary, "fallbacks": fallbacks})
                return primary, fallbacks
    except Exception:
        pass

    # 配置缺失时再走官方 CLI（单次调用拿 default + fallbacks）
    try:
        data = run_cli_json(["models", "status"])
        if "error" not in data:
            primary = data.get("defaultModel")
            fallbacks = data.get("fallbacks", [])
            if not isinstance(fallbacks, list):
                fallbacks = []
            _MODEL_STATUS_CACHE.update({"ts": now, "default": primary, "fallbacks": fallbacks})
            return primary, fallbacks
    except Exception:
        pass

    _MODEL_STATUS_CACHE.update({"ts": now, "default": None, "fallbacks": []})
    return None, []


def _load_model_catalog() -> List[dict]:
    config.reload()
    return config.get_all_models_flat()


def pick_model_from_catalog(title: str, default_model: str = "", allow_empty: bool = True) -> str:
    all_models = _load_model_catalog()
    if not all_models:
        console.print("\n[yellow]⚠️ 当前无可选模型，请先在资源库激活模型[/]")
        pause_enter()
        return default_model or ""

    index_by_name = {m["full_name"]: i + 1 for i, m in enumerate(all_models)}
    default_idx = str(index_by_name.get(default_model, 0))

    while True:
        console.clear()
        console.print(Panel(Text(title, style="bold cyan", justify="center"), box=box.DOUBLE))
        console.print()
        if default_model:
            console.print(f"[dim]当前值: {default_model}[/]")
        elif allow_empty:
            console.print("[dim]当前值: (空)[/]")

        from collections import defaultdict
        grouped = defaultdict(list)
        for i, m in enumerate(all_models, 1):
            provider = m["full_name"].split("/", 1)[0] if "/" in m["full_name"] else "其他"
            grouped[provider].append((i, m))

        for provider in sorted(grouped.keys()):
            console.print(f"  [bold][cyan]{provider}[/][/]:")
            for idx, m in grouped[provider]:
                mark = "⭐ " if m["full_name"] == default_model else "   "
                console.print(f"    {mark}[{idx}] {m['display']}")

        console.print()
        if allow_empty:
            console.print("  [cyan]0[/] 设为空")
        console.print("  [cyan]q[/] 保持当前值并返回")
        choices = [str(i) for i in range(1, len(all_models) + 1)] + ["q"]
        if allow_empty:
            choices = ["0"] + choices
        choice = Prompt.ask("[bold green]>[/]", choices=choices, default=(default_idx if default_idx != "0" else ("0" if allow_empty else "q")))
        if choice == "q":
            return default_model or ""
        if choice == "0":
            return ""
        idx = int(choice) - 1
        if 0 <= idx < len(all_models):
            return all_models[idx]["full_name"]


def pick_fallbacks_from_catalog(title: str, default_csv: str = "", exclude_model: str = "") -> str:
    all_models = _load_model_catalog()
    selected = [x.strip() for x in (default_csv or "").split(",") if x.strip()]
    if not all_models:
        return ",".join(selected)

    candidates = [m for m in all_models if m["full_name"] != exclude_model]
    index_map = {str(i + 1): m["full_name"] for i, m in enumerate(candidates)}
    default_indexes = [k for k, v in index_map.items() if v in selected]

    while True:
        console.clear()
        console.print(Panel(Text(title, style="bold cyan", justify="center"), box=box.DOUBLE))
        console.print()
        console.print(f"[dim]当前值: {', '.join(selected) if selected else '(空)'}[/]")
        console.print("[dim]输入规则: 多选请用逗号，如 1,3,8；输入 q 保持当前值[/]")
        console.print()
        for i, m in enumerate(candidates, 1):
            mark = "✅" if m["full_name"] in selected else "⬜"
            console.print(f"  [{i}] {mark} {m['display']}")
        raw_default = ",".join(default_indexes) if default_indexes else ""
        raw = Prompt.ask("[bold green]选择编号[/]", default=raw_default).strip()
        if raw.lower() == "q":
            return ",".join(selected)
        if not raw:
            return ""
        parts = [x.strip() for x in raw.split(",") if x.strip()]
        if not all(p.isdigit() and p in index_map for p in parts):
            console.print("\n[bold red]❌ 输入无效，请用编号列表（如 1,2,5）[/]")
            pause_enter()
            continue
        chosen = [index_map[p] for p in parts]
        # 去重且保持顺序
        seen = set()
        ordered = []
        for x in chosen:
            if x not in seen:
                seen.add(x)
                ordered.append(x)
        return ",".join(ordered)


def set_default_model_menu():
    """设置首选模型菜单"""
    while True:
        console.clear()
        console.print(Panel(
            Text("🌟 设置首选模型", style="bold cyan", justify="center"),
            box=box.DOUBLE
        ))
        
        # 小贴士
        console.print()
        console.print("  [dim]💡 首选模型是 OpenClaw 优先使用的模型[/]")
        console.print()
        
        # 获取所有可用模型
        try:
            config.reload()
            all_models = config.get_all_models_flat()
        except Exception as e:
            console.print(f"\n[bold red]❌ 获取模型列表失败: {e}[/]")
            pause_enter()
            return
        
        if not all_models:
            console.print("\n[yellow]⚠️ 资源库中无可用模型，请先在「资源库」中激活模型[/]")
            pause_enter()
            return
        
        console.print()
        console.print("[bold]可选模型（按服务商分组）:[/]")
        console.print()
        
        # 按服务商分组
        from collections import defaultdict
        models_by_provider = defaultdict(list)
        for i, m in enumerate(all_models, 1):
            if "/" in m['full_name']:
                provider = m['full_name'].split("/", 1)[0]
            else:
                provider = "其他"
            models_by_provider[provider].append((i, m))
        
        # 显示
        for provider in sorted(models_by_provider.keys()):
            console.print(f"  [bold][cyan]{provider}[/][/]:")
            for idx, m in models_by_provider[provider]:
                console.print(f"    [{idx}] {m['display']}")
        
        console.print()
        console.print("[cyan]0[/] 返回")
        console.print()
        
        choices = ["0"] + [str(i) for i in range(1, len(all_models) + 1)]
        choice = Prompt.ask("[bold green]>[/]", choices=choices, default="0")
        
        if choice == "0":
            break
        elif choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(all_models):
                model = all_models[idx]['full_name']
                set_default_model(model)


def set_default_model(model: str):
    """设置默认模型（使用 CLI，错误提示友好化）"""
    console.print(f"\n[yellow]⏳ 正在设置首选模型: {model}...[/]")
    try:
        # 先手动备份配置
        config.reload()
        backup_path = config.backup()
        if backup_path:
            console.print(f"  [dim]💡 已备份配置到: {backup_path}[/]")
        
        stdout, stderr, code = run_cli(["models", "set", model])
        
        if code == 0:
            _invalidate_model_status_cache()
            console.print(f"\n[green]✅ 已设置首选模型: {model}[/]")
            console.print("\n[dim]💡 此更改热生效，无需重启服务[/]")
        else:
            console.print(f"\n[bold red]❌ 设置失败[/]")
            if stderr:
                console.print(f"  [dim]详情: {stderr}[/]")
    except Exception as e:
        console.print(f"\n[bold red]❌ 设置失败: {e}[/]")
    
        pause_enter()


def manage_fallbacks_menu():
    """管理备选链菜单"""
    while True:
        console.clear()
        console.print(Panel(
            Text("🔄 管理备选链", style="bold cyan", justify="center"),
            box=box.DOUBLE
        ))
        
        # 小贴士
        console.print()
        console.print("  [dim]💡 备选链是当首选模型不可用时，OpenClaw 会依次尝试的模型[/]")
        console.print("  [dim]   支持多层备选：首选 → 备选1 → 备选2 → ...[/]")
        console.print("  [dim]⚠️  目前 OpenClaw 官方 CLI 仅支持追加到末尾，暂不支持插入或重新排序[/]")
        console.print()
        
        try:
            fallbacks = get_fallbacks()
        except Exception as e:
            console.print(f"\n[bold red]❌ 获取备选链失败: {e}[/]")
            pause_enter()
            return
        
        console.print()
        if fallbacks:
            console.print("[bold]当前备选链:[/]")
            table = Table(box=box.SIMPLE)
            table.add_column("顺序", style="cyan", width=6)
            table.add_column("模型", style="bold")
            
            for i, model in enumerate(fallbacks, 1):
                table.add_row(f"#{i}", model)
            
            console.print(table)
        else:
            console.print("[bold]当前备选链:[/] [yellow](未设置)[/]")
        
        console.print()
        console.print("[bold]操作:[/]")
        console.print("  [cyan]1[/] 添加备选模型")
        console.print("  [cyan]2[/] 移除备选模型")
        console.print("  [cyan]3[/] 清空备选链")
        console.print("  [cyan]0[/] 返回")
        console.print()
        
        choice = Prompt.ask("[bold green]>[/]", choices=["0", "1", "2", "3"], default="0")
        
        if choice == "0":
            break
        elif choice == "1":
            add_fallback_menu()
        elif choice == "2":
            remove_fallback_menu()
        elif choice == "3":
            clear_fallbacks_menu()


def add_fallback_menu():
    """添加备选模型菜单"""
    while True:
        console.clear()
        console.print(Panel(
            Text("➕ 添加备选模型", style="bold cyan", justify="center"),
            box=box.DOUBLE
        ))
        
        try:
            # 获取所有可用模型
            config.reload()
            all_models = config.get_all_models_flat()
            current_fallbacks = set(get_fallbacks())
            
            # 过滤掉已在备选链中的模型
            available_models = [m for m in all_models if m['full_name'] not in current_fallbacks]
        except Exception as e:
            console.print(f"\n[bold red]❌ 获取模型列表失败: {e}[/]")
            pause_enter()
            return
        
        if not available_models:
            console.print("\n[yellow]⚠️ 没有更多可用模型可添加[/]")
            pause_enter()
            return
        
        console.print()
        console.print("[bold]可选模型（按服务商分组）:[/]")
        console.print()
        
        # 按服务商分组
        from collections import defaultdict
        models_by_provider = defaultdict(list)
        for i, m in enumerate(available_models, 1):
            if "/" in m['full_name']:
                provider = m['full_name'].split("/", 1)[0]
            else:
                provider = "其他"
            models_by_provider[provider].append((i, m))
        
        # 显示
        for provider in sorted(models_by_provider.keys()):
            console.print(f"  [bold][cyan]{provider}[/][/]:")
            for idx, m in models_by_provider[provider]:
                console.print(f"    [{idx}] {m['display']}")
        
        console.print()
        console.print("[cyan]0[/] 返回")
        console.print()
        
        choices = ["0"] + [str(i) for i in range(1, len(available_models) + 1)]
        choice = Prompt.ask("[bold green]>[/]", choices=choices, default="0")
        
        if choice == "0":
            break
        elif choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(available_models):
                model = available_models[idx]['full_name']
                add_fallback(model)
                break


def add_fallback(model: str):
    """添加备选模型（使用 CLI，错误提示友好化）"""
    console.print(f"\n[yellow]⏳ 正在添加备选模型: {model}...[/]")
    try:
        # 先手动备份配置
        config.reload()
        backup_path = config.backup()
        if backup_path:
            console.print(f"  [dim]💡 已备份配置到: {backup_path}[/]")
        
        stdout, stderr, code = run_cli(["models", "fallbacks", "add", model])
        
        if code == 0:
            _invalidate_model_status_cache()
            console.print(f"\n[green]✅ 已添加备选模型: {model}[/]")
            console.print("\n[dim]💡 此更改热生效，无需重启服务[/]")
        else:
            console.print(f"\n[bold red]❌ 添加失败[/]")
            if stderr:
                console.print(f"  [dim]详情: {stderr}[/]")
    except Exception as e:
        console.print(f"\n[bold red]❌ 添加失败: {e}[/]")
    
        pause_enter()


def remove_fallback_menu():
    """移除备选模型菜单"""
    try:
        fallbacks = get_fallbacks()
    except Exception as e:
        console.print(f"\n[bold red]❌ 获取备选链失败: {e}[/]")
        pause_enter()
        return
    
    if not fallbacks:
        console.print("\n[yellow]⚠️ 备选链为空[/]")
        pause_enter()
        return
    
    while True:
        console.clear()
        console.print(Panel(
            Text("➖ 移除备选模型", style="bold cyan", justify="center"),
            box=box.DOUBLE
        ))
        
        console.print()
        console.print("[bold]当前备选链:[/]")
        
        table = Table(box=box.SIMPLE)
        table.add_column("编号", style="cyan", width=4)
        table.add_column("模型", style="bold")
        
        for i, model in enumerate(fallbacks, 1):
            table.add_row(str(i), model)
        
        console.print(table)
        
        console.print()
        console.print("[cyan]0[/] 返回")
        console.print()
        
        choices = ["0"] + [str(i) for i in range(1, len(fallbacks) + 1)]
        choice = Prompt.ask("[bold green]>[/]", choices=choices, default="0")
        
        if choice == "0":
            break
        elif choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(fallbacks):
                model = fallbacks[idx]
                remove_fallback(model)
                break


def remove_fallback(model: str):
    """移除备选模型（使用 CLI，错误提示友好化）"""
    console.print(f"\n[yellow]⏳ 正在移除备选模型: {model}...[/]")
    try:
        # 先手动备份配置
        config.reload()
        backup_path = config.backup()
        if backup_path:
            console.print(f"  [dim]💡 已备份配置到: {backup_path}[/]")
        
        stdout, stderr, code = run_cli(["models", "fallbacks", "remove", model])
        
        if code == 0:
            _invalidate_model_status_cache()
            console.print(f"\n[green]✅ 已移除备选模型: {model}[/]")
            console.print("\n[dim]💡 此更改热生效，无需重启服务[/]")
        else:
            console.print(f"\n[bold red]❌ 移除失败[/]")
            if stderr:
                console.print(f"  [dim]详情: {stderr}[/]")
    except Exception as e:
        console.print(f"\n[bold red]❌ 移除失败: {e}[/]")
    
        pause_enter()


def clear_fallbacks_menu():
    """清空备选链菜单（错误提示友好化）"""
    if not Confirm.ask("[bold red]确定要清空所有备选模型?[/]", default=False):
        return
    
    console.print("\n[yellow]⏳ 正在清空备选链...[/]")
    try:
        # 先手动备份配置
        config.reload()
        backup_path = config.backup()
        if backup_path:
            console.print(f"  [dim]💡 已备份配置到: {backup_path}[/]")
        
        stdout, stderr, code = run_cli(["models", "fallbacks", "clear"])
        
        if code == 0:
            _invalidate_model_status_cache()
            console.print("\n[green]✅ 已清空备选链[/]")
            console.print("\n[dim]💡 此更改热生效，无需重启服务[/]")
        else:
            console.print(f"\n[bold red]❌ 清空失败[/]")
            if stderr:
                console.print(f"  [dim]详情: {stderr}[/]")
    except Exception as e:
        console.print(f"\n[bold red]❌ 清空失败: {e}[/]")
    
        pause_enter()


def subagent_settings_menu():
    """Agent 派发管理菜单（按固定 Agent 配置，支持继承全局）"""
    selected_agent_id = ""
    while True:
        console.clear()
        console.print(Panel(
            Text("👥 Agent 派发管理", style="bold cyan", justify="center"),
            box=box.DOUBLE
        ))
        
        # 小贴士
        console.print()
        console.print("  [dim]💡 可选择任意固定 Agent，配置其派发开关与并发策略[/]")
        console.print("  [dim]💡 被选中的固定 Agent 可继续向下派发（多层链路）[/]")
        console.print("  [dim]💡 白名单按 Agent ID 生效：更适合固定 Agent；临时 spawn 需可匹配 ID 才能精确限制[/]")
        console.print()
        
        try:
            config.reload()
            agents = _dispatch_manageable_agents()
            if not agents:
                console.print("\n[yellow]⚠️ 暂无固定 Agent，请先在「主 Agent 管理」中创建[/]")
                pause_enter()
                return
            ids = [str(a.get("id", "")) for a in agents if str(a.get("id", ""))]
            if not selected_agent_id or selected_agent_id not in ids:
                selected_agent_id = "main" if "main" in ids else ids[0]
            status = config.get_subagent_status_for(selected_agent_id)
        except Exception as e:
            console.print(f"\n[bold red]❌ 获取子 Agent 状态失败: {e}[/]")
            pause_enter()
            return
        
        enabled_str = "[green]✅ 已启用[/]" if status["enabled"] else "[red]❌ 已禁用[/]"
        allow_str = ", ".join(status["allowAgents"]) if status["allowAgents"] else "[dim]无 (禁用状态)[/]"
        
        console.print()
        console.print(f"  [bold]🧠 当前配置目标 Agent:[/] [cyan]{status.get('agentId', selected_agent_id)}[/]")
        console.print(f"  [bold]🚦 是否允许派发 Agent（固定 + 临时）:[/] {enabled_str}")
        source = "Agent覆盖" if status.get("maxConcurrentFrom") == "agent" else "继承全局"
        console.print(f"  [bold]⚡ 最大派发并发数:[/] {status['maxConcurrent']} [dim]({source})[/]")
        console.print(f"  [bold]📋 固定 Agent 白名单:[/] {allow_str}")
        
        console.print()
        console.print("[bold]操作:[/]")
        console.print("  [cyan]1[/] 切换目标 Agent")
        console.print("  [cyan]2[/] 切换派发开关")
        console.print("  [cyan]3[/] 设置最大派发并发数")
        console.print("  [cyan]4[/] 恢复全局默认并发设置")
        console.print("  [cyan]5[/] 设置固定 Agent 白名单")
        console.print("  [cyan]0[/] 返回")
        console.print()
        
        choice = Prompt.ask("[bold green]>[/]", choices=["0", "1", "2", "3", "4", "5"], default="0")
        
        if choice == "0":
            break
        elif choice == "1":
            resolved = _select_agent_id(ids, title="请选择目标 Agent", default_id=selected_agent_id)
            if not resolved:
                console.print("\n[yellow]⚠️ 已取消选择[/]")
                pause_enter()
            else:
                selected_agent_id = resolved
        elif choice == "2":
            try:
                if status["enabled"]:
                    ok = config.update_subagent_for(selected_agent_id, allow_agents=[])
                    if ok:
                        console.print("\n[green]✅ 已关闭 Agent 派发[/]")
                    else:
                        console.print("\n[bold red]❌ 禁用失败：配置写入失败[/]")
                else:
                    ok = config.update_subagent_for(selected_agent_id, allow_agents=["*"])
                    if ok:
                        console.print("\n[green]✅ 已开启 Agent 派发（允许所有）[/]")
                    else:
                        console.print("\n[bold red]❌ 启用失败：配置写入失败[/]")
                if ok:
                    console.print("\n[yellow]⚠️ 需要重启服务后生效[/]")
            except Exception as e:
                console.print(f"\n[bold red]❌ 操作失败: {e}[/]")
                pause_enter()
        elif choice == "3":
            num = Prompt.ask("[bold]请输入新的最大派发并发数 [1-10][/]", default=str(status["maxConcurrent"]))
            if num.isdigit() and 1 <= int(num) <= 10:
                try:
                    ok = config.update_subagent_for(selected_agent_id, max_concurrent=int(num))
                    if ok:
                        console.print(f"\n[green]✅ 已设置为 {num}[/]")
                        console.print("\n[yellow]⚠️ 需要重启服务后生效[/]")
                    else:
                        console.print("\n[bold red]❌ 设置失败：配置写入失败[/]")
                except Exception as e:
                    console.print(f"\n[bold red]❌ 设置失败: {e}[/]")
            else:
                console.print("\n[bold red]❌ 无效输入[/]")
                pause_enter()
        elif choice == "4":
            try:
                ok = config.update_subagent_for(selected_agent_id, inherit_max_concurrent=True)
                if ok:
                    console.print("\n[green]✅ 最大派发并发数已恢复继承全局[/]")
                    console.print("\n[yellow]⚠️ 需要重启服务后生效[/]")
                else:
                    console.print("\n[bold red]❌ 操作失败：配置写入失败[/]")
            except Exception as e:
                console.print(f"\n[bold red]❌ 设置失败: {e}[/]")
                pause_enter()
        elif choice == "5":
            console.print("\n[dim]- 输入 '*' 允许所有固定 Agent[/]")
            console.print("[dim]- 输入具体固定 Agent ID，用逗号分隔 (如: main1,main2)[/]")
            console.print("[dim]- 输入空白清空白名单（将关闭派发）[/]")
            raw = Prompt.ask("\n[bold]请输入固定 Agent 白名单[/]", default="")
            raw = raw.strip()
            if raw == "": 
                allow_list = []
            elif raw == "*": 
                allow_list = ["*"]
            else: 
                allow_list = [x.strip() for x in raw.split(",") if x.strip()]
            try:
                ok = config.update_subagent_for(selected_agent_id, allow_agents=allow_list)
                if ok:
                    console.print(f"\n[green]✅ 白名单已更新为: {allow_list}[/]")
                    console.print("\n[yellow]⚠️ 需要重启服务后生效[/]")
                else:
                    console.print("\n[bold red]❌ 白名单更新失败：配置写入失败[/]")
            except Exception as e:
                console.print(f"\n[bold red]❌ 设置失败: {e}[/]")
                pause_enter()


if __name__ == "__main__":
    menu_routing()
