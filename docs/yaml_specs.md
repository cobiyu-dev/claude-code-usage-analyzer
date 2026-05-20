# YAML Config 명세

이 문서는 `config/` 디렉토리의 모든 yaml 파일의 실제 형식을 정의.

각 명세 (stage_a_spec.md, format_c_spec.md 등) 는 이 파일을 참조.

---

## 파일 목록

| 파일 | 책임 | 누가 읽나 |
|---|---|---|
| `function_groups.yaml` | 17개 기능 그룹 정의 + 한국어 설명 | Stage A, D |
| `carve_out_rules.yaml` | 기능 그룹별 carve-out 룰 | Stage A |
| `execution_keywords.yaml` | Bash 실행형 키워드 | Stage A |
| `secret_patterns.yaml` | 시크릿 정규식 | Stage A, D 검증 |
| `public_tools_whitelist.yaml` | 일반 공개 도구 목록 | Stage A, D 검증 |
| `split_signals.yaml` | 에피소드 분할 휴리스틱 임계값/키워드 | Stage B |

---

## 1. `config/function_groups.yaml`

17개 기능 그룹의 정의. 도구 → 기능 매핑 시 Claude 가 분류 기준으로 사용.
보고서 도구 표기 시 한국어 설명 (`description_ko`) 가 인라인 괄호에 들어감.

```yaml
function_groups:
  # 정보 검색·조회
  log_search:
    description_ko: "로그 검색 도구"
    description_en: "log search"
    example_tools: [grafana, datadog_logs, splunk, loki]
    
  trace_view:
    description_ko: "분산 trace 분석 도구"
    description_en: "distributed trace analysis"
    example_tools: [datadog_apm, honeycomb, jaeger]
    
  metric_query:
    description_ko: "메트릭 조회 도구"
    description_en: "metric query"
    example_tools: [prometheus, datadog_metrics, cloudwatch]
    
  db_query:
    description_ko: "DB 쿼리 도구"
    description_en: "database query"
    example_tools: [mysql, bigquery, postgres]
    
  code_search:
    description_ko: "코드 검색 도구"
    description_en: "code search"
    example_tools: [grep, ripgrep, github_code_search]
    
  web:
    description_ko: "웹 검색/조회"
    description_en: "web search/fetch"
    example_tools: [web_search, web_fetch]
    
  # 작업 관리·협업
  issue_tracker:
    description_ko: "이슈 트래커"
    description_en: "issue tracker"
    example_tools: [jira, linear, github_issues, asana]
    
  chat:
    description_ko: "채팅 도구"
    description_en: "chat/messaging"
    example_tools: [slack, discord, teams]
    
  docs:
    description_ko: "문서 협업 도구"
    description_en: "documentation"
    example_tools: [confluence, notion, google_docs]
    
  # 파일·코드 조작
  file_read:
    description_ko: "파일 읽기"
    description_en: "file read"
    example_tools: [Read]
    
  file_edit:
    description_ko: "파일 편집"
    description_en: "file edit"
    example_tools: [Edit, Write]
    
  shell_exec:
    description_ko: "셸 실행"
    description_en: "shell execution"
    example_tools: [Bash]
    
  # 자동화·외부 조작
  browser:
    description_ko: "브라우저 자동화"
    description_en: "browser automation"
    example_tools: [chrome_mcp, playwright]
    
  design_tool:
    description_ko: "디자인 도구"
    description_en: "design tool"
    example_tools: [figma]
    
  ide:
    description_ko: "IDE 연동"
    description_en: "IDE integration"
    example_tools: [vscode_mcp, jetbrains_mcp]
    
  # 기타
  agent:
    description_ko: "서브 에이전트"
    description_en: "subagent"
    example_tools: [Task]
    
  other:
    description_ko: ""   # 인라인 괄호 생략
    description_en: ""
    example_tools: []
```

### 사용 방식

**Stage A (도구 → 기능 매핑)**:
- Claude 가 사용자 데이터의 도구 이름을 보고 `function_groups` 중 하나로 분류
- `example_tools` 를 분류 힌트로 사용
- 결과는 사용자 `config.yaml` 의 `tool_function_mapping` 에 캐시

**Stage D (보고서 도구 표기)**:
- 일반 공개 도구 첫 등장 시 `description_ko` 를 괄호에 삽입
- `other` 그룹은 괄호 생략

---

## 2. `config/carve_out_rules.yaml`

Stage A 의 기능 그룹별 본문 절사 룰.

