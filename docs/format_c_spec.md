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

## 참고

이 보고서는 자동 생성됨. 
의심스러운 내용 있으면 raw 데이터 확인: ~/.claude/projects/
의견/오류 신고: [...]
```

---

## 2. 패턴 한 개 형식

```markdown
## [한 문장 제목 — 상황 + 행동]

[1-3문장 본문.
 첫 문장: 상황 + 행동 시퀀스
 (선택) 중간 문장: 구체 예시 또는 변형
 마지막 문장: 효과/이유를 자연스럽게 (별도 "왜" 라벨 X)]

**사용 예시 ([도메인 라벨]):**
```
1. [첫 단계 — 도구 + 짧은 쿼리/명령]
2. [두 번째 단계]
3. [세 번째 단계]
...
```
```

### 규칙

- 도구 이름은 일반 공개 도구만 표기. 회사 내부 시스템명은 본문엔 그대로 노출 (사내 공유 전용)
- 일반 공개 도구 첫 등장 시 인라인 괄호로 기능 설명: `grafana mcp(로그 검색 도구)`
- 같은 패턴 안에서 같은 도구 두 번째부터는 도구명만
- 빈도/통계 표시 X
- 별도 필드 (왜, 변형 등) X — 본문 안에 자연스럽게 녹임
- **사용 예시 블록은 모든 패턴에 필수**. 본문 직후 코드 블록으로 단계 1-2-3-4 형태

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

### 사용 예시 블록 규칙

목적: 본문이 줄글이라 다른 직군 동료가 자기 도구로 치환하기 어려울 때, **단계 시퀀스 형태로** 즉시 이해 가능하게.

- **도메인은 다음 4가지 중에서만 선택**:
  1. **REST API / 디버깅** — user-api, order-api 같은 일반 서비스 이름. 5xx, trace_id, latency 등
  2. **인증 / 토큰** — JWT 만료, OAuth, refresh token, session 등
  3. **캐시 / DB** — Redis cache miss, MySQL slow query, connection pool 등
  4. **Git / 테스트 / 빌드** — git log/bisect, npm test, gradle build, Docker 등

- **도메인 라벨을 블록 헤더에 명시**: `**사용 예시 (REST API 서버 디버깅):**` 형태로
- **회사 내부 시스템명 절대 금지**: WMS, OMS, wms-api, logistics-auth, kakaostyle 등 본인 데이터에 보이는 회사명은 예시에 안 들어감
- **사내 슬래시 스킬 이름 금지**: `/plan-reviewer:review-plan` 같은 사내 플러그인은 예시에 안 들어감 (본문엔 OK)
- **명령/쿼리는 일반적 형태로**: `service:"user-api"`, `status:>=500`, `git log -- src/auth.py` 등 누구나 인식 가능한 패턴
- **3-6 단계**: 너무 짧으면 의미 없고 너무 길면 산만

### 좋은 예시 / 나쁜 예시

좋음:
```
**사용 예시 (REST API 서버 디버깅):**
1. grafana mcp(로그 검색 도구) 에서 5xx 에러 조회
   query: status:>=500 service:"user-api"
2. 응답 느린 user_id 추출
3. 같은 trace_id 로 인증 서비스 로그 이어 조회
4. 코드 경로 확인 시작
```

나쁨 (회사 시스템명 노출):
```
**사용 예시:**
1. grafana 로 wms-api 의 5xx 조회   ← wms-api 는 회사 시스템명
2. SubmitFCWorkerPackingOutbound 호출 추적   ← 회사 메서드명
```

나쁨 (도메인 모호):
```
**사용 예시:**
1. 도구로 데이터 가져오기   ← 어떤 도메인인지 불명, 단계가 추상적
2. 가설 좁히기
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
1. grafana mcp(로그 검색 도구) 에서 5xx 에러 조회
   query: status:>=500 service:"user-api"
2. 응답 느린 user_id 추출
3. 같은 trace_id 로 인증 서비스 로그 이어 조회
4. 코드 경로 확인 시작
```

## 도구 간 식별자를 매개로 체이닝한다

한 도구의 결과에 들어있는 식별자를 추출해 다음 도구의 입력으로 넣는
방식으로 도구를 잇는다. 단일 도구만으로는 답이 안 나오는 문제를 식별자
한 줄로 깊이 분석할 수 있음.

**사용 예시 (인증 / 토큰):**
```
1. grafana mcp(로그 검색 도구) 에서 토큰 검증 실패 로그 조회
   query: msg:"jwt expired" service:"auth"
