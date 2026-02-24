"""
install 命令 - 一键安装/更新 EasyClaw
"""
import os
import sys
import subprocess
import shutil

# 安装目标路径
TARGET_DIR = "/root/.openclaw/software/easyclaw"
BIN_LINK = "/usr/local/bin/easyclaw"
SCRIPT_SOURCE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "cli.py")


def detect_os() -> dict:
    """检测操作系统"""
    info = {
        "os": sys.platform,
        "distro": "",
        "has_python": False,
        "python_version": "",
        "has_pip": False,
    }
    
    # Python 检测
    try:
        result = subprocess.run(["python3", "--version"], capture_output=True, text=True)
        info["has_python"] = True
        info["python_version"] = result.stdout.strip()
    except FileNotFoundError:
        pass
    
    try:
        result = subprocess.run(["pip3", "--version"], capture_output=True, text=True)
        info["has_pip"] = True
    except FileNotFoundError:
        pass
    
    # Linux 发行版检测
    if info["os"] == "linux":
        if os.path.exists("/etc/debian_version"):
            info["distro"] = "debian"
        elif os.path.exists("/etc/centos-release"):
            info["distro"] = "centos"
        elif os.path.exists("/etc/redhat-release"):
            info["distro"] = "rhel"
        elif os.path.exists("/etc/arch-release"):
            info["distro"] = "arch"
        else:
            info["distro"] = "linux"
    
    return info


def check_dependencies() -> list:
    """检查依赖"""
    missing = []
    
    # 检查 Python
    if not shutil.which("python3"):
        missing.append("python3")
    
    # 检查 openclaw CLI
    if not shutil.which("openclaw"):
        missing.append("openclaw")
    
    return missing


def cmd_install(args, env: dict):
    """执行安装"""
    print("🚀 EasyClaw 安装程序".center(60, "="))
    print()
    
    # 1. 环境检测
    print("📋 检测环境...")
    os_info = detect_os()
    print(f"  操作系统: {os_info['distro']} ({os_info['os']})")
    print(f"  Python: {os_info['python_version'] or '未找到'}")
    
    # Docker 检测
    is_docker = os.path.exists("/.dockerenv") or os.path.exists("/proc/1/cgroup")
    print(f"  运行环境: {'Docker 容器' if is_docker else '宿主机'}")
    
    # 2. 依赖检查
    print()
    print("📦 检查依赖...")
    missing = check_dependencies()
    
    if missing:
        print(f"  ⚠️ 缺少依赖: {', '.join(missing)}")
        if "python3" in missing:
            print()
            print("请先安装 Python 3:")
            if os_info["distro"] in ["debian", "ubuntu"]:
                print("  sudo apt update && sudo apt install python3 python3-pip")
            elif os_info["distro"] in ["centos", "rhel"]:
                sudo = "sudo" if os.geteuid() != 0 else ""
                print(f"  {sudo} yum install python3 python3-pip")
        print()
        print("❌ 无法继续安装")
        return False
    
    print("  ✅ 所有依赖已满足")
    
    # 3. 创建目标目录
    print()
    print(f"📁 准备安装到: {TARGET_DIR}")
    
    if os.path.exists(TARGET_DIR) and not args.force:
        print(f"  ⚠️ 目标目录已存在")
        response = input("  是否覆盖? [y/N]: ").strip().lower()
        if response != 'y':
            print("❌ 安装取消")
            return False
    
    os.makedirs(TARGET_DIR, exist_ok=True)
    
    # 4. 复制文件
    print()
    print("📦 复制文件...")
    
    source_dir = os.path.dirname(os.abspath(__file.path.dirname(os.path__)))
    
    for item in os.listdir(source_dir):
        src = os.path.join(source_dir, item)
        dst = os.path.join(TARGET_DIR, item)
        
        if os.path.isdir(src):
            if os.path.exists(dst):
                shutil.rmtree(dst)
            shutil.copytree(src, dst)
        elif item.endswith('.py'):
            shutil.copy2(src, dst)
        
        print(f"  ✓ {item}")
    
    # 5. 创建符号链接
    print()
    print("🔗 创建命令链接...")
    
    cli_path = os.path.join(TARGET_DIR, "cli.py")
    
    # 移除旧链接
    if os.path.exists(BIN_LINK) or os.path.islink(BIN_LINK):
        os.remove(BIN_LINK)
    
    # 创建新链接
    try:
        os.symlink(cli_path, BIN_LINK)
        print(f"  ✓ {BIN_LINK}")
    except PermissionError:
        # 需要 root 权限
        print(f"  ⚠️ 需要 sudo 权限创建链接")
        result = subprocess.run(["sudo", "ln", "-sf", cli_path, BIN_LINK])
        if result.returncode == 0:
            print(f"  ✓ {BIN_LINK} (sudo)")
        else:
            print(f"  ❌ 创建链接失败")
    
    # 6. 验证安装
    print()
    print("✅ 安装完成!")
    print()
    print("📖 使用方法:")
    print(f"  easyclaw tui          # 启动 TUI 菜单")
    print(f"  easyclaw status      # 查看资产状态")
    print(f"  easyclaw models list # 列出模型")
    print(f"  easyclaw --help      # 查看帮助")
    print()
    
    return True


def cmd_install_wrapper(args, env):
    cmd_install(args, env)
