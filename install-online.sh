#!/usr/bin/env bash
# EasyClaw online bootstrap installer
# Example:
#   curl -fsSL https://raw.githubusercontent.com/moshall/easyclaw/main/install-online.sh | bash -s -- --install-dir /opt/easyclaw

set -euo pipefail

usage() {
  cat <<'EOF'
EasyClaw online installer

Usage:
  bash install-online.sh [bootstrap-options] [install-options...]

Bootstrap options:
  --repo <owner/name>   GitHub repo slug (default: moshall/easyclaw)
  --ref <git-ref>       Branch/tag/commit (default: main)
  --auto-deps           Auto-install missing system dependencies (default)
  --no-auto-deps        Disable auto dependency installation
  --keep-temp           Keep temp source directory after install
  --dry-run             Print resolved archive URL and forwarded args, then exit
  -h, --help            Show this help

Install options:
  Any other options are forwarded to install.sh
  e.g. --install-dir /data/easyclaw --bin-dir /usr/local/bin
EOF
}

REPO_SLUG="${EASYCLAW_REPO_SLUG:-moshall/easyclaw}"
REF="${EASYCLAW_REF:-main}"
AUTO_DEPS="${EASYCLAW_AUTO_DEPS:-1}"
KEEP_TEMP="0"
DRY_RUN="0"
FORWARD_ARGS=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo)
      [[ $# -ge 2 ]] || { echo "[ERROR] --repo requires a value" >&2; exit 1; }
      REPO_SLUG="$2"
      shift 2
      ;;
    --ref)
      [[ $# -ge 2 ]] || { echo "[ERROR] --ref requires a value" >&2; exit 1; }
      REF="$2"
      shift 2
      ;;
    --keep-temp)
      KEEP_TEMP="1"
      shift
      ;;
    --auto-deps)
      AUTO_DEPS="1"
      FORWARD_ARGS+=("--auto-deps")
      shift
      ;;
    --no-auto-deps)
      AUTO_DEPS="0"
      FORWARD_ARGS+=("--no-auto-deps")
      shift
      ;;
    --dry-run)
      DRY_RUN="1"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      FORWARD_ARGS+=("$1")
      shift
      ;;
  esac
done

ARCHIVE_URL="${EASYCLAW_ARCHIVE_URL:-https://codeload.github.com/${REPO_SLUG}/tar.gz/${REF}}"

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
      echo "[ERROR] missing sudo, cannot auto-install: ${packages[*]}" >&2
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
      echo "[ERROR] unsupported package manager: ${manager}" >&2
      return 1
      ;;
  esac
}

ensure_command() {
  local cmd="$1"
  shift
  local package_candidates=("$@")
  if command -v "${cmd}" >/dev/null 2>&1; then
    return 0
  fi
  if [[ "${AUTO_DEPS}" != "1" ]]; then
    echo "[ERROR] ${cmd} not found. Please install it first." >&2
    return 1
  fi
  local manager
  manager="$(detect_package_manager)"
  if [[ -z "${manager}" ]]; then
    echo "[ERROR] ${cmd} missing and no supported package manager found." >&2
    return 1
  fi
  echo "[INFO] Missing ${cmd}. Trying auto install via ${manager}: ${package_candidates[*]}"
  if ! run_package_install "${manager}" "${package_candidates[@]}"; then
    echo "[ERROR] Failed to install dependency: ${cmd}" >&2
    return 1
  fi
  if ! command -v "${cmd}" >/dev/null 2>&1; then
    echo "[ERROR] ${cmd} still missing after auto install." >&2
    return 1
  fi
}

if [[ "${DRY_RUN}" == "1" ]]; then
  echo "ARCHIVE_URL=${ARCHIVE_URL}"
  if [[ ${#FORWARD_ARGS[@]} -gt 0 ]]; then
    echo "FORWARDED_ARGS=${FORWARD_ARGS[*]}"
  else
    echo "FORWARDED_ARGS="
  fi
  exit 0
fi

ensure_command curl curl
ensure_command tar tar

tmp_dir="$(mktemp -d 2>/dev/null || mktemp -d -t easyclaw-install)"
cleanup() {
  if [[ "${KEEP_TEMP}" != "1" && -n "${tmp_dir}" && -d "${tmp_dir}" ]]; then
    rm -rf "${tmp_dir}"
  fi
}
trap cleanup EXIT

echo "[INFO] Downloading ${ARCHIVE_URL}"
curl -fsSL "${ARCHIVE_URL}" | tar -xzf - -C "${tmp_dir}"

install_script="$(find "${tmp_dir}" -maxdepth 3 -type f -name "install.sh" | head -n 1)"
if [[ -z "${install_script}" || ! -f "${install_script}" ]]; then
  echo "[ERROR] install.sh not found in downloaded archive." >&2
  exit 1
fi

echo "[INFO] Running installer: ${install_script}"
bash "${install_script}" "${FORWARD_ARGS[@]}"
echo "[OK] EasyClaw installation finished."
