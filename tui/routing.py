"""
任务指派 (Routing) 模块 - 全局默认模型、备选链、子 Agent 策略
完全对齐 OpenClaw 官方 CLI 实现
优化版：模型按服务商分组、小贴士、错误提示友好化
"""
import json
from typing import List, Optional
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich.prompt import Prompt, Confirm
from rich import box

from core import config, run_cli, run_cli_json, OPENCLAW_BIN

console = Console()


def safe_safe_input(prompt=""):
    try:
        return safe_input(prompt)
    except (EOFError, KeyboardInterrupt):
        return ""



def menu_routing():
    """任务指派主菜单"""
    while True:
        console.clear()
        console.print()
        console.print("[bold cyan]========== 🤖 任务指派 (Routing) ==========[/]")
        console.print()
        
        # 小贴士
        console.print(Panel(
            Text("💡 在这里设置你的默认模型和备选链，OpenClaw 会自动切换", 
                 style="dim", justify="center"),
            box=box.ROUNDED,
            border_style="blue"
        ))
        
        # 获取当前状态
        with console.status("[yellow]⏳ 正在获取当前状态...[/]"):
            default_model = get_default_model()
            fallbacks = get_fallbacks()
            sub_status = config.get_subagent_status()
        
        # 显示当前配置
        console.print()
        console.print(Panel(
            Text("当前配置", style="bold", justify="center"),
            box=box.DOUBLE
        ))
        
        console.print()
        if default_model:
            console.print(f"  [bold]🌟 首选模型:[/] [green]{default_model}[/]")
        else:
            console.print(f"  [bold]🌟 首选模型:[/] [yellow](未设置)[/]")
        
        if fallbacks:
            console.print(f"  [bold]🔄 备选链:[/] [cyan]{' → '.join(fallbacks)}[/]")
        else:
            console.print(f"  [bold]🔄 备选链:[/] [dim](未设置)[/]")
        
        sub_str = "[green]✅ 已启用[/]" if sub_status["enabled"] else "[red]❌ 已禁用[/]"
        console.print(f"  [bold]👥 子 Agent:[/] {sub_str} (并发上限: {sub_status['maxConcurrent']})")
        
        console.print()
        console.print("[bold]操作:[/]")
        console.print("  [cyan]1[/] 设置首选模型")
        console.print("  [cyan]2[/] 管理备选链")
        console.print("  [cyan]3[/] 子 Agent 策略")
        console.print("  [cyan]0[/] 返回")
        console.print()
        
        # 接受大小写
        choice = Prompt.ask("[bold green]>[/]", default="0").strip().lower()
        while choice not in ["0", "1", "2", "3"]:
            choice = Prompt.ask("[bold green]>[/]", default="0").strip().lower()
        
        if choice == "0":
            break
        elif choice == "1":
            set_default_model_menu()
        elif choice == "2":
            manage_fallbacks_menu()
        elif choice == "3":
            subagent_settings_menu()


def get_default_model() -> Optional[str]:
    """获取当前默认模型（使用 CLI）"""
    try:
        data = run_cli_json(["models", "status"])
        if "error" not in data:
            return data.get("defaultModel")
    except Exception:
        pass
    return None


def get_fallbacks() -> List[str]:
    """获取当前备选链（使用 CLI）"""
    try:
        stdout, stderr, code = run_cli(["models", "fallbacks", "list", "--json"])
        if code == 0 and stdout:
            data = json.loads(stdout)
            return data.get("fallbacks", [])
    except Exception:
        pass
    return []


def set_default_model_menu():
    """设置首选模型菜单"""
    while True:
        console.clear()
        console.print(Panel(
            Text("🌟 设置首选模型", style="bold cyan", justify="center"),
            box=box.DOUBLE
        ))
        
        # 小贴士
        console.print()
        console.print("  [dim]💡 首选模型是 OpenClaw 优先使用的模型[/]")
        console.print()
        
        # 获取所有可用模型
        try:
            config.reload()
            all_models = config.get_all_models_flat()
        except Exception as e:
            console.print(f"\n[bold red]❌ 获取模型列表失败: {e}[/]")
            safe_input("\n按回车键继续...")
            return
        
        if not all_models:
            console.print("\n[yellow]⚠️ 资源库中无可用模型，请先在「资源库」中激活模型[/]")
            safe_input("\n按回车键继续...")
            return
        
        console.print()
        console.print("[bold]可选模型（按服务商分组）:[/]")
        console.print()
        
        # 按服务商分组
        from collections import defaultdict
        models_by_provider = defaultdict(list)
        for i, m in enumerate(all_models, 1):
            if "/" in m['full_name']:
                provider = m['full_name'].split("/", 1)[0]
            else:
                provider = "其他"
            models_by_provider[provider].append((i, m))
        
        # 显示
        for provider in sorted(models_by_provider.keys()):
            console.print(f"  [bold][cyan]{provider}[/][/]:")
            for idx, m in models_by_provider[provider]:
                console.print(f"    [{idx}] {m['display']}")
        
        console.print()
        console.print("[cyan]0[/] 返回")
        console.print()
        
        choices = ["0"] + [str(i) for i in range(1, len(all_models) + 1)]
        choice = Prompt.ask("[bold green]>[/]", choices=choices, default="0")
        
        if choice == "0":
            break
        elif choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(all_models):
                model = all_models[idx]['full_name']
                set_default_model(model)


