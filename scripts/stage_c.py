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

    # 어조 키워드 카운트 (그룹 전체 본문 매칭)
    tone_counter: Counter = Counter()
    for _, ep in group_eps.iterrows():
        utters = " ".join(str(x) for x in _to_list(ep.get("user_utterances")))
        for name, cnt in count_tone_keywords(utters).items():
            tone_counter[name] += cnt

    # 시스템 마커 카운트
    markers = count_system_markers(group_eps)

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
        "tone_keyword_counts": dict(tone_counter),
        "system_markers": markers,
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


# 일반 어조 키워드 — 데이터 무관 (한국·영어 일반 표현)
# 패턴 검출 룰이 아니라 "본문에 이런 어조가 얼마나 자주 나오나" 안내용.
# Stage D 가 본문 훑을 때 참조하는 보조 신호. 임계값 없음.
TONE_KEYWORDS = {
    "plan_first": [r"계획을\s*세", r"plan\s*을", r"plan\s*먼저", r"plan\s*부터", r"플랜을\s*(설계|세|만들)", r"어떻게\s*할지"],
    "role_split": [r"내가\s*.{0,10}(할게|할께|할거야|만질게|만질께)", r"나는\s*.{0,15}(할게|할께|직접)", r"너가\s*.{0,15}(처리|작업|해)"],
    "option_choose": [r"옵션\s*[A-Z\d]", r"방안\s*[A-Z\d]", r"[A-Z]\s*로\s*가자", r"[A-Z]\s*로\s*해줘"],
    "hypothesis_unfold": [r"만약\s.{0,20}(라면|이면|하면)", r"이런\s*가정(이|이라)", r"~?(가정|가설)\s*(에서|이라면)"],
    "polish_again": [r"너무\s*장황", r"가독성", r"읽기\s*(좋|쉽)게", r"보기\s*좋게", r"줄글", r"좀\s*더\s*명확"],
    "interrupt_correct": [r"아니\s.{0,5}(그게|그것|작업)", r"내가\s*원했던", r"그게\s*아니라"],
    "self_validate_full": [
        r"profile\s*로\s*(띄|실행)", r"직접\s*(띄|실행|돌)",
        r"alpha\s*(db|DB)", r"curl\s*(만들|줘|호출)",
    ],
    "ask_objective": [r"객관적으로", r"독립적으로\s*(재|검토)", r"이전\s*분석에\s*편향"],
    "diff_models": [r"gemini|gpt-|chatgpt|다른\s*모델"],
    "loop_n_times": [r"\d+\s*번\s*(까지)?\s*반복", r"만족할\s*때까지", r"결론.{0,5}나올때까지"],
    "external_doc_first": [r"\.md\s*(에서|를)", r"PRD|prd", r"notion\.so", r"페이지를?\s*(참고|읽|봐)"],
    "trace_chain_logs": [
        r"trace_?id", r"\.trace_id", r"dd\.trace",
        r"같은\s*(request|trace|호출).{0,15}(로그|봐|이어|검색)",
        r"(여러|다른|인접)\s*(서비스|app|모듈).{0,10}(로그|검색)",
    ],
}

# 시스템 마커 — Stage A 의 detect_system_markers 가 부여한 turn 단위 신호를
# episode 레벨로 합산. 메서드러지 패턴 후보로 격상 (continue/interrupted/notification).
SYSTEM_MARKER_NAMES = ("continue", "interrupted", "task_notification", "compact", "teammate_message")

# 노이즈 trigram (시스템 트랜스크립트에서 흘러나오는) — mini_pattern_candidates 에서 제외
# Stage A 에서 분리했지만 user_utterances 본문에도 남아 있을 수 있어 한 번 더 거름.
NOISE_TRIGRAMS = {
    # 인터럽트 마커 파편
    ("no", "user", "prompt"), ("user", "prompt", "no"), ("prompt", "no", "user"),
    ("request", "interrupted", "by"), ("interrupted", "by", "user"),
    ("by", "user", "for"), ("user", "for", "tool"), ("for", "tool", "use"),
    # Skill 헤더 파편 (Claude Code skill 호출 본문)
    ("base", "directory", "for"), ("directory", "for", "this"), ("for", "this", "skill"),
    ("this", "skill", "users"), ("skill", "users", "cobi"),
    # local-command-caveat 시스템 마커 파편
    ("local", "command", "caveat"), ("command", "caveat", "caveat"), ("caveat", "caveat", "the"),
    ("caveat", "the", "messages"), ("the", "messages", "below"), ("messages", "below", "were"),
    # claude 자체 task 컨텍스트 요약 파편
    ("of", "the", "conversation"),
    # 사용자 home/desktop 경로 파편 (마스킹 후에도 남는 토큰)
    ("users", "cobi", "yu"), ("cobi", "yu", "desktop"),
    ("yu", "desktop", "workspace"), ("desktop", "workspace", "wms"),
    ("desktop", "workspace", "logistics"),
}

