import sys
import os
from core.sandbox import is_sandbox_enabled

DEFAULT_WEB_PORT = 4231


def _read_env(*names: str, default: str = "") -> str:
    for name in names:
        value = str(os.environ.get(name, "") or "").strip()
        if value:
            return value
    return default


def _parse_int_port(raw: str, fallback: int) -> int:
    text = str(raw or "").strip()
    if not text:
        return fallback
    try:
        value = int(text)
    except ValueError:
        return fallback
    if 1 <= value <= 65535:
        return value
    return fallback


def _resolve_web_port(args: list[str]) -> int:
    port = _parse_int_port(_read_env("CLAWPANEL_WEB_PORT", "EASYCLAW_WEB_PORT"), DEFAULT_WEB_PORT)
    idx = 0
    while idx < len(args):
        token = str(args[idx] or "").strip().lower()
        if token in ("--port", "-p"):
            if idx + 1 < len(args):
                port = _parse_int_port(args[idx + 1], port)
            break
        idx += 1
    return port


def _resolve_web_reload() -> bool:
    raw = _read_env("CLAWPANEL_WEB_RELOAD", "EASYCLAW_WEB_RELOAD", default="1").lower()
    return raw not in ("0", "false", "no", "off")


def _start_web_server(port: int, reload_enabled: bool) -> None:
    import uvicorn

    uvicorn.run("web.app:app", host="0.0.0.0", port=port, reload=reload_enabled)


def print_help():
    print("ClawPanel 统一管理入口")
    print("用法：")
    print("  clawpanel tui   --- 进入稳定模式 TUI（数字输入）")
    print("  clawpanel web [--port 4231]   --- 启动带鉴权的可视化网页端服务器")
    print("  （兼容）easyclaw tui / easyclaw web")
    print("环境变量：")
    print("  CLAWPANEL_WEB_PORT     --- 自定义 Web 端口（默认 4231）")
    print("  CLAWPANEL_WEB_RELOAD   --- 1/0 控制是否开启自动重载（默认 1）")
    print("  EASYCLAW_TUI_MODE      --- 兼容变量（panel 已废弃，将自动使用稳定模式）")
    print(f"  EASYCLAW_WEB_PORT      --- 兼容 CLAWPANEL_WEB_PORT（默认 {DEFAULT_WEB_PORT}）")
    print("  EASYCLAW_WEB_RELOAD    --- 兼容 CLAWPANEL_WEB_RELOAD（默认 1）")
    print()
    if is_sandbox_enabled():
        print("当前已开启 [Sandbox] 隔离模式。")


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv
    if len(args) < 2:
        print_help()
        return 1

    cmd = str(args[1] or "").lower()

    if cmd == "tui":
        tui_mode = (os.environ.get("EASYCLAW_TUI_MODE", "") or "").strip().lower()
        if tui_mode == "panel":
            print("⚠️ EASYCLAW_TUI_MODE=panel 已废弃，自动使用稳定模式 TUI。")
        from cli import main as classic_main
        classic_main()
        return 0

    elif cmd == "web":
        port = _resolve_web_port(args[2:])
        reload_enabled = _resolve_web_reload()
        print("🚀 启动轻量级 Web 鉴权服务器...")
        _start_web_server(port=port, reload_enabled=reload_enabled)
        return 0

    else:
        print(f"❌ 未知指令: {cmd}")
        print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