```yaml
carve_out_rules:
  log_search:
    rationale: "어떤 검색 쿼리에 어떤 로그가 매칭됐는지가 핵심"
    rule: 
      type: "first_n_entries"
      n: 3
      include_query: true
      include_total_count: true
      
  trace_view:
    rationale: "trace 한 건의 span 구조가 핵심"
    rule:
      type: "first_n_traces"
      n: 1
      include_span_tree: true
      include_total_count: true
      
  metric_query:
    rule:
      type: "query_plus_first_n_points"
      n: 5
      include_total_count: true
      
  db_query:
    rule:
      type: "sql_plus_first_n_rows"
      n: 5
      include_columns: true
      include_total_count: true
      
  code_search:
    rule:
      type: "pattern_plus_first_n_lines"
      n: 10
      
  web:
    rule:
      web_search: 
        type: "query_plus_first_n_results"
        n: 5
        result_snippet_chars: 150
      web_fetch:
        type: "url_plus_head_tail"
        head_chars: 400
        tail_chars: 200
        
  issue_tracker:
    rule:
      type: "issue_summary"
      include: [id, title, status, assignee]
      body_chars: 300
      
  chat:
    rule:
      type: "first_n_messages"
      n: 5
      message_chars: 200
      include_channel: true
      
  docs:
    rule:
      type: "doc_summary"
      include: [title, headers]
      first_paragraph_chars: 300
      header_levels: [1, 2]
      
  file_read:
    rule:
      type: "short_or_signature"
      short_threshold_lines: 80
      signature_includes: ["imports", "function_signatures", "notable_lines"]
      notable_keywords: ["TODO", "FIXME", "XXX", "HACK"]
      
  file_edit:
    rule:
      edit:
        type: "diff_summary"
        old_str_chars: 200
        new_str_chars: 200
        include_path: true
      write:
        type: "head_tail"
        head_chars: 300
        tail_chars: 100
        include_path: true
        
  shell_exec:
    rule:
      type: "delegate_to_output_classifier"   # 작업 3: 출력 유형 분류로 위임
      
  browser:
    rule:
      type: "action_summary"
      include: [current_url, action_type, page_title]
      
  design_tool:
    rule:
      type: "object_summary"
      include: [object_id, object_type]
      change_summary_chars: 200
      
  ide:
    rule:
      type: "action_summary"
      include: [file, position, action_type]
      
  agent:
    rule:
      type: "task_summary"
      task_description_chars: 400
      result_tail_chars: 400
      
  other:
    rule:
      type: "fallback_head_tail"
      tool_name: true
      arguments_summary: true
      result_head_chars: 400
      result_tail_chars: 200
```

### 출력 유형 분류 (shell_exec 위임 대상)

`shell_exec` 의 룰이 `delegate_to_output_classifier` 면 Bash 출력을 다음 5개 유형으로 분류:

```yaml
output_types:
  list_like:
    rule:
      type: "first_n_lines"
      n: 10
      include_total: true
      
  execution_like:
    rule:
      type: "exec_summary"
      include: [exit_code, command]
      stdout_tail_lines: 30
      stderr_tail_lines: 10
      
  document_like:
    rule:
      type: "short_or_signature"
      short_threshold_lines: 80
      signature_includes: ["headers", "function_signatures", "notable_lines"]
      
  short_output:
    rule:
      type: "full"   # 전문 유지
      max_lines: 5
      max_chars: 400
      
  structured_data:
    rule:
      type: "structured_summary"
      include: [top_level_keys]
      first_n_items: 3
      include_total: true
```

---

## 3. `config/execution_keywords.yaml`

Stage A 에서 Bash 출력을 `execution_like` 로 판정할 때 명령어 검사 키워드.

```yaml
execution_keywords:
  # 빌드 관련
  - build
  - compile
  - make
  - cargo
  - go build
  - mvn
  - gradle
  
  # 테스트
  - test
  - jest
  - pytest
  - go test
  - cargo test
  - python -m pytest
  
  # 설치/배포
  - install
  - deploy
  - npm
  - yarn
  - pnpm
  - pip install
  - cargo install
  
  # 컨테이너/CI
  - docker
  - docker-compose
  - kubectl apply
  
  # 확장 가능 — 새 키워드 자유롭게 추가
```

---

## 4. `config/secret_patterns.yaml`

Stage A 와 Stage D 검증에서 사용하는 시크릿 정규식.

