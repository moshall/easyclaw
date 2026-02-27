"""
资源库 (Inventory) 模块 - 服务商/账号/模型管理
优化版：和其他模块风格一致，增加删除功能、协议选择、模型管理
"""
import os
import json
import re
import time
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
from core.write_engine import (
    activate_model,
    deactivate_model,
    set_provider_config,
    clean_quoted_model_keys,
    is_dry_run,
    upsert_provider_api_key,
)
from core.datasource import get_official_models, get_custom_models

console = Console()

from core.utils import safe_input, pause_enter

MODELS_PROVIDERS_CACHE_TTL = int(os.environ.get("EASYCLAW_MODELS_PROVIDERS_CACHE_TTL", "2"))
PLUGIN_PROVIDER_CACHE_TTL = int(os.environ.get("EASYCLAW_PLUGIN_PROVIDER_CACHE_TTL", "45"))

_models_providers_cache_data: Optional[Dict] = None
_models_providers_cache_ts: float = 0.0
_plugin_provider_ids_cache: Optional[set] = None
_plugin_provider_ids_cache_ts: float = 0.0


def invalidate_models_providers_cache():
    global _models_providers_cache_data, _models_providers_cache_ts
    _models_providers_cache_data = None
    _models_providers_cache_ts = 0.0


def get_models_providers_cached(force_refresh: bool = False) -> Dict:
    global _models_providers_cache_data, _models_providers_cache_ts
    now = time.time()
    if (
        force_refresh
        or _models_providers_cache_data is None
        or (now - _models_providers_cache_ts) > MODELS_PROVIDERS_CACHE_TTL
    ):
        _models_providers_cache_data = get_models_providers() or {}
        _models_providers_cache_ts = now
    return _models_providers_cache_data or {}


def refresh_official_model_pool() -> tuple[bool, str]:
    """强制刷新官方模型池与本地缓存。"""
    invalidate_models_providers_cache()
    invalidate_plugin_provider_cache()

    # 触发 OpenClaw 重新拉取/生成最新模型目录
    stdout, stderr, code = run_cli(["models", "list", "--all", "--json"])
    if code != 0:
        # 即使官方刷新失败，也尝试刷新本地缓存，避免 UI 继续读旧值
        get_models_providers_cached(force_refresh=True)
        return False, (stderr or stdout or "刷新失败")

    model_count = 0
    try:
        data = json.loads(stdout or "{}")
        model_count = len(data.get("models", []) or [])
    except Exception:
        model_count = 0

    get_models_providers_cached(force_refresh=True)
    return True, str(model_count)


def invalidate_plugin_provider_cache():
    global _plugin_provider_ids_cache, _plugin_provider_ids_cache_ts
    _plugin_provider_ids_cache = None
    _plugin_provider_ids_cache_ts = 0.0


def _get_plugin_provider_ids(force_refresh: bool = False) -> set:
    global _plugin_provider_ids_cache, _plugin_provider_ids_cache_ts
    now = time.time()
    if (
        not force_refresh
        and _plugin_provider_ids_cache is not None
        and (now - _plugin_provider_ids_cache_ts) <= PLUGIN_PROVIDER_CACHE_TTL
    ):
        return set(_plugin_provider_ids_cache)

    stdout, _, code = run_cli(["plugins", "list", "--json"])
    provider_ids = set()
    if code == 0 and stdout:
        try:
            data = json.loads(stdout)
            for plugin in data.get("plugins", []):
                for pid in (plugin.get("providerIds") or []):
                    provider_ids.add(pid)
        except Exception:
            provider_ids = set()

    _plugin_provider_ids_cache = set(provider_ids)
    _plugin_provider_ids_cache_ts = now
    return provider_ids


