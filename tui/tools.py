"""
工具配置模块 - 搜索服务（官方+第三方）、向量化配置
增强版：按 OpenClaw 官方 schema 展示支持的搜索 provider，并提供可视化写入。
"""
from core.utils import safe_input, pause_enter
import os
import getpass
import re
from typing import Dict, List
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich.prompt import Prompt, Confirm
from rich import box

from core import (
    config,
    run_cli,
    run_cli_json,
    get_memory_search_config,
    clear_memory_search_config,
    OFFICIAL_MEMORY_PROVIDERS,
    get_memory_provider_credential_target,
    has_memory_provider_api_key,
    set_memory_provider_api_key,
    set_env_key,
    check_existing_key,
    read_env_keys,
    DEFAULT_ENV_PATH
)
from core.search_adapters import (
    ADAPTER_SPECS,
    OFFICIAL_SEARCH_SOURCES,
    DEFAULT_SEARCH_ADAPTERS_PATH,
    load_search_adapters,
    set_primary_provider,
    set_primary_source,
    set_fallback_sources,
    update_provider as update_search_adapter_provider,
    test_provider_connection as test_search_adapter_connection,
    search_with_unified_failover,
)

console = Console()


def _run_menu_action(action, label: str):
    try:
        action()
    except KeyboardInterrupt:
        console.print(f"\n[yellow]已取消: {label}[/]")
        pause_enter()
    except EOFError:
        console.print(f"\n[yellow]输入流结束，已返回当前菜单: {label}[/]")
        pause_enter()
    except Exception as e:
        console.print(f"\n[bold red]❌ {label} 执行失败: {e}[/]")
        pause_enter()


def _resolve_adapter_provider_input(raw: str) -> str:
    v = (raw or "").strip().lower()
    alias = {
        "1": "zhipu",
        "2": "serper",
        "3": "tavily",
        "zhipu": "zhipu",
        "serper": "serper",
        "tavily": "tavily",
    }
    return alias.get(v, "")



# 默认官方搜索服务列表（回退值）
DEFAULT_OFFICIAL_SEARCH_PROVIDERS = ["brave", "perplexity", "grok", "gemini", "kimi"]

OFFICIAL_SEARCH_SPECS = {
    "brave": {
        "label": "Brave Search",
        "api_key_path": "tools.web.search.apiKey",
        "env_keys": ["BRAVE_API_KEY"],
    },
    "perplexity": {
        "label": "Perplexity",
        "api_key_path": "tools.web.search.perplexity.apiKey",
        "env_keys": ["PERPLEXITY_API_KEY", "OPENROUTER_API_KEY"],
    },
    "grok": {
        "label": "xAI Grok Search",
        "api_key_path": "tools.web.search.grok.apiKey",
        "env_keys": ["XAI_API_KEY"],
    },
    "gemini": {
        "label": "Google Gemini Search",
        "api_key_path": "tools.web.search.gemini.apiKey",
        "env_keys": ["GEMINI_API_KEY"],
    },
    "kimi": {
        "label": "Moonshot Kimi Search",
        "api_key_path": "tools.web.search.kimi.apiKey",
        "env_keys": ["KIMI_API_KEY", "MOONSHOT_API_KEY"],
    },
}


def _parse_supported_search_providers_from_schema(text: str) -> List[str]:
    """
    从 schema/help 文本中解析 provider 列表。
    典型文本：
      Search provider ("brave" or "perplexity").
    """
    if not text:
        return []
    low = text.lower()
    if "search provider" not in low:
        return []
    # 提取双引号中的值（如 "brave"）
    cands = re.findall(r'"([a-z0-9_-]+)"', low)
    providers = [c for c in cands if c in OFFICIAL_SEARCH_SPECS]
    # 去重并保持顺序
    seen = set()
    out = []
    for p in providers:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


def get_official_search_providers() -> List[str]:
    """获取 OpenClaw 官方支持的 web_search provider（优先运行时 schema）。"""
    base = list(DEFAULT_OFFICIAL_SEARCH_PROVIDERS)

    # 1) 从运行时 schema.help.ts 解析（与你容器中的 OpenClaw 版本一致）
    schema_paths = [
        "/app/src/config/schema.help.ts",
        "/app/packages/clawdbot/node_modules/openclaw/dist/redact-snapshot-DhuwcBRX.js",
        "/app/packages/clawdbot/node_modules/openclaw/dist/redact-snapshot-WZaTTE0O.js",
    ]
    for path in schema_paths:
        try:
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8", errors="ignore") as f:
                    text = f.read()
                parsed = _parse_supported_search_providers_from_schema(text)
                if parsed:
                    # 并集策略：保留最新基线能力，同时吸收运行时实际发现值
                    out = []
                    seen = set()
                    for p in base + parsed:
                        if p in OFFICIAL_SEARCH_SPECS and p not in seen:
                            seen.add(p)
                            out.append(p)
                    return out
        except Exception:
            pass

    # 2) 回退：默认官方列表
    return base


def _ensure_search_config_root():
    if "tools" not in config.data:
        config.data["tools"] = {}
    if "web" not in config.data["tools"]:
        config.data["tools"]["web"] = {}
    if "search" not in config.data["tools"]["web"]:
        config.data["tools"]["web"]["search"] = {}


def _set_nested(d: Dict, dotted_path: str, value):
    keys = [k for k in (dotted_path or "").split(".") if k]
    if not keys:
        return
    cur = d
    for key in keys[:-1]:
        if key not in cur or not isinstance(cur.get(key), dict):
            cur[key] = {}
        cur = cur[key]
    cur[keys[-1]] = value


