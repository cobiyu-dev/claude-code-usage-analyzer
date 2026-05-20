"""시크릿 정규식 마스킹. Stage A 가 사용."""
from __future__ import annotations

import re
from typing import Any

REDACTED = "[REDACTED]"


def compile_secret_patterns(secret_patterns_yaml: list[dict]) -> list[tuple[str, re.Pattern]]:
    """yaml 의 secret_patterns 항목을 컴파일된 정규식 리스트로."""
    compiled = []
    for entry in secret_patterns_yaml or []:
        name = entry.get("name", "?")
        pat = entry.get("pattern")
        if not pat:
            continue
        try:
            compiled.append((name, re.compile(pat)))
        except re.error:
            # 정규식 오류는 무시하고 진행 (다른 패턴은 살림)
            continue
    return compiled


def mask_text(text: str, compiled: list[tuple[str, re.Pattern]]) -> str:
    """본문 텍스트에서 시크릿 정규식 매칭 부분을 [REDACTED] 로 치환."""
    if not text or not compiled:
        return text
    out = text
    for _, regex in compiled:
        out = regex.sub(REDACTED, out)
    return out


def mask_any(value: Any, compiled: list[tuple[str, re.Pattern]]) -> Any:
    """dict/list/str 재귀 마스킹."""
    if isinstance(value, str):
        return mask_text(value, compiled)
    if isinstance(value, list):
        return [mask_any(v, compiled) for v in value]
    if isinstance(value, dict):
        return {k: mask_any(v, compiled) for k, v in value.items()}
    return value
