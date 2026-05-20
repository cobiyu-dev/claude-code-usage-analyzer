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
| `outcome_signals.yaml` | 에피소드 종결 신호 (commit/verify/abandon 등) | Stage B |
| `git_intent_patterns.yaml` | git 명령의 의도 분류 (diagnostic/output/transition) | Stage B |
| `people_name_patterns.yaml` | 사람 이름 자동 발견 정규식 (직함·언어별) | Stage A 마스킹 후보 발견 |
| `company_system_hints.yaml` | (옵션) 보고서 사용 예시에 들어가면 안 되는 회사 식별자 substring | Stage D 후처리 검증 |

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

### 확장 가이드 (다른 직군에서 그룹이 부족할 때)

위 17개는 백엔드 + 물류 도메인 + 일반 SRE 직군 기준으로 추린 것. 다른 직군 사용자가 시스템을 돌렸을 때 자기 도구가 `other` 로만 분류된다면, 이 yaml 에 그룹을 추가하면 된다. **코드 수정 불필요.**

직군별로 추가될 만한 그룹의 예 (가이드만, 본인 데이터로 박지 말 것):

```yaml
# 데이터 분석가
data_warehouse:
  description_ko: "데이터 웨어하우스 쿼리"
  description_en: "data warehouse query"
  example_tools: [bigquery, snowflake, redshift, databricks]

bi_tool:
  description_ko: "BI 대시보드 도구"
  description_en: "BI dashboard"
  example_tools: [looker, tableau, metabase, superset]

notebook:
  description_ko: "노트북 환경"
  description_en: "notebook"
  example_tools: [jupyter, colab, hex]

# 프론트엔드/모바일 개발자
ui_test:
  description_ko: "UI 테스트 도구"
  description_en: "UI test"
  example_tools: [playwright, cypress, storybook, percy]

package_registry:
  description_ko: "패키지 레지스트리"
  description_en: "package registry"
  example_tools: [npm, yarn, pnpm, cargo, pip]

# 디자이너
asset_export:
  description_ko: "디자인 산출물 추출"
  description_en: "asset export"
  example_tools: [figma_export, sketch_export]

# PM / 기획자
roadmap:
  description_ko: "로드맵 도구"
  description_en: "roadmap"
  example_tools: [productboard, aha, roadmunk]

survey:
  description_ko: "설문/리서치 도구"
  description_en: "survey/research"
  example_tools: [typeform, surveymonkey, dovetail]

# 보안/인프라
secrets_manager:
  description_ko: "시크릿 관리 도구"
  description_en: "secrets manager"
  example_tools: [vault, aws_secrets_manager, doppler]

iac:
  description_ko: "IaC 도구"
  description_en: "infrastructure as code"
  example_tools: [terraform, pulumi, cloudformation]
```

### 추가 시 점검 사항

1. **example_tools 는 일반 공개 도구만**. 회사 내부 시스템명을 example_tools 에 박지 말 것 (그건 사용자 config 의 tool_function_mapping 에서 매핑).
2. **description_ko 는 일반 한국어 명사구**. 회사 어휘 X.
3. **새 그룹은 carve_out_rules.yaml 에도 룰을 추가**. 룰 미정의면 `other` 의 fallback 룰 적용됨 (동작은 함, 단 추출 품질 낮음).
4. **약속 1 점검**: 새 그룹 정의가 본인 데이터에 끼워 맞추기인가? 다른 사용자 일반에도 통하는가?

### `other` 그룹 운영 원칙

- `other` 는 fallback. 자주 발생하는 도구가 `other` 에 묶이면 → 새 그룹을 만들 신호
- 단, **본인 데이터에 자주 보인다고 무조건 새 그룹을 만들지 말 것**. 이게 다른 직군에도 보편적인 기능 카테고리인지 먼저 생각

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

## 7. `config/outcome_signals.yaml`

Stage B 작업 3 (에피소드 내부 구조 라벨링) 의 outcome 신호 판정 룰.
**verify phase 안에서만** 매칭한다 (도입부의 commit/push 가 잘못 분류되지 않도록).

