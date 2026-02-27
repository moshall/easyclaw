#!/usr/bin/env bash
# EasyClaw one-click installer (TUI + Web)
# - Installs current project to /root/.openclaw/easyclaw
# - Creates command wrappers: easyclaw, easytui
# - Auto-detects OpenClaw config path and exports runtime env

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

info() { echo -e "${BLUE}[INFO]${NC} $*"; }
ok() { echo -e "${GREEN}[OK]${NC} $*"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }
err() { echo -e "${RED}[ERROR]${NC} $*"; }

if [[ "${EUID}" -ne 0 ]]; then
  err "请使用 root 运行安装脚本（目标目录固定为 /root/.openclaw/easyclaw）"
  err "示例: sudo bash install.sh"
  exit 1
fi

SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="${EASYCLAW_INSTALL_DIR:-/root/.openclaw/easyclaw}"
OPENCLAW_HOME="/root/.openclaw"
RUNTIME_ENV_FILE="${INSTALL_DIR}/.env.runtime"

is_docker="no"
if [[ -f "/.dockerenv" ]]; then
  is_docker="yes"
fi

os_name="$(uname -s || true)"
info "环境检测: os=${os_name}, docker=${is_docker}, src=${SRC_DIR}"
info "安装目录: ${INSTALL_DIR}"

if ! command -v python3 >/dev/null 2>&1; then
  err "未找到 python3，请先安装 Python 3.10+"
  exit 1
fi

if ! command -v pip3 >/dev/null 2>&1; then
  err "未找到 pip3，请先安装 pip"
  exit 1
fi

if ! command -v openclaw >/dev/null 2>&1; then
  warn "未检测到 openclaw CLI，EasyClaw 的官方能力将不可用。"
fi

mkdir -p "${INSTALL_DIR}"
mkdir -p "${OPENCLAW_HOME}"

copy_project() {
  if [[ "${SRC_DIR}" == "${INSTALL_DIR}" ]]; then
    warn "源码目录与安装目录相同，跳过复制。"
    return 0
  fi

  if command -v rsync >/dev/null 2>&1; then
    rsync -a --delete \
      --exclude ".git" \
      --exclude "__pycache__" \
      --exclude ".pytest_cache" \
      --exclude ".venv" \
      --exclude "openclaw_src" \
      --exclude "sandbox" \
      "${SRC_DIR}/" "${INSTALL_DIR}/"
  else
    (cd "${SRC_DIR}" && tar --exclude=".git" --exclude="__pycache__" --exclude=".pytest_cache" --exclude=".venv" --exclude="openclaw_src" --exclude="sandbox" -cf - .) \
      | (cd "${INSTALL_DIR}" && tar -xf -)
  fi
}

copy_project
ok "项目文件已同步到 ${INSTALL_DIR}"

VENV_DIR="${INSTALL_DIR}/.venv"
if [[ ! -d "${VENV_DIR}" ]]; then
  info "创建虚拟环境: ${VENV_DIR}"
  python3 -m venv "${VENV_DIR}"
fi

PY_BIN="${VENV_DIR}/bin/python3"
PIP_BIN="${VENV_DIR}/bin/pip"

info "安装 Python 依赖..."
"${PIP_BIN}" install --upgrade pip >/dev/null
"${PIP_BIN}" install rich questionary fastapi uvicorn jinja2 pydantic >/dev/null
ok "依赖安装完成"

detect_openclaw_config() {
  local candidates=()
  if [[ -n "${OPENCLAW_CONFIG_PATH:-}" ]]; then
    candidates+=("${OPENCLAW_CONFIG_PATH}")
  fi
  candidates+=(
    "/root/.openclaw/openclaw.json"
    "/home/${SUDO_USER:-root}/.openclaw/openclaw.json"
    "/home/${USER:-root}/.openclaw/openclaw.json"
  )
  for p in "${candidates[@]}"; do
    if [[ -n "${p}" && -f "${p}" ]]; then
      echo "${p}"
      return 0
    fi
  done
  echo "/root/.openclaw/openclaw.json"
}

OPENCLAW_CONFIG_DETECTED="$(detect_openclaw_config)"
OPENCLAW_BACKUP_DIR_DETECTED="$(dirname "${OPENCLAW_CONFIG_DETECTED}")/backups"
OPENCLAW_AUTH_PROFILES_DETECTED="$(dirname "${OPENCLAW_CONFIG_DETECTED}")/agents/main/agent/auth-profiles.json"

mkdir -p "$(dirname "${OPENCLAW_CONFIG_DETECTED}")"
mkdir -p "${OPENCLAW_BACKUP_DIR_DETECTED}"

if [[ ! -f "${OPENCLAW_CONFIG_DETECTED}" ]]; then
  warn "未发现 openclaw.json，创建最小骨架: ${OPENCLAW_CONFIG_DETECTED}"
  cat > "${OPENCLAW_CONFIG_DETECTED}" <<'JSON'
{
  "agents": {
    "defaults": {
      "model": {
        "primary": "",
        "fallbacks": []
      },
      "models": {},
      "subagents": {
        "maxConcurrent": 8
      }
    },
    "list": []
  },
  "auth": {
    "profiles": {}
  },
  "models": {
    "providers": {}
  }
}
JSON
fi

cat > "${RUNTIME_ENV_FILE}" <<EOF
OPENCLAW_CONFIG_PATH=${OPENCLAW_CONFIG_DETECTED}
OPENCLAW_BACKUP_DIR=${OPENCLAW_BACKUP_DIR_DETECTED}
OPENCLAW_AUTH_PROFILES_PATH=${OPENCLAW_AUTH_PROFILES_DETECTED}
EASYCLAW_SANDBOX=0
EOF
ok "运行时配置已写入 ${RUNTIME_ENV_FILE}"

cat > /usr/local/bin/easyclaw <<EOF
#!/usr/bin/env bash
set -euo pipefail
EASYCLAW_DIR="${INSTALL_DIR}"
if [[ -f "\${EASYCLAW_DIR}/.env.runtime" ]]; then
  set -a
  source "\${EASYCLAW_DIR}/.env.runtime"
  set +a
fi
exec "\${EASYCLAW_DIR}/.venv/bin/python3" "\${EASYCLAW_DIR}/easyclaw.py" "\$@"
EOF
chmod +x /usr/local/bin/easyclaw

cat > /usr/local/bin/easytui <<EOF
#!/usr/bin/env bash
set -euo pipefail
exec easyclaw tui "\$@"
EOF
chmod +x /usr/local/bin/easytui

ok "命令已注册: easyclaw, easytui"
echo
echo "========== 安装完成 =========="
echo "安装目录: ${INSTALL_DIR}"
echo "OpenClaw 配置: ${OPENCLAW_CONFIG_DETECTED}"
echo
echo "使用方式:"
echo "  easyclaw tui"
echo "  easyclaw web            # 默认 4231"
echo "  easyclaw web --port 5001"
echo "  easytui"
echo "============================"
