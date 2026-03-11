"""
网关设置 (Gateway) 模块 - 端口、绑定、认证、WebUI
"""
from typing import Dict
from core.utils import safe_input, pause_enter
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich.prompt import Prompt, Confirm
from rich import box

from core import run_cli, run_cli_json

console = Console()


def _run_menu_action(action, label: str):
    try:
        action()
    except KeyboardInterrupt:
        console.print(f"\n[yellow]已取消: {label}[/]")
        pause_enter()
    except EOFError:
        console.print(f"\n[yellow]输入流结束，已返回当前菜单: {label}[/]")
        pause_enter()
    except Exception as e:
        console.print(f"\n[bold red]❌ {label} 执行失败: {e}[/]")
        pause_enter()




def menu_gateway():
    """网关设置主菜单"""
    while True:
        console.clear()
        console.print()
        console.print("[bold cyan]========== 🌐 网关设置 (Gateway) ==========[/]")
        console.print()
        
        # 获取当前配置
        with console.status("[yellow]⏳ 正在获取当前配置...[/]"):
            gw = get_gateway_config()
        
        port = gw.get("port", 18789)
        bind_mode = gw.get("bind", "loopback")
        auth_mode = gw.get("auth", {}).get("mode", "token")
        trusted = gw.get("trustedProxies", [])
        ui_enabled = gw.get("controlUi", {}).get("enabled", False)
        
        # 显示当前配置
        console.print(Panel(
            Text("当前配置", style="bold", justify="center"),
            box=box.DOUBLE
        ))
        
        console.print()
        console.print(f"[bold]1. 端口 (port):[/] {port}")
        console.print(f"[bold]2. 绑定模式 (bind):[/] {bind_mode}")
        console.print(f"[bold]3. 认证模式 (auth):[/] {auth_mode}")
        console.print(f"[bold]4. 信任代理 (trustedProxies):[/] {trusted}")
        console.print(f"[bold]5. WebUI 开关:[/] {'✅ 开启' if ui_enabled else '❌ 关闭'}")
        
        console.print()
        console.print("[dim]📖 配置说明:[/]")
        console.print("  [dim]• port: Gateway 监听端口[/]")
        console.print("  [dim]• bind: loopback(仅本机) | lan(局域网) | tailnet | auto[/]")
        console.print("  [dim]• auth: token(令牌) | password(密码)[/]")
        console.print("  [dim]• trustedProxies: 反代服务器IP，信任其 X-Forwarded-For[/]")
        console.print("  [dim]• WebUI: 控制面板开关[/]")
        
        console.print()
        console.print("[bold]操作:[/]")
        console.print("  [cyan]1[/] 修改端口")
        console.print("  [cyan]2[/] 修改绑定模式")
        console.print("  [cyan]3[/] 修改认证模式")
        console.print("  [cyan]4[/] 设置信任代理")
        console.print("  [cyan]5[/] 切换 WebUI")
        console.print("  [cyan]0[/] 返回")
        console.print()
        
        choice = Prompt.ask("[bold green]>[/]", choices=["0", "1", "2", "3", "4", "5"], default="0")
        
        if choice == "0":
            break
        elif choice == "1":
            _run_menu_action(set_gateway_port, "修改端口")
        elif choice == "2":
            _run_menu_action(set_gateway_bind, "修改绑定模式")
        elif choice == "3":
            _run_menu_action(set_gateway_auth, "修改认证模式")
        elif choice == "4":
            _run_menu_action(set_trusted_proxies, "设置信任代理")
        elif choice == "5":
            _run_menu_action(set_webui_toggle, "切换 WebUI")


def get_gateway_config() -> Dict:
    """获取网关配置（使用 CLI）"""
    result = run_cli_json(["config", "get", "gateway"])
    if "error" not in result:
        return result
    return {}


def set_gateway_port():
    """设置网关端口"""
    console.clear()
    console.print(Panel(
        Text("设置网关端口", style="bold cyan", justify="center"),
        box=box.DOUBLE
    ))
    
    gw = get_gateway_config()
    current_port = gw.get("port", 18789)
    
    console.print()
    console.print(f"[bold]当前端口:[/] {current_port}")
    console.print()
    
    new_port = Prompt.ask("[bold]请输入新端口 (1024-65535)[/]", default=str(current_port))
    
    if new_port.isdigit() and 1024 <= int(new_port) <= 65535:
        console.print(f"\n[yellow]⏳ 正在设置端口: {new_port}...[/]")
        out, err, code = run_cli(["config", "set", "gateway.port", new_port])
        
        if code == 0:
            console.print(f"\n[green]✅ 端口已设置为 {new_port}[/]")
        else:
            console.print(f"\n[bold red]❌ 设置失败: {err}[/]")
        
        console.print("\n[yellow]⚠️ 需要重启服务后生效[/]")
    else:
        console.print("\n[bold red]❌ 无效端口[/]")
    
        pause_enter()


