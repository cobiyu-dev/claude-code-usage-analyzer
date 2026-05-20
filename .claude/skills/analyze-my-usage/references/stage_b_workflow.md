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

## 작업 절차 (7단계)

```
1. turns.parquet 읽기
2. 휴리스틱 1차 분할
3. 각 에피소드에 자유 텍스트 라벨 + goal 한 줄
3.5. 에피소드 내부 구조 라벨링 (phase / outcome / git 의도)
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

## 단계 3.5: 에피소드 내부 구조 라벨링

자유 텍스트 라벨은 "이게 어떤 작업이었나" 만 답한다. 이 단계는 "그 작업이 **어떻게 흘러갔나**" 를 짧게 라벨링한다.
LLM 판단 없이 휴리스틱 + yaml 매칭만 사용. (튜닝 여지 없음)

### (3.5-0) episode_kind 판정

phase 라벨이 의미 있는 에피소드와 그렇지 않은 에피소드를 구분.

```python
def classify_episode_kind(ep):
    has_edit = any("file_edit" in t.function_groups for t in ep.turns)
    if has_edit:
        return "with_changes"
    has_investigation_tools = any(
        fg in ("log_search", "db_query", "code_search",
               "metric_query", "trace_view", "file_read")
        for t in ep.turns for fg in t.function_groups
    )
    if has_investigation_tools:
        return "investigation_only"
    return "tooling_only"

ep.episode_kind = classify_episode_kind(ep)
```

`investigation_only` 와 `tooling_only` 는 main/verify phase 가 빈 리스트로 남는다 — 정상.

### (3.5-1) phase 분할

각 에피소드의 turn 시퀀스를 시간순으로 보고 세 phase 로 나눈다:

```
intro       : 사용자 첫 발화 ~ 첫 번째 file_edit/execution_like shell_exec 직전
main        : 첫 file_edit ~ 마지막 file_edit
verify      : 마지막 file_edit 다음 ~ 에피소드 끝
```

판정 의사코드:
```python
edit_indices = [i for i, t in enumerate(ep.turns)
                if "file_edit" in t.function_groups
                or t.is_execution_like_shell]
if not edit_indices:
    # 순수 조사/리뷰 에피소드. main/verify 는 빈 리스트.
    ep.phase_boundaries = {"intro_end": len(ep.turns), "verify_start": len(ep.turns)}
else:
    ep.phase_boundaries = {
        "intro_end": edit_indices[0],
        "verify_start": edit_indices[-1] + 1,
    }
```

verify 가 비어있는 것 자체도 신호다 ("이 그룹은 검증 단계 없이 끝남"). 비어있다고 phase 를 임의로 재할당하지 말 것.

### (3.5-2) outcome 신호 부여

`config/outcome_signals.yaml` 의 룰을 순서대로 적용. 한 에피소드에 복수 outcome 가능.

예시:
```
에피소드 A 의 verify phase 안에:
  - turn 18: Bash "git add . && git commit -m '...'"     → committed
  - turn 19: Bash "git push origin feat/x"                → pushed
  - turn 20: tool=mcp__github__create_pull_request        → pr_opened
  → outcomes = ["committed", "pushed", "pr_opened"]

에피소드 B 의 verify phase 안에:
  - turn 24: mysql_query("select * from orders where ...")  → verified_by_data
  - turn 25: Bash "./gradlew bootRun" (execution_like)        → verified_by_run
  → outcomes = ["verified_by_data", "verified_by_run"]

에피소드 C:
  - main phase 마지막 turn 이 Agent 결과 요약                 → delegated_and_reported
  - verify phase 비어있음
  → outcomes = ["delegated_and_reported"]

에피소드 D:
  - verify phase 비어있고 마지막 turn 에 에러 + 사용자 미응답
  → outcomes = ["abandoned_or_paused"]
```

**중요**: outcome 판정은 phase 정보를 보고 한다. 도입부에서 일어난 `git commit`(예: 작업 시작 전 정리 commit)을 `committed` outcome 으로 잘못 잡지 말 것. yaml 의 `phase: verify` 제약을 반드시 적용.

### (3.5-3) git 의도 태그

각 git Bash 호출을 `config/git_intent_patterns.yaml` 의 분류에 맞춰 태깅.
에피소드 레벨에서는 set 으로 집계:

```
에피소드 E:
  turn 5:  Bash "git log -- src/inventory/Reservation.java"  → diagnostic
  turn 7:  Bash "git blame src/inventory/Reservation.java"   → diagnostic
  turn 9:  Bash "git diff HEAD~5 -- src/inventory/"          → diagnostic
  → git_intents_used = {"diagnostic"}

