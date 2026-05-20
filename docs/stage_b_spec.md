# Stage B 설계 명세

## 역할

```
입력:  turns.parquet (Stage A 출력)

처리:  1. turn 시퀀스를 에피소드 단위로 분할
       2. 각 에피소드에 자유 텍스트 라벨 + 한 줄 goal
       3. 라벨 사후 클러스터링 (비슷한 의미끼리 묶기)

출력:  episodes.parquet (Stage C의 입력)
```

**에피소드 정의**: 하나의 의도/목적을 가진 작업 단위. 
한 세션 안에 여러 에피소드, 한 에피소드가 여러 세션에 걸칠 수 있음.

---

## 작업 1: 카테고리 enum 폐기 → 자유 텍스트 라벨

### 기존 방식의 문제

검증 2에서 14개 카테고리 enum(`prod_incident`, `refactoring`, `bug_fix` 등)을 
코드에 박았음. 두 가지 문제:

1. 14개는 본인 작업 보고 만든 것 — 다른 사람에게 안 맞음
2. 일치율 73% — 14개로 다 안 잡힘

### 새 방식

LLM(Haiku)에게 enum 강제 대신 자유 텍스트로 답하게 함.

```python
# 기존
prompt = "이 에피소드는 다음 중 어느 카테고리야? 
         [prod_incident, refactoring, ...]"
answer: "prod_incident"

# 신규
prompt = "이 에피소드가 어떤 상황이야? 한 문장으로 답해줘"
answer: "production error investigation using grafana logs"
```

### 후속 처리: 사후 클러스터링

자유 텍스트면 같은 의미인데 표현이 다른 라벨이 많이 나옴:
- "production error investigation"
- "prod incident triage"
- "live error debugging"

분석 들어가기 전에 LLM에게 한 번 더 부탁:

```
"여기 라벨 50개가 있어. 비슷한 의미끼리 묶어줘"

→ LLM 답:
그룹 1: production incident
  - "production error investigation"
  - "prod incident triage"
  - "live error debugging"

그룹 2: refactoring
  - "API endpoint refactor"
  - "function extraction"
```

비용: 라벨 50-100개 묶기 ≈ Haiku $0.01 미만

---

## 작업 2: under-split (덜 분할) 문제 해결

### 기존 방식의 문제

휴리스틱 분할(시간 갭, /clear, 세션 변경)은 **과분할만 잡고 덜분할 못 잡음**.

같은 세션 안에 여러 작업이 연속해서 흐르면 한 에피소드로 묶임:
```
[09:00] WMS 에러 디버깅
[09:30] 에러 해결됨
[09:35] "이제 새 기능 작업하자"
[10:00] 새 기능 코딩
   ↑ 두 개의 다른 작업인데 한 에피소드로 묶임
```

LLM에게 "합칠까?"만 물어보는 구조라 분할 기회 없음.

### 해결: 방향 A + 방향 B 혼합

**방향 A: LLM 양방향 판단**

기존 "합칠까?" 질문에 "끊을까?"도 추가. 세 가지 다 묻기:

```python
for ep in episodes:
    decision = haiku.judge(prev=episodes[i-1], curr=ep, next=episodes[i+1])
    # 결과: "merge_with_prev" / "split_into_N" / "keep_as_is"
```

**방향 B: 자동 분할 신호 추가**

휴리스틱에 새 신호 두 개 추가:

```python
heuristic_signals = [
    # 기존
    "time_gap > 20min",
    "session_change",
    "/clear command",
    "topic_keyword_change",
    
    # 신규
    "function_group_disruption",  # 도구 기능 그룹 시퀀스 단절
    "transition_phrase",           # 전환 표현 검출
]
```

- **function_group_disruption**: 도구 사용 패턴 급변
  - 예: log_search + code_search 위주 → 갑자기 file_edit + shell_exec
  - 디버깅에서 코딩으로 전환된 신호
  - 사용자 무관 (어떤 사람이든 도구 패턴 변화는 작업 전환 시사)

- **transition_phrase**: 사용자 발화에 전환 표현
  - "이제 다른 거 하자", "끝났네", "그럼 새로운 작업"
  - 전환 표현 yaml로 분리 (한국어/영어 확장 가능)

