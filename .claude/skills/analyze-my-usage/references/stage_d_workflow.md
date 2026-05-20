# Stage D Workflow

Claude(자신)가 Stage D (패턴 추출 + 보고서 생성) 작업을 수행할 때 보는 가이드.

## 입력 / 출력

```
입력:  ~/.cache/cc-analyzer/{period}/episodes.parquet    (Stage B 출력)
       ~/.cache/cc-analyzer/{period}/aggregated.json     (Stage C 출력)
       ~/.config/cc-analyzer/config.yaml                  (사용자 설정)

출력:  ~/.cache/cc-analyzer/{period}/report_draft.md     (임시, 검증 전)
       → 검증 통과 후 {config.output_dir}/{period.start}_to_{period.end}.md
```

보고서 형식 자체는 `format_c.md` 에 명세됨. 이 문서는 작업 절차에 집중.

---

## 작업 절차 (5단계)

```
1. 입력 데이터 읽기 + 이해
2. 각 그룹에서 패턴 후보 추출
3. 도메인 무관성 필터링
4. 느슨한 그룹화 판정
5. 보고서 작성 (format_c.md 따르기)
```

---

## 단계 1: 입력 데이터 읽기 + 이해

```python
import pandas as pd, json

episodes = pd.read_parquet("~/.cache/cc-analyzer/{period}/episodes.parquet")
aggregated = json.load(open("~/.cache/cc-analyzer/{period}/aggregated.json"))
config = yaml.load(open("~/.config/cc-analyzer/config.yaml"))
```

다음을 머릿속에 그린다:
- 기간 메타 (시작/끝, 세션 수, 에피소드 수)
- situation_cluster 별 그룹 (각 그룹의 대표 에피소드, 시그니처 시퀀스, 메트릭)
- 메타 정보 (자주 쓰는 Claude Code 기능, 기능 그룹, 도구)
- 시계열 데이터 (기간 ≥ 2주일 때)

---

## 단계 2: 각 그룹에서 패턴 후보 추출

각 situation_cluster 그룹마다 패턴 후보 1-3개 뽑기.

### 패턴 후보 추출 방법

각 그룹에 대해 다음을 살펴본다:
1. 대표 에피소드 3-5개의 actual turn 시퀀스 (turns.parquet 참조)
2. 그룹의 시그니처 도구 시퀀스 (aggregated.json)
3. 그룹의 자주 쓰는 기능 그룹
4. **phase 별 분포** (`phase_function_groups`, `phase_signatures`) — 에피소드 도입부/중반/종료부에서 일어나는 일이 다른지
5. **outcome 분포** (`outcome_distribution`) — 이 그룹은 어떻게 끝나는가
6. **git 의도 분포** (`git_intent_distribution`, `diagnostic_git_share`) — 시간축 진단을 쓰는가

이 정보를 보고 **"이 그룹의 사용자는 보통 어떤 상황에서 어떤 행동 시퀀스를 하는가?"** 한 문장으로 추출.

### 도입부에 갇히지 말 것

대표 에피소드를 처음 보면 도입부의 인상이 강해 "코드 보기 전에 로그부터 끌어옴" 류 패턴만 자꾸 잡힌다. 이를 피하기 위해 그룹마다 **세 종류 패턴 후보**를 따로 시도해본다:

**(a) 도입부 패턴 후보** — intro phase 의 도구 흐름이 일관되면
- "본격 작업 전에 [도구]로 사실부터 확보한다" 류

**(b) 종료부 패턴 후보** — verify phase 가 비어있지 않은 에피소드가 절반 이상이거나, `verified_by_data` / `verified_by_run` / `delegated_and_reported` 가 outcome_distribution 에 의미 있는 비중이면
- "변경 후 데이터/실행으로 한 번 더 확인한다" 류
- "검증·실행까지 위임하고 결과 요약만 받는다" 류
- "작업 끝에 commit→push→PR 한 흐름으로 마무리한다" 류 (committed+pushed+pr_opened 가 동반)

**(c) 시간축 진단 패턴 후보** — `diagnostic_git_share` 가 작지 않으면(같은 그룹에서 회귀 추적이 반복 관찰되면)
- "현상만 보지 않고 언제부터 다르게 동작했는지를 git 으로 거슬러 올라간다" 류

