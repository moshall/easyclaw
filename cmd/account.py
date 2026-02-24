"""
account 命令 - 账号管理
"""
from core import config, run_cli
from utils.logger import log


def cmd_account(args, env: dict):
    """执行 account 命令"""
    
    if args.account_action == "list":
        _list_accounts(args)
    elif args.account_action == "add":
        _add_account(args)
    else:
        print("未知操作")


def _list_accounts(args):
    """列出账号"""
    profiles = config.get_profiles_by_provider()
    
    if not profiles:
        print("📭 尚未绑定任何账号")
        return
    
    print("🔑 已绑定账号:")
    for provider, accounts in profiles.items():
        print(f"\n  {provider}:")
        for p in accounts:
            display = p.get('email') or p.get('_key', '').split(':')[-1]
            mode = p.get('mode', 'token')
            mode_label = "OAuth" if mode == "oauth" else "API Key"
            print(f"    • {display} ({mode_label})")


def _add_account(args):
    """添加账号"""
    provider = args.provider
    
    print(f"🔐 正在启动 {provider} 认证流程...")
    print()
    
    # 根据认证类型选择
    if args.type == "api-key":
        run_cli(["models", "auth", "paste-token", "--provider", provider], capture=False)
    elif args.type == "oauth":
        run_cli(["models", "auth", "login", "--provider", provider], capture=False)
    elif args.type == "token":
        run_cli(["models", "auth", "paste-token", "--provider", provider], capture=False)
    else:
        # 默认尝试
        run_cli(["models", "auth", "login", "--provider", provider], capture=False)
    
    print()
    print("💡 账号变更需要重启服务后生效")
    log("account.add", f"添加账号: {provider}")
