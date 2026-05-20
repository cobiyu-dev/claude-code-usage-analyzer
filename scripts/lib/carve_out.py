"""기능 그룹별 tool_result 본문 절사."""
from __future__ import annotations

from typing import Any

from .output_classifier import classify_bash_output


def carve_out(
    function_group: str,
    tool_name: str,
    tool_input: Any,
    tool_output: Any,
    carve_rules: dict,
    execution_keywords: list[str],
    output_type_rules: dict,
) -> dict:
    """
    반환: {"text": str, "meta": {...}}
    분석에 필요한 만큼만 남긴 짧은 텍스트 + 메타.
    """
    rule_block = (carve_rules.get(function_group) or {}).get("rule")

    # shell_exec 는 출력 유형 분류로 위임
    if function_group == "shell_exec" or (
        isinstance(rule_block, dict) and rule_block.get("type") == "delegate_to_output_classifier"
    ):
        command = ""
        if isinstance(tool_input, dict):
            command = str(tool_input.get("command", ""))
        output_str = _to_str(tool_output)
        output_type = classify_bash_output(command, output_str, execution_keywords)
        carved = _apply_output_type_rule(command, output_str, output_type, output_type_rules)
        # 1차 호출 (output 없음) 일 땐 텍스트가 비어 의미가 없으므로 command 를 노출 텍스트로 둔다.
        if not output_str and command:
            carved["text"] = command[:600]
        return carved

    # 일반 그룹: 간단한 head/tail 위주 fallback (룰은 분석 가능 수준만 적용)
    return _generic_carve(function_group, tool_name, tool_input, tool_output, rule_block)


def _apply_output_type_rule(command: str, output: str, otype: str, rules: dict) -> dict:
    rule = (rules.get(otype) or {}).get("rule") or {}
    rtype = rule.get("type", "")

    if rtype == "full":
        return {"text": output[: rule.get("max_chars", 400)], "meta": {"output_type": otype, "command": command}}
    if rtype == "first_n_lines":
        n = int(rule.get("n", 10))
        lines = output.splitlines()
        text = "\n".join(lines[:n])
        return {"text": text, "meta": {"output_type": otype, "command": command, "total_lines": len(lines)}}
    if rtype == "exec_summary":
        lines = output.splitlines()
        tail_n = int(rule.get("stdout_tail_lines", 30))
        text = "\n".join(lines[-tail_n:])
        return {"text": text, "meta": {"output_type": otype, "command": command, "total_lines": len(lines)}}
    if rtype == "short_or_signature":
        lines = output.splitlines()
        thr = int(rule.get("short_threshold_lines", 80))
        if len(lines) <= thr:
            return {"text": output, "meta": {"output_type": otype, "command": command, "total_lines": len(lines)}}
        # 시그니처: 앞부분만
        return {"text": "\n".join(lines[:30]), "meta": {"output_type": otype, "command": command, "total_lines": len(lines)}}
    if rtype == "structured_summary":
        return {"text": output[:600], "meta": {"output_type": otype, "command": command}}

    return {"text": output[:600], "meta": {"output_type": otype, "command": command}}


def _generic_carve(group: str, tool_name: str, tinp: Any, tout: Any, rule: Any) -> dict:
    out_str = _to_str(tout)
    inp_str = _to_str(tinp)

    # head + tail 디폴트
    if len(out_str) <= 600:
        text = out_str
    else:
        text = out_str[:400] + "\n...\n" + out_str[-200:]

    meta = {"tool_name": tool_name, "input_preview": inp_str[:200]}
    return {"text": text, "meta": meta}


def _to_str(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, str):
        return v
    if isinstance(v, (list, dict)):
        try:
            import json
            return json.dumps(v, ensure_ascii=False)[:4000]
        except (TypeError, ValueError):
            return str(v)[:4000]
    return str(v)
