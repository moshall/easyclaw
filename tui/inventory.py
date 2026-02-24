"""
资源库 (Inventory) 模块 - 服务商/账号/模型管理
优化版：和其他模块风格一致，增加删除功能、协议选择、模型管理
"""
import os
import json
import re
import urllib.request
import urllib.error
from typing import Dict, List, Optional
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
    get_models_providers,
    set_models_providers,
    sanitize_auth_profiles,
    normalize_provider_name,
    OPENCLAW_BIN,
    DEFAULT_AUTH_PROFILES_PATH,
    DEFAULT_BACKUP_DIR,
    DEFAULT_CONFIG_PATH
)
from core.write_engine import activate_model, deactivate_model, set_provider_config, clean_quoted_model_keys, is_dry_run
from core.datasource import get_official_models, get_custom_models

console = Console()


def safe_input(prompt=""):
    try:
        return input(prompt)
    except (EOFError, KeyboardInterrupt):
        return ""


def safe_safe_input(prompt=""):
    try:
        return safe_input(prompt)
    except (EOFError, KeyboardInterrupt):
        return ""


# 已知的 API Key 类型服务商映射
API_KEY_PROVIDERS = {
    "openai": "openai-api-key",
    "anthropic": "token",
    "openrouter": "openrouter-api-key",
    "gemini": "gemini-api-key",
    "google-gemini-cli": "gemini-api-key",
    "zai": "zai-api-key",
    "xiaomi": "xiaomi-api-key",
    "minimax": "minimax-api",
    "minimax-cn": "minimax-api",
    "moonshot": "moonshot-api-key",
    "kimi-coding": "kimi-code-api-key",
    "opencode": "opencode-zen",
    "groq": "token",
    "mistral": "token",
    "xai": "token",
    "cerebras": "token",
    "huggingface": "token",
}

# OAuth 服务商
OAUTH_PROVIDERS = ["google-antigravity", "github-copilot"]

# 常见 API 协议
def get_onboard_providers() -> list:
    """解析 OpenClaw onboard --help 的 auth-choice 列表"""
    stdout, _, code = run_cli(["onboard", "--help"])
    if code != 0 or not stdout:
        return []
    m = re.search(r"--auth-choice <choice>\s+Auth: (.*)", stdout)
    if not m:
        return []
    raw = m.group(1).strip()
    choices = raw.split("|")
    ignore = {"token","apiKey","custom-api-key","skip","setup-token","oauth","claude-cli","codex-cli"}
    providers = []
    for c in choices:
        if c in ignore:
            continue
        base = c
        for suf in ["-api-key-cn","-api-key","-api-lightning","-api"]:
            if base.endswith(suf):
                base = base[:-len(suf)]
                break
        providers.append(base)
    # unique preserving order
    seen=set(); ordered=[]
    for p in providers:
        if p not in seen:
            seen.add(p)
            ordered.append(p)
    return ordered


def get_auth_login_providers() -> set:
    """从插件列表解析支持 auth login 的 providerIds"""
    stdout, _, code = run_cli(["plugins", "list", "--json"])
    if code != 0 or not stdout:
        return set()
    try:
        data = json.loads(stdout)
        providers = set()
        for p in data.get("plugins", []):
            for pid in p.get("providerIds", []) or []:
                providers.add(pid)
        return providers
    except Exception:
        return set()


def get_auth_choice_groups() -> list:
    """解析 auth-choice-options.ts 的分组定义"""
    src = "/app/src/commands/auth-choice-options.ts"
    if not os.path.exists(src):
        return []
    text = open(src, 'r').read()
    # extract AUTH_CHOICE_GROUP_DEFS array
    m = re.search(r"AUTH_CHOICE_GROUP_DEFS:\s*\[[\s\S]*?\];", text)
    if not m:
        return []
    block = m.group(0)
    # naive parse of objects
    groups = []
    for g in re.finditer(r"\{[\s\S]*?\}", block):
        obj = g.group(0)
        val = re.search(r"value:\s*\"(.*?)\"", obj)
        label = re.search(r"label:\s*\"(.*?)\"", obj)
        hint = re.search(r"hint:\s*\"(.*?)\"", obj)
        choices = re.search(r"choices:\s*\[(.*?)\]", obj, re.S)
        if not val or not label or not choices:
            continue
        raw_choices = choices.group(1)
        ids = re.findall(r"\"(.*?)\"", raw_choices)
        groups.append({
            "id": val.group(1),
            "label": label.group(1),
            "hint": hint.group(1) if hint else "",
            "choices": ids,
        })
    return groups


def _format_provider_label(pid: str) -> str:
    label = pid.replace('-', ' ')
    label = ' '.join([w.upper() if w in ['ai','api'] else w.capitalize() for w in label.split()])
    label = label.replace('Openai', 'OpenAI')
    label = label.replace('Xai', 'xAI')
    label = label.replace('Vllm', 'vLLM')
    label = label.replace('Zai', 'Z.AI')
    label = label.replace('Qwen', 'Qwen')
    label = label.replace('Kimi', 'Kimi')
    hint = ''
    if 'portal' in pid or 'copilot' in pid:
        hint = ' (OAuth)'
    elif 'gateway' in pid:
        hint = ' (Gateway)'
    elif 'api-key' in pid or pid.endswith('-api'):
        hint = ' (API Key)'
    return label + hint


def get_official_provider_options() -> List[Dict[str, str]]:
    groups = get_auth_choice_groups()
    auth_login = get_auth_login_providers()
    options = []
    if groups:
        for g in groups:
            for cid in g["choices"]:
                base = cid
                for suf in ["-api-key-cn","-api-key","-api-lightning","-api"]:
                    if base.endswith(suf):
                        base = base[:-len(suf)]
                        break
                options.append({"id": base, "label": _format_provider_label(base), "authLogin": (base in auth_login), "group": g["label"], "hint": g["hint"]})
    else:
        ids = get_onboard_providers()
        options = [{"id": pid, "label": _format_provider_label(pid), "authLogin": (pid in auth_login)} for pid in ids]
    # unique by id
    seen=set(); dedup=[]
    for o in options:
        if o["id"] in seen:
            continue
        seen.add(o["id"])
        dedup.append(o)
    return dedup


