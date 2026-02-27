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
import select
import termios
import tty

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
NAV_MODE = os.environ.get("EASYCLAW_NAV_MODE", "line").strip().lower()  # line | keys


class AppState:
    """应用状态管理"""
    def __init__(self):
        self.current_screen: str = "main"  # main | health | models | agent_workspace | subagent | services | automation
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
        ("1", "📊  资产大盘", "health"),
        ("2", "🧩  模型与供应商", "models"),
        ("3", "🧭  Agent 与工作区", "agent_workspace"),
        ("4", "👥  Agent 派发管理", "subagent"),
        ("5", "🛠️  服务配置", "services"),
        ("6", "🔌  自动化与集成", "automation"),
        ("0", "👋  退出", "exit"),
    ]
    
    table = Table(box=box.ROUNDED, border_style="cyan", show_header=False, expand=True)
    table.add_column("Key", style="cyan", width=4)
    table.add_column("功能", style="bold", ratio=1)
    
    for key, label, screen in menu_items:
        is_active = state.current_screen == screen
        style = "reverse" if is_active else ""
        
        key_text = Text(f"[{key}]", style=style)
        label_text = Text(label, style=style)
        
        table.add_row(key_text, label_text)
    
    title = Text.assemble(
        Text("菜单 ", style="bold"),
        Text("(数字键或 ↑↓)", style="dim")
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
            "models": ("🧩 模型与供应商", "管理服务商、激活模型、主备模型"),
            "agent_workspace": ("🧭 Agent 与工作区", "创建主 Agent、绑定 workspace、初始化模板"),
            "subagent": ("👥 Agent 派发管理", "派发开关、并发上限、固定 Agent 白名单"),
            "services": ("🛠️ 服务配置", "搜索服务、向量化等工具配置"),
            "automation": ("🔌 自动化与集成", "网关、系统"),
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
    if NAV_MODE == "keys":
        hint = "[1-6/↑↓/j/k] 选择功能  |  [Enter/e/l/o/→] 进入完整界面  |  [0] 返回/退出"
    else:
        hint = "[1-6] 选择功能  |  [Enter] 进入完整界面  |  [0] 返回/退出"
    return Panel(
        Text(
            hint,
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


def _read_menu_key() -> str:
    """读取单键输入。返回: UP/DOWN/ENTER/0-6/UNKNOWN"""
    if NAV_MODE != "keys":
        # 稳定模式：读取整行，取首个有效字符，避免 Prompt.ask 在某些 TTY 里丢值
        try:
            raw = sys.stdin.readline()
        except Exception:
            return "UNKNOWN"
        if raw is None:
            return "UNKNOWN"
        s = raw.strip()
        if s == "":
            return "ENTER"
        c = s[0]
        if c in "0123456":
            return c
        return "UNKNOWN"

    if not sys.stdin.isatty():
        choice = Prompt.ask("", choices=["0", "1", "2", "3", "4", "5", "6", ""], default="", show_choices=False)
        return "ENTER" if choice == "" else choice

    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        # 读取一个小批次字节，避免分段读导致 ESC 序列解析不完整
        if not select.select([sys.stdin], [], [], 0.5)[0]:
            return "UNKNOWN"
        data = os.read(fd, 32)
        if not data:
            return "UNKNOWN"

        if b"\x03" in data:
            raise KeyboardInterrupt

        # 数字键
        for d in b"012345":
            if bytes([d]) == data or data.startswith(bytes([d])):
                return chr(d)

        # 回车（含 keypad enter 常见序列）
        if data in (b"\r", b"\n", b"\r\n") or data.endswith(b"\r") or data.endswith(b"\n"):
            return "ENTER"
        if b"\x1bOM" in data or b"[13~" in data:
            return "ENTER"

        # vim 风格备用键
        if data[:1] in (b"k", b"K"):
            return "UP"
        if data[:1] in (b"j", b"J"):
            return "DOWN"
        if data[:1] in (b"l", b"L", b"e", b"E", b"o", b"O", b" "):
            return "ENTER"

        # 方向右键也作为进入
        if b"[C" in data or b"OC" in data:
            return "ENTER"

        # 一些终端的 Enter 可能被编码到更长序列中，兜底识别 "13~"
        if b"13~" in data:
            return "ENTER"

        # 方向键（兼容 ESC [ A/B 与 ESC O A/B，及混合前缀）
        if b"[A" in data or b"OA" in data:
            return "UP"
        if b"[B" in data or b"OB" in data:
            return "DOWN"

        return "UNKNOWN"
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
    
    # 导入模块
    from tui.health import show_health_dashboard
    from tui.navigation import (
        menu_model_provider,
        menu_agent_workspace,
        menu_subagent_control,
        menu_service_config,
        menu_automation_integration,
    )
    
    # 模块映射
    module_map = {
        "health": show_health_dashboard,
        "models": menu_model_provider,
        "agent_workspace": menu_agent_workspace,
        "subagent": menu_subagent_control,
        "services": menu_service_config,
        "automation": menu_automation_integration,
    }
    
    if screen in module_map:
        module_map[screen]()
    
    console.clear()


def _drain_stdin_buffer():
    """清空 stdin 缓冲，避免回车残留导致子菜单瞬间返回。"""
    if not sys.stdin.isatty():
        return
    fd = sys.stdin.fileno()
    try:
        while select.select([sys.stdin], [], [], 0.0)[0]:
            os.read(fd, 256)
    except Exception:
        pass


def main():
    """主函数"""
    state = AppState()
    
    console.clear()
    
    # 定义屏幕映射
    screen_map = {
        "1": "health",
        "2": "models",
        "3": "agent_workspace",
        "4": "subagent",
        "5": "services",
        "6": "automation",
        "0": "exit",
    }
    nav_order = ["health", "models", "agent_workspace", "subagent", "services", "automation", "exit"]
    
    try:
        with Live(make_layout(state), console=console, auto_refresh=False, screen=True) as live:
            while True:
                # 渲染当前布局
                live.update(make_layout(state))
                live.refresh()
                
                key = _read_menu_key()

                # 处理输入
                if key == "ENTER":
                    # Enter 键 - 如果在非主界面，进入完整模块
                    if state.current_screen == "exit":
                        console.clear()
                        console.print("[bold cyan]👋 再见![/]")
                        return
                    if state.current_screen != "main":
                        _drain_stdin_buffer()
                        live.stop()
                        launch_full_module(state.current_screen)
                        state.current_screen = "main"
                        live.start()
                        live.update(make_layout(state))
                        live.refresh()
                elif key == "UP":
                    if state.current_screen not in nav_order:
                        state.current_screen = nav_order[0]
                    else:
                        idx = nav_order.index(state.current_screen)
                        state.current_screen = nav_order[(idx - 1) % len(nav_order)]
                elif key == "DOWN":
                    if state.current_screen not in nav_order:
                        state.current_screen = nav_order[0]
                    else:
                        idx = nav_order.index(state.current_screen)
                        state.current_screen = nav_order[(idx + 1) % len(nav_order)]
                elif key in screen_map:
                    screen = screen_map[key]
                    
                    if screen == "exit":
                        console.clear()
                        console.print("[bold cyan]👋 再见![/]")
                        return
                    else:
                        if NAV_MODE == "keys":
                            state.current_screen = screen
                        else:
                            # 稳定模式：数字直达模块，避免依赖二次回车
                            _drain_stdin_buffer()
                            live.stop()
                            launch_full_module(screen)
                            state.current_screen = "main"
                            live.start()
                            live.update(make_layout(state))
                            live.refresh()
    
    except KeyboardInterrupt:
        console.clear()
        console.print("[bold cyan]👋 再见![/]")
        return


if __name__ == "__main__":
    main()
