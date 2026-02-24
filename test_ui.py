#!/usr/bin/env python3
"""
测试服务商列表显示 UI
"""
import json
import sys
sys.path.insert(0, '/root/.openclaw/software/easyclaw')

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich.prompt import Prompt
from rich import box

console = Console()


def fetch_provider_list():
    """从 CLI 获取支持的服务商列表"""
    from core import run_cli
    stdout, _, code = run_cli(['models', 'list', '--all', '--json'])
    if code == 0:
        try:
            data = json.loads(stdout)
            providers = set()
            for m in data.get('models', []):
                key = m.get('key', '')
                if '/' in key:
                    provider = key.split('/')[0]
                    providers.add(provider)
            return sorted(providers)
        except Exception as e:
            print(f"Error: {e}")
    return []


def test_provider_list():
    """测试服务商列表显示"""
    console.clear()
    console.print(Panel(
        Text("➕ 添加服务商 (官方支持)", style="bold cyan", justify="center"),
        box=box.DOUBLE
    ))
    console.print("\n[yellow]⏳ 正在获取 OpenClaw 支持的服务商列表...[/]")
    
    providers = fetch_provider_list()
    
    if not providers:
        console.print("\n[bold red]❌ 无法获取服务商列表，请检查网络或手动添加。[/]")
        return
    
    console.print(f"\n✅ 找到 {len(providers)} 个服务商")
    
    # 分页显示
    page_size = 15
    page = 0
    total_pages = (len(providers) - 1) // page_size + 1
    
    while True:
        console.clear()
        console.print(Panel(
            Text(f"选择服务商 - 第 {page+1}/{total_pages} 页", style="bold cyan", justify="center"),
            box=box.DOUBLE
        ))
        
        table = Table(box=box.SIMPLE)
        table.add_column("编号", style="cyan", width=4)
        table.add_column("服务商", style="bold")
        
        start = page * page_size
        end = min(start + page_size, len(providers))
        for i, p in enumerate(providers[start:end], start + 1):
            table.add_row(str(i), p)
        
        console.print(table)
        
        console.print()
        console.print("[cyan]N[/] 下一页  [cyan]P[/] 上一页  [cyan]0[/] 取消")
        
        choices = ["0", "n", "p"] + [str(i) for i in range(start + 1, end + 1)]
        choice = Prompt.ask("[bold green]>[/]", choices=choices, default="0").strip().lower()
        
        if choice == "0":
            break
        elif choice == "n" and end < len(providers):
            page += 1
        elif choice == "p" and page > 0:
            page -= 1
        elif choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(providers):
                console.print(f"\n✅ 选择了: {providers[idx]}")
                break


if __name__ == "__main__":
    try:
        test_provider_list()
    except KeyboardInterrupt:
        console.print("\n\n[bold cyan]👋 再见![/]")
