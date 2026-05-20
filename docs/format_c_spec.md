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
```

### 규칙

- 도구 이름은 일반 공개 도구만 표기. 회사 내부 시스템명은 그대로 노출 (사내 공유 전용)
- 일반 공개 도구 첫 등장 시 인라인 괄호로 기능 설명: `grafana mcp(로그 검색 도구)`
- 같은 패턴 안에서 같은 도구 두 번째부터는 도구명만
- 빈도/통계 표시 X
- 별도 필드 (왜, 변형, 예시 등) X — 본문 안에 자연스럽게 녹임

### 예시

```markdown
## 에러나 이상 신호가 보이면 관련 로그를 통째로 수집한 뒤 분석을 시작한다

운영 환경에서 에러나 특이사항이 발생하면 코드부터 보지 않고, 먼저 
**grafana mcp(로그 검색 도구)**에서 관련 access log 키를 주고 한 번에 
끌어와 전체를 훑은 뒤 본 작업에 들어간다. 가설을 좁힌 상태에서 코드를 
보기 때문에 무관한 path를 헤매지 않게 됨.

## 도구 간 식별자를 매개로 체이닝한다

한 도구의 결과에 들어있는 식별자를 추출해 다음 도구의 입력으로 넣는 
방식으로 도구를 잇는다. 예: **grafana mcp(로그 검색)**에서 dd.trace_id를 
뽑아 **datadog mcp(분산 trace 분석 도구)**로 연결. 단일 도구만으로는 
답이 안 나오는 문제를 식별자 한 줄로 깊이 분석할 수 있음.
```

---

## 3. 느슨한 그룹화

### 판정 규칙

```
- 패턴 5-8개 추출됨
- LLM에게 "비슷한 메서드러지끼리 묶을 수 있나? 강제 X" 질문
- 자연스러운 그룹이 3개 이상 보이면 → 그룹화
- 자연스러운 그룹이 없거나 모호하면 → 평탄 (그냥 나열)
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

### 검증 3가지

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
    
    return issues
```

### 처리

| 레벨 | 종류 | 처리 |
|---|---|---|
| CRITICAL | 시크릿 누출 | LLM 재호출 → 재시도 후에도 남으면 **보고서 폐기 + 사용자 알림** |
| WARN | 동료 이름 | 자동 치환 (이름 → "동료") |
| WARN | 괄호 누락 | 자동 보완 (yaml에서 기능명 가져와 추가) |

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