API_PROTOCOLS = [
    "openai-chat",
    "openai-completions",
    "anthropic-messages",
    "anthropic-completions",
    "gemini-v1beta",
]


def menu_inventory():
    """资源库主菜单（和其他模块风格一致）"""
    # 静默修复带引号的模型键（用户无感知）
    clean_quoted_model_keys()

    while True:
        console.clear()
        console.print()
        console.print("[bold cyan]========== ⚙️ 资源库 (Inventory) ==========[/]")
        console.print()
        
        # 获取数据
        all_providers, profiles, models = get_providers()
        providers_cfg = get_models_providers()
        
        # 服务商列表表格
        table = Table(box=box.SIMPLE)
        table.add_column("编号", style="cyan", width=4)
        table.add_column("服务商", style="bold", width=20)
        table.add_column("认证授权", style="green", width=10)
        table.add_column("配置Key", style="yellow", width=10)
        table.add_column("模型", style="magenta", width=6)
        
        for i, p in enumerate(all_providers, 1):
            p_count = len(profiles.get(p, []))
            m_count = len(models.get(p, []))
            cfg_count = 1 if p in providers_cfg and providers_cfg.get(p, {}).get('apiKey') else 0
            table.add_row(str(i), p, str(p_count), str(cfg_count), str(m_count))
        
        console.print(table)
        
        # 操作选项
        console.print()
        console.print("[bold]操作:[/]")
        console.print("  [cyan]N[/] 添加新服务商 (从官方列表)")
        console.print("  [cyan]C[/] 添加自定义服务商")
        console.print("  [cyan]D[/] 删除服务商")
        console.print("  [cyan]E[/] 向量化/记忆检索配置")
        console.print("  [cyan]0[/] 返回主菜单")
        console.print()
        
        # 接受大小写，先获取输入再转小写
        choice = Prompt.ask("[bold green]>[/]", default="0").strip().lower()
        
        # 验证输入
        valid_choices = ["0", "n", "c", "d", "e"] + [str(i) for i in range(1, len(all_providers) + 1)]
        while choice not in valid_choices:
            choice = Prompt.ask("[bold green]>[/]", default="0").strip().lower()
        
        if choice == "0":
            return
        elif choice == "n":
            add_official_provider()
        elif choice == "c":
            add_custom_provider()
        elif choice == "d":
            delete_provider_menu()
        elif choice == "e":
            from tui.tools import menu_embeddings
            menu_embeddings()
        elif choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(all_providers):
                menu_provider(all_providers[idx])


def get_providers():
    """获取所有服务商"""
    profiles = config.get_profiles_by_provider()
    models = config.get_models_by_provider()
    providers_cfg = get_models_providers()
    # 合并三处来源：账号、激活模型、models.providers 配置
    all_providers = sorted(set(list(profiles.keys()) + list(models.keys()) + list(providers_cfg.keys())))
    return all_providers, profiles, models


def delete_provider_menu():
    """删除服务商菜单"""
    all_providers, _, _ = get_providers()
    
    if not all_providers:
        console.print("\n[yellow]⚠️ 没有服务商可删除[/]")
        safe_input("\n按回车键继续...")
        return
    
    while True:
        console.clear()
        console.print(Panel(
            Text("🗑️ 删除服务商", style="bold cyan", justify="center"),
            box=box.DOUBLE
        ))
        
        # 服务商列表
        table = Table(box=box.SIMPLE)
        table.add_column("编号", style="cyan", width=4)
        table.add_column("服务商", style="bold")
        
        for i, p in enumerate(all_providers, 1):
            table.add_row(str(i), p)
        
        console.print(table)
        
        console.print()
        console.print("[cyan]0[/] 返回")
        console.print()
        
        choices = ["0"] + [str(i) for i in range(1, len(all_providers) + 1)]
        choice = Prompt.ask("[bold green]>[/]", choices=choices, default="0")
        
        if choice == "0":
            break
        elif choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(all_providers):
                provider = all_providers[idx]
                delete_provider(provider)
                # 删除后刷新列表
                all_providers, _, _ = get_providers()
                continue


