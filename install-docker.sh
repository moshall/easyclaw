#!/usr/bin/env bash
# EasyClaw Docker bootstrap installer
# Example:
#   curl -fsSL https://raw.githubusercontent.com/moshall/easyclaw/main/install-docker.sh | \
#     bash -s -- --container easyclaw-web --install-dir /opt/easyclaw --bin-dir /usr/local/bin

set -euo pipefail

usage() {
  cat <<'EOF'
EasyClaw Docker installer

Usage:
  bash install-docker.sh --container <name> [bootstrap-options] [install-options...]

Required:
  --container <name>     Target running container name

Bootstrap options:
  --repo <owner/name>    GitHub repo slug (default: moshall/easyclaw)
  --ref <git-ref>        Branch/tag/commit (default: main)
  --dry-run              Print resolved command and exit
  -h, --help             Show this help

Install options:
  Any other options are forwarded to install-online.sh inside container
  e.g. --install-dir /opt/easyclaw --bin-dir /usr/local/bin
EOF
}

CONTAINER_NAME=""
REPO_SLUG="${EASYCLAW_REPO_SLUG:-moshall/easyclaw}"
REF="${EASYCLAW_REF:-main}"
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
  echo "REMOTE_CMD=${remote_cmd}"
  exit 0
fi

echo "[INFO] Installing EasyClaw in container: ${CONTAINER_NAME}"
docker exec -i "${CONTAINER_NAME}" bash -lc "${remote_cmd}"
echo "[OK] EasyClaw installation finished in container ${CONTAINER_NAME}."
