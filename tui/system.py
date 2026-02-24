"""
系统辅助 (System) 模块 - 重启、更新、回滚、Onboard
"""
import os
import glob
import subprocess
import signal
from typing import List
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich.prompt import Prompt, Confirm
from rich import box

from core import run_cli, DEFAULT_CONFIG_PATH, DEFAULT_BACKUP_DIR, OPENCLAW_BIN

console = Console()


def safe_safe_input(prompt=""):
    try:
        return safe_input(prompt)
    except (EOFError, KeyboardInterrupt):
        return ""



def menu_system():
    """系统辅助主菜单"""
    while True:
        console.clear()
        console.print()
        console.print("[bold cyan]========== 🛠️ 系统辅助 ==========[/]")
        console.print()
        
        console.print("[bold]功能:[/]")
        console.print("  [cyan]1[/] 🔄 重启/重载配置")
        console.print("  [cyan]2[/] 🚀 检查系统更新")
        console.print("  [cyan]3[/] 🛡️ 配置回滚")
        console.print("  [cyan]4[/] 🧙 重新运行 Onboard 向导")
        console.print("  [cyan]0[/] 返回")
        console.print()
        
        choice = Prompt.ask("[bold green]>[/]", choices=["0", "1", "2", "3", "4"], default="0")
        
        if choice == "0":
            break
        elif choice == "1":
            restart_gateway()
        elif choice == "2":
            check_update()
        elif choice == "3":
            rollback_config()
        elif choice == "4":
            run_onboard()


def is_docker_env() -> bool:
    """判断是否在 Docker 环境中"""
    return os.path.exists("/.dockerenv")


def get_container_name() -> str:
    """尝试获取容器名（从 TOOLS.md 或 hostname）"""
    # 先看看 TOOLS.md 里有没有记录
    try:
        with open("/root/.openclaw/workspace/TOOLS.md", "r") as f:
            content = f.read()
            # 查找类似 "openclaw_container: openclaw_260205" 这样的记录
            for line in content.split("\n"):
                if "openclaw_container" in line and ":" in line:
                    return line.split(":", 1)[1].strip()
    except Exception:
        pass
    
    # 试试 hostname
    try:
        with open("/etc/hostname", "r") as f:
            return f.read().strip()
    except Exception:
        pass
    
    return "openclaw"


def restart_gateway():
    """重启/重载配置"""
    console.clear()
    console.print(Panel(
        Text("🔄 重启/重载服务", style="bold cyan", justify="center"),
        box=box.DOUBLE
    ))
    
    in_docker = is_docker_env()
    container_name = get_container_name()
    
    console.print()
    
    if in_docker:
        console.print("[yellow]⚠️ 检测到 Docker 环境[/]")
        console.print()
        console.print("[bold]选择操作:[/]")
        console.print("  [cyan]1[/] 发送 SIGHUP 信号重载配置 (推荐)")
        console.print("     (如果网关支持热重载)")
        console.print()
        console.print("  [cyan]2[/] 重启 openclaw-gateway 进程")
        console.print("     (如果主进程是 openclaw，这可能会导致容器退出)")
        console.print()
        console.print("  [cyan]3[/] 重启整个容器 (需要在宿主机操作)")
        console.print(f"     docker restart {container_name}")
        console.print("     (Docker 环境请在宿主机执行)")
        console.print()
        console.print("  [cyan]0[/] 取消")
        console.print()
        
        choice = Prompt.ask("[bold green]请选择[/]", choices=["0", "1", "2", "3"], default="0")
        
        if choice == "0":
            return
        elif choice == "1":
            # 发送 SIGHUP 给 openclaw-gateway 进程
            try:
                import signal
                # 查找 openclaw-gateway 进程
                result = subprocess.run(["pgrep", "-f", "openclaw-gateway"], capture_output=True, text=True)
                if result.returncode == 0:
                    pids = result.stdout.strip().split()
                    if pids:
                        for pid in pids:
                            os.kill(int(pid), signal.SIGHUP)
                        console.print(f"\n[green]✅ 已发送 SIGHUP 信号给 {len(pids)} 个 openclaw-gateway 进程[/]")
                        console.print("\n[dim]💡 如果配置支持热重载，应该已经生效了[/]")
                    else:
                        console.print("\n[yellow]⚠️ 未找到 openclaw-gateway 进程[/]")
                else:
                    console.print("\n[yellow]⚠️ 未找到 openclaw-gateway 进程[/]")
            except Exception as e:
                console.print(f"\n[bold red]❌ 发送信号失败: {e}[/]")
                safe_input("\n按回车键继续...")
        elif choice == "2":
            console.print("\n[yellow]⚠️ 注意：在容器中直接重启进程可能会导致容器退出[/]")
            if Confirm.ask("[bold red]确定要继续吗?[/]", default=False):
                console.print("\n执行: 尝试重启 openclaw-gateway 进程\n")
                console.print("-" * 40)
                # 这里不实际执行，因为风险太大
                console.print("[yellow]⚠️ 此操作在容器中风险较大，已跳过[/]")
                console.print("-" * 40)
                safe_input("\n按回车键继续...")
        elif choice == "3":
            console.print(f"\n[yellow]⚠️ 容器重启需要在宿主机执行：[/]")
            console.print()
            console.print(f"   docker restart {container_name}")
            console.print()
            console.print("   或通过 1Panel 面板操作")
            safe_input("\n按回车键继续...")
    else:
        # 非 Docker 环境，显示原来的选项
        console.print("[bold]选择操作:[/]")
        console.print("  [cyan]1[/] openclaw gateway restart")
        console.print("     (宿主机模式重启，需要 systemd)")
        console.print()
        console.print("  [cyan]0[/] 取消")
        console.print()
        
        choice = Prompt.ask("[bold green]请选择[/]", choices=["0", "1"], default="0")
        
        if choice == "0":
            return
        elif choice == "1":
            console.print("\n执行: openclaw gateway restart\n")
            console.print("-" * 40)
            run_cli(["gateway", "restart"], capture=False)
            console.print("-" * 40)
            safe_input("\n按回车键继续...")


