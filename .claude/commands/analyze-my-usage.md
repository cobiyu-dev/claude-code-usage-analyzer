---
description: Claude Code 사용 패턴을 분석해 보고서를 생성합니다.
---

`.claude/skills/analyze-my-usage/SKILL.md` 의 흐름대로 진행해주세요.

사용자 입력: `$ARGUMENTS`

지원 인자:

기간 옵션:
- `--last 1w` / `--last 4w` / `--last 1m` / `--last 3m`
- `--from YYYY-MM-DD --to YYYY-MM-DD`
- `--since YYYY-MM-DD`

부가 옵션:
- `--no-mask-names` — 동료 이름 마스킹 끄기 (이번 실행만)
- `--output <path>` — 보고서 저장 위치 (이번 실행만)
- `--reconfigure` — 첫 실행 마법사 재실행
- `--curated` — 큐레이션 모드 (5-8 패턴, 1회성 폐기, 동료 직접 공유용). 디폴트는 광역 모드.

인자가 비어있으면 SKILL.md 단계 1 에 따라 사용자에게 인터랙티브하게 묻기.
