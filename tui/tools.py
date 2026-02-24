"""
工具配置模块 - 搜索服务（官方+第三方）、向量化配置
增强版：拆分成搜索服务管理，支持 3 个官方搜索 + 第三方搜索
"""
import os
import getpass
from typing import Dict
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
    get_memory_search_config,
    clear_memory_search_config,
    write_env_template,
    set_env_key,
    check_existing_key,
    read_env_keys,
    DEFAULT_ENV_PATH,
    DEFAULT_ENV_TEMPLATE_PATH
)

console = Console()


def safe_safe_input(prompt=""):
    try:
        return safe_input(prompt)
    except (EOFError, KeyboardInterrupt):
        return ""


# 默认官方搜索服务列表（3个）
DEFAULT_OFFICIAL_SEARCH_PROVIDERS = [
    "brave",
    "perplexity",
    "grok",
]

# 官方搜索服务的 env key 映射
OFFICIAL_SEARCH_KEYS = {
    "brave": "BRAVE_API_KEY",
    "perplexity": "PERPLEXITY_API_KEY",
    "grok": "GROK_API_KEY",
}


def get_official_search_providers() -> list:
    """
    获取官方搜索服务列表（优先从配置读取，否则用默认列表）
    未来可扩展：自动从 OpenClaw 官方检测
    """
    # 未来可扩展：这里可以自动从 OpenClaw 官方检测
    # 暂时先用默认列表 + 配置扩展
    config.reload()
    custom_providers = config.data.get("easyclaw", {}).get("searchProviders", [])
    return list(set(DEFAULT_OFFICIAL_SEARCH_PROVIDERS + custom_providers))


def menu_tools():
    """工具配置主菜单（增强版）"""
    while True:
        console.clear()
        console.print()
        console.print("[bold cyan]========== 🧭 工具配置 ==========[/]")
        console.print()
        
        console.print("[bold]功能:[/]")
        console.print("  [cyan]1[/] 搜索服务管理 (官方+第三方)")
        console.print("  [cyan]2[/] 向量化/记忆检索配置 (Embeddings)")
        console.print("  [cyan]0[/] 返回")
        console.print()
        
        choice = Prompt.ask("[bold green]>[/]", choices=["0", "1", "2"], default="0").strip().lower()
        while choice not in ["0", "1", "2"]:
            choice = Prompt.ask("[bold green]>[/]", choices=["0", "1", "2"], default="0").strip().lower()
        
        if choice == "0":
            break
        elif choice == "1":
            menu_search_services()
        elif choice == "2":
            menu_embeddings()


def menu_search_services():
    """搜索服务管理主菜单"""
    while True:
        console.clear()
        console.print(Panel(
            Text("🔍 搜索服务管理", style="bold cyan", justify="center"),
            box=box.DOUBLE
        ))
        
        # 获取当前配置
        config.reload()
        search_cfg = config.data.get("tools", {}).get("web", {}).get("search", {})
        default_provider = search_cfg.get("provider", "brave")
        
        console.print()
        console.print(f"[bold]当前默认搜索服务:[/] {default_provider}")
        
        console.print()
        console.print("[bold]操作:[/]")
        console.print("  [cyan]1[/] 官方搜索服务配置")
        console.print("  [cyan]2[/] 第三方搜索服务配置")
        console.print("  [cyan]3[/] 选择默认搜索服务")
        console.print("  [cyan]0[/] 返回")
        console.print()
        
        choice = Prompt.ask("[bold green]>[/]", choices=["0", "1", "2", "3"], default="0").strip().lower()
        while choice not in ["0", "1", "2", "3"]:
            choice = Prompt.ask("[bold green]>[/]", choices=["0", "1", "2", "3"], default="0").strip().lower()
        
        if choice == "0":
            break
        elif choice == "1":
            menu_official_search()
        elif choice == "2":
            menu_thirdparty_search()
        elif choice == "3":
            select_default_search_provider_enhanced()


def menu_official_search():
    """官方搜索服务配置"""
    while True:
        console.clear()
        console.print(Panel(
            Text("🔍 官方搜索服务配置", style="bold cyan", justify="center"),
            box=box.DOUBLE
        ))
        
        providers = get_official_search_providers()
        
        console.print()
        console.print("[bold]官方搜索服务:[/]")
        for i, provider in enumerate(providers, 1):
            console.print(f"  [cyan]{i}[/] {provider}")
        
        console.print("  [cyan]A[/] 添加自定义官方搜索服务")
        console.print("  [cyan]0[/] 返回")
        console.print()
        
        choices = ["0", "a"] + [str(i) for i in range(1, len(providers) + 1)]
        choice = Prompt.ask("[bold green]>[/]", choices=choices, default="0").strip().lower()
        while choice not in choices:
            choice = Prompt.ask("[bold green]>[/]", choices=choices, default="0").strip().lower()
        
        if choice == "0":
            break
        elif choice == "a":
            add_custom_official_provider()
        elif choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(providers):
                provider = providers[idx]
                configure_official_search(provider)


