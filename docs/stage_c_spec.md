# Stage C 설계 명세

## 역할

```
입력: episodes.parquet (Stage B 출력)

처리: 코드만 (LLM 호출 없음)
  1. 에피소드 그룹화 (situation_cluster 기준)
  2. 그룹별 메트릭 계산
  3. 시그니처 도구 시퀀스 추출
  4. 메타 정보 집계 (자주 쓰는 기능/도구 top N)
  5. 시계열 데이터 (기간 ≥ 2주일 때)

출력: aggregated.json (Stage D 입력)
```

LLM 호출 없음. 산수만. 사용자 무관 알고리즘.

---

## 작업 1: 에피소드 그룹화

Stage B의 `situation_cluster` 필드 기준으로 묶기.

```python
def group_episodes(episodes):
    groups = defaultdict(list)
    for ep in episodes:
        groups[ep.situation_cluster].append(ep)
    return groups
```

---

## 작업 2: 그룹별 메트릭

```python
@dataclass
class GroupMetrics:
    cluster_name: str
    episode_count: int
    total_turns: int
    avg_turns_per_episode: float
    avg_duration_minutes: float
    
    function_groups_used: dict      # {"log_search": 12, ...}
    tools_used: dict                # {"grafana_query_logs": 12, ...}
    
    # 내부 구조 집계 (작업 6)
    episode_kind_distribution: dict # {"with_changes": 12, "investigation_only": 8,
                                    #  "tooling_only": 1}
    phase_function_groups: dict     # {"intro": {"log_search": 8, ...},
                                    #  "main":  {"file_edit": 12, ...},
                                    #  "verify":{"db_query": 5, "shell_exec": 4, ...}}
    outcome_distribution: dict      # {"committed": 9, "verified_by_run": 4,
                                    #  "verified_by_data": 3, "delegated_and_reported": 2,
                                    #  "abandoned_or_paused": 1,
                                    #  "incremental_commits": 3, "single_final_commit": 6,
                                    #  "pr_with_structured_body": 5}
    git_intent_distribution: dict   # {"diagnostic": 5, "output": 9, "transition": 2}
    verify_phase_share: float       # verify 가 비어있지 않은 에피소드 비율 (0.0~1.0)
    diagnostic_git_share: float     # diagnostic git 의도가 들어있는 에피소드 비율
    
    representative_episodes: list   # 그룹 내 대표 에피소드 ID 3-5개
```

### 대표 에피소드 선정

빈도만으로 고르면 도입부에 묻힌 패턴(완료 후 검증, 회귀 추적)이 누락된다.
대표성 점수 + **구조 다양성 보너스** 로 선정한다.

```python
def score_representativeness(ep, group):
    # 기본 대표성
    turn_score = 1 - abs(ep.turn_count - group.avg_turns) / group.avg_turns
    func_overlap = jaccard(ep.function_groups, group.top_function_groups)
    base = (turn_score + func_overlap) / 2

    # 구조 보너스 (에피소드 내부 구조 라벨이 풍부할수록 가점)
    bonus = 0.0
    if ep.phase_boundaries.get("verify_start") is not None \
       and len(ep.turns) > ep.phase_boundaries["verify_start"]:
        bonus += 0.15   # verify phase 존재
    if ep.outcomes:
        bonus += 0.10   # outcome 신호 1개 이상
    if "diagnostic" in ep.git_intents_used:
        bonus += 0.15   # 회귀 추적 신호

    return base + bonus

def select_representatives(group, n=5):
    scored = [(ep, score_representativeness(ep, group)) for ep in group.episodes]
    scored.sort(key=lambda x: -x[1])

    # 상위 8개에서 outcome 다양성 보장
    candidates = [ep for ep, _ in scored[:8]]
    selected, seen_outcomes = [], set()
    for ep in candidates:
        ep_outcomes = frozenset(ep.outcomes)
        if ep_outcomes not in seen_outcomes or len(selected) < 3:
            selected.append(ep)
            seen_outcomes.add(ep_outcomes)
        if len(selected) >= n:
            break
    return selected
```

선정 결과는 Stage D의 LLM이 패턴 추출 시 참고함. 동일 outcome 만 가진 에피소드만 골리는 일이 없도록 다양성 보장.

---

## 작업 2.5: phase·outcome·git 의도 집계

Stage B 가 에피소드마다 부여한 `phase_boundaries`, `outcomes`, `git_intents_used`,
`function_groups_by_phase` 를 그룹 단위로 합산.

