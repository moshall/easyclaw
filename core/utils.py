"""
提供与控制台交互和公共异常包装相关的基础函数
"""
from rich.console import Console

console = Console()

def safe_input(prompt: str = "") -> str:
    """安全的捕获终端输入，避免 Ctr+C 或 EOF 错误导致程序彻底异常退出"""
    try:
        return input(prompt)
    except (EOFError, KeyboardInterrupt):
        return ""

def pause_enter(message: str = "\n[dim]按回车键继续...[/]"):
    """通用的等待回车停顿提示"""
    console.print(message)
    safe_input()