# 노이즈 토큰 — trigram 한 자리에라도 들어가면 제외할 토큰 (개별 단어 기준)
NOISE_TOKENS_IN_TRIGRAM = {"caveat", "stdout", "stderr"}


def count_tone_keywords(text: str) -> dict:
    """본문 한 덩어리에서 어조 키워드 종류별 매칭 카운트."""
    out: dict = {}
    if not text:
        return out
    for name, patterns in TONE_KEYWORDS.items():
        c = 0
        for p in patterns:
            c += len(re.findall(p, text))
        if c:
            out[name] = c
    return out


def count_system_markers(group_eps: pd.DataFrame) -> dict:
    """그룹 안 에피소드들의 marker_counts 합산.
    Stage B 가 turn 별 marker_* feature 를 합쳐 episode 레벨 카운트로 만들었음.
    """
    out: Counter = Counter()
    interrupt_multi_eps = 0
    for _, ep in group_eps.iterrows():
        mc_raw = ep.get("marker_counts")
        if mc_raw is None:
            continue
        try:
            mc = json.loads(mc_raw) if isinstance(mc_raw, str) else dict(mc_raw)
        except (json.JSONDecodeError, TypeError):
            continue
        for name, cnt in mc.items():
            out[name] += cnt
        if mc.get("interrupted", 0) >= 2:
            interrupt_multi_eps += 1
    res = dict(out)
    if interrupt_multi_eps:
        res["interrupted_multi_episodes"] = interrupt_multi_eps
    return res


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

    # 2) user utterance trigram (시스템 노이즈 제외)
    trigrams: Counter = Counter()
    for _, ep in eps.iterrows():
        utters = " ".join(str(x) for x in _to_list(ep.get("user_utterances")))
        if not utters:
            utters = str(ep.get("goal") or "") + " " + str(ep.get("label") or "") + " " + str(ep.get("situation_raw") or "")
        toks = simple_tokenize(utters)
        for i in range(len(toks) - 2):
            tri = tuple(toks[i:i + 3])
            if tri in NOISE_TRIGRAMS:
                continue
            if any(t in NOISE_TOKENS_IN_TRIGRAM for t in tri):
                continue
            trigrams[tri] += 1

    # 3) tool arg pattern — episodes.parquet 에 인자 정보가 일반적으로 없음 → 빈 dict
    arg_patterns: dict = {}

    # 4) 의미 마커 — 전체 에피소드의 marker_counts 합산 (Stage B 가 부여)
    meaningful_markers: Counter = Counter()
    for _, ep in eps.iterrows():
        mc_raw = ep.get("marker_counts")
        if mc_raw is None:
            continue
        try:
            mc = json.loads(mc_raw) if isinstance(mc_raw, str) else dict(mc_raw)
        except (json.JSONDecodeError, TypeError):
            continue
        if mc.get("continue", 0):
            meaningful_markers["session_continue_episodes"] += 1
        if mc.get("interrupted", 0) >= 2:
            meaningful_markers["multi_interrupt_episodes"] += 1
        if mc.get("task_notification", 0):
            meaningful_markers["background_task_notification_episodes"] += 1
        if mc.get("compact", 0):
            meaningful_markers["context_compact_episodes"] += 1
        if mc.get("teammate_message", 0):
            meaningful_markers["teammate_message_episodes"] += 1

    return {
        "tool_microsequences": [(list(k), v) for k, v in micro.most_common(50)],
        "user_utterance_trigrams": [(list(k), v) for k, v in trigrams.most_common(50)],
        "tool_arg_patterns": arg_patterns,
        "meaningful_markers": dict(meaningful_markers),
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
