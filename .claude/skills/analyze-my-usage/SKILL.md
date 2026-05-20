---
name: analyze-my-usage
description: Claude Code 사용 패턴을 분석하고 보고서를 생성. 
  사용자가 /analyze-my-usage 슬래시를 호출했을 때 사용. 
  ~/.claude/projects/ 의 jsonl 대화 기록을 입력으로 받아, 
  특정 기간의 워크플로 패턴을 도메인 무관한 형태로 추출한 사내 공유용 보고서를 생성.
---

# Claude Code 사용 패턴 분석기

## 목적

사용자의 Claude Code 대화 기록을 분석해 "이런 상황에선 보통 이렇게 한다"
같은 메서드러지 패턴을 자동으로 문서화. 도메인과 무관한 사내 공유용 보고서를 생성.

회사 내부 시스템명(WMS, OMS 등)은 그대로 노출(사내 공유 전용),
시크릿/동료 이름은 마스킹.

## 전체 흐름

```
1. 인자 확인 → 기간 결정
2. 첫 실행 vs 일반 실행 분기
3. Stage A 실행 (Bash로 preprocess.sh) → turns.parquet
4. Stage B 처리 (Claude 자신이) → episodes.parquet
5. Stage C 실행 (Bash로 postprocess.sh) → aggregated.json
6. Stage D 처리 (Claude 자신이) → 보고서 작성
7. 보고서 검증 + 저장
8. 에러 처리 (각 단계에서 막힐 때)
```

각 단계에서 무엇이 일어나는지 사용자에게 짧게 알린다.

---

## 단계 1: 기간 결정

슬래시 인자에서 기간을 받는다:
- `--last 1w` / `--last 4w` / `--last 1m` / `--last 3m`
- `--from YYYY-MM-DD --to YYYY-MM-DD`
- `--since YYYY-MM-DD` (해당 날짜부터 오늘까지)

**인자가 없으면 사용자에게 묻는다 (인터랙티브):**

```
분석 기간을 선택하세요:
  1. 지난 1주
  2. 지난 4주 (추천)
  3. 지난 한 달
  4. 지난 분기
  5. 직접 입력 (YYYY-MM-DD 형식)
```

선택받은 결과를 `period` 변수로 보관 (start_date, end_date).

---

## 단계 2: 첫 실행 vs 일반 실행 분기

`~/.config/cc-analyzer/config.yaml` 확인:

- **파일 없음** → 첫 실행 마법사 (references/first_time_setup.md 따르기)
- **파일 있음 + 필수 필드 모두 있음** → 일반 실행, 기존 config 로드
- **파일 있음 + 필수 필드 빠짐** → 첫 실행 마법사 (config 손상으로 간주)

필수 필드:
```yaml
tool_function_mapping: {...}      # 도구→기능 그룹 매핑 (필수)
mask_people_names: bool            # 동료 이름 마스킹 옵션 (필수)
people_names: [...]                # 마스킹할 동료 이름 (mask_people_names=true 일 때 필수)
output_dir: str                    # 보고서 저장 위치 (필수)
```

`--reconfigure` 인자가 있으면 항상 마법사 실행 (사용자 명시적 재설정).

---

## 단계 3: Stage A 실행 (전처리)

Bash 도구로 preprocess.sh 호출:

```bash
./scripts/preprocess.sh \
  --from {period.start_date} \
  --to {period.end_date} \
  --config ~/.config/cc-analyzer/config.yaml
```

preprocess.sh는:
1. Stage A 실행 → ~/.cache/cc-analyzer/{period}/turns.parquet
2. 진행 상황 stdout 출력

**사용자에게 알림 예시:**
```
[Stage A 실행 중...] jsonl 파싱 + carve-out + 시크릿 마스킹
✓ 1247 turns 처리
```

오류 발생 시 단계 8(에러 처리)로.

---

## 단계 4: Stage B 처리 (에피소드 분할 + 라벨)

`references/stage_b_workflow.md` 의 지시를 따른다.

큰 흐름:
1. turns.parquet 읽기
2. 휴리스틱 1차 분할
3. 각 에피소드에 자유 텍스트 라벨 생성 + goal 한 줄
4. LLM 양방향 판단 (합칠지/끊을지/유지)
5. 라벨 사후 클러스터링
6. episodes.parquet 저장

이 단계는 Claude(자신)가 수행. 외부 API 호출 없음.

**사용자에게 알림 예시:**
```
[Stage B 처리 중...] 에피소드 분할 + 라벨
✓ 23 에피소드 (4개 클러스터로 묶임)
```

---

## 단계 5: Stage C 실행 (집계)

Stage B 끝난 직후, Bash 도구로 postprocess.sh 호출:

```bash
./scripts/postprocess.sh \
  --episodes ~/.cache/cc-analyzer/{period}/episodes.parquet \
  --output ~/.cache/cc-analyzer/{period}/aggregated.json
```

postprocess.sh는:
1. Stage C 실행 → ~/.cache/cc-analyzer/{period}/aggregated.json
2. 진행 상황 stdout 출력

**사용자에게 알림 예시:**
```
[Stage C 실행 중...] 그룹별 메트릭 + 시그니처 시퀀스 + 메타 집계
✓ aggregated.json 생성
```

오류 발생 시 단계 8(에러 처리)로.

---

## 단계 6: Stage D 처리 (보고서 생성)

`references/stage_d_workflow.md` 와 `references/format_c.md` 를 따른다.