def set_gateway_bind():
    """设置绑定模式"""
    console.clear()
    console.print(Panel(
        Text("设置绑定模式", style="bold cyan", justify="center"),
        box=box.DOUBLE
    ))
    
    gw = get_gateway_config()
    current_bind = gw.get("bind", "loopback")
    
    console.print()
    console.print(f"[bold]当前绑定模式:[/] {current_bind}")
    console.print()
    console.print("[bold]可选值:[/]")
    console.print("  [cyan]1[/] loopback - 仅本机访问 (127.0.0.1)")
    console.print("  [cyan]2[/] lan      - 局域网访问 (0.0.0.0)")
    console.print("  [cyan]3[/] tailnet  - Tailscale 网络")
    console.print("  [cyan]4[/] auto     - 自动选择")
    console.print()
    
    choice = Prompt.ask("[bold green]请选择[/]", choices=["1", "2", "3", "4", "0"], default="0")
    
    if choice == "0":
        return
    
    modes = {"1": "loopback", "2": "lan", "3": "tailnet", "4": "auto"}
    if choice in modes:
        bind_mode = modes[choice]
        console.print(f"\n[yellow]⏳ 正在设置绑定模式: {bind_mode}...[/]")
        out, err, code = run_cli(["config", "set", "gateway.bind", bind_mode])
        
        if code == 0:
            console.print(f"\n[green]✅ 绑定模式已设置为 {bind_mode}[/]")
        else:
            console.print(f"\n[bold red]❌ 设置失败: {err}[/]")
        
        console.print("\n[yellow]⚠️ 需要重启服务后生效[/]")
    
        pause_enter()


def set_gateway_auth():
    """设置认证模式"""
    console.clear()
    console.print(Panel(
        Text("设置认证模式", style="bold cyan", justify="center"),
        box=box.DOUBLE
    ))
    
    gw = get_gateway_config()
    current_auth = gw.get("auth", {}).get("mode", "token")
    
    console.print()
    console.print(f"[bold]当前认证模式:[/] {current_auth}")
    console.print()
    console.print("[bold]可选值:[/]")
    console.print("  [cyan]1[/] token    - 使用令牌认证 (推荐)")
    console.print("  [cyan]2[/] password - 使用密码认证")
    console.print()
    
    choice = Prompt.ask("[bold green]请选择[/]", choices=["1", "2", "0"], default="0")
    
    if choice == "0":
        return
    
    modes = {"1": "token", "2": "password"}
    if choice in modes:
        auth_mode = modes[choice]
        console.print(f"\n[yellow]⏳ 正在设置认证模式: {auth_mode}...[/]")
        out, err, code = run_cli(["config", "set", "gateway.auth.mode", auth_mode])
        
        if code == 0:
            console.print(f"\n[green]✅ 认证模式已设置为 {auth_mode}[/]")
            
            if choice == "2":
                pwd = Prompt.ask("[bold]请输入新密码[/]", password=True)
                if pwd:
                    run_cli(["config", "set", "gateway.auth.password", pwd])
                    console.print("\n[green]✅ 密码已设置[/]")
        else:
            console.print(f"\n[bold red]❌ 设置失败: {err}[/]")
        
        console.print("\n[yellow]⚠️ 需要重启服务后生效[/]")
    
        pause_enter()


def set_trusted_proxies():
    """设置信任代理 IP"""
    console.clear()
    console.print(Panel(
        Text("设置信任代理 IP", style="bold cyan", justify="center"),
        box=box.DOUBLE
    ))
    
    # 获取当前值
    stdout, _, _ = run_cli(["config", "get", "gateway.trustedProxies"])
    
    console.print()
    console.print("[dim]💡 说明: 当使用 Nginx/Caddy 反代时，需要将反代服务器 IP 加入信任列表[/]")
    console.print("[dim]   这样 OpenClaw 才会信任 X-Forwarded-For 头中的真实客户端 IP[/]")
    console.print()
    console.print(f"[bold]当前值:[/] {stdout}")
    console.print()
    
    raw = Prompt.ask("[bold]请输入信任代理 IP (逗号分隔，留空清空)[/]", default="")
    raw = raw.strip()
    
    if raw == "":
        trusted = []
    else:
        trusted = [x.strip() for x in raw.split(",") if x.strip()]
    
    # 设置
    import json
    payload = json.dumps(trusted)
    console.print(f"\n[yellow]⏳ 正在设置信任代理: {trusted}...[/]")
    out, err, code = run_cli(["config", "set", "gateway.trustedProxies", payload, "--json"])
    
    if code == 0:
        console.print(f"\n[green]✅ 信任代理已设置为: {trusted}[/]")
    else:
        console.print(f"\n[bold red]❌ 设置失败: {err}[/]")
    
    console.print("\n[yellow]⚠️ 需要重启服务后生效[/]")
    pause_enter()


def set_webui_toggle():
    """切换 WebUI 开关"""
    console.clear()
    console.print(Panel(
        Text("切换 WebUI 开关", style="bold cyan", justify="center"),
        box=box.DOUBLE
    ))
    
    gw = get_gateway_config()
    current_enabled = gw.get("controlUi", {}).get("enabled", False)
    
    console.print()
    console.print(f"[bold]当前状态:[/] {'✅ 开启' if current_enabled else '❌ 关闭'}")
    console.print()
    
    new_state = not current_enabled
    console.print(f"[yellow]⏳ 正在切换 WebUI 到: {'开启' if new_state else '关闭'}...[/]")
    out, err, code = run_cli(["config", "set", "gateway.controlUi.enabled", "true" if new_state else "false"])
    
    if code == 0:
        console.print(f"\n[green]✅ WebUI 已{'开启' if new_state else '关闭'}[/]")
    else:
        console.print(f"\n[bold red]❌ 设置失败: {err}[/]")
    
    console.print("\n[yellow]⚠️ 需要重启服务后生效[/]")
    pause_enter()


if __name__ == "__main__":
    menu_gateway()