에피소드 F:
  turn 22: Bash "git add . && git commit"                    → output
  turn 23: Bash "git push"                                   → output
  → git_intents_used = {"output"}

에피소드 G:
  turn 3:  Bash "git checkout feat/x"                        → transition
  turn 18: Bash "git commit"                                 → output
  turn 19: Bash "git push"                                   → output
  → git_intents_used = {"transition", "output"}
```

`diagnostic` 이 들어있다는 것 자체가 시간축 진단을 했다는 강한 신호. Stage D 에서 "회귀 시점 추적" 패턴의 1차 후보가 된다.

### (3.5-4) phase 별 기능 그룹 분포 캐시

Stage C 가 다시 계산하기 전에 여기서 한 번 만들어 저장 (Stage C 부담 감소):

```python
ep.function_groups_by_phase = {
    "intro":  Counter(fg for t in ep.turns[:ep.phase_boundaries["intro_end"]]
                          for fg in t.function_groups),
    "main":   Counter(fg for t in ep.turns[ep.phase_boundaries["intro_end"]
                                           : ep.phase_boundaries["verify_start"]]
                          for fg in t.function_groups),
    "verify": Counter(fg for t in ep.turns[ep.phase_boundaries["verify_start"]:]
                          for fg in t.function_groups),
}
```

### 셀프 체크 (이 단계만)

- LLM 호출 X? → OK (모두 휴리스틱·yaml 매칭)
- 본인 데이터 보고 임계값 만들지 않았나? → outcome/git 의도 룰은 도구 호출과 정규식 매칭. 임계값 없음.
- 다른 직군에서 무너지나? → git 없는 직군은 git_intents_used 가 빈 set. outcome 도 `committed/pushed/pr_opened` 가 비고 `verified_by_run/_by_data/delegated_and_reported/abandoned_or_paused` 만 발현. 형식은 그대로 유지.

---

## 단계 4: 양방향 판단 (합칠지/끊을지/유지)

휴리스틱 1차 분할 결과를 점검. 각 에피소드 경계에서 세 가지 판단:

```
"이 에피소드와 직전 에피소드는 한 작업이야? (합치자)"
"이 에피소드 안에 두 개 작업이 섞여있어? (끊자)"
"그대로 한 작업이야? (유지)"
```

### 판단 기준

LLM 판단을 최종 결정자로 유지하되, 다음 결정론적 보조 신호를 먼저 계산해 함께 제시한다. **모호한 표현으로만 판단하지 말 것** — 보조 신호가 있으면 같이 보고, 충돌하면 그 이유를 한 줄 메모.

**합칠 신호** — 다음 중 2개 이상이면 강한 합칠 후보:

| 신호 | 측정 | 임계 |
|---|---|---|
| 라벨 토큰 jaccard | 두 에피소드의 자유 텍스트 라벨을 토큰화(소문자, 공백/언더스코어 분할)해 Jaccard | ≥ 0.5 |
| goal 토큰 jaccard | goal 한 줄을 토큰화해 Jaccard | ≥ 0.5 |
| 기능 그룹 overlap | function_groups_used set 의 overlap 비율 (작은 쪽 기준) | ≥ 0.7 |
| 시간 갭 | prev.end_time ↔ curr.start_time 차이 | ≤ 5분 |
| outcome 연속성 | prev.outcomes 가 비어있고 curr 가 verify-only 인 경우 (이어진 검증) | true |

**끊을 신호** — 다음 중 2개 이상이면 강한 분할 후보:

| 신호 | 측정 | 임계 |
|---|---|---|
| 라벨 토큰 jaccard | 같은 방식 | ≤ 0.2 |
| 기능 그룹 overlap (앞/뒤 윈도우) | turn 시퀀스를 절반으로 갈라 각 절반의 function_groups set overlap | ≤ 0.2 |
| outcome 발현 위치 | 에피소드 중간에 `committed`/`pushed`/`pr_opened` 가 보이고 그 후 새 작업이 다시 시작 | true |
| 사용자 발화에 전환 표현 | split_signals.yaml 의 transition_phrases 매칭 | true |

**유지**: 합칠 신호와 끊을 신호가 둘 다 약하거나 충돌하면 그대로. 망설여지면 **건드리지 않는 게 디폴트** (휴리스틱 1차 결과 신뢰).

### LLM 호출 형태

각 경계마다 위 보조 신호를 표로 만들어 LLM 에게 함께 전달:

```
이 두 에피소드를 합칠지/끊을지/유지할지 결정해주세요.