def set_default_model(model: str):
    """设置默认模型（使用 CLI，错误提示友好化）"""
    console.print(f"\n[yellow]⏳ 正在设置首选模型: {model}...[/]")
    try:
        # 先手动备份配置
        config.reload()
        backup_path = config.backup()
        if backup_path:
            console.print(f"  [dim]💡 已备份配置到: {backup_path}[/]")
        
        stdout, stderr, code = run_cli(["models", "set", model])
        
        if code == 0:
            console.print(f"\n[green]✅ 已设置首选模型: {model}[/]")
            console.print("\n[dim]💡 此更改热生效，无需重启服务[/]")
        else:
            console.print(f"\n[bold red]❌ 设置失败[/]")
            if stderr:
                console.print(f"  [dim]详情: {stderr}[/]")
    except Exception as e:
        console.print(f"\n[bold red]❌ 设置失败: {e}[/]")
    
        safe_input("\n按回车键继续...")


def manage_fallbacks_menu():
    """管理备选链菜单"""
    while True:
        console.clear()
        console.print(Panel(
            Text("🔄 管理备选链", style="bold cyan", justify="center"),
            box=box.DOUBLE
        ))
        
        # 小贴士
        console.print()
        console.print("  [dim]💡 备选链是当首选模型不可用时，OpenClaw 会依次尝试的模型[/]")
        console.print("  [dim]   支持多层备选：首选 → 备选1 → 备选2 → ...[/]")
        console.print("  [dim]⚠️  目前 OpenClaw 官方 CLI 仅支持追加到末尾，暂不支持插入或重新排序[/]")
        console.print()
        
        try:
            fallbacks = get_fallbacks()
        except Exception as e:
            console.print(f"\n[bold red]❌ 获取备选链失败: {e}[/]")
            safe_input("\n按回车键继续...")
            return
        
        console.print()
        if fallbacks:
            console.print("[bold]当前备选链:[/]")
            table = Table(box=box.SIMPLE)
            table.add_column("顺序", style="cyan", width=6)
            table.add_column("模型", style="bold")
            
            for i, model in enumerate(fallbacks, 1):
                table.add_row(f"#{i}", model)
            
            console.print(table)
        else:
            console.print("[bold]当前备选链:[/] [yellow](未设置)[/]")
        
        console.print()
        console.print("[bold]操作:[/]")
        console.print("  [cyan]1[/] 添加备选模型")
        console.print("  [cyan]2[/] 移除备选模型")
        console.print("  [cyan]3[/] 清空备选链")
        console.print("  [cyan]0[/] 返回")
        console.print()
        
        choice = Prompt.ask("[bold green]>[/]", choices=["0", "1", "2", "3"], default="0")
        
        if choice == "0":
            break
        elif choice == "1":
            add_fallback_menu()
        elif choice == "2":
            remove_fallback_menu()
        elif choice == "3":
            clear_fallbacks_menu()


