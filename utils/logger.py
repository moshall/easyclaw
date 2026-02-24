"""
EasyClaw 日志模块 - 操作历史记录
"""
import os
import json
from datetime import datetime
from pathlib import Path

LOG_DIR = "/root/.openclaw/logs"
LOG_FILE = os.path.join(LOG_DIR, "easyclaw.log")


def ensure_log_dir():
    """确保日志目录存在"""
    if not os.path.exists(LOG_DIR):
        os.makedirs(LOG_DIR, exist_ok=True)


def log(action: str, detail: str = "", level: str = "INFO"):
    """记录操作日志
    
    Args:
        action: 操作类型 (如 "models.add", "account.list")
        detail: 详细描述
        level: 日志级别 (INFO/WARN/ERROR)
    """
    ensure_log_dir()
    
    entry = {
        "timestamp": datetime.now().isoformat(),
        "level": level,
        "action": action,
        "detail": detail,
    }
    
    try:
        with open(LOG_FILE, "a") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass  # 日志失败不中断主流程


def get_recent_logs(count: int = 20) -> list:
    """获取最近的操作日志
    
    Args:
        count: 返回条数
    """
    if not os.path.exists(LOG_FILE):
        return []
    
    logs = []
    try:
        with open(LOG_FILE, "r") as f:
            lines = f.readlines()
        
        for line in reversed(lines[-count:]):
            try:
                logs.append(json.loads(line.strip()))
            except json.JSONDecodeError:
                continue
    except Exception:
        pass
    
    return list(reversed(logs))


def print_recent_logs(count: int = 10):
    """打印最近的操作日志"""
    logs = get_recent_logs(count)
    
    if not logs:
        print("暂无操作记录")
        return
    
    print(f"📜 最近 {len(logs)} 条操作记录:")
    print("─" * 50)
    
    for entry in logs:
        ts = entry.get("timestamp", "")[:19]
        action = entry.get("action", "")
        detail = entry.get("detail", "")
        level = entry.get("level", "INFO")
        
        icon = {
            "INFO": "•",
            "WARN": "⚠️",
            "ERROR": "❌"
        }.get(level, "•")
        
        print(f"{icon} [{ts}] {action}")
        if detail:
            print(f"   {detail}")
    
    print("─" * 50)


def clear_logs():
    """清空日志"""
    if os.path.exists(LOG_FILE):
        os.remove(LOG_FILE)
        print("✅ 日志已清空")
    else:
        print("📭 无日志可清空")