**(d) commit/PR 양상 패턴 후보** — `outcome_distribution` 의 `incremental_commits` / `single_final_commit` / `pr_with_structured_body` 중 어느 하나가 의미 있는 비중이면
- "작업 도중 단계마다 commit 으로 끊어 가며 진행한다" 류 (incremental_commits)
- "작업을 끝까지 끌고 가 한 번에 commit 으로 마무리한다" 류 (single_final_commit)
- "PR 본문을 요약·테스트 계획 섹션으로 구조화해 만든다" 류 (pr_with_structured_body)
- 단, 두 양상이 비슷한 비중이면 보고서에서 단정하지 말고 평탄하게(둘 다 관찰됨) 적기

세 후보가 모두 만들어지지 않을 수도 있다 — 그 자체가 정상. 신호가 약하면 후보를 만들지 말 것.

### (e) turn 단위 미니 패턴 후보 (광역 모드만)

`aggregated.json.mini_pattern_candidates` 가 있으면 (= 광역 모드) 다음 3가지에서 추가 후보를 뽑는다:

1. **tool_microsequences**: `(Read, Edit, Read)` 같은 짧은 도구 조합. 같은 도구가 반복되거나 의식적인 재확인 신호.
   - 후보 문장 예: "수정 직후 다시 같은 파일을 한 번 더 읽어 확인한다"

2. **user_utterance_trigrams**: 사용자가 자주 쓰는 짧은 표현. 작업 방식의 관용구.
   - 후보 문장 예: "복잡한 결정엔 'ultrathink 별도 context' 표현으로 본 컨텍스트와 분리된 사고를 요청한다"

3. **tool_arg_patterns**: 같은 도구를 비슷한 인자 조합으로 자주 호출. 도구 사용 습관.
   - 후보 문장 예: "코드 검색 시 항상 언어 필터(`rg -t java`)를 붙여 false positive 를 미리 줄인다"

**중요**: 후보는 빈도가 아니라 **의미** 로 판단. trigram 빈도가 50 이어도 의미가 없으면 (예: "그리고 그 다음") 패턴 아님. 빈도가 1 이어도 메서드러지가 명확하면 (예: 1회의 git bisect 시퀀스라도 절차가 분명하면) 후보.

`--curated` 모드에서는 이 후보를 보지 않는다. 광역 모드에서만 시도.

### 검토 대상 누락 방지 체크리스트 (광역 모드 필수)

광역 모드에서 "도입부 류 패턴" 만 잡고 끝내는 편향을 막기 위해, 다음 체크리스트를
**모든 그룹에 대해** 한 번씩 적용. 신호가 약하면 후보 미생성 — 강제 X.

```
[ ] outcome_distribution 에 등장하는 모든 outcome 종류에 대해
    "이 outcome 이 발현되는 작업 흐름은 어떤가?" 를 한 번씩 점검
    - committed / pushed / pr_opened → 작업 마무리 흐름
    - verified_by_data / verified_by_run → 변경 후 검증 흐름
    - delegated_and_reported → 위임 결과 수령 흐름
    - incremental_commits / single_final_commit → commit 단위 양상
    - pr_with_structured_body → PR 본문 작성 양상
    - abandoned_or_paused → 중단·재개 양상 (보고서엔 단정 X)

[ ] git_intent_distribution 의 세 종류 모두 확인
    - diagnostic → 시간축 진단 패턴
    - output → 산출 마무리 패턴
    - transition → 브랜치 이동 패턴

[ ] phase_function_groups 의 intro / main / verify 각각 도구 분포 차이 확인
    - intro 에만 두드러진 도구 → 작업 시작 의식 패턴 후보
    - main 에만 두드러진 도구 → 본격 작업 도구 패턴 후보
    - verify 에만 두드러진 도구 → 작업 종료부 의식 패턴 후보

[ ] episode_kind_distribution 의 세 종류 각각 점검
    - with_changes → 변경 + 결과 양상 패턴
    - investigation_only → 조사 메서드러지 패턴
    - tooling_only → 도구 자체 사용 양상 패턴

[ ] mini_pattern_candidates 세 종류 모두 훑기 (광역 모드일 때)
    - tool_microsequences → 짧은 도구 조합 의식
    - user_utterance_trigrams → 사용자 발화 관용구
    - tool_arg_patterns → 도구 호출 옵션 습관
```

각 항목에서 발견한 후보를 모두 **일단 적어두고**, 최종 본문 작성 시점에 비슷한 의미끼리만
머지하거나 단독 패턴으로 유지. 어느 것도 미리 폐기하지 말 것 (`--curated` 모드가 아닌 한).

