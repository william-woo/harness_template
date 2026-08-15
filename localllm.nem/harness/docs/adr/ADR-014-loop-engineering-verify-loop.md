# ADR-014: `claude.loope` 변형 — Loop 2(검증 루프) 정형화

> Feature: F020 — Phase 15 `claude.loope` 변형
> 상태: `Accepted` (구현 — verify_loop.py + rubrics + reviewer/qa/product-cycle 연동)
> 관련: ADR-011(productmgr/product-cycle), LangChain "The Art of Loop Engineering"

## 맥락

LangChain 의 **loop engineering**("the art of stacking loops", Swyx)은 에이전트 위에 4개 루프를
쌓는 규율이다: ① Agent Loop ② Verification Loop ③ Event-Driven Loop ④ Hill-Climbing Loop (+ HITL).

우리 하네스를 이 렌즈로 보면 **4개 루프를 이미 다른 기질(Markdown 에이전트 + stdlib)로 갖고 있다**:
- ① = host(Claude Code/OpenCode)가 제공 · ③ = 훅/consortium/`/loop` · ④ = retro/learn/skill_forge/brain
- **HITL = Autonomous Mode #1/#2/#3 + Gatekeeper**

유일하게 **비정형**인 것이 ② **Verification Loop** 다. 하네스엔 Reviewer→NEEDS REVISION→재시도 +
QA 게이트 + "3회 에스컬레이션" 규칙이 있으나, **rubric 이 산문에 암묵적이고 재시도 상태가 코드화되지
않았다**. LangChain 은 이걸 `RubricMiddleware` + grader(결정론 or LLM-judge)로 정형화한다.

## 결정

### 결정 1 — 새 변형 `claude.loope` = productmgr 복사 + loop 오버레이
Loop 2 의 대상(Reviewer→QA 검증)이 이미 `product-cycle` 의 **검증(verify) 단계**에 있으므로,
productmgr 를 복사(auto+design+wiki+orch+hermes+pm 상속)해 그 위에 정형화를 얹는다.
(consortium 이 없는 productmgr 가 base — Loop 2 와 무관한 분산 레이어 노이즈 배제.)

### 결정 2 — 라이브러리가 아니라 규율만 이식 (zero-dep 유지)
LangChain/LangGraph 는 **채택하지 않는다**: (a) zero-dep 계약 위반, (b) 실행 모델이 다름
(LangChain 은 Python 이 루프를 소유하고 API 호출 / 우리는 host 가 tool-loop 소유), (c) Loop 3·4 가
LangSmith(SaaS) 의존. **"루프를 명시적·유계로 만든다"는 규율만** stdlib 로 이식.

### 결정 3 — `verify_loop.py` (stdlib): rubric + 재시도 상태 + 에스컬레이션
- `start/record/status/list/rubric/self`. 상태: `.claude/state/verify-loop/<F>.json` (런타임 gitignore).
- **grader 종류 구분** (LangChain 차용): 결정론(lint/design-review/qa-browser/test) vs judge(reviewer/qa).
- verdict `pass|revision|fail` → 상태 전이. **revision 3회 누적 → 자동 `escalated`** (산문 규칙의 코드화).
- 과잉 추상화 금지(Karpathy): 클래스 프레임워크 아님 — 함수 + JSON 상태.

### 결정 4 — rubric 을 명시 파일로 (`.claude/rubrics/*.md`)
`code-review.md`(MUST/SHOULD/CONSIDER), `qa-acceptance.md`(acceptance_criteria 기반).
reviewer.md/qa.md 의 암묵 체크리스트를 **명시 rubric** 으로 승격 → grader 가 이걸로 채점·기록.

### 결정 5 — 기존 흐름에 연동 (대체 아님)
reviewer.md/qa.md 의 "판정 후 액션" 에 `verify_loop record` 를 추가하고, product-cycle 검증 단계에
verify-loop 훅을 단다. **결정론 grader 먼저 → judge 나중** (값싼 실패를 앞에서 게이트).

### 결정 6 — 격리: LINT-MR-13
loop 오버레이(`verify_loop.py`, `verify-loop.md`, `.claude/rubrics/`)는 **claude.loope 에만**.
다른 11 변형에 누수 시 BLOCK. `lint.py check --only=LINT-MR` (MR-13) 가드. pm/hermes 는 상속.

## 대안 검토

| 옵션 | 장점 | 단점 |
|---|---|---|
| (A) **새 변형 + verify_loop 규율 이식 (채택)** | zero-dep, 기존 흐름 강화, 격리 | 12번째 변형 |
| (B) LangChain/LangGraph 직접 채택 | "정통" | 의존성·실행모델·SaaS 충돌 — 계약 위반 |
| (C) reviewer.md 산문만 강화 | 파일 0 추가 | 재시도 상태 여전히 비코드화 — 정형화 실패 |

→ **(A) 채택**. codex/openclaw stub·localllm 위임과 같은 "규율은 이식, 무거운 런타임은 미채택" 패턴.

## 결정 7 — Loop 4(Hill-Climbing) 도 같은 변형에 정형화 (F020 후속)
Loop 2 의 산출(verify-loop 트레이스)이 Loop 4(트레이스→분석→harness 개선)의 입력이므로, 두 루프를
같은 변형(claude.loope = "loop engineering" 변형)에 둔다. `hill_climb.py` 가 3개 트레이스 소스
(verify-loop + analytics.jsonl + learnings.jsonl)를 **결정론으로 집계**해 신호 + **개선 후보** 를 낸다.
- 하네스 패턴 유지: **헬퍼=결정론 신호/후보, 에이전트=개선안 판단** — 헬퍼는 config 를 직접 안 고침.
- retro(일반 회고)와 보완: hill-climb 은 개선 신호(특히 verify-loop 기반)에 특화. retro 가 참조.
- **루프 닫힘(retro Step 5)**: retro 가 `hill_climb --json` 을 읽어 개선안을 초안 → 이것이 Loop 4 의
  "analysis agent that improves harness config" 노드다. **auto-apply 금지 — 사람 승인 후에만 반영**
  (에이전트가 CLAUDE.md/rubric 자동 편집 X). 트레이스 얇으면 생략(성급한 변경 방지). 반영분은
  다음 사이클 트레이스로 재검증 = hill climb 반복. LangChain 은 LangSmith(SaaS)로 구현 — 우리는
  로컬 트레이스 파일로 **의존성 0** 대체 (보조 루프이지 완전 자동은 아님 — 사람 게이트 유지).

## 결과
- 신규(Loop 2): `verify_loop.py`, `.claude/rubrics/{code-review,qa-acceptance}.md`, `verify-loop.md`,
  `.claude/state/verify-loop/`.
- 신규(Loop 4): `hill_climb.py`, `hill-climb.md` (결정 7).
- 변경: reviewer.md/qa.md(record 연동), product-cycle.md(검증 단계 훅). 이 ADR, LINT-MR-13(6파일).
- 미채택: LangChain 라이브러리 + Loop 3·4 의 LangSmith 방식 (우리는 로컬 retro/learn/analytics 로 대체).
- 검증: mock E2E — (Loop 2) 결정론→judge, revision→재시도→pass, revision 3회→escalation.
  (Loop 4) 합성 트레이스로 5개 개선 후보 heuristic(에스컬레이션·revision율·big handoff·반복·learnings0)
  모두 발화 확인.