def check_update():
    """检查系统更新"""
    console.clear()
    console.print(Panel(
        Text("🚀 检查系统更新", style="bold cyan", justify="center"),
        box=box.DOUBLE
    ))
    
    console.print()
    console.print("[yellow]⏳ 正在检查更新...[/]")
    console.print()
    
    stdout, _, _ = run_cli(["update", "status"])
    console.print(stdout)
    
    safe_input("\n按回车键继续...")


def rollback_config():
    """配置回滚"""
    console.clear()
    console.print(Panel(
        Text("🛡️ 配置回滚", style="bold cyan", justify="center"),
        box=box.DOUBLE
    ))
    
    if not os.path.exists(DEFAULT_BACKUP_DIR):
        console.print("\n[bold red]❌ 没有发现备份[/]")
        safe_input("\n按回车键继续...")
        return
    
    backups = sorted(glob.glob(f"{DEFAULT_BACKUP_DIR}/*.json.bak"), reverse=True)[:10]
    
    if not backups:
        console.print("\n[bold red]❌ 没有发现备份[/]")
        safe_input("\n按回车键继续...")
        return
    
    console.print()
    console.print("[bold]可用的备份:[/]")
    console.print()
    
    table = Table(box=box.SIMPLE)
    table.add_column("编号", style="cyan", width=4)
    table.add_column("备份文件", style="bold")
    
    for i, b in enumerate(backups, 1):
        table.add_row(str(i), os.path.basename(b))
    
    console.print(table)
    
    console.print()
    console.print("[cyan]0[/] 返回")
    console.print()
    
    choices = ["0"] + [str(i) for i in range(1, len(backups) + 1)]
    choice = Prompt.ask("[bold green]>[/]", choices=choices, default="0")
    
    if choice == "0":
        return
    elif choice.isdigit():
        idx = int(choice) - 1
        if 0 <= idx < len(backups):
            backup_file = backups[idx]
            if Confirm.ask(f"[bold red]恢复 {os.path.basename(backup_file)}?[/]", default=False):
                import shutil
                shutil.copy(backup_file, DEFAULT_CONFIG_PATH)
                console.print("\n[green]✅ 已恢复，需要重启服务[/]")
                safe_input("\n按回车键继续...")


def run_onboard():
    """运行 Onboard 向导"""
    console.clear()
    console.print(Panel(
        Text("🧙 Onboard 向导", style="bold cyan", justify="center"),
        box=box.DOUBLE
    ))
    
    console.print()
    console.print("[yellow]即将启动 OpenClaw 初始化向导...[/]")
    console.print()
    console.print("[dim]💡 Onboard 可以帮助你：[/]")
    console.print("  [dim]- 配置新的 API Key / OAuth 账号[/]")
    console.print("  [dim]- 设置默认模型[/]")
    console.print("  [dim]- 配置 Telegram 等渠道[/]")
    console.print("  [dim]- 安装常用 Skills[/]")
    console.print()
    console.print("[yellow]⚠️ 注意：Onboard 会进入交互式流程，按 Ctrl+C 可随时退出[/]")
    console.print()
    
    if Confirm.ask("[bold green]确定要启动吗?[/]", default=False):
        console.print()
        run_cli(["onboard"], capture=False)
        console.print("\n[yellow]⚠️ 配置变更需要重启服务后生效[/]")
        safe_input("\n按回车键继续...")


if __name__ == "__main__":
    menu_system()
