#!/usr/bin/env bash
# EasyClaw 一键构建与环境配置脚本
# 支持 macOS, Linux 及 Docker 环境的配置与拉起

set -e

EASYCLAW_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="$EASYCLAW_DIR/.venv"
LOG_PREFIX="[EasyClaw Setup]"

echo "$LOG_PREFIX 🚀 开始 EasyClaw 一键环境部署..."

# 1. 检查 Python 环境
if ! command -v python3 &> /dev/null; then
    echo "$LOG_PREFIX ❌ 错误: 未找到 Python3, 请先安装 Python (>=3.9)。"
    exit 1
fi

PY_VERSION=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
echo "$LOG_PREFIX ✅ 发现 Python 版本: $PY_VERSION"

# 2. 检查底层的 OpenClaw CLI
# macOS 优先检查 Homebrew，Linux 优先检查全局 PATH，如果实在没有则警告
OPENCLAW_CLI=$(command -v openclaw || true)
if [ -z "$OPENCLAW_CLI" ]; then
    echo "$LOG_PREFIX ⚠️ 警告: 系统中未找到 openclaw 官方命令, EasyClaw 需要挂载或安装官方组件。"
    echo "$LOG_PREFIX 💡 如果你想稍后在 Docker 映射路径也可, 暂时忽略此警告。"
else
    echo "$LOG_PREFIX ✅ 发现底层 OpenClaw 命令: $OPENCLAW_CLI"
fi

# 3. 构建 Python 虚拟环境
if [ ! -d "$VENV_DIR" ]; then
    echo "$LOG_PREFIX 📦 正在创建新虚拟环境: $VENV_DIR"
    python3 -m venv "$VENV_DIR"
fi

# 激活环境
source "$VENV_DIR/bin/activate"

echo "$LOG_PREFIX 🔄 正在安装项目依赖..."
pip install --upgrade pip > /dev/null
pip install fastapi uvicorn rich questionary

# 4. 生成或初始化配置文件，写入默认 Web Token（为了安全默认产生）
cd "$EASYCLAW_DIR"
DEFAULT_WEB_TOKEN=$(python3 -c "import secrets; print(secrets.token_hex(16))")

ENV_FILE=".env.claw"

if [ ! -f "$ENV_FILE" ]; then
    echo "WEB_API_TOKEN=$DEFAULT_WEB_TOKEN" > "$ENV_FILE"
    echo "$LOG_PREFIX 🔐 生成 Web 服务专用安全令牌: $DEFAULT_WEB_TOKEN"
    echo "$LOG_PREFIX 请妥善保存该令牌用于浏览器页面的第一道防线登录！"
else
    echo "$LOG_PREFIX 🔐 已存在配置 .env.claw 文件，保留已有令牌配置。"
fi

# 5. 提醒下一步指令
echo "======================================================"
echo "🎉 EasyClaw 部署依赖准备完毕！"
echo ""
echo "▶️ [1] 启动 TUI (经典终端界面):"
echo "    source $VENV_DIR/bin/activate"
echo "    python $EASYCLAW_DIR/easyclaw.py tui"
echo ""
echo "▶️ [2] 启动 Web 端可视化后台:"
echo "    source $VENV_DIR/bin/activate"
echo "    python $EASYCLAW_DIR/easyclaw.py web"
echo ""
echo "======================================================"
