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

### 2. `config/*.yaml` 9개 작성

`docs/yaml_specs.md` 에 박혀있는 yaml 내용을 **그대로** 파일로 만들기:
- `config/function_groups.yaml`
- `config/carve_out_rules.yaml`
- `config/execution_keywords.yaml`
- `config/secret_patterns.yaml`
- `config/public_tools_whitelist.yaml`
- `config/split_signals.yaml`
- `config/outcome_signals.yaml`          ← 신규 (에피소드 종결 신호)
- `config/git_intent_patterns.yaml`      ← 신규 (git 명령 의도 분류)
- `config/people_name_patterns.yaml`     ← 신규 (사람 이름 자동 발견)

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
- 사람 이름 자동 발견 (`config/people_name_patterns.yaml`) — 첫 실행 마법사용 후보 목록만 산출
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
- 그룹별 메트릭 계산 (대표 에피소드 선정에 phase/outcome/git_intent 보너스 적용)
- **phase·outcome·git 의도 집계** (작업 2.5) — 그룹별 phase_function_groups, outcome_distribution, git_intent_distribution, episode_kind_distribution 등
- n-gram 시그니처 시퀀스 추출 (n=2,3,4) + **phase 분리 시그니처**
- **turn 단위 미니 패턴 후보 추출** (작업 3.5) — 광역 모드일 때만. tool_microsequences / user_utterance_trigrams / tool_arg_patterns
- 메타 정보 집계
- 시계열 데이터 (기간 ≥ 2주)
- aggregated.json 저장

CLI:
```bash
python3 scripts/stage_c.py \
  --episodes ~/.cache/cc-analyzer/{period}/episodes.parquet \
  --output ~/.cache/cc-analyzer/{period}/aggregated.json \
  --mode broad   # default. --mode curated 면 미니 패턴 후보 추출 건너뜀
```

### 6. `scripts/preprocess.sh`, `scripts/postprocess.sh` 작성

`docs/pipeline_spec.md` 의 4번, 5번 섹션 그대로.
실행 가능하게 chmod +x.

### 7. `.claude/commands/analyze-my-usage.md` 작성

`docs/pipeline_spec.md` 의 CLI 인자 명세 기반.
슬래시 커맨드는 짧게 — skill 호출 + 인자 파싱만.

인자 목록:
- 기간: `--last N(w|m)`, `--from/--to`, `--since`
- 부가: `--no-mask-names`, `--output`, `--reconfigure`, `--curated`

**`--curated`**: 큐레이션 모드. 전체 5-8개 패턴만, 1회성 폐기. 동료 직접 공유용.
디폴트는 광역 모드 (상한 없음, 사용자가 첨삭).

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

본인(코비) 의 4주치 데이터로 광역 모드(디폴트) + 큐레이션 모드 양쪽 실행:
```bash
$ /analyze-my-usage --from 2026-04-20 --to 2026-05-17
$ /analyze-my-usage --from 2026-04-20 --to 2026-05-17 --curated
```

다음 확인:
- 각 단계가 막힘 없이 진행되는지
- 보고서가 `~/Documents/claude-usage-reports/` 에 생성되는지
- 보고서 내용이 `docs/format_c_spec.md` 형식과 일치하는지
- 시크릿/동료이름 누출 없는지
- 광역 모드에서 도입부뿐 아니라 종료부(verified_by_data/run, commit/PR)·시간축 진단(git diagnostic)·turn 단위 미니 패턴까지 잡히는지
- 큐레이션 모드에서 패턴 수가 5-8 로 줄고, 1회성/도메인 특화가 빠지는지
- 첫 실행 마법사에서 분류 모호 도구가 `other` 로 자동 폴백되는지 (사용자에게 강제 선택 X)

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

### 광역 모드 vs --curated 모드

- **디폴트는 광역 모드**. 패턴 개수 상한 X, 1회성/도메인 특화도 후보 유지, turn 단위 미니 패턴 후보 추출 ON
- **`--curated`**: 5-8 패턴 상한, 1회성 폐기, 미니 패턴 후보 OFF
- 사용자 데이터로 광역 모드 돌렸을 때 패턴이 10개 넘게 나오는 게 정상. "많아 보여서 자르고 싶다" 는 약속 1 위반 — 사용자가 첨삭함

### 에피소드 내부 구조 라벨 (phase / outcome / git_intent / episode_kind)

Stage B 단계 3.5 에서 부여. 모두 휴리스틱·yaml 매칭. LLM 호출 X.

- `phase`: intro / main / verify
- `outcome`: committed / pushed / pr_opened / verified_by_data / verified_by_run / delegated_and_reported / abandoned_or_paused / incremental_commits / single_final_commit / pr_with_structured_body
- `git_intents_used`: diagnostic / output / transition
- `episode_kind`: with_changes / investigation_only / tooling_only

이 라벨들은 Stage D 가 도입부 편향에서 벗어나 종료부·시간축 진단 패턴을 잡게 하기 위한 신호.

### 자가 검증할 때 자주 흔들리는 지점 (약속 1 함정)

본인 데이터 결과를 보고 다음 유혹이 생길 수 있음. **모두 위반:**

- ❌ "내 데이터에 `git bisect` 가 0회네. yaml 에서 빼자"
- ❌ "내 데이터엔 `pr_with_structured_body` 가 안 잡히네. 정규식 더 느슨하게"
- ❌ "split_signals 의 20분이 너무 크네. 5분으로 줄이자"
- ❌ "미니 패턴 trigram 빈도가 너무 적네. 임계값 1 → 3 으로"

`docs/principles_user_agnostic.md` 의 "yaml 룰 깎기 함정" 섹션 참고. 결과가 이상하면 **알고리즘이 아니라 가정 어디가 틀렸는지** 추적.

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
