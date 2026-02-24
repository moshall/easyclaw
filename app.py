#!/usr/bin/env python3
"""
EasyClaw - 高级界面版本
用 Rich Layout + 状态管理
数字键快速选择 + 优秀的视觉引导
"""
import os
import sys
from typing import Optional, Dict, Any
from datetime import datetime

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from rich.console import Console, RenderableType
from rich.layout import Layout
from rich.panel import Panel
from rich.text import Text
from rich.table import Table
from rich.prompt import Prompt, Confirm
from rich.live import Live
from rich import box
from rich.align import Align
from rich.style import Style

from core import config

console = Console()


class AppState:
    """应用状态管理"""
    def __init__(self):
        self.current_screen: str = "main"  # main | health | inventory | routing | tools | gateway | system
        self.last_update: datetime = datetime.now()
        self.notification: Optional[str] = None
        self.notification_level: str = "info"  # info | success | warning | error


def make_header(state: AppState) -> RenderableType:
    """渲染头部（更友好）"""
    header = Table.grid(expand=True)
    header.add_column()
    header.add_column(justify="right")
    
    title = Text("EasyClaw", style="bold cyan", justify="left")
    subtitle = Text("OpenClaw 管理面板", style="dim", justify="left")
    
    time_str = datetime.now().strftime("%H:%M:%S")
    right_info = Text(time_str, style="dim", justify="right")
    
    header.add_row(
        Panel(
            Text.assemble(title, "  ", subtitle),
            box=box.ROUNDED,
            border_style="blue"
        ),
        Panel(
            right_info,
            box=box.ROUNDED,
            border_style="blue"
        )
    )
    
    return header


def make_sidebar(state: AppState) -> RenderableType:
    """渲染侧边栏菜单（更好的视觉引导）"""
    menu_items = [
        ("1", "📊 资产大盘", "health", "查看账号状态和模型用量"),
        ("2", "⚙️ 资源库", "inventory", "管理服务商、账号和模型"),
        ("3", "🤖 任务指派", "routing", "设置默认模型和备选链"),
        ("4", "🧭 工具配置", "tools", "配置 Web 搜索和向量化"),
        ("5", "🌐 网关设置", "gateway", "配置端口、绑定和认证"),
        ("6", "🛠️ 系统辅助", "system", "重启、更新、回滚等"),
        ("0", "👋 退出", "exit", "退出 EasyClaw"),
    ]
    
    table = Table(box=box.ROUNDED, border_style="cyan", show_header=False, expand=True)
    table.add_column("Key", style="cyan", width=4)
    table.add_column("功能", style="bold")
    table.add_column("说明", style="dim", ratio=1)
    
    for key, label, screen, desc in menu_items:
        is_active = state.current_screen == screen
        style = "reverse" if is_active else ""
        
        key_text = Text(f"[{key}]", style=style)
        label_text = Text(label, style=style)
        desc_text = Text(desc, style="dim" if not is_active else style)
        
        table.add_row(key_text, label_text, desc_text)
    
    title = Text.assemble(
        Text("菜单 ", style="bold"),
        Text("(按数字键直接选择)", style="dim")
    )
    
    return Panel(table, title=title, border_style="cyan", padding=(1, 1))


def make_main_content(state: AppState) -> RenderableType:
    """渲染主内容区（更友好的引导）"""
    if state.current_screen == "main":
        # 主界面欢迎（更好的引导）
        welcome = Table.grid(expand=True)
        
        welcome_msg = Text(
            "欢迎使用 EasyClaw!\n\n",
            style="bold cyan",
            justify="center"
        )
        
        quick_start = Text(
            "🚀 快速开始：\n",
            style="bold green",
            justify="center"
        )
        
        instructions = Text(
            "  1. 看左侧菜单，找到你想用的功能\n"
            "  2. 按对应的数字键 (1-6) 直接选中\n"
            "  3. 按 [Enter] 进入完整功能界面\n"
            "  4. 按 [0] 返回这里或退出\n\n",
            justify="center"
        )
        
        tips = Text(
            "💡 小提示：所有配置更改都会自动备份！",
            style="dim",
            justify="center"
        )
        
        content = Text.assemble(welcome_msg, quick_start, instructions, tips)
        
        welcome.add_row(
            Panel(
                Align.center(content),
                box=box.ROUNDED,
                border_style="green"
            )
        )
        return welcome
    else:
        # 其他屏幕显示提示（更友好）
        screen_name_map = {
            "health": ("📊 资产大盘", "查看所有模型账号、用量配额"),
            "inventory": ("⚙️ 资源库", "管理服务商、绑定账号、激活模型"),
            "routing": ("🤖 任务指派", "设置默认模型、备选链、子 Agent"),
            "tools": ("🧭 工具配置", "配置 Web 搜索、向量化检索"),
            "gateway": ("🌐 网关设置", "配置端口、绑定地址、认证方式"),
            "system": ("🛠️ 系统辅助", "重启服务、检查更新、配置回滚"),
        }
        
        screen_name, screen_desc = screen_name_map.get(state.current_screen, (state.current_screen, ""))
        
        instructions = Text(
            "\n按 [Enter] 进入完整功能界面\n"
            "按 [0] 返回主菜单",
            justify="center"
        )
        
        content = Text.assemble(
            Text(f"{screen_name}\n\n", style="bold cyan", justify="center"),
            Text(f"{screen_desc}\n", justify="center"),
            instructions
        )
        
        return Panel(
            Align.center(content),
            title=screen_name,
            border_style="cyan"
        )


