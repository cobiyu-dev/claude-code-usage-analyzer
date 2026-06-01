# Format C 명세 (Stage D 통합)

## 역할

이 문서는 두 가지를 정의함:

1. **보고서 출력 형식** — 사용자가 받는 최종 결과물의 구조와 톤
2. **Stage D 동작 명세** — 위 형식을 만들기 위한 LLM(Opus) 호출 방식과 후처리

```
입력:  episodes.parquet (Stage B 출력) + aggregated.json (Stage C 출력)

처리:  1. LLM(Opus) 1회 호출 — 패턴 추출 + 보고서 생성
       2. 자동 검증 (시크릿/이름/도구 표기)
       3. 자동 보완 (도구 괄호 표기 누락 시)

출력:  {start}_to_{end}.md
```

---

## 1. 보고서 전체 구조

```markdown
# Claude Code 사용 패턴 분석

[메타 헤더]
기간: 2026-04-20 ~ 2026-05-17 (4주)
세션 수: 47개
에피소드 수: 23개  
실행 시각: 2026-05-18 09:32
실행 모드: manual --last 4w

---

## 주요 워크플로 패턴

[패턴들 — 느슨한 그룹화 또는 평탄]

---

## 시계열 추이 (기간 ≥ 2주일 때만)

[주차별 또는 월별 요약]

---

## 사용 메타 정보

자주 쓰는 Claude Code 기능 top 5
자주 쓰는 기능 그룹 top 5
자주 쓰는 도구 top 10

---

## 개인 로컬 셋업

[다른 사람과 공유 안 하는 ~/.claude/ 의 개인 설정 — 자연어 설명 톤]

---

## 참고

이 보고서는 자동 생성됨. 
의심스러운 내용 있으면 raw 데이터 확인: ~/.claude/projects/
의견/오류 신고: [...]
```

---

## 2. 패턴 한 개 형식

```markdown
#### [그룹문자]-[번호]. [짧은 라벨 — 2-5단어]

> [한 줄 제목 — 상황 + 행동을 한 줄로 요약]

[1-2 문장 짧은 본문. 패턴의 핵심을 풀어 씀. "언제/어떻게/왜" 를 한 단락에 욱여넣지 말고
 다음 3줄 bullet 에서 쪼개 보여줄 것이므로, 본문은 그 위 짧은 안내 정도로.]

- **언제**: [이 패턴이 발동되는 상황·트리거 — 한 줄]
- **어떻게**: [구체적 행동·발화 모양 — 한 줄. 사용자 발화 예시를 따옴표로 짧게 넣을 수 있음]
- **왜**: [이 패턴이 가져다 주는 효과·동기 — 한 줄]

**사용 예시 ([도메인 라벨])**

상황: [한 줄로 어떤 상황인지 — 일상 표현]
이렇게 풀어갔다 ↓

1. [그 시점에 사용자가 뭘 하고 싶었는지 — 의도 한 줄]
   → "[실제로 친 자연어 메시지]"

2. [AI 가 1번에 어떻게 응답했는지 + 다음 의도]
   → "[실제로 친 메시지]"

3. ...

---
```

### 헤더·구분선

- **패턴 헤더**: `#### [그룹문자]-[번호]. [짧은 라벨]`
  - 그룹문자: A, B, C, D ... (그룹 헤더 `### A. ...` 에 맞춤)
  - 번호: 그룹 안에서 1부터 (A-1, A-2, B-1, B-2 ...)
  - 짧은 라벨: 2-5단어. "사실 수집 위임", "분담 명시", "푸시백 의식" 같이 패턴의 핵심을 짧게.
- **한 줄 제목**: 인용구 (`> `) 한 줄. 본문 첫 줄과 같은 톤 (사용자 지시 어조).
- **본문**: 1-2문장. 길어지면 안 됨. 세부는 아래 3줄 bullet 으로 쪼갬.
- **bullet 3줄 (언제 / 어떻게 / 왜)**: 각각 한 줄. **언제** 는 트리거, **어떻게** 는 구체 행동·발화, **왜** 는 효과·동기.
- **사용 예시 블록**: 기존 형식 그대로 (상황 한 줄 + 단계별 두 줄).
- **패턴 사이 구분선**: `---` 한 줄. 시각적으로 패턴 단위가 분명히 끊기게.

### 규칙

- 도구 이름은 일반 공개 도구만 표기. 회사 내부 시스템명은 본문엔 그대로 노출 (사내 공유 전용)
- 일반 공개 도구 첫 등장 시 인라인 괄호로 기능 설명: `grafana mcp(로그 검색 도구)`
- 같은 패턴 안에서 같은 도구 두 번째부터는 도구명만
- 빈도/통계 표시 X
- **언제/어떻게/왜 3줄 bullet 은 모든 패턴에 필수** — 본문이 길게 풀어진 한 단락 X
- **사용 예시 블록은 모든 패턴에 필수**. bullet 직후

### 가독성 룰 (다른 직군 개발자가 읽을 수 있도록)

보고서를 받는 동료는 coding agent 를 쓰지만 시스템 내부 구조는 모른다. 다음 두 종류 용어는 본문·사용 예시·시계열·메타 정보 어디에도 등장하면 안 된다.

#### 금지 1: 시스템 내부 라벨

`outcome`, `phase`, `intro`, `main`, `verify`, `git_intent`, `diagnostic`, `episode_kind`, `with_changes`, `investigation_only`, `tooling_only`, `mini_pattern`, `mini_pattern_candidates`, `tool_microsequences`, `user_utterance_trigrams`, `situation_cluster`, `function_group`, `phase_function_groups`, `verify_phase_share`, `diagnostic_git_share`, `committed`, `pushed`, `pr_opened`, `verified_by_data`, `verified_by_run`, `delegated_and_reported`, `incremental_commits`, `single_final_commit`, `pr_with_structured_body`, `abandoned_or_paused`

이건 시스템이 신호를 부르는 이름일 뿐 보고서 독자 어휘가 아니다. 본문에 들어가면 즉시 FAIL.

#### 금지 2: Claude Code 도구 내부명을 그대로 노출