### 사용자 인지 vs 데이터 발현 가드 (약속 1 함정 회피)

분석 결과를 보고 사용자가 "내가 자주 한 X 패턴이 왜 없냐" 고 물어도, 그걸 보고서에
강제 삽입하지 말 것. 대신 다음 세 가지 중 무엇인지 추적:

1. **실측 신호 결함** — 그 패턴의 신호(outcome/git_intent/mini) 가 데이터에는 있는데
   추출 단계에서 누락. 이건 코드/명세 보완 대상.
2. **인지 편향** — 사용자가 자주 했다고 기억하지만 실제 빈도는 낮음. 보고서가 맞음.
3. **다른 형태** — 같은 의미인데 보고서엔 다른 이름·다른 표현으로 들어가 있음.

(1) 이면 다음 실행에서 자연스럽게 잡힘. (2)(3) 이면 그대로 둠. **(1) 도 끼워맞춤 X — 다음 분석에서 자연히 나올지 관찰**.

### episode_kind 별 처리

`episode_kind_distribution` 을 보고 그룹의 성격을 먼저 파악한다.

- **`with_changes` 위주 그룹**: 위 (a)~(d) 모든 후보 시도 가능
- **`investigation_only` 위주 그룹**: (a) 도입부 패턴과 (c) 시간축 진단 패턴만 시도. (b) 종료부 패턴과 (d) commit/PR 양상은 정의상 발현 안 됨 — 억지로 만들지 말 것.
- **`tooling_only` 위주 그룹**: 패턴 후보 만들지 말 것. 메타 정보에서만 다룸.

직군 차이 주의: 본인 데이터에선 with_changes 비율이 높지만, 다른 직군(PM/QA/오퍼레이션) 은 investigation_only 비율이 더 높을 수 있다. 그룹별 성격에 맞춰 후보를 시도하는 게 약속 5(직군 무관) 를 지키는 길.

### 신호 → 패턴 매핑 표

Stage C 가 제공하는 신호와 패턴 후보의 매핑은 `format_c_spec.md` 의 "신호 → 패턴 후보 매핑" 표 참고.
단일 신호만으로 패턴 문장을 만들지 말 것. **신호 + 대표 에피소드 actual turn 시퀀스가 일치할 때만** 채택.

### 대표 에피소드 선정에 대한 메모

Stage C 가 이미 선정해 둔 representative_episodes 는 빈도 외에도:
- verify phase 존재 여부
- outcome 보유 여부
- diagnostic git 의도 여부

에 따라 가점된 것이다. 즉 종료부·회귀추적 패턴이 발현된 에피소드가 우선적으로 들어있다. Stage D 가 다시 빈도 기준으로만 골라 도입부 편향을 만들지 말 것.

### 좋은 패턴의 특징

다음을 충족하는 것을 패턴이라 부른다:

1. **상황 + 행동 구조**
   - "[어떤 상황]일 때 [어떤 행동 시퀀스]한다"
   
2. **메서드러지 (방법론)**
   - 단순히 "어떤 도구를 자주 쓴다" 가 아니라
   - "어떤 도구를 어떤 순서로, 왜 그렇게 쓰는가"

3. **재사용성**
   - 다른 상황에서도 같은 메서드러지가 반복 관찰됨
   - 1회성 우연이 아닌 일관된 패턴

### 패턴 후보 예시

좋은 후보:
- "에러나 이상 신호가 보이면 관련 로그를 통째로 수집한 뒤 분석을 시작한다"  ← 도입부
- "복잡한 검토는 별도 에이전트에 위임하고 결과를 반복 반영한다"
- "도구 간 식별자를 매개로 체이닝한다"
- "변경을 마쳤으면 데이터로 결과를 다시 확인한 뒤 보고만 받는다"  ← 종료부
- "현상만 보지 않고 언제부터 다르게 동작했는지를 git 으로 거슬러 올라간다"  ← 시간축 진단
- "작업 도중 단계마다 commit 으로 끊어 가며 진행한다"  ← commit 양상
- "PR 본문을 요약·테스트 계획 섹션으로 구조화해 만든다"  ← PR 양상

나쁜 후보:
- "grafana mcp 를 자주 쓴다" (메서드러지가 아니라 통계)
- "디버깅을 잘 한다" (행동이 구체적이지 않음)
- "WMS 인벤토리 락 에러 처리" (재사용성 X — 단일 상황)