def _get_nested(d: Dict, dotted_path: str, default=None):
    keys = [k for k in (dotted_path or "").split(".") if k]
    cur = d
    for key in keys:
        if not isinstance(cur, dict) or key not in cur:
            return default
        cur = cur[key]
    return cur


def set_search_provider(provider: str) -> bool:
    provider = (provider or "").strip().lower()
    if provider not in OFFICIAL_SEARCH_SPECS:
        return False
    config.reload()
    backup_path = config.backup()
    if backup_path:
        console.print(f"\n  [dim]💡 已备份配置到: {backup_path}[/]")
    _ensure_search_config_root()
    config.data["tools"]["web"]["search"]["provider"] = provider
    return config.save()


def set_official_search_api_key(provider: str, api_key: str) -> bool:
    provider = (provider or "").strip().lower()
    spec = OFFICIAL_SEARCH_SPECS.get(provider)
    if not spec:
        return False
    path = spec["api_key_path"]
    if not api_key:
        return False
    config.reload()
    backup_path = config.backup()
    if backup_path:
        console.print(f"\n  [dim]💡 已备份配置到: {backup_path}[/]")
    _, _, code = run_cli(["config", "set", path, api_key, "--json"])
    if code == 0:
        config.reload()
        return True
    # fallback：本地写入
    _ensure_search_config_root()
    rel_path = path.replace("tools.web.search.", "")
    search_cfg = config.data["tools"]["web"]["search"]
    _set_nested(search_cfg, rel_path, api_key)
    return config.save()


def _provider_has_configured_key(provider: str, env_keys: Dict[str, str]) -> bool:
    provider = (provider or "").strip().lower()
    spec = OFFICIAL_SEARCH_SPECS.get(provider, {})
    key_path = spec.get("api_key_path", "")
    if key_path:
        config_key = _get_nested(config.data, key_path, "")
        if isinstance(config_key, str) and config_key.strip():
            return True
    for env_key in spec.get("env_keys", []):
        if env_keys.get(env_key, "").strip():
            return True
    return False


def list_configured_official_search_providers(providers: List[str]) -> List[str]:
    """返回已配置 API Key（config 或 .env）的官方搜索 provider。"""
    config.reload()
    env_keys = read_env_keys()
    out = []
    for p in providers:
        if _provider_has_configured_key(p, env_keys):
            out.append(p)
    return out


def menu_tools():
    """工具配置主菜单（增强版）"""
    while True:
        console.clear()
        console.print()
        console.print("[bold cyan]========== 🧭 工具配置 ==========[/]")
        console.print()
        
        console.print("[bold]功能:[/]")
        console.print("  [cyan]1[/] 搜索服务管理 (官方+第三方)")
        console.print("  [cyan]2[/] 向量化/记忆检索配置 (Embeddings)")
        console.print("  [cyan]0[/] 返回")
        console.print()
        
        choice = Prompt.ask("[bold green]>[/]", choices=["0", "1", "2"], default="0").strip().lower()
        while choice not in ["0", "1", "2"]:
            choice = Prompt.ask("[bold green]>[/]", choices=["0", "1", "2"], default="0").strip().lower()
        
        if choice == "0":
            break
        elif choice == "1":
            _run_menu_action(menu_search_services, "搜索服务管理")
        elif choice == "2":
            _run_menu_action(menu_embeddings, "向量化/记忆检索配置")


def menu_search_services():
    """搜索服务管理主菜单（统一入口）"""
    while True:
        console.clear()
        console.print(Panel(
            Text("🔍 搜索服务管理", style="bold cyan", justify="center"),
            box=box.DOUBLE
        ))
        
        config.reload()
        search_cfg = config.data.get("tools", {}).get("web", {}).get("search", {})
        default_provider = str(search_cfg.get("provider", "") or "")
        official_configured = list_configured_official_search_providers(get_official_search_providers())
        adapter_cfg = load_search_adapters()
        primary_source = str(adapter_cfg.get("primarySource", "") or "")
        fallback_sources = adapter_cfg.get("fallbackSources", []) if isinstance(adapter_cfg.get("fallbackSources"), list) else []
        
        console.print()
        console.print(f"[bold]当前默认搜索服务:[/] {default_provider or '(未设置)'}")
        console.print(f"[bold]已配置官方服务:[/] {', '.join(official_configured) if official_configured else '(无)'}")
        console.print(f"[bold]主搜索服务商:[/] {primary_source or '(未设置)'}")
        console.print(f"[bold]候选搜索服务商:[/] {' -> '.join(fallback_sources) if fallback_sources else '(未设置)'}")
        
        console.print()
        console.print("[bold]操作:[/]")
        console.print("  [cyan]1[/] 添加与维护搜索服务")
        console.print("  [cyan]2[/] 激活默认搜索服务")
        console.print("  [cyan]3[/] 搜索服务主备切换设置")
        console.print("  [cyan]0[/] 返回")
        console.print()
        
        choice = Prompt.ask("[bold green]>[/]", choices=["0", "1", "2", "3"], default="0").strip().lower()
        while choice not in ["0", "1", "2", "3"]:
            choice = Prompt.ask("[bold green]>[/]", choices=["0", "1", "2", "3"], default="0").strip().lower()
        
        if choice == "0":
            break
        elif choice == "1":
            _run_menu_action(menu_search_service_maintenance, "添加与维护搜索服务")
        elif choice == "2":
            _run_menu_action(activate_configured_search_provider, "激活默认搜索服务")
        elif choice == "3":
            _run_menu_action(menu_search_failover_settings, "搜索服务主备切换设置")


