#!/usr/bin/env bash
# Stage C 진입점. episodes.parquet → aggregated.json.
set -euo pipefail

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
REPO_ROOT="$( cd "${SCRIPT_DIR}/.." && pwd )"

PYTHON_BIN="${CC_ANALYZER_PYTHON:-}"
if [ -z "${PYTHON_BIN}" ]; then
  if [ -x "${REPO_ROOT}/.venv/bin/python" ]; then
    PYTHON_BIN="${REPO_ROOT}/.venv/bin/python"
  else
    PYTHON_BIN="python3"
  fi
fi

EPISODES=""
OUTPUT=""
MODE="broad"

while [ $# -gt 0 ]; do
  case "$1" in
    --episodes) EPISODES="$2"; shift 2;;
    --output)   OUTPUT="$2"; shift 2;;
    --mode)     MODE="$2"; shift 2;;
    *) echo "Error: 알 수 없는 인자 $1" >&2; exit 2;;
  esac
done

if [ -z "${EPISODES}" ] || [ -z "${OUTPUT}" ]; then
  echo "Usage: $0 --episodes PATH --output PATH [--mode broad|curated]" >&2
  exit 2
fi

if [ ! -f "${EPISODES}" ]; then
  echo "Error: episodes.parquet 없음: ${EPISODES}" >&2
  exit 1
fi

echo "[Stage C] 그룹별 메트릭 + 시그니처 + 미니 패턴 집계 (mode=${MODE})" >&2

"${PYTHON_BIN}" "${REPO_ROOT}/scripts/stage_c.py" \
  --episodes "${EPISODES}" \
  --output "${OUTPUT}" \
  --mode "${MODE}" \
  || { echo "Error: stage_c.py 실패" >&2; exit 3; }

echo "✓ Stage C 완료: ${OUTPUT}" >&2