```python
def aggregate_structure(group):
    phase_fg = {"intro": Counter(), "main": Counter(), "verify": Counter()}
    outcome_dist = Counter()
    git_intent_dist = Counter()
    verify_nonempty = 0
    diagnostic_present = 0

    for ep in group.episodes:
        for phase in ("intro", "main", "verify"):
            phase_fg[phase].update(ep.function_groups_by_phase.get(phase, {}))
        outcome_dist.update(ep.outcomes)
        git_intent_dist.update(ep.git_intents_used)
        if ep.function_groups_by_phase.get("verify"):
            verify_nonempty += 1
        if "diagnostic" in ep.git_intents_used:
            diagnostic_present += 1

    n = len(group.episodes)
    kind_dist = Counter(ep.episode_kind for ep in group.episodes)
    return {
        "episode_kind_distribution": dict(kind_dist),
        "phase_function_groups": {k: dict(v) for k, v in phase_fg.items()},
        "outcome_distribution": dict(outcome_dist),
        "git_intent_distribution": dict(git_intent_dist),
        "verify_phase_share": verify_nonempty / n if n else 0.0,
        "diagnostic_git_share": diagnostic_present / n if n else 0.0,
    }
```

### 이 집계가 Stage D 에서 어떻게 쓰이나

- `phase_function_groups["verify"]` 에 db_query/shell_exec 가 높으면
  → "작업 종료부에서 데이터로 검증한다" 패턴 후보
- `outcome_distribution["delegated_and_reported"]` 가 높으면
  → "위임 후 결과 보고만 받음" 패턴 후보
- `diagnostic_git_share` 가 높으면
  → "현상만 보지 않고 git 으로 회귀 시점 추적" 패턴 후보

빈도만 보고 "이 그룹 = 이 패턴" 으로 결정하지 말 것. 후보 식별 신호로만 쓰고,
실제 패턴 추출은 Stage D 의 LLM 이 대표 에피소드의 actual turn 시퀀스를 보고 판단.

---

## 작업 3: 시그니처 도구 시퀀스 추출

각 그룹에서 자주 나타나는 도구 사용 순서 (n-gram).

### 누가 보는가 (용도)

시그니처는 **Stage D 의 LLM 만** 본다. 보고서에 직접 노출되지 않는다.

| 누가 | 어떻게 쓰는가 |
|---|---|
| Stage D LLM | 그룹의 대표 시퀀스를 보고 "이 그룹에서 보통 어떤 도구를 어떤 순서로 쓰는가" 를 파악. 패턴 후보 본문 작성 시 도구 표기 근거로 사용. |
| 보고서 독자 | **보지 않음**. 시그니처 자체가 보고서에 들어가지 않음. 본문이 자연어로 "grafana → DB 로 식별자 잇기" 식으로 풀려야 함. |
| 자가 디버깅 | aggregated.json 안에 남아있어 분석 결과가 이상할 때 디버그에 사용. |

### Stage D 가 쓰는 방법

1. 그룹의 top 3-5 시그니처를 본다 (예: `(log_search, code_search, log_search)`).
2. 그 시그니처가 무엇을 의미하는지 대표 에피소드의 actual turn 시퀀스(turns.parquet 참조) 와 대조한다.
3. 의미가 확인되면 패턴 본문에 자연어로 풀어 쓴다.
4. 시그니처 카운트나 빈도는 보고서에 노출하지 않는다 (format_c_spec.md 의 "빈도 표시 X" 룰).

### phase 분리 시그니처와의 관계

작업 3 본 단계는 **전체 turn 시퀀스의 n-gram**.  
`extract_phase_signatures` 는 phase 별 시그니처를 따로 추출한다 (아래).  
Stage D 는 두 시그니처를 모두 본다:
- 전체 시그니처 → 그룹의 도구 흐름
- phase 분리 시그니처 → 도입부/본격/종료부 특유의 흐름 (도입부 편향 방지)


```python
def extract_signatures(group):
    sequences = [
        [turn.function_group for turn in ep.turns if turn.is_tool_use]
        for ep in group.episodes
    ]
    
    # n-gram (n = 2, 3, 4)
    ngrams = {}
    for n in [2, 3, 4]:
        for seq in sequences:
            for i in range(len(seq) - n + 1):
                ngram = tuple(seq[i:i+n])
                ngrams[ngram] = ngrams.get(ngram, 0) + 1
    
    # 빈도 + 길이 가중치
    scored = [(ngram, count * len(ngram)) for ngram, count in ngrams.items()]
    return sorted(scored, key=lambda x: -x[1])[:5]
```