def menu_search_service_maintenance():
    """添加与维护搜索服务"""
    while True:
        console.clear()
        console.print(Panel(
            Text("🧩 添加与维护搜索服务", style="bold cyan", justify="center"),
            box=box.DOUBLE
        ))
        console.print()
        console.print("[bold]操作:[/]")
        console.print("  [cyan]1[/] 官方支持服务搜索配置（增/清空）")
        console.print("  [cyan]2[/] 扩展搜索服务配置（增/清空）")
        console.print("  [cyan]0[/] 返回")
        console.print()
        choice = Prompt.ask("[bold green]>[/]", choices=["0", "1", "2"], default="0").strip().lower()
        if choice == "0":
            return
        if choice == "1":
            _run_menu_action(menu_official_search, "官方搜索配置")
        elif choice == "2":
            _run_menu_action(menu_thirdparty_search, "扩展搜索配置")


def _resolve_unified_source_input(raw: str) -> str:
    v = (raw or "").strip().lower()
    source_index = {
        "1": "official:brave",
        "2": "official:perplexity",
        "3": "official:grok",
        "4": "official:gemini",
        "5": "official:kimi",
        "6": "adapter:zhipu",
        "7": "adapter:serper",
        "8": "adapter:tavily",
    }
    if v in source_index:
        return source_index[v]
    if v in OFFICIAL_SEARCH_SOURCES:
        return v
    if v in ["adapter:zhipu", "adapter:serper", "adapter:tavily"]:
        return v
    return ""


def menu_search_failover_settings():
    """搜索服务主备切换设置"""
    while True:
        console.clear()
        console.print(Panel(
            Text("🔁 搜索服务主备切换设置", style="bold cyan", justify="center"),
            box=box.DOUBLE
        ))
        cfg = load_search_adapters()
        primary = str(cfg.get("primarySource", "") or "")
        fallbacks = cfg.get("fallbackSources", []) if isinstance(cfg.get("fallbackSources"), list) else []
        console.print()
        console.print(f"[bold]主搜索服务商:[/] {primary or '(未设置)'}")
        console.print(f"[bold]候选搜索服务商:[/] {' -> '.join(fallbacks) if fallbacks else '(未设置)'}")
        console.print()
        console.print("[dim]可选源:[/]")
        console.print("  1 official:brave")
        console.print("  2 official:perplexity")
        console.print("  3 official:grok")
        console.print("  4 official:gemini")
        console.print("  5 official:kimi")
        console.print("  6 adapter:zhipu")
        console.print("  7 adapter:serper")
        console.print("  8 adapter:tavily")
        console.print()
        console.print("[bold]操作:[/]")
        console.print("  [cyan]1[/] 设置主搜索服务商")
        console.print("  [cyan]2[/] 设置候选搜索服务商（逗号分隔）")
        console.print("  [cyan]3[/] 演练主备切换")
        console.print("  [cyan]0[/] 返回")
        console.print()
        choice = Prompt.ask("[bold green]>[/]", choices=["0", "1", "2", "3"], default="0").strip().lower()
        if choice == "0":
            return
        if choice == "1":
            raw = Prompt.ask("[bold]请输入主搜索服务商编号或source_id（留空清除）[/]", default="").strip()
            target = _resolve_unified_source_input(raw) if raw else ""
            ok = set_primary_source(target)
            console.print(f"\n[green]✅ 已设置主搜索服务商: {target or '(未设置)'}[/]" if ok else "\n[bold red]❌ 设置失败[/]")
            pause_enter()
        elif choice == "2":
            raw = Prompt.ask("[bold]请输入候选服务商（逗号分隔，编号或source_id；留空清除）[/]", default="").strip()
            items = []
            for part in raw.split(","):
                sid = _resolve_unified_source_input(part)
                if sid and sid not in items:
                    items.append(sid)
            ok = set_fallback_sources(items)
            console.print(f"\n[green]✅ 已设置候选搜索服务商: {' -> '.join(items) if items else '(未设置)'}[/]" if ok else "\n[bold red]❌ 设置失败[/]")
            pause_enter()
        elif choice == "3":
            q = Prompt.ask("[bold]请输入演练查询词[/]", default="OpenClaw").strip() or "OpenClaw"
            try:
                results = search_with_unified_failover(q, count=3)
                cfg = load_search_adapters()
                src = str(cfg.get("activeSource", "") or "")
                console.print(f"\n[green]✅ 演练成功，当前命中: {src}，结果数: {len(results)}[/]")
            except Exception as e:
                console.print(f"\n[bold red]❌ 演练失败: {e}[/]")
            pause_enter()


def menu_official_search():
    """官方搜索服务配置"""
    while True:
        console.clear()
        console.print(Panel(
            Text("🔍 官方搜索服务配置", style="bold cyan", justify="center"),
            box=box.DOUBLE
        ))
        
        providers = get_official_search_providers()
        configured = set(list_configured_official_search_providers(providers))
        config.reload()
        default_provider = str(config.data.get("tools", {}).get("web", {}).get("search", {}).get("provider", "") or "")
        
        console.print()
        console.print(f"[bold]当前默认搜索服务:[/] {default_provider or '(未设置)'}")
        console.print("[bold]OpenClaw 官方支持搜索服务:[/]")
        for i, provider in enumerate(providers, 1):
            label = OFFICIAL_SEARCH_SPECS.get(provider, {}).get("label", provider)
            mark = "✅" if provider in configured else "⬜"
            default_mark = "⭐" if provider == default_provider else "  "
            console.print(f"  [cyan]{i}[/] {default_mark} {mark} {provider} [dim]({label})[/]")
        
        console.print("  [cyan]0[/] 返回")
        console.print()
        
        choices = ["0"] + [str(i) for i in range(1, len(providers) + 1)]
        choice = Prompt.ask("[bold green]>[/]", choices=choices, default="0").strip().lower()
        while choice not in choices:
            choice = Prompt.ask("[bold green]>[/]", choices=choices, default="0").strip().lower()
        
        if choice == "0":
            break
        elif choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(providers):
                provider = providers[idx]
                _run_menu_action(lambda p=provider: configure_official_search(p), f"配置官方搜索服务 {provider}")


