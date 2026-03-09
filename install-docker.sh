#!/usr/bin/env bash
# ClawPanel Docker bootstrap installer
# Example:
#   curl -fsSL https://raw.githubusercontent.com/moshall/easyclaw/main/install-docker.sh | \
#     bash -s -- --container clawpanel-web --install-dir /opt/clawpanel --bin-dir /usr/local/bin

set -euo pipefail

usage() {
  cat <<'EOF'
ClawPanel Docker installer

Usage:
  bash install-docker.sh --container <name> [bootstrap-options] [install-options...]

Required:
  --container <name>     Target running container name

Bootstrap options:
  --repo <owner/name>    GitHub repo slug (default: moshall/easyclaw)
  --ref <git-ref>        Branch/tag/commit (default: main)
  --auto-deps            Auto-install missing deps in container (default)
  --no-auto-deps         Disable auto dependency installation
  --dry-run              Print resolved command and exit
  -h, --help             Show this help

Install options:
  Any other options are forwarded to install-online.sh inside container
  e.g. --install-dir /opt/clawpanel --bin-dir /usr/local/bin
EOF
}

CONTAINER_NAME=""
REPO_SLUG="${EASYCLAW_REPO_SLUG:-moshall/easyclaw}"
REF="${EASYCLAW_REF:-main}"
AUTO_DEPS="${EASYCLAW_AUTO_DEPS:-1}"
DRY_RUN="0"
FORWARD_ARGS=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --container)
      [[ $# -ge 2 ]] || { echo "[ERROR] --container requires a value" >&2; exit 1; }
      CONTAINER_NAME="$2"
      shift 2
      ;;
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
    --dry-run)
      DRY_RUN="1"
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

if [[ -z "${CONTAINER_NAME}" ]]; then
  echo "[ERROR] --container is required" >&2
  usage
  exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "[ERROR] docker command not found." >&2
  exit 1
fi

if ! docker inspect "${CONTAINER_NAME}" >/dev/null 2>&1; then
  echo "[ERROR] container not found: ${CONTAINER_NAME}" >&2
  exit 1
fi

running_state="$(docker inspect -f '{{.State.Running}}' "${CONTAINER_NAME}" 2>/dev/null || echo "false")"
if [[ "${running_state}" != "true" ]]; then
  echo "[ERROR] container is not running: ${CONTAINER_NAME}" >&2
  exit 1
fi

container_has_command() {
  local cmd="$1"
  docker exec -i "${CONTAINER_NAME}" sh -lc "command -v ${cmd} >/dev/null 2>&1"
}

ensure_container_bootstrap_deps() {
  local missing=()
  local cmd
  for cmd in bash curl tar; do
    if ! container_has_command "${cmd}"; then
      missing+=("${cmd}")
    fi
  done
  if [[ ${#missing[@]} -eq 0 ]]; then
    return 0
  fi

  if [[ "${AUTO_DEPS}" != "1" ]]; then
    echo "[ERROR] missing deps in container: ${missing[*]} (use --auto-deps or install manually)" >&2
    return 1
  fi

  echo "[INFO] Missing deps in container, trying auto install: ${missing[*]}"
  if ! docker exec -i "${CONTAINER_NAME}" sh -lc '
set -e
if command -v apt-get >/dev/null 2>&1; then
  apt-get update -y >/dev/null
  apt-get install -y bash curl tar >/dev/null
elif command -v dnf >/dev/null 2>&1; then
  dnf install -y bash curl tar >/dev/null
elif command -v yum >/dev/null 2>&1; then
  yum install -y bash curl tar >/dev/null
elif command -v apk >/dev/null 2>&1; then
  apk add --no-cache bash curl tar >/dev/null
elif command -v pacman >/dev/null 2>&1; then
  pacman -Sy --noconfirm bash curl tar >/dev/null
elif command -v zypper >/dev/null 2>&1; then
  zypper --non-interactive install bash curl tar >/dev/null
else
  exit 91
fi
'; then
    echo "[ERROR] failed to auto-install deps in container" >&2
    return 1
  fi

  for cmd in bash curl tar; do
    if ! container_has_command "${cmd}"; then
      echo "[ERROR] dependency still missing after install: ${cmd}" >&2
      return 1
    fi
  done
}

INSTALL_ONLINE_URL="https://raw.githubusercontent.com/${REPO_SLUG}/${REF}/install-online.sh"
remote_cmd="curl -fsSL $(printf '%q' "${INSTALL_ONLINE_URL}") | bash -s --"
if [[ ${#FORWARD_ARGS[@]} -gt 0 ]]; then
  for arg in "${FORWARD_ARGS[@]}"; do
    remote_cmd+=" $(printf '%q' "${arg}")"
  done
fi

if [[ "${DRY_RUN}" == "1" ]]; then
  echo "CONTAINER=${CONTAINER_NAME}"
  echo "INSTALL_ONLINE_URL=${INSTALL_ONLINE_URL}"
  echo "AUTO_DEPS=${AUTO_DEPS}"
  echo "REMOTE_CMD=${remote_cmd}"
  exit 0
fi

ensure_container_bootstrap_deps

echo "[INFO] Installing ClawPanel in container: ${CONTAINER_NAME}"
docker exec -i "${CONTAINER_NAME}" bash -lc "${remote_cmd}"
echo "[OK] ClawPanel installation finished in container ${CONTAINER_NAME}."
