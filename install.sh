#!/usr/bin/env bash
# ClawPanel one-click installer (TUI + Web)
# - Installs current project to $HOME/.openclaw/clawpanel (default)
# - Creates command wrappers: clawpanel, clawtui (with easyclaw/easytui compatibility aliases)
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

usage() {
  cat <<'EOF'
ClawPanel installer

Usage:
  bash install.sh [options]

Options:
  --install-dir <path>    Install ClawPanel into target directory
  --bin-dir <path>        Install wrappers (clawpanel/clawtui + compatibility aliases) into directory
  --openclaw-home <path>  Set OpenClaw home directory
  --target-user <name>    Install for specific user
  --target-home <path>    Home directory for target user
  --auto-deps             Auto-install system dependencies when missing (default)
  --no-auto-deps          Disable auto dependency installation
  --skip-pip              Skip pip dependency installation
  --print-config          Print resolved install config and exit
  -h, --help              Show this help
EOF
}

CLI_INSTALL_DIR=""
CLI_BIN_DIR=""
CLI_OPENCLAW_HOME=""
CLI_TARGET_USER=""
CLI_TARGET_HOME=""
CLI_SKIP_PIP="0"
CLI_AUTO_DEPS="1"
PRINT_CONFIG_ONLY="0"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --install-dir)
      [[ $# -ge 2 ]] || { err "--install-dir requires a path"; exit 1; }
      CLI_INSTALL_DIR="$2"
      shift 2
      ;;
    --bin-dir)
      [[ $# -ge 2 ]] || { err "--bin-dir requires a path"; exit 1; }
      CLI_BIN_DIR="$2"
      shift 2
      ;;
    --openclaw-home)
      [[ $# -ge 2 ]] || { err "--openclaw-home requires a path"; exit 1; }
      CLI_OPENCLAW_HOME="$2"
      shift 2
      ;;
    --target-user)
      [[ $# -ge 2 ]] || { err "--target-user requires a value"; exit 1; }
      CLI_TARGET_USER="$2"
      shift 2
      ;;
    --target-home)
      [[ $# -ge 2 ]] || { err "--target-home requires a path"; exit 1; }
      CLI_TARGET_HOME="$2"
      shift 2
      ;;
    --skip-pip)
      CLI_SKIP_PIP="1"
      shift
      ;;
    --auto-deps)
      CLI_AUTO_DEPS="1"
      shift
      ;;
    --no-auto-deps)
      CLI_AUTO_DEPS="0"
      shift
      ;;
    --print-config)
      PRINT_CONFIG_ONLY="1"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      err "未知参数: $1"
      usage
      exit 1
      ;;
  esac
done

[[ -n "${CLI_INSTALL_DIR}" ]] && EASYCLAW_INSTALL_DIR="${CLI_INSTALL_DIR}"
[[ -n "${CLI_BIN_DIR}" ]] && EASYCLAW_BIN_DIR="${CLI_BIN_DIR}"
[[ -n "${CLI_OPENCLAW_HOME}" ]] && OPENCLAW_HOME="${CLI_OPENCLAW_HOME}"
[[ -n "${CLI_TARGET_USER}" ]] && EASYCLAW_TARGET_USER="${CLI_TARGET_USER}"
[[ -n "${CLI_TARGET_HOME}" ]] && EASYCLAW_TARGET_HOME="${CLI_TARGET_HOME}"
[[ "${CLI_SKIP_PIP}" == "1" ]] && EASYCLAW_SKIP_PIP="1"
EASYCLAW_AUTO_DEPS="${CLI_AUTO_DEPS}"

SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
is_docker="no"
if [[ -f "/.dockerenv" ]]; then
  is_docker="yes"
fi

os_name="$(uname -s || true)"

detect_package_manager() {
  local managers=(apt-get dnf yum apk pacman zypper brew)
  local manager
  for manager in "${managers[@]}"; do
    if command -v "${manager}" >/dev/null 2>&1; then
      echo "${manager}"
      return 0
    fi
  done
  echo ""
}

run_package_install() {
  local manager="$1"
  shift
  local packages=("$@")
  if [[ ${#packages[@]} -eq 0 ]]; then
    return 0
  fi

  local prefix=()
  if [[ "${EUID}" -ne 0 ]]; then
    if command -v sudo >/dev/null 2>&1; then
      prefix=(sudo)
    else
      err "缺少 sudo，无法自动安装依赖: ${packages[*]}"
      return 1
    fi
  fi

  case "${manager}" in
    apt-get)
      "${prefix[@]}" apt-get update -y >/dev/null
      "${prefix[@]}" apt-get install -y "${packages[@]}" >/dev/null
      ;;
    dnf)
      "${prefix[@]}" dnf install -y "${packages[@]}" >/dev/null
      ;;
    yum)
      "${prefix[@]}" yum install -y "${packages[@]}" >/dev/null
      ;;
    apk)
      "${prefix[@]}" apk add --no-cache "${packages[@]}" >/dev/null
      ;;
    pacman)
      "${prefix[@]}" pacman -Sy --noconfirm "${packages[@]}" >/dev/null
      ;;
    zypper)
      "${prefix[@]}" zypper --non-interactive install "${packages[@]}" >/dev/null
      ;;
    brew)
      brew install "${packages[@]}" >/dev/null
      ;;
    *)
      err "不支持的包管理器: ${manager}"
      return 1
      ;;
  esac
}