def add_custom_official_provider():
    """添加自定义官方搜索服务（用于官方新增服务时手动添加）"""
    console.clear()
    console.print(Panel(
        Text("➕ 添加自定义官方搜索服务", style="bold cyan", justify="center"),
        box=box.DOUBLE
    ))
    
    console.print()
    console.print("  [dim]💡 用于 OpenClaw 官方新增搜索服务时手动添加[/]")
    console.print()
    
    provider = Prompt.ask("[bold]请输入官方搜索服务名称[/]").strip()
    if not provider:
        console.print("\n[yellow]⚠️  服务名称不能为空[/]")
        safe_input("\n按回车键继续...")
        return
    
    # 备份
    config.reload()
    backup_path = config.backup()
    if backup_path:
        console.print(f"\n  [dim]💡 已备份配置到: {backup_path}[/]")
    
    # 更新配置
    if "easyclaw" not in config.data:
        config.data["easyclaw"] = {}
    if "searchProviders" not in config.data["easyclaw"]:
        config.data["easyclaw"]["searchProviders"] = []
    
    if provider not in config.data["easyclaw"]["searchProviders"]:
        config.data["easyclaw"]["searchProviders"].append(provider)
        config.save()
        console.print(f"\n[green]✅ 已添加官方搜索服务: {provider}[/]")
    else:
        console.print(f"\n[yellow]⚠️  官方搜索服务已存在: {provider}[/]")
    
        safe_input("\n按回车键继续...")


def configure_official_search(provider: str):
    """配置单个官方搜索服务"""
    while True:
        console.clear()
        console.print(Panel(
            Text(f"🔍 配置官方搜索服务: {provider}", style="bold cyan", justify="center"),
            box=box.DOUBLE
        ))
        
        # 获取当前配置
        config.reload()
        search_cfg = config.data.get("tools", {}).get("web", {}).get("search", {})
        
        console.print()
        console.print("[bold]操作:[/]")
        console.print("  [cyan]1[/] 设置 API Key")
        
        if provider == "perplexity":
            console.print("  [cyan]2[/] 设置 Base URL")
            console.print("  [cyan]3[/] 设置 Model")
        
        console.print("  [cyan]0[/] 返回")
        console.print()
        
        choices = ["0", "1"]
        if provider == "perplexity":
            choices += ["2", "3"]
        
        choice = Prompt.ask("[bold green]>[/]", choices=choices, default="0").strip().lower()
        while choice not in choices:
            choice = Prompt.ask("[bold green]>[/]", choices=choices, default="0").strip().lower()
        
        if choice == "0":
            break
        elif choice == "1":
            # 设置 API Key
            key_name = OFFICIAL_SEARCH_KEYS.get(provider, f"{provider.upper()}_API_KEY")
            choose_or_prompt_key(key_name, provider)
        elif choice == "2" and provider == "perplexity":
            # 设置 Base URL
            set_perplexity_baseurl()
        elif choice == "3" and provider == "perplexity":
            # 设置 Model
            set_perplexity_model()


def set_perplexity_baseurl():
    """设置 Perplexity Base URL"""
    console.clear()
    console.print(Panel(
        Text("🌐 设置 Perplexity Base URL", style="bold cyan", justify="center"),
        box=box.DOUBLE
    ))
    
    config.reload()
    search_cfg = config.data.get("tools", {}).get("web", {}).get("search", {})
    perplexity_cfg = search_cfg.get("perplexity", {})
    current = perplexity_cfg.get("baseUrl", "")
    
    console.print()
    console.print(f"  [dim]当前值: {current or '(未设置)'}[/]")
    console.print()
    
    new_url = Prompt.ask("[bold]请输入 Base URL[/]", default=current).strip()
    
    # 备份
    config.reload()
    backup_path = config.backup()
    if backup_path:
        console.print(f"\n  [dim]💡 已备份配置到: {backup_path}[/]")
    
    # 更新
    if "tools" not in config.data:
        config.data["tools"] = {}
    if "web" not in config.data["tools"]:
        config.data["tools"]["web"] = {}
    if "search" not in config.data["tools"]["web"]:
        config.data["tools"]["web"]["search"] = {}
    if "perplexity" not in config.data["tools"]["web"]["search"]:
        config.data["tools"]["web"]["search"]["perplexity"] = {}
    
    config.data["tools"]["web"]["search"]["perplexity"]["baseUrl"] = new_url
    config.save()
    
    console.print(f"\n[green]✅ 已更新 Base URL: {new_url}[/]")
    safe_input("\n按回车键继续...")