`Bash`, `Edit`, `Read`, `Write`, `Grep`, `Glob`, `Task`, `TaskCreate`, `TaskUpdate`, `ToolSearch`, `ExitPlanMode`, `AskUserQuestion`, `Agent` (대문자 그대로의 도구 이름)

이걸 본문에 그대로 쓰면 coding agent 내부를 아는 독자만 이해 가능. 일반 동사로 풀어 쓴다:

| 내부명 | 본문 표기 |
|---|---|
| Bash | "셸 실행", "명령 실행", "스크립트 실행" |
| Edit | "파일 수정", "코드 수정" |
| Read | "파일 읽기" |
| Write | "파일 작성", "새 파일 생성" |
| Grep | "코드 검색", "패턴 검색" |
| Glob | "파일 경로 검색" |
| Task / Agent | "별도 세션으로 작업 위임", "서브 에이전트에 위임" |
| TaskCreate / TaskUpdate | "단계별 to-do 관리", "작업 추적" |
| ToolSearch | "필요한 도구 찾아 로딩" |
| ExitPlanMode | "Plan Mode 의 계획 확정" |
| AskUserQuestion | "사용자에게 선택지 묻기" |

#### 유지 OK

- AI agent 추상 구조 어휘: `Subagent`, `서브 에이전트`, `Plan Mode`, `슬래시 커맨드`, `/clear`, `별도 컨텍스트 agent`, `fresh agent`, `cold review`, `ultrathink` 같은 표현은 그대로 쓰거나 자연어로 풀어도 OK
- MCP 표기: `grafana mcp(로그 검색 도구)`, `mysql mcp(DB 쿼리 도구)` 등. 일반 공개 도구의 MCP 이름은 그대로
- 회사 시스템명(WMS, OMS 등) 은 본문엔 OK (사내 공유 전용)
- 회사 내부 메서드명은 추상화 ("특정 워커" 등)

### 사용 예시 블록 안에서의 도구 표기

사용 예시 코드 블록은 단계 시퀀스 형태인데, 여기서 도구 내부명을 쓰는 건 일부 허용한다 (시퀀스가 짧고 구체적이라 일반 동사로 풀면 오히려 모호). 다음 두 가지 중 선택:
- "1. grafana mcp(로그 검색 도구) 로 ... " — MCP/공개 도구는 그대로
- "1. 파일 검색 → 의심 위치 발견" — 내부 도구는 동사화

같은 사용 예시 블록 안에서 일관성만 지키면 됨.

### 패턴 본문 어조 (사용자 지시 어조 — 필수)

이 보고서는 "어떤 패턴으로 coding agent 를 프롬프트하는가" 를 잡는 문서.
따라서 본문 어조도 **사용자가 AI 에게 시키는 시점** 으로 통일.

- "AI 가 ... 한다" → "... 하도록 시킨다" / "... 하게 지시한다" / "... 게 한다"
- "... 직접 한다" (사용자 자기 손으로) → 보통 "... 직접 하게 시킨다" 로
  단, 사용자가 실제로 자기 손으로 하는 행동 (메시지 본문 작성, 외부 시스템에서 직접 두드린 결과 붙여 넣기 등) 은 그대로
- 어미를 다양화: "...게 한다", "...도록 시킨다", "...라고 한 번 묻는다", "...게 만든다", "...게 굴린다"
  - 같은 어미만 반복 X
- 길이 변화 최소. 한 문장이 더 길어지지 않게 짧게 끊거나 어미만 바꾼다.
- 사용 예시 블록 안의 "의도 줄" / "→ 메시지 줄" / 시계열·메타 정보 / 그룹 헤더는 어조 변경 대상이 **아님** (각각 사용자 시점 또는 통계 톤)

| Before (모호한 톤) | After (사용자 지시 어조) |
|---|---|
| "코드부터 열지 않고 grafana mcp 로 ... 호출해 ... 수집한다" | "코드부터 열지 않고 grafana mcp 로 ... 끌어오게 시켜 ... 모으는 흐름" |
| "git 으로 변화 시점을 추적하는 비중이 ..." | "git log/diff 로 변화 시점을 거슬러 보게 시키는 흐름이 ..." |
| "PR 본문을 ... 섹션을 갖춰 만든다" | "PR 본문도 ... 섹션을 갖춰 만들도록 시킨다" |
| "변경이 끝나면 commit · push · PR 까지 한 번에 마무리한다" | "변경이 끝나면 commit · push · PR 까지 한 흐름에서 마무리하도록 시킨다" |
| "작업이 끝나면 직접 앱·배치를 띄워 curl 로 호출해 보고 alpha DB 로 결과까지 확인한다" | "작업이 끝나면 claude code 가 직접 앱·배치를 띄우게 지시하고 직접 curl 로 호출해서 alpha DB mcp 로 결과까지 확인하도록 한다" |

### 사용 예시 블록 규칙

**보고서의 본질**: 이 보고서는 사용자가 **"어떤 패턴으로 coding agent 를 프롬프트하면서 사용하는가"** 를 잡는다. **"어떤 명령어를 사용했는가"** 가 아니다.

따라서 사용 예시 블록은 **사용자가 coding agent 에게 보낸 메시지(프롬프트)의 시퀀스** 다. AI 가 호출한 도구나 실행한 명령의 시퀀스가 아니다.

#### 사용자 발화 vs AI 실행 — 명확한 차이

| ❌ AI 실행 시퀀스 (틀림) | ✅ 사용자 프롬프트 시퀀스 (맞음) |
|---|---|
| `grafana mcp 로 5xx 에러 조회` | `"운영에서 5xx 떨어지는 거 같은데 같이 봐줘. 14시쯤"` |
| `mysql mcp 로 user_id 토큰 만료 조회` | `"위에서 뽑힌 user_id 로 토큰 상태도 확인해줘"` |
| `git log -- src/auth.py 로 최근 변경 확인` | `"이거 언제부터 이렇게 동작했지? 최근 변경 봐줘"` |
| `Edit 으로 cache TTL 조정` | `"이 부분 TTL 좀 줄여줘"` |
| `gh pr list --search "graphql" 로 PR 조회` | `"graphql 스키마 관련 최근 PR 들 찾아줘"` |

