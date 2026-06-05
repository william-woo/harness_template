<!-- AUTO-GENERATED — 손으로 수정하지 말 것 -->
<!-- python3 .claude/bin/lint.py regenerate-index 로 재생성 -->

# 프로젝트 산출물 인덱스

자동 생성됨. 손으로 수정하지 말 것 — `python3 .claude/bin/lint.py regenerate-index` 로 재생성.
마지막 갱신: 2026-05-21T07:09:30+09:00

## Features

| ID | 상태 | 우선순위 | 제목 |
|---|---|---|---|
| F001 | done | critical | Phase 1 — Safety Guards + Learn + Context Save/Restore |
| F002 | done | high | Phase 2 — Autoplan 커맨드 (/project:plan-full) |
| F003 | done | high | Phase 2 — Review Readiness Dashboard (/project:ship) |
| F004 | done | medium | Phase 2 — Retro + Analytics (/project:retro) |
| F005 | done | medium | Phase 3 — Brain Local (SQLite 기반 영구 지식) |
| F006 | done | low | Phase 3 — 멀티 호스트 아키텍처 준비 |
| F007 | done | low | Phase 4 — Design Review 강화 (단계 1) |
| F008 | done | low | Phase 4 — QA 브라우저 자동화 스킬 |
| F009 | done | medium | Phase 5 — LLM Wiki 패턴 (lint + index) |

## ADR (Architecture Decision Records)

| 번호 | 상태 | 제목 | 관련 feature |
|---|---|---|---|
| ADR-001 | accepted | 멀티 호스트 아키텍처 준비 (claude-code / openclaw / codex) | F005, F006 |
| ADR-002 | accepted | Design Review 강화 (단계 1) — 메타-하네스 제공 모델 결정 | F003, F005, F006, F007, F008, F009 |
| ADR-003 | accepted | QA 브라우저 자동화 (Playwright) — 옵셔널 의존성 + 메타-하네스 듀얼 모드 | F003, F004, F005, F006, F007, F008, F009 |
| ADR-004 | accepted | LLM Wiki 패턴 (lint + index) — 정합성 헬스체크 + 산출물 카탈로그 | F001, F003, F005, F006, F007, F008, F009 |

## Design Documents

| 파일 | 관련 feature |
|---|---|
| F007-design-review-checklist.md | F007 |
| F008-qa-browser-templates.md | F008 |

## Agents

architect / developer / planner / qa / reviewer (5종)
각각 [.claude/agents/](.claude/agents/)에 정의.

## Skills

| 이름 | 설명 |
|---|---|
| coding | 코드 구현 시 참조하는 스킬. Developer 에이전트가 기능을 구현할 때 사용한다. |
| design-review | 디자인 감사 스킬. 다운스트림 프로젝트의 UI/문서 또는 하네스 자체의 정합성을 |
| planning | 프로젝트 기획 및 feature_list.json 관리 스킬. Planner 에이전트가 사용한다. |
| qa-browser | QA 브라우저 자동화 스킬. acceptance_criteria 자연어를 Playwright 스크립트 템플릿으로 |
| testing | E2E 테스트 및 인수 검증 스킬. QA 에이전트가 기능 완료 여부를 검증할 때 사용한다. |

## Commands

21종의 슬래시 커맨드 — [.claude/commands/](.claude/commands/)

| 카테고리 | 커맨드 |
|---|---|
| 세션 | init-project, start-session, handoff, status |
| 안전 | freeze, unfreeze, guard |
| 학습 | learn, context-save, context-restore |
| 자동화 | plan-full, ship, retro, lint |
| 영구지식 | brain-sync, brain-search, brain-stats, brain-list |
| 호스트 | host |
| 감사 | design-review, qa-browser |

## Learnings 통계

총 43건 — pattern: 18 / pitfall: 7 / architecture: 10 / preference: 6 / decision: 2

최근 5건:
- [pattern] subprocess-external-tool-detection: 외부 도구(node/npx) 감지는 subprocess.run() + try/except(FileNotFoundError, TimeoutE... (F008)
- [architecture] atomic-loop-simulate-before-playwright: Playwright 미설치 환경에서도 원자적 루프 인터페이스를 simulate_atomic_loop()로 dry-run 가능하다. 실제 실... (F008)
- [architecture] design-review-cmd-plus-skill-not-agent: design-review는 Reviewer를 보완하는 별도 영역(IA/A11Y/일관성) 검사 도구다. 에이전트 신설이 아닌 커맨드+스킬 조... (F007)
- [pattern] atomic-fix-loop-1-block-1-call: 원자적 수정 루프 — BLOCK N건 = Developer N회 호출 (직렬). 한 번에 한 수정으로 변경 범위를 명확히 하고 회귀 원인 ... (F007)
- [pitfall] design-review-self-vs-downstream-mode-confusion: design-review 셀프 모드와 다운스트림 모드는 체크리스트 항목이 다르다 (A11Y 전체 N/A, IA/CON 항목도 부분 대체).... (F007)
