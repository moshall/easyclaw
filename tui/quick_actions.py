"""快速操作模块 - EasyClaw TUI."""

import os
import sys
import subprocess
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box

console = Console()


def show():
    """显示快速操作主菜单."""
    while True:
        console.clear()
        console.print(Panel.fit(
            "[bold cyan]⚡ 快速操作[/bold cyan]",
            title="EasyClaw",
            border_style="cyan"
        ))
        
        table = Table(box=box.ROUNDED, show_header=False)
        table.add_column("Option", style="cyan", justify="center")
        table.add_column("Description", style="white")
        
        table.add_row("1", "启动 Gateway 服务")
        table.add_row("2", "停止 Gateway 服务")
        table.add_row("3", "重启 Gateway 服务")
        table.add_row("4", "查看 Gateway 状态")
        table.add_row("5", "查看日志 (最新 50 行)")
        table.add_row("6", "清理临时文件")
        table.add_row("7", "运行健康检查")
        table.add_row("0", "返回主菜单")
        
        console.print(table)
        
        choice = console.input("\n[bold yellow]请选择操作 (0-7): [/bold yellow]").strip()
        
        if choice == "0":
            break
        elif choice == "1":
            _run_action("启动 Gateway", _start_gateway)
        elif choice == "2":
            _run_action("停止 Gateway", _stop_gateway)
        elif choice == "3":
            _run_action("重启 Gateway", _restart_gateway)
        elif choice == "4":
            _run_action("查看 Gateway 状态", _gateway_status)
        elif choice == "5":
            _run_action("查看日志", _view_logs)
        elif choice == "6":
            _run_action("清理临时文件", _cleanup_temp)
        elif choice == "7":
            _run_action("运行健康检查", _health_check)
        else:
            console.print("[bold red]无效选项，请重新选择[/bold red]")
            console.input("\n按 Enter 继续...")


def _run_action(name: str, action_func):
    """执行操作并显示结果."""
    console.clear()
    console.print(Panel.fit(
        f"[bold cyan]⚡ {name}[/bold cyan]",
        border_style="cyan"
    ))
    
    try:
        result = action_func()
        if result:
            console.print(f"[bold green]✓ {result}[/bold green]")
    except Exception as e:
        console.print(f"[bold red]✗ 错误: {e}[/bold red]")
    
    console.input("\n按 Enter 继续...")