2. 결과에서 user_id 와 token_id 추출
3. mysql mcp(DB 쿼리 도구) 로 같은 user_id 의 refresh token 만료 시각 조회
   select expires_at from refresh_tokens where user_id = ...
4. 만료 시각과 실패 시각 비교
```

## 변경을 마쳤으면 데이터로 결과를 다시 확인한 뒤 보고만 받는다

코드 수정이 끝나면 같은 컨텍스트에서 곧장 **mysql mcp(DB 쿼리 도구)**로
관련 테스트 데이터를 다시 꺼내거나, 앱 실행과 검증 절차를 한 번에 위임해
최종 결과 요약만 받는다. 종료부에서 데이터로 한 번 더 확인하기 때문에
본인 가설이 틀렸을 때 그 자리에서 잡힌다.

**사용 예시 (캐시 / DB):**
```
1. Edit 으로 cache TTL 조정 코드 변경
2. Bash 로 단위 테스트 실행 (jest / pytest)
3. mysql mcp 로 변경 전후 cache hit ratio 비교
   select hit_count, miss_count from cache_metrics where window = ...
4. 결과 요약만 보고받고 다음 작업으로
```

## 현상만 보지 않고 언제부터 다르게 동작했는지를 git 으로 거슬러 올라간다

문제 상황을 처음 만났을 때 현재 로그·코드만 보는 대신 `git log` / `git blame` /
`git bisect` 로 정상이었던 시점을 찾아 그 사이의 변경 폭으로 좁힌다. 시간축으로
한 번 자르고 들어가면 검토할 코드 범위가 크게 줄어든다.

**사용 예시 (Git / 회귀 추적):**
```
1. git log -- src/auth/jwt.py 로 최근 변경 커밋 후보 확인
2. git show <commit> --stat 으로 변경 폭 한 번에 보기
3. 의심 커밋 직전 시점으로 git checkout 해서 동작 재현
4. 정상 / 비정상 시점 사이의 diff 만 좁혀서 본격 분석
```

## 작업 도중 단계마다 commit 으로 끊어 가며 진행한다

큰 변경을 한 덩어리로 끌고 가지 않고, 단위 변경이 일단락될 때마다 짧은 메시지로
commit 을 만들어 두고 다음으로 넘어간다. 나중에 PR 을 만들 때도 변경의 흐름이
이미 잘게 쪼개져 있어 설명할 거리가 적어진다.

**사용 예시 (Git / 테스트):**
```
1. 모델 클래스 정의 → git commit -m "add User model"
2. 핸들러 추가 → git commit -m "add /users endpoint"
3. 단위 테스트 작성 → git commit -m "add user handler tests"
4. PR 생성 시 위 3개 커밋이 그대로 변경 단위가 됨
```

## PR 본문을 요약·테스트 계획 섹션으로 구조화해 만든다

PR 을 만들 때 단순 한 줄 설명이 아니라 변경 요약, 테스트 계획 같은 섹션을 갖춘
본문을 함께 작성한다. 리뷰어가 변경 의도와 검증 범위를 같은 문서에서 한 번에
파악할 수 있어 리뷰 라운드가 줄어든다.

**사용 예시 (Git / PR):**
```
1. 변경 완료 → gh pr create --title "..." --body "..."
2. body 안에 ## Summary / ## Test plan 섹션 명시
3. Test plan 은 체크리스트로:
   - [ ] unit tests
   - [ ] manual test: POST /api/users with invalid email
4. 리뷰어가 한 문서에서 의도 + 검증 범위 다 확인
```

## 복잡한 결정엔 본 컨텍스트와 분리된 별도 에이전트로 사고를 요청한다

본인이 이미 한 방향으로 기울었을 때 별도 에이전트를 띄워 같은 문제를 다시
검토하게 한다. 새 컨텍스트는 본 컨텍스트의 편향에서 자유롭기 때문에 이중 점검의
역할로 쓰인다.

**사용 예시 (REST API / 설계 결정):**
```
1. 본 컨텍스트에서 API 설계안 v1 작성
2. Agent(서브 에이전트) 호출:
   "이 설계의 약점이 뭔지 처음 보는 시각으로 검토해줘"
3. fresh agent 의 검토 결과만 요약으로 받기
4. 본 컨텍스트에서 검토 결과 반영해 v2 작성
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

판정 기준:
- 단일 신호 하나만으로 패턴 문장 만들지 말 것. 신호 + 대표 에피소드의 실제 turn 흐름이 일치해야 패턴으로 채택.
- 신호는 있는데 실제 turn 시퀀스가 다양하게 갈리면 → 패턴 후보 폐기 (1회성 우연).

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
