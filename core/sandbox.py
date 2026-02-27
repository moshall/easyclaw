import os

def is_sandbox_enabled() -> bool:
    """是否启用了保护主机的沙箱模式"""
    return os.environ.get("EASYCLAW_SANDBOX", "0") == "1"

def get_sandbox_paths() -> dict:
    """若是沙箱模式，将所有底层配置文件挂载到本项目内的 sandbox/ 隔离目录"""
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sb_dir = os.path.join(base_dir, "sandbox")
    
    if not os.path.exists(sb_dir):
        os.makedirs(sb_dir, exist_ok=True)
        # 初始化沙盒基础目录和 mock 配置
        os.makedirs(os.path.join(sb_dir, "backups"), exist_ok=True)
        # 写一个空的假装 openclaw.json 的骨架
        with open(os.path.join(sb_dir, "openclaw.json"), "w") as f:
            f.write('{"agents":{"defaults":{"models":{}}},"auth":{"profiles":{}}}')
            
    return {
        "OPENCLAW_CONFIG_PATH": os.path.join(sb_dir, "openclaw.json"),
        "OPENCLAW_BACKUP_DIR": os.path.join(sb_dir, "backups"),
        "OPENCLAW_AUTH_PROFILES_PATH": os.path.join(sb_dir, "auth-profiles.json"),
    }

# 初始化系统环境变量时应用隔离保护策略
if is_sandbox_enabled():
    print("[Sandbox] 🛡️ 启用宿主隔离模式，配置和执行挂载在 ./sandbox 临时沙盒目录。")
    paths = get_sandbox_paths()
    for k, v in paths.items():
        # 这里重写 os.environ, 其他导入的模块如果是动态读 os.environ.get 就能拿沙盒路径
        os.environ[k] = v
