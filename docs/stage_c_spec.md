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
    
    representative_episodes: list   # 그룹 내 대표 에피소드 ID 3-5개
```

### 대표 에피소드 선정

```python
def score_representativeness(ep, group):
    turn_score = 1 - abs(ep.turn_count - group.avg_turns) / group.avg_turns
    func_overlap = jaccard(ep.function_groups, group.top_function_groups)
    return (turn_score + func_overlap) / 2
```

상위 3-5개 선정. Stage D의 LLM이 패턴 추출 시 참고함.

---

## 작업 3: 시그니처 도구 시퀀스 추출

각 그룹에서 자주 나타나는 도구 사용 순서 (n-gram).

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

### 빈도 ≠ 가치 문제

높은 빈도 시그니처가 좋은 패턴이라는 보장 없음. Stage C는 후보만 뽑고, Stage D의 LLM이 의미 있는 패턴 선별. **책임 분리**.

`outcome_signal` (커밋, 빠른 종료 등) 가중치 도입은 7단계 검증 후 재평가. 지금은 도입 X.

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
```

---

## 셀프 체크

**약속 1**: 산수만 함. 사용자 데이터 보고 알고리즘 바꾸는 거 없음.

**약속 2**: 박힌 거 거의 없음. n-gram 윈도우 크기 `[2, 3, 4]`는 일반 통계 파라미터.

**약속 3**: 사용자가 손댈 거 없음.

**약속 4**: Stage A에서 시크릿 이미 마스킹됨. 회사 시스템명은 사내 공유라 그대로 OK.

---

## 다음 단계

- 6단계: Pipeline + Install 명세 (CLI 인자, 첫 실행 흐름)
- 7단계: 본인 데이터로 PASS/FAIL 검증
- 8단계: 베타 사용자 적용
