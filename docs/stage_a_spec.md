# Stage A 설계 명세

## 역할

```
입력:  ~/.claude/projects/<encoded-cwd>/<session>.jsonl
       (Claude Code가 자동 생성하는 raw 대화 기록)

처리:  1. JSONL 파싱 → 정규화된 turn 객체로 변환
       2. tool_result 본문 절사 (carve-out)
       3. 마스킹 (시크릿 즉시 / 회사 정보는 Stage D에서)

출력:  turns.parquet
       (Stage B의 입력)
```

Stage A의 책임은 **"raw 대화를 분석 가능한 turn 시퀀스로 만들기"**. 
분석은 하지 않음, 정리만 함.

---

## 작업 1: 도구 → 기능 매핑

### 기능 그룹 (17개, 확장 가능)

```
[정보 검색·조회]
log_search       — 로그 검색 (grafana, datadog logs, splunk, loki, ...)
trace_view       — 분산 trace (datadog APM, honeycomb, jaeger, ...)
metric_query     — 메트릭 조회 (prometheus, datadog metrics, ...)
db_query         — DB 쿼리 (MySQL, BigQuery, Postgres MCP, ...)
code_search      — 코드 검색 (Grep, ripgrep, ...)
web              — 웹 검색/조회 (WebFetch, WebSearch)

[작업 관리·협업]
issue_tracker    — 이슈 트래커 (JIRA, Linear, GitHub Issues, ...)
chat             — 채팅 (Slack, Discord, Teams MCP, ...)
docs             — 문서 협업 (Confluence, Notion, Google Docs MCP, ...)

[파일·코드 조작]
file_read        — 파일 읽기 (Read)
file_edit        — 파일 편집 (Edit, Write)
shell_exec       — 셸 실행 (Bash)

[자동화·외부 조작]
browser          — 브라우저 (Chrome MCP, Playwright)
design_tool      — 디자인 도구 (Figma MCP)
ide              — IDE 연동 (VSCode, JetBrains MCP)

[기타]
agent            — 서브 에이전트 / Task 도구
other            — 위에 없는 도구 (fallback)
```

새 기능 그룹은 자유롭게 추가/수정 가능. 코드 변경 필요 (yaml 분리는 추후).

### 도구 → 기능 매핑 알고리즘

**방법 B: LLM 1회 분류 + 사용자 1회 확인 + 캐시**

```python
def build_tool_function_map(user_data, cached_map):
    # 1. 사용자 데이터에서 unique 도구 이름 수집
    all_tools = collect_unique_tools(user_data)
    
    # 2. 캐시에 없는 새 도구만 추출
    new_tools = [t for t in all_tools if t not in cached_map]
    
    if not new_tools:
        return cached_map  # 모두 캐시됨
    
    # 3. LLM에 한 번에 분류 요청
    llm_classification = haiku.classify_tools(new_tools, FUNCTION_GROUPS)
    
    # 4. 사용자에게 확인 (첫 실행 또는 새 도구 발견 시)
    confirmed = prompt_user_to_confirm(llm_classification)
    
    # 5. 캐시 업데이트
    cached_map.update(confirmed)
    save_cache(cached_map)
    
    return cached_map
```

사용자 확인 인터페이스:
```
이번에 분석할 데이터에서 다음 도구들을 발견했습니다.
자동 분류 결과 확인해주세요:

  grafana_query_logs        → log_search ✓
  atlassian_jira_search     → issue_tracker ✓
  atlassian_confluence_get  → docs ✓
  custom_mcp_xyz            → other (분류 실패, 직접 지정?)

[Enter로 확정 / e로 수정]
```

---

## 작업 2: 기능 그룹별 carve-out 룰

본문이 너무 크니까 분석에 필요한 부분만 남김. 그룹별 룰:

```yaml
log_search:
  rationale: "어떤 검색 쿼리에 어떤 로그가 매칭됐는지가 핵심"
  rule: "첫 3개 로그 entry + 총 개수 + 검색 쿼리"
  
trace_view:
  rationale: "trace 한 건의 span 구조가 핵심"
  rule: "첫 1 trace의 span tree 요약 + 총 개수"

metric_query:
  rationale: "메트릭 이름/태그/시간 윈도우가 핵심"
  rule: "쿼리 식 + 첫 5개 데이터 포인트 + 총 개수"

db_query:
  rationale: "쿼리문이 핵심, 결과 행은 첫 몇 개만"
  rule: "SQL + 첫 5행 + 총 행 수 + 컬럼명"

code_search:
  rationale: "어떤 패턴 검색했고 어디서 매칭됐는지"
  rule: "검색 패턴 + 매칭된 첫 10라인 (파일:줄:내용)"

web:
  rule:
    - web_search: "쿼리 + 첫 5개 결과 (제목+URL+짧은 스니펫)"
    - web_fetch:  "URL + 페이지 시작 400자 + 끝 200자"

issue_tracker:
  rule: "ID + 제목 + 상태 + 담당자 + 본문 첫 300자"

chat:
  rule: "메시지 첫 5개 (작성자+시간+본문 200자) + 채널명"

docs:
  rule: "제목 + 헤더 리스트 (h1, h2만) + 첫 단락 300자"

file_read:
  rule:
    - if total_lines <= 80: "전문 유지"
    - else: "import/export + 시그니처 + notable 라인 (TODO, FIXME)"

file_edit:
  rule:
    - edit: "old_str 첫 200자 + new_str 첫 200자 + 파일 경로"
    - write: "파일 경로 + 내용 첫 300자 + 끝 100자"

shell_exec:
  rule: "작업 3 (출력 유형 분류)로 위임"

browser:
  rule: "현재 URL + 액션 종류 + 페이지 제목"

design_tool:
  rule: "객체 ID + 객체 타입 + 변경 요약 200자"

ide:
  rule: "파일 + 위치 + 액션 종류"

agent:
  rule: "task description 첫 400자 + result 끝 400자"

other:
  rule: "tool_name + arguments 요약 + result 첫 400자 + 끝 200자"
```

**숫자(3, 10, 300, 80 등)는 고정값**으로 박음. 5단계 검증 결과 보고 동적 조정 도입 여부 재평가.

---

## 작업 3: 기본 도구 출력 유형 분류 (Bash, Read)

기본 도구는 용도가 다양해서 기능 그룹 1개로 못 묶음. 출력 유형 5가지로 분류:

```yaml
list_like:
  description: "라인 단위로 의미 있는 결과"
  examples: "grep, find, ls, ps"
  detection: 
    - 라인 수 > 5
    - 라인들이 비슷한 패턴 (path:N:content 등)
  rule: "첫 10라인 + 총 라인 수"

execution_like:
  description: "명령 실행 결과, exit_code 의미 있음"
  examples: "build, test, deploy, install, npm/yarn/pnpm"
  detection:
    - tool_use_input에 build/test/install/deploy 키워드 (yaml 분리)
    - exit_code 존재 + non-zero 가능
    - stderr 존재
  rule: "exit_code + 명령어 + stdout 끝 30라인 + stderr 끝 10라인"

document_like:
  description: "길게 이어지는 텍스트, 구조 있음"
  examples: "README, 긴 코드, 문서"
  detection:
    - 라인 수 > 80
    - 들여쓰기/헤더 구조 존재
  rule:
    - if total_lines <= 80: "전문 유지"
    - else: "헤더 + 시그니처 + notable 라인"

short_output:
  description: "짧은 출력, 전체 보존 가능"
  examples: "echo, date, whoami"
  detection: 
    - 라인 수 <= 5
    - 글자 수 <= 400
  rule: "전문 유지"

structured_data:
  description: "JSON, YAML, XML 등 구조화 데이터"
  examples: "curl 결과, API 응답"
  detection:
    - JSON/YAML 파싱 가능
    - 첫 글자 { 또는 [
  rule: "최상위 키 리스트 + 첫 3개 항목 + 총 항목 수"
```

### 판정 알고리즘

```python
def classify_output(tool_name, tool_input, tool_output):
    # 1. 도구별 힌트 (yaml: execution_keywords)
    if tool_name == "Bash":
        cmd = tool_input.get("command", "")
        if any(kw in cmd for kw in EXECUTION_KEYWORDS):
            return "execution_like"
    
    # 2. 출력 자체 분석 (도구 무관)
    if len(tool_output) <= 400 and tool_output.count("\n") <= 5:
        return "short_output"
    
    if tool_output.strip().startswith(("{", "[")):
        try:
            json.loads(tool_output)
            return "structured_data"
        except: pass
    
    lines = tool_output.split("\n")
    
    if is_list_like_pattern(lines):
        return "list_like"
    
    if len(lines) > 80 or has_structural_markers(tool_output):
        return "document_like"
    
    return "document_like"  # fallback
```