# 已知的 API Key 类型服务商 -> 官方 auth-choice 映射
API_KEY_PROVIDERS = {
    "openai": "openai-api-key",
    "anthropic": "apiKey",
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
BASE_AUTH_OPTIONS = {
    "token": {"label": "Anthropic 令牌（粘贴 setup-token）", "authType": "Token", "hint": "在其他地方运行 `claude setup-token`，然后在此粘贴令牌"},
    "openai-codex": {"label": "OpenAI Codex（ChatGPT OAuth）", "authType": "OAuth"},
    "chutes": {"label": "Chutes（OAuth）", "authType": "OAuth"},
    "vllm": {"label": "vLLM (custom URL + model)", "authType": "Custom", "hint": "Local/self-hosted OpenAI-compatible server"},
    "openai-api-key": {"label": "OpenAI API 密钥", "authType": "API Key", "provider": "openai"},
    "mistral-api-key": {"label": "Mistral API 密钥", "authType": "API Key", "provider": "mistral"},
    "xai-api-key": {"label": "xAI（Grok）API 密钥", "authType": "API Key", "provider": "xai"},
    "volcengine-api-key": {"label": "火山引擎 API 密钥", "authType": "API Key", "provider": "volcengine"},
    "byteplus-api-key": {"label": "BytePlus API 密钥", "authType": "API Key", "provider": "byteplus"},
    "qianfan-api-key": {"label": "百度千帆 API 密钥", "authType": "API Key", "provider": "qianfan"},
    "openrouter-api-key": {"label": "OpenRouter API 密钥", "authType": "API Key", "provider": "openrouter"},
    "litellm-api-key": {"label": "LiteLLM API 密钥", "authType": "API Key", "hint": "Unified gateway for 100+ LLM providers", "provider": "litellm"},
    "ai-gateway-api-key": {"label": "Vercel AI Gateway API 密钥", "authType": "API Key", "provider": "ai-gateway"},
    "cloudflare-ai-gateway-api-key": {"label": "Cloudflare AI Gateway", "authType": "API Key", "hint": "账户 ID + 网关 ID + API 密钥", "provider": "cloudflare-ai-gateway"},
    "moonshot-api-key": {"label": "Kimi API 密钥（.ai）", "authType": "API Key", "provider": "moonshot"},
    "moonshot-api-key-cn": {"label": "Kimi API 密钥（.cn）", "authType": "API Key", "provider": "moonshot"},
    "kimi-code-api-key": {"label": "Kimi Code API 密钥（订阅版）", "authType": "API Key", "provider": "moonshot"},
    "synthetic-api-key": {"label": "Synthetic API 密钥", "authType": "API Key", "provider": "synthetic"},
    "venice-api-key": {"label": "Venice AI API 密钥", "authType": "API Key", "hint": "隐私优先推理（无审查模型）", "provider": "venice"},
    "together-api-key": {"label": "Together AI API 密钥", "authType": "API Key", "hint": "Llama、DeepSeek、Qwen 等开源模型", "provider": "togetherai"},
    "shengsuanyun-api-key": {"label": "胜算云 API 密钥", "authType": "API Key", "hint": "国内 API 聚合平台 - shengsuanyun.com", "provider": "shengsuanyun"},
    "huggingface-api-key": {"label": "Hugging Face API key (HF token)", "authType": "API Key", "hint": "Inference Providers — OpenAI-compatible chat", "provider": "huggingface"},
    "github-copilot": {"label": "GitHub Copilot（设备登录）", "authType": "OAuth", "hint": "使用 GitHub 设备流程"},
    "gemini-api-key": {"label": "Google Gemini API 密钥", "authType": "API Key", "provider": "gemini"},
    "google-antigravity": {"label": "Google Antigravity OAuth", "authType": "OAuth", "hint": "使用内置 Antigravity 认证插件"},
    "google-gemini-cli": {"label": "Google Gemini CLI OAuth", "authType": "OAuth", "hint": "使用内置 Gemini CLI 认证插件"},
    "zai-api-key": {"label": "Z.AI API 密钥", "authType": "API Key", "provider": "zai"},
    "zai-coding-global": {"label": "编程计划-国际版", "authType": "API Key", "hint": "GLM 编程计划国际版 (api.z.ai)", "provider": "zai"},
    "zai-coding-cn": {"label": "编程计划-国内版", "authType": "API Key", "hint": "GLM 编程计划国内版 (open.bigmodel.cn)", "provider": "zai"},
    "zai-global": {"label": "国际版", "authType": "API Key", "hint": "Z.AI 国际版 (api.z.ai)", "provider": "zai"},
    "zai-cn": {"label": "国内版", "authType": "API Key", "hint": "Z.AI 国内版 (open.bigmodel.cn)", "provider": "zai"},
    "xiaomi-api-key": {"label": "小米 API 密钥", "authType": "API Key", "provider": "xiaomi"},
    "minimax-portal": {"label": "MiniMax OAuth", "authType": "OAuth", "hint": "MiniMax 的 OAuth 插件"},
    "qwen-portal": {"label": "通义千问 OAuth", "authType": "OAuth"},
    "copilot-proxy": {"label": "Copilot 代理（本地）", "authType": "Proxy", "hint": "VS Code Copilot 模型的本地代理"},
    "apiKey": {"label": "Anthropic API 密钥", "authType": "API Key", "provider": "anthropic"},
    "opencode-zen": {"label": "OpenCode Zen（多模型代理）", "authType": "API Key", "hint": "通过 opencode.ai/zen 使用 Claude、GPT、Gemini", "provider": "opencode-zen"},
    "minimax-api": {"label": "MiniMax M2.5", "authType": "API Key", "provider": "minimax"},
    "minimax-api-key-cn": {"label": "MiniMax M2.5 (CN)", "authType": "API Key", "hint": "China endpoint (api.minimaxi.com)", "provider": "minimax"},
    "minimax-api-lightning": {"label": "MiniMax M2.5 Lightning", "authType": "API Key", "hint": "更快，输出成本更高", "provider": "minimax"},
    "custom-api-key": {"label": "自定义服务商", "authType": "API Key", "hint": "任意 OpenAI 或 Anthropic 兼容端点"},
}

AUTH_GROUPS = [
    {"group": "OpenAI", "hint": "Codex OAuth + API 密钥", "choices": ["openai-codex", "openai-api-key"]},
    {"group": "Anthropic", "hint": "setup-token + API 密钥", "choices": ["token", "apiKey"]},
    {"group": "Chutes", "hint": "OAuth", "choices": ["chutes"]},
    {"group": "vLLM", "hint": "Local/self-hosted OpenAI-compatible", "choices": ["vllm"]},
    {"group": "MiniMax", "hint": "M2.5（推荐）", "choices": ["minimax-portal", "minimax-api", "minimax-api-key-cn", "minimax-api-lightning"]},
    {"group": "Moonshot AI", "hint": "Kimi K2.5 + Kimi Coding", "choices": ["moonshot-api-key", "moonshot-api-key-cn", "kimi-code-api-key"]},
    {"group": "Google", "hint": "Gemini API 密钥 + OAuth", "choices": ["gemini-api-key", "google-antigravity", "google-gemini-cli"]},
    {"group": "xAI (Grok)", "hint": "API 密钥", "choices": ["xai-api-key"]},
    {"group": "Mistral AI", "hint": "API 密钥", "choices": ["mistral-api-key"]},
    {"group": "Volcano Engine", "hint": "API 密钥", "choices": ["volcengine-api-key"]},
    {"group": "BytePlus", "hint": "API 密钥", "choices": ["byteplus-api-key"]},
    {"group": "OpenRouter", "hint": "API 密钥", "choices": ["openrouter-api-key"]},
    {"group": "Qwen", "hint": "OAuth", "choices": ["qwen-portal"]},
    {"group": "Z.AI", "hint": "GLM 编程计划 / 国际版 / 国内版", "choices": ["zai-coding-global", "zai-coding-cn", "zai-global", "zai-cn"]},
    {"group": "Qianfan", "hint": "API 密钥", "choices": ["qianfan-api-key"]},
    {"group": "Copilot", "hint": "GitHub + 本地代理", "choices": ["github-copilot", "copilot-proxy"]},
    {"group": "Vercel AI Gateway", "hint": "API 密钥", "choices": ["ai-gateway-api-key"]},
    {"group": "OpenCode Zen", "hint": "API 密钥", "choices": ["opencode-zen"]},
    {"group": "Xiaomi", "hint": "API 密钥", "choices": ["xiaomi-api-key"]},
    {"group": "Synthetic", "hint": "Anthropic 兼容（多模型）", "choices": ["synthetic-api-key"]},
    {"group": "Together AI", "hint": "API 密钥", "choices": ["together-api-key"]},
    {"group": "胜算云 (国产模型)", "hint": "国内 API 聚合平台", "choices": ["shengsuanyun-api-key"]},
    {"group": "Hugging Face", "hint": "Inference API (HF token)", "choices": ["huggingface-api-key"]},
    {"group": "Venice AI", "hint": "隐私优先（无审查模型）", "choices": ["venice-api-key"]},
    {"group": "LiteLLM", "hint": "统一 LLM 网关（100+ 提供商）", "choices": ["litellm-api-key"]},
    {"group": "Cloudflare AI Gateway", "hint": "账户 ID + 网关 ID + API 密钥", "choices": ["cloudflare-ai-gateway-api-key"]},
    {"group": "自定义服务商", "hint": "任意 OpenAI 或 Anthropic 兼容端点", "choices": ["custom-api-key"]}
]

def get_official_provider_options() -> List[Dict[str, str]]:
    options = []
    for g in AUTH_GROUPS:
        for cid in g["choices"]:
            if cid in BASE_AUTH_OPTIONS:
                opt = BASE_AUTH_OPTIONS[cid]
                provider_id = opt.get("provider", cid)
                options.append({
                    "id": cid,
                    "providerId": provider_id,
                    "label": opt.get("label", cid),
                    "authType": opt.get("authType", "API Key"),
                    "group": g["group"],
                    "hint": opt.get("hint", "")
                })

    # 自动补齐 OpenClaw 最新 provider（避免 EasyClaw 静态表滞后）
    known_provider_ids = {opt.get("providerId") or opt["id"] for opt in options}
    try:
        stdout, _, code = run_cli(["models", "list", "--all", "--json"])
        if code == 0 and stdout:
            data = json.loads(stdout)
            providers = set()
            for m in data.get("models", []):
                key = (m.get("key") or "").strip()
                if "/" in key:
                    providers.add(key.split("/", 1)[0])
            for provider_id in sorted(providers):
                if provider_id in known_provider_ids:
                    continue
                options.append({
                    "id": provider_id,
                    "providerId": provider_id,
                    "label": f"{provider_id} (Auto)",
                    "authType": "Unknown",
                    "group": "OpenClaw Auto",
                    "hint": "自动发现的官方 provider；可先尝试官方向导，再回退 API Key。",
                })
    except Exception:
        pass

    return options


def resolve_provider_id(raw_provider: str) -> str:
    """将 UI 选项 ID 归一化为真实 provider ID。"""
    if not raw_provider:
        return raw_provider
    opt = BASE_AUTH_OPTIONS.get(raw_provider, {})
    return normalize_provider_name(opt.get("provider", raw_provider))


def is_oauth_provider(provider: str) -> bool:
    """判断 provider 是否属于 OAuth 认证类型。"""
    return any(
        (opt_id == provider or opt.get("provider") == provider) and opt.get("authType") == "OAuth"
        for opt_id, opt in BASE_AUTH_OPTIONS.items()
    )


def provider_auth_plugin_available(provider: str) -> bool:
    """检测 provider 是否存在可用的 auth plugin 声明。"""
    provider = resolve_provider_id(provider)
    return provider in _get_plugin_provider_ids()


def get_onboard_api_key_flags() -> set:
    """解析 `openclaw onboard --help`，提取支持的 `<key>` 参数名。"""
    stdout, stderr, code = run_cli(["onboard", "--help"])
    text = f"{stdout}\n{stderr}" if code == 0 else (stderr or stdout or "")
    flags = set(re.findall(r"--([a-z0-9-]+)\s+<key>", text))
    return flags


def resolve_api_key_auth_choice(provider: str) -> str:
    """根据 provider 解析官方 auth-choice（优先使用人工定义映射）。"""
    provider = resolve_provider_id(provider)
    preferred = API_KEY_PROVIDERS.get(provider, "")
    if preferred and BASE_AUTH_OPTIONS.get(preferred, {}).get("authType") == "API Key":
        return preferred

    for opt_id, opt in BASE_AUTH_OPTIONS.items():
        if opt.get("authType") != "API Key":
            continue
        if resolve_provider_id(opt.get("provider", opt_id)) == provider:
            return opt_id
    return ""


def resolve_onboard_api_key_flag(provider: str, auth_choice: str) -> str:
    """解析 onboard 的 API key flag（如 `openrouter-api-key`）。"""
    # 常见场景可直接推断，避免每次都调用 `onboard --help`
    if auth_choice.endswith("-api-key"):
        return auth_choice
    if auth_choice == "apiKey":
        return "anthropic-api-key"
    if auth_choice == "opencode-zen":
        return "opencode-zen-api-key"

    flags = get_onboard_api_key_flags()
    provider = resolve_provider_id(provider)

    candidates = [
        auth_choice,
        auth_choice[:-3] if auth_choice.endswith("-cn") else "",
        f"{provider}-api-key" if provider else "",
        f"{provider.replace('-cn', '')}-api-key" if provider else "",
    ]

    seen = set()
    for c in candidates:
        if not c or c in seen:
            continue
        seen.add(c)
        if c in flags:
            return c
    return ""


def apply_official_api_key_via_onboard(provider: str, auth_choice: str, api_key: str):
    """通过 OpenClaw 官方 onboard 非交互流程写入 API key。"""
    if not provider:
        return False, "provider is required"
    if not auth_choice:
        return False, "auth choice is required"
    if not api_key:
        return False, "api key is required"

    key_flag = resolve_onboard_api_key_flag(provider, auth_choice)
    if not key_flag:
        return False, f"missing onboard key flag for auth choice: {auth_choice}"

    cmd = [
        "onboard",
        "--non-interactive",
        "--accept-risk",
        "--auth-choice",
        auth_choice,
        f"--{key_flag}",
        api_key,
        "--skip-channels",
        "--skip-skills",
        "--skip-health",
        "--skip-ui",
        "--no-install-daemon",
        "--json",
    ]
    stdout, stderr, code = run_cli(cmd)
    if code != 0:
        return False, stderr or stdout or "onboard failed"
    return True, ""


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
        providers_cfg = get_models_providers_cached()
        all_providers, profiles, models = get_providers(providers_cfg)
        
        # 服务商列表表格
        table = Table(box=box.SIMPLE)
        table.add_column("编号", style="cyan", width=4)
        table.add_column("服务商", style="bold", width=20)
        table.add_column("官方账号", style="green", width=10)
        table.add_column("本地Key", style="yellow", width=10)
        table.add_column("凭据总数", style="cyan", width=10)
        table.add_column("模型", style="magenta", width=6)
        
        for i, p in enumerate(all_providers, 1):
            p_count = len(profiles.get(p, []))
            m_count = _provider_model_count(p, models, providers_cfg)
            cfg_count = 1 if p in providers_cfg and providers_cfg.get(p, {}).get('apiKey') else 0
            cred_total = p_count + cfg_count
            table.add_row(str(i), p, str(p_count), str(cfg_count), str(cred_total), str(m_count))
        
        console.print(table)
        
        # 操作选项
        console.print()
        console.print("[bold]操作:[/]")
        console.print("  [cyan]N[/] 添加新服务商 (从官方列表)")
        console.print("  [cyan]C[/] 添加自定义服务商")
        console.print("  [cyan]D[/] 删除服务商")
        console.print("  [cyan]R[/] 刷新官方模型池")
        console.print("  [cyan]E[/] 向量化/记忆检索配置")
        console.print("  [cyan]0[/] 返回主菜单")
        console.print()
        
        # 接受大小写，先获取输入再转小写
        choice = Prompt.ask("[bold green]>[/]", default="0").strip().lower()
        
        # 验证输入
        valid_choices = ["0", "n", "c", "d", "r", "e"] + [str(i) for i in range(1, len(all_providers) + 1)]
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
        elif choice == "r":
            console.print("\n[yellow]⏳ 正在刷新官方模型池...[/]")
            ok, info = refresh_official_model_pool()
            if ok:
                console.print(f"[green]✅ 已刷新官方模型池（目录模型数: {info}）[/]")
            else:
                console.print(f"[bold red]❌ 刷新失败: {info}[/]")
            pause_enter()
        elif choice == "e":
            from tui.tools import menu_embeddings
            menu_embeddings()
        elif choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(all_providers):
                menu_provider(all_providers[idx])


def get_providers(providers_cfg: Optional[Dict] = None):
    """获取所有服务商"""
    if providers_cfg is None:
        providers_cfg = get_models_providers_cached()
    profiles = config.get_profiles_by_provider()
    models = config.get_models_by_provider()
    # 合并三处来源：账号、激活模型、models.providers 配置
    all_providers = sorted(set(list(profiles.keys()) + list(models.keys()) + list(providers_cfg.keys())))
    return all_providers, profiles, models


def delete_provider_menu():
    """删除服务商菜单"""
    all_providers, _, _ = get_providers()
    
    if not all_providers:
        console.print("\n[yellow]⚠️ 没有服务商可删除[/]")
        pause_enter()
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
            providers_cfg = get_models_providers_cached()
            if provider in providers_cfg:
                del providers_cfg[provider]
                ok, err = set_provider_config(provider, providers_cfg)
                if ok:
                    invalidate_models_providers_cache()
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
        pause_enter()
        return True
    except Exception as e:
        console.print(f"\n[bold red]❌ 删除失败: {e}[/]")
        pause_enter()
        return False


def add_official_provider():
    """添加官方服务商 (两级目录)"""
    console.clear()
    console.print(Panel(
        Text("➕ 添加服务商 (官方支持)", style="bold cyan", justify="center"),
        box=box.DOUBLE
    ))
    console.print("\n[yellow]⏳ 正在获取 OpenClaw 支持的服务商列表...[/]")
    
    providers = get_official_provider_options()
    
    if not providers:
        console.print("\n[bold red]❌ 无法获取服务商列表，请检查网络或手动添加。[/]")
        pause_enter()
        return
    
    # 按 group 聚合
    groups_map = {}
    for p in providers:
        g = p.get("group", "Other")
        if g not in groups_map:
            groups_map[g] = []
        groups_map[g].append(p)
        
    group_names = list(groups_map.keys())
    auto_group_name = "OpenClaw Auto"
    show_auto_groups = False
    
    while True:
        console.clear()
        console.print(Panel(
            Text("选择服务商平台 (第 1 级)", style="bold cyan", justify="center"),
            box=box.DOUBLE
        ))

        visible_group_names = [
            g for g in group_names
            if show_auto_groups or g != auto_group_name
        ]
        
        # 渲染一级菜单 (Group 列表)
        table = Table(box=box.SIMPLE)
        table.add_column("编号", style="cyan", width=4)
        table.add_column("服务商平台 (Group)", style="bold")
        table.add_column("包含模式数", style="green")

        for i, g_name in enumerate(visible_group_names, 1):
            table.add_row(str(i), g_name, f"{len(groups_map[g_name])} 项")
            
        console.print(table)
        auto_count = len(groups_map.get(auto_group_name, []))
        if auto_count > 0 and not show_auto_groups:
            console.print(f"\n[dim]已默认隐藏自动发现分组: {auto_group_name} ({auto_count} 项)[/]")
            console.print("[cyan]A[/] 展开自动发现分组")
        elif auto_count > 0 and show_auto_groups:
            console.print(f"\n[dim]当前已展开自动发现分组: {auto_group_name} ({auto_count} 项)[/]")
            console.print("[cyan]A[/] 折叠自动发现分组")
        console.print("[cyan]0[/] 取消")
        
        choices = ["0"] + [str(i) for i in range(1, len(visible_group_names) + 1)]
        if auto_count > 0:
            choices.append("a")
        choice = Prompt.ask("[bold green]>[/]", choices=choices, default="0").strip().lower()
        
        if choice == "0":
            break
        elif choice == "a" and auto_count > 0:
            show_auto_groups = not show_auto_groups
            continue
        elif choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(visible_group_names):
                selected_group = visible_group_names[idx]
                # 进入二级菜单
                _add_provider_secondary_menu(selected_group, groups_map[selected_group])

def _add_provider_secondary_menu(group_name: str, group_providers: List[Dict]):
    """二级菜单：选择组内的具体认证方式"""
    page_size = 15
    page = 0
    total_pages = (len(group_providers) - 1) // page_size + 1
    
    while True:
        console.clear()
        console.print(Panel(
            Text(f"【{group_name}】的具体连接方式 - 第 {page+1}/{total_pages} 页", style="bold cyan", justify="center"),
            box=box.DOUBLE
        ))
        
        table = Table(box=box.SIMPLE)
        table.add_column("编号", style="cyan", width=4)
        table.add_column("名 称", style="bold")
        table.add_column("认 证", style="green", width=8)
        table.add_column("说 明", style="dim")
        table.add_column("内部ID", style="dim")
        
        start = page * page_size
        end = min(start + page_size, len(group_providers))
        for i, p in enumerate(group_providers[start:end], start + 1):
            auth_tag = p.get("authType", "API Key")
            table.add_row(str(i), p["label"], auth_tag, p.get("hint",""), p["id"])
            
        console.print(table)
        console.print()
        console.print("[cyan]N[/] 下一页  [cyan]P[/] 上一页  [cyan]B[/] 返回上级  [cyan]0[/] 取消")
        
        choices = ["0", "b", "n", "p"] + [str(i) for i in range(start + 1, end + 1)]
        choice = Prompt.ask("[bold green]>[/]", choices=choices, default="b").strip().lower()
        
        if choice == "0":
            return # Should probably exit entirely, but keeping it simple to just go back to Main Menu or Group menu
        elif choice == "b":
            break # 返回上一级
        elif choice == "n" and end < len(group_providers):
            page += 1
        elif choice == "p" and page > 0:
            page -= 1
        elif choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(group_providers):
                menu_provider(resolve_provider_id(group_providers[idx]["id"]))
                # After configuring a provider, we probably want to return to the main inventory menu.
                # Since menu_provider handles the setup dialog, when it's done, we can just break out
                return


def fetch_provider_list() -> List[str]:
    """从 CLI 获取支持的服务商列表（对齐 onboard）"""
    return sorted({p.get("providerId") or p["id"] for p in get_official_provider_options()})



def ensure_provider_config(providers_cfg: Dict, provider: str) -> Dict:
    """确保 provider 配置结构完整"""
    providers_cfg[provider] = providers_cfg.get(provider, {})
    cfg = providers_cfg[provider]
    # OpenClaw 校验要求 models 为数组
    if "models" not in cfg or not isinstance(cfg["models"], list):
        cfg["models"] = []
    # 基础字段确保存在
    cfg.setdefault("apiKey", "")
    cfg.setdefault("baseUrl", "")
    return cfg


def configure_custom_provider_config(
    provider: str,
    api_proto: str,
    base_url: str,
    api_key: str,
    discover_models: bool = True,
):
    """配置自定义服务商，并可选自动发现模型（失败不影响配置写入）。"""
    provider = normalize_provider_name(provider)
    providers_cfg = get_models_providers_cached()
    ensure_provider_config(providers_cfg, provider)

    providers_cfg[provider]["api"] = api_proto
    providers_cfg[provider]["baseUrl"] = base_url
    providers_cfg[provider]["apiKey"] = api_key

    ok, err = set_provider_config(provider, providers_cfg)
    if not ok:
        return False, err, 0, ""
    invalidate_models_providers_cache()

    if not discover_models or not base_url:
        return True, "", 0, ""

    try:
        discovered = get_custom_models(provider, base_url, api_key)
    except Exception as e:
        return True, "", 0, str(e)

    if not discovered:
        return True, "", 0, "未发现模型"

    normalized_models = []
    for m in discovered:
        key = (m.get("key") or m.get("id") or m.get("name") or "").strip()
        if not key:
            continue
        if key.startswith(f"{provider}/"):
            model_id = key.split("/", 1)[1]
        else:
            model_id = key
        normalized_models.append({
            "id": model_id,
            "name": m.get("name") or model_id,
        })

    if not normalized_models:
        return True, "", 0, "未发现模型"

    providers_cfg = get_models_providers_cached(force_refresh=True)
    ensure_provider_config(providers_cfg, provider)
    # 防止二次写回时覆盖掉刚配置的关键字段（某些实现读取时会隐藏/清空 apiKey）
    providers_cfg[provider]["api"] = api_proto
    providers_cfg[provider]["baseUrl"] = base_url
    providers_cfg[provider]["apiKey"] = api_key
    providers_cfg[provider]["models"] = normalized_models
    ok2, err2 = set_provider_config(provider, providers_cfg)
    if not ok2:
        return True, "", 0, err2 or "模型列表写入失败"
    invalidate_models_providers_cache()
    return True, "", len(normalized_models), ""




def _model_key(provider: str, model: Dict) -> str:
    key = model.get("key") or model.get("id") or model.get("name") or ""
    if not key:
        return ""
    if "/" not in key:
        return f"{provider}/{key}"
    return key


def _activate_model(key: str):
    return activate_model(key)


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
        pause_enter()
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
    explicit_selection_changed = False
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
            # 若用户尚未显式调整选择集，Enter 默认将当前光标模型一并确认。
            # 这样支持“移动到目标模型后直接回车激活”的直觉操作。
            if not explicit_selection_changed and page_items:
                key = _model_key(provider, page_items[cursor])
                if key:
                    selected.add(key)
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
            explicit_selection_changed = True
            continue
        if k in ("a", "A"):
            for m in page_items:
                key = _model_key(provider, m)
                if key:
                    selected.add(key)
            explicit_selection_changed = True
            continue
        if k in ("x", "X"):
            for m in page_items:
                key = _model_key(provider, m)
                if key and key in selected:
                    selected.discard(key)
            explicit_selection_changed = True
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
                explicit_selection_changed = True
            except Exception:
                console.print("[yellow]⚠️ 输入无效[/]")
            continue


        if k in ("m", "M"):
            added_key = add_model_manual_wizard(provider)
            # 刷新列表：若是官方 provider 且已激活模型，补到当前列表便于立刻可见。
            if added_key and added_key not in discovered_keys:
                all_models.append({"key": added_key, "name": added_key.split("/", 1)[1] if "/" in added_key else added_key})
                discovered_keys.add(added_key)
                activated_current.add(added_key)
                selected.add(added_key)
                explicit_selection_changed = True
            continue
    to_add = [k for k in selected if k not in activated_current]
    to_remove = [k for k in activated_current if k not in selected]

    success_add = 0
    failed_add = []
    for k in to_add:
        result = _activate_model(k)
        if isinstance(result, tuple):
            ok, err = result
        else:
            ok, err = bool(result), ""
        if ok:
            success_add += 1
        else:
            failed_add.append((k, err))

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
        console.print("  [dim]" + ", ".join([f"{k}: {e}" for k, e in failed_add[:3]]) + (" ..." if len(failed_add) > 3 else "") + "[/]")
    if failed_remove:
        console.print(f"[bold red]❌ 取消失败 {len(failed_remove)} 个[/]")
        console.print("  [dim]" + ", ".join([f"{k}: {e}" for k,e in failed_remove[:3]]) + (" ..." if len(failed_remove)>3 else "") + "[/]")

    pause_enter()



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
    auto_discover = Confirm.ask("[bold]配置完成后自动发现模型列表?[/]", default=True)

    ok, err, discovered_count, discover_err = configure_custom_provider_config(
        provider=provider,
        api_proto=api_proto,
        base_url=base_url,
        api_key=api_key,
        discover_models=auto_discover,
    )

    if ok:
        console.print(f"\n[green]✅ 已添加/更新服务商: {provider} (协议: {api_proto})[/]")
        if auto_discover:
            if discovered_count > 0:
                console.print(f"  [dim]✅ 已自动发现并写入 {discovered_count} 个模型[/]")
            elif discover_err:
                console.print(f"  [yellow]⚠️ 自动发现未完成: {discover_err}[/]")
                console.print("  [dim]你仍可稍后在「模型管理」里手动自动发现/手动添加。[/]")
            else:
                console.print("  [yellow]⚠️ 未发现模型，可稍后在「模型管理」中重试。[/]")
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
        pause_enter()
        return
    
    provider = normalize_provider_name(provider)
    configure_provider_wizard(provider)
    
    pause_enter()
    menu_provider(provider)


def is_official_provider(provider: str) -> bool:
    """判断是否是官方支持的服务商
    规则：
    1) 若该 provider 已有 auth profile（官方授权产生），判定为官方
    2) 若 provider 在内置官方选项中，判定为官方
    3) 若 provider 存在官方 auth plugin，判定为官方
    4) 其他默认归类为自定义
    """
    provider = normalize_provider_name(provider)

    # 1) auth profile 判断（官方授权后会出现）
    profiles = config.get_profiles_by_provider()
    if provider in profiles and profiles[provider]:
        return True

    # 2) 仅以内置官方选项为准；OpenClaw Auto 分组不参与官方判定
    official_ids = set()
    for g in AUTH_GROUPS:
        for cid in g.get("choices", []):
            if cid == "custom-api-key":
                continue
            opt = BASE_AUTH_OPTIONS.get(cid, {})
            official_ids.add(resolve_provider_id(opt.get("provider", cid)))
    if provider in official_ids:
        return True

    # 3) 插件声明可认证，视为官方 provider
    if provider_auth_plugin_available(provider):
        return True

    # 4) 其他都按自定义处理（包含 OpenClaw Auto 补齐出来的未知 provider）
    return False


def _provider_model_count(provider: str, models_by_provider: Dict, providers_cfg: Dict) -> int:
    """服务商模型数：取已激活模型数与已配置模型数中的较大值。"""
    active_count = len(models_by_provider.get(provider, []))
    configured_models = providers_cfg.get(provider, {}).get("models", [])
    configured_count = len(configured_models) if isinstance(configured_models, list) else 0
    return max(active_count, configured_count)


def reauthorize_provider(provider: str, is_official: bool):
    """重新授权：清空模型/配置后重新配置"""
    ok = delete_provider(provider)
    if not ok:
        return
    if is_official:
        do_official_auth(provider)
    else:
        configure_provider_wizard(provider)
        pause_enter()


def menu_provider(provider: str):
    """单个服务商管理菜单（官方 vs 自定义区分版）"""
    provider = resolve_provider_id(provider)
    while True:
        console.clear()
        console.print(Panel(
            Text(f"⚙️ 服务商管理: {provider}", style="bold cyan", justify="center"),
            box=box.DOUBLE
        ))
        
        # 获取当前状态
        profiles = config.get_profiles_by_provider()
        models = config.get_models_by_provider()
        providers_cfg = get_models_providers_cached()
        
        p_count = len(profiles.get(provider, []))
        active_count = len(models.get(provider, []))
        provider_cfg = providers_cfg.get(provider, {})
        configured_models = provider_cfg.get("models", [])
        pool_count = len(configured_models) if isinstance(configured_models, list) else 0
        
        console.print()
        console.print(f"  [bold]账号数:[/] {p_count}")
        console.print(f"  [bold]已激活:[/] {active_count}")
        if pool_count > 0:
            console.print(f"  [bold]模型池:[/] {pool_count}")
        else:
            console.print("  [bold]模型池:[/] (动态/未缓存)")

        # 显示当前配置
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
        is_oauth = is_oauth_provider(provider)
        plugin_auth_available = is_official and (is_oauth or provider_auth_plugin_available(provider))
        
        if authorized:
            if is_official:
                if is_oauth:
                    console.print("  [cyan]1[/] 重新授权 (调用官方向导)")
                    console.print("  [cyan]2[/] 强制清空配置")
                    console.print("  [cyan]3[/] 模型管理")
                    console.print("  [cyan]0[/] 返回")
                    choices = ["0", "1", "2", "3"]
                else:
                    if plugin_auth_available:
                        console.print("  [cyan]1[/] 运行官方配置向导")
                        console.print("  [cyan]2[/] 更换 API Key")
                        console.print("  [cyan]3[/] 强制清空配置")
                        console.print("  [cyan]4[/] 模型管理")
                        console.print("  [cyan]0[/] 返回")
                        choices = ["0", "1", "2", "3", "4"]
                    else:
                        console.print("  [cyan]1[/] 更换 API Key (推荐)")
                        console.print("  [cyan]2[/] 强制清空配置")
                        console.print("  [cyan]3[/] 模型管理")
                        console.print("  [dim]官方向导不可用: 未检测到 provider auth plugin[/]")
                        console.print("  [cyan]0[/] 返回")
                        choices = ["0", "1", "2", "3"]
            else:
                console.print("  [cyan]1[/] 更换 API Key")
                console.print("  [cyan]2[/] 重新授权 (清空配置+模型)")
                console.print("  [cyan]3[/] 模型管理")
                console.print("  [cyan]0[/] 返回")
                choices = ["0", "1", "2", "3"]
        else:
            if is_official:
                if is_oauth:
                    console.print("  [cyan]1[/] 运行官方配置向导 (推荐)")
                    console.print("  [cyan]2[/] 模型管理")
                    console.print("  [cyan]0[/] 返回")
                    choices = ["0", "1", "2"]
                else:
                    if plugin_auth_available:
                        console.print("  [cyan]1[/] 运行官方配置向导")
                        console.print("  [cyan]2[/] 配置 API Key")
                        console.print("  [cyan]3[/] 模型管理")
                        console.print("  [cyan]0[/] 返回")
                        choices = ["0", "1", "2", "3"]
                    else:
                        console.print("  [cyan]1[/] 配置 API Key (推荐)")
                        console.print("  [cyan]2[/] 模型管理")
                        console.print("  [dim]官方向导不可用: 未检测到 provider auth plugin[/]")
                        console.print("  [cyan]0[/] 返回")
                        choices = ["0", "1", "2"]
            else:
                console.print("  [cyan]1[/] 配置自定义服务商 (协议/BaseURL/API Key)")
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
            if is_official:
                if is_oauth:
                    if choice == "1":
                        do_official_auth(provider)
                    elif choice == "2":
                        reauthorize_provider(provider, is_official)
                    elif choice == "3":
                        manage_models_menu(provider)
                else:
                    if plugin_auth_available:
                        if choice == "1":
                            do_official_auth(provider)
                        elif choice == "2":
                            set_provider_apikey(provider)
                        elif choice == "3":
                            reauthorize_provider(provider, is_official)
                        elif choice == "4":
                            manage_models_menu(provider)
                    else:
                        if choice == "1":
                            set_provider_apikey(provider)
                        elif choice == "2":
                            reauthorize_provider(provider, is_official)
                        elif choice == "3":
                            manage_models_menu(provider)
            else:
                if choice == "1":
                    set_provider_apikey(provider)
                elif choice == "2":
                    reauthorize_provider(provider, is_official)
                elif choice == "3":
                    manage_models_menu(provider)
        else:
            if is_official:
                if is_oauth:
                    if choice == "1":
                        do_official_auth(provider)
                    elif choice == "2":
                        manage_models_menu(provider)
                else:
                    if plugin_auth_available:
                        if choice == "1":
                            do_official_auth(provider)
                        elif choice == "2":
                            set_provider_apikey(provider)
                        elif choice == "3":
                            manage_models_menu(provider)
                    else:
                        if choice == "1":
                            set_provider_apikey(provider)
                        elif choice == "2":
                            manage_models_menu(provider)
            else:
                if choice == "1":
                    configure_provider_wizard(provider)
                    pause_enter()
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
    """执行官方授权流程（完全脱离 Rich Console，让渡终端控制权给原生进程）"""
    provider = resolve_provider_id(provider)
    import os
    # 彻底退出任何 TUI 状态，还回干净的终端环境
    try:
        os.system('clear')
    except:
        pass

    # 非 OAuth provider 若无 auth plugin，直接回退到 API Key 流程，避免无意义报错。
    if (not is_oauth_provider(provider)) and (not provider_auth_plugin_available(provider)):
        print(f"⚠️ 未检测到 [{provider}] 对应的 provider auth plugin，改用 API Key 配置流程。")
        set_provider_apikey(provider)
        return
    
    print(f"👉 正在唤起 OpenClaw 原生配置向导 [{provider}] ...\n")
    print("--------------------------------------------------------------------------------")
    
    # dry-run: 不实际执行授权
    if is_dry_run():
        print("[DRY-RUN] 跳过官方授权执行")
        safe_input("\n按回车键继续...")
        return

    try:
        from core import OPENCLAW_BIN
        import subprocess
        
        # 不使用 capture_output，直接继承当前终端的 stdin/stdout/stderr
        # 这样官方的 inquirer prompt 交互、输入 API Key 都能在控制台正常画出来并获取键盘输入
        cmd = [OPENCLAW_BIN, "models", "auth", "login", "--provider", provider]
        result = subprocess.run(cmd)
        
        print("\n--------------------------------------------------------------------------------")
        if result.returncode == 0:
            print(f"✅ [{provider}] 官方授权/配置流程被成功登出！")
            
            # 由于可能写入了新的配置，建议立即重载配置对象
            import core
            if hasattr(core, 'config'):
                core.config.reload()
                
        else:
            print(f"❌ 流程中断或执行失败 (Exit code: {result.returncode})")
            
    except Exception as e:
        print("\n--------------------------------------------------------------------------------")
        print(f"❌ 调用原生 CLI 失败: {e}")
    
    print()
    safe_input("按回车键返回管理面板...")
    
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
        
    pause_enter()


def set_provider_apikey(provider: str):
    """设置服务商 API Key（官方 provider 走 onboard，其他 provider 走本地配置写入）"""
    provider = resolve_provider_id(provider)
    console.clear()
    console.print(Panel(
        Text(f"🔑 设置 API Key: {provider}", style="bold cyan", justify="center"),
        box=box.DOUBLE
    ))

    # 获取当前遮码显示
    providers_cfg = get_models_providers_cached()
    current = providers_cfg.get(provider, {}).get("apiKey", "")
    masked = current[:8] + "..." if current and len(current) > 8 else current

    console.print()
    console.print(f"  [dim]当前值: {masked or '(未设置)'}[/]")
    console.print("  [dim]直接回车保持不变，输入新值覆盖[/]")
    console.print()

    new_key = Prompt.ask("[bold]请输入 API Key[/]", default=current).strip()
    if not new_key or new_key == current:
        return

    # 备份
    config.reload()
    backup_path = config.backup()
    if backup_path:
        console.print(f"\n  [dim]💡 已备份配置到: {backup_path}[/]")

    is_official = is_official_provider(provider)
    auth_choice = resolve_api_key_auth_choice(provider) if is_official else ""

    if is_official and auth_choice:
        ok, err = apply_official_api_key_via_onboard(provider, auth_choice, new_key)
    else:
        ok, err = upsert_provider_api_key(provider, new_key)

    # OpenClaw 官方流程可能写入 auth-profiles/openclaw.json，刷新本地视图
    config.reload()
    if ok:
        invalidate_models_providers_cache()
        console.print(f"\n[green]✅ API Key 已写入并校验成功: {provider}[/]")
    else:
        console.print(f"\n[bold red]❌ API Key 写入失败[/]")
        console.print(f"  [dim]原因: {_friendly_error_message(err)}[/]")

    pause_enter()




def set_provider_baseurl(provider: str):
    """设置服务商 Base URL"""
    console.clear()
    console.print(Panel(
        Text(f"🌐 设置 Base URL: {provider}", style="bold cyan", justify="center"),
        box=box.DOUBLE
    ))
    
    providers_cfg = get_models_providers_cached()
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
        invalidate_models_providers_cache()
        console.print(f"\n[green]✅ 已更新 Base URL: {provider}[/]")
        if err == "(dry-run)":
            console.print("  [dim]（dry-run：未落盘）[/]")
    else:
        console.print(f"\n[bold red]❌ 更新 Base URL 失败[/]")
        console.print(f"  [dim]原因: {_friendly_error_message(err)}[/]")
    pause_enter()


def set_provider_protocol(provider: str):
    """设置服务商 API 协议"""
    console.clear()
    console.print(Panel(
        Text(f"🔌 设置 API 协议: {provider}", style="bold cyan", justify="center"),
        box=box.DOUBLE
    ))
    
    providers_cfg = get_models_providers_cached()
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
        invalidate_models_providers_cache()
        console.print(f"\n[green]✅ 已更新 API 协议: {new_proto}[/]")
        if err == "(dry-run)":
            console.print("  [dim]（dry-run：未落盘）[/]")
    else:
        console.print(f"\n[bold red]❌ 更新 API 协议失败[/]")
        console.print(f"  [dim]原因: {_friendly_error_message(err)}[/]")
    pause_enter()


def auto_discover_models(provider: str):
    """自动发现模型（从 baseUrl 调用 /v1/models）"""
    console.clear()
    console.print(Panel(
        Text(f"🔍 自动发现模型: {provider}", style="bold cyan", justify="center"),
        box=box.DOUBLE
    ))
    
    providers_cfg = get_models_providers_cached()
    base_url = providers_cfg.get(provider, {}).get("baseUrl", "")
    
    if not base_url:
        console.print("\n[yellow]⚠️ 请先设置 Base URL[/]")
        pause_enter()
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
            else:
                invalidate_models_providers_cache()
            
            console.print("\n发现的模型:")
            for m in discovered[:10]:
                console.print(f"  - {m['id']}")
            if len(discovered) > 10:
                console.print(f"  ... 还有 {len(discovered) - 10} 个")
        else:
            console.print("\n[yellow]⚠️ 未发现模型[/]")
    
    except Exception as e:
        console.print(f"\n[bold red]❌ 自动发现失败: {e}[/]")
    
    pause_enter()


def add_model_manual_wizard(provider: str):
    """手动添加模型引导"""
    mid = safe_input("\n输入模型 ID (如 model-name / gpt-4): ").strip()
    if not mid:
        return None

    provider = resolve_provider_id(provider)

    # 官方 provider 走激活链路，避免触发 models.providers 的 schema 约束（如 openrouter 需要 baseUrl）
    if is_official_provider(provider):
        key = mid if mid.startswith(f"{provider}/") else f"{provider}/{mid}"
        ok, err = activate_model(key)
        if ok:
            console.print(f"[green]✅ 已激活模型: {key}[/]")
            pause_enter()
            return key
        console.print(f"[red]❌ 激活失败: {err}[/]")
        pause_enter()
        return None
    
    providers_cfg = get_models_providers_cached()
    ensure_provider_config(providers_cfg, provider)
    
    # 检查是否已存在
    existing_ids = [m.get("id") for m in providers_cfg[provider]["models"]]
    if mid in existing_ids:
        console.print(f"[yellow]⚠️ 模型 {mid} 已存在[/]")
        return None
        
    providers_cfg[provider]["models"].append({"id": mid, "name": mid})
    ok, err = set_provider_config(provider, providers_cfg)
    if ok:
        invalidate_models_providers_cache()
        console.print(f"[green]✅ 已手动添加模型: {mid}[/]")
        pause_enter()
        return f"{provider}/{mid}" if "/" not in mid else mid
    else:
        console.print(f"[red]❌ 添加失败: {err}[/]")
    
    pause_enter()
    return None


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
    
    pause_enter()


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
            pause_enter()
            return
        
        # 获取当前已激活的模型
        config.reload()
        activated = set(config.data.get("agents", {}).get("defaults", {}).get("models", {}).keys())
        
        activate_models_with_search(provider, all_models, activated)
    
    except Exception as e:
        console.print(f"\n[bold red]❌ 失败: {e}[/]")
    pause_enter()


def manage_models_menu(provider: str):
    """模型管理（搜索/多选激活）"""
    provider = resolve_provider_id(provider)
    console.clear()
    console.print(Panel(
        Text(f"📦 模型管理: {provider}", style="bold cyan", justify="center"),
        box=box.DOUBLE
    ))

    # 官方 provider 优先走 OpenClaw 官方模型目录，避免依赖本地 providers.models/baseUrl。
    if is_official_provider(provider):
        console.print("\n[yellow]⏳ 正在从 OpenClaw 官方目录加载模型...[/]")
        try:
            models = get_official_models(provider)
            if models:
                config.reload()
                activated = set(config.data.get("agents", {}).get("defaults", {}).get("models", {}).keys())
                activate_models_with_search(provider, models, activated)
                return
            console.print("\n[yellow]⚠️ 官方目录未返回模型，回退到本地/自定义发现流程。[/]")
        except Exception as e:
            console.print(f"\n[yellow]⚠️ 官方目录加载失败，回退到本地/自定义发现流程: {e}[/]")

    providers_cfg = get_models_providers_cached()
    models = providers_cfg.get(provider, {}).get("models", [])
    
    if not models:
        console.print("\n[yellow]⏳ 检测到模型列表为空，正在尝试自动发现...[/]")
        auto_discover_models(provider)
        
        # 操作完后重新获取模型
        providers_cfg = get_models_providers_cached(force_refresh=True)
        models = providers_cfg.get(provider, {}).get("models", [])
        
        # 如果还是没有，展示手动引导菜单作为回退
        if not models:
            console.print("\n[yellow]⚠️ 自动同步后仍未发现模型。[/]")
            console.print()
            console.print("  [cyan]1[/] 🔍 重新自动发现 (同步)")
            console.print("  [cyan]2[/] ➕ 手动添加模型")
            console.print("  [cyan]0[/] 返回")
            console.print()
            
            choice = Prompt.ask("[bold green]请选择操作[/]", choices=["0", "1", "2"], default="1")
            if choice == "1":
                auto_discover_models(provider)
            elif choice == "2":
                add_model_manual_wizard(provider)
            else:
                return
                
            # 再次确认
            providers_cfg = get_models_providers_cached(force_refresh=True)
            models = providers_cfg.get(provider, {}).get("models", [])
            if not models:
                return
    
    # 获取当前已激活的模型
    config.reload()
    activated = set(config.data.get("agents", {}).get("defaults", {}).get("models", {}).keys())
    
    activate_models_with_search(provider, models, activated)


if __name__ == "__main__":
    menu_inventory()
