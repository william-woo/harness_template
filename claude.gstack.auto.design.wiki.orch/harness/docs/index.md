<!-- AUTO-GENERATED — 손으로 수정하지 말 것 -->
<!-- python3 .claude/bin/lint.py regenerate-index 로 재생성 -->

# 프로젝트 산출물 인덱스

자동 생성됨. 손으로 수정하지 말 것 — `python3 .claude/bin/lint.py regenerate-index` 로 재생성.
마지막 갱신: 2026-06-06T04:12:43+09:00

## Features

| ID | 상태 | 우선순위 | 제목 |
|---|---|---|---|
| F001 | todo | critical | 프로젝트 환경 설정 |
| F002 | todo | critical | [주요 기능 1] |
| F003 | todo | high | [주요 기능 2] |

## ADR (Architecture Decision Records)

| 번호 | 상태 | 제목 | 관련 feature |
|---|---|---|---|
| ADR-001 | accepted | 멀티 호스트 아키텍처 준비 (claude-code / openclaw / codex) | — |
| ADR-002 | accepted | Design Review 강화 (단계 1) — 메타-하네스 제공 모델 결정 | F003 |
| ADR-003 | accepted | QA 브라우저 자동화 (Playwright) — 옵셔널 의존성 + 메타-하네스 듀얼 모드 | F003 |
| ADR-004 | accepted | LLM Wiki 패턴 (lint + index) — 정합성 헬스체크 + 산출물 카탈로그 | F001, F003 |
| ADR-005 | accepted | 다운스트림 백업 동기화 (`/project:backup-sync`) | F001 |
| ADR-006 | accepted | Design-Pick 자동화 + `claude.gstack.auto.design` 변형 신설 | F001 |
| ADR-007 | proposed | LLM Wiki 지식 그래프 + `claude.gstack.auto.design.wiki` 변형 + 외부 의존성 정책 예외 | F001, F002 |
| ADR-008 | accepted | 이종 에이전트 오케스트레이션 (supervisor pattern) + `claude.gstack.auto.design.wiki.orch` 변형 + d-1/d-2/d-3 경계 | F001, F002 |

## Design Documents

| 파일 | 관련 feature |
|---|---|
| F007-design-review-checklist.md | — |
| F008-qa-browser-templates.md | — |
| F011-tokens-schema.md | — |

## Agents

architect / designer / developer / gatekeeper / planner / qa / researcher / reviewer (8종)
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

25종의 슬래시 커맨드 — [.claude/commands/](.claude/commands/)

| 카테고리 | 커맨드 |
|---|---|
| 세션 | init-project, start-session, handoff, status |
| 안전 | freeze, unfreeze, guard |
| 학습 | learn, context-save, context-restore |
| 자동화 | plan-full, ship, retro, lint |
| 영구지식 | brain-sync, brain-search, brain-stats, brain-list |
| 호스트 | host |
| 감사 | design-review, qa-browser |
| 기타 | backup-sync, design-pick, orchestrate, wiki |

## Learnings 통계

learnings.jsonl 없음 또는 비어있음.
