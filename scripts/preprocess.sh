#!/usr/bin/env bash
# Stage A 진입점. jsonl 파싱 + carve-out + 시크릿 마스킹 → turns.parquet.
set -euo pipefail

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
REPO_ROOT="$( cd "${SCRIPT_DIR}/.." && pwd )"

# venv 자동 감지 (CC_ANALYZER_PYTHON 환경변수가 있으면 우선)
PYTHON_BIN="${CC_ANALYZER_PYTHON:-}"
if [ -z "${PYTHON_BIN}" ]; then
  if [ -x "${REPO_ROOT}/.venv/bin/python" ]; then
    PYTHON_BIN="${REPO_ROOT}/.venv/bin/python"
  else
    PYTHON_BIN="python3"
  fi
fi

FROM=""
TO=""
CONFIG="${HOME}/.config/cc-analyzer/config.yaml"
CACHE_DIR="${HOME}/.cache/cc-analyzer"
PEOPLE_CANDIDATES=""

while [ $# -gt 0 ]; do
  case "$1" in
    --from) FROM="$2"; shift 2;;
    --to)   TO="$2"; shift 2;;
    --config) CONFIG="$2"; shift 2;;
    --cache-dir) CACHE_DIR="$2"; shift 2;;
    --people-candidates) PEOPLE_CANDIDATES="$2"; shift 2;;
    *) echo "Error: 알 수 없는 인자 $1" >&2; exit 3;;
  esac
done

if [ -z "${FROM}" ] || [ -z "${TO}" ]; then
  echo "Usage: $0 --from YYYY-MM-DD --to YYYY-MM-DD [--config PATH] [--cache-dir PATH] [--people-candidates PATH]" >&2
  exit 3
fi

DESKTOP_SESSIONS="${HOME}/Library/Application Support/Claude/local-agent-mode-sessions"
if [ ! -d "${HOME}/.claude/projects" ] && [ ! -d "${DESKTOP_SESSIONS}" ]; then
  echo "Error: ~/.claude/projects/ 와 Claude Desktop 세션 디렉터리 모두 없습니다. Claude Code (터미널 또는 Desktop) 를 한 번이라도 사용 후 다시 시도해주세요." >&2
  exit 1
fi

PERIOD="${FROM}_to_${TO}"
WORK_DIR="${CACHE_DIR}/${PERIOD}"
mkdir -p "${WORK_DIR}"

echo "[Stage A] 파싱 + carve-out + 시크릿 마스킹" >&2

EXTRA=""
if [ -n "${PEOPLE_CANDIDATES}" ]; then
  EXTRA="--people-candidates-output ${PEOPLE_CANDIDATES}"
fi

"${PYTHON_BIN}" "${REPO_ROOT}/scripts/stage_a.py" \
  --from "${FROM}" \
  --to "${TO}" \
  --config "${CONFIG}" \
  --output "${WORK_DIR}/turns.parquet" \
  ${EXTRA} \
  || { echo "Error: stage_a.py 실패" >&2; exit 4; }

echo "✓ Stage A 완료: ${WORK_DIR}/turns.parquet" >&2
