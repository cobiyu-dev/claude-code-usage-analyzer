# Stage B Workflow

Claude(자신)가 Stage B (에피소드 분할 + 라벨) 작업을 수행할 때 보는 가이드.

## 입력 / 출력

```
입력:  ~/.cache/cc-analyzer/{period}/turns.parquet
       (Stage A 가 생성. 정규화된 turn 시퀀스 + carve-out + 시크릿 마스킹 완료)

출력:  ~/.cache/cc-analyzer/{period}/episodes.parquet
       (에피소드 단위로 묶이고 라벨 붙은 결과)
```

---

## 작업 절차 (6단계)

```
1. turns.parquet 읽기
2. 휴리스틱 1차 분할
3. 각 에피소드에 자유 텍스트 라벨 + goal 한 줄
4. 양방향 판단 (합칠지/끊을지/유지)
5. 라벨 사후 클러스터링
6. episodes.parquet 저장
```

---

## 단계 1: turns.parquet 읽기

Bash 또는 Python으로 parquet 읽고 turn 시퀀스 확보:

```python
import pandas as pd
turns = pd.read_parquet("~/.cache/cc-analyzer/{period}/turns.parquet")
```

각 row의 필드:
- `turn_id`, `session_id`
- `timestamp`
- `role` (user / assistant)
- `content` (carve-out 적용된 본문)
- `tool_uses` (list of {name, function_group, input, output})
- `claude_code_features` (Plan Mode, /clear 등)

---

## 단계 2: 휴리스틱 1차 분할

`config/split_signals.yaml` 의 규칙으로 1차 분할. 다음 신호가 보이면 끊는다:

```yaml
# config/split_signals.yaml
time_gap_minutes: 20         # 20분 이상 갭이면 끊기
session_change: true          # 세션 변경 시 끊기
clear_command: true           # /clear 시 끊기
topic_keyword_change: true    # 주제 키워드 큰 변화 시 끊기
function_group_disruption:    # 도구 사용 패턴 급변
  window_size: 5
  overlap_threshold: 0.2
transition_phrases:           # 사용자 발화의 전환 표현
  ko: ["이제 다른", "끝났네", "그럼 새로운", "다음으로"]
  en: ["now let's", "done with", "moving on", "next up"]
```

### 신호별 처리

**time_gap_minutes**: 인접 turn 시간 차이 계산. 임계값 초과면 그 사이에서 끊기.

**session_change**: turn.session_id 가 직전과 다르면 끊기.

**clear_command**: turn.content 에 `/clear` 슬래시 보이면 그 turn 직후 끊기.

**topic_keyword_change**: 직전 5턴 vs 다음 5턴의 명사 키워드 (Korean+English 명사) Jaccard 유사도가 0.2 이하면 끊기. 명사 추출은 단순한 토큰화로 충분.

**function_group_disruption**: 직전 5턴의 도구 기능 그룹 set vs 다음 5턴의 도구 기능 그룹 set 의 overlap 비율이 0.2 이하면 끊기.
- 예: 직전 5턴이 `{log_search, code_search}`, 다음 5턴이 `{file_edit, shell_exec}` → overlap 0 → 끊기
- 디버깅에서 코딩으로 전환된 신호

**transition_phrases**: turn.content (role=user 만) 에 전환 표현 등장 시 그 turn 직후 끊기.

### 결과

각 turn 에 `episode_id` 부여. 같은 episode_id 끼리 묶음.

---

## 단계 3: 각 에피소드에 자유 텍스트 라벨 + goal

휴리스틱으로 끊은 각 에피소드에 대해:

### 라벨 생성

각 에피소드의 첫 2-3 turn (user prompt + 첫 응답) 을 보고 자유 텍스트로 한 문장 라벨 생성.

**중요**: enum 강제 X. 14개 카테고리 같은 거 박지 말 것.

```
좋은 라벨 예시:
- "production error investigation using grafana logs"
- "API endpoint refactor for cleaner naming"
- "exploring new MCP plugin architecture"
- "drafting team handover documentation"

나쁜 라벨 예시:
- "prod_incident"  ← enum 처럼 보임. 자유 텍스트 X
- "refactoring"    ← 너무 단어. 한 문장으로
- "WMS 인벤토리 락 문제"  ← 회사 도메인 들어감 (괜찮긴 한데 일반화 표현 선호)
```

### Goal 생성

라벨과는 별개로 "이 에피소드의 목적은?" 한 줄로 답하기:

```
예시:
- 라벨: "production error investigation using grafana logs"
- goal: "What caused the 500 errors in the order service"

- 라벨: "API endpoint refactor for cleaner naming"
- goal: "Rename /api/v1/getUserData to /api/v1/users"
```

### Claude Code 기능 추출

각 에피소드에서 사용된 Claude Code 기능 검출:
- Plan Mode: turn 에 `subtype: "ExitPlanMode"` 도구 사용 있나
- /clear: 세션 시작에 /clear 있나
- Subagent: `subtype: "Task"` 도구 있나
- 슬래시 커맨드: user prompt 가 `/` 로 시작하나

결과를 `claude_code_features` 필드에 list 로.

---

