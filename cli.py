#!/usr/bin/env python3
"""
EasyClaw - OpenClaw 管理 CLI 工具
基于 Rich 库的现代化终端界面
"""
import argparse
import os
import sys
from datetime import datetime

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

OPENCLAW_BIN = "/usr/local/bin/openclaw"

# ========== Rich 初始化 ==========
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich.prompt import Prompt, Confirm
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich import box
from rich.layout import Layout
from rich.align import Align

console = Console(force_terminal=True)

# ========== 导入新模块 ==========
from tui.health import show_health_dashboard
from tui.navigation import (
    menu_model_provider,
    menu_agent_workspace,
    menu_subagent_control,
    menu_automation_integration,
    menu_service_config,
)
from tui.routing import get_default_model, get_fallbacks


def _build_main_layout() -> Layout:
    now = datetime.now().strftime("%H:%M:%S")
    layout = Layout()
    layout.split(
        Layout(name="header", size=3),
        Layout(name="body", ratio=1),
        Layout(name="footer", size=3),
    )
    layout["body"].split_row(
        Layout(name="menu", size=34),
        Layout(name="content", ratio=1),
    )

    header = Panel(
        Text.assemble(
            ("EasyClaw", "bold cyan"),
            ("  ", ""),
            ("OpenClaw 管理面板", "dim"),
            ("   ", ""),
            (now, "bold green"),
            justify="center",
        ),
        box=box.DOUBLE,
        border_style="cyan",
        padding=(0, 1),
    )
    layout["header"].update(header)

    menu_table = Table(box=box.SIMPLE_HEAVY, border_style="blue", pad_edge=True)
    menu_table.add_column("编号", style="bold cyan", width=6, justify="center", no_wrap=True)
    menu_table.add_column("模块", style="bold", min_width=22, no_wrap=True)
    menu_table.add_row("[1]", "📊  资产大盘")
    menu_table.add_row("[2]", "🧩  模型与供应商")
    menu_table.add_row("[3]", "🧭  Agent 与工作区")
    menu_table.add_row("[4]", "👥  Agent 派发管理")
    menu_table.add_row("[5]", "🛠️  服务配置")
    menu_table.add_row("[6]", "🔌  自动化与集成")
    menu_table.add_row("[0]", "👋  退出")
    layout["menu"].update(Panel(menu_table, border_style="blue", box=box.ROUNDED, title="操作菜单"))

    default_model = get_default_model() or "(未设置)"
    fallbacks = get_fallbacks()
    fallback_text = " -> ".join(fallbacks[:3]) if fallbacks else "(未设置)"
    if len(fallbacks) > 3:
        fallback_text += " -> ..."
    guidance = Table.grid(padding=(0, 1))
    guidance.add_row(Text("模块说明", style="bold", overflow="fold", no_wrap=False))
    guidance.add_row(Text("1. 资产大盘: 账号状态 / 模型用量 / 子 Agent", overflow="fold", no_wrap=False))
    guidance.add_row(Text("2. 模型与供应商: 供应商、模型激活、主备模型", overflow="fold", no_wrap=False))
    guidance.add_row(Text("3. Agent 与工作区: 创建主 Agent、绑定 workspace", overflow="fold", no_wrap=False))
    guidance.add_row(Text("4. Agent 派发管理: 派发开关、并发、固定 Agent 白名单", overflow="fold", no_wrap=False))
    guidance.add_row(Text("5. 服务配置: 搜索服务 / 向量化等工具配置", overflow="fold", no_wrap=False))
    guidance.add_row(Text("6. 自动化与集成: 网关 / 系统", overflow="fold", no_wrap=False))
    guidance.add_row("")
    guidance.add_row(Text("当前全局模型", style="bold", overflow="fold", no_wrap=False))
    guidance.add_row(Text(default_model, style="green", overflow="fold", no_wrap=False))
    guidance.add_row("")
    guidance.add_row(Text("当前备用链", style="bold", overflow="fold", no_wrap=False))
    guidance.add_row(Text(fallback_text, style="cyan", overflow="fold", no_wrap=False))
    guidance.add_row("")
    guidance.add_row(Text("使用方式", style="bold", overflow="fold", no_wrap=False))
    guidance.add_row(Text("输入数字后回车，直接进入对应模块", overflow="fold", no_wrap=False))
    guidance.add_row(Text("示例: 输入 2 进入模型与供应商管理", overflow="fold", no_wrap=False))
    guidance.add_row(Text("输入 0 退出", overflow="fold", no_wrap=False))
    layout["content"].update(Panel(Align.left(guidance), box=box.ROUNDED, border_style="green", title="状态与指引"))

    footer = Panel(
        Text("稳定模式: 纯数字输入（不依赖方向键兼容）", justify="center", style="dim"),
        box=box.ROUNDED,
        border_style="grey50",
    )
    layout["footer"].update(footer)
    return layout


def menu_main():
    """主菜单"""
    while True:
        console.clear()
        console.print(_build_main_layout())
        console.print()
        
        # 获取用户输入
        choice = Prompt.ask("[bold yellow]请选择[/]", choices=["0", "1", "2", "3", "4", "5", "6"], default="0")
        
        if choice == '0':
            console.print("[bold cyan]👋 再见![/]")
            break
        elif choice == '1':
            show_health_dashboard()
        elif choice == '2':
            menu_model_provider()
        elif choice == '3':
            menu_agent_workspace()
        elif choice == '4':
            menu_subagent_control()
        elif choice == '5':
            menu_service_config()
        elif choice == '6':
            menu_automation_integration()


def show_status():
    """状态入口（当前直接复用资产大盘）"""
    show_health_dashboard()


# ========== 入口 ==========
def main():
    parser = argparse.ArgumentParser(prog="easyclaw", description="EasyClaw - OpenClaw 管理工具")
    parser.add_argument("command", nargs="?", help="命令")
    args = parser.parse_args()
    
    if args.command == "status":
        show_status()
    else:
        try:
            menu_main()
        except KeyboardInterrupt:
            console.print("\n[bold cyan]👋 再见![/]")
        except Exception as e:
            console.print(f"[bold red]错误: {e}[/]")


if __name__ == "__main__":
    main()
