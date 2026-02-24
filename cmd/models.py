"""
models 命令 - 模型管理
"""
import json
from core import config, run_cli, run_cli_json
from utils.logger import log


def cmd_models(args, env: dict):
    """执行 models 命令"""
    
    if args.models_action == "list":
        _list_models(args)
    elif args.models_action == "add":
        _add_model(args)
    elif args.models_action == "remove":
        _remove_model(args)
    elif args.models_action == "auth":
        _auth_model(args)
    else:
        print("未知操作")


def _list_models(args):
    """列出模型"""
    if args.all:
        # 显示所有可用模型
        provider = args.provider or ""
        result = run_cli_json(["models", "list", "--all"] + (["--provider", provider] if provider else []))
        models = result.get("models", [])
        
        print(f"📦 可用模型 ({len(models)} 个):")
        for m in models:
            key = m.get("key", "")
            name = m.get("name", "")
            available = "✅" if m.get("available") else "❌"
            print(f"  {available} {key}: {name}")
    else:
        # 显示已激活模型
        models = config.get_all_models_flat()
        
        if args.json:
            print(json.dumps(models, indent=2, ensure_ascii=False))
            return
        
        print("🤖 已激活模型:")
        if not models:
            print("  (无)")
        else:
            for m in models:
                print(f"  • {m['display']}")


def _add_model(args):
    """激活模型"""
    model_key = args.model_key
    
    # 使用 CLI 设置
    if args.url:
        stdout, stderr, code = run_cli([
            "config", "set", 
            f'agents.defaults.models["{model_key}"]', 
            json.dumps({"baseUrl": args.url}),
            "--json"
        ])
    else:
        stdout, stderr, code = run_cli([
            "config", "set", 
            f'agents.defaults.models["{model_key}"]', 
            "{}"
        ])
    
    if code == 0:
        print(f"✅ 模型 {model_key} 已激活")
        print("💡 重启服务后生效")
        log("models.add", f"激活模型: {model_key}")
    else:
        print(f"❌ 激活失败: {stderr}")
        log("models.add", f"激活失败: {model_key} - {stderr}", "ERROR")


def _remove_model(args):
    """取消激活模型"""
    model_key = args.model_key
    
    stdout, stderr, code = run_cli([
        "config", "unset",
        f'agents.defaults.models["{model_key}"]'
    ])
    
    if code == 0:
        print(f"✅ 模型 {model_key} 已取消激活")
        print("💡 重启服务后生效")
        log("models.remove", f"取消激活: {model_key}")
    else:
        print(f"❌ 取消激活失败: {stderr}")
        log("models.remove", f"取消激活失败: {model_key} - {stderr}", "ERROR")


def _auth_model(args):
    """模型认证"""
    provider = args.provider
    
    # 启动认证流程
    print(f"🔐 正在启动 {provider} 认证流程...")
    run_cli(["models", "auth", "login", "--provider", provider], capture=False)


# 保持向后兼容
def cmd_models_wrapper(args, env):
    cmd_models(args, env)
