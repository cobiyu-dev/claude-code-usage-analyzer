# Claude Code 구현 지시 프롬프트

이 파일은 새 Claude Code 세션에서 구현을 시작할 때 첫 메시지로 그대로 복사해 넣는 텍스트.

---

## 사용 방법

```bash
$ cd claude-code-usage-analyzer
$ claude
```

그리고 아래 텍스트를 복사해서 첫 메시지로 입력:

---

## (아래부터 복사)

이 repo 의 `docs/` 안 명세에 따라 시스템을 구현해줘.

## 먼저 읽어야 할 것 (이 순서대로)

1. **`docs/principles_user_agnostic.md`** — 절대 어겨선 안 되는 약속 5개. 매번 셀프 체크할 것.
2. **`docs/pipeline_spec.md`** — 전체 시스템 구조와 흐름.
3. **`docs/yaml_specs.md`** — config 파일들의 실제 형식.
4. **`docs/stage_a_spec.md`** — Stage A (파싱 + carve-out + 시크릿 마스킹) 알고리즘.
5. **`docs/stage_c_spec.md`** — Stage C (집계) 알고리즘.
6. **`docs/stage_b_spec.md`, `docs/format_c_spec.md`** — Stage B 와 Stage D 는 코드 X. Claude 가 SKILL.md 따라 수행. 참고만.

## 구현 순서

다음 10단계 순서로 진행. 각 단계 끝낼 때마다 약속 1-5 셀프 체크.

### 1. 디렉토리 구조 생성

`docs/pipeline_spec.md` 의 디렉토리 구조 그대로 만들기. 다음 디렉토리/파일 생성:
- `scripts/`, `scripts/lib/`
- `config/`
- `.claude/commands/`
- `.claude/skills/analyze-my-usage/references/`

### 2. `config/*.yaml` 6개 작성

`docs/yaml_specs.md` 에 박혀있는 yaml 내용을 **그대로** 파일로 만들기:
- `config/function_groups.yaml`
- `config/carve_out_rules.yaml`
- `config/execution_keywords.yaml`
- `config/secret_patterns.yaml`
- `config/public_tools_whitelist.yaml`
- `config/split_signals.yaml`

**중요**: 값을 임의로 바꾸지 말 것. yaml_specs.md 그대로.

### 3. `pyproject.toml` 작성

`docs/pipeline_spec.md` 의 의존성 명세대로:
```toml
[project]
name = "cc-analyzer-scripts"
version = "0.1.0"
requires-python = ">=3.10"
dependencies = [
    "pandas",
    "pyarrow",
    "pyyaml",
]
```

### 4. `scripts/stage_a.py` 작성

`docs/stage_a_spec.md` 명세 그대로:
- jsonl 파싱 (`~/.claude/projects/**/*.jsonl`)
- 도구 → 기능 그룹 매핑 (사용자 config 의 `tool_function_mapping` 사용)
- 기능 그룹별 carve-out 룰 적용 (`config/carve_out_rules.yaml`)
- Bash, Read 출력 유형 분류 (5가지)
- 시크릿 정규식 마스킹 (`config/secret_patterns.yaml`)
- 결과를 turns.parquet 으로 저장

CLI:
```bash
python3 scripts/stage_a.py \
  --from 2026-04-20 \
  --to 2026-05-17 \
  --config ~/.config/cc-analyzer/config.yaml \
  --output ~/.cache/cc-analyzer/{period}/turns.parquet
```

### 5. `scripts/stage_c.py` 작성

`docs/stage_c_spec.md` 명세 그대로:
- episodes.parquet 읽기
- situation_cluster 기준 그룹화
- 그룹별 메트릭 계산
- n-gram 시그니처 시퀀스 추출 (n=2,3,4)
- 메타 정보 집계
- 시계열 데이터 (기간 ≥ 2주)
- aggregated.json 저장

CLI:
```bash
python3 scripts/stage_c.py \
  --episodes ~/.cache/cc-analyzer/{period}/episodes.parquet \
  --output ~/.cache/cc-analyzer/{period}/aggregated.json
```

### 6. `scripts/preprocess.sh`, `scripts/postprocess.sh` 작성

`docs/pipeline_spec.md` 의 4번, 5번 섹션 그대로.
실행 가능하게 chmod +x.

### 7. `.claude/commands/analyze-my-usage.md` 작성