def configure_official_search(provider: str):
    """配置单个官方搜索服务"""
    while True:
        console.clear()
        console.print(Panel(
            Text(f"🔍 配置官方搜索服务: {provider}", style="bold cyan", justify="center"),
            box=box.DOUBLE
        ))
        
        provider = (provider or "").strip().lower()
        spec = OFFICIAL_SEARCH_SPECS.get(provider, {})
        # 获取当前配置
        config.reload()
        search_cfg = config.data.get("tools", {}).get("web", {}).get("search", {})
        
        console.print()
        console.print("[bold]操作:[/]")
        console.print("  [cyan]1[/] 设为默认搜索服务")
        console.print("  [cyan]2[/] 写入 API Key 到配置")
        env_keys = spec.get("env_keys", [])
        if env_keys:
            console.print(f"  [cyan]3[/] 使用环境变量方式配置 Key ({', '.join(env_keys)})")
        
        if provider in ["perplexity", "kimi"]:
            console.print("  [cyan]4[/] 设置 Base URL")
        console.print("  [cyan]6[/] 清空此服务配置")
        
        console.print("  [cyan]0[/] 返回")
        console.print()
        
        choices = ["0", "1", "2", "3", "6"]
        if provider in ["perplexity", "kimi"]:
            choices += ["4"]
        
        choice = Prompt.ask("[bold green]>[/]", choices=choices, default="0").strip().lower()
        while choice not in choices:
            choice = Prompt.ask("[bold green]>[/]", choices=choices, default="0").strip().lower()
        
        if choice == "0":
            break
        elif choice == "1":
            ok = set_search_provider(provider)
            if ok:
                console.print(f"\n[green]✅ 默认搜索服务已设置为: {provider}[/]")
                console.print("\n[yellow]⚠️ 建议重启服务后生效[/]")
            else:
                console.print("\n[bold red]❌ 设置失败[/]")
            pause_enter()
        elif choice == "2":
            key = getpass.getpass(f"请输入 {provider} API Key (输入不会显示): ").strip()
            if not key:
                console.print("\n[bold red]❌ 未输入 Key[/]")
                pause_enter()
                continue
            ok = set_official_search_api_key(provider, key)
            if ok:
                console.print(f"\n[green]✅ 已写入 API Key 到配置: {spec.get('api_key_path','')}[/]")
                console.print("\n[yellow]⚠️ 建议重启服务后生效[/]")
            else:
                console.print("\n[bold red]❌ 写入失败[/]")
            pause_enter()
        elif choice == "3":
            # 环境变量写法（官方推荐的 fallback 方式）
            first_key = env_keys[0] if env_keys else f"{provider.upper()}_API_KEY"
            choose_or_prompt_key(first_key, provider)
            pause_enter()
        elif choice == "4" and provider in ["perplexity", "kimi"]:
            set_provider_baseurl(provider)
        elif choice == "6":
            clear_official_search_provider_config(provider)


def clear_official_search_provider_config(provider: str):
    provider = (provider or "").strip().lower()
    unset_paths = []
    if provider == "brave":
        unset_paths = ["tools.web.search.apiKey"]
    elif provider == "perplexity":
        unset_paths = [
            "tools.web.search.perplexity.apiKey",
            "tools.web.search.perplexity.baseUrl",
            "tools.web.search.perplexity.model",
        ]
    elif provider == "grok":
        unset_paths = [
            "tools.web.search.grok.apiKey",
            "tools.web.search.grok.model",
        ]
    elif provider == "gemini":
        unset_paths = [
            "tools.web.search.gemini.apiKey",
            "tools.web.search.gemini.model",
        ]
    elif provider == "kimi":
        unset_paths = [
            "tools.web.search.kimi.apiKey",
            "tools.web.search.kimi.baseUrl",
            "tools.web.search.kimi.model",
        ]
    else:
        console.print("\n[bold red]❌ 不支持的服务商[/]")
        pause_enter()
        return

    if not Confirm.ask(f"[bold red]确认清空 {provider} 的搜索配置？[/]", default=False):
        return

    config.reload()
    backup_path = config.backup()
    if backup_path:
        console.print(f"\n  [dim]💡 已备份配置到: {backup_path}[/]")
    ok = True
    for path in unset_paths:
        _, _, code = run_cli(["config", "unset", path])
        if code != 0:
            ok = False
    if ok:
        console.print(f"\n[green]✅ 已清空 {provider} 搜索配置[/]")
    else:
        console.print(f"\n[yellow]⚠️ 部分配置清空失败，请检查权限或配置路径[/]")
    pause_enter()


