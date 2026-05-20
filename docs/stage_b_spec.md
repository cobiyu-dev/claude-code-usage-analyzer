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

## 작업 3: 에피소드 내부 구조 라벨링 (phase / outcome / git 의도)

### 동기

기존 라벨(`label`, `goal`, `situation_cluster`)은 **에피소드의 정체성**만 잡음.
보고서 검증 결과 패턴이 대부분 **에피소드 도입부**에 편향됨:
- "코드 보기 전에 로그부터 끌어옴" (도입)
- "본격 편집 전에 정상 동작 정리" (도입)
- ...

빠진 것:
- **종료부 행동**: "작업 마치고 alpha DB 로 결과 검증", "위임 후 보고만 받음"
- **진단 시간축**: "현상만 보지 않고 git log/bisect 로 언제부터 깨졌는지 추적"
- **종결 신호**: 같은 commit 으로 끝났는지, 위임으로 끝났는지, 미해결 중단인지

이건 분할 임계값을 튜닝해 해결할 일이 아니라 **에피소드 내부에 구조 라벨이 없어서** 생긴 누락이다.
Stage B 가 자유 텍스트 라벨 옆에 다음 세 가지 구조 라벨을 추가로 붙인다.

### 라벨 3종

**(1) phase 분할** — 에피소드를 시간순으로 3 단계로 나눔:

| phase | 정의 |
|---|---|
| `intro` | 사용자 첫 발화부터 본격 변경(file_edit/shell_exec_modify)이 시작되기 직전까지 |
| `main` | 본격 변경이 일어나는 구간 |
| `verify` | 마지막 변경 이후의 turn 들. 검증/마무리/위임 결과 보고가 여기 들어감 |

판정은 휴리스틱 1패스로:
```
intro_end_idx  = 첫 번째 file_edit / shell_exec(빌드·테스트·실행) turn 의 직전
verify_start_idx = 마지막 file_edit turn 다음
intro = turns[:intro_end_idx]
main  = turns[intro_end_idx:verify_start_idx]
verify = turns[verify_start_idx:]
```

edit 가 없는 에피소드(순수 조사/리뷰)는 `intro`만 가짐 (`main`, `verify` 는 빈 리스트).
verify 가 비어있어도 OK — "검증 단계가 없었다" 자체가 신호다.

### 에피소드 유형 분류 (phase 라벨의 적용 가능성)

phase/outcome 라벨은 모든 에피소드에 동일하게 적용되지 않는다. 에피소드를 다음 유형으로 나누고, Stage C/D 가 유형별로 다르게 다룬다 (에피소드를 버리지 말 것 — 자체로 신호다).

| 유형 | 판정 | phase 라벨 유효성 | outcome 적용 |
|---|---|---|---|
| `with_changes` | file_edit ≥ 1 | intro/main/verify 모두 의미 있음 | 전체 outcome 적용 |
| `investigation_only` | file_edit = 0, function_groups 에 log_search/db_query/code_search 등 조사 도구 위주 | intro 만 의미 | `verified_by_data` / `delegated_and_reported` 등은 적용 X. 다만 `diagnostic` git 의도는 잡힘 |
| `tooling_only` | file_edit = 0, 도구 호출만 (예: 슬래시 커맨드 시도, 환경 확인) | intro 만 | outcome 적용 X |

`episode_kind` 필드를 출력 스키마에 추가해 명시. 보고서에서는 유형별로 패턴 후보를 다르게 본다 (예: `investigation_only` 만 모인 그룹은 "조사 에피소드의 메서드러지" 로 따로 다룸).

**중요**: `investigation_only` 가 많다고 "분석 실패"로 보지 말 것. 약속 1 적용 — 본인 데이터에선 with_changes 비율이 높지만, 다른 직군(PM/QA/오퍼레이션)은 investigation_only 비율이 더 높을 수 있다.

**(2) outcome 신호** — 에피소드가 어떻게 끝났는지:

`config/outcome_signals.yaml` 의 정규식·휴리스틱으로 판정. 다음 중 하나 이상이 set 으로 부여됨:

| outcome | 판정 신호 |
|---|---|
| `committed` | verify phase 안에 `git commit` Bash 호출 존재 |
| `pushed` | verify phase 안에 `git push` Bash 호출 존재 |
| `pr_opened` | verify phase 안에 `gh pr create` 또는 GitHub MCP `create_pull_request` |
| `verified_by_data` | verify phase 안에 db_query / log_search / metric_query 호출 존재 |
| `verified_by_run` | verify phase 안에 execution_like shell_exec (앱 실행/테스트 실행) 존재 |
| `delegated_and_reported` | main 또는 verify phase 마지막 turn 이 agent 도구(Subagent) 결과 요약 |
| `abandoned_or_paused` | verify phase 비어있고 마지막 turn 이 미완 상태(에러 출력, 사용자 미응답) |

복수 부여 가능. 한 에피소드가 `{verified_by_run, verified_by_data, committed, pushed, pr_opened}` 다 가질 수 있음.

**(3) git 의도 시그니처** — 에피소드 안에서 git 명령이 어떤 의도로 쓰였는지:

`config/git_intent_patterns.yaml` 의 분류대로 각 git Bash 호출에 의도 태그 부여:

| intent | 해당 명령 |
|---|---|
| `diagnostic` | `git log`, `git blame`, `git bisect`, `git diff` (커밋 비교용), `git show` |
| `output` | `git add`, `git commit`, `git push`, `git tag` |
| `transition` | `git checkout`, `git switch`, `git merge`, `git rebase`, `git stash`, `git pull` |

에피소드 레벨에서는 `git_intents_used: set[str]` 로 집계.
**`diagnostic` 가 들어있다는 것 자체가** 사용자가 시간축으로 회귀 시점을 추적했다는 신호 → 패턴 추출에서 별도 단위로 작동.

### 누가 라벨링하는가

- phase 분할: **휴리스틱** (Stage B 의 Python/Claude 어느 쪽에서도 OK, LLM 호출 X)
- outcome 신호: **휴리스틱** (yaml 의 정규식·도구 호출 매칭)
- git 의도: **휴리스틱** (yaml lookup)

→ LLM 판단 없음. 약속 1 충돌 없음 (튜닝 여지 없는 단순 매칭).

### 셀프 체크

- 약속 1: 임계값 없음. 본인 데이터 보고 룰 안 만들어짐. yaml 의 정규식은 사용자 무관 (git 명령 / Bash 검출).
- 약속 2: 모든 분류 룰을 `config/outcome_signals.yaml`, `config/git_intent_patterns.yaml` 에 분리.
- 약속 3: 사용자가 라벨링하지 않음.
- 약속 5: 다른 직군은 `committed/pushed/pr_opened` 가 비어있고 `verified_by_run/verified_by_data` 만 발현됨 — 무너지지 않음. git 의도 분류는 git 을 안 쓰는 직군이면 단순히 빈 set.

---

## 작업 4: 본인 작업 방식 박힘 제거

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
    
    # 내부 구조 라벨 (작업 3)
    episode_kind: str                # "with_changes" | "investigation_only" | "tooling_only"
    phase_boundaries: dict           # {"intro_end": idx, "verify_start": idx}
    outcomes: list[str]              # ["committed", "verified_by_run", ...]  복수 가능
    git_intents_used: list[str]      # ["diagnostic", "output"] subset
    
    # phase 별 기능 그룹 분포 (Stage C 가 한 번 더 계산해도 되지만 여기서 캐시)
    function_groups_by_phase: dict   # {"intro": {...}, "main": {...}, "verify": {...}}
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