핵심: 사용 예시 한 단계 = **사용자가 친 메시지 한 번**.

#### 형식

```markdown
**사용 예시 ([도메인 라벨])**

상황: [한 줄로 어떤 상황인지 — 일상 어휘]
이렇게 풀어갔다 ↓

1. [사용자가 그때 무엇을 하고 싶었는지 — 한 줄]
   → "[실제로 친 자연어 메시지]"

2. [AI 가 1번에 어떻게 응답했는지 + 다음에 뭐 하고 싶었는지]
   → "[실제로 친 메시지]"

3. ...
```

- 각 단계는 **두 줄 구성**: 윗줄은 사용자 의도 (왜 이 메시지를 쳤는지), 아랫줄은 화살표 (→) 뒤에 실제 친 메시지 (따옴표)
- 메시지가 짧으면 짧은 채로 ("응 진행해줘", "그렇게 해줘" 도 OK — 실제로 자주 쓰는 흐름)
- AI 응답 단계는 다음 사용자 단계의 윗줄에 자연스럽게 녹임 ("AI 가 로그 모아 보여줘서, 그중 …") — 별도 단계로 분리하지 말 것
- 첫 줄 "상황:" 은 작업의 시작점만 한 줄로. 본문과 중복되지 않게 일상 표현 한 줄로
- 도구 이름·MCP 이름이 메시지 안에 자연스럽게 등장 가능 (사용자가 "grafana 에서 봐줘" 라고 친 경우)
- **3-6 단계**

#### 도메인 라벨 (예시 도메인은 4가지 중)

블록 헤더에 도메인 명시:
1. **REST API / 디버깅** — user-api, order-api 같은 일반 서비스. 5xx, trace_id, latency
2. **인증 / 토큰** — JWT 만료, OAuth, refresh token
3. **캐시 / DB** — Redis cache miss, MySQL slow query
4. **Git / 테스트 / 빌드** — 회귀 추적, 테스트 실행, 빌드 오류

#### 금지

- **회사 내부 시스템명** — WMS, OMS, wms-api, logistics-auth, kakaostyle 같은 본인 데이터 어휘
- **사내 슬래시 스킬 이름** — `/plan-reviewer:review-plan` 같은 사내 플러그인 (본문엔 OK)
- **AI 실행 시퀀스 형태** — "grafana mcp 로 5xx 에러 조회" 처럼 AI 가 무엇을 했는지 서술 X. 사용자가 무엇을 부탁했는지로.

### 좋은 예시 / 나쁜 예시

✅ 좋음:
```
**사용 예시 (REST API 서버 디버깅)**

상황: 운영에서 user-api 가 갑자기 5xx 를 뱉기 시작.
이렇게 풀어갔다 ↓

1. 로그부터 끌어와 가설을 좁히고 싶다.
   → "운영에서 5xx 떨어지는 거 같은데 시간대 14시쯤 로그 좀 봐줘"

2. AI 가 에러 응답을 모아 보여줘서, 그중 응답 느린 사용자를 추리고 싶다.
   → "응답 느린 user_id 들 추출해줘"

3. 같은 호출 흐름을 인증 서비스에서도 이어서 보고 싶다.
   → "같은 trace_id 로 인증 서비스 로그도 이어서 봐줘"

4. 이제 코드 어디부터 봐야 할지 짚어 달라.
   → "이제 코드에서 어디가 원인인지 찾자"
```

✅ 좋음 (짧은 승인 포함):
```
**사용 예시 (Git / 회귀 추적)**

상황: 멀쩡하던 기능이 어느 순간 이상 동작. 최근 커밋들 중 뭐가 원인일지 모름.
이렇게 풀어갔다 ↓

1. 언제부터 다르게 동작했는지 시간축에서 시작.
   → "이거 언제부터 이렇게 됐지? 최근 커밋들 좀 봐줘"

2. AI 가 의심되는 커밋 후보를 보여줘서, 그 직전 상태로 한 번 돌려 보고 싶다.
   → "의심되는 커밋 직전 시점 동작 재현해줘"

3. 정상 시점을 확인했으니 그 사이 변경만 좁혀서 보고 싶다.
   → "그럼 그 사이 diff 만 좁혀서 분석해줘"

4. 원인을 짚었으니 수정 부탁.
   → "이 부분이 원인 같네. 고쳐줘"

5. 제시한 수정안에 동의.
   → "응 진행해줘"
```

❌ 나쁨 (AI 실행 시퀀스):
```
**사용 예시:**
1. grafana mcp 로 5xx 에러 조회        ← AI 가 무엇을 한 단계로 서술
2. 응답 느린 user_id 추출
3. mysql mcp 로 토큰 만료 시각 조회
```

❌ 나쁨 (상황 / 의도 없이 메시지만):
```
**사용 예시:**
1. "운영에서 5xx 떨어지는 거 봐줘"
2. (AI 가 보여주면) "응답 느린 user_id 들 뽑아줘"
3. "같은 trace_id 로 인증 쪽도"
4. "코드 봐줘"
```
문제: 무슨 상황에서, 왜 이 흐름인지가 안 보임. 단순 메시지 나열로 읽힘.

❌ 나쁨 (회사 시스템명):
```
**사용 예시:**
1. "wms-api 의 5xx 좀 봐줘"            ← wms-api 회사 시스템명
2. "SubmitFCWorkerPackingOutbound 호출 추적"   ← 회사 메서드명
```

❌ 나쁨 (도메인 모호):
```
**사용 예시:**
1. "이거 봐줘"                          ← 무엇을 부탁한 건지 불명
2. "다음으로 가자"
```

### 예시

