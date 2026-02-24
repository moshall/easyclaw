"""
logs 命令 - 查看操作历史
"""
from utils.logger import print_recent_logs, clear_logs, get_recent_logs
import json


def cmd_logs(args, env: dict):
    """执行 logs 命令"""
    
    if args.clear:
        clear_logs()
        return
    
    count = args.count
    if args.json:
        logs = get_recent_logs(count)
        print(json.dumps(logs, indent=2, ensure_ascii=False))
    else:
        print_recent_logs(count)


def add_logs_parser(subparsers):
    """添加 logs 子命令"""
    logs_parser = subparsers.add_parser("logs", help="查看操作历史")
    logs_parser.add_argument("--count", type=int, default=10, help="显示条数")
    logs_parser.add_argument("--json", action="store_true", help="JSON 格式输出")
    logs_parser.add_argument("--clear", action="store_true", help="清空日志")
    logs_parser.set_defaults(func="logs")
    return logs_parser
