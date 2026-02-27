"""
顶层导航聚合菜单
"""
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.text import Text
from rich import box

from core.utils import pause_enter
from tui.inventory import menu_inventory
from tui.routing import (
    global_model_policy_menu,
    main_agent_settings_menu,
    subagent_settings_menu,
    agent_model_policy_menu,
    spawn_model_policy_menu,
    list_agent_model_override_details,
    get_spawn_model_policy,
    get_default_model,
    get_fallbacks,
)
from tui.gateway import menu_gateway
from tui.system import menu_system
from tui.tools import menu_tools

console = Console()


def _get_model_provider_status():
    try:
        default_model = get_default_model() or ""
        fallbacks = get_fallbacks() or []
        override_details = list_agent_model_override_details() or []
        spawn_primary, spawn_fallbacks = get_spawn_model_policy()
        return {
            "default_model": default_model,
            "fallbacks": fallbacks,
            "agent_override_details": override_details,
            "spawn_primary": spawn_primary or "",
            "spawn_fallbacks": spawn_fallbacks or [],
            "error": "",
        }
    except Exception as e:
        return {
            "default_model": "",
            "fallbacks": [],
            "agent_override_details": [],
            "spawn_primary": "",
            "spawn_fallbacks": [],
            "error": str(e),
        }


def menu_model_provider():
    """模型与供应商管理"""
    while True:
        console.clear()
        console.print(Panel(
            Text("🧩 模型与供应商管理", style="bold cyan", justify="center"),
            box=box.DOUBLE
        ))
        console.print()
        status = _get_model_provider_status()
        default_model = status["default_model"]
        fallbacks = status["fallbacks"]
        override_details = status["agent_override_details"]
        spawn_primary = status["spawn_primary"]
        spawn_fallbacks = status["spawn_fallbacks"]
        console.print("[bold]当前设置:[/]")
        if status["error"]:
            console.print(f"  [yellow]主模型:[/] [dim](读取失败)[/]")
            console.print(f"  [yellow]备用链:[/] [dim](读取失败)[/]")
            console.print(f"  [dim]详情: {status['error']}[/]")
        else:
            console.print(f"  [yellow]主模型:[/] [green]{default_model}[/]" if default_model else "  [yellow]主模型:[/] [dim](未设置)[/]")
            if fallbacks:
                console.print(f"  [yellow]备用链:[/] [cyan]{' → '.join(fallbacks)}[/]")
            else:
                console.print("  [yellow]备用链:[/] [dim](未设置)[/]")
            if override_details:
                console.print("  [yellow]Agent 独立模型:[/]")
                for item in override_details[:3]:
                    aid = item.get("agent_id", "")
                    primary = item.get("primary", "") or "(仅备选)"
                    fb = item.get("fallbacks", []) or []
                    if fb:
                        console.print(f"    [magenta]{aid}[/]: [green]{primary}[/] | [cyan]{' → '.join(fb)}[/]")
                    else:
                        console.print(f"    [magenta]{aid}[/]: [green]{primary}[/]")
                if len(override_details) > 3:
                    console.print(f"    [dim]... 还有 {len(override_details) - 3} 个 Agent[/]")
            else:
                console.print("  [yellow]Agent 独立模型:[/] [dim](无，均跟随全局)[/]")
            if spawn_primary:
                console.print(f"  [yellow]Spawn 默认模型:[/] [green]{spawn_primary}[/]")
            else:
                console.print("  [yellow]Spawn 默认模型:[/] [dim](继承全局)[/]")
            if spawn_fallbacks:
                console.print(f"  [yellow]Spawn 备用链:[/] [cyan]{' → '.join(spawn_fallbacks)}[/]")
        console.print()
        console.print("[bold]操作:[/]")
        console.print("  [cyan]1[/] 供应商/模型资源库")
        console.print("  [cyan]2[/] 全局模型优先级")
        console.print("  [cyan]3[/] 指定Agent模型优先级")
        console.print("  [cyan]4[/] 临时指派Agent（Spawn）模型优先级（默认与全局一致）")
        console.print("  [cyan]0[/] 返回")
        console.print()
        choice = Prompt.ask("[bold green]>[/]", choices=["0", "1", "2", "3", "4"], default="0")
        if choice == "0":
            return
        if choice == "1":
            menu_inventory()
        elif choice == "2":
            global_model_policy_menu()
        elif choice == "3":
            agent_model_policy_menu()
        elif choice == "4":
            spawn_model_policy_menu()


def menu_service_config():
    """服务配置"""
    while True:
        console.clear()
        console.print(Panel(
            Text("🛠️ 服务配置", style="bold cyan", justify="center"),
            box=box.DOUBLE
        ))
        console.print()
        console.print("[bold]操作:[/]")
        console.print("  [cyan]1[/] 工具配置 (搜索服务/向量化)")
        console.print("  [cyan]0[/] 返回")
        console.print()
        choice = Prompt.ask("[bold green]>[/]", choices=["0", "1"], default="0")
        if choice == "0":
            return
        if choice == "1":
            menu_tools()


def menu_agent_workspace():
    """Agent 与工作区"""
    main_agent_settings_menu()


def menu_subagent_control():
    """Agent 派发管理"""
    subagent_settings_menu()


def menu_automation_integration():
    """自动化与集成"""
    while True:
        console.clear()
        console.print(Panel(
            Text("🔌 自动化与集成", style="bold cyan", justify="center"),
            box=box.DOUBLE
        ))
        console.print()
        console.print("[bold]操作:[/]")
        console.print("  [cyan]1[/] 网关设置")
        console.print("  [cyan]2[/] 系统辅助 (Onboard/重启/回滚)")
        console.print("  [cyan]0[/] 返回")
        console.print()
        choice = Prompt.ask("[bold green]>[/]", choices=["0", "1", "2"], default="0")
        if choice == "0":
            return
        if choice == "1":
            menu_gateway()
        elif choice == "2":
            menu_system()