### 그룹 단위 vs 전체 단위

**디폴트는 광역 추출**. 사용자가 보고서를 받아서 첨삭하는 운영 모델이므로, 사소한 패턴까지 후보로 남겨두는 게 낫다.

- 각 situation_cluster 안에서 **개수 상한 없음**. 신호가 보이는 만큼 추출
- 전체 패턴 수도 **상한 없음**. 30개, 50개도 OK
- 너무 적으면(전체 3개 미만) 분석 의미 약함 → 그 경우엔 기간이 짧거나 데이터가 부족한 신호
- 한 그룹에서 같은 메서드러지가 여러 변주로 보이면 변주마다 별도 패턴으로 추출 (합치지 말 것)

**`--curated` 모드** (사용자가 명시적으로 지정한 경우만): 전체 5-8개, 그룹당 1-3개로 제한. 1회성·도메인 특화 폐기. 동료에게 직접 공유할 보고서가 필요할 때 사용.

---

## 단계 3: 도메인 무관성 필터링

추출된 패턴 후보에서 도메인 의존적인 것 제거 또는 추상화.

### 판정 기준

각 패턴 후보에 대해 다음 질문:

> "이 패턴을 다른 도메인 사람 (예: 프론트엔드 개발자, 디자이너) 이 읽고 자기 도구로 치환해서 따라할 수 있을까?"

**Yes** → 유지
**No** → 추상화 시도 or 폐기

### 추상화 예시

도메인 의존:
```
"WMS 인벤토리 락 충돌 발생 시 grafana 에서 SubmitFCWorkerPackingOutbound 
관련 로그를 일괄 수집"
```

추상화:
```
"동시성 충돌 발생 시 grafana mcp(로그 검색 도구)에서 관련 로그를 일괄 수집"
```

핵심:
- 회사 시스템명 (WMS, OMS 등) 은 사내 공유 전용이라 그대로 OK
- 회사 내부 메서드명/엔티티명 (SubmitFCWorkerPackingOutbound, InventoryEntity 등) 은 추상화 ("동시성 충돌", "관련 로그" 등)
- 도구 이름 (grafana, datadog 등) 은 그대로 유지

### 후보가 너무 도메인 특화일 때

**디폴트 (광역 모드)**: 추상화를 시도해보고, 실패하더라도 후보를 폐기하지 말 것. 도메인 어휘가 남아있어도 그대로 보고서에 넣는다. 사용자가 첨삭 시 판단함.

**`--curated` 모드일 때**: 추상화해도 무의미해지는 패턴(예: "WMS 의 특정 워커가 X 상황에서만 발생하는 Y" 같은 1회성)은 폐기.

### 좋은 패턴의 기준 (디폴트 모드 재정의)

앞서 정의한 "좋은 후보의 3가지 특징" 중 **재사용성(일관성)** 만 디폴트에서 완화한다:

- ✅ 상황 + 행동 구조 (유지) — 단순 "도구를 자주 쓴다" 류는 여전히 제외
- ✅ 메서드러지 (유지) — "왜 그렇게 쓰는가" 가 보이지 않으면 후보 제외
- ⚠️ 재사용성 (광역 모드에서 완화) — 발현 1회여도 메서드러지가 명확하면 후보 유지

이 완화는 약속 1 위반이 아니다 (본인 데이터에 맞춰 룰을 좁히는 게 아니라, **모든 사용자에게 동일하게 적용되는 모드 정책**임).

---

## 단계 4: 느슨한 그룹화 판정

`format_c.md` 의 그룹화 규칙 따르기.

요약:
- 패턴 5-8개를 보고 의미상 자연스럽게 묶이는 그룹이 있나?
- 조건:
  - 그룹당 최소 2개 패턴
  - 그룹은 3개 이상 형성될 때만 그룹화
  - 한 패턴이 두 그룹에 걸치면 그룹화 안 함 (모호)
- 자연스러운 그룹 3개 이상 → 그룹화
- 없거나 모호 → 평탄 (그냥 나열)

### 그룹화 가능 예시

3개 자연 그룹 형성:

```
A. 정보 우선 (본격 작업 전 사실 데이터부터 확보)
  - 에러나 이상 신호가 보이면 관련 로그를 통째로 수집한 뒤 분석을 시작한다
  - 에러 디버깅 전 관련 기능의 정상 동작 설명을 먼저 만든다

B. 도구 체이닝 (식별자로 도구 잇기)
  - 도구 간 식별자를 매개로 체이닝한다

C. 외부 검토 루프
  - 복잡한 검토가 필요한 작업은 별도 컨텍스트의 에이전트에 위임한다
```