def set_provider_baseurl(provider: str):
    """设置 provider Base URL（当前支持 perplexity/kimi）"""
    console.clear()
    console.print(Panel(
        Text(f"🌐 设置 {provider} Base URL", style="bold cyan", justify="center"),
        box=box.DOUBLE
    ))
    
    provider = (provider or "").strip().lower()
    path_by_provider = {
        "perplexity": "tools.web.search.perplexity.baseUrl",
        "kimi": "tools.web.search.kimi.baseUrl",
    }
    config_path = path_by_provider.get(provider)
    if not config_path:
        console.print("\n[bold red]❌ 当前 provider 不支持 Base URL 设置[/]")
        pause_enter()
        return

    config.reload()
    current = _get_nested(config.data, config_path, "")
    
    console.print()
    console.print(f"  [dim]当前值: {current or '(未设置)'}[/]")
    console.print()
    
    new_url = Prompt.ask("[bold]请输入 Base URL[/]", default=current).strip()
    
    # 备份
    config.reload()
    backup_path = config.backup()
    if backup_path:
        console.print(f"\n  [dim]💡 已备份配置到: {backup_path}[/]")
    
    # 优先官方命令写入，失败回退本地写入
    _, _, code = run_cli(["config", "set", config_path, new_url, "--json"])
    if code != 0:
        _ensure_search_config_root()
        rel_path = config_path.replace("tools.web.search.", "")
        _set_nested(config.data["tools"]["web"]["search"], rel_path, new_url)
        config.save()
    else:
        config.reload()

    console.print(f"\n[green]✅ 已更新 Base URL: {new_url}[/]")
    pause_enter()


def set_provider_model(provider: str):
    """设置 provider Model（支持 perplexity/grok/gemini/kimi）"""
    console.clear()
    console.print(Panel(
        Text(f"🤖 设置 {provider} Model", style="bold cyan", justify="center"),
        box=box.DOUBLE
    ))
    
    provider = (provider or "").strip().lower()
    path_by_provider = {
        "perplexity": "tools.web.search.perplexity.model",
        "grok": "tools.web.search.grok.model",
        "gemini": "tools.web.search.gemini.model",
        "kimi": "tools.web.search.kimi.model",
    }
    config_path = path_by_provider.get(provider)
    if not config_path:
        console.print("\n[bold red]❌ 当前 provider 不支持 Model 设置[/]")
        pause_enter()
        return

    config.reload()
    current = _get_nested(config.data, config_path, "")
    
    console.print()
    console.print(f"  [dim]当前值: {current or '(未设置)'}[/]")
    console.print()
    
    new_model = Prompt.ask("[bold]请输入 Model[/]", default=current).strip()
    
    # 备份
    config.reload()
    backup_path = config.backup()
    if backup_path:
        console.print(f"\n  [dim]💡 已备份配置到: {backup_path}[/]")
    
    # 优先官方命令写入，失败回退本地写入
    _, _, code = run_cli(["config", "set", config_path, new_model, "--json"])
    if code != 0:
        _ensure_search_config_root()
        rel_path = config_path.replace("tools.web.search.", "")
        _set_nested(config.data["tools"]["web"]["search"], rel_path, new_model)
        config.save()
    else:
        config.reload()
    
    console.print(f"\n[green]✅ 已更新 Model: {new_model}[/]")
    pause_enter()


def _render_adapter_status():
    cfg = load_search_adapters()
    active = cfg.get("active", "")
    primary = cfg.get("primary", "")
    fallbacks = cfg.get("fallbacks", []) if isinstance(cfg.get("fallbacks"), list) else []
    primary_source = cfg.get("primarySource", "") or (f"adapter:{primary}" if primary else "")
    fallback_sources = cfg.get("fallbackSources", []) if isinstance(cfg.get("fallbackSources"), list) else []
    providers = cfg.get("providers", {}) if isinstance(cfg.get("providers"), dict) else {}
    console.print()
    console.print(f"[bold]配置文件:[/] {DEFAULT_SEARCH_ADAPTERS_PATH}")
    console.print(f"[bold]当前激活扩展源:[/] {active or '(未激活)'}")
    console.print(f"[bold]主搜索源:[/] {primary or '(未设置)'}")
    console.print(f"[bold]备用链:[/] {' -> '.join(fallbacks) if fallbacks else '(未设置)'}")
    console.print(f"[bold]统一主源(官方+扩展):[/] {primary_source or '(未设置)'}")
    console.print(f"[bold]统一备用链(官方+扩展):[/] {' -> '.join(fallback_sources) if fallback_sources else '(未设置)'}")
    table = Table(box=box.SIMPLE)
    table.add_column("Provider", style="cyan")
    table.add_column("已启用", style="bold", width=6)
    table.add_column("Key", style="yellow", width=10)
    table.add_column("冷却(s)", style="magenta", width=8)
    table.add_column("Base URL", style="dim")
    for pid in ADAPTER_SPECS.keys():
        p = providers.get(pid, {}) if isinstance(providers.get(pid), dict) else {}
        key = str(p.get("apiKey", "") or "")
        masked = "已配置" if key else "未配置"
        table.add_row(
            pid,
            "是" if bool(p.get("enabled")) else "否",
            masked,
            str(p.get("cooldownSeconds", 60)),
            str(p.get("baseUrl", "") or ""),
        )
    console.print(table)