```markdown
## 에러나 이상 신호가 보이면 관련 로그를 통째로 수집한 뒤 분석을 시작한다

운영 환경에서 에러나 특이사항이 발생하면 코드부터 보지 않고, 먼저
**grafana mcp(로그 검색 도구)**에서 관련 access log 키를 주고 한 번에
끌어와 전체를 훑은 뒤 본 작업에 들어간다. 가설을 좁힌 상태에서 코드를
보기 때문에 무관한 path를 헤매지 않게 됨.

**사용 예시 (REST API 서버 디버깅):**
```
1. "운영에서 5xx 떨어지는 거 같은데, 14시쯤 user-api 로그 좀 봐줘"
2. (AI 가 로그 정리하면) "응답 느린 user_id 들 추출해줘"
3. "같은 trace_id 로 인증 서비스 로그도 이어서 봐줘"
4. "이제 코드에서 어디가 원인인지 가설 좁혀보자"
```

## 도구 간 식별자를 매개로 체이닝한다

한 도구의 결과에 들어있는 식별자를 추출해 다음 도구의 입력으로 넣는
방식으로 도구를 잇는다. 단일 도구만으로는 답이 안 나오는 문제를 식별자
한 줄로 깊이 분석할 수 있음.

**사용 예시 (인증 / 토큰):**
```
1. "auth 서비스에서 jwt expired 로그 나오는 거 좀 보여줘"
2. (로그 보여주면) "여기 나온 user_id 들로 DB 에서 refresh token 만료 시각 조회해줘"
3. "만료 시각이랑 실패 시각이 어떻게 어긋나 있는지 비교해줘"
```

## 변경을 마쳤으면 데이터로 결과를 다시 확인한 뒤 보고만 받는다

코드 수정이 끝나면 같은 컨텍스트에서 곧장 **mysql mcp(DB 쿼리 도구)**로
관련 테스트 데이터를 다시 꺼내거나, 앱 실행과 검증 절차를 한 번에 위임해
최종 결과 요약만 받는다. 종료부에서 데이터로 한 번 더 확인하기 때문에
본인 가설이 틀렸을 때 그 자리에서 잡힌다.

**사용 예시 (캐시 / DB):**
```
1. "이 부분 캐시 TTL 좀 줄여줘"
2. "변경 적용했으면 테스트 한 번 돌려줘"
3. "테스트 통과하면 DB 에서 변경 전후 cache hit ratio 차이도 확인해줘"
4. "결과 요약만 알려줘"
```

## 현상만 보지 않고 언제부터 다르게 동작했는지를 git 으로 거슬러 올라간다

문제 상황을 처음 만났을 때 현재 로그·코드만 보는 대신 `git log` / `git blame` /
`git bisect` 로 정상이었던 시점을 찾아 그 사이의 변경 폭으로 좁힌다. 시간축으로
한 번 자르고 들어가면 검토할 코드 범위가 크게 줄어든다.

**사용 예시 (Git / 회귀 추적):**
```
1. "이거 언제부터 이렇게 동작했지? 이 파일 최근 커밋들 좀 봐줘"
2. "의심되는 커밋 변경 폭 보여줘"
3. "그 커밋 직전 시점으로 돌려서 동작 재현해줘"
4. "정상이었네. 그럼 그 사이 diff 만 좁혀서 분석해줘"
```

## 작업 도중 단계마다 commit 으로 끊어 가며 진행한다

큰 변경을 한 덩어리로 끌고 가지 않고, 단위 변경이 일단락될 때마다 짧은 메시지로
commit 을 만들어 두고 다음으로 넘어간다. 나중에 PR 을 만들 때도 변경의 흐름이
이미 잘게 쪼개져 있어 설명할 거리가 적어진다.

**사용 예시 (Git / 테스트):**
```
1. "User 모델 클래스부터 정의해줘"
2. (모델 끝나면) "여기까지 커밋해줘"
3. "이제 /users 엔드포인트 핸들러 추가"
4. (핸들러 끝) "이것도 커밋"
5. "마지막으로 단위 테스트 작성하고 같이 커밋"
6. (전체 끝) "PR 만들어줘"
```

## PR 본문을 요약·테스트 계획 섹션으로 구조화해 만든다

PR 을 만들 때 단순 한 줄 설명이 아니라 변경 요약, 테스트 계획 같은 섹션을 갖춘
본문을 함께 작성한다. 리뷰어가 변경 의도와 검증 범위를 같은 문서에서 한 번에
파악할 수 있어 리뷰 라운드가 줄어든다.

**사용 예시 (Git / PR):**
```
1. (변경 완료 후) "PR 만들어줘. body 에 Summary 랑 Test plan 섹션 꼭 넣어줘"
2. "Test plan 은 체크리스트로 unit test 항목, 수동 테스트 시나리오 항목 분리해서"
3. (PR 본문 보여주면) "수동 테스트 항목에 invalid email 케이스도 추가해줘"
4. "그대로 생성"
```

## 복잡한 결정엔 본 컨텍스트와 분리된 별도 에이전트로 사고를 요청한다

본인이 이미 한 방향으로 기울었을 때 별도 에이전트를 띄워 같은 문제를 다시
검토하게 한다. 새 컨텍스트는 본 컨텍스트의 편향에서 자유롭기 때문에 이중 점검의
역할로 쓰인다.

**사용 예시 (REST API / 설계 결정):**
```
1. "이 API 설계안 v1 정리해줘"
2. (v1 받고) "이거 별도 컨텍스트의 에이전트한테 처음 보는 시각으로 검토 부탁해줘. 약점 위주로 봐달라고"
3. (검토 결과 받으면) "요약만 보여줘"
4. "이 부분이 일리 있네. 반영해서 v2 만들어줘"
```
```

---

### 신호 → 패턴 후보 매핑

Stage D 가 패턴을 도출할 때 다음 신호를 그대로 한 종류로 정형화하지 말 것.
신호는 **어디를 들여다볼지** 알려주는 후보 표시일 뿐, 실제 패턴 문장은 대표 에피소드의 actual turn 시퀀스를 보고 작성한다.