def set_perplexity_model():
    """设置 Perplexity Model"""
    console.clear()
    console.print(Panel(
        Text("🤖 设置 Perplexity Model", style="bold cyan", justify="center"),
        box=box.DOUBLE
    ))
    
    config.reload()
    search_cfg = config.data.get("tools", {}).get("web", {}).get("search", {})
    perplexity_cfg = search_cfg.get("perplexity", {})
    current = perplexity_cfg.get("model", "")
    
    console.print()
    console.print(f"  [dim]当前值: {current or '(未设置)'}[/]")
    console.print()
    
    new_model = Prompt.ask("[bold]请输入 Model[/]", default=current).strip()
    
    # 备份
    config.reload()
    backup_path = config.backup()
    if backup_path:
        console.print(f"\n  [dim]💡 已备份配置到: {backup_path}[/]")
    
    # 更新
    if "tools" not in config.data:
        config.data["tools"] = {}
    if "web" not in config.data["tools"]:
        config.data["tools"]["web"] = {}
    if "search" not in config.data["tools"]["web"]:
        config.data["tools"]["web"]["search"] = {}
    if "perplexity" not in config.data["tools"]["web"]["search"]:
        config.data["tools"]["web"]["search"]["perplexity"] = {}
    
    config.data["tools"]["web"]["search"]["perplexity"]["model"] = new_model
    config.save()
    
    console.print(f"\n[green]✅ 已更新 Model: {new_model}[/]")
    safe_input("\n按回车键继续...")


def menu_thirdparty_search():
    """第三方搜索服务配置"""
    while True:
        console.clear()
        console.print(Panel(
            Text("🔍 第三方搜索服务配置", style="bold cyan", justify="center"),
            box=box.DOUBLE
        ))
        
        # 预留：第三方搜索服务配置
        console.print()
        console.print("[yellow]⚠️  第三方搜索服务配置功能开发中...[/]")
        console.print()
        
        console.print("[cyan]0[/] 返回")
        console.print()
        
        choice = Prompt.ask("[bold green]>[/]", choices=["0"], default="0")
        if choice == "0":
            break


def select_default_search_provider_enhanced():
    """选择默认搜索 provider（增强版）"""
    while True:
        console.clear()
        console.print(Panel(
            Text("选择默认搜索服务", style="bold cyan", justify="center"),
            box=box.DOUBLE
        ))
        
        providers = get_official_search_providers()
        
        console.print()
        console.print("[bold]选项:[/]")
        for i, provider in enumerate(providers, 1):
            console.print(f"  [cyan]{i}[/] {provider}")
        
        console.print("  [cyan]0[/] 返回")
        console.print()
        
        choices = ["0"] + [str(i) for i in range(1, len(providers) + 1)]
        choice = Prompt.ask("[bold green]>[/]", choices=choices, default="0").strip().lower()
        while choice not in choices:
            choice = Prompt.ask("[bold green]>[/]", choices=choices, default="0").strip().lower()
        
        if choice == "0":
            break
        elif choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(providers):
                provider = providers[idx]
                
                # 备份
                config.reload()
                backup_path = config.backup()
                if backup_path:
                    console.print(f"\n  [dim]💡 已备份配置到: {backup_path}[/]")
                
                # 更新
                if "tools" not in config.data:
                    config.data["tools"] = {}
                if "web" not in config.data["tools"]:
                    config.data["tools"]["web"] = {}
                if "search" not in config.data["tools"]["web"]:
                    config.data["tools"]["web"]["search"] = {}
                
                config.data["tools"]["web"]["search"]["provider"] = provider
                config.save()
                
                console.print(f"\n[green]✅ 默认搜索服务已切换为: {provider}[/]")
                console.print("\n[yellow]⚠️ 建议重启服务后生效[/]")
                safe_input("\n按回车键继续...")
                break