def _configure_adapter_provider(provider_id: str):
    provider_id = (provider_id or "").strip().lower()
    if provider_id not in ADAPTER_SPECS:
        console.print("\n[bold red]❌ 无效 provider[/]")
        pause_enter()
        return
    while True:
        console.clear()
        console.print(Panel(
            Text(f"🔍 扩展搜索源配置: {provider_id}", style="bold cyan", justify="center"),
            box=box.DOUBLE
        ))
        cfg = load_search_adapters()
        p = cfg.get("providers", {}).get(provider_id, {})
        spec = ADAPTER_SPECS.get(provider_id, {})
        env_keys = spec.get("envKeys", [])
        console.print()
        console.print(f"[bold]标签:[/] {spec.get('label', provider_id)}")
        console.print(f"[bold]启用:[/] {'是' if p.get('enabled') else '否'}")
        console.print(f"[bold]API Key:[/] {'已配置' if p.get('apiKey') else '未配置'}")
        console.print(f"[bold]Base URL:[/] {p.get('baseUrl', '')}")
        console.print(f"[bold]TopK:[/] {p.get('topK', 5)}")
        console.print(f"[bold]冷却秒数:[/] {p.get('cooldownSeconds', 60)}")
        if env_keys:
            console.print(f"[dim]环境变量候选: {', '.join(env_keys)}[/]")
        console.print()
        console.print("[bold]操作:[/]")
        console.print("  [cyan]1[/] 切换启用状态")
        console.print("  [cyan]2[/] 设置 API Key")
        console.print("  [cyan]3[/] 设置 Base URL")
        console.print("  [cyan]4[/] 设置 TopK")
        console.print("  [cyan]5[/] 设置冷却秒数 (限流后跳过)")
        console.print("  [cyan]6[/] 连接测试")
        console.print("  [cyan]7[/] 清空此扩展源配置")
        console.print("  [cyan]0[/] 返回")
        console.print()
        choice = Prompt.ask("[bold green]>[/]", choices=["0", "1", "2", "3", "4", "5", "6", "7"], default="0")
        if choice == "0":
            return
        if choice == "1":
            ok = update_search_adapter_provider(provider_id, {"enabled": not bool(p.get("enabled"))})
            console.print("\n[green]✅ 已更新[/]" if ok else "\n[bold red]❌ 更新失败[/]")
            pause_enter()
        elif choice == "2":
            key = getpass.getpass(f"请输入 {provider_id} API Key (输入不会显示): ").strip()
            if not key:
                console.print("\n[bold red]❌ 未输入 Key[/]")
                pause_enter()
                continue
            ok = update_search_adapter_provider(provider_id, {"apiKey": key})
            console.print("\n[green]✅ 已写入 API Key[/]" if ok else "\n[bold red]❌ 写入失败[/]")
            pause_enter()
        elif choice == "3":
            base = Prompt.ask("[bold]请输入 Base URL[/]", default=str(p.get("baseUrl", "") or "")).strip()
            ok = update_search_adapter_provider(provider_id, {"baseUrl": base})
            console.print("\n[green]✅ 已更新 Base URL[/]" if ok else "\n[bold red]❌ 更新失败[/]")
            pause_enter()
        elif choice == "4":
            top_k_raw = Prompt.ask("[bold]请输入 TopK (1-20)[/]", default=str(p.get("topK", 5))).strip()
            try:
                top_k = int(top_k_raw)
            except Exception:
                console.print("\n[bold red]❌ TopK 必须是整数[/]")
                pause_enter()
                continue
            ok = update_search_adapter_provider(provider_id, {"topK": top_k})
            console.print("\n[green]✅ 已更新 TopK[/]" if ok else "\n[bold red]❌ 更新失败[/]")
            pause_enter()
        elif choice == "5":
            raw = Prompt.ask("[bold]请输入冷却秒数(5-3600)[/]", default=str(p.get("cooldownSeconds", 60))).strip()
            try:
                cooldown = int(raw)
            except Exception:
                console.print("\n[bold red]❌ 必须是整数[/]")
                pause_enter()
                continue
            ok = update_search_adapter_provider(provider_id, {"cooldownSeconds": cooldown})
            console.print("\n[green]✅ 已更新冷却秒数[/]" if ok else "\n[bold red]❌ 更新失败[/]")
            pause_enter()
        elif choice == "6":
            ok, msg = test_search_adapter_connection(provider_id)
            if ok:
                console.print(f"\n[green]✅ 连通测试成功: {msg}[/]")
            else:
                console.print(f"\n[bold red]❌ 连通测试失败: {msg}[/]")
            pause_enter()
        elif choice == "7":
            if not Confirm.ask(f"[bold red]确认清空 {provider_id} 扩展源配置？[/]", default=False):
                continue
            reset = {
                "enabled": False,
                "apiKey": "",
                "baseUrl": ADAPTER_SPECS.get(provider_id, {}).get("defaultBaseUrl", ""),
                "model": "",
                "topK": 5,
                "cooldownSeconds": 60,
            }
            ok = update_search_adapter_provider(provider_id, reset)
            console.print("\n[green]✅ 已清空扩展源配置[/]" if ok else "\n[bold red]❌ 清空失败[/]")
            pause_enter()


