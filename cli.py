#!/usr/bin/env python3
"""
EasyClaw - OpenClaw 管理 CLI 工具
基于 Rich 库的现代化终端界面
"""
import argparse
import os
import sys

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

console = Console(force_terminal=True, width=80)

# ========== 导入新模块 ==========
from tui.health import show_health_dashboard
from tui.inventory import menu_inventory
from tui.tools import menu_tools
from tui.routing import menu_routing
from tui.gateway import menu_gateway
from tui.system import menu_system


def menu_main():
    """主菜单"""
    while True:
        console.clear()
        
        # 简洁标题
        console.print()
        console.print("[bold cyan]========== EasyClaw - OpenClaw 管理面板 ==========[/]")
        console.print()
        
        # 功能列表（简单文本）
        console.print("[bold]功能菜单:[/]")
        console.print("  [cyan]1[/] 资源库       服务商/账号/模型管理")
        console.print("  [cyan]2[/] 资产大盘     账号状态/模型用量/子 Agent")
        console.print("  [cyan]3[/] 任务指派     Agent 模型路由配置")
        console.print("  [cyan]4[/] 子 Agent     开关/并发/白名单")
        console.print("  [cyan]5[/] 工具箱       日志清理/备份/配置向导")
        console.print("  [cyan]6[/] 网关设置     模式切换/端口/SSL")
        console.print("  [cyan]7[/] 快速操作     常用命令快捷入口")
        console.print("  [cyan]s[/] 状态速览     一键看全局健康")
        console.print("  [cyan]0[/] 退出")
        console.print()
        
        # 获取用户输入
        choice = Prompt.ask("[bold yellow]请选择[/]", choices=["0", "1", "2", "3", "4", "5", "6", "7", "s"], default="0")
        
        if choice == '0':
            console.print("[bold cyan]👋 再见![/]")
            break
        elif choice == '1':
            menu_inventory()
        elif choice == '2':
            show_health_dashboard()
        elif choice == '3':
            menu_routing()
        elif choice == '4':
            menu_subagent()
        elif choice == '5':
            menu_tools()
        elif choice == '6':
            menu_gateway()
        elif choice == '7':
            menu_quick_actions()
        elif choice == 's':
            show_status()


def menu_routing():
    """任务指派"""
    from tui.routing import menu_routing as routing_menu
    routing_menu()


def menu_subagent():
    """子 Agent（占位符，待移植）"""
    console.print("\n[yellow]⏳ 子 Agent 模块待移植...[/]")
    console.input("\n[dim]按回车键继续...[/]")


def menu_gateway():
    """网关设置"""
    from tui.gateway import menu_gateway as gateway_menu
    gateway_menu()


def menu_system():
    """系统辅助"""
    from tui.system import menu_system as system_menu
    system_menu()


def menu_quick_actions():
    """快速操作菜单"""
    try:
        from tui.quick_actions import show
        show()
    except ImportError as e:
        console.print(f"\n[bold red]错误: 无法加载快速操作模块 - {e}[/]")
        console.input("\n[dim]按回车键继续...[/]")


def show_status():
    """快速状态（占位符，待移植）"""
    console.print("\n[yellow]⏳ 快速状态模块待移植...[/]")
    console.input("\n[dim]按回车键继续...[/]")


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