def menu_embeddings():
    """向量化配置"""
    while True:
        console.clear()
        console.print(Panel(
            Text("🔍 向量化/记忆检索配置", style="bold cyan", justify="center"),
            box=box.DOUBLE
        ))
        
        ms = get_memory_search_config()
        provider = ms.get("provider", "auto")
        local_path = (ms.get("local") or {}).get("modelPath")
        remote = ms.get("remote") or {}
        remote_base = remote.get("baseUrl")
        
        console.print()
        console.print(f"[bold]当前模式:[/] {provider}")
        if local_path:
            console.print(f"[bold]本地模型:[/] {local_path}")
        if remote_base:
            console.print(f"[bold]自定义端点:[/] {remote_base}")
        
        console.print()
        console.print("[bold]选项:[/]")
        console.print("  [cyan]1[/] Auto (推荐，依赖 .env)")
        console.print("  [cyan]2[/] OpenAI")
        console.print("  [cyan]3[/] Gemini")
        console.print("  [cyan]4[/] Voyage")
        console.print("  [cyan]5[/] Local")
        console.print("  [cyan]6[/] Custom OpenAI-compatible")
        console.print("  [cyan]T[/] 输出 .env 模板")
        console.print("  [cyan]0[/] 返回")
        console.print()
        
        choice = Prompt.ask("[bold green]>[/]", choices=["0", "1", "2", "3", "4", "5", "6", "t"], default="0").lower()
        
        if choice == "0":
            break
        elif choice == "t":
            ok = write_env_template(to_env=True)
            if ok:
                console.print(f"\n[green]✅ 模板已写入: {DEFAULT_ENV_PATH} (同时更新 {DEFAULT_ENV_TEMPLATE_PATH})[/]")
                safe_input("\n按回车键继续...")
        elif choice == "1":
            clear_memory_search_config(clear_provider=True)
            console.print("\n[green]✅ 已设置为 Auto (依赖 .env)[/]")
            console.print("\n[yellow]⚠️ 建议重启服务后生效[/]")
            safe_input("\n按回车键继续...")
        elif choice in ["2", "3", "4"]:
            provider_map = {"2": "openai", "3": "gemini", "4": "voyage"}
            key_map = {"2": "OPENAI_API_KEY", "3": "GEMINI_API_KEY", "4": "VOYAGE_API_KEY"}
            clear_memory_search_config(clear_provider=False)
            run_cli(["config", "set", "memorySearch.provider", provider_map[choice]])
            console.print(f"\n[green]✅ 已设置 provider: {provider_map[choice]}[/]")
            choose_or_prompt_key(key_map[choice], provider_map[choice])
            console.print("\n[yellow]⚠️ 建议重启服务后生效[/]")
            safe_input("\n按回车键继续...")
        elif choice == "5":
            path = Prompt.ask("[bold]请输入本地模型路径[/]")
            if path:
                if not os.path.exists(path):
                    console.print("\n[bold red]❌ 路径不存在[/]")
                    safe_input("\n按回车键继续...")
                    continue
                clear_memory_search_config(clear_provider=False)
                run_cli(["config", "set", "memorySearch.provider", "local"])
                run_cli(["config", "set", "memorySearch.local.modelPath", path])
                console.print("\n[green]✅ 已设置为 Local 模式[/]")
                console.print("\n[yellow]⚠️ 建议重启服务后生效[/]")
                safe_input("\n按回车键继续...")
        elif choice == "6":
            base_url = Prompt.ask("[bold]请输入自定义 OpenAI 兼容 Base URL[/]")
            if base_url:
                clear_memory_search_config(clear_provider=False)
                run_cli(["config", "set", "memorySearch.provider", "openai"])
                run_cli(["config", "set", "memorySearch.remote.baseUrl", base_url])
                console.print("\n[green]✅ 已设置自定义 OpenAI 兼容端点[/]")
                console.print("\n[yellow]⚠️ 请在 ~/.openclaw/.env 配置 OPENAI_API_KEY[/]")
                console.print("\n[yellow]⚠️ 建议重启服务后生效[/]")
                safe_input("\n按回车键继续...")


def choose_or_prompt_key(key_name: str, provider_name: str = None) -> bool:
    """选择使用已有 key 或输入新 key"""
    exists = check_existing_key(key_name, provider_name)
    if not exists:
        return prompt_and_set_env_key(key_name)
    console.print(f"\n[yellow]检测到已有 {key_name}[/]")
    console.print("  [cyan]1[/] 使用已有 Key")
    console.print("  [cyan]2[/] 输入新 Key (计费隔离)")
    c = Prompt.ask("\n[bold green]请选择[/]", choices=["1", "2"], default="1")
    if c == "2":
        return prompt_and_set_env_key(key_name)
    console.print("\n[green]✅ 已继续使用已有 Key[/]")
    return True


def prompt_and_set_env_key(key_name: str) -> bool:
    """提示输入并设置 env key"""
    value = getpass.getpass(f"请输入 {key_name} (输入不会显示): ").strip()
    if not value:
        console.print("\n[bold red]❌ 未输入 Key[/]")
        return False
    ok = set_env_key(key_name, value)
    if ok:
        console.print(f"\n[green]✅ 已写入 {key_name} 到 {DEFAULT_ENV_PATH}[/]")
    return ok


if __name__ == "__main__":
    menu_tools()
