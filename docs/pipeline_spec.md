# Pipeline + Install 명세

이 문서는 시스템 전체의 실행 흐름과 설치 방법을 정의.
개별 stage 알고리즘은 stage_a_spec.md, stage_b_spec.md 등 참고.

---

## 1. 디렉토리 구조

### 1-1. Repo 구조 (git clone 받는 것)

```
claude-code-usage-analyzer/
├── .claude/
│   ├── commands/
│   │   └── analyze-my-usage.md      ← slash command
│   └── skills/
│       └── analyze-my-usage/
│           ├── SKILL.md             ← 메인 워크플로
│           └── references/
│               ├── stage_b_workflow.md
│               ├── stage_d_workflow.md
│               ├── format_c.md
│               └── first_time_setup.md
│
├── scripts/
│   ├── preprocess.sh                ← Stage A 진입점
│   ├── postprocess.sh               ← Stage C 진입점
│   ├── stage_a.py                   ← 파싱 + carve-out + 마스킹
│   ├── stage_c.py                   ← 집계
│   └── lib/
│       ├── tool_mapper.py
│       ├── output_classifier.py
│       └── masker.py
│
├── config/                          ← 시스템 기본 설정
│   ├── secret_patterns.yaml
│   ├── public_tools_whitelist.yaml
│   ├── function_groups.yaml
│   ├── carve_out_rules.yaml
│   ├── execution_keywords.yaml
│   └── split_signals.yaml
│
├── docs/                            ← 설계 명세 문서
│   ├── principles_user_agnostic.md
│   ├── stage_a_spec.md
│   ├── stage_b_spec.md
│   ├── stage_c_spec.md
│   ├── format_c_spec.md
│   └── pipeline_spec.md            ← 이 문서
│
├── pyproject.toml                   ← Python 의존성
├── .gitignore
└── README.md
```

### 1-2. 사용자 데이터 위치 (repo 밖)

```
~/.config/cc-analyzer/                 ← 사용자별 설정 (gitignore X — 별도 위치)
└── config.yaml                        # 도구 매핑 캐시, 동료 이름 등

~/.cache/cc-analyzer/                  ← 중간 산출물
└── {start}_to_{end}/                  # 예: 2026-04-20_to_2026-05-17/
    ├── turns.parquet                  # Stage A 결과
    ├── episodes.parquet               # Stage B 결과
    ├── aggregated.json                # Stage C 결과
    └── report_draft.md                # 검증 전 임시

~/Documents/claude-usage-reports/      ← 최종 보고서
└── {start}_to_{end}.md
```

---

## 2. 설치 흐름

### 2-1. 사용자가 하는 일

```bash
$ git clone https://github.com/cobi/claude-code-usage-analyzer
$ cd claude-code-usage-analyzer

# Python 의존성 설치
$ uv pip install -r pyproject.toml
# 또는: pip install -e .

# Claude Code 시작
$ claude

# 슬래시 호출
> /analyze-my-usage
```

별도 install.sh 없음. README.md 에 위 3줄만 안내.

### 2-2. 사전 요구사항

- macOS (또는 Linux)
- Claude Code 설치되어 있음
- Python 3.10+
- uv 또는 pip
- ~/.claude/projects/ 에 대화 기록 있음 (Claude Code 한 번이라도 사용)

부족하면 사용자에게 친절히 안내. README.md 에 명시.

### 2-3. Python 의존성

```toml
# pyproject.toml
[project]
name = "cc-analyzer-scripts"
version = "0.1.0"
dependencies = [
    "pandas",          # parquet
    "pyarrow",         # parquet
    "pyyaml",          # config
]
```

LLM 호출 라이브러리 (anthropic) 불필요. Claude Code 환경에서 실행되니까.

### 2-4. ANTHROPIC_API_KEY?

**불필요.** Claude Code 안에서 실행되므로 사용자의 Claude Code 인증을 그대로 사용.
별도 API key 입력받지 않음.

---

## 3. 실행 흐름

### 3-1. 슬래시 호출 흐름

```
사용자: /analyze-my-usage --last 4w
   ↓
.claude/commands/analyze-my-usage.md (slash command 정의)
   ↓
.claude/skills/analyze-my-usage/SKILL.md (skill 호출)
   ↓
Claude가 SKILL.md 의 8단계 따라 진행
```

### 3-2. 8단계 실행 흐름

```
1. 기간 결정
   - 인자 파싱 (--last 4w, --from/--to 등)
   - 인자 없으면 사용자에게 대화형 질문

2. 첫 실행 vs 일반 실행 분기
   - ~/.config/cc-analyzer/config.yaml 확인
   - 없거나 손상이면 first_time_setup.md 마법사 실행
   - 있으면 config 로드

3. Stage A 실행 (Bash로 preprocess.sh 호출)
   - jsonl 파싱 → turns.parquet
   - carve-out (도구별 본문 절사)
   - 시크릿 마스킹 (자동)

4. Stage B 처리 (Claude 자신이)
   - turns.parquet 읽기
   - 휴리스틱 분할
   - 자유 텍스트 라벨 생성
   - 양방향 판단 (합칠지/끊을지/유지)
   - 라벨 사후 클러스터링
   - episodes.parquet 저장

5. Stage C 실행 (Bash로 postprocess.sh 호출)
   - episodes.parquet 읽기
   - 그룹화 + 메트릭 + 시그니처 시퀀스 + 메타 집계
   - aggregated.json 저장

6. Stage D 처리 (Claude 자신이)
   - episodes.parquet + aggregated.json 읽기
   - 패턴 추출 (메서드러지 패턴, 도메인 무관)
   - 느슨한 그룹화 판정
   - 시계열 추이 (기간 ≥ 2주일 때)
   - 보고서 작성 → report_draft.md

7. 보고서 검증 + 저장
   - 시크릿/동료 이름/도구 표기 자동 검증
   - WARN → 자동 보완
   - CRITICAL → 보고서 폐기 또는 재시도
   - 검증 통과 → 최종 위치에 저장

8. 에러 처리 (각 단계 실패 시)
```