def add_fallback_menu():
    """添加备选模型菜单"""
    while True:
        console.clear()
        console.print(Panel(
            Text("➕ 添加备选模型", style="bold cyan", justify="center"),
            box=box.DOUBLE
        ))
        
        try:
            # 获取所有可用模型
            config.reload()
            all_models = config.get_all_models_flat()
            current_fallbacks = set(get_fallbacks())
            
            # 过滤掉已在备选链中的模型
            available_models = [m for m in all_models if m['full_name'] not in current_fallbacks]
        except Exception as e:
            console.print(f"\n[bold red]❌ 获取模型列表失败: {e}[/]")
            safe_input("\n按回车键继续...")
            return
        
        if not available_models:
            console.print("\n[yellow]⚠️ 没有更多可用模型可添加[/]")
            safe_input("\n按回车键继续...")
            return
        
        console.print()
        console.print("[bold]可选模型（按服务商分组）:[/]")
        console.print()
        
        # 按服务商分组
        from collections import defaultdict
        models_by_provider = defaultdict(list)
        for i, m in enumerate(available_models, 1):
            if "/" in m['full_name']:
                provider = m['full_name'].split("/", 1)[0]
            else:
                provider = "其他"
            models_by_provider[provider].append((i, m))
        
        # 显示
        for provider in sorted(models_by_provider.keys()):
            console.print(f"  [bold][cyan]{provider}[/][/]:")
            for idx, m in models_by_provider[provider]:
                console.print(f"    [{idx}] {m['display']}")
        
        console.print()
        console.print("[cyan]0[/] 返回")
        console.print()
        
        choices = ["0"] + [str(i) for i in range(1, len(available_models) + 1)]
        choice = Prompt.ask("[bold green]>[/]", choices=choices, default="0")
        
        if choice == "0":
            break
        elif choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(available_models):
                model = available_models[idx]['full_name']
                add_fallback(model)
                break


def add_fallback(model: str):
    """添加备选模型（使用 CLI，错误提示友好化）"""
    console.print(f"\n[yellow]⏳ 正在添加备选模型: {model}...[/]")
    try:
        # 先手动备份配置
        config.reload()
        backup_path = config.backup()
        if backup_path:
            console.print(f"  [dim]💡 已备份配置到: {backup_path}[/]")
        
        stdout, stderr, code = run_cli(["models", "fallbacks", "add", model])
        
        if code == 0:
            console.print(f"\n[green]✅ 已添加备选模型: {model}[/]")
            console.print("\n[dim]💡 此更改热生效，无需重启服务[/]")
        else:
            console.print(f"\n[bold red]❌ 添加失败[/]")
            if stderr:
                console.print(f"  [dim]详情: {stderr}[/]")
    except Exception as e:
        console.print(f"\n[bold red]❌ 添加失败: {e}[/]")
    
        safe_input("\n按回车键继续...")


def remove_fallback_menu():
    """移除备选模型菜单"""
    try:
        fallbacks = get_fallbacks()
    except Exception as e:
        console.print(f"\n[bold red]❌ 获取备选链失败: {e}[/]")
        safe_input("\n按回车键继续...")
        return
    
    if not fallbacks:
        console.print("\n[yellow]⚠️ 备选链为空[/]")
        safe_input("\n按回车键继续...")
        return
    
    while True:
        console.clear()
        console.print(Panel(
            Text("➖ 移除备选模型", style="bold cyan", justify="center"),
            box=box.DOUBLE
        ))
        
        console.print()
        console.print("[bold]当前备选链:[/]")
        
        table = Table(box=box.SIMPLE)
        table.add_column("编号", style="cyan", width=4)
        table.add_column("模型", style="bold")
        
        for i, model in enumerate(fallbacks, 1):
            table.add_row(str(i), model)
        
        console.print(table)
        
        console.print()
        console.print("[cyan]0[/] 返回")
        console.print()
        
        choices = ["0"] + [str(i) for i in range(1, len(fallbacks) + 1)]
        choice = Prompt.ask("[bold green]>[/]", choices=choices, default="0")
        
        if choice == "0":
            break
        elif choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(fallbacks):
                model = fallbacks[idx]
                remove_fallback(model)
                break


def remove_fallback(model: str):
    """移除备选模型（使用 CLI，错误提示友好化）"""
    console.print(f"\n[yellow]⏳ 正在移除备选模型: {model}...[/]")
    try:
        # 先手动备份配置
        config.reload()
        backup_path = config.backup()
        if backup_path:
            console.print(f"  [dim]💡 已备份配置到: {backup_path}[/]")
        
        stdout, stderr, code = run_cli(["models", "fallbacks", "remove", model])
        
        if code == 0:
            console.print(f"\n[green]✅ 已移除备选模型: {model}[/]")
            console.print("\n[dim]💡 此更改热生效，无需重启服务[/]")
        else:
            console.print(f"\n[bold red]❌ 移除失败[/]")
            if stderr:
                console.print(f"  [dim]详情: {stderr}[/]")
    except Exception as e:
        console.print(f"\n[bold red]❌ 移除失败: {e}[/]")
    
        safe_input("\n按回车键继续...")