python3_has_venv() {
  if ! command -v python3 >/dev/null 2>&1; then
    return 1
  fi
  if ! python3 -c "import venv" >/dev/null 2>&1; then
    return 1
  fi
  python3 -m ensurepip --version >/dev/null 2>&1
}

ensure_python_runtime() {
  local missing_python="0"
  local missing_venv="0"
  local want_auto="${EASYCLAW_AUTO_DEPS:-1}"

  if ! command -v python3 >/dev/null 2>&1; then
    missing_python="1"
  fi
  if ! python3_has_venv; then
    missing_venv="1"
  fi
  if [[ "${missing_python}" == "0" && "${missing_venv}" == "0" ]]; then
    return 0
  fi

  if [[ "${want_auto}" != "1" ]]; then
    if [[ "${missing_python}" == "1" ]]; then
      err "未找到 python3，请先安装 Python 3.10+"
    else
      err "检测到 python3 缺少可用的 venv/ensurepip，请先安装 python3-venv"
    fi
    return 1
  fi

  local manager
  manager="$(detect_package_manager)"
  if [[ -z "${manager}" ]]; then
    err "无法识别包管理器，无法自动安装依赖。请先安装 python3 与 python3-venv。"
    return 1
  fi

  local packages=()
  case "${manager}" in
    apt-get)
      [[ "${missing_python}" == "1" ]] && packages+=("python3")
      [[ "${missing_venv}" == "1" ]] && packages+=("python3-venv")
      ;;
    dnf|yum)
      [[ "${missing_python}" == "1" || "${missing_venv}" == "1" ]] && packages+=("python3")
      ;;
    apk)
      [[ "${missing_python}" == "1" || "${missing_venv}" == "1" ]] && packages+=("python3" "py3-pip")
      ;;
    pacman)
      [[ "${missing_python}" == "1" || "${missing_venv}" == "1" ]] && packages+=("python")
      ;;
    zypper)
      [[ "${missing_python}" == "1" || "${missing_venv}" == "1" ]] && packages+=("python3")
      ;;
    brew)
      [[ "${missing_python}" == "1" || "${missing_venv}" == "1" ]] && packages+=("python")
      ;;
  esac

  if [[ ${#packages[@]} -eq 0 ]]; then
    err "无法计算可安装的 python 依赖包，请手动安装 python3 与 python3-venv。"
    return 1
  fi

  info "检测到缺失依赖，尝试自动安装: ${packages[*]}"
  if ! run_package_install "${manager}" "${packages[@]}"; then
    err "自动安装依赖失败，请手动安装后重试。"
    return 1
  fi
  ok "系统依赖安装完成: ${packages[*]}"

  if ! command -v python3 >/dev/null 2>&1; then
    err "自动安装后仍未找到 python3，请手动检查。"
    return 1
  fi
  if ! python3_has_venv; then
    err "自动安装后 python3 仍缺少可用的 venv/ensurepip，请手动安装 python3-venv。"
    return 1
  fi
}

if ! command -v openclaw >/dev/null 2>&1; then
  warn "未检测到 openclaw CLI，ClawPanel 的官方能力将不可用。"
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
DEFAULT_INSTALL_DIR="${OPENCLAW_HOME}/clawpanel"
LEGACY_INSTALL_DIR="${OPENCLAW_HOME}/easyclaw"
if [[ -n "${EASYCLAW_INSTALL_DIR:-}" ]]; then
  INSTALL_DIR="${EASYCLAW_INSTALL_DIR}"
elif [[ -d "${DEFAULT_INSTALL_DIR}" ]]; then
  INSTALL_DIR="${DEFAULT_INSTALL_DIR}"
elif [[ -d "${LEGACY_INSTALL_DIR}" ]]; then
  INSTALL_DIR="${LEGACY_INSTALL_DIR}"
else
  INSTALL_DIR="${DEFAULT_INSTALL_DIR}"
fi
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

if [[ "${PRINT_CONFIG_ONLY}" == "1" ]]; then
  cat <<EOF
SRC_DIR=${SRC_DIR}
TARGET_USER=${TARGET_USER}
TARGET_HOME=${TARGET_HOME}
OPENCLAW_HOME=${OPENCLAW_HOME}
INSTALL_DIR=${INSTALL_DIR}
BIN_DIR=${BIN_DIR}
RUNTIME_ENV_FILE=${RUNTIME_ENV_FILE}
EASYCLAW_SKIP_PIP=${EASYCLAW_SKIP_PIP:-0}
EASYCLAW_AUTO_DEPS=${EASYCLAW_AUTO_DEPS:-1}
EOF
  exit 0
fi

ensure_python_runtime

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
# rsync --delete 可能会移除 INSTALL_DIR 内的 bin 子目录，这里兜底重建。
mkdir -p "${BIN_DIR}"

VENV_DIR="${INSTALL_DIR}/.venv"
create_virtualenv() {
  info "创建虚拟环境: ${VENV_DIR}"
  if python3 -m venv "${VENV_DIR}"; then
    return 0
  fi

  if [[ "${EASYCLAW_AUTO_DEPS:-1}" == "1" ]]; then
    warn "虚拟环境创建失败，尝试修复系统 Python 运行时后重试。"
    if ensure_python_runtime && python3 -m venv "${VENV_DIR}"; then
      return 0
    fi
  fi

  err "创建虚拟环境失败。请确认 python3-venv 可用后重试。"
  return 1
}

if [[ ! -d "${VENV_DIR}" ]]; then
  create_virtualenv
fi

PY_BIN="${VENV_DIR}/bin/python3"

if [[ ! -x "${PY_BIN}" ]]; then
  warn "检测到虚拟环境不完整，重建: ${VENV_DIR}"
  rm -rf "${VENV_DIR}"
  create_virtualenv
  PY_BIN="${VENV_DIR}/bin/python3"
fi

ensure_venv_pip() {
  if "${PY_BIN}" -m pip --version >/dev/null 2>&1; then
    return 0
  fi

  info "虚拟环境缺少 pip，尝试修复..."
  "${PY_BIN}" -m ensurepip --upgrade >/dev/null 2>&1 || true

  if "${PY_BIN}" -m pip --version >/dev/null 2>&1; then
    return 0
  fi

  if [[ "${EASYCLAW_AUTO_DEPS:-1}" == "1" ]]; then
    warn "尝试安装缺失的 Python venv 依赖并重建虚拟环境..."
    if ensure_python_runtime; then
      rm -rf "${VENV_DIR}"
      create_virtualenv || return 1
      PY_BIN="${VENV_DIR}/bin/python3"
      "${PY_BIN}" -m ensurepip --upgrade >/dev/null 2>&1 || true
      if "${PY_BIN}" -m pip --version >/dev/null 2>&1; then
        return 0
      fi
    fi
  fi

  err "虚拟环境中 pip 不可用。请先安装 python3-venv（Debian/Ubuntu）后重试。"
  return 1
}

if [[ "${EASYCLAW_SKIP_PIP:-0}" == "1" ]]; then
  warn "跳过依赖安装 (EASYCLAW_SKIP_PIP=1)"
else
  ensure_venv_pip
  info "安装 Python 依赖..."
  "${PY_BIN}" -m pip install --upgrade pip >/dev/null
  "${PY_BIN}" -m pip install rich questionary fastapi uvicorn jinja2 pydantic >/dev/null
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
OPENCLAW_HOME_DETECTED="$(dirname "${OPENCLAW_CONFIG_DETECTED}")"
OPENCLAW_BIN_DETECTED="$(command -v openclaw 2>/dev/null || true)"
if [[ -z "${OPENCLAW_BIN_DETECTED}" ]]; then
  OPENCLAW_BIN_DETECTED="/usr/local/bin/openclaw"
fi
MAIN_AGENT_DIR_DETECTED="${OPENCLAW_HOME_DETECTED}/agents/main/agent"
MAIN_SESSIONS_DIR_DETECTED="${OPENCLAW_HOME_DETECTED}/agents/main/sessions"
MAIN_WORKSPACE_DETECTED="${OPENCLAW_HOME_DETECTED}/workspace"

mkdir -p "$(dirname "${OPENCLAW_CONFIG_DETECTED}")"
mkdir -p "${OPENCLAW_BACKUP_DIR_DETECTED}"
mkdir -p "${MAIN_AGENT_DIR_DETECTED}" "${MAIN_SESSIONS_DIR_DETECTED}" "${MAIN_WORKSPACE_DETECTED}"

if [[ ! -f "${OPENCLAW_CONFIG_DETECTED}" ]]; then
  warn "未发现 openclaw.json，创建最小骨架: ${OPENCLAW_CONFIG_DETECTED}"
  cat > "${OPENCLAW_CONFIG_DETECTED}" <<'JSON'
{
  "gateway": {
    "mode": "local"
  },
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
    "list": [
      {
        "id": "main",
        "workspace": "__MAIN_WORKSPACE__",
        "agentDir": "__MAIN_AGENT_DIR__"
      }
    ]
  },
  "auth": {
    "profiles": {}
  },
  "models": {
    "providers": {}
  }
}
JSON
  "${PY_BIN}" - <<PY
from pathlib import Path
config_path = Path(r"${OPENCLAW_CONFIG_DETECTED}")
text = config_path.read_text(encoding="utf-8")
text = text.replace("__MAIN_WORKSPACE__", r"${MAIN_WORKSPACE_DETECTED}")
text = text.replace("__MAIN_AGENT_DIR__", r"${MAIN_AGENT_DIR_DETECTED}")
config_path.write_text(text, encoding="utf-8")
PY
fi

cat > "${RUNTIME_ENV_FILE}" <<EOF
OPENCLAW_CONFIG_PATH=${OPENCLAW_CONFIG_DETECTED}
OPENCLAW_BACKUP_DIR=${OPENCLAW_BACKUP_DIR_DETECTED}
OPENCLAW_AUTH_PROFILES_PATH=${OPENCLAW_AUTH_PROFILES_DETECTED}
OPENCLAW_BIN=${OPENCLAW_BIN_DETECTED}
EASYCLAW_SANDBOX=0
EOF
ok "运行时配置已写入 ${RUNTIME_ENV_FILE}"

cat > "${BIN_DIR}/clawpanel" <<EOF
#!/usr/bin/env bash
set -euo pipefail
CLAWPANEL_DIR="${INSTALL_DIR}"
if [[ -f "\${CLAWPANEL_DIR}/.env.runtime" ]]; then
  set -a
  source "\${CLAWPANEL_DIR}/.env.runtime"
  set +a
fi
exec "\${CLAWPANEL_DIR}/.venv/bin/python3" "\${CLAWPANEL_DIR}/easyclaw.py" "\$@"
EOF
chmod +x "${BIN_DIR}/clawpanel"

cat > "${BIN_DIR}/clawtui" <<EOF
#!/usr/bin/env bash
set -euo pipefail
exec "${BIN_DIR}/clawpanel" tui "\$@"
EOF
chmod +x "${BIN_DIR}/clawtui"

# Compatibility aliases for existing users/tools.
cat > "${BIN_DIR}/easyclaw" <<EOF
#!/usr/bin/env bash
set -euo pipefail
exec "${BIN_DIR}/clawpanel" "\$@"
EOF
chmod +x "${BIN_DIR}/easyclaw"

cat > "${BIN_DIR}/easytui" <<EOF
#!/usr/bin/env bash
set -euo pipefail
exec "${BIN_DIR}/clawtui" "\$@"
EOF
chmod +x "${BIN_DIR}/easytui"

if [[ "${EUID}" -eq 0 && "${TARGET_USER}" != "root" ]]; then
  chown -R "${TARGET_USER}:${TARGET_GROUP}" "${OPENCLAW_HOME}"
  if [[ "${BIN_DIR}" == "${TARGET_HOME}"* ]]; then
    chown -R "${TARGET_USER}:${TARGET_GROUP}" "${BIN_DIR}"
  fi
fi

ok "命令已注册: ${BIN_DIR}/clawpanel, ${BIN_DIR}/clawtui（兼容别名: easyclaw, easytui）"

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
echo "  ${BIN_DIR}/clawpanel tui"
echo "  ${BIN_DIR}/clawpanel web            # 默认 4231"
echo "  ${BIN_DIR}/clawpanel web --port 5001"
echo "  ${BIN_DIR}/clawtui"
echo "  （兼容）${BIN_DIR}/easyclaw tui"
echo "============================"
