#!/usr/bin/env bash
# EasyClaw one-click installer (TUI + Web)
# - Installs current project to $HOME/.openclaw/easyclaw (default)
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

SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
is_docker="no"
if [[ -f "/.dockerenv" ]]; then
  is_docker="yes"
fi

os_name="$(uname -s || true)"

if ! command -v python3 >/dev/null 2>&1; then
  err "未找到 python3，请先安装 Python 3.10+"
  exit 1
fi

if ! command -v openclaw >/dev/null 2>&1; then
  warn "未检测到 openclaw CLI，EasyClaw 的官方能力将不可用。"
fi

resolve_target_user() {
  if [[ -n "${EASYCLAW_TARGET_USER:-}" ]]; then
    echo "${EASYCLAW_TARGET_USER}"
    return 0
  fi
  if [[ "${EUID}" -eq 0 && -n "${SUDO_USER:-}" && "${SUDO_USER}" != "root" ]]; then
    echo "${SUDO_USER}"
    return 0
  fi
  id -un
}

resolve_target_home() {
  if [[ -n "${EASYCLAW_TARGET_HOME:-}" ]]; then
    echo "${EASYCLAW_TARGET_HOME}"
    return 0
  fi
  local user="$1"
  if [[ "${user}" == "root" ]]; then
    echo "/root"
    return 0
  fi
  local user_home
  user_home="$(eval "echo ~${user}" 2>/dev/null || true)"
  if [[ -n "${user_home}" && "${user_home}" != "~${user}" ]]; then
    echo "${user_home}"
    return 0
  fi
  echo "${HOME}"
}

TARGET_USER="$(resolve_target_user)"
TARGET_HOME="$(resolve_target_home "${TARGET_USER}")"
TARGET_GROUP="$(id -gn "${TARGET_USER}" 2>/dev/null || echo "${TARGET_USER}")"

OPENCLAW_HOME="${OPENCLAW_HOME:-${TARGET_HOME}/.openclaw}"
INSTALL_DIR="${EASYCLAW_INSTALL_DIR:-${OPENCLAW_HOME}/easyclaw}"
RUNTIME_ENV_FILE="${INSTALL_DIR}/.env.runtime"

if [[ -n "${EASYCLAW_BIN_DIR:-}" ]]; then
  BIN_DIR="${EASYCLAW_BIN_DIR}"
elif [[ "${EUID}" -eq 0 ]]; then
  BIN_DIR="/usr/local/bin"
else
  BIN_DIR="${TARGET_HOME}/.local/bin"
fi

info "环境检测: os=${os_name}, docker=${is_docker}, src=${SRC_DIR}"
info "目标用户: ${TARGET_USER} (${TARGET_HOME})"
info "安装目录: ${INSTALL_DIR}"
info "命令目录: ${BIN_DIR}"

mkdir -p "${INSTALL_DIR}"
mkdir -p "${OPENCLAW_HOME}"
mkdir -p "${BIN_DIR}"

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

if [[ "${EASYCLAW_SKIP_PIP:-0}" == "1" ]]; then
  warn "跳过依赖安装 (EASYCLAW_SKIP_PIP=1)"
else
  info "安装 Python 依赖..."
  "${PIP_BIN}" install --upgrade pip >/dev/null
  "${PIP_BIN}" install rich questionary fastapi uvicorn jinja2 pydantic >/dev/null
  ok "依赖安装完成"
fi

detect_openclaw_config() {
  local candidates=()
  if [[ -n "${OPENCLAW_CONFIG_PATH:-}" ]]; then
    candidates+=("${OPENCLAW_CONFIG_PATH}")
  fi
  candidates+=("${OPENCLAW_HOME}/openclaw.json")
  candidates+=(
    "/root/.openclaw/openclaw.json"
    "/home/${TARGET_USER}/.openclaw/openclaw.json"
    "/Users/${TARGET_USER}/.openclaw/openclaw.json"
  )
  for p in "${candidates[@]}"; do
    if [[ -n "${p}" && -f "${p}" ]]; then
      echo "${p}"
      return 0
    fi
  done
  echo "${OPENCLAW_HOME}/openclaw.json"
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

cat > "${BIN_DIR}/easyclaw" <<EOF
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
chmod +x "${BIN_DIR}/easyclaw"

cat > "${BIN_DIR}/easytui" <<EOF
#!/usr/bin/env bash
set -euo pipefail
exec easyclaw tui "\$@"
EOF
chmod +x "${BIN_DIR}/easytui"

if [[ "${EUID}" -eq 0 && "${TARGET_USER}" != "root" ]]; then
  chown -R "${TARGET_USER}:${TARGET_GROUP}" "${OPENCLAW_HOME}"
  if [[ "${BIN_DIR}" == "${TARGET_HOME}"* ]]; then
    chown -R "${TARGET_USER}:${TARGET_GROUP}" "${BIN_DIR}"
  fi
fi

ok "命令已注册: ${BIN_DIR}/easyclaw, ${BIN_DIR}/easytui"

if [[ ":${PATH}:" != *":${BIN_DIR}:"* ]]; then
  local_rc="${TARGET_HOME}/.bashrc"
  if [[ "${os_name}" == "Darwin" ]]; then
    local_rc="${TARGET_HOME}/.zprofile"
  fi
  warn "当前 PATH 未包含 ${BIN_DIR}，请执行："
  echo "  export PATH=\"${BIN_DIR}:\$PATH\""
  warn "可追加到 ${local_rc}"
fi

echo
echo "========== 安装完成 =========="
echo "安装目录: ${INSTALL_DIR}"
echo "命令目录: ${BIN_DIR}"
echo "OpenClaw 配置: ${OPENCLAW_CONFIG_DETECTED}"
echo
echo "使用方式:"
echo "  ${BIN_DIR}/easyclaw tui"
echo "  ${BIN_DIR}/easyclaw web            # 默认 4231"
echo "  ${BIN_DIR}/easyclaw web --port 5001"
echo "  ${BIN_DIR}/easytui"
echo "============================"