def clear_fallbacks_menu():
    """清空备选链菜单（错误提示友好化）"""
    if not Confirm.ask("[bold red]确定要清空所有备选模型?[/]", default=False):
        return
    
    console.print("\n[yellow]⏳ 正在清空备选链...[/]")
    try:
        # 先手动备份配置
        config.reload()
        backup_path = config.backup()
        if backup_path:
            console.print(f"  [dim]💡 已备份配置到: {backup_path}[/]")
        
        stdout, stderr, code = run_cli(["models", "fallbacks", "clear"])
        
        if code == 0:
            console.print("\n[green]✅ 已清空备选链[/]")
            console.print("\n[dim]💡 此更改热生效，无需重启服务[/]")
        else:
            console.print(f"\n[bold red]❌ 清空失败[/]")
            if stderr:
                console.print(f"  [dim]详情: {stderr}[/]")
    except Exception as e:
        console.print(f"\n[bold red]❌ 清空失败: {e}[/]")
    
        safe_input("\n按回车键继续...")


def subagent_settings_menu():
    """子 Agent 策略菜单（小贴士、错误提示友好化）"""
    while True:
        console.clear()
        console.print(Panel(
            Text("👥 子 Agent 全局策略", style="bold cyan", justify="center"),
            box=box.DOUBLE
        ))
        
        # 小贴士
        console.print()
        console.print("  [dim]💡 子 Agent 可以帮你并行处理多个任务[/]")
        console.print()
        
        try:
            config.reload()
            status = config.get_subagent_status()
        except Exception as e:
            console.print(f"\n[bold red]❌ 获取子 Agent 状态失败: {e}[/]")
            safe_input("\n按回车键继续...")
            return
        
        enabled_str = "[green]✅ 已启用[/]" if status["enabled"] else "[red]❌ 已禁用[/]"
        allow_str = ", ".join(status["allowAgents"]) if status["allowAgents"] else "[dim]无 (禁用状态)[/]"
        
        console.print()
        console.print(f"  [bold]1. 开关状态:[/] {enabled_str}")
        console.print(f"  [bold]2. 最大并发:[/] {status['maxConcurrent']}")
        console.print(f"  [bold]3. 白名单:[/] {allow_str}")
        
        console.print()
        console.print("[bold]操作:[/]")
        console.print("  [cyan]1[/] 切换开关")
        console.print("  [cyan]2[/] 设置最大并发")
        console.print("  [cyan]3[/] 设置白名单")
        console.print("  [cyan]0[/] 返回")
        console.print()
        
        choice = Prompt.ask("[bold green]>[/]", choices=["0", "1", "2", "3"], default="0")
        
        if choice == "0":
            break
        elif choice == "1":
            try:
                if status["enabled"]:
                    config.update_subagent_global(allow_agents=[])
                    console.print("\n[green]✅ 已禁用子 Agent[/]")
                else:
                    config.update_subagent_global(allow_agents=["*"])
                    console.print("\n[green]✅ 已启用子 Agent (允许所有)[/]")
                console.print("\n[yellow]⚠️ 需要重启服务后生效[/]")
            except Exception as e:
                console.print(f"\n[bold red]❌ 操作失败: {e}[/]")
                safe_input("\n按回车键继续...")
        elif choice == "2":
            num = Prompt.ask("[bold]请输入新的最大并发数 [1-10][/]", default=str(status["maxConcurrent"]))
            if num.isdigit() and 1 <= int(num) <= 10:
                try:
                    config.update_subagent_global(max_concurrent=int(num))
                    console.print(f"\n[green]✅ 已设置为 {num}[/]")
                    console.print("\n[yellow]⚠️ 需要重启服务后生效[/]")
                except Exception as e:
                    console.print(f"\n[bold red]❌ 设置失败: {e}[/]")
            else:
                console.print("\n[bold red]❌ 无效输入[/]")
                safe_input("\n按回车键继续...")
        elif choice == "3":
            console.print("\n[dim]- 输入 '*' 允许所有 agent[/]")
            console.print("[dim]- 输入具体 agent ID，用逗号分隔 (如: worker1,worker2)[/]")
            console.print("[dim]- 输入空白清空白名单 (禁用)[/]")
            raw = Prompt.ask("\n[bold]请输入白名单[/]", default="")
            raw = raw.strip()
            if raw == "": 
                allow_list = []
            elif raw == "*": 
                allow_list = ["*"]
            else: 
                allow_list = [x.strip() for x in raw.split(",") if x.strip()]
            try:
                config.update_subagent_global(allow_agents=allow_list)
                console.print(f"\n[green]✅ 白名单已更新为: {allow_list}[/]")
                console.print("\n[yellow]⚠️ 需要重启服务后生效[/]")
            except Exception as e:
                console.print(f"\n[bold red]❌ 设置失败: {e}[/]")
                safe_input("\n按回车键继续...")


if __name__ == "__main__":
    menu_routing()