| Stage C 가 제공하는 신호 | 들여다볼 후보 패턴 |
|---|---|
| `phase_function_groups["intro"]` 에 log_search/db_query/code_search 비중 큼 | "본격 작업 전 사실 데이터부터 끌어와 가설을 좁힌다" 류 |
| `phase_function_groups["verify"]` 에 db_query / shell_exec(execution_like) 비중 큼 | "변경 후 데이터·실행으로 결과를 다시 확인한다" 류 |
| `outcome_distribution["delegated_and_reported"]` 가 작지 않음 | "검증·실행까지 위임하고 결과 요약만 받는다" 류 |
| `outcome_distribution` 에 `committed→pushed→pr_opened` 가 함께 나타남 | "작업 끝에 commit→push→PR 을 한 흐름으로 마무리한다" 류 |
| `outcome_distribution["incremental_commits"]` 가 작지 않음 | "작업 도중 단계마다 commit 으로 끊어 가며 진행한다" 류 |
| `outcome_distribution["single_final_commit"]` 가 작지 않음 | "작업을 끝까지 끌고 가 한 번에 commit 으로 마무리한다" 류 |
| `outcome_distribution["pr_with_structured_body"]` 가 작지 않음 | "PR 본문을 요약·테스트 계획 같은 섹션으로 구조화해 만든다" 류 |
| `diagnostic_git_share` 가 작지 않음 | "현상 외에 git 으로 회귀 시점을 추적한다" 류 |
| `episode_kind_distribution` 에 `investigation_only` 비중이 큼 | 이 그룹은 조사/리뷰 메서드러지 위주로 보고, 변경·종결 패턴을 억지로 만들지 말 것 |
| `mini_pattern_candidates.tool_microsequences` 에 같은 도구 반복 시퀀스 | "수정 직후 같은 파일 재확인" 류 의식 패턴 |
| `mini_pattern_candidates.user_utterance_trigrams` 에 의미 있는 표현 반복 | "특정 발화 관용구로 작업 모드 전환" 류 |
| `mini_pattern_candidates.tool_arg_patterns` 에 동일 인자 조합 반복 | "도구 호출 시 항상 같은 옵션을 붙이는 습관" 류 |
| `outcome_distribution["abandoned_or_paused"]` 가 비교적 높음 | 보고서에 어떻게 표현할지 신중히 — 부정적 단정 X, 본인이 읽고도 도움 되는 톤으로 |
| 사용자 첫 메시지에 코드/명령/쿼리 본문이 **일정 길이 이상 그대로 붙여 들어오는** 케이스가 그룹 안에서 반복 | "외부 출력·본문을 그대로 첫 메시지로 던지고 의미 해석을 시킨다" 류 (도메인은 본문 종류로 분리 — 아래 가드 참조) |
| `outcome_sequences` 에 같은 outcome 이 **둘러싸는 패턴** (A→B→A) 또는 **연쇄** (A→B→C) 가 의미 있는 빈도 | "본인이 한 검증·작업을 다음 도구로 잇고 다시 처음 도구로 돌아와 확인하는 흐름" 류. 시퀀스를 그대로 추상화하지 말고 **대표 에피소드 실제 발화** 의 구체성을 살려 추출 (예: 사용자가 4단계로 발화했으면 4단계로) |
| 신호는 빈약한데 turn 시퀀스에 같은 도구로 다른 인자가 반복 (예: db_query 3회+ 동일 에피소드) | "한 도구를 인자만 바꿔 반복 호출하며 점진적으로 좁힌다" 류 |
| `tone_keyword_counts["plan_first"]` 가 작지 않음 | "본격 작업 전 계획 먼저 박기" 류 |
| `tone_keyword_counts["role_split"]` 가 작지 않음 | "사람·AI 분담 통보하고 시작" 류 |
| `tone_keyword_counts["option_choose"]` 가 작지 않음 | "후보 펼치게 한 다음 한 개 고르기" 류 |
| `tone_keyword_counts["hypothesis_unfold"]` 가 작지 않음 | "본인 가정 박고 결과 같이 펼치기" 류 |
| `tone_keyword_counts["polish_again"]` 가 작지 않음 | "결과물 표현·이름까지 다시 다듬게 시키기" 류 |
| `tone_keyword_counts["interrupt_correct"]` 가 작지 않음 | "안 맞으면 즉시 인터럽트 정정" 류 |
| `tone_keyword_counts["self_validate_full"]` 가 작지 않음 | "띄우기·호출·DB 검증까지 한 번에 맡기기" 류 |
| `tone_keyword_counts["ask_objective"]` 가 작지 않음 | "별도 창에 객관 검토 받기" 류 |
| `tone_keyword_counts["diff_models"]` 가 작지 않음 | "다른 모델로 한 번 더 검토" 류 |
| `tone_keyword_counts["loop_n_times"]` 가 작지 않음 | "N회 반복 검토 루프 만들기" 류 |
| `tone_keyword_counts["external_doc_first"]` 가 작지 않음 | "작업서·스펙 문서 박고 시작" 류 |
| `tone_keyword_counts["trace_chain_logs"]` 가 작지 않음 | "trace id 로 여러 앱 로그 잇고 가설 세워 검증하기" 류 (한 서비스 로그만 보지 않고 호출 흐름 전체를 이어 붙임) |
| `meaningful_markers["session_continue_episodes"]` 가 작지 않음 | "끊긴 자리에서 그대로 이어가기" 류 (컨텍스트 리셋 후 작업 재개) |
| `meaningful_markers["multi_interrupt_episodes"]` 가 작지 않음 | "안 맞으면 인터럽트로 방향 정정" 류 |
| `meaningful_markers["background_task_notification_episodes"]` 가 작지 않음 | "백그라운드로 던지고 알림으로 받기" 류 |
| `meaningful_markers["context_compact_episodes"]` 가 작지 않음 | "/compact 로 컨텍스트 정리 후 진행" 류 |
| `meaningful_markers["teammate_message_episodes"]` 가 작지 않음 | "별도 창 동료 AI 호출" 류 (역할 명시 가능) |

판정 기준:
- 단일 신호 하나만으로 패턴 문장 만들지 말 것. 신호 + 대표 에피소드의 실제 turn 흐름이 일치해야 패턴으로 채택.
- 신호는 있는데 실제 turn 시퀀스가 다양하게 갈리면 → 패턴 후보 폐기 (1회성 우연).

### 입력 형태별 분리 가드

