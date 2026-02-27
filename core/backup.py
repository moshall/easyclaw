import os
import subprocess
import shutil
from datetime import datetime

# 加载沙箱安全拦截
from core import sandbox

# 动态获取，不能写死，以兼容从 sandbox 初始化注入的 os.environ
def _get_env_path(key: str, default: str) -> str:
    return os.environ.get(key, default)

# 环境变量及基础路径优先获取 (每次调用时动态取，由于 python module 缓存)
DEFAULT_CONFIG_PATH = _get_env_path("OPENCLAW_CONFIG_PATH", "/root/.openclaw/openclaw.json")
DEFAULT_BACKUP_DIR = _get_env_path("OPENCLAW_BACKUP_DIR", "/root/.openclaw/backups")
# 根据是否有 Docker 环境变量识别
IS_DOCKER = os.path.exists("/.dockerenv")

def get_backup_path(timestamp_str: str) -> str:
    """获取格式化的备份快照路径"""
    return os.path.join(DEFAULT_BACKUP_DIR, f"openclaw_bkp_{timestamp_str}.json")

def create_backup(reason: str = "manual") -> str:
    """强制备份系统核心状态 JSON，返回备份文件的绝对路径"""
    conf_path = _get_env_path("OPENCLAW_CONFIG_PATH", "/root/.openclaw/openclaw.json")
    bkp_dir = _get_env_path("OPENCLAW_BACKUP_DIR", "/root/.openclaw/backups")
    
    if not os.path.exists(bkp_dir):
        try:
            os.makedirs(bkp_dir, exist_ok=True)
        except Exception as e:
            print(f"[Backup] Failed to create backup dir: {e}")
            return ""

    if not os.path.exists(conf_path):
        return ""

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    b_path = os.path.join(bkp_dir, f"openclaw_bkp_{timestamp}.json")
    
    try:
        shutil.copy2(conf_path, b_path)
    except Exception as e:
        print(f"[Backup Error] Failed to backup to {b_path}: {e}")
        return ""
        
    # 我们可以在备份同级写一个 metadata file 或者在文件名尾部体现 reason，这里从简
    return b_path

def rollback_config(target_backup_file: str) -> bool:
    """回滚配置到指定快照"""
    conf_path = _get_env_path("OPENCLAW_CONFIG_PATH", "/root/.openclaw/openclaw.json")
    if not os.path.exists(target_backup_file):
        print(f"[Rollback Error] Backup file {target_backup_file} not found.")
        return False
        
    try:
        # 回滚前再做一次防呆备份
        create_backup(reason="pre-rollback")
        shutil.copy2(target_backup_file, conf_path)
        return True
    except Exception as e:
        print(f"[Rollback Error] Failed: {e}")
        return False

def list_backups() -> list[str]:
    """仅列出有效的 JSON 备份文件"""
    bkp_dir = _get_env_path("OPENCLAW_BACKUP_DIR", "/root/.openclaw/backups")
    if not os.path.exists(bkp_dir):
        return []
    files = []
    for f in os.listdir(bkp_dir):
        if f.endswith(".json") and f.startswith("openclaw_bkp_"):
            files.append(os.path.join(bkp_dir, f))
    # 按照修改时间倒序（最新的在前）
    return sorted(files, key=os.path.getmtime, reverse=True)