EXECUTION_KEYWORDS (yaml 분리):
```yaml
execution_keywords:
  - build
  - test
  - install
  - deploy
  - npm
  - yarn
  - pnpm
  - make
  - cargo
  - go build
  - go test
  - mvn
  - gradle
  - python -m pytest
  # 확장 가능
```

---

## 작업 4: 마스킹

### 4-1. 자동 마스킹 (시크릿, 사용자 무관)

```yaml
# config/secret_patterns.yaml
secret_patterns:
  - name: "AWS Access Key"
    pattern: "AKIA[0-9A-Z]{16}"
  - name: "AWS Secret Key"  
    pattern: "[a-zA-Z0-9+/]{40}"
    context: "preceded by aws_secret"
  - name: "JWT"
    pattern: "eyJ[A-Za-z0-9_-]+\\.[A-Za-z0-9_-]+\\.[A-Za-z0-9_-]+"
  - name: "Generic API Key"
    pattern: "(api[_-]?key|token|secret)[\"']?\\s*[:=]\\s*[\"']?([a-zA-Z0-9_-]{20,})"
  - name: "Bearer Token"
    pattern: "Bearer\\s+[A-Za-z0-9_-]+"
  - name: "Private Key"
    pattern: "-----BEGIN (RSA |EC |DSA )?PRIVATE KEY-----"
  - name: "URL with Password"
    pattern: "[a-z]+://[^:]+:[^@]+@"
  - name: "Slack Token"
    pattern: "xox[bpoa]-[0-9]{12}-[0-9]{12}-[a-zA-Z0-9]{24}"
  - name: "GitHub Token"
    pattern: "gh[ps]_[A-Za-z0-9]{36}"
```

### 4-2. 사용자 입력 마스킹 (동료 이름)

사내 공유 전용이라 회사 시스템명(WMS, OMS 등)은 마스킹 안 함.
대신 동료 이름만 마스킹 (관찰자 효과 방지).

첫 실행 시 인터페이스:

```
[2/4] 동료 이름 마스킹 설정

보고서에서 동료 이름을 "동료" 로 추상화합니다.
(관찰자 효과 방지)

마스킹 사용?
  [Y] 사용 (권장)
  [n] 끄기

⓵ 마스킹할 동료 이름 입력 (한 줄에 하나, 빈 줄로 종료):

⓶ 자동 발견 후보 (한국어 이름 패턴 검출):
   - X님, X 매니저, X 선임, X PM, X 디자이너 등의 패턴
   - @사람태그
   - 등장 빈도 3회 이상
   
   [1] 철수 (12회 등장)    [Y/n]
   [2] 영수님 (8회 등장)    [Y/n]
```

자동 발견 룰:
- 한국어 이름 패턴 (2-4자 한글 + 직함/존칭)
- @사람태그
- 등장 빈도 3회 이상

저장 위치: `~/.config/cc-analyzer/config.yaml` 의 `people_names` 필드
(별도 yaml 분리 X — 사용자 config 의 일부로 관리)

### 4-3. 일반 도구 화이트리스트 (마스킹 제외)

```yaml
# config/public_tools_whitelist.yaml
observability:
  - grafana
  - datadog
  - prometheus
  - sentry
  - honeycomb
  - newrelic
  - splunk
  - kibana
  - loki

issue_tracker:
  - jira
  - linear
  - github
  - gitlab
  - asana
  - trello
  - notion
  - clickup

chat:
  - slack
  - discord
  - teams

cloud:
  - aws
  - gcp
  - azure
  - kubernetes
  - docker

# 확장 가능 (디자인 도구 등)
```

### 4-4. 마스킹 적용 시점 (옵션 C - 하이브리드)

```
Stage A (즉시):
  ✓ 시크릿 정규식 마스킹 → turns.parquet 저장 전 적용
  - 이유: 시크릿은 어디서도 새면 안 됨

Stage D (최종):
  ✓ 회사 내부 시스템명 마스킹 → 보고서 생성 직전 적용
  - 이유: 분석 자체엔 회사 이름 필요할 수 있음 (예: 패턴 묶기)
```

---

## 다음 단계 (3단계: Stage B 일반화)

- 14개 카테고리 enum 폐기
- 자유 텍스트 situation 라벨 + 사후 클러스터링
- under-split 문제 해결 방향 검토