"외부 출력을 첫 메시지로 던진다" 류 패턴은 **본문 형태에 따라 별도 패턴**으로 나눠 추출한다. 한 패턴으로 묶지 말 것 — 본문 형태가 다르면 사용자 발화의 모양이 다른데 한 흐름인 양 흐려진다.

분리 기준은 **본문의 종류 그 자체** (SQL · 셸·빌드 출력 · 스택트레이스 · 다른 형태) 이며, 카테고리를 명세에 미리 박아 두지 않는다. **대표 에피소드의 실제 본문을 보고 어떤 종류가 반복되는지 그 자리에서 분리**한다. 신호가 약한 종류는 후보 폐기.

> **참고 사례** (이전 분석에서 잡힌 본문 종류 예시 — 검출 룰 X, 본인 데이터 케이스):
> SQL 본문/결과, gradlew/npm/terraform/docker 같은 빌드·셸 명령 출력, 스택 트레이스/컴파일 에러 전문, PR/리뷰 코멘트 본문 등이 분리돼 나타날 수 있다. 단, **이 목록은 닫힌 카테고리가 아니다**. 다른 직군 (PM/QA/오퍼레이션) 의 데이터에서는 전혀 다른 본문 종류가 잡힐 수 있다. 명세는 카테고리를 강제하지 않고, 데이터를 보고 추출한다.

---

## 2.5 개인 로컬 셋업 섹션

`aggregated.json` 의 `local_setup` 키에 자동 수집된 데이터가 들어 있으면, 보고서 끝에 **`## 개인 로컬 셋업`** 섹션을 만든다. 다른 사람과 공유 안 하는 `~/.claude/` 의 개인 설정들을 자연어로 풀어 쓴다.

### 목적

이 보고서를 받는 동료가 본인의 환경에도 적용해볼 만한 설정을 발견할 수 있도록 한다. **수치/목록 나열이 아니라 "왜 이걸 깔아 뒀는지" 가 보이는 설명 톤**.

### 데이터 소스

`local_setup` 키 안에 다음 6가지:
- `mcp_servers`: 개인 MCP 서버 (이름·타입·env 키만, 시크릿 마스킹)
- `personal_claude_md`: `~/.claude/CLAUDE.md` (섹션 헤더만, 전문 노출 X)
- `plugins`: 설치된 플러그인 (회사 내부 vs 공개 구분)
- `skills`: `~/.claude/skills/` 의 개인 스킬 (이름 + description)
- `slash_commands`: `~/.claude/commands/` 의 사용자 정의 슬래시 커맨드
- `settings`: `~/.claude/settings.json` 요약 (hooks/statusline/toggle 등)

### 섹션 구조

```markdown
## 개인 로컬 셋업

[한 문단 개요 — 어떤 셋업으로 일하고 있는지 친구에게 소개하듯]

### 개인 MCP 서버

[자주 호출하는 외부 시스템을 MCP 서버로 묶어 두는 흐름]
- **이름** — 무엇에 쓰는지 한 줄
- ...

### 개인 CLAUDE.md 관습

[어떤 원칙을 적어 두고 모든 작업에 자동 적용시키는지]
- ...

### 개인 skill · plugin · 슬래시 커맨드

[자주 반복되는 절차를 자동화한 묶음]
- **이름** — 무엇을 하는지
- ...

### 개인 hooks · statusline · 그 외 설정

[작업 흐름을 보조하기 위한 자잘한 토글]
- ...
```

### 규칙

- **자연어 설명 톤** — "MCP 서버 8개를 깔아 뒀다" 같은 수치 나열 X. "운영 로그와 DB 를 한 흐름에서 묻기 위해 ... 를 깔아 둔다" 식으로
- **회사 내부 플러그인은 그대로 노출 OK** (사내 공유 전용) — 단 시크릿은 마스킹
- **개인 식별자 (userID, 홈 경로) 는 자동 마스킹** — masker 모듈이 처리
- **수치는 정성 표현으로**: "8개" → "여러 개", "5개 권한" → "몇 개 권한"
- **설치된 게 0개인 카테고리는 sub-section 생략** (예: 개인 skill 없으면 그 sub-section 안 만들기)
- **시스템 내부 라벨 / Claude Code 도구 내부명 노출 X** (다른 본문과 동일 룰 적용)

### 좋은 예시 (개인 MCP sub-section)

```markdown
### 개인 MCP 서버

자주 묻는 외부 시스템을 MCP 서버로 묶어 두고 코딩 에이전트가 직접 호출하게 한다. 운영 로그를 보는 datadog, DB 쿼리용 datagrip, 이슈/PR 을 묻는 atlassian·github, 별도 사고용 gemini-cli 까지 함께 깔아 두면 한 흐름 안에서 외부 도구를 갈아 끼우게 시킬 수 있다.

- **datadog** — 운영 로그·trace 를 코드 작업 중간에 묻기 위해
- **datagrip** — alpha/prod DB 를 쿼리로 즉시 두드려 보기 위해
- **github · atlassian** — PR 이력·이슈 컨텍스트를 본 흐름에 끌어오기 위해
- **gemini-cli** — 같은 문제에 다른 모델의 시각을 한 번 더 받기 위해
- (회사 내부) **mcp-server-mysql-wms-alpha**, **mcp-server-mysql-logistics-auth-alpha** — 회사 alpha DB 직접 쿼리용
```

### 나쁜 예시

```markdown
### 개인 MCP 서버

총 8개의 MCP 서버가 설정되어 있다:
1. mcp-atlassian (type: undefined)
2. github (type: undefined)
3. mcp-server-mysql-wms-alpha (type: undefined)
...
```
문제: 수치 나열, "왜 깔아 뒀는지" 안 보임, 시스템 필드 (type: undefined) 노출.

---

## 3. 느슨한 그룹화

### 패턴 추출 모드

**디폴트 (광역 모드)** — 사소한 패턴까지 다 후보로. 상한 없음.

- 사용자가 보고서를 받아 첨삭하는 운영 모델
- 패턴 수 상한 없음 (30개, 50개도 OK)
- 1회성·도메인 특화도 추상화 시도 후 살아남으면 유지

**`--curated` 모드** — 동료에게 직접 공유할 때만 사용자가 명시.

