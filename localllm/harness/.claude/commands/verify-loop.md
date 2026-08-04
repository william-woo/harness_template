# /project:verify-loop — Loop 2 검증 루프 (claude.loope 전용)

LangChain "loop engineering" 의 **Loop 2(Verification Loop)** 를 하네스에 이식한 정형화 도구.
"Agent runs → output scored against a rubric → retried with feedback" 를 상태로 추적한다.

**claude.loope · localllm 변형 전용** (ADR-014 / ADR-017 loope 계보 승격). 다른 변형엔 verify_loop.py / rubrics 가 없어 미인식.

> 하네스는 이미 Reviewer→NEEDS REVISION→재시도 + 3회 에스컬레이션 규칙을 갖고 있었으나,
> **rubric 이 암묵적이고 재시도 상태가 코드화되지 않았다.** 이 도구가 그 둘을 명시적·유계로 만든다.
> (프레임워크를 새로 짓지 않음 — 이미 도는 루프를 bounded 하게: Karpathy 단순성.)

## 사용법

```bash
python3 .claude/bin/verify_loop.py start <F> --rubric code-review    # 루프 개시
python3 .claude/bin/verify_loop.py record <F> --grader lint --verdict pass
python3 .claude/bin/verify_loop.py record <F> --grader reviewer --verdict revision --must 1 --should 2 --notes "docstring 누락"
python3 .claude/bin/verify_loop.py record <F> --grader reviewer --verdict pass
python3 .claude/bin/verify_loop.py status <F>                        # 루프 상태·이력
python3 .claude/bin/verify_loop.py list                             # 진행중/완료 루프
python3 .claude/bin/verify_loop.py rubric [<name>]                  # rubric 표시/목록
python3 .claude/bin/verify_loop.py self                             # 점검
```

## grader 종류 (LangChain 차용)

| 종류 | grader | 특성 |
|---|---|---|
| **결정론(deterministic)** | lint · design-review · qa-browser · test | 프로그램이 pass/fail — 빠르고 값쌈, 먼저 게이트 |
| **judge (LLM-as-judge)** | reviewer · qa · architect | 에이전트가 rubric 으로 판단 |

→ 권장 순서: **결정론 grader 먼저 → judge 나중** (값싼 실패를 앞에서 걸러 judge 비용 절감).

## verdict → 상태 전이

| verdict | 의미 | 상태 |
|---|---|---|
| `pass` | rubric 충족 | `passed` |
| `revision` | MUST 미해결 → 재작업 | `in-loop` (revision_count++) |
| `fail` | 설계/방향 오류 | `failed` |
| revision **3회** 누적 | — | `escalated` (자동 — Planner+Architect 재검토 안내) |

## rubric

- `.claude/rubrics/code-review.md` — Reviewer 용 (MUST/SHOULD/CONSIDER)
- `.claude/rubrics/qa-acceptance.md` — QA 용 (acceptance_criteria 기반)
- 프로젝트에 맞게 편집/추가 가능 (`.claude/rubrics/<name>.md` → `--rubric <name>`)

## 호출 기준

- Reviewer/QA 가 판정을 내릴 때마다 `record` (reviewer.md/qa.md 에 연동됨)
- product-cycle 의 **검증(verify) 단계**에서 Reviewer→QA 게이트를 이 루프로 추적
- 재시도가 반복돼 에스컬레이션 여부를 객관적으로 판단하고 싶을 때

해당 없으면 (단순 1회 통과) 굳이 호출 안 해도 됨 — **옵셔널**. 상태 위치는 `.claude/state/verify-loop/` (런타임 gitignore).