def delete_provider(provider: str) -> bool:
    """删除服务商（彻底清理：删除 models.providers + 账号 + 激活模型）"""
    console.print()
    if not Confirm.ask(f"[bold red]确定要删除服务商 '{provider}' 吗？[/]", default=False):
        return False

    if is_dry_run():
        console.print(f"\n[yellow]⏳ (dry-run) 将删除服务商: {provider}...[/]")
        console.print("  [dim]（dry-run：未落盘）[/]")
        return True
    
    console.print(f"\n[yellow]⏳ 正在删除服务商: {provider}...[/]")
    
    try:
        # 先备份配置
        config.reload()
        backup_path = config.backup()
        if backup_path:
            console.print(f"  [dim]💡 已备份配置到: {backup_path}[/]")
        
        # 特殊处理："其他"是虚拟服务商，对应没有明确 provider 的模型
        is_virtual_other = (provider == "其他")
        
        # 1) 删除 models.providers 中的自定义 provider（仅当不是"其他"时）
        if not is_virtual_other:
            providers_cfg = get_models_providers()
            if provider in providers_cfg:
                del providers_cfg[provider]
                ok, err = set_provider_config(provider, providers_cfg)
                if ok:
                    console.print(f"  [dim]✅ 已清理 models.providers[/]")
                else:
                    console.print(f"  [dim]⚠️ 清理 models.providers 失败: {err}[/]")
        
        # 2) 删除激活的模型（agents.defaults.models）
        config.reload()
        models = config.data.get("agents", {}).get("defaults", {}).get("models", {})
        
        if is_virtual_other:
            # "其他"对应：没有 "/" 的模型，或者 provider 字段是"其他"的模型
            to_delete = []
            for k, v in models.items():
                if "/" not in k:
                    # 没有 "/" 的模型（格式不是 provider/model）
                    to_delete.append(k)
                else:
                    # 检查 provider 字段是否是"其他"
                    if v.get("provider") == "其他":
                        to_delete.append(k)
        else:
            # 正常服务商：删除 provider/model 格式的模型
            to_delete = [k for k in models.keys() if k.startswith(f"{provider}/")]
        
        if to_delete:
            try:
                with open(DEFAULT_CONFIG_PATH, 'r') as f:
                    data = json.load(f)
                models_map = data.get("agents", {}).get("defaults", {}).get("models", {})
                for k in to_delete:
                    if k in models_map:
                        del models_map[k]
                with open(DEFAULT_CONFIG_PATH, 'w') as f:
                    json.dump(data, f, indent=2)
                config.reload()
                console.print(f"  [dim]✅ 已清理 {len(to_delete)} 个激活模型[/]")
            except Exception as e:
                console.print(f"  [dim]⚠️ 清理激活模型失败: {e}[/]")
        
        # 3) 清理 auth-profiles 文件中的账号（仅当不是"其他"时）
        if not is_virtual_other and os.path.exists(DEFAULT_AUTH_PROFILES_PATH):
            try:
                with open(DEFAULT_AUTH_PROFILES_PATH, 'r') as f:
                    data = json.load(f)
                profiles_map = data.get("profiles", {})
                to_del_profiles = [k for k, v in profiles_map.items() if v.get("provider") == provider]
                if to_del_profiles:
                    for k in to_del_profiles:
                        del profiles_map[k]
                    with open(DEFAULT_AUTH_PROFILES_PATH, 'w') as f:
                        json.dump(data, f, indent=2)
                    console.print(f"  [dim]✅ 已清理 {len(to_del_profiles)} 个账号[/]")
            except Exception as e:
                console.print(f"  [dim]⚠️ 清理 auth-profiles 失败: {e}[/]")
        
        # 4) 清理 openclaw.json 里的 auth.profiles（仅当不是"其他"时）
        if not is_virtual_other:
            try:
                config.reload()
                with open(DEFAULT_CONFIG_PATH, 'r') as f:
                    data = json.load(f)
                auth_profiles = data.get("auth", {}).get("profiles", {})
                to_del_openclaw = [k for k, v in auth_profiles.items() if v.get("provider") == provider]
                if to_del_openclaw:
                    for k in to_del_openclaw:
                        del auth_profiles[k]
                    with open(DEFAULT_CONFIG_PATH, 'w') as f:
                        json.dump(data, f, indent=2)
                    config.reload()
                    console.print(f"  [dim]✅ 已清理 openclaw.json auth.profiles[/]")
            except Exception as e:
                console.print(f"  [dim]⚠️ 清理 openclaw.json auth profiles 失败: {e}[/]")
        
        console.print(f"\n[green]✅ 已删除服务商: {provider}[/]")
        safe_input("\n按回车键继续...")
        return True
    except Exception as e:
        console.print(f"\n[bold red]❌ 删除失败: {e}[/]")
        safe_input("\n按回车键继续...")
        return False


def add_official_provider():
    """添加官方服务商"""
    console.clear()
    console.print(Panel(
        Text("➕ 添加服务商 (官方支持)", style="bold cyan", justify="center"),
        box=box.DOUBLE
    ))
    console.print("\n[yellow]⏳ 正在获取 OpenClaw 支持的服务商列表...[/]")
    
    providers = get_official_provider_options()
    
    if not providers:
        console.print("\n[bold red]❌ 无法获取服务商列表，请检查网络或手动添加。[/]")
        safe_input("\n按回车键继续...")
        return
    
    console.print(f"  [dim]✅ 获取到 {len(providers)} 个服务商[/]")
    
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
        
        # 不用 Table，直接打印，避免显示问题
        # 渲染官方服务商列表（名称 + 说明）
        table = Table(box=box.SIMPLE)
        table.add_column("编号", style="cyan", width=4)
        table.add_column("分组", style="cyan", width=12)
        table.add_column("服务商", style="bold")
        table.add_column("说明", style="dim")
        table.add_column("认证", style="green", width=8)
        table.add_column("ID", style="dim")
        
        start = page * page_size
        end = min(start + page_size, len(providers))
        for i, p in enumerate(providers[start:end], start + 1):
            auth_tag = "OAuth" if p.get("authLogin") else "API Key"
            table.add_row(str(i), p.get("group",""), p["label"], p.get("hint",""), auth_tag, p["id"])
        
        console.print(table)
        console.print()
        console.print("[cyan]N[/] 下一页  [cyan]P[/] 上一页  [cyan]0[/] 取消")
        
        # 构建 choices 列表
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
                menu_provider(providers[idx]["id"])
                break


def fetch_provider_list() -> List[str]:
    """从 CLI 获取支持的服务商列表（对齐 onboard）"""
    return [p["id"] for p in get_official_provider_options()]



def ensure_provider_config(providers_cfg: Dict, provider: str) -> Dict:
    """确保 provider 配置结构完整（通过 OpenClaw 校验）"""
    providers_cfg[provider] = providers_cfg.get(provider, {})
    cfg = providers_cfg[provider]
    # OpenClaw 校验要求 models 为数组
    if "models" not in cfg:
        cfg["models"] = []
    # 可选字段补默认值，避免校验失败
    cfg.setdefault("apiKey", "")
    cfg.setdefault("baseUrl", "")
    cfg.setdefault("api", "")
    return cfg