```yaml
secret_patterns:
  - name: "AWS Access Key"
    pattern: "AKIA[0-9A-Z]{16}"
    
  - name: "AWS Secret Key"
    pattern: "[a-zA-Z0-9+/]{40}"
    context_required: "aws_secret"   # context 매칭 시에만 (false positive 방지)
    
  - name: "JWT"
    pattern: 'eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+'
    
  - name: "Generic API Key"
    pattern: '(api[_-]?key|token|secret)["'']?\s*[:=]\s*["'']?([a-zA-Z0-9_-]{20,})'
    
  - name: "Bearer Token"
    pattern: 'Bearer\s+[A-Za-z0-9_-]+'
    
  - name: "Private Key"
    pattern: '-----BEGIN (RSA |EC |DSA )?PRIVATE KEY-----'
    
  - name: "URL with Password"
    pattern: '[a-z]+://[^:]+:[^@]+@'
    
  - name: "Slack Token"
    pattern: 'xox[bpoa]-[0-9]{12}-[0-9]{12}-[a-zA-Z0-9]{24}'
    
  - name: "GitHub Token"
    pattern: 'gh[ps]_[A-Za-z0-9]{36}'
    
  # 확장 가능
```

### 사용 위치

- **Stage A**: 파싱 직후 turn 본문에 정규식 매칭 → 검출 시 `[REDACTED]` 로 치환
- **Stage D 검증**: 생성된 보고서 후처리 시 다시 확인 → 검출 시 CRITICAL (보고서 폐기)

---

## 5. `config/public_tools_whitelist.yaml`

마스킹 제외할 일반 공개 도구 이름.

```yaml
# 카테고리는 가독성용. 매칭 시 평탄화해서 사용
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
  
design:
  - figma
  - sketch
  - adobe_xd

# 확장 가능 — 새 카테고리/도구 자유롭게 추가
```

### 사용 위치

- **Stage A**: 자동 발견된 사람 이름 후보 중 화이트리스트에 있는 것 (예: grafana) 은 "추천: n" 표시
- **Stage D 검증**: 도구 표기 룰 적용 시 (인라인 괄호 추가 대상 판정)

---

## 6. `config/split_signals.yaml`

Stage B 에피소드 분할 휴리스틱.

```yaml
time_gap:
  threshold_minutes: 20

session_change:
  enabled: true   # 세션 ID 다르면 끊기

clear_command:
  enabled: true   # /clear 직후 끊기

topic_keyword_change:
  enabled: true
  window_size: 5
  jaccard_threshold: 0.2   # 직전/다음 5턴의 명사 키워드 jaccard 0.2 이하면 끊기

function_group_disruption:
  enabled: true
  window_size: 5
  overlap_threshold: 0.2   # 도구 기능 그룹 set overlap 0.2 이하면 끊기

transition_phrases:
  ko:
    - "이제 다른"
    - "끝났네"
    - "그럼 새로운"
    - "다음으로"
    - "이제 됐다"
    - "이제 진짜"
  en:
    - "now let's"
    - "done with"
    - "moving on"
    - "next up"
    - "alright now"
```

---

## 사용자 config 와의 관계

위 6개 파일은 모두 repo 의 `config/` 에 있음 (시스템 기본값).
사용자별 설정은 `~/.config/cc-analyzer/config.yaml` 에 별도 (디렉토리 다름).

사용자 config 형식:

```yaml
# ~/.config/cc-analyzer/config.yaml

tool_function_mapping:           # 도구 → 기능 그룹 (사용자별)
  grafana_query_logs: log_search
  atlassian_jira_search: issue_tracker

mask_people_names: true           # 동료 이름 마스킹 ON/OFF
people_names:                     # 마스킹할 동료 이름
  - "코비"
  - "영희"

output_dir: "~/Documents/claude-usage-reports/"

created_at: "2026-05-19T10:32:00"
schema_version: 1
```

---

## 셀프 체크

**약속 1**: yaml 형식은 사용자 무관. 본인 데이터 보고 만든 값 없음.

**약속 2**: 모든 룰을 코드 밖 yaml 로 분리. 코드에 박혀있는 값 없음 (숫자 임계값도 모두 yaml).

**약속 3**: 사용자가 yaml 직접 손댈 일 없음 (기본값 그대로 사용).

**약속 4**: 시크릿 패턴, 공개 도구 화이트리스트 모두 명시.

**약속 5**: 사용자/직군 무관 (예: 디자이너는 design_tool, browser 그룹 자주 사용).