```yaml
outcomes:
  committed:
    description: "git commit 으로 종결"
    detect:
      tool: shell_exec
      command_regex: '^\s*git\s+commit(\s|$)'
      phase: verify

  pushed:
    description: "원격 푸시까지 진행"
    detect:
      tool: shell_exec
      command_regex: '^\s*git\s+push(\s|$)'
      phase: verify

  pr_opened:
    description: "PR 생성으로 종결"
    detect:
      any_of:
        - tool: shell_exec
          command_regex: '^\s*gh\s+pr\s+create(\s|$)'
        - tool_name_regex: '^(mcp__)?github__create_pull_request$'
      phase: verify

  verified_by_data:
    description: "작업 결과를 데이터로 직접 검증"
    detect:
      function_group_in: [db_query, log_search, metric_query, trace_view]
      phase: verify

  verified_by_run:
    description: "앱/테스트 실행으로 결과 검증"
    detect:
      tool: shell_exec
      output_type: execution_like   # Stage A 의 출력 유형 분류 결과
      phase: verify

  delegated_and_reported:
    description: "위임 후 결과 요약만 받음"
    detect:
      # main 또는 verify phase 마지막 turn 이 agent 도구의 결과 요약
      tool: agent
      position: last_turn_of_main_or_verify

  abandoned_or_paused:
    description: "검증·종결 없이 끊김"
    detect:
      verify_phase_empty: true
      last_turn_signals:
        any_of:
          - has_error_output: true
          - no_assistant_response_within: 5m

  # commit/PR 양상 세분화 (패턴 2)
  # 위 committed/pushed/pr_opened 와 동시 부여 가능. 양상을 한 단계 더 라벨링.

  incremental_commits:
    description: "작업 중간중간 여러 번 commit 으로 끊어 감"
    detect:
      git_commits_count_gte: 2
      commit_positions:
        any_in: [main]   # main phase 안에 commit 이 1번 이상 있음 (verify 의 마지막 commit 외)

  single_final_commit:
    description: "작업 전체를 끝까지 끌고 가서 한 번에 commit"
    detect:
      git_commits_count_eq: 1
      commit_positions:
        all_in: [verify]

  pr_with_structured_body:
    description: "PR 본문을 구조화해 생성 (요약·테스트 계획 등 섹션)"
    detect:
      any_of:
        - tool: shell_exec
          command_regex: 'gh\s+pr\s+create.*--body'
          body_contains_any: ["## Summary", "## Test", "## 변경", "## 요약"]
        - tool_name_regex: '^(mcp__)?github__create_pull_request$'
          body_contains_any: ["## Summary", "## Test", "## 변경", "## 요약"]
      phase: verify
```

### 룰 작성 원칙

- **하드코딩 금지**: 모든 정규식·임계값을 이 파일에 두기. Python 코드에 박지 말 것.
- **약속 1 (튜닝 X)**: 본인 데이터에 맞춰 정규식 늘리지 말 것. 빠진 outcome 이 보이면 명세를 보완해 신규 outcome 으로 추가하는 게 정도.
- **약속 5 (직군 무관)**: `committed/pushed/pr_opened` 가 비는 직군(디자이너 등)은 `verified_by_run/verified_by_data/delegated_and_reported` 만 발현되어도 무너지지 않음.

---

## 8. `config/git_intent_patterns.yaml`

git Bash 호출을 의도별로 분류. Stage B 가 각 git turn 에 의도 태그를 붙이고, 에피소드 레벨에서는 `git_intents_used: set` 으로 집계.

```yaml
git_intent_patterns:
  diagnostic:
    description: "시간축 기반 진단 — 언제부터 깨졌나, 누가 바꿨나"
    commands:
      - regex: '^\s*git\s+log(\s|$)'
      - regex: '^\s*git\s+blame(\s|$)'
      - regex: '^\s*git\s+bisect(\s|$)'
      - regex: '^\s*git\s+show(\s|$)'
      - regex: '^\s*git\s+diff\s+[a-z0-9._-]+\.\.'   # 커밋 범위 비교
      - regex: '^\s*git\s+reflog(\s|$)'

  output:
    description: "산출 — 변경을 외부로 내보냄"
    commands:
      - regex: '^\s*git\s+add(\s|$)'
      - regex: '^\s*git\s+commit(\s|$)'
      - regex: '^\s*git\s+push(\s|$)'
      - regex: '^\s*git\s+tag(\s|$)'

  transition:
    description: "전환 — 브랜치/상태 이동"
    commands:
      - regex: '^\s*git\s+checkout(\s|$)'
      - regex: '^\s*git\s+switch(\s|$)'
      - regex: '^\s*git\s+merge(\s|$)'
      - regex: '^\s*git\s+rebase(\s|$)'
      - regex: '^\s*git\s+stash(\s|$)'
      - regex: '^\s*git\s+pull(\s|$)'
      - regex: '^\s*git\s+fetch(\s|$)'

  # 분류 안 되면 의도 태그 없음. 빈도 낮은 잡 명령(status, branch -l)은 의도 없음으로 OK.
```