### phase 분리 시그니처

기본 n-gram 외에 phase 별 시그니처도 추출한다. **종료부 시그니처가 가장 약하게 잡히는 문제** 를 보완하기 위함.

```python
def extract_phase_signatures(group):
    phase_seqs = {"intro": [], "main": [], "verify": []}
    for ep in group.episodes:
        for phase in ("intro", "main", "verify"):
            seq = ep.function_group_sequence_by_phase.get(phase, [])
            if seq:
                phase_seqs[phase].append(seq)

    return {
        phase: extract_ngrams(phase_seqs[phase], ns=[2, 3])[:3]
        for phase in ("intro", "main", "verify")
    }
```

verify phase 의 시그니처가 비어있다면 "이 그룹은 종료부가 짧거나 검증 단계가 없다"는 신호.
보고서 패턴 추출 시 이 차이를 그대로 사용.

### 빈도 ≠ 가치 문제

높은 빈도 시그니처가 좋은 패턴이라는 보장 없음. Stage C는 후보만 뽑고, Stage D의 LLM이 의미 있는 패턴 선별. **책임 분리**.

`outcome_signal` (커밋, 빠른 종료 등) 가중치 도입은 7단계 검증 후 재평가. 지금은 도입 X.

---

## 작업 3.5: turn 단위 미니 패턴 추출 (광역 모드 한정)

기본 시그니처(작업 3) 는 **에피소드 단위**의 도구 시퀀스. 그것만으로는 다음 류 사소한 습관이 안 잡힌다:

- 짧은 도구 조합 의식 (예: `Read → Edit → Read` 재확인)
- verify phase 안 짧은 의식 (예: 작업 끝마다 `git status`)
- 자주 쓰는 사용자 발화 관용구 (예: "ultrathink 별도 컨텍스트로", "한 번 더 검토")
- 도구 인자 패턴 (예: `rg -t java` 항상 언어 필터)

광역 모드(디폴트) 에서 이 류 후보를 추출해 Stage D 가 검토할 수 있게 한다.
`--curated` 모드에서는 이 작업을 건너뛴다 (큐레이션 모드는 5-8 패턴만 추출하므로 미니 패턴 후보가 불필요).

### 추출 3종

```python
@dataclass
class MiniPatternCandidates:
    # (1) 짧은 도구 시퀀스 (n=2, 3): 에피소드 무관, 전체 turn 시퀀스에서 빈도
    tool_microsequences: list[tuple[tuple[str, ...], int]]    # [(("Read","Edit","Read"), 47), ...]

    # (2) 사용자 발화 trigram: user role turn 의 토큰 trigram 빈도
    user_utterance_trigrams: list[tuple[tuple[str, ...], int]]
    # 예: [(("ultrathink","별도","context"), 12), (("한","번","더"), 8), ...]

    # (3) 도구 인자 키 패턴: 같은 도구가 자주 받는 인자 키 조합
    tool_arg_patterns: dict[str, list[tuple[tuple[str, ...], int]]]
    # 예: {"Bash": [(("rg", "-t", "java"), 23), ...], "Edit": [(("old_string", "new_string"), 145)]}
```

### 추출 룰

```python
def extract_mini_patterns(turns):
    # 1. 도구 microsequence
    tool_seq = [t.tool_name for t in turns if t.is_tool_use]
    micro = Counter()
    for n in (2, 3):
        for i in range(len(tool_seq) - n + 1):
            micro[tuple(tool_seq[i:i+n])] += 1

    # 2. 사용자 발화 trigram
    user_text = " ".join(t.content for t in turns if t.role == "user")
    tokens = simple_tokenize(user_text)   # 소문자, 공백/구두점 분리, 한국어는 어절 그대로
    trigrams = Counter(
        tuple(tokens[i:i+3]) for i in range(len(tokens) - 2)
    )

    # 3. 도구 인자 키 패턴 (도구별)
    arg_patterns = defaultdict(Counter)
    for t in turns:
        if not t.is_tool_use: continue
        keys = tuple(sorted(t.tool_input.keys())) if t.tool_input else ()
        arg_patterns[t.tool_name][keys] += 1

    return MiniPatternCandidates(
        tool_microsequences=micro.most_common(50),
        user_utterance_trigrams=trigrams.most_common(50),
        tool_arg_patterns={k: v.most_common(20) for k, v in arg_patterns.items()},
    )
```

