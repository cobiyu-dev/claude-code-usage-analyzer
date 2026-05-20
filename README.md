# Claude Code Usage Analyzer

Claude Code 사용 패턴을 자동으로 문서화하는 시스템.
"어떤 상황에서 보통 어떻게 한다" 같은 메서드러지 패턴을 추출해서 
도메인 무관한 사내 공유용 보고서를 만든다.

## 무엇을 하는가

`~/.claude/projects/` 의 대화 기록을 분석해서, 사용자가 지정한 기간의 
워크플로 패턴을 마크다운 보고서로 추출.

예시 패턴:
- "에러나 이상 신호가 보이면 관련 로그를 통째로 수집한 뒤 분석을 시작한다"
- "도구 간 식별자를 매개로 체이닝한다"
- "복잡한 검토는 별도 에이전트에 위임하고 결과를 반복 반영한다"
- "변경을 마쳤으면 데이터로 결과를 다시 확인한 뒤 보고만 받는다"
- "현상만 보지 않고 언제부터 다르게 동작했는지를 git 으로 거슬러 올라간다"

다른 도메인 개발자가 봐도 자기 도구로 치환해서 따라할 수 있는 형태.

## 사용법

### 사전 요구사항

- macOS 또는 Linux
- Claude Code 설치 + 한 번이라도 사용 (`~/.claude/projects/` 에 데이터 있음)
- Python 3.10+
- uv 또는 pip

### 설치 + 실행

```bash
git clone https://github.com/cobiyu-dev/claude-code-usage-analyzer
cd claude-code-usage-analyzer

# Python 의존성 설치 (시스템 Python 오염 방지를 위해 venv 권장)
python3 -m venv .venv
.venv/bin/pip install -e .
# 또는 uv 사용: uv venv && uv pip install -e .

# Claude Code 시작 (이 디렉토리 안에서)
claude

# 슬래시 호출
> /analyze-my-usage --last 4w
```

`scripts/preprocess.sh` / `postprocess.sh` 가 `./.venv/bin/python` 을 자동 감지해서 호출합니다.
다른 Python 인터프리터를 쓰고 싶으면 `CC_ANALYZER_PYTHON=/path/to/python` 환경변수로 지정.

첫 실행 시 4단계 설정 마법사 (도구 매핑 확인, 동료 이름 마스킹, 보고서 위치).
이후 실행부터는 바로 분석.

### 명령어 옵션

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
  --curated                       큐레이션 모드 (동료 직접 공유용, 5-8 패턴만)

(인자 없으면 인터랙티브)
```

### 두 가지 모드

- **디폴트 (광역)**: 사소한 패턴까지 다 보고서에 포함. 사용자가 첨삭 후 공유하는 운영 모델
- **`--curated`**: 핵심 5-8 패턴만. 동료에게 첨삭 없이 바로 공유할 때 사용

## 어떻게 동작하나

```
사용자: /analyze-my-usage --last 4w
   ↓
Stage A   파싱 + carve-out + 시크릿 마스킹       (코드, preprocess.sh)
   ↓
Stage B   에피소드 분할 + 자유 텍스트 라벨        (Claude 자신이 수행)
   ↓
Stage C   집계 + 시그니처 추출                    (코드, postprocess.sh)
   ↓
Stage D   패턴 추출 + 보고서 작성                 (Claude 자신이 수행)
   ↓
검증      시크릿/동료이름/도구표기 자동 검증
   ↓
저장      ~/Documents/claude-usage-reports/{period}.md
```

별도 API key 불필요. Claude Code 환경 안에서 LLM 호출이 처리됨.

## 보고서 예시

```markdown
# Claude Code 사용 패턴 분석

**기간**: 2026-04-20 ~ 2026-05-17 (4주)
**세션 수**: 47개
**에피소드 수**: 23개

## 주요 워크플로 패턴

### A. 정보 우선 (본격 작업 전 사실 데이터부터 확보)

#### 에러나 이상 신호가 보이면 관련 로그를 통째로 수집한 뒤 분석을 시작한다

운영 환경에서 에러나 특이사항이 발생하면 코드부터 보지 않고, 먼저
**grafana mcp(로그 검색 도구)**에서 관련 access log 키를 주고 한 번에
끌어와 전체를 훑은 뒤 본 작업에 들어간다. 가설을 좁힌 상태에서 코드를
보기 때문에 무관한 path를 헤매지 않게 됨.

