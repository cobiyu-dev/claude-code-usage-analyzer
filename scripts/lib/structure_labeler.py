"""
Turn 단위 구조 라벨링 — git_intent 및 outcome 후보 신호 결정론적 부여.

Stage A 끝에 호출. yaml 매칭만 사용, LLM 호출 X.
Stage B 가 episode 단위 합산을 쉽게 할 수 있도록 turn 의 tool_use 마다 태그.

부여 항목:
- tool_use.git_intent: "diagnostic" / "output" / "transition" / None
- tool_use.is_pr_create: bool — gh pr create 또는 github mcp create_pull_request
- tool_use.pr_body_has_sections: bool — PR 본문에 ## Summary / ## Test 등
- tool_use.outcome_signals: list[str] — 이 turn 단독으로 시사하는 outcome 후보
  예: ["committed"], ["verified_by_run"], ["pr_opened"], ["delegated_and_reported"]
  phase 컨텍스트가 필요한 outcome (verify-phase 안인지) 은 Stage B 가 확인.
"""
from __future__ import annotations

import re
from typing import Any


def compile_git_intent_patterns(yaml_data: dict) -> dict[str, list[re.Pattern]]:
    """git_intent_patterns.yaml -> intent -> [compiled regex]."""
    out: dict[str, list[re.Pattern]] = {}
    block = yaml_data.get("git_intent_patterns") or {}
    for intent_name, intent_block in block.items():
        regs = []
        for cmd in (intent_block.get("commands") or []):
            pat = cmd.get("regex") if isinstance(cmd, dict) else None
            if not pat:
                continue
            try:
                regs.append(re.compile(pat))
            except re.error:
                continue
        if regs:
            out[intent_name] = regs
    return out


def detect_git_intent(command: str, compiled: dict[str, list[re.Pattern]]) -> str | None:
    """command 가 어느 git intent 에 속하는지 (없으면 None)."""
    if not command:
        return None
    for intent_name, regs in compiled.items():
        for r in regs:
            if r.search(command):
                return intent_name
    return None


# 정적 outcome 신호 정규식 — turn 단독으로 판정 가능한 것만
_GIT_COMMIT_RE = re.compile(r'^\s*git\s+commit(\s|$)')
_GIT_PUSH_RE = re.compile(r'^\s*git\s+push(\s|$)')
_GH_PR_CREATE_RE = re.compile(r'^\s*gh\s+pr\s+create(\s|$)')
_PR_BODY_SECTION_RE = re.compile(
    r'(##\s*Summary|##\s*Test|##\s*변경|##\s*요약)',
    re.IGNORECASE
)
_GITHUB_PR_TOOL_RE = re.compile(r'^(mcp__)?github__create_pull_request$')


def detect_outcome_signals(tool_use: dict) -> list[str]:
    """
    이 turn 의 tool_use 만 보고 부여 가능한 outcome 후보.
    Stage B 가 verify-phase 안인지 확인해서 최종 부여 여부 결정.
    """
    out: list[str] = []
    name = tool_use.get("name") or ""
    meta = tool_use.get("meta") or {}
    command = (meta.get("command") or "")

    # Bash 기반 신호
    if name == "Bash" and command:
        if _GIT_COMMIT_RE.search(command):
            out.append("committed")
        if _GIT_PUSH_RE.search(command):
            out.append("pushed")
        if _GH_PR_CREATE_RE.search(command):
            out.append("pr_opened")
            # PR body 구조화 여부도 확인
            if _PR_BODY_SECTION_RE.search(command):
                out.append("pr_with_structured_body")

    # GitHub MCP 기반 PR 생성
    if _GITHUB_PR_TOOL_RE.match(name or ""):
        out.append("pr_opened")
        # input_carved 안에 PR body 가 있을 수 있음
        body_text = (tool_use.get("input_carved") or "")
        if _PR_BODY_SECTION_RE.search(body_text):
            out.append("pr_with_structured_body")

    # Agent / Task 호출 — delegated_and_reported 후보
    if name in ("Agent", "Task"):
        out.append("delegated_and_reported")

    # function_group 기반 신호
    fg = tool_use.get("function_group")
    if fg in ("db_query", "log_search", "metric_query", "trace_view"):
        out.append("verified_by_data_candidate")

    # execution_like Bash — verified_by_run 후보
    output_type = meta.get("output_type")
    if name == "Bash" and output_type == "execution_like":
        out.append("verified_by_run_candidate")

    return out


def label_turns(turns_records: list[dict], git_intent_yaml: dict) -> dict:
    """
    turns 의 각 tool_use 에 git_intent / outcome_signals / is_pr_create 등 태그.
    in-place 수정 + 통계 dict 반환.

    turns_records: stage_a 의 dataclass.asdict() 결과 리스트 (dict 형태)
    """
    compiled_git = compile_git_intent_patterns(git_intent_yaml)

    stats = {
        "git_intent_diagnostic": 0,
        "git_intent_output": 0,
        "git_intent_transition": 0,
        "outcome_committed": 0,
        "outcome_pushed": 0,
        "outcome_pr_opened": 0,
        "outcome_pr_with_structured_body": 0,
        "outcome_delegated_and_reported": 0,
        "outcome_verified_by_data_candidate": 0,
        "outcome_verified_by_run_candidate": 0,
    }

    for turn in turns_records:
        tus = turn.get("tool_uses") or []
        for tu in tus:
            meta = tu.get("meta") or {}
            command = meta.get("command") or ""

            # git_intent
            intent = detect_git_intent(command, compiled_git)
            tu["git_intent"] = intent
            if intent:
                key = f"git_intent_{intent}"
                if key in stats:
                    stats[key] += 1

            # outcome 후보
            signals = detect_outcome_signals(tu)
            tu["outcome_signals"] = signals
            for s in signals:
                key = f"outcome_{s}"
                if key in stats:
                    stats[key] += 1

    return stats