→ 그룹화 가능 (단 B 그룹이 1개라 조건 위반. 다시 검토. B 가 더 안 묶이면 전체 평탄으로)

### 평탄 출력

```
- 에러나 이상 신호가 보이면 관련 로그를 통째로 수집한 뒤 분석을 시작한다
- 도구 간 식별자를 매개로 체이닝한다
- 복잡한 검토가 필요한 작업은 별도 에이전트에 위임한다
- ...
```

---

## 단계 5: 보고서 작성

`format_c.md` 의 형식 명세 정확히 따르기.

큰 흐름:
1. 메타 헤더 (기간, 세션 수, 에피소드 수 등)
2. 주요 워크플로 패턴 (그룹화 또는 평탄)
3. 시계열 추이 (기간 ≥ 2주일 때만)
4. 사용 메타 정보 (자주 쓰는 기능/도구 top N)
5. 참고 (raw 데이터 위치, 오류 신고 등)

### 패턴 본문 작성 시 주의

`format_c.md` 의 도구 표기 룰 정확히 적용:
- 일반 공개 도구 첫 등장 시: `grafana mcp(로그 검색 도구)`
- 두 번째 등장부터: `grafana mcp` 만
- 한 패턴 안에서만 카운트 (다른 패턴에선 다시 처음)
- 회사 시스템명 (WMS 등) 그대로 노출 (사내 공유)
- 동료 이름은 마스킹 (config.mask_people_names = true 일 때)

### 가독성 — 다른 직군 개발자 기준

받는 사람은 coding agent 사용자이지만 시스템 내부 신호 이름·도구 내부명은 모른다.
본문·시계열·메타 정보 어디에도 다음 어휘를 쓰지 말 것:

**금지 1: 시스템 내부 라벨**
outcome, phase, intro, main, verify, git_intent, diagnostic, episode_kind, with_changes, investigation_only, tooling_only, mini_pattern, situation_cluster, function_group, committed, pushed, pr_opened, verified_by_data, verified_by_run, delegated_and_reported, incremental_commits, single_final_commit, pr_with_structured_body, abandoned_or_paused

**금지 2: Claude Code 도구 내부명** — 일반 동사로:
- Bash → 셸 실행, 명령 실행
- Edit → 파일 수정
- Read → 파일 읽기
- Write → 새 파일 작성
- Grep / Glob → 코드 검색, 파일 검색
- Task / Agent → 별도 세션 위임, 서브 에이전트 위임
- TaskCreate / TaskUpdate → 단계별 to-do 관리, 진행 추적
- ToolSearch → 필요 도구 찾아 로딩
- ExitPlanMode → Plan Mode 의 계획 확정
- AskUserQuestion → 사용자에게 선택지 묻기

**유지 OK**
- AI agent 추상 구조 (Subagent, Plan Mode, 슬래시 커맨드, /clear, 별도 컨텍스트 agent, fresh agent, cold review, ultrathink)
- MCP 표기 (`grafana mcp(로그 검색 도구)` 등)

이 룰은 **본문 어휘**에 대한 것이며, 신호 다양성(어떤 종류의 패턴을 다루는가) 점검과는 별개. 종료부 의식 패턴을 추출하되 본문에는 "verify phase outcome" 같은 어휘 X, 대신 "작업이 끝나면 ..." 같은 일반 표현으로 풀어 쓰기.

### 사용 예시 블록 작성 (모든 패턴 필수)

각 패턴 본문 뒤에 코드 블록 형태의 사용 예시 추가. 줄글만 있으면 다른 직군 동료가
자기 도구로 치환하기 어려워서 단계 시퀀스로 즉시 이해 가능하게.

**도메인은 4가지 중에서만 선택**:
1. REST API / 디버깅
2. 인증 / 토큰
3. 캐시 / DB
4. Git / 테스트 / 빌드

**도메인 선택 가이드** (패턴의 본질에 가까운 걸로):
- 로그 검색·이상 신호 패턴 → REST API / 디버깅
- 식별자 체이닝 패턴 → 인증 / 토큰 또는 REST API / 디버깅
- DB 쿼리·데이터 검증 패턴 → 캐시 / DB
- git diagnostic 패턴 → Git / 회귀 추적
- commit/PR 양상 패턴 → Git / 테스트 / 빌드 또는 Git / PR
- 위임·검토 패턴 → REST API / 설계 결정