def menu_thirdparty_search():
    """扩展搜索源配置（智谱/Serper/Tavily）"""
    while True:
        console.clear()
        console.print(Panel(
            Text("🔍 扩展搜索源 (智谱/Serper/Tavily)", style="bold cyan", justify="center"),
            box=box.DOUBLE
        ))

        _render_adapter_status()
        console.print()
        console.print("[bold]操作:[/]")
        console.print("  [cyan]1[/] 配置 zhipu")
        console.print("  [cyan]2[/] 配置 serper")
        console.print("  [cyan]3[/] 配置 tavily")
        console.print("  [cyan]4[/] 设置激活扩展源")
        console.print("  [cyan]5[/] 测试激活扩展源连接")
        console.print("  [cyan]0[/] 返回")
        console.print()
        choice = Prompt.ask("[bold green]>[/]", choices=["0", "1", "2", "3", "4", "5"], default="0")
        if choice == "0":
            break
        elif choice == "1":
            _run_menu_action(lambda: _configure_adapter_provider("zhipu"), "配置 zhipu")
        elif choice == "2":
            _run_menu_action(lambda: _configure_adapter_provider("serper"), "配置 serper")
        elif choice == "3":
            _run_menu_action(lambda: _configure_adapter_provider("tavily"), "配置 tavily")
        elif choice == "4":
            console.print()
            console.print("[dim]可输入: 1=zhipu, 2=serper, 3=tavily，或直接输入名称；留空清除[/]")
            raw = Prompt.ask("[bold]请输入主搜索源[/]", default="").strip()
            target = _resolve_adapter_provider_input(raw) if raw else ""
            ok = set_primary_provider(target)
            if ok:
                console.print(f"\n[green]✅ 已设置主搜索源: {target or '(未设置)'}[/]")
            else:
                console.print("\n[bold red]❌ 设置失败：请输入 zhipu/serper/tavily 或 1/2/3[/]")
            pause_enter()
        elif choice == "5":
            cfg = load_search_adapters()
            active = str(cfg.get("active", "") or "")
            if not active:
                console.print("\n[yellow]⚠️ 当前没有激活扩展源[/]")
                pause_enter()
                continue
            ok, msg = test_search_adapter_connection(active)
            if ok:
                console.print(f"\n[green]✅ {active} 连通测试成功: {msg}[/]")
            else:
                console.print(f"\n[bold red]❌ {active} 连通测试失败: {msg}[/]")
            pause_enter()


def select_default_search_provider_enhanced():
    """选择默认搜索 provider（增强版）"""
    while True:
        console.clear()
        console.print(Panel(
            Text("选择默认搜索服务", style="bold cyan", justify="center"),
            box=box.DOUBLE
        ))
        
        providers = get_official_search_providers()
        
        console.print()
        console.print("[bold]选项:[/]")
        for i, provider in enumerate(providers, 1):
            console.print(f"  [cyan]{i}[/] {provider}")
        
        console.print("  [cyan]0[/] 返回")
        console.print()
        
        choices = ["0"] + [str(i) for i in range(1, len(providers) + 1)]
        choice = Prompt.ask("[bold green]>[/]", choices=choices, default="0").strip().lower()
        while choice not in choices:
            choice = Prompt.ask("[bold green]>[/]", choices=choices, default="0").strip().lower()
        
        if choice == "0":
            break
        elif choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(providers):
                provider = providers[idx]
                if set_search_provider(provider):
                    console.print(f"\n[green]✅ 默认搜索服务已切换为: {provider}[/]")
                    console.print("\n[yellow]⚠️ 建议重启服务后生效[/]")
                else:
                    console.print("\n[bold red]❌ 切换失败[/]")
                pause_enter()
                break


def activate_configured_search_provider():
    """仅展示已配置 API Key 的官方搜索 provider，并激活其为默认。"""
    while True:
        console.clear()
        console.print(Panel(
            Text("激活已配置 Key 的搜索服务", style="bold cyan", justify="center"),
            box=box.DOUBLE
        ))

        providers = get_official_search_providers()
        configured = list_configured_official_search_providers(providers)

        if not configured:
            console.print("\n[yellow]未检测到已配置 API Key 的官方搜索服务。[/]")
            console.print("[dim]可在“官方搜索服务配置”中写入 key 或配置 .env。[/]")
            pause_enter()
            return

        console.print()
        console.print("[bold]可激活服务:[/]")
        for i, provider in enumerate(configured, 1):
            label = OFFICIAL_SEARCH_SPECS.get(provider, {}).get("label", provider)
            console.print(f"  [cyan]{i}[/] {provider} [dim]({label})[/]")
        console.print("  [cyan]0[/] 返回")
        console.print()

        choices = ["0"] + [str(i) for i in range(1, len(configured) + 1)]
        choice = Prompt.ask("[bold green]>[/]", choices=choices, default="0").strip().lower()
        while choice not in choices:
            choice = Prompt.ask("[bold green]>[/]", choices=choices, default="0").strip().lower()

        if choice == "0":
            return

        idx = int(choice) - 1
        provider = configured[idx]
        if set_search_provider(provider):
            console.print(f"\n[green]✅ 已激活默认搜索服务: {provider}[/]")
            console.print("\n[yellow]⚠️ 建议重启服务后生效[/]")
        else:
            console.print("\n[bold red]❌ 激活失败[/]")
        pause_enter()
        return


def _show_memory_provider_key_status(active_provider: str):
    console.print("\n[bold]向量 Provider 凭据状态 (models.providers.*.apiKey):[/]")
    active = str(active_provider or "auto").strip().lower() or "auto"
    for provider in OFFICIAL_MEMORY_PROVIDERS:
        target = get_memory_provider_credential_target(provider) or provider
        has_key = has_memory_provider_api_key(provider)
        mark = "✅" if has_key else "⬜"
        star = "⭐" if active == provider else "  "
        console.print(f"  {star} {mark} {provider}  -> models.providers.{target}.apiKey")


def _prompt_memory_provider_key(provider: str) -> bool:
    target = get_memory_provider_credential_target(provider)
    if not target:
        console.print("\n[bold red]❌ 当前 provider 不在官方支持列表[/]")
        return False

    if has_memory_provider_api_key(provider):
        console.print(f"\n[yellow]已检测到 models.providers.{target}.apiKey[/]")
        console.print("  [cyan]1[/] 继续使用已有 Key")
        console.print("  [cyan]2[/] 输入新 Key 覆盖")
        choice = Prompt.ask("[bold green]>[/]", choices=["1", "2"], default="1").strip()
        if choice == "1":
            return True

    token = getpass.getpass(f"请输入 {provider} 的 API Key (输入不会显示): ").strip()
    if not token:
        console.print("\n[bold red]❌ 未输入 Key，已取消[/]")
        return False
    ok = set_memory_provider_api_key(provider, token)
    if ok:
        console.print(f"\n[green]✅ 已写入 models.providers.{target}.apiKey[/]")
    else:
        console.print(f"\n[bold red]❌ 写入失败: models.providers.{target}.apiKey[/]")
    return ok