### 왜 분리하는가

`git` 명령들은 모두 `shell_exec` 기능 그룹으로 묶이지만, **의도가 다르다**:
- `git log` (진단) 가 들어있는 에피소드는 "회귀 시점 추적"이라는 별도 메서드러지 패턴
- `git commit/push` (산출) 만 들어있는 에피소드는 "마무리 흐름"

이 둘이 같은 shell_exec 빈도로 묶이면 패턴 추출이 무뎌진다. yaml 로 분리해 Stage D 가 별도 신호로 사용한다.

### 직군 무관성

git 을 안 쓰는 직군이면 `git_intents_used` 가 빈 set 으로 남음. 보고서에서 자연스럽게 누락 → 무너지지 않음.

---

## 9. `config/people_name_patterns.yaml`

Stage A 가 첫 실행 마법사에서 사람 이름 자동 발견 후보를 뽑을 때 쓰는 정규식 모음.
직함 enum 을 코드에 박지 말 것. yaml 로 분리해 언어·문화권마다 확장 가능하게.

```yaml
people_name_patterns:
  # 한국어
  - lang: ko
    name_regex: '[가-힣]{2,4}'           # 2~4자 한글 (이름 후보)
    suffixes:                              # 직함/존칭 (이름 뒤에 붙음)
      - 님
      - 씨
      - 매니저
      - 선임
      - 책임
      - 수석
      - 팀장
      - 실장
      - 과장
      - 차장
      - 부장
      - PM
      - PO
      - 개발자
      - 디자이너
      - 엔지니어
      - 기획자
    prefixes:                              # 직함/존칭 (이름 앞에 붙음)
      - PM
      - PO
      - 매니저
      - 선임
      - 책임
      - 디자이너
      - 기획자
    tag_regex: '@[가-힣]{2,4}'            # 멘션 표기

  # 영어 (기본 패턴, 직군·조직마다 확장 가능)
  - lang: en
    name_regex: '[A-Z][a-z]{2,15}'         # 첫 글자 대문자 + 2~15자 (이름 후보)
    suffixes: []                            # 영어는 직함이 앞에 오는 게 일반적
    prefixes:
      - Manager
      - Senior
      - Lead
      - Principal
      - Staff
      - PM
      - PO
      - Designer
      - Engineer
    tag_regex: '@[A-Za-z][A-Za-z0-9._-]{1,30}'

# 자동 발견 임계값
min_frequency: 3        # 이 횟수 이상 등장한 후보만 사용자에게 제시
deduplication: true     # "철수" 와 "철수님" 같은 같은 사람의 변형은 묶어서 제시
```

### 자동 발견 알고리즘

```python
def discover_name_candidates(turns, config_yaml):
    candidates = Counter()
    variants_of = defaultdict(set)   # 정규화된 키 -> 원본 변형 집합

    for lang_block in config_yaml["people_name_patterns"]:
        name_re = lang_block["name_regex"]
        # name + suffix 패턴
        for suf in lang_block.get("suffixes", []):
            pat = re.compile(f'({name_re}){re.escape(suf)}')
            for t in turns:
                for m in pat.finditer(t.content):
                    full = m.group(0)
                    base = m.group(1)
                    candidates[full] += 1
                    variants_of[base].add(full)
        # prefix + name 패턴
        for pre in lang_block.get("prefixes", []):
            pat = re.compile(f'{re.escape(pre)}\\s*({name_re})')
            ...
        # @태그
        if "tag_regex" in lang_block:
            ...

    min_freq = config_yaml.get("min_frequency", 3)
    return [
        (name, count) for name, count in candidates.most_common()
        if count >= min_freq
    ]
```

### 사용 위치

- **Stage A 첫 실행 마법사** (단계 3 — 동료 이름 마스킹): 자동 발견 후보 제시
- 검출된 후보 자체는 마스킹 대상이 아님. 사용자가 Y/n 선택한 것만 `config.people_names` 에 들어가고, 이후 Stage D 검증에서 마스킹.

### 셀프 체크

- **약속 1**: 직함 enum 을 본인 조직에 맞춰 좁히지 말 것. ko/en 양쪽에 일반 직함이 들어가야 함. 본인 조직에 없는 직함도 다른 사용자에겐 있을 수 있음.
- **약속 2**: 모든 직함을 yaml 로 분리. 코드에 박힌 정규식 없음.
- **약속 5**: 새 언어권(일본어 さん, 중국어 先生 등) 은 yaml 에 `lang: ja` block 추가만으로 확장. 코드 변경 불필요.

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