**예시 작성 룰**:
- 도메인 라벨 명시: `**사용 예시 (REST API 서버 디버깅):**`
- 3-6 단계, 각 단계는 한 줄~두 줄
- 명령/쿼리는 인라인 코드: `service:"user-api"`, `git log -- src/auth.py`
- 회사 시스템명 절대 금지 — WMS, OMS, wms-api, logistics-auth, kakaostyle 등
- 사내 슬래시/플러그인 이름 금지 — `/plan-reviewer:review-plan` 같은 거 안 됨

**예시 작성 후 자가 점검 (필수)**:
```
checklist:
  - 도메인 라벨이 위 4가지 중 하나인가?
  - 회사 시스템명이 들어가지 않았나? (wms/oms/logistics/kakaostyle 키워드 검색)
  - 명령·쿼리가 일반 개발자가 즉시 이해할 형태인가?
  - 단계 수가 3-6 사이인가?
```

**구체 작성 예시**:

본문이:
> 운영 환경에서 cache miss나 fail-open 같은 이상이 보이면 코드부터 보지 않고
> grafana mcp(로그 검색 도구) 의 query_logs 를 3-4회 연속 호출해 시간대·사용자·필터별로
> 좁혀가며 로그를 통째로 끌어온다...

사용 예시 후보 (REST API / 디버깅 도메인 선택):
```
**사용 예시 (REST API 서버 디버깅):**
1. grafana mcp(로그 검색 도구) 에서 5xx 에러 조회
   query: status:>=500 service:"user-api"
2. 응답 느린 user_id 추출
3. 같은 trace_id 로 인증 서비스 로그 이어 조회
4. 코드 경로 확인 시작
```

**예시 검증 실패 (회사명 포함) 시**:
Stage D 후처리에서 `company_system_in_example` WARN 이 뜨면, 해당 패턴의 사용 예시만
일반 도메인으로 재생성 1회. 재시도 후에도 남으면 그대로 두되 사용자에게 안내.

### "왜" 는 본문에 자연스럽게 녹임

```
좋음:
"운영 환경에서 에러가 발생하면 코드부터 보지 않고, 먼저 grafana mcp 
(로그 검색 도구)에서 관련 access log 키를 주고 한 번에 끌어와 전체를 
훑은 뒤 본 작업에 들어간다. 가설을 좁힌 상태에서 코드를 보기 때문에 
무관한 path를 헤매지 않게 됨."

나쁨:
"... 일괄 수집한 뒤 본 작업에 들어간다.
**왜**: 가설을 좁힌 상태에서 ..."
```

`**왜**:` 같은 라벨 X. 마지막 문장으로 자연스럽게.

### 저장

임시 위치에 작성:
```python
draft_path = f"~/.cache/cc-analyzer/{period}/report_draft.md"
with open(draft_path, 'w') as f:
    f.write(report_markdown)
```

이 시점엔 아직 최종 저장 X. SKILL.md 단계 6 (보고서 검증) 후에 최종 저장.

---

## 셀프 체크 (이 단계 끝났을 때)

**약속 1 (튜닝 X)**:
- 본인 데이터 보고 패턴 추출 기준 바꾼 적 있나? 없음 → OK
- 본인이 잘 보이게 보고서 톤 조정한 적 있나? 없음 → OK
- 종료부/회귀추적 패턴이 안 보인다고 신호 임계값을 낮춰 억지로 만들지 않았나? → 안 보이면 안 쓰는 게 정답. 약속 1 위반 X.

**약속 2 (코드에 박지 마)**:
- 패턴 후보를 미리 정해둔 enum 에서 고르지 않음 → OK
- 보고서 형식은 format_c.md 명세 따름 → OK

**약속 3 (다른 사람 검증 강제 X)**:
- 사용자에게 "이 패턴 맞나요?" 확인 받지 않음 → OK

**약속 4 (정보 안 새기)**:
- 회사 메서드명/엔티티명 추상화 → OK
- 회사 시스템명은 사내 공유 전용이라 OK
- 시크릿/동료 이름은 단계 6 검증에서 자동 처리

**약속 5 (일반화 강건성)**:
- 도메인 무관성 필터링 거침 (단계 3) → OK
- 다른 직군 사람이 읽고 자기 도구로 치환 가능한지 확인 → OK
