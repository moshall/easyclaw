import sys
import os
import uvicorn
from core.sandbox import is_sandbox_enabled

def print_help():
    print("EasyClaw 统一管理入口")
    print("用法：")
    print("  python easyclaw.py tui   --- 进入命令行双向互动系统")
    print("  python easyclaw.py web   --- 启动带鉴权的可视化网页端服务器")
    print()
    if is_sandbox_enabled():
        print("当前已开启 [Sandbox] 隔离模式。")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print_help()
        sys.exit(1)
        
    cmd = sys.argv[1].lower()
    
    if cmd == "tui":
        # 默认走稳定模式（cli.py），面板模式需显式开启
        tui_mode = (os.environ.get("EASYCLAW_TUI_MODE", "classic") or "classic").strip().lower()
        if tui_mode == "panel":
            from app import main as panel_main
            panel_main()
        else:
            from cli import main as classic_main
            classic_main()

    elif cmd == "web":
        print("🚀 启动轻量级 Web 鉴权服务器...")
        uvicorn.run("web.app:app", host="0.0.0.0", port=8080, reload=True)
        
    else:
        print(f"❌ 未知指令: {cmd}")
        print_help()