- 전체 5-8개, 그룹당 1-3개 제한
- 1회성·도메인 특화 폐기
- 메서드러지로 단단히 굳은 것만 유지

### 그룹화 판정 (양 모드 공통)

```
- 추출된 패턴들을 보고 "비슷한 메서드러지끼리 묶을 수 있나? 강제 X" 질문
- 자연스러운 그룹이 3개 이상 보이면 → 그룹화
- 자연스러운 그룹이 없거나 모호하면 → 평탄 (그냥 나열)
- 광역 모드에서 패턴 수가 많으면 평탄 출력이 디폴트가 됨 (그룹화 무리 X)
```

### 그룹화 기준

```
- 그룹당 최소 2개 패턴
- 그룹은 3개 이상 형성될 때만 사용
- 한 패턴이 두 그룹에 걸치면 그룹화 안 함 (모호)
- 그룹명은 추상적이지만 명확해야 함
```

### 그룹화된 출력

```markdown
## 주요 워크플로 패턴

### A. 정보 우선 (본격 작업 전 사실 데이터부터 확보)

#### 에러나 이상 신호가 보이면 관련 로그를 통째로 수집한 뒤 분석을 시작한다
[본문...]

#### 에러 디버깅 전 관련 기능의 정상 동작 설명을 먼저 만든다
[본문...]

### B. 도구 체이닝 (식별자로 도구 잇기)

#### 도구 간 식별자를 매개로 체이닝한다
[본문...]
```

### 평탄 출력

```markdown
## 주요 워크플로 패턴

### 에러나 이상 신호가 보이면 관련 로그를 통째로 수집한 뒤 분석을 시작한다
[본문...]

### 도구 간 식별자를 매개로 체이닝한다
[본문...]
```

---

## 4. 도구 표기 룰

### 도구 분류

```
1. 일반 공개 도구: public_tools_whitelist.yaml에 있는 도구
   → 이름 유지 + 첫 등장 시 인라인 괄호

2. 회사 내부 시스템: 사내 공유라 그대로 노출
   → 마스킹 안 함

3. 시크릿: secret_patterns.yaml의 정규식 매칭
   → 항상 마스킹 (사용자 옵션 X)

4. 동료 이름: 사용자 입력 names + 자동 발견 names
   → 디폴트 마스킹 (사용자 끌 수 있음)
```

### 인라인 괄호 표기 룰

```
1. 첫 등장 시: "도구명(짧은 기능 설명)"
   예: "grafana mcp(로그 검색 도구)"
   
2. 두 번째 등장부터: 도구명만
   예: "grafana mcp"

3. 한 패턴 안에서만 카운트
   다른 패턴에선 다시 "첫 등장"으로 처리
   이유: 사용자가 패턴 단위로 읽음

4. 기능 설명은 기능 그룹 이름 기반
   log_search → "로그 검색 도구"
   trace_view → "분산 trace 분석 도구"
   issue_tracker → "이슈 트래커"
   docs → "문서 협업 도구"
   ...
```

---

## 5. 마스킹 자동 검증

LLM이 보고서 생성 후 후처리로 자동 검증:

### 검증 4가지

```python
def validate_report(report_md, config):
    issues = []
    
    # 1. 시크릿 검출 (항상 ON, CRITICAL)
    for pattern in SECRET_PATTERNS:
        if re.search(pattern, report_md):
            issues.append({
                "level": "CRITICAL",
                "type": "secret_leak",
                "action": "차단. LLM 재호출. 재시도 후에도 남으면 보고서 폐기"
            })
    
    # 2. 동료 이름 검출 (옵션 ON일 때만, WARN)
    if config.mask_people_names:
        for name in config.people_names:
            if name in report_md:
                issues.append({
                    "level": "WARN",
                    "type": "people_name_leak",
                    "action": "자동 치환: 이름 → '동료'"
                })
    
    # 3. 일반 도구 첫 등장 시 인라인 괄호 누락 (WARN)
    for tool in find_public_tools(report_md):
        first_mention = find_first_mention(tool, report_md)
        if not has_inline_paren_after(tool, first_mention):
            issues.append({
                "level": "WARN",
                "type": "missing_function_description",
                "action": "자동 보완: yaml에서 기능명 가져와 괄호 추가"
            })

    # 4. 사용 예시 블록의 회사 시스템명 검출 (WARN)
    # 본문엔 회사 시스템명 OK 지만 사용 예시 블록은 도메인 무관해야 함.
    # `**사용 예시 ...:**` 다음 코드 블록만 스캔.
    for example_block in find_example_blocks(report_md):
        for token in scan_company_system_tokens(example_block, config):
            issues.append({
                "level": "WARN",
                "type": "company_system_in_example",
                "token": token,
                "action": "Stage D 재생성 요청 (사용 예시는 일반 도메인으로)",
            })

    return issues
```

### 사용 예시 블록의 회사 시스템명 검출 룰

`scan_company_system_tokens` 가 검출하는 패턴:

- **확장자 없는 카멜케이스 + 회사 접속어**: `wms-*`, `oms-*`, `*-api`, `*-svc`, `*-internal` 류
- **사용자 config 의 `tool_function_mapping` 키 중 사내 도구로 분류된 이름**: 예 `mcp__plugin_logistics-plugin_grafana-prod__*` 같은 사내 플러그인
- **public_tools_whitelist.yaml 에 없는 도메인 명사가 사용 예시 블록 안에 등장**

판정이 모호하면 WARN 만 띄우고 보고서는 그대로 통과. (CRITICAL 아님)

### 신규 yaml: `config/company_system_hints.yaml` (옵션)

자동 검출의 false positive 를 줄이고 싶을 때 사용자가 명시적으로 추가 가능:

```yaml
# config/company_system_hints.yaml (옵션 — 없으면 룰만 적용)
company_system_substrings:
  - wms
  - oms
  - logistics
  # 회사 도메인 시스템의 짧은 식별자 (선택)
```

룰: 사용 예시 블록 안에 이 substring 이 포함되면 WARN. 본문은 영향 없음.

### 처리

