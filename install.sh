#!/bin/bash
# EasyClaw 一键部署脚本（无脑版）
# 自动判断环境、安装依赖、启动服务，用户无需干预

set -e

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 脚本所在目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
print_info "脚本目录: $SCRIPT_DIR"

# 默认安装目录
INSTALL_DIR="${EASYCLAW_INSTALL_DIR:-/opt/easyclaw}"
print_info "安装目录: $INSTALL_DIR"

# 检查是否为 root
if [[ $EUID -ne 0 ]]; then
    print_warning "未以 root 运行，部分操作可能需要 sudo"
fi

# ========== 步骤 1：检查环境 ==========
print_info "========== 步骤 1：检查环境 =========="

# 检查 Python3
if ! command -v python3 &> /dev/null; then
    print_error "未找到 Python3，请先安装 Python3"
    exit 1
fi
PYTHON_VERSION=$(python3 --version | awk '{print $2}')
print_success "Python3 已安装: $PYTHON_VERSION"

# 检查 pip3
if ! command -v pip3 &> /dev/null; then
    print_error "未找到 pip3，请先安装 pip3"
    exit 1
fi
print_success "pip3 已安装"

# 检查 OpenClaw CLI
if ! command -v openclaw &> /dev/null; then
    print_warning "未找到 OpenClaw CLI，请先安装 OpenClaw"
fi

# ========== 步骤 2：安装依赖 ==========
print_info "========== 步骤 2：安装依赖 =========="

print_info "正在安装 Python 依赖（rich, questionary, fastapi, uvicorn, jinja2）..."
pip3 install --break-system-packages rich questionary fastapi uvicorn jinja2
print_success "Python 依赖安装完成"

# ========== 步骤 3：部署项目文件 ==========
print_info "========== 步骤 3：部署项目文件 =========="

# 创建安装目录
print_info "创建安装目录: $INSTALL_DIR"
mkdir -p "$INSTALL_DIR"

# 复制项目文件
print_info "复制项目文件..."
cp -r "$SCRIPT_DIR"/* "$INSTALL_DIR/"
chmod +x "$INSTALL_DIR/cli.py" "$INSTALL_DIR/app.py" "$INSTALL_DIR/webui/main.py"
print_success "项目文件已部署"

# ========== 步骤 4：创建命令行 wrapper ==========
print_info "========== 步骤 4：创建命令行 wrapper =========="

# 创建 easyclaw 命令
cat > /usr/local/bin/easyclaw << 'EOF'
#!/bin/bash
# EasyClaw 启动脚本
# 支持经典版和高级版两种模式

EASYCLAW_DIR="/opt/easyclaw"
CLASSIC_CLI="$EASYCLAW_DIR/cli.py"
ADVANCED_APP="$EASYCLAW_DIR/app.py"

# 判断使用哪个版本
if [[ "$1" == "--app" || "$1" == "--advanced" ]]; then
    # 高级版
    shift
    export TERM=xterm-256color
    if command -v python3 &> /dev/null; then
        exec python3 "$ADVANCED_APP" "$@"
    else
        echo "未找到 Python3" >&2
        exit 1
    fi
else
    # 经典版（默认）
    if command -v python3 &> /dev/null; then
        export TERM=dumb
        exec python3 "$CLASSIC_CLI" "$@"
    else
        echo "未找到 Python3" >&2
        exit 1
    fi
fi
EOF

# 创建 easyclaw-app 命令
cat > /usr/local/bin/easyclaw-app << 'EOF'
#!/bin/bash
# EasyClaw 高级版启动脚本
export TERM=xterm-256color
EASYCLAW_DIR="/opt/easyclaw"
exec python3 "$EASYCLAW_DIR/app.py" "$@"
EOF

# 创建 easyclaw-webui 命令
cat > /usr/local/bin/easyclaw-webui << 'EOF'
#!/bin/bash
# EasyClaw Web UI 启动脚本
EASYCLAW_DIR="/opt/easyclaw"
export TERM=xterm-256color
cd "$EASYCLAW_DIR/webui"
exec python3 main.py "$@"
EOF

# 加执行权限
chmod +x /usr/local/bin/easyclaw /usr/local/bin/easyclaw-app /usr/local/bin/easyclaw-webui
print_success "命令行 wrapper 已创建"

# ========== 步骤 5：检测环境并启动服务 ==========
print_info "========== 步骤 5：检测环境并启动服务 =========="

# 检测是否在 Docker 环境
IN_DOCKER=false
if [ -f /.dockerenv ] || grep -q "docker" /proc/1/cgroup 2>/dev/null; then
    IN_DOCKER=true
    print_info "检测到 Docker 环境"
fi

# 检测是否有 systemd 并正在运行
HAS_SYSTEMD=false
if command -v systemctl &> /dev/null && pidof systemd &> /dev/null; then
    HAS_SYSTEMD=true
    print_info "检测到 systemd 正在运行"
fi

# ========== 启动 Web UI ==========
print_info "正在启动 EasyClaw Web UI..."

if [ "$HAS_SYSTEMD" = true ] && [ "$IN_DOCKER" = false ]; then
    # 非 Docker + systemd 环境：创建并启动 systemd 服务
    print_info "使用 systemd 服务启动 Web UI"
    
    cat > /etc/systemd/system/easyclaw-webui.service << 'EOF'
[Unit]
Description=EasyClaw Web UI
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/easyclaw/webui
ExecStart=/usr/bin/python3 /opt/easyclaw/webui/main.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF
    
    # 重载 systemd，启动服务并设置开机自启
    systemctl daemon-reload
    systemctl start easyclaw-webui
    systemctl enable easyclaw-webui
    print_success "systemd 服务已创建并启动，开机自启已启用"
    
else
    # Docker 或非 systemd 环境：用 nohup 后台启动
    print_info "使用 nohup 后台启动 Web UI"
    
    # 创建日志目录
    mkdir -p /var/log/easyclaw
    
    # 杀掉可能存在的旧进程
    pkill -f "python3.*easyclaw/webui/main.py" 2>/dev/null || true
    
    # 后台启动
    nohup python3 "$INSTALL_DIR/webui/main.py" > /var/log/easyclaw/webui.log 2>&1 &
    WEBUI_PID=$!
    
    # 保存 PID 到文件
    echo $WEBUI_PID > /var/run/easyclaw-webui.pid
    
    print_success "Web UI 已在后台启动 (PID: $WEBUI_PID)"
    print_info "日志文件: /var/log/easyclaw/webui.log"
fi

# ========== 完成 ==========
print_success "========== 一键安装完成！=========="
echo ""
echo "🚀 使用方式："
echo "  - 经典版 CLI: easyclaw"
echo "  - 高级版 CLI: easyclaw --app 或 easyclaw-app"
echo "  - Web UI: http://localhost:2001"
echo ""
if [ "$HAS_SYSTEMD" = true ] && [ "$IN_DOCKER" = false ]; then
    echo "📦 systemd 服务已启动并设置开机自启"
    echo "   查看状态: systemctl status easyclaw-webui"
else
    echo "📦 Web UI 已在后台运行"
    echo "   查看日志: tail -f /var/log/easyclaw/webui.log"
fi
echo ""