## 단계 4: 양방향 판단 (합칠지/끊을지/유지)

휴리스틱 1차 분할 결과를 점검. 각 에피소드 경계에서 세 가지 판단:

```
"이 에피소드와 직전 에피소드는 한 작업이야? (합치자)"
"이 에피소드 안에 두 개 작업이 섞여있어? (끊자)"
"그대로 한 작업이야? (유지)"
```

### 판단 기준

**합칠 신호**:
- 두 에피소드의 라벨이 의미적으로 같음
- 두 에피소드의 도구 기능 그룹이 거의 같음
- 시간 갭이 작음 (휴리스틱이 잘못 끊은 케이스)

**끊을 신호**:
- 한 에피소드 안에서 라벨이 두 가지로 명확히 나뉨
- 도구 사용 패턴이 에피소드 중간에 급변
- 사용자가 중간에 "이제 다른 거" 같은 표현 사용

**유지**: 위 신호가 명확하지 않으면 그대로.

### 결과 적용

판단 결과로 episode_id 재할당:
- "merge_with_prev" → 직전 에피소드의 id 로 통합
- "split_into_N" → 새 id 부여하면서 분할
- "keep" → 그대로

---

## 단계 5: 라벨 사후 클러스터링

각 에피소드의 라벨이 자유 텍스트라 같은 의미인데 표현이 다른 경우 많음.
같은 의미끼리 묶어서 `situation_cluster` 부여.

### 절차

**(5-1) 전체 에피소드의 라벨 수집**

```python
all_labels = [ep.label for ep in episodes]
# 예시:
# ["production error investigation",
#  "prod incident triage",
#  "live error debugging",
#  "API endpoint refactor",
#  "function extraction",
#  ...]
```

**(5-2) Claude(자신)가 한 번에 묶기**

라벨이 50-100개 정도면 한 번에 묶을 수 있음. 묶기 기준:
- 의미적으로 동일한 작업 종류면 같은 그룹
- 그룹마다 대표 이름 부여 (영문 짧은 명사구)

```
그룹 1: "production incident"
  - "production error investigation"
  - "prod incident triage"
  - "live error debugging"

그룹 2: "refactoring"
  - "API endpoint refactor"
  - "function extraction"
  - "naming cleanup"

그룹 3: "exploration"
  - "exploring new MCP plugin architecture"
  - "investigating subagent workflow"
```

**(5-3) 각 에피소드에 situation_cluster 부여**

```python
for ep in episodes:
    ep.situation_cluster = lookup_cluster(ep.label)
```

### 그룹 명명 규칙

- 영문 명사구 (소문자, 공백 또는 underscore)
- 추상적이되 명확하게
- 회사 도메인 명사 X (예: "WMS bug fix" 같은 거 X. "bug fix" OK)
- 사용자 행동 동사 또는 작업 종류

```
좋음: "production incident", "refactoring", "documentation",
      "exploration", "code review iteration"

나쁨: "various tasks" (모호), "the WMS thing" (도메인),
      "stuff" (의미 없음)
```

---

## 단계 6: episodes.parquet 저장

각 에피소드를 다음 스키마로 저장:

```python
@dataclass
class Episode:
    episode_id: str
    session_ids: list[str]
    turn_ids: list[str]
    
    start_time: datetime
    end_time: datetime
    
    label: str                       # 자유 텍스트 라벨
    situation_cluster: str           # 사후 클러스터링 그룹명
    goal: str                        # 한 줄 요약
    
    claude_code_features: list[str]  # Plan Mode, /clear, Subagent 등
    
    # 통계
    turn_count: int
    function_groups_used: list[str]
    tools_used: list[str]
```

저장:
```python
import pandas as pd
pd.DataFrame([asdict(ep) for ep in episodes]) \
  .to_parquet("~/.cache/cc-analyzer/{period}/episodes.parquet")
```

---

## 셀프 체크 (이 단계 끝났을 때)

**약속 1 (튜닝 X)**:
- 본인 데이터 보고 휴리스틱 임계값 (20분, 0.2 등) 바꾼 적 있나? 없음 → OK
- 본인 데이터 패턴 잘 잡게 라벨 가이드 조정한 적 있나? 없음 → OK

**약속 2 (코드에 박지 마)**:
- 카테고리 enum 강제 X (자유 텍스트) → OK
- 휴리스틱 임계값은 config/split_signals.yaml 에 분리 → OK
- 전환 표현 (transition_phrases) yaml 분리 → OK

**약속 3 (다른 사람 검증 강제 X)**:
- Stage B 결과를 사용자에게 보여주고 라벨 확인 받지 않음 → OK
- (사용자는 최종 보고서만 보고, 중간 산출물은 신경 안 씀)

**약속 4 (정보 안 새기)**:
- 라벨에 회사 도메인 명사 들어가도 OK (사내 공유 전용)
- 시크릿은 Stage A 에서 이미 마스킹됨

**약속 5 (일반화 강건성)**:
- 자유 텍스트 라벨이라 어느 직군이든 자기 작업에 맞는 라벨 생성 가능 → OK
- 휴리스틱 신호들 (시간 갭, 세션 변경, 도구 패턴 단절) 사용자 무관 → OK