| 레벨 | 종류 | 처리 |
|---|---|---|
| CRITICAL | 시크릿 누출 | LLM 재호출 → 재시도 후에도 남으면 **보고서 폐기 + 사용자 알림** |
| WARN | 동료 이름 | 자동 치환 (이름 → "동료") |
| WARN | 괄호 누락 | 자동 보완 (yaml에서 기능명 가져와 추가) |
| WARN | 사용 예시에 회사 시스템명 | Stage D 재요청 (해당 패턴의 사용 예시만 일반 도메인으로 재생성). 재시도 후에도 남으면 그대로 두되 사용자에게 한 줄 안내. |
| WARN | 본문에 시스템 내부 라벨 등장 (outcome/phase/git_intent 등 금지어) | Stage D 재요청 (해당 패턴 본문만 일반 어휘로 재작성). |
| WARN | 본문에 Claude Code 도구 내부명 (Bash/Edit/Read/Grep/Task 등) 그대로 노출 | Stage D 재요청. 일반 동사로 풀어쓰기. |
| WARN | 사용 예시 블록이 AI 실행 시퀀스 형태 (도구 호출/명령 실행 서술) | Stage D 재요청. 사용자 발화·프롬프트 시퀀스로 재작성 ("grafana mcp 로 5xx 조회" → "5xx 떨어지는데 로그 봐줘"). |

### 시크릿 누출 시 사용자 알림

```
⚠️ 보고서 생성 중 시크릿으로 의심되는 패턴이 검출됐습니다.
   재시도했지만 여전히 남아있어 보고서를 폐기했습니다.
   
   검출된 패턴: API_KEY 패턴 (위치: 23번 turn)
   원본 데이터 확인: ~/.claude/projects/abc/session-xyz.jsonl
   
   조치:
   - 해당 turn에 시크릿이 있는지 직접 확인
   - secret_patterns.yaml 에 추가 패턴 등록 가능
```

---

## 6. 기간 길이에 따른 분기

### 시계열 섹션 포함 여부

```python
def should_include_timeseries_section(period_days):
    return period_days >= 14  # 2주 이상일 때만
```

### 단위 자동 결정

| 기간 | 단위 | 형식 |
|---|---|---|
| 2-4주 | 주 단위 | "W17 (4-20~4-26): ..." |
| 1-3개월 | 주 단위 | "W17: ... W18: ..." |
| 3개월+ | 월 단위 | "2026-04: ... 2026-05: ..." |

### 시계열 섹션 내용

각 단위마다:
- 그 기간의 주된 작업 성격 (1-2문장)
- 자주 쓴 기능 그룹 1-2개
- 주요 에피소드 수

```markdown
## 시계열 추이

### W17 (2026-04-20 ~ 2026-04-26)
주로 프로덕션 디버깅. log_search 기능 빈도 높음.
주요 에피소드 3개

### W18 (2026-04-27 ~ 2026-05-03)
신규 기능 개발 중심으로 전환. file_edit 비중 증가.
주요 에피소드 5개
```

이건 별도 LLM 호출 없이 메인 보고서 생성 시 같이 만듦.

---

## 7. Stage D 동작 (LLM 호출)

### 입력

```python
inputs = {
    "period_meta": {
        "start": "2026-04-20",
        "end": "2026-05-17",
        "session_count": 47,
        "episode_count": 23,
    },
    "episodes": [...],          # Stage B 출력
    "aggregated": {...},        # Stage C 출력 (집계)
    "config": {
        "mask_people_names": True,
        "people_names": ["코비", "..."],
    },
}
```

### LLM 호출 (Opus, 1회)

프롬프트 구성:
1. 시스템: 역할 + 형식 명세 + 룰
2. 사용자: 입력 데이터 + 출력 요청

핵심 지시 사항:
- Format C 명세대로 보고서 생성
- 도구 표기 룰 적용
- 회사 시스템명은 그대로, 동료 이름은 추상화
- 시계열 섹션 (기간 ≥ 2주)
- 느슨한 그룹화 판정

### 후처리

```python
def post_process(llm_output, config):
    # 1. 검증
    issues = validate_report(llm_output, config)
    
    # 2. CRITICAL 처리
    critical = [i for i in issues if i["level"] == "CRITICAL"]
    if critical:
        # 재호출 (1회만)
        llm_output = retry_with_warning(critical)
        issues = validate_report(llm_output, config)
        critical = [i for i in issues if i["level"] == "CRITICAL"]
        if critical:
            return None, "보고서 폐기. 사용자 알림."
    
    # 3. WARN 자동 보완
    for issue in issues:
        if issue["type"] == "people_name_leak":
            llm_output = replace_name(llm_output, issue, "동료")
        elif issue["type"] == "missing_function_description":
            llm_output = add_paren(llm_output, issue)
    
    return llm_output, None
```

---

## 8. 출력 파일

### 파일명

```
{start}_to_{end}.md

예:
2026-04-20_to_2026-05-17.md
2026-05-12_to_2026-05-18.md
```

### 위치

```
~/Documents/claude-usage-reports/
└── 2026-04-20_to_2026-05-17.md
```

---

## 셀프 체크 통과 사항

**약속 1 (튜닝 X)**: 출력 형식은 사용자 무관. 본인 데이터 보고 만든 룰 아님.

**약속 2 (코드에 박지 마)**: 기능 그룹 이름 → 기능 설명 문구 매핑은 yaml. 
시크릿 패턴, 동료 이름 자동 발견 룰도 yaml.

**약속 3 (다른 사람 검증 강제 X)**: 사용자는 보고서만 받음. 검증은 시스템이 자동.

**약속 4 (보고서 정합성)**: 사내 공유 전용으로 합의됨. 회사 시스템명 노출 OK, 
시크릿/동료 이름 마스킹.

**약속 5 (셀프 체크 4질문)**: 형식 자체가 사용자/직군 무관 → OK.

---

## 다음 단계

- 5단계: Stage C 가벼운 명세 (집계 단계)
- 6단계: Pipeline + Install 명세 (CLI 인자, 첫 실행 흐름)
- 7단계: 본인 데이터로 PASS/FAIL 검증
- 8단계: 베타 사용자 적용
