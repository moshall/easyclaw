"""
status 命令 - 资产大盘
"""
import json
import os
from datetime import datetime
from core import run_cli, run_cli_json, config
from core.agent_runtime import resolve_agent_runtime_paths
from utils.logger import log


def cmd_status(args, env: dict):
    """执行 status 命令"""
    
    # 读取 auth-profiles.json 获取账号状态
    auth_profiles = _load_auth_profiles()
    
    if args.json:
        # JSON 模式输出完整状态
        status = run_cli_json(["status"])
        status["auth_profiles"] = auth_profiles
        print(json.dumps(status, indent=2, ensure_ascii=False))
        return
    
    # 人类可读格式
    status = run_cli_json(["status"])
    
    if args.usage:
        usage = run_cli_json(["status", "--usage"])
        _print_usage(usage, auth_profiles)
    else:
        _print_summary(status, auth_profiles)


def _load_auth_profiles() -> dict:
    """直接读取 auth-profiles.json"""
    auth_path = resolve_agent_runtime_paths("main", config.path)["auth_profiles"]
    if not os.path.exists(auth_path):
        return {}
    try:
        with open(auth_path) as f:
            data = json.load(f)
        return data.get("profiles", {})
    except Exception:
        return {}


def _print_summary(status: dict, auth_profiles: dict):
    """打印摘要"""
    print("📊 资产大盘".center(50, "─"))
    print()
    
    # 账号状态 - 从 auth-profiles.json 读取
    print("🔑 账号状态:")
    if not auth_profiles:
        print("  (尚未绑定任何账号)")
    else:
        for key, info in auth_profiles.items():
            provider = info.get("provider", "unknown")
            ptype = info.get("type", "unknown")
            email = info.get("email", "")
            
            if ptype == "oauth":
                expires = info.get("expires", 0)
                remaining = expires - int(datetime.now().timestamp() * 1000)
                if remaining > 86400000:
                    time_str = f"{remaining // 86400000}天"
                elif remaining > 3600000:
                    time_str = f"{remaining // 3600000}小时"
                elif remaining > 0:
                    time_str = f"{remaining // 60000}分钟"
                else:
                    time_str = "已过期"
                display = f"{email} ({time_str})" if email else time_str
            else:
                display = "API Key"
            
            icon = "🔑" if ptype == "oauth" else "🔐"
            print(f"  {icon} {provider}: {display}")
    
    print()
    
    # 模型状态 - 从配置读取
    models = config.get_all_models_flat()
    default = status.get("defaultModel", "未设置")
    print(f"🤖 已激活模型 ({len(models)} 个):")
    print(f"  默认: {default}")
    if models:
        # 显示前5个
        for m in models[:5]:
            print(f"  • {m['display']}")
        if len(models) > 5:
            print(f"  ... 还有 {len(models) - 5} 个")
    
    print()
    print("💡 使用 --usage 查看用量详情")


def _print_usage(usage: dict, auth_profiles: dict = None):
    """打印用量信息"""
    print("📈 用量配额".center(50, "─"))
    print()
    
    providers = usage.get("usage", {}).get("providers", [])
    if not providers:
        print("  (无用量数据)")
        return
    
    for p in providers:
        name = p.get("displayName") or p.get("provider", "?")
        plan = p.get("plan", "")
        title = f"{name} ({plan})" if plan else name
        print(f"┌─ {title} ─" + "─" * (40 - len(title)))
        
        for w in p.get("windows", []):
            label = w.get("label", "")
            used = w.get("usedPercent", 0)
            left = max(0, 100 - int(used))
            reset = w.get("resetAt")
            reset_str = ""
            if reset:
                dt = datetime.fromtimestamp(reset / 1000)
                reset_str = f" | 重置: {dt.strftime('%m-%d %H:%M')}"
            
            bar = "█" * (left // 5) + "░" * (20 - left // 5)
            print(f"│ {label}: [{bar}] {left}%{reset_str}")
        
        print()