[보조 신호]
- 라벨 jaccard:        0.67   (prev: "production error investigation", curr: "prod incident root cause")
- goal jaccard:        0.50
- 기능 그룹 overlap:   0.83   (prev: {log_search, code_search}, curr: {log_search, code_search, file_read})
- 시간 갭:             3분
- 종결 outcome:        prev 없음, curr 검증중

[판단]
   merge_with_prev / split_into_N / keep_as_is
```

이렇게 하면 LLM 답이 보조 신호와 일치하는지 확인 가능. 일치하지 않으면 LLM 답 그대로 채택하되 디버그 로그에 기록.

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

라벨이 ~100개 이하면 한 번에 묶을 수 있음. 그 이상이면 분할 전략(아래 5-2-bis) 적용.

묶기 기준:
- 의미적으로 동일한 작업 종류면 같은 그룹
- 그룹마다 대표 이름 부여 (영문 짧은 명사구)

**(5-2-bis) 라벨이 많아 컨텍스트가 빠듯할 때 분할 전략**

라벨 수를 먼저 추정한다. 라벨 1개당 평균 약 20 토큰 가정 (자유 텍스트 한 문장). 라벨이 200개 → 4k 토큰만으로도 OK. 1000개 → 20k 토큰. 단순 라벨 묶기는 거의 안 막힌다.

진짜 막히는 경우는 **각 라벨의 근거 turn 까지 같이 보고 싶을 때**. 이 경우 다음 순서:

1. **claim/근거 분리**: 1차 묶기는 라벨 텍스트만 보고 진행. 근거 turn 은 추후 검증용으로만 분리 보관.
2. **청크 분할**: 라벨이 너무 많으면 카테고리 hint(예: 라벨에 "error"/"refactor"/"explore" 키워드 포함 여부)로 1차 prebucket → 각 bucket 안에서 의미 묶기.
3. **후속 머지**: bucket 간 동일 의미 그룹이 있으면 한 번 더 합치는 round. (예: bucket A 의 "production incident" 와 bucket B 의 "live error triage" 가 같은 그룹이면 머지)
4. **막힐 때 알림**: 위 절차로도 안 되면 사용자에게 "기간이 너무 길어 클러스터링이 어렵습니다. 기간을 좁혀 다시 시도해주세요" 안내. **임의로 잘라 결과 내지 말 것** (약속 1 — 가정 점검).

### 디폴트 분기 의사코드

```python
def cluster_labels(labels, turns_by_label):
    if len(labels) <= 150:
        return claude_cluster_in_one_pass(labels)

    # 1차: 라벨 텍스트만으로 카테고리 hint prebucket
    buckets = prebucket_by_keyword_hints(labels)

    # 2차: bucket 안에서 의미 묶기
    intra_groups = []
    for bucket in buckets:
        if len(bucket) > 150:
            # 안전장치 — 한 bucket 이 너무 크면 사용자에게 알림
            raise ContextOverflow(
                f"카테고리 hint 적용 후에도 {len(bucket)}개 라벨이 한 bucket 에 남음."
                f" 기간을 좁혀주세요."
            )
        intra_groups.append(claude_cluster_in_one_pass(bucket))

    # 3차: bucket 간 동일 의미 그룹 머지
    return merge_cross_bucket_groups(intra_groups)
```

`prebucket_by_keyword_hints` 의 hint 는 라벨에 자주 나타나는 영문 명사 토큰 빈도로 동적 생성 — yaml 박을 필요 없음 (라벨 분포에서 유도).

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
    
    # 내부 구조 라벨 (단계 3.5)
    episode_kind: str                # "with_changes" | "investigation_only" | "tooling_only"
    phase_boundaries: dict           # {"intro_end": int, "verify_start": int}
    outcomes: list[str]              # ["committed", "verified_by_run", ...]
    git_intents_used: list[str]      # ["diagnostic", "output", ...]
    function_groups_by_phase: dict   # {"intro": {...}, "main": {...}, "verify": {...}}
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