#### 에러 디버깅 전 관련 기능의 정상 동작 설명을 먼저 만든다

...

### B. 도구 체이닝 (식별자로 도구 잇기)

...

## 시계열 추이

### W17 (2026-04-20 ~ 2026-04-26)
주로 프로덕션 디버깅. log_search 기능 빈도 높음. 주요 에피소드 3개.
...
```

## 디렉토리 구조

```
claude-code-usage-analyzer/
├── .claude/                        # Claude Code 설정 (slash + skill)
│   ├── commands/
│   │   └── analyze-my-usage.md
│   └── skills/
│       └── analyze-my-usage/
│           ├── SKILL.md
│           └── references/
│
├── scripts/                        # Stage A, C 코드
│   ├── preprocess.sh
│   ├── postprocess.sh
│   ├── stage_a.py
│   └── stage_c.py
│
├── config/                         # 시스템 기본 yaml (튜닝 X)
│   ├── function_groups.yaml
│   ├── carve_out_rules.yaml
│   ├── execution_keywords.yaml
│   ├── secret_patterns.yaml
│   ├── public_tools_whitelist.yaml
│   ├── split_signals.yaml
│   ├── outcome_signals.yaml
│   ├── git_intent_patterns.yaml
│   └── people_name_patterns.yaml
│
├── docs/                           # 설계 명세
│   ├── principles_user_agnostic.md     ← 시스템 약속 5개 (필독)
│   ├── pipeline_spec.md                ← 전체 흐름
│   ├── yaml_specs.md                   ← config 명세
│   ├── stage_a_spec.md
│   ├── stage_b_spec.md
│   ├── stage_c_spec.md
│   └── format_c_spec.md
│
├── pyproject.toml
└── README.md
```

사용자 데이터는 repo 밖:
- `~/.config/cc-analyzer/config.yaml` — 사용자별 설정
- `~/.cache/cc-analyzer/{period}/` — 중간 산출물
- `~/Documents/claude-usage-reports/` — 최종 보고서

## 약속 / 한계

### 약속

- **사내 공유 전용**: 회사 시스템명(WMS, OMS 등)을 마스킹하지 않음. 외부 공유 금지.
- **시크릿 자동 마스킹**: API 키, 토큰, 비밀번호 정규식 자동 검출.
- **동료 이름 마스킹** (디폴트 ON): 보고서에 "동료" 로 추상화. 옵션으로 끌 수 있음.
- **사용자 데이터로 알고리즘 튜닝 X**: 결과가 마음에 안 들어도 룰을 바꾸지 않음.

자세한 약속 5개: [docs/principles_user_agnostic.md](docs/principles_user_agnostic.md)

### 한계

- **macOS / Linux 만 지원** (Windows 미지원)
- **Claude Code 환경 필수**: 외부 API key 로 동작하지 않음
- **데이터 양 한계**: 너무 긴 기간 (예: 1년+) 은 컨텍스트 윈도우 초과 가능. 기간 좁혀서 시도.
- **결정론 보장 X**: LLM 호출 단계 (Stage B, D) 가 매번 약간 다른 결과 낼 수 있음.
- **사람 이름 자동 발견은 후보 제시 단계에서만 사용**: 영문 `@` 멘션 정규식이 Java 어노테이션(`@Transactional` 등)을 후보로 잡을 수 있음 — 첫 실행 마법사에서 사용자가 Y/n 선택하므로 최종 마스킹 결과엔 영향 없음.

## 개발 / 구현

이 시스템은 명세 기반으로 Claude Code 가 직접 구현하도록 설계됨.
구현 시 `docs/` 의 명세를 따른다.

구현 시작 시:
```bash
cd claude-code-usage-analyzer
claude

> 이 repo 의 docs/ 명세대로 구현해줘.
  순서:
  1. docs/principles_user_agnostic.md 먼저 읽기 (절대 약속)
  2. docs/pipeline_spec.md - 전체 구조
  3. docs/yaml_specs.md - config 형식
  4. docs/stage_a_spec.md, stage_c_spec.md - 구현할 코드
  
  Stage B, D 는 코드 아님. 
  .claude/skills/analyze-my-usage/SKILL.md 따라 Claude 가 수행.
```

자세한 구현 지시: 별도 프롬프트 참고.

## 라이선스

내부 사용. 외부 공개 시 보안팀 협의 필요.
