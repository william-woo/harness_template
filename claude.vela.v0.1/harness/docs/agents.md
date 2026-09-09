# 에이전트 9종 — 역할과 사용법

> `.claude/agents/*.md` 에 정의된 전문 에이전트의 책임·권한·호출 기준.
> 실제 정의 파일에서 뽑았으며 마지막 갱신: 2026-08-11 (F029 시점).
> 재생성 명령은 문서 끝 [재생성](#재생성) 참조.

## 한눈에 보기

| 에이전트 | 모델 | 도구 | 쓰기 | 최소 변형 | 트리거 |
|---|---|---|:-:|---|---|
| `planner` | opus | Read Write Edit Glob Grep Bash | ✅ | gstack | 프로젝트 초기·기능 추가 요청 |
| `architect` | opus | Read Write Edit Glob Grep Bash | ✅ | gstack | 구조 변경·DB·외부 API·보안 |
| `developer` | opus | Read Write Edit Glob Grep Bash | ✅ | gstack | 구현 |
| `reviewer` | **fable** | Read Glob Grep Bash | ❌ | gstack | 구현 완료 후 |
| `qa` | **fable** | Read Write Edit Glob Grep Bash | ✅ | gstack | 리뷰 통과 후 |
| `gatekeeper` | opus | Read Glob Grep Bash | ❌ | auto | 자율 진행 중 경계 판단이 모호할 때 |
| `designer` | **fable** | Read Glob Grep Bash Write | ✅ | design | 브랜드·토큰 결정 |
| `researcher` | opus | Read Glob Grep Bash **WebSearch WebFetch** | ❌ | orch | 모르는 것을 먼저 조사해야 할 때 |
| `product-manager` | opus | Read Write Edit Glob Grep Bash | ✅ | productmgr | 아이디어 → 제품 brief |

## 설계 원칙 세 가지

**1. 판정 역할은 상위 모델에 둔다.** `reviewer`·`qa`·`designer` 가 `fable`, 생성·설계 역할이
`opus` 다. 검증형 다홉 추론이 생성보다 어렵다는 실측(측정 04)과 같은 방향이며, 로컬 LLM 변형에서
"생성 14B / 판정 32B+" 로 나타나는 규율의 Claude 판본이다.

**2. 판정자에게 쓰기 권한을 주지 않는다.** `reviewer`·`researcher`·`gatekeeper` 는 `Write`/`Edit`
가 없다 — 평가하는 주체가 평가 대상을 고칠 수 있으면 판정이 무의미해진다. 예외는 `qa` 로,
`feature_list.json` 의 `passes` 를 설정해야 하므로 쓰기를 갖는다.

**3. 산출물은 파일로, 판정은 기록으로.** `researcher` 는 `Write` 가 없어 결과를 stdout 으로
반환하고 저장은 호출한 커맨드가 책임진다. 판정은 `verify_loop.py record` 로 남겨야 유효하다.

---

## 파이프라인과 소유권

```
planner ──> architect ──> developer ──> reviewer ──> qa ──> (done)
 기능 분해    설계·ADR      구현·테스트     품질 판정    인수 판정
                              ↑              │
                              └──────────────┘
                            revision (유계 — 3회 초과 시 에스컬레이션)
```

`feature_list.json` 의 `status` 전이와 소유자:

| 전이 | 주체 | 조건 |
|---|---|---|
| `todo` → `in-progress` | developer / architect | 세션 시작 |
| `in-progress` → `review` | developer | 구현 + 테스트 완료 |
| `review` → `qa` | reviewer | APPROVED |
| `qa` → `done` (+ `passes: true`) | **qa 단독** | 모든 acceptance_criteria 충족 |

> `passes` 는 **QA 만** 바꾼다. 다른 에이전트가 손대면 "테스트 없이 완료 마킹" 금지 규칙 위반이다.
> `revision` 3회 누적 시 `verify_loop.py` 가 자동 **ESCALATION** — planner + architect 재검토.

---

## 호출 방법

### 직접 호출

```
Use the planner agent to break down this feature: <기능 설명>
Use the developer agent to implement: <구현 내용>
Use the reviewer agent to review the F001 implementation
Use the qa agent to verify F001 is complete
```

**단일 역할이면 해당 에이전트를 직접 부르는 것이 맞다.** 오케스트레이션 커맨드는 복합 요청용이다.

### 커맨드 경유

| 커맨드 | 태우는 에이전트 |
|---|---|
| `/project:init-project` | planner |
| `/project:start-session` | (상태에 따라) developer · reviewer · qa |
| `/project:plan-full` | planner → architect → reviewer |
| `/project:orchestrate` | researcher → designer → developer → reviewer → qa (조건부) |
| `/project:product-cycle` | product-manager → planner → architect/designer → developer → reviewer → qa |
| `/project:ship` | reviewer · qa (필요한 리뷰만 제안) |
| `/project:verify-loop` | reviewer · qa · architect (판정 기록) |
| `/project:design-pick` | designer |
| `/project:hill-climb` | reviewer · architect (신호 해석) |

`gatekeeper` 는 **어떤 커맨드도 부르지 않는다** — 다른 에이전트가 자율 진행 중 판단이 모호할 때
직접 호출하는 구조다 (Autonomous Mode 규칙 #2).

---

## 에이전트별 상세

### planner — 무엇을 만들 것인가
요구사항을 **검증 가능한** 기능 목록으로 변환하고 `feature_list.json` 을 관리한다. 우선순위와
`dependencies` 를 정한다. 스킬: `planning`.

> 하지 않는 것: 구현, 설계 결정(architect 몫), `passes` 변경.

### architect — 어떻게 구성할 것인가
시스템 설계·기술 선택·ADR 작성. **다음 중 하나라도 해당되면 developer 앞에 반드시 넣는다** —
새 DB 스키마 / 새 외부 API 연동 / 모듈 간 의존성 변경 / 3개 이상 파일에 걸친 구조 변경 / 보안·인증.
해당 없으면 developer 가 바로 시작한다.

### developer — 구현
한 번에 **기능 하나만** 구현하고 테스트를 동반한다. 스킬: `coding`. 완료 시 `status: review`.

> 하지 않는 것: 여러 기능 동시 구현, 테스트 없는 완료 마킹, 리뷰 지적 없는 대량 리팩토링.

### reviewer — 코드 품질 판정 (읽기 전용)
코드 품질·보안·성능·가독성. rubric: `.claude/rubrics/code-review.md` (loope 이상).
판정은 `verify_loop.py record <F> --grader reviewer --verdict pass|revision|fail` 로 기록해야 유효하다.

> **design-review 와의 분리**: reviewer 는 코드 품질·보안·성능, `/project:design-review` 는
> 정보구조·접근성·일관성. 둘 다 필요하면 **reviewer 를 먼저** — 동작하는 코드의 디자인을 보는 것이
> 순서상 자연스럽다.

### qa — 인수 판정 (`passes` 권한 단독)
`acceptance_criteria` 를 항목 단위로 검증한다. 부분 동작은 통과가 아니다.
rubric: `.claude/rubrics/qa-acceptance.md`. 스킬: `testing` · `qa-browser`.
UI 기준(URL·폼·텍스트 노출·라우팅)이 있으면 `/project:qa-browser` 를 호출한다.

> 결정론 grader(lint / 테스트 / design-review)를 **judge 판정보다 먼저** 통과시킨다 — 프로그램이
> pass/fail 을 내므로 빠르고 값싸다.

### gatekeeper — 자율 경계 판정 (auto 변형)
`PROCEED` / `CONSULT` / `ESCALATE` 를 5초 내 결정한다. 사용자에게 묻는 대신 이 에이전트를 부른다.
`CONSULT` 면 reviewer/architect 추가 검토, `ESCALATE` 면 사용자 승인 대기.

> 승인 필수 경계는 3종 — 계정·인증(#3-A) / 외부 부수효과(#3-B) / 비가역 외부 통신(#3-C).

### designer — 브랜드·토큰 결정 (design 변형)
Apple / Claude / Spotify / Tesla 4 브랜드 명세를 비교해 프로젝트 맥락에 맞는 스타일을 추천하고
`tokens.json` 시안을 만든다. `design_pick.py` 의 판단 주체다.

> `design-review` 와의 분리: designer 는 토큰 **선택**, design-review 는 적용된 토큰 **감사**.

### researcher — 조사 (orch 변형, 읽기 전용)
내부 지식(`brain-search`)과 외부 웹(`WebSearch`/`WebFetch`)을 종합해 리서치 노트를 만든다.
코딩·디자인 **전에** "무엇을·왜" 를 규명하는 역할이며, 오케스트레이션의 첫 단계다.

> `Write` 가 없다 — 결과는 stdout 으로 반환하고 저장은 `/project:orchestrate` 본문이 책임진다.

### product-manager — 제품 관점 (productmgr 변형)
사용자·가치·**성공지표**를 정의한 제품 brief 를 만들고, `/project:product-cycle` 의 5단계를
supervisor 로 조율한다. PM = why·what / planner = feature 분해·how-much.

> 하지 않는 것: `passes` 변경, 코드 직접 수정 (조율자다).

---

## 변형별 가용성

| 에이전트 | gstack | auto | design | orch | productmgr | loope | aif | localllm |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| planner · architect · developer · reviewer · qa | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| gatekeeper | ❌ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| designer | ❌ | ❌ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| researcher | ❌ | ❌ | ❌ | ✅ | ✅ | ✅ | ✅ | ✅ |
| product-manager | ❌ | ❌ | ❌ | ❌ | ✅ | ✅ | ✅ | ✅ |

## 로컬 LLM 변형에서의 차이 (localllm 계열)

`.claude/agents/*.md` 가 **소스**이고 `.opencode/agent/*.md` 는 `render-agents` 산출물이다
(수동 편집 금지). 변환 시 `model:` 프론트매터는 **드롭**되고 `--model` 또는 `opencode.json` 으로
지정한다. `tools:` allow-list 는 `permission:` **deny-list 로 역변환**된다.

역할별 모델은 `opencode.json` 이 SSOT 다 — 현재 9 역할 중 8개가 `qwen2.5:32b`, `gatekeeper` 만
`qwen2.5:14b` 다 (측정 08: 14B 는 다중파일·AC 준수에서 수렴 실패).

무인 실행 시 `cycle_driver.py` 가 developer → grade → reviewer → qa 를 결정론 상태 기계로
구동한다 (ADR-018).

---

## 재생성

```bash
# 프론트매터 (모델·도구·줄수)
for f in .claude/agents/*.md; do
  echo "$(basename $f .md): $(awk '/^model:/{print}' $f) | $(awk '/^tools:/{print}' $f)"
done

# 커맨드 ↔ 에이전트 매핑
for a in planner architect developer reviewer qa designer researcher product-manager gatekeeper; do
  echo "$a: $(grep -rl "\b$a\b" .claude/commands/*.md | xargs -r -n1 basename | tr '\n' ' ')"
done

# 로컬 LLM 역할별 모델 (localllm 계열)
python3 -c "import json;d=json.load(open('opencode.json'));print(json.dumps(d['agent'],indent=2,ensure_ascii=False))"
```

## 관련 문서

- [CLAUDE.md](../CLAUDE.md) — 에이전트 호출 기준과 status 전이 규칙
- [docs/tools.md](./tools.md) — 에이전트가 쓰는 도구 인벤토리
- [.claude/rules/coding-standards.md](../.claude/rules/coding-standards.md) — 프롬프트 규율
- [docs/adr/](./adr/) — 각 에이전트를 도입한 결정 기록