`docs/pipeline_spec.md` 의 CLI 인자 명세 기반.
슬래시 커맨드는 짧게 — skill 호출 + 인자 파싱만.

### 8. `.claude/skills/analyze-my-usage/` 작성

`SKILL.md` 와 `references/` 4개 파일.

**중요**: 이 5개 파일은 이미 우리가 설계해놨음. 다음 위치의 내용을 가져와서:
- `SKILL.md` ← (별도 제공된 SKILL.md 그대로)
- `references/first_time_setup.md` ← (별도 제공)
- `references/stage_b_workflow.md` ← (별도 제공)
- `references/stage_d_workflow.md` ← (별도 제공)
- `references/format_c.md` ← (별도 제공)

만약 위 5개 파일이 repo 에 이미 있다면 그대로 두기. 없으면 docs/ 에 있는 spec 들 참고해서 작성.

### 9. `README.md` 확인

이미 작성돼있는지 확인. 없으면 작성. (별도 제공된 README.md 사용)

### 10. 자가 테스트

본인(코비) 의 4주치 데이터로 실행:
```bash
$ /analyze-my-usage --from 2026-04-20 --to 2026-05-17
```

다음 확인:
- 각 단계가 막힘 없이 진행되는지
- 보고서가 `~/Documents/claude-usage-reports/2026-04-20_to_2026-05-17.md` 에 생성되는지
- 보고서 내용이 `docs/format_c_spec.md` 형식과 일치하는지
- 시크릿/동료이름 누출 없는지

## 절대 지킬 약속

`docs/principles_user_agnostic.md` 의 5개 약속. 매 단계 끝나면 셀프 체크:

1. **본인 데이터 보고 튜닝 X**: 결과 이상해도 알고리즘 안 고침. 가정 어디 틀렸는지 추적.
2. **사람마다 다른 정보는 코드에 박지 마**: 도구 이름, 카테고리 등은 자동 발견 또는 사용자 입력.
3. **다른 사람이 검증 직접 해야 한다면 실패**: 사용자는 보고서만 받음. 손라벨링 X.
4. **사내 공유 전용**: 회사 시스템명 마스킹 X (그대로 노출). 시크릿/동료 이름은 자동 마스킹.
5. **헷갈리면 질문 4개**: 다른 사람한테도 적용 가능? 출발점이 본인 데이터? 코드 밖으로 뺄 수 있나? 다른 직군에도 작동?

## 자주 헷갈릴 만한 것 미리 짚음

### Stage B, D 는 코드 X

이 둘은 Claude(너 자신)가 SKILL.md 따라 수행하는 단계. `.py` 파일 만들지 말 것.

### 사용자 config vs 시스템 config

- **시스템 config (repo 내 `config/*.yaml`)**: yaml_specs.md 그대로. 사용자가 안 건드림.
- **사용자 config (`~/.config/cc-analyzer/config.yaml`)**: 첫 실행 마법사가 생성. 사용자별로 다름.

### LLM 호출 X

Stage A, C 는 LLM 안 부름. Stage B, D 도 외부 API 호출 X (Claude Code 환경 안에서 처리됨).
`anthropic` 라이브러리 사용 X. `ANTHROPIC_API_KEY` 환경변수 사용 X.

### 숫자값은 yaml 에서

carve-out 룰의 숫자 (첫 3개, 첫 10라인, 첫 300자 등) 모두 yaml 에 있음.
Python 코드에 박지 말 것. yaml 읽어서 사용.

### "느슨한 그룹화" 의미

Stage D 에서 패턴들을 강제 그룹화 X. 자연스럽게 3개 이상 그룹 형성되면 그룹화, 아니면 평탄.
판정은 Claude(너 자신)가 함.

## 막혔을 때

- 명세에 명확히 안 적힌 부분이 있으면 docs/ 의 어떤 파일 참고하면 좋을지 알려줘.
- 약속 1-5 와 충돌하는 결정 필요하면 멈추고 사용자에게 물어볼 것.
- 본인(코비) 데이터로 돌렸을 때 결과가 이상하면 약속 1 적용: 알고리즘 안 고치고 가정 어디가 틀렸는지 추적해서 보고.

## 끝났을 때

10단계 끝나면:
1. 4주치 본인 데이터로 한 번 돌려본 결과 알려줘 (보고서 일부 + 막혔던 점)
2. 약속 1-5 위반 없었는지 회고
3. 발견한 명세 모호한 부분 정리 (다음 세션에서 보완)

## (위까지 복사)
