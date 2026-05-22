"""Stage B: turns.parquet → episodes.parquet

휴리스틱 분할 + 구조 라벨링. LLM 호출 없이 결정론적으로 처리.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import yaml


# ---------- 유틸 ----------

KO_EN_TOKEN = re.compile(r"[A-Za-z]{2,}|[가-힣]{2,}")


def tokenize(text: str) -> set[str]:
    if not text:
        return set()
    return {t.lower() for t in KO_EN_TOKEN.findall(text)}


def jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def overlap_small_side(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    smaller = min(len(a), len(b))
    return len(a & b) / smaller


def parse_ts(s: str) -> datetime:
    # 2026-05-04T01:31:46.935Z 형태
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    return datetime.fromisoformat(s)


def _safe_list(x):
    """numpy array 또는 list 를 안전하게 list 로."""
    if x is None:
        return []
    try:
        return list(x)
    except TypeError:
        return []


def turn_function_groups(tool_uses) -> list[str]:
    out = []
    for tu in _safe_list(tool_uses):
        fg = tu.get("function_group")
        if fg:
            out.append(fg)
    return out


def turn_tool_names(tool_uses) -> list[str]:
    return [tu.get("name") or "" for tu in tool_uses if tu.get("name")]


def is_execution_like_turn(tool_uses) -> bool:
    for tu in _safe_list(tool_uses):
        if tu.get("name") == "Bash":
            meta = tu.get("meta") or {}
            if isinstance(meta, dict) and meta.get("output_type") == "execution_like":
                return True
    return False


def turn_has_clear(content: str) -> bool:
    return bool(content and "<command-name>/clear" in content) or (content or "").strip().startswith("/clear")


def last_turn_has_error_or_unresponded(turn) -> bool:
    """단순 휴리스틱: assistant 의 마지막 응답이 도구 에러 출력 포함."""
    if turn["role"] != "assistant":
        return False
    for tu in _safe_list(turn["tool_uses"]):
        out = tu.get("output_carved") or ""
        if isinstance(out, str) and any(k in out.lower() for k in ("error", "fatal", "traceback", "exception", "fail")):
            return True
    return False


# ---------- Stage B 파이프라인 ----------

def load_split_config(repo_root: Path) -> dict:
    with open(repo_root / "config" / "split_signals.yaml") as f:
        return yaml.safe_load(f)


def first_pass_split(turns: pd.DataFrame, cfg: dict) -> list[list[int]]:
    """turns DataFrame (시간순 정렬됨)을 받아, 에피소드별 turn index 리스트 반환."""
    n = len(turns)
    if n == 0:
        return []

    # 시간/세션 등은 row 단위로 빠르게
    ts = [parse_ts(t) for t in turns["timestamp"]]
    sessions = list(turns["session_id"])
    contents = list(turns["content"])
    roles = list(turns["role"])
    tool_uses_list = list(turns["tool_uses"])

    fg_per_turn = [set(turn_function_groups(tu)) for tu in tool_uses_list]
    tok_per_turn = [tokenize(c or "") for c in contents]

    time_gap_min = cfg["time_gap"]["threshold_minutes"]
    win = cfg["function_group_disruption"]["window_size"]
    fg_overlap_th = cfg["function_group_disruption"]["overlap_threshold"]
    topic_th = cfg["topic_keyword_change"]["jaccard_threshold"]
    transition_phrases = []
    for arr in cfg.get("transition_phrases", {}).values():
        transition_phrases.extend(arr)

    boundaries = set()  # turn index i 이전에 분할 (즉 i 가 새 에피소드 첫 turn)

    for i in range(1, n):
        # session change
        if sessions[i] != sessions[i - 1]:
            boundaries.add(i)
            continue
        # time gap
        gap_min = (ts[i] - ts[i - 1]).total_seconds() / 60.0
        if gap_min > time_gap_min:
            boundaries.add(i)
            continue
        # /clear 직후 (i-1 turn 에 /clear 가 있었으면 i 에서 분할)
        if turn_has_clear(contents[i - 1] or ""):
            boundaries.add(i)
            continue
        # transition phrases: user turn 의 i-1 turn 에서 매칭 시 i 에서 분할
        if roles[i - 1] == "user":
            c = contents[i - 1] or ""
            for p in transition_phrases:
                if p in c:
                    boundaries.add(i)
                    break
            if i in boundaries:
                continue

        # window 기반 신호 (5턴 윈도우)
        if i >= win and i + win <= n:
            prev_fg = set().union(*fg_per_turn[i - win:i]) if any(fg_per_turn[i - win:i]) else set()
            next_fg = set().union(*fg_per_turn[i:i + win]) if any(fg_per_turn[i:i + win]) else set()
            if prev_fg or next_fg:
                ov = overlap_small_side(prev_fg, next_fg)
                if (prev_fg and next_fg) and ov <= fg_overlap_th:
                    boundaries.add(i)
                    continue

            # topic keyword jaccard
            prev_tok = set().union(*tok_per_turn[i - win:i]) if any(tok_per_turn[i - win:i]) else set()
            next_tok = set().union(*tok_per_turn[i:i + win]) if any(tok_per_turn[i:i + win]) else set()
            jac = jaccard(prev_tok, next_tok)
            if jac <= topic_th and (prev_tok and next_tok):
                boundaries.add(i)

    # 에피소드 인덱스 리스트 구성
    episodes: list[list[int]] = []
    start = 0
    for i in range(1, n):
        if i in boundaries:
            episodes.append(list(range(start, i)))
            start = i
    episodes.append(list(range(start, n)))
    return episodes


# ---------- 에피소드 라벨링 ----------

def build_episode_label_and_goal(turns_slice: pd.DataFrame) -> tuple[str, str]:
    """첫 user prompt 를 기반으로 자유 텍스트 라벨/goal 생성 (LLM 없이 휴리스틱)."""
    # 첫 user turn 찾기
    first_user_content = ""
    for _, row in turns_slice.iterrows():
        if row["role"] == "user" and row["content"]:
            first_user_content = (row["content"] or "").strip()
            if first_user_content:
                break
    # slash command 면 첫 줄로
    snippet = first_user_content[:200].replace("\n", " ").strip()
    if not snippet:
        snippet = "(no user prompt)"
    # 라벨: 짧게
    label = snippet[:120]
    # goal: 같은 문장 (단순화)
    goal = snippet[:160]
    return label, goal


def detect_claude_code_features(turns_slice: pd.DataFrame) -> list[str]:
    feats = set()
    for _, row in turns_slice.iterrows():
        for f in _safe_list(row["claude_code_features"]):
            feats.add(f)
        # 슬래시 커맨드
        if row["role"] == "user" and (row["content"] or "").lstrip().startswith("/"):
            c = (row["content"] or "").lstrip()
            if c.startswith("/") and not c.startswith("/clear"):
                feats.add("slash_command")
    return sorted(feats)


def compute_phase_boundaries(tool_uses_list: list, fg_per_turn: list[set]) -> dict:
    edit_indices = []
    for i, fgs in enumerate(fg_per_turn):
        if "file_edit" in fgs or is_execution_like_turn(tool_uses_list[i]):
            edit_indices.append(i)
    n = len(fg_per_turn)
    if not edit_indices:
        return {"intro_end": n, "verify_start": n}
    return {"intro_end": edit_indices[0], "verify_start": edit_indices[-1] + 1}


def classify_episode_kind(fg_per_turn: list[set]) -> str:
    has_edit = any("file_edit" in fgs for fgs in fg_per_turn)
    if has_edit:
        return "with_changes"
    invest = {"log_search", "db_query", "code_search", "metric_query", "trace_view", "file_read"}
    has_invest = any(fgs & invest for fgs in fg_per_turn)
    if has_invest:
        return "investigation_only"
    return "tooling_only"


def aggregate_outcomes(turns_slice: pd.DataFrame, phase_boundaries: dict) -> tuple[list[str], list[str], list[str]]:
    """
    반환: (outcomes set, git_intents set, outcome_sequence list)

    outcome_sequence: turn 순서대로 등장한 outcome (phase 무관, 동일 outcome 연속은 dedup).
    시퀀스 패턴 검출용 (예: verified_by_data → verified_by_run → verified_by_data).
    """
    intro_end = phase_boundaries["intro_end"]
    verify_start = phase_boundaries["verify_start"]
    n = len(turns_slice)

    outcomes: set[str] = set()
    git_intents: set[str] = set()
    commit_positions: list[str] = []
    outcome_sequence: list[str] = []

    def _push_seq(name: str) -> None:
        if not outcome_sequence or outcome_sequence[-1] != name:
            outcome_sequence.append(name)

    for idx, (_, row) in enumerate(turns_slice.iterrows()):
        for tu in _safe_list(row["tool_uses"]):
            gi = tu.get("git_intent")
            if gi:
                git_intents.add(gi)
            sigs = _safe_list(tu.get("outcome_signals"))
            in_verify = idx >= verify_start
            in_main = intro_end <= idx < verify_start
            for sig in sigs:
                # 정규화 (candidate 접미사 제거)
                base = sig.replace("_candidate", "")

                # 시퀀스에는 모든 정규화 신호 포함 (phase 무관)
                if base in ("verified_by_data", "verified_by_run",
                            "committed", "pushed", "pr_opened",
                            "pr_with_structured_body", "delegated_and_reported"):
                    _push_seq(base)

                # episode set 합산 (phase 필터)
                if base in ("committed", "pushed", "pr_opened", "pr_with_structured_body"):
                    if in_verify:
                        outcomes.add(base)
                elif base == "verified_by_data":
                    # verify phase 우선, main phase 도 포함 (변경 도중 데이터 검증)
                    if in_verify or in_main:
                        outcomes.add("verified_by_data")
                elif base == "verified_by_run":
                    if in_verify or in_main:
                        outcomes.add("verified_by_run")
                elif base == "delegated_and_reported":
                    if in_main or in_verify:
                        outcomes.add(base)

            # commit positions (전체에서 추적)
            if "committed" in sigs:
                if idx < intro_end:
                    commit_positions.append("intro")
                elif idx < verify_start:
                    commit_positions.append("main")
                else:
                    commit_positions.append("verify")

    if len(commit_positions) >= 2 and "main" in commit_positions:
        outcomes.add("incremental_commits")
    elif len(commit_positions) == 1 and commit_positions[0] == "verify":
        outcomes.add("single_final_commit")

    # abandoned_or_paused
    if verify_start >= n and not outcomes:
        last = turns_slice.iloc[-1]
        if last_turn_has_error_or_unresponded(last):
            outcomes.add("abandoned_or_paused")

    return sorted(outcomes), sorted(git_intents), outcome_sequence


def compute_function_groups_by_phase(fg_per_turn: list[set], phase_boundaries: dict) -> dict:
    ie = phase_boundaries["intro_end"]
    vs = phase_boundaries["verify_start"]
    intro = Counter(fg for fgs in fg_per_turn[:ie] for fg in fgs)
    main = Counter(fg for fgs in fg_per_turn[ie:vs] for fg in fgs)
    verify = Counter(fg for fgs in fg_per_turn[vs:] for fg in fgs)
    return {"intro": dict(intro), "main": dict(main), "verify": dict(verify)}


def compute_function_group_sequence(fg_per_turn: list[list[str]]) -> list[str]:
    """turn 별 첫 fg 를 시퀀스로. dedupe consecutive."""
    seq = []
    for fgs in fg_per_turn:
        if not fgs:
            continue
        # 한 turn 안에서 여러 fg 면 그대로 다 추가 (순서 유지, 한 turn 안에서는 중복 제거)
        seen = set()
        for fg in fgs:
            if fg not in seen:
                seen.add(fg)
                if not seq or seq[-1] != fg:
                    seq.append(fg)
    return seq


def compute_function_group_sequence_by_phase(fg_per_turn: list[list[str]], pb: dict) -> dict:
    return {
        "intro": compute_function_group_sequence(fg_per_turn[:pb["intro_end"]]),
        "main": compute_function_group_sequence(fg_per_turn[pb["intro_end"]:pb["verify_start"]]),
        "verify": compute_function_group_sequence(fg_per_turn[pb["verify_start"]:]),
    }


def compute_tool_sequence(turns_slice: pd.DataFrame) -> list[str]:
    seq = []
    for _, row in turns_slice.iterrows():
        for tu in row["tool_uses"]:
            name = tu.get("name") or ""
            # mcp 도구는 name 그대로
            if name:
                if not seq or seq[-1] != name:
                    seq.append(name)
    return seq


def extract_user_utterances(turns_slice: pd.DataFrame, max_per_episode: int = 8) -> list[str]:
    out = []
    for _, row in turns_slice.iterrows():
        if row["role"] == "user" and row["content"]:
            txt = (row["content"] or "").strip()
            if txt and not txt.startswith("<command-name>"):
                # 짧게 자르기
                out.append(txt[:200].replace("\n", " "))
                if len(out) >= max_per_episode:
                    break
    return out


# ---------- 사후 클러스터링 (라벨 → situation_cluster) ----------

CLUSTER_KEYWORDS = [
    # 키워드 (소문자 부분문자열) -> 클러스터 이름
    (["incident", "error", "오류", "에러", "이슈", "디버그", "debug", "장애", "버그", "fail", "실패"], "error_or_incident_investigation"),
    (["refactor", "리팩토링", "리팩터링", "naming", "rename", "정리", "cleanup"], "refactoring"),
    (["test", "테스트", "spec", "단위 테스트", "단위테스트"], "testing"),
    (["doc", "문서", "readme", "guide", "가이드", "보고서", "report"], "documentation"),
    (["explore", "explor", "investigat", "조사", "탐색", "분석", "analyze", "review", "리뷰"], "exploration_or_review"),
    (["plan", "기획", "design", "설계", "아키텍처", "architecture"], "planning_or_design"),
    (["setup", "config", "설정", "환경", "install", "초기화", "init"], "setup_or_configuration"),
    (["mcp", "skill", "스킬", "agent", "subagent", "automation", "자동화", "hook", "plugin", "플러그인"], "claude_code_tooling"),
    (["api", "엔드포인트", "endpoint", "graphql", "rest"], "api_work"),
    (["db", "쿼리", "query", "데이터베이스", "database", "mysql", "sql", "테이블"], "data_or_db_work"),
    (["log", "grafana", "loki", "로그"], "log_investigation"),
    (["배포", "deploy", "release", "릴리즈", "build", "빌드"], "deploy_or_build"),
    (["feature", "추가", "구현", "implement", "기능", "add "], "feature_implementation"),
    (["fix", "수정", "고치", "패치", "patch"], "bug_fix"),
    (["스크립트", "script", "데이터 처리", "변환", "convert"], "scripting_or_data_processing"),
    (["pr ", "풀 리퀘", "리뷰", "pull request"], "code_review_or_pr"),
    (["커밋", "commit", "push", "푸시", "git "], "git_workflow"),
]


def merge_adjacent_episodes(rows: list[dict]) -> list[dict]:
    """단계 4: 보조 신호 기반 인접 머지.

    합칠 조건 (2개 이상 만족 시 머지):
      - 라벨 토큰 jaccard >= 0.5
      - goal 토큰 jaccard >= 0.5
      - 기능 그룹 overlap(작은쪽) >= 0.7
      - 시간 갭 <= 5분
      - prev outcome 비어있고 curr verify-only (이어진 검증)
    추가 강한 신호 (단독으로도 머지):
      - 같은 세션 + 시간 갭 <= 2분 + (라벨 jaccard >= 0.3 또는 fg overlap >= 0.5)
    """
    if not rows:
        return rows

    merged = [rows[0]]
    for cur in rows[1:]:
        prev = merged[-1]
        # 다른 세션이면 머지 안 함
        if set(prev["session_ids"]) != set(cur["session_ids"]):
            # 단, prev 가 한 세션만 갖고 cur 도 한 세션이면 다른 세션 — 분할 유지
            if not (set(prev["session_ids"]) & set(cur["session_ids"])):
                merged.append(cur)
                continue

        prev_label_tok = tokenize(prev["label"])
        cur_label_tok = tokenize(cur["label"])
        prev_goal_tok = tokenize(prev["goal"])
        cur_goal_tok = tokenize(cur["goal"])

        prev_fg = set(prev["function_groups_used"])
        cur_fg = set(cur["function_groups_used"])
        fg_ov = overlap_small_side(prev_fg, cur_fg)

        try:
            t_prev_end = parse_ts(prev["end_time"])
            t_cur_start = parse_ts(cur["start_time"])
            gap_min = (t_cur_start - t_prev_end).total_seconds() / 60.0
        except Exception:
            gap_min = 999

        lab_j = jaccard(prev_label_tok, cur_label_tok)
        goal_j = jaccard(prev_goal_tok, cur_goal_tok)

        signals = 0
        if lab_j >= 0.5:
            signals += 1
        if goal_j >= 0.5:
            signals += 1
        if fg_ov >= 0.7:
            signals += 1
        if gap_min <= 5:
            signals += 1
        if not prev["outcomes"] and cur["episode_kind"] == "investigation_only":
            signals += 1

        # 강한 단독 신호
        strong = gap_min <= 2 and (lab_j >= 0.3 or fg_ov >= 0.5)
        # 같은 세션 + 10분 이내 + (prev verify 가 비어있거나 cur 가 매우 짧음) → 머지
        same_session = bool(set(prev["session_ids"]) & set(cur["session_ids"]))
        bridging = same_session and gap_min <= 10 and (
            cur["turn_count"] <= 2 or prev["turn_count"] <= 2 or fg_ov >= 0.3
        )

        if signals >= 2 or strong or bridging:
            # 머지
            prev["turn_ids"] = list(prev["turn_ids"]) + list(cur["turn_ids"])
            prev["session_ids"] = sorted(set(list(prev["session_ids"]) + list(cur["session_ids"])))
            prev["project_dirs"] = sorted(set(list(prev["project_dirs"]) + list(cur["project_dirs"])))
            prev["end_time"] = cur["end_time"]
            # 라벨: 더 긴 쪽 유지 또는 결합
            if len(cur["label"]) > len(prev["label"]) and len(prev["label"]) < 60:
                prev["label"] = cur["label"]
            prev["turn_count"] += cur["turn_count"]
            prev["function_groups_used"] = sorted(set(list(prev["function_groups_used"]) + list(cur["function_groups_used"])))
            prev["tools_used"] = sorted(set(list(prev["tools_used"]) + list(cur["tools_used"])))
            prev["claude_code_features"] = sorted(set(list(prev["claude_code_features"]) + list(cur["claude_code_features"])))
            # outcome / git_intent set union (머지 후 재계산이 권위, 여기는 임시값)
            prev["outcomes"] = sorted(set(list(prev["outcomes"]) + list(cur["outcomes"])))
            prev["outcome_sequence"] = list(prev.get("outcome_sequence", [])) + list(cur.get("outcome_sequence", []))
            prev["git_intents_used"] = sorted(set(list(prev["git_intents_used"]) + list(cur["git_intents_used"])))
            # function_group_sequence 연결
            prev["function_group_sequence"] = list(prev["function_group_sequence"]) + list(cur["function_group_sequence"])
            prev["tool_sequence"] = list(prev["tool_sequence"]) + list(cur["tool_sequence"])
            prev["user_utterances"] = list(prev["user_utterances"]) + list(cur["user_utterances"])
            # phase / fg_by_phase 등 dict 필드는 union (대략)
            prev_pb = json.loads(prev["phase_boundaries_json"])
            prev_fg_phase = json.loads(prev["function_groups_by_phase_json"])
            cur_fg_phase = json.loads(cur["function_groups_by_phase_json"])
            for phase in ("intro", "main", "verify"):
                a = Counter(prev_fg_phase.get(phase, {}))
                b = Counter(cur_fg_phase.get(phase, {}))
                prev_fg_phase[phase] = dict(a + b)
            prev["function_groups_by_phase_json"] = json.dumps(prev_fg_phase)
            # phase_boundaries 는 머지 후 의미가 흐려지므로 prev 의 값 그대로 + verify_start 를 새 끝으로
            new_pb = {"intro_end": prev_pb["intro_end"], "verify_start": prev_pb["verify_start"]}
            prev["phase_boundaries_json"] = json.dumps(new_pb)
            # episode_kind 는 우선순위 (with_changes > investigation > tooling)
            order = {"with_changes": 2, "investigation_only": 1, "tooling_only": 0}
            if order[cur["episode_kind"]] > order[prev["episode_kind"]]:
                prev["episode_kind"] = cur["episode_kind"]
            prev["situation_cluster"] = cluster_label(prev["label"])
        else:
            merged.append(cur)
    return merged


def cluster_label(label: str) -> str:
    s = (label or "").lower()
    for kws, name in CLUSTER_KEYWORDS:
        for kw in kws:
            if kw in s:
                return name
    return "misc_task"


# ---------- 메인 ----------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--turns", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--repo", default=None,
                    help="repo root (config/*.yaml 위치). 미지정 시 스크립트 위치에서 추론")
    args = ap.parse_args()

    repo_root = Path(args.repo) if args.repo else Path(__file__).resolve().parent.parent
    cfg = load_split_config(repo_root)

    print(f"[Stage B] reading {args.turns}")
    turns = pd.read_parquet(args.turns)

    # 시간 정렬 (안정성)
    turns = turns.sort_values("timestamp").reset_index(drop=True)
    print(f"[Stage B] turns: {len(turns)}")

    print("[Stage B] 1차 분할")
    episodes_idx = first_pass_split(turns, cfg)
    print(f"[Stage B] 1차 에피소드 수: {len(episodes_idx)}")

    episode_rows = []
    for ep_i, idxs in enumerate(episodes_idx):
        sl = turns.iloc[idxs].reset_index(drop=True)
        n = len(sl)
        tool_uses_list = list(sl["tool_uses"])
        fg_per_turn = [turn_function_groups(tu) for tu in tool_uses_list]  # list[list]
        fg_per_turn_set = [set(x) for x in fg_per_turn]

        phase_boundaries = compute_phase_boundaries(tool_uses_list, fg_per_turn_set)
        episode_kind = classify_episode_kind(fg_per_turn_set)
        outcomes, git_intents, outcome_sequence = aggregate_outcomes(sl, phase_boundaries)
        fg_by_phase = compute_function_groups_by_phase(fg_per_turn_set, phase_boundaries)
        fg_seq = compute_function_group_sequence(fg_per_turn)
        fg_seq_phase = compute_function_group_sequence_by_phase(fg_per_turn, phase_boundaries)
        tool_seq = compute_tool_sequence(sl)
        user_utts = extract_user_utterances(sl)

        label, goal = build_episode_label_and_goal(sl)
        features = detect_claude_code_features(sl)
        situation = cluster_label(label)

        function_groups_used = sorted({fg for fgs in fg_per_turn_set for fg in fgs})
        tools_used = sorted({tu.get("name") for tu in (t for ts in tool_uses_list for t in ts) if tu.get("name")})
        # 위 컴프리헨션 bug 회피
        tools_used = sorted({tu.get("name") for tlist in tool_uses_list for tu in tlist if tu.get("name")})

        episode_rows.append({
            "episode_id": f"ep_{ep_i:05d}",
            "session_ids": sorted(set(sl["session_id"])),
            "turn_ids": list(sl["turn_id"]),
            "project_dirs": sorted(set(sl["project_dir"])),
            "start_time": sl["timestamp"].iloc[0],
            "end_time": sl["timestamp"].iloc[-1],
            "label": label,
            "situation_cluster": situation,
            "goal": goal,
            "claude_code_features": features,
            "turn_count": n,
            "function_groups_used": function_groups_used,
            "tools_used": tools_used,
            "episode_kind": episode_kind,
            "phase_boundaries_json": json.dumps(phase_boundaries),
            "outcomes": outcomes,
            "outcome_sequence": outcome_sequence,
            "git_intents_used": git_intents,
            "function_groups_by_phase_json": json.dumps(fg_by_phase),
            "function_group_sequence": fg_seq,
            "function_group_sequence_by_phase_json": json.dumps(fg_seq_phase),
            "tool_sequence": tool_seq,
            "user_utterances": user_utts,
        })

    print(f"[Stage B] 에피소드 라벨링 완료: {len(episode_rows)}")

    # ---------- 단계 4: 양방향 머지 ----------
    # 보조 신호 기반 결정론적 머지 (LLM 호출 없음 — 명세에 따라 휴리스틱 보조 신호로 판단)
    print("[Stage B] 양방향 머지 점검")
    episode_rows = merge_adjacent_episodes(episode_rows)
    print(f"[Stage B] 머지 후 에피소드 수: {len(episode_rows)}")

    # ---------- 머지 후 phase / outcome 재계산 ----------
    print("[Stage B] 머지 후 phase / outcome 재계산")
    turns_by_id = {row["turn_id"]: row for _, row in turns.iterrows()}
    for r in episode_rows:
        # turns slice 다시 구성
        sub_rows = [turns_by_id[tid] for tid in r["turn_ids"] if tid in turns_by_id]
        sl = pd.DataFrame(sub_rows).reset_index(drop=True)
        if len(sl) == 0:
            continue
        tool_uses_list = list(sl["tool_uses"])
        fg_per_turn = [turn_function_groups(tu) for tu in tool_uses_list]
        fg_per_turn_set = [set(x) for x in fg_per_turn]
        pb = compute_phase_boundaries(tool_uses_list, fg_per_turn_set)
        outcomes, git_intents, outcome_sequence = aggregate_outcomes(sl, pb)
        fg_by_phase = compute_function_groups_by_phase(fg_per_turn_set, pb)
        fg_seq_phase = compute_function_group_sequence_by_phase(fg_per_turn, pb)
        r["phase_boundaries_json"] = json.dumps(pb)
        r["outcomes"] = outcomes
        r["outcome_sequence"] = outcome_sequence
        r["git_intents_used"] = git_intents
        r["function_groups_by_phase_json"] = json.dumps(fg_by_phase)
        r["function_group_sequence_by_phase_json"] = json.dumps(fg_seq_phase)
        r["episode_kind"] = classify_episode_kind(fg_per_turn_set)


    # outcome / git intent 분포 통계
    oc = Counter()
    gi = Counter()
    kinds = Counter()
    for r in episode_rows:
        for o in r["outcomes"]:
            oc[o] += 1
        for g in r["git_intents_used"]:
            gi[g] += 1
        kinds[r["episode_kind"]] += 1
    print("[Stage B] episode_kind:", dict(kinds))
    print("[Stage B] outcomes:", dict(oc))
    print("[Stage B] git_intents:", dict(gi))

    # Stage C 호환: dict 필드도 함께 (string 으로 직렬화한 것을 다시 dict 로 풀어 저장)
    # parquet 의 dict 필드는 빈 dict 일 경우 schema 추론 문제 있어 json 문자열 그대로 두되,
    # Stage C 가 함께 읽을 수 있도록 두 키 다 채움.
    for r in episode_rows:
        r["function_groups_by_phase"] = json.loads(r["function_groups_by_phase_json"])
        r["phase_boundaries"] = json.loads(r["phase_boundaries_json"])
        r["function_group_sequence_by_phase"] = json.loads(r["function_group_sequence_by_phase_json"])
        # parquet 저장 시 빈 dict 문제 회피 — JSON 문자열 형태로 변환
        r["function_groups_by_phase"] = json.dumps(r["function_groups_by_phase"])
        r["phase_boundaries"] = json.dumps(r["phase_boundaries"])
        r["function_group_sequence_by_phase"] = json.dumps(r["function_group_sequence_by_phase"])

    out_df = pd.DataFrame(episode_rows)
    out_df.to_parquet(args.output, index=False)
    print(f"[Stage B] saved {args.output} (rows={len(out_df)})")


if __name__ == "__main__":
    main()
