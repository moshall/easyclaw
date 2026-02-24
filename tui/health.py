"""
资产大盘 (Health) 模块 - 账号状态、模型用量、子 Agent 状态
优化版：进度条、颜色强化、小贴士、模型可用状态、Key 探测
修复版：修正 JSON 解析逻辑
"""
import os
import json
import time
import re
from typing import Dict, List
from collections import defaultdict
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
    DEFAULT_AUTH_PROFILES_PATH,
    DEFAULT_BACKUP_DIR,
    DEFAULT_CONFIG_PATH
)

console = Console()


def safe_safe_input(prompt=""):
    try:
        return safe_input(prompt)
    except (EOFError, KeyboardInterrupt):
        return ""



def show_health_dashboard():
    """显示资产大盘"""
    console.clear()
    console.print()
    console.print("[bold cyan]========== 📊 资产大盘 (Health) ==========[/]")
    console.print()
    
    # 小贴士
    console.print(Panel(
        Text("💡 这里展示你的所有模型账号、用量配额", 
             style="dim", justify="center"),
        box=box.ROUNDED,
        border_style="blue"
    ))
    
    with console.status("[yellow]⏳ 正在获取实时状态...[/]"):
        # 获取完整状态
        usage_output, _, usage_code = run_cli(["status", "--usage"])
        status = run_cli_json(["models", "status", "--json"])
        # 获取所有模型的 available 状态
        all_models_available = get_all_models_available()
    
    # 1. 账号授权状态
    show_account_status(status)
    
    # 2. 模型资产概览（带 available 状态）
    show_models_overview(status, all_models_available)
    
    # 3. 用量统计（带进度条，最后加 probe 选项）
    show_usage_stats_with_progress(usage_output, usage_code)


def get_all_models_available() -> Dict[str, bool]:
    """获取所有模型的 available 状态（从 models list --all --json）"""
    available_map = {}
    try:
        stdout, stderr, code = run_cli(["models", "list", "--all", "--json"])
        if code == 0 and stdout:
            data = json.loads(stdout)
            for m in data.get("models", []):
                key = m.get("key")
                if key:
                    available_map[key] = m.get("available", False)
    except Exception:
        pass
    return available_map


def show_account_status(status: Dict):
    """显示账号授权状态（修正 JSON 解析）"""
    console.print()
    console.print(Panel(
        Text("🔑 账号授权状态", style="bold", justify="center"),
        box=box.DOUBLE
    ))
    
    # 小贴士
    console.print("  [dim]💡 OAuth 账号有有效期，API Key/环境变量/models.json 长期有效[/]")
    console.print()
    
    # 获取 providers 数组（修正路径）
    providers_status = status.get("auth", {}).get("providers", [])
    
    if not providers_status:
        console.print("  [yellow](尚未配置任何账号授权)[/]")
    else:
        table = Table(box=box.SIMPLE)
        table.add_column("状态", style="cyan", width=10)
        table.add_column("服务商", style="bold", width=20)
        table.add_column("类型", style="green", width=12)
        table.add_column("详情", style="yellow")
        
        for p in providers_status:
            provider = p.get("provider", "unknown")
            effective = p.get("effective", {})
            kind = effective.get("kind", "unknown")
            profiles = p.get("profiles", {})
            count = profiles.get("count", 0)
            
            # 状态图标
            if count > 0:
                status_icon = "[green]✅[/]"
                status_color = "green"
            else:
                # 看 effective kind
                if kind in ["env", "models.json"]:
                    status_icon = "[green]✅[/]"
                    status_color = "green"
                else:
                    status_icon = "[dim]⬜[/]"
                    status_color = "dim"
            
            # 类型
            type_label = kind
            if kind == "profiles":
                oauth_count = profiles.get("oauth", 0)
                apikey_count = profiles.get("apiKey", 0)
                if oauth_count > 0 and apikey_count > 0:
                    type_label = "OAuth+API Key"
                elif oauth_count > 0:
                    type_label = "OAuth"
                elif apikey_count > 0:
                    type_label = "API Key"
            elif kind == "env":
                type_label = "环境变量"
            elif kind == "models.json":
                type_label = "models.json"
            
            # 详情（安全处理：不暴露 key）
            detail = ""
            labels = profiles.get("labels", [])
            if labels:
                # 优先显示 labels（通常是安全的账号信息）
                detail = ", ".join(labels[:1])
            else:
                # 如果没有 labels，只显示类型，不显示可能包含 key 的 detail
                kind = effective.get("kind", "")
                if kind == "env":
                    detail = "环境变量已配置"
                elif kind == "models.json":
                    detail = "models.json 已配置"
                else:
                    detail = "已配置"
            
            table.add_row(
                status_icon,
                provider,
                Text(type_label, style=status_color),
                Text(detail, style=status_color)
            )
        
        console.print(table)


