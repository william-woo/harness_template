# Rubric — code-review (Reviewer grader, LLM-judge)

> Loop 2 검증 rubric. Reviewer 에이전트가 이 항목으로 채점하고,
> `verify_loop.py record <F> --grader reviewer --verdict <pass|revision> --must N --should N` 로 기록한다.
> grader 종류: **judge** (에이전트 판단). MUST 1건이라도 미해결이면 `revision`.

## MUST (미해결 시 revision — 반드시 수정)

- [ ] docstring/JSDoc — 함수·클래스에 존재
- [ ] 단위 테스트 — 새 기능/변경에 포함, 통과
- [ ] 에러 처리 — 외부 I/O·API·사용자 입력 경계에서 방어 (에러 삼킴 금지)
- [ ] 보안 — 자격증명 하드코딩 없음, 입력 검증
- [ ] Surgical Changes — 무관한 대량 변경·리포맷 섞이지 않음
- [ ] 계약 준수 — 변형별 외부 의존성 정책(zero-dep 등) 위반 없음

## SHOULD (강력 권장 — revision 사유 아니나 기록)

- [ ] 네이밍 — 의도가 드러나는 이름 (Boolean is/has/can)
- [ ] 함수 크기 — 40줄 이하 권장 / 단일 책임
- [ ] 중복 — 3회 이상 반복 시 추상화 (단, 추측 추상화 금지)
- [ ] 주석 — why 위주 (what 아님)

## CONSIDER (제안)

- [ ] 성능 — N+1·불필요한 순회
- [ ] 가독성 — 조기 반환, 중첩 축소

## 판정 규칙

| 조건 | verdict |
|---|---|
| MUST 전부 해결 | `pass` → status: qa 로 전환 |
| MUST 1건 이상 미해결 | `revision` → Developer 재구현 (revision_count++) |
| 설계 자체가 부적합 | `fail` (REJECTED) |

> revision 3회 누적 시 verify_loop 가 자동 **ESCALATION** — Planner+Architect 재검토.
