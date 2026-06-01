#!/usr/bin/env python3
"""
Stage A — jsonl 파싱 + carve-out + 시크릿 마스킹.

입력: ~/.claude/projects/**/*.jsonl (날짜 필터)
출력: turns.parquet (Stage B 입력)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

# 패키지/스크립트 양쪽 실행 지원
try:
    from .lib.masker import compile_secret_patterns, mask_any, mask_text
    from .lib.tool_mapper import map_tool_to_function_group
    from .lib.carve_out import carve_out
    from .lib.people_finder import discover_candidates
    from .lib.structure_labeler import label_turns
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent))
    from lib.masker import compile_secret_patterns, mask_any, mask_text
    from lib.tool_mapper import map_tool_to_function_group
    from lib.carve_out import carve_out
    from lib.people_finder import discover_candidates
    from lib.structure_labeler import label_turns


REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = REPO_ROOT / "config"

CC_FEATURES = ["plan_mode", "clear", "subagent", "slash_command"]


@dataclass
class Turn:
    turn_id: str
    session_id: str
    project_dir: str
    timestamp: str
    role: str
    content: str
    tool_uses: list[dict] = field(default_factory=list)
    claude_code_features: list[str] = field(default_factory=list)


# ---------- 로딩 ----------

def load_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_system_configs() -> dict:
    return {
        "function_groups": load_yaml(CONFIG_DIR / "function_groups.yaml").get("function_groups", {}),
        "carve_out_rules": load_yaml(CONFIG_DIR / "carve_out_rules.yaml").get("carve_out_rules", {}),
        "output_types": load_yaml(CONFIG_DIR / "carve_out_rules.yaml").get("output_types", {}),
        "execution_keywords": load_yaml(CONFIG_DIR / "execution_keywords.yaml").get("execution_keywords", []),
        "secret_patterns": load_yaml(CONFIG_DIR / "secret_patterns.yaml").get("secret_patterns", []),
        "people_patterns": load_yaml(CONFIG_DIR / "people_name_patterns.yaml"),
        "git_intent_patterns": load_yaml(CONFIG_DIR / "git_intent_patterns.yaml"),
    }


def load_user_config(config_path: Path) -> dict:
    if not config_path.exists():
        return {"tool_function_mapping": {}, "mask_people_names": True, "people_names": []}
    return load_yaml(config_path)


# ---------- jsonl 스캔 ----------

def find_jsonl_files(start_date: str, end_date: str) -> list[Path]:
    """기간 안에 timestamp 가 하나라도 들어있는 jsonl 만 후보로.

    수집 경로 두 곳:
    1. 터미널 Claude Code: ~/.claude/projects/**/*.jsonl
    2. Claude Desktop 의 Claude Code 모드:
       ~/Library/Application Support/Claude/local-agent-mode-sessions/**/.claude/projects/**/*.jsonl
       (Desktop 이 임시 워크스페이스마다 .claude/projects 를 따로 두지만 jsonl 스키마는 동일)
    """
    home = Path.home()
    candidates: list[Path] = []

    projects_dir = home / ".claude" / "projects"
    if projects_dir.exists():
        candidates.extend(projects_dir.rglob("*.jsonl"))

    desktop_root = home / "Library" / "Application Support" / "Claude" / "local-agent-mode-sessions"
    if desktop_root.exists():
        # 임시 워크스페이스 안의 .claude/projects/**/*.jsonl 만 가져옴 (audit.jsonl 등 다른 jsonl 은 제외)
        for p in desktop_root.rglob("*.jsonl"):
            if ".claude/projects/" in str(p):
                candidates.append(p)

    return sorted(set(candidates))


def in_period(ts: str, start: datetime, end: datetime) -> bool:
    if not ts:
        return False
    try:
        t = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return False
    if t.tzinfo is None:
        t = t.replace(tzinfo=timezone.utc)
    return start <= t <= end


# ---------- turn 정규화 ----------

def normalize_record(
    rec: dict,
    project_dir: str,
    user_mapping: dict,
    function_groups: dict,
    carve_rules: dict,
    output_type_rules: dict,
    execution_keywords: list,
    secret_compiled,
) -> Turn | None:
    """JSONL record 한 줄 → Turn. None 이면 분석 무관 record."""
    rtype = rec.get("type")
    if rtype not in ("user", "assistant"):
        return None

    msg = rec.get("message") or {}
    role = msg.get("role") or rtype
    ts = rec.get("timestamp", "")
    session_id = rec.get("sessionId", "")
    turn_id = rec.get("uuid") or f"{session_id}:{ts}"

    content = msg.get("content")
    text_parts: list[str] = []
    tool_uses: list[dict] = []

    if isinstance(content, str):
        text_parts.append(content)
    elif isinstance(content, list):
        for item in content:
            if not isinstance(item, dict):
                continue
            itype = item.get("type")
            if itype == "text":
                text_parts.append(str(item.get("text", "")))
            elif itype == "tool_use":
                tname = item.get("name", "?")
                fg = map_tool_to_function_group(tname, user_mapping, function_groups)
                tinp = item.get("input")
                # tool_result 는 같은 message 에 안 옴 — 별도 record 에서 매칭해야 함
                # 여기선 input 만 carve 처리
                carved = carve_out(
                    function_group=fg,
                    tool_name=tname,
                    tool_input=tinp,
                    tool_output=None,
                    carve_rules=carve_rules,
                    execution_keywords=execution_keywords,
                    output_type_rules=output_type_rules,
                )
                tool_uses.append({
                    "tool_use_id": item.get("id", ""),
                    "name": tname,
                    "function_group": fg,
                    "input_carved": mask_text(carved["text"], secret_compiled),
                    "meta": mask_any(carved["meta"], secret_compiled),
                })
            elif itype == "tool_result":
                # user role 안에 들어오는 tool_result. tool_use_id 로 나중에 매칭하기 위해 별도 저장.
                tcontent = item.get("content")
                tool_uses.append({
                    "tool_use_id": item.get("tool_use_id", ""),
                    "name": "<result>",
                    "function_group": "",
                    "is_result": True,
                    "result_raw": _flatten_result(tcontent),
                })

    # Claude Code 기능 검출
    feats: list[str] = []
    txt_joined = "\n".join(text_parts)
    if role == "user":
        if txt_joined.lstrip().startswith("/clear"):
            feats.append("clear")
        elif txt_joined.lstrip().startswith("/"):
            feats.append("slash_command")
    for tu in tool_uses:
        nm = tu.get("name", "")
        if "ExitPlanMode" in nm:
            feats.append("plan_mode")
        if nm == "Task" or nm == "Agent":
            feats.append("subagent")

    # 시스템 메타 마커 검출 — 본문에 새지 않게 별도 신호로 격상
    # (claude_code_features 와 별개로 turn 단위 흐름 신호로 저장)
    meta_markers = detect_system_markers(txt_joined)
    if meta_markers:
        for mk in meta_markers:
            feats.append(f"marker_{mk}")

    # 시크릿 마스킹
    masked_text = mask_text(txt_joined, secret_compiled)

    return Turn(
        turn_id=str(turn_id),
        session_id=session_id,
        project_dir=project_dir,
        timestamp=ts,
        role=role,
        content=masked_text,
        tool_uses=tool_uses,
        claude_code_features=sorted(set(feats)),
    )


# 시스템 트랜스크립트 마커 (사용자 발화가 아닌 시스템 생성 텍스트)
# 별도 신호로 인식해 Stage B/C 가 의미 있는 메타 패턴으로 활용 가능하게 함.
# 데이터 무관 일반 룰 (Claude Code 자체가 만드는 마커들).
SYSTEM_MARKERS = (
    ("continue", ("Continue from where you left off", "continue from where you left off")),
    ("interrupted", ("Request interrupted by user", "[Request interrupted by user]")),
    ("task_notification", ("<task-notification>", "<task-notification ")),
    ("local_command", ("<local-command-stdout>", "<local-command-caveat>")),
    ("compact", ("This session is being continued", "ran out of context")),
    ("no_user_prompt", ("(no user prompt)", "No user prompt found")),
    ("teammate_message", ("<teammate-message",)),
)


def detect_system_markers(text: str) -> list[str]:
    if not text:
        return []
    out: list[str] = []
    for name, needles in SYSTEM_MARKERS:
        if any(n in text for n in needles):
            out.append(name)
    return out


def _flatten_result(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict):
                if item.get("type") == "text":
                    parts.append(str(item.get("text", "")))
                else:
                    parts.append(json.dumps(item, ensure_ascii=False)[:2000])
            else:
                parts.append(str(item))
        return "\n".join(parts)
    return str(content)


def merge_tool_results(turns: list[Turn], carve_rules, exec_kw, output_type_rules, function_groups, user_mapping, secret_compiled) -> None:
    """tool_result(별도 turn) 를 같은 tool_use_id 의 tool_use 에 합쳐서 carve 적용."""
    # 1) result lookup 만들기
    results: dict[str, str] = {}
    keep_turns: list[Turn] = []
    for t in turns:
        leftover_tus = []
        for tu in t.tool_uses:
            if tu.get("is_result"):
                tu_id = tu.get("tool_use_id", "")
                if tu_id:
                    results[tu_id] = tu.get("result_raw", "")
            else:
                leftover_tus.append(tu)
        t.tool_uses = leftover_tus
        keep_turns.append(t)

    # 2) tool_use 에 result 합쳐서 carve 다시
    # 머지 시 1차에서 박은 input 관련 meta(command, input_preview)는 보존한다.
    # output 관련 meta(output_type, total_lines 등) 만 새로 추가.
    # Bash 의 경우 output_type 분류가 command 키워드에 의존하므로 1차 command 를 다시 전달.
    PRESERVE_FROM_FIRST_PASS = {"command", "input_preview", "tool_name"}
    for t in keep_turns:
        for tu in t.tool_uses:
            tu_id = tu.get("tool_use_id", "")
            if tu_id and tu_id in results:
                raw = results[tu_id]
                fg = tu.get("function_group", "other")
                # 1차에서 박힌 command 를 머지 단계에 다시 전달해
                # classify_bash_output 이 execution_keywords 매칭에 사용 가능하도록.
                old_meta = tu.get("meta") or {}
                preserved_command = old_meta.get("command", "")
                tinp_for_merge = {"command": preserved_command} if preserved_command else None
                carved = carve_out(
                    function_group=fg,
                    tool_name=tu.get("name", ""),
                    tool_input=tinp_for_merge,
                    tool_output=raw,
                    carve_rules=carve_rules,
                    execution_keywords=exec_kw,
                    output_type_rules=output_type_rules,
                )
                tu["output_carved"] = mask_text(carved["text"], secret_compiled)
                # meta 머지: 1차 결과의 input 관련 키는 보존, 나머지만 update
                new_meta = carved.get("meta") or {}
                merged = dict(new_meta)
                for k in PRESERVE_FROM_FIRST_PASS:
                    if old_meta.get(k):
                        merged[k] = old_meta[k]
                tu["meta"] = mask_any(merged, secret_compiled)


# ---------- 메인 ----------

def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--from", dest="from_date", required=True)
    p.add_argument("--to", dest="to_date", required=True)
    p.add_argument("--config", default=str(Path.home() / ".config" / "cc-analyzer" / "config.yaml"))
    p.add_argument("--output", required=True)
    p.add_argument("--people-candidates-output", default=None,
                   help="사람 이름 자동 발견 후보 저장 경로 (옵션, 첫 실행 마법사용)")
    args = p.parse_args()

    start = datetime.fromisoformat(args.from_date).replace(tzinfo=timezone.utc)
    end = datetime.fromisoformat(args.to_date).replace(hour=23, minute=59, second=59, tzinfo=timezone.utc)

    sysc = load_system_configs()
    usrc = load_user_config(Path(args.config).expanduser())

    secret_compiled = compile_secret_patterns(sysc["secret_patterns"])
    user_mapping = usrc.get("tool_function_mapping") or {}

    print(f"[Stage A] 파싱 시작 {args.from_date} ~ {args.to_date}", file=sys.stderr)

    files = find_jsonl_files(args.from_date, args.to_date)
    if not files:
        print("Error: ~/.claude/projects/ 에서 jsonl 을 찾지 못했습니다.", file=sys.stderr)
        return 1

    all_turns: list[Turn] = []
    sample_texts: list[str] = []

    for f in files:
        project_dir = f.parent.name
        try:
            with open(f, encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    ts = rec.get("timestamp", "")
                    if not in_period(ts, start, end):
                        continue
                    turn = normalize_record(
                        rec, project_dir, user_mapping,
                        sysc["function_groups"], sysc["carve_out_rules"],
                        sysc["output_types"], sysc["execution_keywords"],
                        secret_compiled,
                    )
                    if turn is not None:
                        all_turns.append(turn)
                        if len(sample_texts) < 5000:
                            sample_texts.append(turn.content)
        except OSError:
            continue

    if not all_turns:
        print(f"Error: 해당 기간({args.from_date}~{args.to_date}) 에 turn 이 없습니다.", file=sys.stderr)
        return 1

    # tool_result 머지
    merge_tool_results(
        all_turns,
        sysc["carve_out_rules"], sysc["execution_keywords"], sysc["output_types"],
        sysc["function_groups"], user_mapping, secret_compiled,
    )

    # turn 단위 구조 라벨링 (git_intent, outcome 후보 신호)
    turn_dicts = [asdict(t) for t in all_turns]
    label_stats = label_turns(turn_dicts, sysc["git_intent_patterns"])
    print(f"[Stage A] 구조 라벨링: {label_stats}", file=sys.stderr)

    # parquet 저장
    df = pd.DataFrame(turn_dicts)
    out_path = Path(args.output).expanduser()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out_path, index=False)
    print(f"✓ {len(all_turns)} turns → {out_path}", file=sys.stderr)

    # 사람 이름 후보 (옵션)
    if args.people_candidates_output:
        cands = discover_candidates(sample_texts, sysc["people_patterns"])
        cand_path = Path(args.people_candidates_output).expanduser()
        cand_path.parent.mkdir(parents=True, exist_ok=True)
        with open(cand_path, "w", encoding="utf-8") as f:
            json.dump([{"name": n, "count": c} for n, c in cands], f, ensure_ascii=False, indent=2)
        print(f"✓ 이름 후보 {len(cands)}개 → {cand_path}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