def _activate_memory_provider(provider: str):
    clear_memory_search_config(clear_provider=False)
    _, err, code = run_cli(["config", "set", "agents.defaults.memorySearch.provider", provider])
    if code != 0:
        console.print("\n[bold red]❌ 写入向量 provider 失败[/]")
        if err:
            console.print(f"[dim]{err}[/]")
        return
    console.print(f"\n[green]✅ 已设置向量 provider: {provider}[/]")
    console.print("\n[yellow]⚠️ 建议执行: openclaw memory status --deep[/]")
    console.print("[yellow]⚠️ 首次建立索引可执行: openclaw memory index --verbose[/]")


def _manage_memory_provider_key():
    providers = list(OFFICIAL_MEMORY_PROVIDERS)
    while True:
        console.print("\n[bold]选择要管理的凭据:[/]")
        for i, provider in enumerate(providers, 1):
            target = get_memory_provider_credential_target(provider) or provider
            mark = "✅" if has_memory_provider_api_key(provider) else "⬜"
            console.print(f"  [cyan]{i}[/] {mark} {provider} [dim](models.providers.{target}.apiKey)[/]")
        console.print("  [cyan]0[/] 返回")
        choices = ["0"] + [str(i) for i in range(1, len(providers) + 1)]
        choice = Prompt.ask("[bold green]>[/]", choices=choices, default="0").strip().lower()
        if choice == "0":
            return
        idx = int(choice) - 1
        if 0 <= idx < len(providers):
            _prompt_memory_provider_key(providers[idx])


def menu_embeddings():
    """向量化配置"""
    provider_map = {"2": "openai", "3": "gemini", "4": "voyage", "5": "mistral"}
    while True:
        console.clear()
        console.print(Panel(
            Text("🔍 向量化/记忆检索配置", style="bold cyan", justify="center"),
            box=box.DOUBLE
        ))

        ms = get_memory_search_config()
        provider = str(ms.get("provider", "auto") or "auto")

        console.print()
        console.print(f"[bold]当前向量 provider:[/] {provider}")
        _show_memory_provider_key_status(provider)

        console.print()
        console.print("[bold]选项:[/]")
        console.print("  [cyan]1[/] Auto (按已配置 Provider 凭据自动选择)")
        console.print("  [cyan]2[/] OpenAI")
        console.print("  [cyan]3[/] Gemini")
        console.print("  [cyan]4[/] Voyage")
        console.print("  [cyan]5[/] Mistral")
        console.print("  [cyan]6[/] 管理向量 Provider 凭据")
        console.print("  [cyan]V[/] 查看索引验证命令")
        console.print("  [cyan]0[/] 返回")
        console.print()

        choice = Prompt.ask(
            "[bold green]>[/]",
            choices=["0", "1", "2", "3", "4", "5", "6", "v"],
            default="0",
        ).strip().lower()

        if choice == "0":
            break
        if choice == "1":
            clear_memory_search_config(clear_provider=True)
            console.print("\n[green]✅ 已切换为 Auto[/]")
            console.print("\n[yellow]⚠️ Auto 会按已配置凭据自动选择向量 provider[/]")
            console.print("[yellow]⚠️ 建议执行: openclaw memory status --deep[/]")
            pause_enter()
            continue
        if choice in provider_map:
            selected = provider_map[choice]
            if not _prompt_memory_provider_key(selected):
                pause_enter()
                continue
            _activate_memory_provider(selected)
            pause_enter()
            continue
        if choice == "6":
            _run_menu_action(_manage_memory_provider_key, "管理向量 Provider 凭据")
            pause_enter()
            continue
        if choice == "v":
            console.print("\n[bold]验证命令:[/]")
            console.print("  [cyan]openclaw memory status --deep[/]")
            console.print("  [cyan]openclaw memory index --verbose[/]")
            pause_enter()


def choose_or_prompt_key(key_name: str, provider_name: str = None) -> bool:
    """选择使用已有 key 或输入新 key"""
    exists = check_existing_key(key_name, provider_name)
    if not exists:
        return prompt_and_set_env_key(key_name)
    console.print(f"\n[yellow]检测到已有 {key_name}[/]")
    console.print("  [cyan]1[/] 使用已有 Key")
    console.print("  [cyan]2[/] 输入新 Key (计费隔离)")
    c = Prompt.ask("\n[bold green]请选择[/]", choices=["1", "2"], default="1")
    if c == "2":
        return prompt_and_set_env_key(key_name)
    console.print("\n[green]✅ 已继续使用已有 Key[/]")
    return True


def prompt_and_set_env_key(key_name: str) -> bool:
    """提示输入并设置 env key"""
    value = getpass.getpass(f"请输入 {key_name} (输入不会显示): ").strip()
    if not value:
        console.print("\n[bold red]❌ 未输入 Key[/]")
        return False
    ok = set_env_key(key_name, value)
    if ok:
        console.print(f"\n[green]✅ 已写入 {key_name} 到 {DEFAULT_ENV_PATH}[/]")
    return ok


if __name__ == "__main__":
    menu_tools()