---

## 4. preprocess.sh 명세

Stage A 만 실행하는 진입점.

### 사용법

```bash
./scripts/preprocess.sh \
  --from 2026-04-20 \
  --to 2026-05-17 \
  --config ~/.config/cc-analyzer/config.yaml
```

### 인자

- `--from YYYY-MM-DD` (필수)
- `--to YYYY-MM-DD` (필수)
- `--config <path>` (필수)
- `--cache-dir <path>` (옵션, 디폴트 `~/.cache/cc-analyzer/`)

### 동작

```bash
#!/usr/bin/env bash
set -euo pipefail

# 인자 파싱 (생략)

# 사전 체크
[ -d "$HOME/.claude/projects" ] || {
  echo "Error: ~/.claude/projects/ 가 없습니다." >&2
  exit 1
}

[ -f "$CONFIG" ] || {
  echo "Error: config 파일 없음: $CONFIG" >&2
  exit 2
}

# 출력 디렉토리 준비
PERIOD="${FROM}_to_${TO}"
WORK_DIR="${CACHE_DIR}/${PERIOD}"
mkdir -p "$WORK_DIR"

# Stage A 실행
echo "[Stage A] 파싱 + carve-out + 시크릿 마스킹"
python3 scripts/stage_a.py \
  --from "$FROM" \
  --to "$TO" \
  --config "$CONFIG" \
  --output "${WORK_DIR}/turns.parquet"

echo "✓ Stage A 완료: ${WORK_DIR}/turns.parquet"
```

### 종료 코드

- 0: 성공
- 1: ~/.claude/projects 없음
- 2: config 파일 없음
- 3: 인자 형식 오류
- 4: stage_a.py 실행 실패

---

## 5. postprocess.sh 명세

Stage C 만 실행하는 진입점.

### 사용법

```bash
./scripts/postprocess.sh \
  --episodes ~/.cache/cc-analyzer/{period}/episodes.parquet \
  --output ~/.cache/cc-analyzer/{period}/aggregated.json
```

### 인자

- `--episodes <path>` (필수): Stage B 결과 parquet
- `--output <path>` (필수): aggregated.json 저장 위치

### 동작

```bash
#!/usr/bin/env bash
set -euo pipefail

# 인자 파싱

[ -f "$EPISODES" ] || {
  echo "Error: episodes.parquet 없음: $EPISODES" >&2
  exit 1
}

echo "[Stage C] 그룹별 메트릭 + 시그니처 시퀀스 + 메타 집계"
python3 scripts/stage_c.py \
  --episodes "$EPISODES" \
  --output "$OUTPUT"

echo "✓ Stage C 완료: $OUTPUT"
```

### 종료 코드

- 0: 성공
- 1: episodes.parquet 없음
- 2: 인자 형식 오류
- 3: stage_c.py 실행 실패

---

## 6. config.yaml 스키마

`~/.config/cc-analyzer/config.yaml`. 첫 실행 마법사가 생성.

```yaml
# 도구 → 기능 그룹 매핑 (사용자별, 첫 실행 마법사에서 확인됨)
tool_function_mapping:
  grafana_query_logs: log_search
  atlassian_jira_search: issue_tracker
  atlassian_confluence_get: docs
  slack_search_public: chat
  # ... 모든 도구

# 동료 이름 마스킹
mask_people_names: true            # default true
people_names:
  - "코비"
  - "영희"
  - "철수"

# 보고서 저장 위치
output_dir: "~/Documents/claude-usage-reports/"

# 메타
created_at: "2026-05-19T10:32:00"
schema_version: 1
```

### 필수 필드

- `tool_function_mapping`: 비어있어도 됨 ({}). 분석 중 새 도구 등장 시 사용자에게 확인하고 추가
- `mask_people_names`: bool
- `output_dir`: 절대 경로

손상되면 (필수 필드 빠지면) 첫 실행 마법사 재실행.

---

## 7. CLI 인자 (슬래시 커맨드)

```
/analyze-my-usage [옵션]

기간 옵션:
  --last 1w / 4w / 1m / 3m       지난 N주/개월
  --from YYYY-MM-DD --to YYYY-MM-DD
  --since YYYY-MM-DD              해당 날짜부터 오늘까지

부가 옵션:
  --no-mask-names                 동료 이름 마스킹 끄기 (이번 실행만)
  --output <path>                 보고서 저장 위치 (이번 실행만)
  --reconfigure                   설정 마법사 재실행

(인자 없으면 인터랙티브)
```

---

## 8. 결과 보고서 파일명

```
{output_dir}/{start}_to_{end}.md

예시:
~/Documents/claude-usage-reports/2026-04-20_to_2026-05-17.md
```

---

## 9. 셀프 체크

**약속 1**: 본 파이프라인은 단순 실행 흐름. 본인 데이터 보고 만든 룰 없음.

**약속 2**: 파이프라인 단계 자체는 사용자 무관. 사용자별 정보는 config.yaml 에 분리.

**약속 3**: 사용자가 직접 손댈 거 없음. 슬래시 하나로 자동 진행.

**약속 4**: 시크릿 마스킹은 Stage A 에서 (preprocess.sh). 동료 이름 마스킹은 단계 7 검증.

**약속 5**: macOS/Linux + Python + Claude Code 환경이면 어느 사용자에게도 동일 동작.