def show_models_overview(status: Dict, all_models_available: Dict[str, bool]):
    """显示模型资产概览（按服务商分组，带 available 状态）"""
    console.print()
    console.print(Panel(
        Text("🤖 已激活模型", style="bold", justify="center"),
        box=box.DOUBLE
    ))
    
    # 小贴士
    console.print("  [dim]💡 ⭐=默认模型 | ✅=可用 | ❌=不可用/已下架[/]")
    console.print("  [dim]   可用状态来自 OpenClaw 官方模型目录[/]")
    console.print()
    
    default_model = status.get("defaultModel", "")
    allowed_models = status.get("allowed", [])
    
    if not allowed_models:
        console.print("  [yellow](尚未激活任何模型)[/]")
    else:
        # 按服务商分组
        models_by_provider = {}
        for m in allowed_models:
            if "/" in m:
                provider, name = m.split("/", 1)
            else:
                provider, name = "其他", m
            
            if provider not in models_by_provider:
                models_by_provider[provider] = []
            models_by_provider[provider].append((m, name))
        
        # 显示
        for provider in sorted(models_by_provider.keys()):
            console.print(f"  [bold][cyan]{provider}[/][/]:")
            for m_full, m_name in models_by_provider[provider]:
                is_default = "⭐" if m_full == default_model else "  "
                available = all_models_available.get(m_full, None)
                
                if available is True:
                    status_icon = "[green]✅[/]"
                elif available is False:
                    status_icon = "[red]❌[/]"
                else:
                    status_icon = "[dim]?[/]"
                
                if is_default == "⭐":
                    console.print(f"    {is_default} {status_icon} [green]{m_name}[/]")
                else:
                    console.print(f"    {is_default} {status_icon} {m_name}")


