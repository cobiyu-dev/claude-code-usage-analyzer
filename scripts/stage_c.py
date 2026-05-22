#!/usr/bin/env python3
"""
Stage C — episodes.parquet 읽고 그룹별 메트릭, 시그니처, 미니 패턴 후보, 시계열을 집계.

입력: episodes.parquet (Stage B 출력)
출력: aggregated.json (Stage D 입력)

LLM 호출 없음. 산수만.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


# ---------- 헬퍼 ----------

def _to_list(v: Any) -> list:
    if v is None:
        return []
    if isinstance(v, list):
        return list(v)
    if isinstance(v, str):
        try:
            x = json.loads(v)
            return x if isinstance(x, list) else [x]
        except (json.JSONDecodeError, ValueError):
            return [v] if v else []
    if isinstance(v, dict):
        return [v]
    try:
        return list(v)
    except TypeError:
        return [v]


def _to_dict(v: Any) -> dict:
    if v is None:
        return {}
    if isinstance(v, dict):
        return v
    if isinstance(v, str):
        try:
            x = json.loads(v)
            return x if isinstance(x, dict) else {}
        except (json.JSONDecodeError, ValueError):
            return {}
    return {}


def jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 1.0
    u = a | b
    if not u:
        return 0.0
    return len(a & b) / len(u)


# ---------- 그룹별 메트릭 ----------

def avg(nums: list[float]) -> float:
    return sum(nums) / len(nums) if nums else 0.0


def compute_group_metrics(group_eps: pd.DataFrame, cluster_name: str) -> dict:
    n = len(group_eps)
    turn_counts = [int(x) for x in group_eps["turn_count"].fillna(0).tolist()]
    avg_turns = avg(turn_counts)

    durations = []
    for _, ep in group_eps.iterrows():
        try:
            s = datetime.fromisoformat(str(ep["start_time"]).replace("Z", "+00:00"))
            e = datetime.fromisoformat(str(ep["end_time"]).replace("Z", "+00:00"))
            durations.append((e - s).total_seconds() / 60.0)
        except (ValueError, TypeError):
            continue

    fg_counter: Counter = Counter()
    tools_counter: Counter = Counter()
    for _, ep in group_eps.iterrows():
        for fg in _to_list(ep.get("function_groups_used")):
            fg_counter[str(fg)] += 1
        for t in _to_list(ep.get("tools_used")):
            tools_counter[str(t)] += 1

    # phase 별 기능 그룹
    phase_fg = {"intro": Counter(), "main": Counter(), "verify": Counter()}
    outcome_dist: Counter = Counter()
    git_intent_dist: Counter = Counter()
    kind_dist: Counter = Counter()
    verify_nonempty = 0
    diagnostic_present = 0

    # outcome 시퀀스 (전이 + 3-gram)
    outcome_transitions: Counter = Counter()
    outcome_trigrams: Counter = Counter()

    for _, ep in group_eps.iterrows():
        fpb = _to_dict(ep.get("function_groups_by_phase"))
        for phase in ("intro", "main", "verify"):
            for k, v in _to_dict(fpb.get(phase, {})).items():
                try:
                    phase_fg[phase][str(k)] += int(v)
                except (ValueError, TypeError):
                    phase_fg[phase][str(k)] += 1
        outcome_dist.update(str(x) for x in _to_list(ep.get("outcomes")))
        git_intent_dist.update(str(x) for x in _to_list(ep.get("git_intents_used")))
        kind_dist[str(ep.get("episode_kind") or "with_changes")] += 1
        if _to_dict(fpb.get("verify", {})):
            verify_nonempty += 1
        if "diagnostic" in _to_list(ep.get("git_intents_used")):
            diagnostic_present += 1

        # outcome 시퀀스 분포
        seq = [str(x) for x in _to_list(ep.get("outcome_sequence"))]
        for i in range(len(seq) - 1):
            outcome_transitions[f"{seq[i]} → {seq[i+1]}"] += 1
        for i in range(len(seq) - 2):
            outcome_trigrams[f"{seq[i]} → {seq[i+1]} → {seq[i+2]}"] += 1

    # 대표 에피소드 선정
    reps = select_representatives(group_eps, fg_counter)

    return {
        "cluster_name": cluster_name,
        "episode_count": n,
        "total_turns": sum(turn_counts),
        "avg_turns_per_episode": avg_turns,
        "avg_duration_minutes": avg(durations),
        "function_groups_used": dict(fg_counter),
        "tools_used": dict(tools_counter),
        "episode_kind_distribution": dict(kind_dist),
        "phase_function_groups": {k: dict(v) for k, v in phase_fg.items()},
        "outcome_distribution": dict(outcome_dist),
        "outcome_transitions": dict(outcome_transitions.most_common(30)),
        "outcome_trigrams": dict(outcome_trigrams.most_common(30)),
        "git_intent_distribution": dict(git_intent_dist),
        "verify_phase_share": verify_nonempty / n if n else 0.0,
        "diagnostic_git_share": diagnostic_present / n if n else 0.0,
        "representative_episodes": reps,
        "signatures": extract_signatures(group_eps),
        "phase_signatures": extract_phase_signatures(group_eps),
    }


def select_representatives(group_eps: pd.DataFrame, fg_counter: Counter) -> list[str]:
    """대표 에피소드 선정 (구조 보너스 적용)."""
    avg_turns = avg([int(x) for x in group_eps["turn_count"].fillna(0).tolist()]) or 1.0
    top_fg = set(name for name, _ in fg_counter.most_common(5))

    scored = []
    for _, ep in group_eps.iterrows():
        turn_cnt = int(ep.get("turn_count") or 0)
        turn_score = 1.0 - abs(turn_cnt - avg_turns) / (avg_turns + 1e-9)
        turn_score = max(0.0, turn_score)
        ep_fg = set(str(x) for x in _to_list(ep.get("function_groups_used")))
        func_overlap = jaccard(ep_fg, top_fg)
        base = (turn_score + func_overlap) / 2

        bonus = 0.0
        pb = _to_dict(ep.get("phase_boundaries"))
        if pb.get("verify_start") is not None:
            # verify phase 가 비어있지 않으면 보너스
            verify_fg = _to_dict(_to_dict(ep.get("function_groups_by_phase")).get("verify", {}))
            if verify_fg:
                bonus += 0.15
        if _to_list(ep.get("outcomes")):
            bonus += 0.10
        if "diagnostic" in _to_list(ep.get("git_intents_used")):
            bonus += 0.15

        scored.append((str(ep.get("episode_id") or ""), base + bonus, _to_list(ep.get("outcomes"))))

    scored.sort(key=lambda x: -x[1])
    # outcome 다양성
    selected: list[str] = []
    seen_outcomes: set = set()
    for ep_id, _score, outcomes in scored[:8]:
        key = frozenset(str(o) for o in outcomes)
        if key not in seen_outcomes or len(selected) < 3:
            selected.append(ep_id)
            seen_outcomes.add(key)
        if len(selected) >= 5:
            break
    return selected


def extract_signatures(group_eps: pd.DataFrame) -> list[tuple[list[str], int]]:
    sequences = []
    for _, ep in group_eps.iterrows():
        seq = [str(x) for x in _to_list(ep.get("function_group_sequence"))]
        if seq:
            sequences.append(seq)

    ngrams: Counter = Counter()
    for n in (2, 3, 4):
        for seq in sequences:
            for i in range(len(seq) - n + 1):
                ngrams[tuple(seq[i:i + n])] += 1

    scored = sorted(ngrams.items(), key=lambda kv: -kv[1] * len(kv[0]))[:5]
    return [(list(k), v) for k, v in scored]


def extract_phase_signatures(group_eps: pd.DataFrame) -> dict:
    phase_seqs = {"intro": [], "main": [], "verify": []}
    for _, ep in group_eps.iterrows():
        seqs = _to_dict(ep.get("function_group_sequence_by_phase"))
        for phase in ("intro", "main", "verify"):
            s = [str(x) for x in _to_list(seqs.get(phase))]
            if s:
                phase_seqs[phase].append(s)

    out = {}
    for phase, seqs in phase_seqs.items():
        ngrams: Counter = Counter()
        for n in (2, 3):
            for seq in seqs:
                for i in range(len(seq) - n + 1):
                    ngrams[tuple(seq[i:i + n])] += 1
        scored = sorted(ngrams.items(), key=lambda kv: -kv[1] * len(kv[0]))[:3]
        out[phase] = [(list(k), v) for k, v in scored]
    return out


# ---------- 메타 ----------

def aggregate_meta(eps: pd.DataFrame) -> dict:
    feats: Counter = Counter()
    fgs: Counter = Counter()
    tools: Counter = Counter()
    for _, ep in eps.iterrows():
        for f in _to_list(ep.get("claude_code_features")):
            feats[str(f)] += 1
        for fg in _to_list(ep.get("function_groups_used")):
            fgs[str(fg)] += 1
        for t in _to_list(ep.get("tools_used")):
            tools[str(t)] += 1

    return {
        "top_claude_code_features": feats.most_common(5),
        "top_function_groups": fgs.most_common(5),
        "top_tools": tools.most_common(10),
    }


# ---------- 시계열 ----------

def aggregate_timeseries(eps: pd.DataFrame, period_days: int) -> list[dict] | None:
    if period_days < 14:
        return None

    unit = "week" if period_days < 90 else "month"
    buckets: dict[str, list] = defaultdict(list)
    for _, ep in eps.iterrows():
        try:
            t = datetime.fromisoformat(str(ep["start_time"]).replace("Z", "+00:00"))
        except (ValueError, TypeError):
            continue
        if unit == "week":
            iso = t.isocalendar()
            key = f"W{iso[1]:02d}({iso[0]})"
        else:
            key = t.strftime("%Y-%m")
        buckets[key].append(ep)

    out = []
    for key, items in sorted(buckets.items()):
        fgc: Counter = Counter()
        cls: Counter = Counter()
        for ep in items:
            for fg in _to_list(ep.get("function_groups_used")):
                fgc[str(fg)] += 1
            cls[str(ep.get("situation_cluster") or "")] += 1
        out.append({
            "label": key,
            "episode_count": len(items),
            "top_function_groups": fgc.most_common(2),
            "dominant_clusters": cls.most_common(2),
        })
    return out


# ---------- 미니 패턴 (광역 모드) ----------

WORD_TOKEN = re.compile(r'[A-Za-z0-9가-힣]+')


def simple_tokenize(text: str) -> list[str]:
    return [m.group(0).lower() for m in WORD_TOKEN.finditer(text or "")]


def extract_mini_patterns(eps: pd.DataFrame) -> dict:
    """
    turns 시퀀스 정보가 episodes.parquet 에 충분히 안 들어있을 수 있으므로,
    가용한 필드(tools_used, function_group_sequence, user_utterances) 기반으로 추출.
    """
    # 1) tool microsequence — function_group_sequence 가 있으면 그것으로, 없으면 tools_used 순서로
    micro: Counter = Counter()
    for _, ep in eps.iterrows():
        seq = [str(x) for x in _to_list(ep.get("tool_sequence"))]
        if not seq:
            seq = [str(x) for x in _to_list(ep.get("tools_used"))]
        for n in (2, 3):
            for i in range(len(seq) - n + 1):
                micro[tuple(seq[i:i + n])] += 1

    # 2) user utterance trigram
    trigrams: Counter = Counter()
    for _, ep in eps.iterrows():
        utters = " ".join(str(x) for x in _to_list(ep.get("user_utterances")))
        if not utters:
            utters = str(ep.get("goal") or "") + " " + str(ep.get("label") or "") + " " + str(ep.get("situation_raw") or "")
        toks = simple_tokenize(utters)
        for i in range(len(toks) - 2):
            trigrams[tuple(toks[i:i + 3])] += 1

    # 3) tool arg pattern — episodes.parquet 에 인자 정보가 일반적으로 없음 → 빈 dict
    arg_patterns: dict = {}

    return {
        "tool_microsequences": [(list(k), v) for k, v in micro.most_common(50)],
        "user_utterance_trigrams": [(list(k), v) for k, v in trigrams.most_common(50)],
        "tool_arg_patterns": arg_patterns,
    }


# ---------- 메인 ----------

def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--episodes", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--mode", choices=["broad", "curated"], default="broad")
    args = p.parse_args()

    ep_path = Path(args.episodes).expanduser()
    if not ep_path.exists():
        print(f"Error: episodes.parquet 없음: {ep_path}", file=sys.stderr)
        return 1

    eps = pd.read_parquet(ep_path)
    if eps.empty:
        print("Error: episodes.parquet 이 비어있습니다.", file=sys.stderr)
        return 1

    print(f"[Stage C] {len(eps)} 에피소드 집계", file=sys.stderr)

    # 기간 계산
    starts = pd.to_datetime(eps["start_time"], errors="coerce", utc=True)
    ends = pd.to_datetime(eps["end_time"], errors="coerce", utc=True)
    start_date = starts.min()
    end_date = ends.max()
    period_days = max(1, (end_date - start_date).days + 1) if pd.notna(start_date) and pd.notna(end_date) else 0

    # 그룹별 메트릭
    groups: list[dict] = []
    for cluster, group_eps in eps.groupby("situation_cluster", dropna=False):
        groups.append(compute_group_metrics(group_eps, str(cluster) if cluster is not None else "(unlabeled)"))

    meta = aggregate_meta(eps)
    timeseries = aggregate_timeseries(eps, period_days)

    mini = extract_mini_patterns(eps) if args.mode == "broad" else None

    # 개인 로컬 셋업 (다른 사람과 공유 안 하는 ~/.claude/ 설정 들) 자동 수집
    local_setup = None
    try:
        import yaml
        from lib.local_setup_extractor import extract_all as extract_local_setup
        repo_root = Path(__file__).resolve().parent.parent
        sp_path = repo_root / "config" / "secret_patterns.yaml"
        sp = []
        if sp_path.exists():
            with sp_path.open() as f:
                sp = (yaml.safe_load(f) or {}).get("secret_patterns") or []
        local_setup = extract_local_setup(repo_root, sp)
    except Exception as e:
        print(f"[Stage C] local_setup 수집 실패 (무시): {e}", file=sys.stderr)

    result = {
        "start_date": str(start_date.date()) if pd.notna(start_date) else None,
        "end_date": str(end_date.date()) if pd.notna(end_date) else None,
        "period_days": period_days,
        "session_count": (
            len({str(s) for sids in eps["session_ids"] for s in _to_list(sids)})
            if "session_ids" in eps.columns else 0
        ),
        "episode_count": int(len(eps)),
        "mode": args.mode,
        "groups": groups,
        "top_claude_code_features": meta["top_claude_code_features"],
        "top_function_groups": meta["top_function_groups"],
        "top_tools": meta["top_tools"],
        "timeseries": timeseries,
        "mini_pattern_candidates": mini,
        "local_setup": local_setup,
    }

    out_path = Path(args.output).expanduser()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2, default=str)

    mini_n = sum(len(v) if isinstance(v, list) else 0 for v in (mini or {}).values())
    print(f"✓ Stage C 완료 → {out_path} (그룹 {len(groups)}, 미니 패턴 후보 {mini_n})", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
