# Rubric — qa-acceptance (QA grader, LLM-judge)

> Loop 2 검증 rubric. QA 에이전트가 feature 의 `acceptance_criteria` 를 이 항목으로 검증하고,
> `verify_loop.py record <F> --grader qa --verdict <pass|revision|fail>` 로 기록한다.
> grader 종류: **judge**. `passes: true` 권한은 QA 단독 — pass 시에만 설정.

## MUST (미충족 시 revision/fail)

- [ ] acceptance_criteria — feature_list.json 의 모든 항목 충족 (부분 동작 = PASS 아님)
- [ ] E2E 동작 — 실제 실행 경로에서 기대 결과 확인
- [ ] 엣지 케이스 — 빈 입력·경계값·오류 경로 검증
- [ ] 회귀 없음 — 기존 기능 파손 없음
- [ ] (해당 시) qa-browser — URL/폼/텍스트/라우팅 기준은 Playwright 로 검증

## 판정 규칙

| 조건 | verdict | 후속 |
|---|---|---|
| 모든 acceptance_criteria 충족 | `pass` | `passes: true` + `status: done` |
| 일부 미충족 (수정 가능) | `revision` | Developer 재작업 (revision_count++) |
| 인수 기준 자체 오류/구현 방향 오류 | `fail` | Planner/Architect 재검토 |

## 결정론 grader 연계 (deterministic)

QA 판정 전, 결정론 grader 를 먼저 통과시키는 것을 권장 — 각각 `record` 로 기록:
- `lint` (거버넌스 정합성) · `design-review` (IA/A11Y/CON) · `qa-browser` (E2E 렌더)

> 결정론 grader 는 프로그램이 pass/fail 을 내므로 judge 보다 먼저 게이트한다 (빠르고 값쌈).