def _model_key(provider: str, model: Dict) -> str:
    key = model.get("key") or model.get("id") or model.get("name") or ""
    if not key:
        return ""
    if "/" not in key:
        return f"{provider}/{key}"
    return key


def _activate_model(key: str) -> bool:
    ok, _ = activate_model(key)
    return ok


def _deactivate_model(key: str):
    return deactivate_model(key)


def _model_label(key: str, model: Dict, activated: set) -> str:
    name = model.get("name") or model.get("id") or key
    tag = "✅" if key in activated else "⬜"
    return f"{tag} {name} ({key})"


def _read_key():
    import sys, termios, tty
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch = sys.stdin.read(1)
        if ch == "\x1b":
            seq = sys.stdin.read(2)
            return ch + seq
        return ch
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


def activate_models_with_search(provider: str, all_models: List[Dict], activated: set):
    """分页 + 搜索 + 序号选择模型（raw key 模式）"""
    if not all_models:
        console.print("\n[yellow]⚠️ 未发现可用模型[/]")
        safe_input("\n按回车键继续...")
        return

    activated_current = {k for k in activated if k.startswith(f"{provider}/")}

    bad_activated = {k for k in activated if k.startswith('"') and k.strip('"').startswith(f"{provider}/")}
    for k in bad_activated:
        fixed = k.strip('"')
        _deactivate_model(k)
        _activate_model(fixed)
        activated_current.add(fixed)

    discovered_keys = {(_model_key(provider, m) or "") for m in all_models}
    extra_keys = [k for k in activated_current if k not in discovered_keys]
    for k in extra_keys:
        all_models.append({"key": k, "name": k.split("/", 1)[1] if "/" in k else k})

    selected = set(activated_current)
    keyword = ""
    page_size = 20
    page = 0
    cursor = 0

    def filter_models():
        items = list(all_models)
        if keyword:
            def match(m):
                key = _model_key(provider, m)
                name = (m.get("name") or m.get("id") or "")
                text = f"{key} {name}".lower()
                return keyword.lower() in text
            items = [m for m in items if match(m)]
        items.sort(key=lambda m: 0 if _model_key(provider, m) in activated_current else 1)
        return items

    while True:
        items = filter_models()
        if not items:
            console.print("\n[yellow]⚠️ 没有匹配的模型，请换关键词[/]")
            keyword = ""
            continue

        total_pages = max(1, (len(items) - 1) // page_size + 1)
        page = max(0, min(page, total_pages - 1))
        start_idx = page * page_size
        end_idx = min(start_idx + page_size, len(items))
        page_items = items[start_idx:end_idx]
        cursor = max(0, min(cursor, len(page_items) - 1))

        console.clear()
        console.print(Panel(
            Text(f"📦 模型管理: {provider}", style="bold cyan", justify="center"),
            box=box.DOUBLE
        ))
        console.print(f"  [dim]页 {page+1}/{total_pages} | 已选 {len(selected)} | 过滤: {keyword or '无'}[/]")
        console.print("  [dim]键: n/p 翻页 | j/k/↑/↓ 移动 | 空格切换 | / 搜索 | # 批量选择 | m 手动添加 | a 全选页 | x 清空页 | Enter 确认 | q 退出[/]")
        console.print()

        for i, m in enumerate(page_items, 1):
            key = _model_key(provider, m)
            name = m.get("name") or m.get("id") or key
            checked = "✅" if key in selected else "⬜"
            pointer = "➤" if i-1 == cursor else " "
            console.print(f"  {pointer} [{i:>2}] {checked} {name} ({key})")

        k = _read_key()
        if k in ("q", "Q"):
            return
        if k in ("\r", "\n"):
            break
        if k in ("n", "N"):
            page += 1
            cursor = 0
            continue
        if k in ("p", "P"):
            page -= 1
            cursor = 0
            continue
        if k in ("j", "J", "\x1b[B"):
            cursor = min(cursor + 1, len(page_items) - 1)
            continue
        if k in ("k", "K", "\x1b[A"):
            cursor = max(cursor - 1, 0)
            continue
        if k == " ":
            key = _model_key(provider, page_items[cursor])
            if key in selected:
                selected.discard(key)
            else:
                selected.add(key)
            continue
        if k in ("a", "A"):
            for m in page_items:
                key = _model_key(provider, m)
                if key:
                    selected.add(key)
            continue
        if k in ("x", "X"):
            for m in page_items:
                key = _model_key(provider, m)
                if key and key in selected:
                    selected.discard(key)
            continue
        if k == "/":
            keyword = safe_input("\n搜索关键词: ").strip()
            page = 0
            cursor = 0
            continue
        if k == "#":
            cmd = safe_input("\n选择序号(如 1,3,8-12): ").strip()
            try:
                parts = [p.strip() for p in cmd.split(',') if p.strip()]
                indices = set()
                for p in parts:
                    if '-' in p:
                        a,b = p.split('-',1)
                        a=int(a); b=int(b)
                        for x in range(min(a,b), max(a,b)+1):
                            indices.add(x)
                    else:
                        indices.add(int(p))
                for idx in indices:
                    if 1 <= idx <= len(page_items):
                        key = _model_key(provider, page_items[idx-1])
                        if key in selected:
                            selected.discard(key)
                        else:
                            selected.add(key)
            except Exception:
                console.print("[yellow]⚠️ 输入无效[/]")
            continue


        if k in ("m", "M"):
            mid = safe_input("\n输入模型ID (如 model-name): ").strip()
            if mid:
                key = mid if "/" in mid else f"{provider}/{mid}"
                all_models.append({"key": key, "name": mid})
                selected.add(key)
                providers_cfg = get_models_providers()
                if provider in providers_cfg:
                    ensure_provider_config(providers_cfg, provider)
                    providers_cfg[provider]["models"].append({"id": mid, "name": mid})
                    set_provider_config(provider, providers_cfg)
            continue
    to_add = [k for k in selected if k not in activated_current]
    to_remove = [k for k in activated_current if k not in selected]

    success_add = 0
    failed_add = []
    for k in to_add:
        if _activate_model(k):
            success_add += 1
        else:
            failed_add.append(k)

    success_remove = 0
    failed_remove = []
    for k in to_remove:
        ok, err = _deactivate_model(k)
        if ok:
            success_remove += 1
        else:
            failed_remove.append((k, err))

    if success_add > 0:
        console.print(f"\n[green]✅ 已激活 {success_add} 个模型[/]")
    if success_remove > 0:
        console.print(f"[green]✅ 已取消 {success_remove} 个模型[/]")
    if failed_add:
        console.print(f"[bold red]❌ 激活失败 {len(failed_add)} 个[/]")
    if failed_remove:
        console.print(f"[bold red]❌ 取消失败 {len(failed_remove)} 个[/]")
        console.print("  [dim]" + ", ".join([f"{k}: {e}" for k,e in failed_remove[:3]]) + (" ..." if len(failed_remove)>3 else "") + "[/]")

    safe_input("\n按回车键继续...")



def configure_provider_wizard(provider: str):
    """配置向导：协议 + Base URL + API Key（用于新增/重配）"""
    console.print()
    console.print("[bold]请选择 API 协议:[/]")
    for i, proto in enumerate(API_PROTOCOLS, 1):
        console.print(f"  [cyan]{i}[/] {proto}")
    
    proto_choice = Prompt.ask("[bold green]>[/]", choices=[str(i) for i in range(1, len(API_PROTOCOLS) + 1)], default="1")
    api_proto = API_PROTOCOLS[int(proto_choice) - 1]
    
    console.print()
    base_url = Prompt.ask("[bold]请输入 Base URL[/]", default="").strip()
    api_key = Prompt.ask("[bold]请输入 API Key[/]", default="").strip()
    
    # 添加到 models.providers 配置（含必需字段）
    providers_cfg = get_models_providers()
    ensure_provider_config(providers_cfg, provider)
    providers_cfg[provider]["api"] = api_proto
    providers_cfg[provider]["baseUrl"] = base_url
    providers_cfg[provider]["apiKey"] = api_key
    ok, err = set_provider_config(provider, providers_cfg)
    
    if ok:
        console.print(f"\n[green]✅ 已添加/更新服务商: {provider} (协议: {api_proto})[/]")
        if err == "(dry-run)":
            console.print("  [dim]（dry-run：未落盘）[/]")
    else:
        console.print(f"\n[bold red]❌ 添加服务商失败：{err}[/]")


def add_custom_provider():
    """添加自定义服务商（增强版：支持 API 协议选择）"""
    console.clear()
    console.print(Panel(
        Text("➕ 添加自定义服务商", style="bold cyan", justify="center"),
        box=box.DOUBLE
    ))
    console.print()
    
    provider = Prompt.ask("[bold]请输入服务商名称[/]").strip()
    if not provider:
        console.print("\n[yellow]⚠️  服务商名称不能为空[/]")
        safe_input("\n按回车键继续...")
        return
    
    provider = normalize_provider_name(provider)
    configure_provider_wizard(provider)
    
    safe_input("\n按回车键继续...")
    menu_provider(provider)


def is_official_provider(provider: str) -> bool:
    """判断是否是官方支持的服务商
    规则：
    1) 若该 provider 已有 auth profile（官方授权产生），判定为官方
    2) 否则若 provider 存在于 models.providers 且有 baseUrl/api，判定为自定义
    3) 否则按官方列表兜底
    """
    # 1) auth profile 判断（官方授权后会出现）
    profiles = config.get_profiles_by_provider()
    if provider in profiles and profiles[provider]:
        return True

    providers_cfg = get_models_providers()
    cfg = providers_cfg.get(provider, {}) if providers_cfg else {}

    # 2) 自定义配置优先
    if cfg.get("baseUrl") or cfg.get("api"):
        return False

    # 3) 官方列表兜底
    official_providers = get_official_provider_options()
    official_ids = {p["id"] for p in official_providers}
    return provider in official_ids


def reauthorize_provider(provider: str, is_official: bool):
    """重新授权：清空模型/配置后重新配置"""
    ok = delete_provider(provider)
    if not ok:
        return
    if is_official:
        do_official_auth(provider)
    else:
        configure_provider_wizard(provider)
        safe_input("\n按回车键继续...")


def menu_provider(provider: str):
    """单个服务商管理菜单（官方 vs 自定义区分版）"""
    while True:
        console.clear()
        console.print(Panel(
            Text(f"⚙️ 服务商管理: {provider}", style="bold cyan", justify="center"),
            box=box.DOUBLE
        ))
        
        # 获取当前状态
        profiles = config.get_profiles_by_provider()
        models = config.get_models_by_provider()
        providers_cfg = get_models_providers()
        
        p_count = len(profiles.get(provider, []))
        m_count = len(models.get(provider, []))
        
        console.print()
        console.print(f"  [bold]账号数:[/] {p_count}")
        console.print(f"  [bold]模型数:[/] {m_count}")
        
        # 显示当前配置
        provider_cfg = providers_cfg.get(provider, {})
        current_api = provider_cfg.get("api", "(未设置)")
        current_baseurl = provider_cfg.get("baseUrl", "(未设置)")
        
        # 判断是否是官方服务商
        is_official = is_official_provider(provider)
        
        if is_official:
            console.print("  [bold][green]类型: 官方服务商[/][/]")
            console.print("  [dim]  (无需手动配置协议/Base URL)[/]")
        else:
            console.print("  [bold][yellow]类型: 自定义服务商[/][/]")
            console.print(f"  [bold]API 协议:[/] {current_api}")
            console.print(f"  [bold]Base URL:[/] {current_baseurl}")
        
        # 展示已激活模型（当前服务商）
        console.print()
        console.print("[bold]已激活模型:[/]")
        active_models = models.get(provider, [])
        if not active_models:
            console.print("  [dim](尚未激活)[/]")
        else:
            # 显示前 10 个，避免刷屏
            for m in active_models[:10]:
                name = m.get('_display_name') or m.get('_full_name')
                console.print(f"  - {name}")
            if len(active_models) > 10:
                console.print(f"  ... 还有 {len(active_models) - 10} 个")
        
        console.print()
        console.print("[bold]操作:[/]")
        
        # 判断是否已授权（有 profile 或 apiKey）
        authorized = bool(profiles.get(provider)) or bool(provider_cfg.get("apiKey"))
        
        if authorized:
            console.print("  [cyan]1[/] 更换 API Key")
            console.print("  [cyan]2[/] 重新授权 (清空配置+模型)")
            console.print("  [cyan]3[/] 模型管理")
            console.print("  [cyan]0[/] 返回")
            choices = ["0", "1", "2", "3"]
        else:
            if is_official:
                # 根据插件支持决定是否走官方授权
                auth_login = get_auth_login_providers()
                if provider in auth_login:
                    console.print("  [cyan]1[/] 官方授权流程 (推荐)")
                    console.print("  [cyan]2[/] 模型管理")
                    console.print("  [cyan]0[/] 返回")
                    choices = ["0", "1", "2"]
                else:
                    console.print("  [cyan]1[/] 配置 API Key")
                    console.print("  [cyan]2[/] 模型管理")
                    console.print("  [cyan]0[/] 返回")
                    choices = ["0", "1", "2"]
            else:
                console.print("  [cyan]1[/] 配置服务商 (协议/BaseURL/API Key)")
                console.print("  [cyan]2[/] 模型管理")
                console.print("  [cyan]0[/] 返回")
                choices = ["0", "1", "2"]
        
        console.print()
        
        # 接受大小写
        choice = Prompt.ask("[bold green]>[/]", choices=choices, default="0").strip().lower()
        while choice not in choices:
            choice = Prompt.ask("[bold green]>[/]", choices=choices, default="0").strip().lower()
        
        if choice == "0":
            break
        elif authorized:
            if choice == "1":
                set_provider_apikey(provider)
            elif choice == "2":
                reauthorize_provider(provider, is_official)
            elif choice == "3":
                manage_models_menu(provider)
        else:
            if is_official:
                auth_login = get_auth_login_providers()
                if provider in auth_login:
                    if choice == "1":
                        do_official_auth(provider)
                    elif choice == "2":
                        manage_models_menu(provider)
                else:
                    if choice == "1":
                        set_provider_apikey(provider)
                    elif choice == "2":
                        manage_models_menu(provider)
            else:
                if choice == "1":
                    configure_provider_wizard(provider)
                    safe_input("\n按回车键继续...")
                elif choice == "2":
                    manage_models_menu(provider)


def _friendly_error_message(err: str) -> str:
    if not err:
        return "未知错误"
    low = err.lower()
    if "unknown provider" in low:
        return "该服务商未安装官方插件，无法走官方授权"
    if "config validation failed" in low or "invalid input" in low:
        return "配置未通过校验（可能缺少 models 列表）"
    if "permission" in low or "eacces" in low:
        return "权限不足，无法写入配置"
    if "timeout" in low or "timed out" in low:
        return "命令执行超时，请稍后重试"
    if "no such file" in low:
        return "配置文件不存在"
    if "json" in low and "parse" in low:
        return "配置解析失败（JSON 格式异常）"
    return err


def do_official_auth(provider: str):
    """执行官方授权流程（完全脱离 Rich Console，纯原生方式）"""
    # 完全脱离 Rich Console，避免任何终端冲突
    # 用纯 Python 原生方式，最安全
    
    # 先尝试清除控制台
    try:
        console.clear()
    except:
        pass
    
    # 纯原生输出
    print()
    print("=" * 60)
    print(f"  🔑 官方授权流程: {provider}")
    print("=" * 60)
    print()
    print("  💡 将直接调用 OpenClaw 官方授权流程")
    print("     OpenClaw 会自动判断是 OAuth 还是 API Key")
    print()
    print("  ⚠️  提示: OAuth 授权需要在浏览器中完成，请耐心等待...")
    print()
    
    # dry-run: 不实际执行授权
    if is_dry_run():
        print("  [DRY-RUN] 跳过官方授权执行")
        safe_input("  按回车键继续...")
        return

    # 直接启动（减少确认步骤）
    print()
    print("  ⏳ 正在启动官方授权流程...")
    print()
    print("-" * 60)
    print()
    
    try:
        from core import OPENCLAW_BIN
        import subprocess
        
        cmd = [OPENCLAW_BIN, "models", "auth", "login", "--provider", provider]
        result = subprocess.run(cmd, capture_output=True, text=True)
        code = result.returncode
        stderr = (result.stderr or "").strip()
        
        print()
        print("-" * 60)
        print()
        
        if code == 0:
            print("  ✅ 授权成功！")
        else:
            print("  ❌ 授权失败")
            if stderr:
                print(f"  原因: {_friendly_error_message(stderr)}")
            if "Unknown provider" in stderr or "unknown provider" in stderr:
                print("  ⚠️ 该服务商不支持官方授权，已切换到 API Key 配置")
                safe_input("\n  按回车键继续...")
                set_provider_apikey(provider)
                return
    
    except Exception as e:
        print()
        print("-" * 60)
        print()
        print(f"  ❌ 授权失败: {e}")
    
    print()
    safe_input("  按回车键继续...")
    
    # 最后重新清除一下，准备回到 Rich Console
    try:
        console.clear()
    except:
        pass


def do_oauth(provider: str):
    """执行 OAuth 授权（已废弃，保留用于向后兼容）"""
    console.print(f"\n[yellow]⚠️ 该方式已废弃，请使用「官方授权流程」[/]")
    console.print()
    if Confirm.ask(f"[bold]还是继续用旧方式吗？[/]", default=False):
        console.print(f"\n[yellow]⏳ 正在启动 OAuth 授权流程: {provider}...[/]")
        console.print("  [dim]浏览器会自动打开，请完成授权后返回[/]")
        
        try:
            stdout, stderr, code = run_cli(["auth", "login", provider])
            if code == 0:
                console.print(f"\n[green]✅ OAuth 授权成功: {provider}[/]")
            else:
                console.print(f"\n[bold red]❌ OAuth 授权失败[/]")
                if stderr:
                    console.print(f"  [dim]详情: {stderr}[/]")
        except Exception as e:
            console.print(f"\n[bold red]❌ OAuth 授权失败: {e}[/]")
        
    safe_input("\n按回车键继续...")


def set_provider_apikey(provider: str):
    """设置服务商 API Key"""
    console.clear()
    console.print(Panel(
        Text(f"🔑 设置 API Key: {provider}", style="bold cyan", justify="center"),
        box=box.DOUBLE
    ))
    
    providers_cfg = get_models_providers()
    current = providers_cfg.get(provider, {}).get("apiKey", "")
    masked = current[:8] + "..." if current and len(current) > 8 else current
    
    console.print()
    console.print(f"  [dim]当前值: {masked or '(未设置)'}[/]")
    console.print("  [dim]直接回车保持不变，输入新值覆盖[/]")
    console.print()
    
    new_key = Prompt.ask("[bold]请输入 API Key[/]", default=current).strip()
    
    # 备份
    config.reload()
    backup_path = config.backup()
    if backup_path:
        console.print(f"\n  [dim]💡 已备份配置到: {backup_path}[/]")
    
    # 更新
    ensure_provider_config(providers_cfg, provider)
    providers_cfg[provider]["apiKey"] = new_key
    ok, err = set_provider_config(provider, providers_cfg)
    
    if ok:
        console.print(f"\n[green]✅ 已更新 API Key: {provider}[/]")
        if err == "(dry-run)":
            console.print("  [dim]（dry-run：未落盘）[/]")
    else:
        console.print(f"\n[bold red]❌ 更新 API Key 失败[/]")
        console.print(f"  [dim]原因: {_friendly_error_message(err)}[/]")
    safe_input("\n按回车键继续...")


def set_provider_baseurl(provider: str):
    """设置服务商 Base URL"""
    console.clear()
    console.print(Panel(
        Text(f"🌐 设置 Base URL: {provider}", style="bold cyan", justify="center"),
        box=box.DOUBLE
    ))
    
    providers_cfg = get_models_providers()
    current = providers_cfg.get(provider, {}).get("baseUrl", "")
    
    console.print()
    console.print(f"  [dim]当前值: {current or '(未设置)'}[/]")
    console.print("  [dim]直接回车保持不变，输入新值覆盖[/]")
    console.print()
    
    new_url = Prompt.ask("[bold]请输入 Base URL[/]", default=current).strip()
    
    # 备份
    config.reload()
    backup_path = config.backup()
    if backup_path:
        console.print(f"\n  [dim]💡 已备份配置到: {backup_path}[/]")
    
    # 更新
    ensure_provider_config(providers_cfg, provider)
    providers_cfg[provider]["baseUrl"] = new_url
    ok, err = set_provider_config(provider, providers_cfg)
    
    if ok:
        console.print(f"\n[green]✅ 已更新 Base URL: {provider}[/]")
        if err == "(dry-run)":
            console.print("  [dim]（dry-run：未落盘）[/]")
    else:
        console.print(f"\n[bold red]❌ 更新 Base URL 失败[/]")
        console.print(f"  [dim]原因: {_friendly_error_message(err)}[/]")
    safe_input("\n按回车键继续...")


def set_provider_protocol(provider: str):
    """设置服务商 API 协议"""
    console.clear()
    console.print(Panel(
        Text(f"🔌 设置 API 协议: {provider}", style="bold cyan", justify="center"),
        box=box.DOUBLE
    ))
    
    providers_cfg = get_models_providers()
    current = providers_cfg.get(provider, {}).get("api", "")
    
    console.print()
    console.print(f"  [dim]当前协议: {current or '(未设置)'}[/]")
    console.print()
    console.print("[bold]请选择 API 协议:[/]")
    for i, proto in enumerate(API_PROTOCOLS, 1):
        console.print(f"  [cyan]{i}[/] {proto}")
    
    console.print()
    
    choices = [str(i) for i in range(1, len(API_PROTOCOLS) + 1)]
    choice = Prompt.ask("[bold green]>[/]", choices=choices, default="1")
    new_proto = API_PROTOCOLS[int(choice) - 1]
    
    # 备份
    config.reload()
    backup_path = config.backup()
    if backup_path:
        console.print(f"\n  [dim]💡 已备份配置到: {backup_path}[/]")
    
    # 更新
    ensure_provider_config(providers_cfg, provider)
    providers_cfg[provider]["api"] = new_proto
    ok, err = set_provider_config(provider, providers_cfg)
    
    if ok:
        console.print(f"\n[green]✅ 已更新 API 协议: {new_proto}[/]")
        if err == "(dry-run)":
            console.print("  [dim]（dry-run：未落盘）[/]")
    else:
        console.print(f"\n[bold red]❌ 更新 API 协议失败[/]")
        console.print(f"  [dim]原因: {_friendly_error_message(err)}[/]")
    safe_input("\n按回车键继续...")


def auto_discover_models(provider: str):
    """自动发现模型（从 baseUrl 调用 /v1/models）"""
    console.clear()
    console.print(Panel(
        Text(f"🔍 自动发现模型: {provider}", style="bold cyan", justify="center"),
        box=box.DOUBLE
    ))
    
    providers_cfg = get_models_providers()
    base_url = providers_cfg.get(provider, {}).get("baseUrl", "")
    
    if not base_url:
        console.print("\n[yellow]⚠️ 请先设置 Base URL[/]")
        safe_input("\n按回车键继续...")
        return
    
    # 生成模型发现 URL：避免重复拼接 /v1
    base = base_url.rstrip("/")
    if base.endswith("/v1"):
        models_url = base + "/models"
    else:
        models_url = base + "/v1/models"
    
    console.print(f"\n[yellow]⏳ 正在从 {models_url} 发现模型...[/]")
    
    try:
        req = urllib.request.Request(models_url)
        # 如果有 apiKey，添加 Authorization header
        api_key = providers_cfg.get(provider, {}).get("apiKey", "")
        if api_key:
            req.add_header("Authorization", f"Bearer {api_key}")
        
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
        
        discovered = []
        for m in data.get("data", []):
            model_id = m.get("id")
            if model_id:
                discovered.append({
                    "id": model_id,
                    "name": model_id,
                    "reasoning": False,
                    "input": ["text"],
                    "cost": {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0},
                    "contextWindow": 128000,
                    "maxTokens": 4096
                })
        
        if discovered:
            console.print(f"\n[green]✅ 发现 {len(discovered)} 个模型[/]")
            
            # 备份
            config.reload()
            backup_path = config.backup()
            if backup_path:
                console.print(f"  [dim]💡 已备份配置到: {backup_path}[/]")
            
            # 更新
            providers_cfg[provider] = providers_cfg.get(provider, {})
            providers_cfg[provider]["models"] = discovered
            ok, err = set_provider_config(provider, providers_cfg)
            if not ok:
                console.print(f"\n[bold red]❌ 写入模型列表失败：{err}[/]")
            
            console.print("\n发现的模型:")
            for m in discovered[:10]:
                console.print(f"  - {m['id']}")
            if len(discovered) > 10:
                console.print(f"  ... 还有 {len(discovered) - 10} 个")
        else:
            console.print("\n[yellow]⚠️ 未发现模型[/]")
    
    except Exception as e:
        console.print(f"\n[bold red]❌ 自动发现失败: {e}[/]")
    
    safe_input("\n按回车键继续...")


def list_all_available_models(provider: str):
    """查看官方服务商的所有可用模型"""
    console.clear()
    console.print(Panel(
        Text(f"📋 所有可用模型: {provider}", style="bold cyan", justify="center"),
        box=box.DOUBLE
    ))
    console.print()
    console.print("[yellow]⏳ 正在获取模型列表...[/]")
    
    try:
        stdout, stderr, code = run_cli(["models", "list", "--all", "--provider", provider, "--json"])
        if code == 0 and stdout:
            data = json.loads(stdout)
            models = data.get("models", [])
            
            if models:
                console.clear()
                console.print(Panel(
                    Text(f"📋 所有可用模型: {provider} ({len(models)} 个)", style="bold cyan", justify="center"),
                    box=box.DOUBLE
                ))
                
                table = Table(box=box.SIMPLE)
                table.add_column("可用", style="cyan", width=6)
                table.add_column("模型", style="bold")
                
                for m in models:
                    available = m.get("available", False)
                    status = "✅" if available else "❌"
                    name = m.get("name", m.get("key", ""))
                    table.add_row(status, name)
                
                console.print()
                console.print(table)
            else:
                console.print("\n[yellow]⚠️ 未发现可用模型[/]")
        else:
            console.print("\n[bold red]❌ 获取模型列表失败[/]")
            if stderr:
                console.print(f"  [dim]{stderr}[/]")
    except Exception as e:
        console.print(f"\n[bold red]❌ 失败: {e}[/]")
    
    safe_input("\n按回车键继续...")


def add_official_models(provider: str):
    """从官方激活模型（和官方对齐）"""
    console.clear()
    console.print(Panel(
        Text(f"📦 激活官方模型: {provider}", style="bold cyan", justify="center"),
        box=box.DOUBLE
    ))
    console.print()
    console.print("[yellow]⏳ 正在获取模型列表...[/]")
    
    try:
        all_models = get_official_models(provider)
        
        if not all_models:
            console.print("\n[yellow]⚠️ 未发现可用模型[/]")
            safe_input("\n按回车键继续...")
            return
        
        # 获取当前已激活的模型
        config.reload()
        activated = set(config.data.get("agents", {}).get("defaults", {}).get("models", {}).keys())
        
        activate_models_with_search(provider, all_models, activated)
    
    except Exception as e:
        console.print(f"\n[bold red]❌ 失败: {e}[/]")
    safe_input("\n按回车键继续...")


def manage_models_menu(provider: str):
    """模型管理（搜索/多选激活）"""
    console.clear()
    console.print(Panel(
        Text(f"📦 模型管理: {provider}", style="bold cyan", justify="center"),
        box=box.DOUBLE
    ))
    
    providers_cfg = get_models_providers()
    models = providers_cfg.get(provider, {}).get("models", [])
    
    if not models:
        console.print("\n[yellow]⚠️ 没有模型，请先自动发现或手动添加[/]")
        safe_input("\n按回车键继续...")
        return
    
    # 获取当前已激活的模型
    config.reload()
    activated = set(config.data.get("agents", {}).get("defaults", {}).get("models", {}).keys())
    
    activate_models_with_search(provider, models, activated)


if __name__ == "__main__":
    menu_inventory()
