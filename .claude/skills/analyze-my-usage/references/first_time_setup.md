# First-Time Setup

`~/.config/cc-analyzer/config.yaml` 이 없거나 손상됐을 때 Claude가 수행하는 첫 실행 마법사.

## 목적

사용자가 처음 분석기를 쓸 때 필요한 최소 설정만 받아 저장.
한 번 끝내면 다음부터는 이 마법사 거치지 않음.

## 흐름 (4단계)

1. 환영 메시지 + 무엇을 설정하는지 안내
2. 도구 → 기능 그룹 매핑 자동 분류 + 사용자 확인
3. 동료 이름 마스킹 설정
4. 보고서 저장 위치 확인
5. config.yaml 저장

각 단계 끝나면 사용자에게 짧게 확인.

---

## 단계 1: 환영 메시지

```
[Claude Code 사용 패턴 분석기 — 첫 설정]

이 시스템은 ~/.claude/projects/ 의 Claude Code 대화 기록을 분석해서
당신의 워크플로 패턴을 자동으로 문서화합니다.

설정에 약 2-3분 소요됩니다. 4단계로 진행됩니다:
  [1/4] 도구 매핑 확인
  [2/4] 동료 이름 마스킹 설정
  [3/4] 보고서 저장 위치
  [4/4] 저장

(API key 입력 불필요 — Claude Code 환경에서 실행되므로)
```

---

## 단계 2: 도구 매핑 자동 분류 + 사용자 확인

`config/function_groups.yaml` 의 17개 기능 그룹 기준으로,
사용자 데이터에 등장한 도구를 자동 분류.

### 절차

**(2-1) 사용자 데이터에서 unique 도구 이름 수집**

Bash로:
```bash
find ~/.claude/projects -name "*.jsonl" \
  | xargs grep -oh '"name":"[^"]*"' \
  | sort -u
```

또는 stage_a.py 가 도구 수집만 하는 모드 (`--list-tools`) 제공할 것.

**(2-2) Claude가 각 도구를 17개 기능 그룹 중 하나로 분류**

`config/function_groups.yaml` 참고. 각 그룹의 설명과 예시 도구를 보고 분류.

예시:
```
grafana_query_logs        → log_search
atlassian_jira_search     → issue_tracker
atlassian_confluence_get  → docs
slack_search_public       → chat
custom_internal_mcp_xyz   → other (분류 모호)
```

**(2-3) 사용자에게 확인 요청**

```
[1/4] 도구 매핑 확인

당신의 데이터에서 다음 도구들을 발견했고 기능 그룹으로 자동 분류했습니다:

  grafana_query_logs        → log_search       ✓
  atlassian_jira_search     → issue_tracker    ✓
  atlassian_confluence_get  → docs             ✓
  slack_search_public       → chat             ✓
  custom_internal_mcp_xyz   → other (분류 모호) ⚠️

[Enter로 확정 / e로 수정]
```

**(2-4) 사용자가 'e'를 누르면 수정 모드:**

```
어느 도구를 어느 그룹으로 바꾸시겠어요?
형식: <도구이름> -> <기능그룹>
예: custom_internal_mcp_xyz -> log_search

빈 줄로 종료.
> custom_internal_mcp_xyz -> log_search
> 
✓ 수정됨
```

**(2-5) 결과를 config.tool_function_mapping 에 저장**

---

## 단계 3: 동료 이름 마스킹 설정

관찰자 효과 방지. 디폴트는 ON.

### 절차

**(3-1) 마스킹 ON/OFF 결정**

```
[2/4] 동료 이름 마스킹 설정

보고서에서 동료 이름을 "동료" 로 추상화합니다.
(관찰자 효과 방지 — 동료가 본인 의지와 무관하게 노출되는 것 방지)

마스킹 사용?
  [Y] 사용 (권장)
  [n] 끄기
```

`n` 선택 시 단계 3 건너뛰고 4단계로.

**(3-2) 마스킹할 이름 직접 입력**

```
마스킹할 동료 이름을 입력하세요 (한 줄에 하나, 빈 줄로 종료):
> 코비
> 영희
> 
✓ 2개 등록됨
```

**(3-3) 자동 발견 후보 제시**

사용자 데이터에서 사람 이름 패턴 자동 검출:
- 한국어 이름 패턴 (X님, X 매니저, X 선임, X PM, X 디자이너 등)
- @사람태그
- 등장 빈도 3회 이상

검출 알고리즘:
```python
# 한국어 이름 후보: 2-4자 한글 + 직함/존칭
patterns = [
    r'([가-힣]{2,4})(님|씨|매니저|선임|책임|PM|개발자|디자이너)',
    r'@([가-힣]{2,4})',
]
```

자동 발견된 이름 + 빈도를 보여줌:

```
자동 발견 후보 (한국어 이름 패턴 검출):
[1] 철수 (12회 등장)    [Y/n]
[2] 영수님 (8회 등장)    [Y/n]
[3] PM 지영 (5회 등장)   [Y/n]

각 항목에 Y/n 입력:
> Y
> Y
> n
✓ 2개 추가됨 (총 4개)
```

**(3-4) 결과를 config 에 저장**

```yaml
mask_people_names: true
people_names:
  - "코비"
  - "영희"
  - "철수"
  - "영수님"
```

---

## 단계 4: 보고서 저장 위치

```
[3/4] 보고서 저장 위치

디폴트: ~/Documents/claude-usage-reports/
변경하려면 경로 입력, 그대로 두려면 Enter:
> [Enter]

✓ ~/Documents/claude-usage-reports/
```

디렉토리 없으면 생성.

---

## 단계 5: config.yaml 저장

```
[4/4] 저장

✓ 설정 완료. ~/.config/cc-analyzer/config.yaml 에 저장됨.
```

저장 형식:
```yaml
# ~/.config/cc-analyzer/config.yaml

tool_function_mapping:
  grafana_query_logs: log_search
  atlassian_jira_search: issue_tracker
  atlassian_confluence_get: docs
  slack_search_public: chat
  custom_internal_mcp_xyz: log_search   # 사용자 수정 반영
  # ... 모든 도구

mask_people_names: true
people_names:
  - "코비"
  - "영희"
  - "철수"
  - "영수님"

output_dir: "~/Documents/claude-usage-reports/"

# 메타
created_at: "2026-05-19T10:32:00"
schema_version: 1
```

---

## 마법사 후 흐름

설정 끝나면 사용자에게 바로 묻기:

```
지금 분석을 시작하시겠습니까?
  [Y] 시작 (단계 1 — 기간 결정으로 이동)
  [n] 나중에 (종료)
```

`Y` → SKILL.md 단계 1 (기간 결정)으로 점프.
`n` → 종료. 다음에 `/analyze-my-usage` 호출 시 단계 1부터 시작.

---

## 실패 / 회복

**도구 매핑 자동 분류 실패 (도구 0개 발견):**
- 사용자가 Claude Code 처음 쓰는 경우일 수 있음
- "~/.claude/projects/ 가 비어있습니다. Claude Code 를 한 번이라도 사용한 후 다시 시도해주세요." 안내 후 종료

**config 저장 실패 (권한 등):**
- 사용자에게 권한 확인 안내
- chmod 명령어 알려줌

**중간 종료 (사용자 Ctrl+C):**
- 설정 미저장. 다음 실행 시 처음부터 다시 진행됨을 안내.
