import subprocess
import os
import json
from typing import Tuple, Any, Optional

from core.backup import create_backup

# MacOS: 检测是不是装在系统 /usr/local/bin 或是 brew /opt/homebrew/bin
POSSIBLE_PATHS = [
    os.environ.get("OPENCLAW_BIN", ""),
    "/usr/local/bin/openclaw",
    "/opt/homebrew/bin/openclaw",
    "openclaw"  # 依赖PATH
]

def find_openclaw_bin() -> str:
    """探索本地底层 CLI 位置"""
    for p in POSSIBLE_PATHS:
        if not p: continue
        # 如果是依赖PATH这种单纯字符 "openclaw"
        if not p.startswith('/'):
            try:
                ret = subprocess.run(["which", p], capture_output=True, text=True)
                if ret.returncode == 0 and ret.stdout.strip():
                    return ret.stdout.strip()
            except Exception:
                pass
        else:
            if os.path.exists(p) and os.access(p, os.X_OK):
                return p
    # 保底
    return "openclaw"

CLI_BIN = find_openclaw_bin()

def safe_exec(args: list[str], require_backup: bool = False, backup_reason: str = "cli_exec") -> Tuple[bool, str, str]:
    """安全的调用原生 OpenClaw 终端命令。
    永远不使用 shell=True，防止注入漏洞。
    
    如果 require_backup=True, 会在实际执行子进程前强行备份环境 config JSON。
    返回: (是否成功: bool, stdout: str, stderr: str)
    """
    if require_backup:
        create_backup(reason=backup_reason)
        
    cmd = [CLI_BIN] + [str(a) for a in args]
    try:
        ret = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            shell=False,  # 绝对禁用
            timeout=120  # 防挂死
        )
        success = (ret.returncode == 0)
        return success, ret.stdout.strip(), ret.stderr.strip()
    except subprocess.TimeoutExpired:
        return False, "", "Execution timeout exceeded 120s"
    except FileNotFoundError:
        return False, "", f"OpenClaw binary not found: {CLI_BIN}"
    except Exception as e:
        return False, "", f"Execution Error: {str(e)}"

def safe_exec_json(args: list[str]) -> Tuple[bool, dict]:
    """安全调用自带 --json 支持的命令行获取结构体"""
    use_args = args.copy()
    if "--json" not in use_args:
        use_args.append("--json")
    
    ok, stdout, stderr = safe_exec(use_args, require_backup=False)
    if not ok:
        return False, {"error": stderr}
    
    if stdout:
        try:
            data = json.loads(stdout)
            return True, data
        except json.JSONDecodeError:
            return False, {"error": "Invalid output format from CLI", "raw": stdout}
            
    return False, {"error": "Empty stdout from JSON instruction"}