큰 흐름:
1. episodes.parquet + aggregated.json 읽기
2. 각 그룹에서 패턴 5-8개 추출 (도메인 무관한 메서드러지 패턴)
3. 느슨한 그룹화 판정 (3개 이상 자연 그룹 형성 시 그룹화)
4. 시계열 추이 (기간 ≥ 2주일 때)
5. 메타 정보 (자주 쓰는 기능/도구 top N)
6. 보고서 마크다운 생성

**사용자에게 알림 예시:**
```
[Stage D 처리 중...] 패턴 추출 + 보고서 작성
✓ 6개 패턴 (3개 그룹) + 시계열 추이
```

---

## 단계 7: 보고서 검증 + 저장

생성된 보고서를 바로 최종 위치에 쓰지 않는다. 임시 위치에 작성 후 검증 통과해야 최종 저장.

### 검증 흐름

1. 보고서를 임시 위치에 작성: `~/.cache/cc-analyzer/{period}/report_draft.md`

2. 자동 검증 3가지 (Format C 명세):
   - **시크릿 패턴** (CRITICAL): config/secret_patterns.yaml 정규식 매칭
   - **동료 이름** (WARN): config.people_names 검출 (mask_people_names=true 일 때만)
   - **일반 도구 첫 등장 시 인라인 괄호 누락** (WARN)

3. 처리:
   - CRITICAL → 보고서 재작성 시도 (1회). 재시도 후에도 남으면 보고서 폐기 + 사용자에게 알림 (단계 8)
   - WARN (동료 이름) → 자동 치환 (이름 → "동료")
   - WARN (괄호 누락) → 자동 보완 (config/function_groups.yaml 의 기능 설명 가져와 괄호 추가)

4. 검증 통과 → 최종 저장:
   `{config.output_dir}/{period.start}_to_{period.end}.md`

**사용자에게 알림 예시:**
```
[검증 중...]
✓ 시크릿 검출 없음
✓ 동료 이름 마스킹 2건 (코비 → 동료, 영희 → 동료)
✓ 도구 표기 보완 1건 (datadog mcp → datadog mcp(분산 trace 분석 도구))
```

---

## 단계 8: 에러 처리

각 단계에서 막힐 때 사용자에게 명확히 알린다. 회복 가능하면 회복 시도, 아니면 명확히 실패 보고.

### 단계별 실패 처리

**단계 1 (기간 결정) 실패:**
- 인자 형식 오류 → 올바른 형식 안내 후 재입력 요청
- 미래 날짜 → 경고하고 오늘까지로 자동 조정 제안

**단계 2 (분기) 실패:**
- config.yaml 파싱 오류 → 사용자에게 보여주고 마법사 재실행 제안

**단계 3 (Stage A) 실패:**
- preprocess.sh 종료 코드 != 0 → stderr 사용자에게 보여줌
- jsonl 디렉토리 없음 → Claude Code 처음 사용한 경우일 수 있음을 안내
- Python 의존성 부족 → install 가이드 (`uv pip install -r requirements.txt`)
- 해당 기간의 jsonl 파일 0개 → 친절히 안내, 다른 기간 시도 권유

**단계 4, 6 (Stage B / Stage D) 실패:**
- Claude 본인이 컨텍스트 윈도우 초과 등으로 막힘 → 기간 좁혀서 재시도 권유
- 부분 결과만 있는 경우 → 사용자에게 알리고 부분 보고서 생성할지 묻기

**단계 5 (Stage C) 실패:**
- postprocess.sh 종료 코드 != 0 → stderr 사용자에게 보여줌
- episodes.parquet 형식 오류 → Stage B 결과 확인 권유

**단계 7 (검증) 실패:**
- CRITICAL 시크릿 검출 → 보고서 폐기, 의심 위치 사용자에게 알림:
  ```
  ⚠️ 보고서 생성 중 시크릿으로 의심되는 패턴이 검출됐습니다.
     재시도했지만 여전히 남아있어 보고서를 폐기했습니다.
     
     검출된 패턴: API_KEY 패턴 (위치: 23번 turn)
     원본 데이터 확인: ~/.claude/projects/
     
     조치:
     - 해당 turn 직접 확인
     - 추가 시크릿 패턴이 필요하면 config/secret_patterns.yaml 에 추가
  ```

### 일반 원칙
- 막혔으면 솔직하게 막혔다고 알리기. "어떻게든 진행" 금지.
- 중간 산출물은 `~/.cache/cc-analyzer/{period}/` 에 남겨둠 → 디버깅용
- 부분적 성공도 보고 (예: "Stage A까지는 됐는데 Stage B에서 막힘")

---

## 셀프 체크 (작업 끝났을 때 자체 점검)

보고서 생성 후 한 번 더 확인:

**약속 1 (튜닝 X)**
- 분석 중 본인이 본 패턴이 마음에 안 들어서 룰을 바꾼 적 있나?
- 없음 → OK

**약속 2 (코드에 박지 마)**
- 분석 중 발견한 새 카테고리/기능을 SKILL.md 나 yaml 에 박은 적 있나?
- 없음 → OK

**약속 3 (다른 사람 검증 강제 X)**
- 사용자에게 손라벨링 같은 검증 작업 강제하지 않았나?
- 없음 → OK

**약속 4 (정보 안 새기)**
- 시크릿/동료 이름이 최종 보고서에 남아있나?
- 자동 검증 통과 → OK

**약속 5 (일반화 강건성)**
- 이 흐름을 다른 직군 (프론트엔드, 디자이너) 에게 줘도 작동할까?
- 도구 매핑이 일반화돼있음, 카테고리도 자유 텍스트 → OK