### 최종 알고리즘

```python
def split_into_episodes(turns):
    # 1차: 휴리스틱 분할 (기존 + 신규 신호)
    episodes = heuristic_split(turns, signals=ALL_SIGNALS)
    
    # 2차: LLM 양방향 판단
    decisions = []
    for i, ep in enumerate(episodes):
        decision = haiku.judge_episode_boundary(
            prev=episodes[i-1] if i > 0 else None,
            curr=ep,
            next=episodes[i+1] if i < len(episodes)-1 else None,
        )
        decisions.append(decision)
    
    # 3차: 결정 적용 (병합/분할/유지)
    episodes = apply_decisions(episodes, decisions)
    return episodes
```

### 임계값/키워드는 yaml 분리

```yaml
# config/split_signals.yaml
time_gap_minutes: 20
transition_phrases:
  ko:
    - "이제 다른"
    - "끝났네"
    - "그럼 새로운"
    - "다음으로"
  en:
    - "now let's"
    - "done with"
    - "moving on"
    - "next up"

function_group_disruption:
  window_size: 5     # 직전 5턴 도구 vs 다음 5턴 도구
  overlap_threshold: 0.2  # 겹치는 기능 그룹 비율 임계값
```

---

## 작업 3: 본인 작업 방식 박힘 제거

### 박힘 1: ultrathink/megathink 키워드 검출

**처리**: 빼기.

- 본인이 자주 쓰는 키워드. 다른 사람은 안 씀
- 패턴 분석에 필수 아님 — 빠져도 보고서 품질 영향 없음
- 나중에 필요하면 일반화된 "thinking 강도 신호"로 재도입 검토 (YAGNI)

### 박힘 2: Plan Mode 진입 비율 분석

**처리**: 일반화.

기존:
```
Plan Mode 진입 비율 35%
```

신규:
```
자주 쓰는 Claude Code 기능 top 5
  1. Plan Mode (45% 작업에서 사용)
  2. /clear (28%)
  3. Subagent 호출 (15%)
  4. ultrathink 키워드 (10%)
  5. Plan Mode in subagent (5%)
```

검출 방법 (Claude Code 표준이라 사용자 무관):
- Plan Mode: `subtype: "ExitPlanMode"` 도구 사용
- /clear: 세션 메타
- Subagent: `subtype: "Task"` 도구
- 슬래시 커맨드: user prompt 시작 문자

### 박힘 3: 본인 MCP 우선 처리

이미 Stage A 작업 1에서 해결됨 (도구→기능 그룹 매핑). 확인만 함.

---

## 출력 스키마

```python
@dataclass
class Episode:
    episode_id: str
    session_ids: list[str]       # 한 에피소드가 여러 세션 걸칠 수 있음
    turn_ids: list[str]
    
    start_time: datetime
    end_time: datetime
    
    situation_raw: str           # LLM 자유 텍스트 라벨
    situation_cluster: str       # 사후 클러스터링 결과 그룹명
    goal: str                    # 한 줄 요약
    
    claude_code_features: list[str]  # 사용된 Claude Code 기능 (Plan Mode 등)
    
    # 메타
    turn_count: int
    function_groups_used: list[str]  # 사용된 기능 그룹 (log_search 등)
```

---

## 셀프 체크 통과 사항

**약속 1 (튜닝 X)**: 자유 텍스트 라벨/클러스터링은 알고리즘 자체가 사용자 무관. 
본인 데이터에서 룰 박는 거 없음.

**약속 2 (코드에 박지 마)**: 카테고리 enum 폐기. 임계값/키워드는 yaml 분리.

**약속 3 (다른 사람 검증 강제 X)**: 자유 텍스트 라벨이라 사용자가 손 라벨링 안 해도 됨.

**약속 4 (정보 안 새기)**: 클러스터링 결과의 그룹명은 추상화된 일반 표현 
("production incident" 같은). 회사 내부 시스템명 안 들어감.

---

## 다음 단계 (4단계: Format C 명세 문서화)

- 보고서 출력 형식 명세
- 도메인 명사 0% 자동 검증
- 도구명 + 인라인 기능 설명 룰
- 사내용 vs 사외용 마스킹 분기
