"""
config 命令 - 配置管理
"""
import json
from core import config, run_cli, run_cli_json
from utils.logger import log


def cmd_config(args, env: dict):
    """执行 config 命令"""
    
    if args.config_action == "get":
        _get_config(args)
    elif args.config_action == "set":
        _set_config(args)
    elif args.config_action == "list":
        _list_config(args)
    else:
        print("未知操作")


def _get_config(args):
    """获取配置"""
    # 获取剩余参数作为 key
    key = args.key if hasattr(args, 'key') else None
    
    if not key:
        # 交互式获取
        key = input("请输入配置 key (如 agents.defaults.model): ").strip()
        if not key:
            print("❌ 未指定 key")
            return
    
    result = run_cli_json(["config", "get", key])
    
    if "error" in result:
        print(f"❌ 获取失败: {result['error']}")
    else:
        print(json.dumps(result, indent=2, ensure_ascii=False))


def _set_config(args):
    """设置配置"""
    key = args.key if hasattr(args, 'key') else None
    value = args.value if hasattr(args, 'value') else None
    
    if not key:
        key = input("请输入配置 key: ").strip()
    if not value:
        value = input("请输入配置 value: ").strip()
    
    if not key:
        print("❌ 未指定 key")
        return
    
    # 尝试 JSON 解析
    try:
        json_val = json.dumps(json.loads(value)) if value else ""
        stdout, stderr, code = run_cli(["config", "set", key, json_val, "--json"])
    except json.JSONDecodeError:
        # 字符串值
        stdout, stderr, code = run_cli(["config", "set", key, value])
    
    if code == 0:
        print(f"✅ 已设置 {key} = {value}")
        print("💡 重启服务后生效")
        log("config.set", f"设置配置: {key} = {value}")
    else:
        print(f"❌ 设置失败: {stderr}")
        log("config.set", f"设置失败: {key} - {stderr}", "ERROR")


def _list_config(args):
    """列出配置"""
    result = run_cli_json(["config", "list"])
    
    if "error" in result:
        print(f"❌ 获取失败: {result['error']}")
    else:
        print(json.dumps(result, indent=2, ensure_ascii=False))