상한 (50, 20) 은 컨텍스트 부담을 막기 위한 표시용 상한일 뿐, **빈도 임계값으로 필터링하지 않는다**. 빈도 1회짜리도 후보로 둘 수 있게 — Stage D 가 LLM 판단으로 의미 있는지 결정.

### 빈도 ≠ 가치 (동일 원칙 재확인)

이 단계의 출력도 **후보 표시일 뿐**. Stage D 의 LLM 이 대표 에피소드의 actual turn 시퀀스와 대조해 의미를 확인한 것만 패턴으로 채택. 단순 trigram 빈도만 보고 "자주 쓰는 표현 = 패턴" 으로 단정하지 말 것.

### 약속 1 점검

- **본인 데이터에 맞춰 추출 룰을 좁히는가?** No — 룰은 일반 n-gram, 일반 trigram, 일반 인자 키 카운트. 사용자 데이터와 무관.
- **본인 데이터에 자주 보이는 표현을 보고 yaml 에 박는가?** No — 모든 표현이 사용자 데이터에서 동적으로 유도됨. 박힌 표현 없음.
- **빈도 임계값을 본인 데이터에 맞추는가?** No — 임계값 자체가 없음. 빈도 1회짜리도 후보.

### 약속 5 점검

- 다른 직군에서도 도구 microsequence, 사용자 발화 trigram, 도구 인자 패턴은 동일하게 발현. 직군 무관.
- 데이터가 적은 사용자(짧은 기간)는 대부분 빈도 1회로만 발현 — Stage D 가 의미 있는 것만 골라내면 됨.

### 출력 위치

`aggregated.json` 의 새 필드 `mini_pattern_candidates` 에 추가. Stage D 만 읽는다 (보고서 직접 노출 X).

---

## 작업 4: 메타 정보 집계

```python
def aggregate_meta(episodes):
    return {
        "top_claude_code_features": Counter(
            feat for ep in episodes for feat in ep.claude_code_features
        ).most_common(5),
        
        "top_function_groups": Counter(
            fg for ep in episodes for fg in ep.function_groups_used
        ).most_common(5),
        
        "top_tools": Counter(
            tool for ep in episodes for tool in ep.tools_used
        ).most_common(10),
    }
```

---

## 작업 5: 시계열 데이터 (옵션, 기간 ≥ 2주)

```python
def aggregate_timeseries(episodes, period_days):
    if period_days < 14:
        return None
    
    unit = "week" if period_days < 90 else "month"
    
    buckets = defaultdict(list)
    for ep in episodes:
        key = get_bucket_key(ep.start_time, unit)
        buckets[key].append(ep)
    
    return [
        {
            "label": key,
            "episode_count": len(eps),
            "top_function_groups": Counter(
                fg for ep in eps for fg in ep.function_groups_used
            ).most_common(2),
            "dominant_clusters": Counter(
                ep.situation_cluster for ep in eps
            ).most_common(2),
        }
        for key, eps in sorted(buckets.items())
    ]
```

---

## 출력 스키마

```python
@dataclass
class AggregatedData:
    # 기간 메타
    start_date: date
    end_date: date
    period_days: int
    session_count: int
    episode_count: int
    
    # 그룹별 데이터
    groups: list[GroupMetrics]
    
    # 메타 정보
    top_claude_code_features: list[tuple[str, int]]
    top_function_groups: list[tuple[str, int]]
    top_tools: list[tuple[str, int]]
    
    # 시계열 (옵션)
    timeseries: list[TimeBucket] | None
    
    # turn 단위 미니 패턴 후보 (광역 모드에서만 채워짐)
    mini_pattern_candidates: MiniPatternCandidates | None
```

---

## 셀프 체크

**약속 1**: 산수만 함. 사용자 데이터 보고 알고리즘 바꾸는 거 없음.

**약속 2**: 박힌 거 거의 없음. n-gram 윈도우 크기 `[2, 3, 4]`는 일반 통계 파라미터.
phase·outcome·git 의도 집계는 Stage B 가 부여한 라벨을 단순 합산한 것으로, Stage C 가 룰을 정의하지 않음.

**약속 3**: 사용자가 손댈 거 없음.

**약속 4**: Stage A에서 시크릿 이미 마스킹됨. 회사 시스템명은 사내 공유라 그대로 OK.

---

## 다음 단계

- 6단계: Pipeline + Install 명세 (CLI 인자, 첫 실행 흐름)
- 7단계: 본인 데이터로 PASS/FAIL 검증
- 8단계: 베타 사용자 적용
