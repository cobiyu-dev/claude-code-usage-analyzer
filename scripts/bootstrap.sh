#!/usr/bin/env bash
# 첫 실행 부트스트랩: venv 없으면 만들고, 의존성 없으면 설치.
# preprocess.sh / postprocess.sh 가 본격 실행 직전에 source 로 부른다.
#
# 출력: PYTHON_BIN 변수를 export — 호출자가 그대로 쓰면 됨.

set -euo pipefail

# 호출자가 이미 정의한 REPO_ROOT 가 있으면 그대로, 없으면 추론
if [ -z "${REPO_ROOT:-}" ]; then
  _BOOT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
  REPO_ROOT="$( cd "${_BOOT_DIR}/.." && pwd )"
fi

# 사용자가 명시한 파이썬이 있으면 그걸 우선
if [ -n "${CC_ANALYZER_PYTHON:-}" ]; then
  PYTHON_BIN="${CC_ANALYZER_PYTHON}"
  export PYTHON_BIN
  return 0 2>/dev/null || exit 0
fi

VENV_DIR="${REPO_ROOT}/.venv"
VENV_PYTHON="${VENV_DIR}/bin/python"
MARKER="${VENV_DIR}/.cc-analyzer-deps-installed"

# 1. venv 없으면 생성
if [ ! -x "${VENV_PYTHON}" ]; then
  # python3 가 있어야 venv 만들 수 있음
  if ! command -v python3 >/dev/null 2>&1; then
    echo "Error: python3 가 시스템에 없습니다. python3 (3.10+) 를 먼저 설치해주세요." >&2
    exit 1
  fi
  echo "[bootstrap] .venv 가 없어 새로 만듭니다 (한 번만 걸리는 작업)..." >&2
  python3 -m venv "${VENV_DIR}"
fi

# 2. 의존성 설치 — marker 파일이 없으면 한 번만
if [ ! -f "${MARKER}" ]; then
  echo "[bootstrap] 의존성을 설치합니다 (한 번만 걸리는 작업)..." >&2
  # pip 최신화 후 editable 설치
  "${VENV_PYTHON}" -m pip install --upgrade pip --quiet
  "${VENV_PYTHON}" -m pip install -e "${REPO_ROOT}" --quiet
  touch "${MARKER}"
  echo "[bootstrap] 설치 완료" >&2
fi

PYTHON_BIN="${VENV_PYTHON}"
export PYTHON_BIN