def make_notification(state: AppState) -> Optional[RenderableType]:
    """渲染通知"""
    if not state.notification:
        return None
    
    style_map = {
        "info": "blue",
        "success": "green",
        "warning": "yellow",
        "error": "red"
    }
    style = style_map.get(state.notification_level, "blue")
    
    return Panel(
        Text(state.notification, justify="center"),
        border_style=style,
        box=box.ROUNDED
    )


def make_footer() -> RenderableType:
    """渲染底部提示栏（更清晰）"""
    return Panel(
        Text(
            "[1-6] 选择功能  |  [Enter] 进入完整界面  |  [0] 返回/退出",
            style="dim",
            justify="center"
        ),
        box=box.ROUNDED,
        border_style="dim"
    )


def make_layout(state: AppState) -> Layout:
    """构建整个布局"""
    layout = Layout()
    
    # 分割为头部、主体、底部
    layout.split(
        Layout(make_header(state), name="header", size=3),
        Layout(name="body", ratio=1),
        Layout(make_footer(), name="footer", size=3)
    )
    
    # 主体分割为侧边栏和主内容
    layout["body"].split_row(
        Layout(make_sidebar(state), name="sidebar", size=40),
        Layout(make_main_content(state), name="content", ratio=1)
    )
    
    return layout


def launch_full_module(screen: str):
    """启动完整功能模块（临时离开 Live）"""
    console.clear()
    
    # 导入模块
    from tui.health import show_health_dashboard
    from tui.inventory import menu_inventory
    from tui.routing import menu_routing
    from tui.tools import menu_tools
    from tui.gateway import menu_gateway
    from tui.system import menu_system
    
    # 模块映射
    module_map = {
        "health": show_health_dashboard,
        "inventory": menu_inventory,
        "routing": menu_routing,
        "tools": menu_tools,
        "gateway": menu_gateway,
        "system": menu_system,
    }
    
    if screen in module_map:
        module_map[screen]()
    
    console.clear()


def main():
    """主函数"""
    state = AppState()
    
    console.clear()
    
    # 定义屏幕映射
    screen_map = {
        "1": "health",
        "2": "inventory",
        "3": "routing",
        "4": "tools",
        "5": "gateway",
        "6": "system",
        "0": "exit",
    }
    
    try:
        with Live(make_layout(state), console=console, auto_refresh=False, screen=True) as live:
            while True:
                # 渲染当前布局
                live.update(make_layout(state))
                live.refresh()
                
                # 等待用户输入（更清晰的提示）
                choice = Prompt.ask(
                    "",
                    choices=["0", "1", "2", "3", "4", "5", "6", ""],
                    default="",
                    show_choices=False
                )
                
                # 处理输入
                if choice == "":
                    # Enter 键 - 如果在非主界面，进入完整模块
                    if state.current_screen != "main" and state.current_screen != "exit":
                        live.stop()
                        launch_full_module(state.current_screen)
                        state.current_screen = "main"
                        live.start()
                        live.update(make_layout(state))
                        live.refresh()
                elif choice in screen_map:
                    screen = screen_map[choice]
                    
                    if screen == "exit":
                        console.clear()
                        console.print("[bold cyan]👋 再见![/]")
                        return
                    else:
                        state.current_screen = screen
    
    except KeyboardInterrupt:
        console.clear()
        console.print("[bold cyan]👋 再见![/]")
        return


if __name__ == "__main__":
    main()