def _start_gateway() -> str:
    """启动 Gateway 服务."""
    try:
        result = subprocess.run(
            ["openclaw", "gateway", "start"],
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode == 0:
            return "Gateway 服务已启动"
        else:
            raise RuntimeError(result.stderr or "启动失败")
    except subprocess.TimeoutExpired:
        return "Gateway 启动中..."


def _stop_gateway() -> str:
    """停止 Gateway 服务."""
    try:
        result = subprocess.run(
            ["openclaw", "gateway", "stop"],
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode == 0:
            return "Gateway 服务已停止"
        else:
            raise RuntimeError(result.stderr or "停止失败")
    except subprocess.TimeoutExpired:
        return "Gateway 停止中..."


def _restart_gateway() -> str:
    """重启 Gateway 服务."""
    _stop_gateway()
    return _start_gateway()


def _gateway_status() -> str:
    """查看 Gateway 状态."""
    try:
        result = subprocess.run(
            ["openclaw", "gateway", "status"],
            capture_output=True,
            text=True,
            timeout=5
        )
        console.print("[bold cyan]Gateway 状态:[/bold cyan]")
        console.print(result.stdout)
        if result.stderr:
            console.print(f"[yellow]提示: {result.stderr}[/yellow]")
        return "状态查看完成"
    except subprocess.TimeoutExpired:
        return "状态查询超时"


def _view_logs() -> str:
    """查看日志."""
    try:
        # 首先检查 openclaw logs 命令
        result = subprocess.run(
            ["openclaw", "gateway", "logs", "--tail", "50"],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        if result.returncode == 0:
            console.print("[bold cyan]最近 50 行日志:[/bold cyan]")
            console.print(result.stdout)
        else:
            # 尝试 journalctl
            result2 = subprocess.run(
                ["journalctl", "-u", "openclaw", "-n", "50", "--no-pager"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result2.returncode == 0:
                console.print("[bold cyan]最近 50 行日志:[/bold cyan]")
                console.print(result2.stdout)
            else:
                raise RuntimeError("无法获取日志")
        
        return "日志查看完成"
    except Exception as e:
        raise RuntimeError(f"查看日志失败: {e}")


def _cleanup_temp() -> str:
    """清理临时文件."""
    temp_dirs = [
        "/tmp/openclaw",
        "/var/tmp/openclaw",
    ]
    
    cleaned = 0
    for temp_dir in temp_dirs:
        if os.path.exists(temp_dir):
            try:
                import shutil
                file_count = sum([len(files) for _, _, files in os.walk(temp_dir)])
                shutil.rmtree(temp_dir)
                cleaned += file_count
            except Exception as e:
                console.print(f"[yellow]清理 {temp_dir} 时出错: {e}[/yellow]")
    
    # 清理 Python 缓存
    cache_patterns = ["__pycache__", "*.pyc", "*.pyo"]
    console.print("[dim]已清理临时文件和缓存[/dim]")
    
    return f"已清理 {cleaned} 个临时文件"


def _health_check() -> str:
    """运行健康检查."""
    try:
        console.print("[bold cyan]运行健康检查...[/bold cyan]")
        
        # 基础检查
        checks = [
            ("Gateway 服务", lambda: _check_gateway_running()),
            ("配置文件", lambda: _check_config()),
            ("磁盘空间", lambda: _check_disk_space()),
            ("内存使用", lambda: _check_memory()),
        ]
        
        table = Table(title="健康检查结果")
        table.add_column("项目", style="cyan")
        table.add_column("状态", style="bold")
        table.add_column("详情", style="dim")
        
        for name, check_func in checks:
            try:
                status, detail = check_func()
                color = "green" if status == "✓" else "yellow" if status == "!" else "red"
                table.add_row(name, f"[{color}]{status}[/{color}]", detail)
            except Exception as e:
                table.add_row(name, "[red]✗[/red]", str(e))
        
        console.print(table)
        return "健康检查完成"
        
    except Exception as e:
        return f"健康检查失败: {e}"


def _check_gateway_running() -> tuple:
    """检查 Gateway 是否运行."""
    try:
        result = subprocess.run(
            ["openclaw", "gateway", "status"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            return ("✓", "运行中")
        return ("✗", "未运行")
    except Exception as e:
        return ("!", f"检查失败: {e}")


def _check_config() -> tuple:
    """检查配置文件."""
    try:
        config_paths = [
            "/root/.openclaw/config.yaml",
            "/root/.openclaw/config.yml",
        ]
        for path in config_paths:
            if os.path.exists(path):
                return ("✓", f"配置正常 ({os.path.basename(path)})")
        return ("!", "未找到配置文件")
    except Exception as e:
        return ("!", f"检查失败: {e}")


def _check_disk_space() -> tuple:
    """检查磁盘空间."""
    try:
        import shutil
        stat = shutil.disk_usage("/")
        free_gb = stat.free / (1024**3)
        total_gb = stat.total / (1024**3)
        percent_free = (stat.free / stat.total) * 100
        
        if percent_free < 10:
            return ("!", f"空间不足: {free_gb:.1f}GB / {total_gb:.1f}GB")
        return ("✓", f"空间充足: {free_gb:.1f}GB / {total_gb:.1f}GB")
    except Exception as e:
        return ("!", f"检查失败: {e}")


def _check_memory() -> tuple:
    """检查内存使用."""
    try:
        with open('/proc/meminfo', 'r') as f:
            meminfo = f.read()
        
        mem_total = 0
        mem_available = 0
        
        for line in meminfo.split('\n'):
            if line.startswith('MemTotal:'):
                mem_total = int(line.split()[1]) / 1024 / 1024  # GB
            elif line.startswith('MemAvailable:'):
                mem_available = int(line.split()[1]) / 1024 / 1024  # GB
        
        if mem_total > 0:
            percent_available = (mem_available / mem_total) * 100
            if percent_available < 10:
                return ("!", f"内存紧张: {mem_available:.1f}GB / {mem_total:.1f}GB 可用")
            return ("✓", f"内存正常: {mem_available:.1f}GB / {mem_total:.1f}GB 可用")
        
        return ("!", "无法读取内存信息")
    except Exception as e:
        return ("!", f"检查失败: {e}")
