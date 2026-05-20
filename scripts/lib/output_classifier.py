"""Bash 출력 유형 분류 (5가지). Stage A 의 shell_exec carve-out 위임 대상."""
from __future__ import annotations

import json
import re


LIST_LIKE_PATTERN = re.compile(r'^[^\s:]+:\d+[:\s]')  # path:line 형태


def classify_bash_output(
    command: str,
    output: str,
    execution_keywords: list[str],
) -> str:
    """다섯 가지 출력 유형 중 하나 반환."""
    cmd = (command or "")
    out = (output or "")

    # 1) execution_like — 명령어 키워드 매칭
    cmd_low = cmd.lower()
    for kw in execution_keywords or []:
        if str(kw).lower() in cmd_low:
            return "execution_like"

    # 2) short_output — 짧으면
    if len(out) <= 400 and out.count("\n") <= 5:
        return "short_output"

    # 3) structured_data — JSON 같은 모양
    stripped = out.strip()
    if stripped.startswith(("{", "[")):
        try:
            json.loads(stripped)
            return "structured_data"
        except (json.JSONDecodeError, ValueError):
            pass

    # 4) list_like — 라인이 path:N: 같은 패턴이거나 동일 형태
    lines = out.splitlines()
    if len(lines) > 5:
        matched = sum(1 for ln in lines[:20] if LIST_LIKE_PATTERN.match(ln))
        if matched >= max(3, len(lines[:20]) // 3):
            return "list_like"

    # 5) document_like — 길거나 구조 마커가 있는 경우 + fallback
    return "document_like"