def show_usage_stats_with_progress(usage_output: str, usage_code: int):
    """显示用量统计（带进度条，最后加 probe 选项）"""
    console.print()
    console.print("=" * 60)
    console.print(" 📈 模型用量配额 ".center(60, "="))
    console.print("=" * 60)
    
    # 小贴士
    console.print()
    console.print("  [dim]💡 这里显示各服务商的剩余配额，来自 openclaw status --usage[/]")
    console.print()
    
    if usage_code != 0 or not usage_output:
        console.print("  [yellow](无法获取用量信息)[/]")
    else:
        # 解析用量统计
        in_usage_section = False
        current_provider = None
        usage_data = []
        
        for line in usage_output.split("\n"):
            if "用量统计" in line or "Usage:" in line:
                in_usage_section = True
                continue
            if in_usage_section:
                if line.strip() == "" and usage_data:
                    break
                if line.startswith("FAQ:") or line.startswith("Troubleshooting:"):
                    break
                
                line_stripped = line.strip()
                if not line_stripped:
                    continue
                
                # 判断是否是 provider 行
                if (
                    line_stripped 
                    and not line_stripped.startswith((" ", "-", "•"))
                    and not any(x in line_stripped.lower() for x in ["left", "resets", "tokens", "monthly", "day", "5h"])
                ):
                    current_provider = line_stripped.rstrip(":")
                    continue
                
                # 判断是否是模型/配额行
                if current_provider and (":" in line_stripped or "left" in line_stripped or "%" in line_stripped):
                    usage_data.append((current_provider, line_stripped))
        
        if not usage_data:
            # 如果没解析出来，就直接打印原始输出
            in_usage_section = False
            usage_lines = []
            for line in usage_output.split("\n"):
                if "用量统计" in line or "Usage:" in line:
                    in_usage_section = True
                    continue
                if in_usage_section:
                    if line.strip() == "" and usage_lines:
                        break
                    if line.startswith("FAQ:") or line.startswith("Troubleshooting:"):
                        break
                    if line.strip():
                        usage_lines.append(line)
            
            if usage_lines:
                for line in usage_lines:
                    console.print(f"  {line}")
            else:
                console.print("  [yellow](未获取到用量信息)[/]")
        else:
            # 按 provider 分组显示，带进度条
            by_provider = defaultdict(list)
            for provider, line in usage_data:
                by_provider[provider].append(line)
            
            for provider in sorted(by_provider.keys()):
                console.print()
                console.print(f"  [bold][cyan]{provider}[/][/]")
                
                for line in by_provider[provider]:
                    # 尝试提取百分比
                    percent = None
                    if "%" in line:
                        match = re.search(r'(\d+)%', line)
                        if match:
                            percent = int(match.group(1))
                    
                    if percent is not None:
                        # 显示进度条
                        color = "green" if percent >= 50 else "yellow" if percent >= 20 else "red"
                        
                        bar_len = 20
                        filled = "█" * (percent // (100 // bar_len))
                        empty = "░" * (bar_len - percent // (100 // bar_len))
                        bar = f"[{color}]{filled}[/{color}][dim]{empty}[/]"
                        console.print(f"    {line.split(':')[0]}: [{color}]{bar}[/] {percent}%")
                    else:
                        console.print(f"    {line}")
    
    # 加 probe 选项
    console.print()
    console.print("=" * 60)
    console.print()
    console.print("[cyan]P[/] 探测账号 Key 可用性 (慢，需几秒)")
    console.print("[cyan]0[/] 返回")
    console.print()
    console.print("  [dim]💡 提示：不是所有服务商都支持用量查询[/]")
    console.print()
    
    # 接受大小写 P/0
    choice = Prompt.ask("[bold green]>[/]", default="0").strip().lower()
    while choice not in ["0", "p", ""]:
        choice = Prompt.ask("[bold green]>[/]", default="0").strip().lower()
    
    if choice == "p":
        probe_auth_status()
    elif choice == "0" or choice == "":
        return


def probe_auth_status():
    """探测账号 Key 可用性（调用 openclaw models status --probe）"""
    console.clear()
    console.print()
    console.print(Panel(
        Text("🔍 探测账号 Key 可用性", style="bold", justify="center"),
        box=box.DOUBLE
    ))
    
    console.print()
    console.print("  [yellow]⏳ 正在探测，可能需要几秒...[/]")
    console.print()
    
    try:
        # 调用 probe (去掉 --plain，因为 --probe 和 --plain 不能一起用)
        stdout, stderr, code = run_cli(["models", "status", "--probe"])
        
        console.clear()
        console.print()
        console.print(Panel(
            Text("🔍 探测结果", style="bold", justify="center"),
            box=box.DOUBLE
        ))
        
        console.print()
        if code == 0 and stdout:
            for line in stdout.split("\n"):
                console.print(f"  {line}")
        else:
            console.print("  [yellow](无探测结果)[/]")
            if stderr:
                console.print(f"  [dim]详情: {stderr}[/]")
    
    except Exception as e:
        console.print(f"\n[bold red]❌ 探测失败: {e}[/]")
    
    console.print()
    safe_input("[dim]按回车键返回...[/]")


if __name__ == "__main__":
    show_health_dashboard()
