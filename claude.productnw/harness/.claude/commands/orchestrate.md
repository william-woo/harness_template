# /project:orchestrate — 이종 에이전트 오케스트레이션 (supervisor)

이종 에이전트(리서치·디자인·아키텍처·코딩·리뷰·QA)를 한 흐름으로 묶는 supervisor 커맨드.
복합 요청을 분해 → 적합 에이전트에 순차 배분 → 산출물을 다음 단계 입력으로 핸드오프 → 통합.

**claude.gstack.auto.design.wiki.orch 변형 전용.** single-host (모든 에이전트가 같은 컨텍스트 풀).

> ADR-008 결정 1 (orchestrate 커맨드 형태) + 결정 3 (핸드오프 규약) + 결정 4 (조건부 라우팅) + 결정 5 (single-host 원칙)
> plan-full 패턴 (Planner→Architect→Reviewer 설계 체인) 과 보완 관계 — 책임 분리.

---

## 사용법

```
/project:orchestrate "<복합 요청>"
/project:orchestrate --feature=F0XX
/project:orchestrate --steps=research,design,dev   # 단계 명시 override (선택)
```

예:
```
/project:orchestrate "사용자 인증에 OAuth2 PKCE 추가"
/project:orchestrate "결제 페이지 신규 디자인 + Stripe 연동"
/project:orchestrate --feature=F042
/project:orchestrate "Redis 캐싱 레이어 도입" --steps=research,architect,dev,reviewer
```

### plan-full 과의 차이

| 도구 | 범위 | 출력 | 후속 |
|---|---|---|---|
| `/project:plan-full` (F002) | **설계 체인** — 요구사항 → Feature 분해 → ADR 작성 → 설계 감사 | feature_list 추가 + ADR | Developer 가 별도 실행 |
| **`/project:orchestrate` (F013)** | **실행 라우팅** — 요구사항 → 리서치/디자인/코딩 분기 → 에이전트 순차 spawn → 산출물 통합 | 핸드오프 디렉토리 + 최종 통합 리포트 | QA + 사용자 검수 |

복잡한 요청 시 plan-full → orchestrate 순서 권장:
`plan-full` 이 Feature + ADR 을 만들고, `orchestrate` 가 그 Feature 를 리서치+디자인+코딩으로 실행.

---

## 오케스트레이션 흐름 (조건부 라우팅 — ADR-008 결정 4)

```
사용자 요청
   │
   ▼
[Step 0] task-id 발급 + 핸드오프 디렉토리 신설
         .claude/state/orch/<task-id>/
         request.md + plan.md 저장
   │
   ▼
[Step 1] 라우팅 판정 — 아래 "라우팅 판별 규칙" 적용
   │
   ├─ 리서치 필요? ──▶ [Step 2] researcher 에이전트 호출
   │                             산출물: research.md
   │
   ├─ 아키텍처 필요? ─▶ [Step 3] architect 에이전트 호출 (research.md 입력)
   │                             산출물: adr.md
   │
   ├─ 디자인 필요? ──▶ [Step 4] designer 에이전트 호출 (research.md 입력)
   │                             산출물: design.md
   │                             [NOTE] architect ↔ designer 는 의존성 없으면 병렬 spawn 가능
   │
   ▼
[Step 5] developer 에이전트 호출 (research + adr + design 인라인 주입)
         산출물: impl.md (요약)
   │
   ▼
[Step 6] reviewer 에이전트 호출
         산출물: review.md → APPROVED / NEEDS REVISION
   │
   ├─ NEEDS REVISION ─▶ developer 재호출 (최대 2 회) ─▶ 그래도 실패 시 architect 재호출
   │                     각 반복을 flow.md 에 기록
   │
   ├─ UI 변경? ───────▶ [Step 7] /project:design-review 호출
   │
   ├─ AC 동작 기술? ──▶ [Step 8] qa 에이전트 (+ qa-browser) 호출
   │                             산출물: qa.md
   │                             qa FAIL → developer 재호출 (최대 2 회)
   │
   ▼
[Step 9] 통합 리포트 (final.md) + 사용자 출력
```

각 단계 산출물은 핸드오프 디렉토리에 저장 + 다음 에이전트에 **인라인 주입**.
→ sub-agent 는 직전 단계 산출물의 발췌를 입력으로 받음. supervisor 가 발췌 책임.

---

## 라우팅 판별 규칙 (ADR-008 결정 4)

### 단계별 포함/스킵 기준

| 단계 | 포함 조건 | 스킵 조건 | 키워드 예시 |
|---|---|---|---|
| **researcher** | 신규 도메인, 모르는 외부 API/서비스, "어떻게 X 가 작동", 모범 사례 조사, 학술 배경 필요 | 익숙한 영역, 이미 알려진 패턴, 내부 모듈 변경 | "조사", "비교", "best practice", 외부 라이브러리 이름, "왜", "어떻게" |
| **architect** | 신규 DB 테이블/스키마, 외부 API 연동, 모듈 의존성 변경, 3+ 파일 구조 변경, 보안·인증 | 기존 패턴 복제, 단순 UI/스타일, 단순 버그 | plan-full CLAUDE.md "Architect 호출 기준" 동일 |
| **designer** | UI 컴포넌트/페이지, 디자인 시스템 토큰 변경, 사용자 대면 화면, 브랜드 스타일 변경 | 순수 백엔드·CLI·로직, API 변경, 리팩토링 | "디자인", "UI", "스타일", "색", "폰트", "레이아웃", 화면 이름 |
| **developer** | 거의 항상 포함 (코드 변경 발생하는 모든 요청) | 순수 조사·문서 작업, typo 수준은 supervisor 직접 처리 | (기본 포함) |
| **reviewer** | 코드 변경 발생 (거의 항상) | 문서만 변경, 순수 조사 결과만 | (기본 포함) |
| **qa + qa-browser** | acceptance_criteria 에 동작 기술 (로그인, 폼 제출, 라우팅, 버튼 클릭) | 단위 테스트로 충분한 경우, 코드 변경 없는 조사 | F008 호출 기준 일관 |
| **design-review** | UI 변경 + reviewer 통과 후 | 순수 백엔드·로직 변경 | F007 호출 기준 일관 |

**보수적 기본값**: 의심스러우면 단계 추가 — 누락 비용이 추가 비용보다 큼.
(plan-full 의 "설계 필요 시 포함" 정신 일관)

### 라우팅 매트릭스 (요청 카테고리별)

| 요청 카테고리 | researcher | architect | designer | developer | reviewer | qa | design-review |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| 신규 UI 컴포넌트 (디자인 시스템 있음) | ❌ | ❌ | ✅ | ✅ | ✅ | ✅ | ✅ |
| 신규 UI 컴포넌트 (디자인 시스템 미정) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| 신규 외부 API 연동 (모르는 서비스) | ✅ | ✅ | ❌ | ✅ | ✅ | (조건부) | ❌ |
| 신규 DB 스키마 + 기능 | (조건부) | ✅ | ❌ | ✅ | ✅ | ❌ | ❌ |
| 단순 버그 수정 | ❌ | ❌ | ❌ | ✅ | ✅ | ❌ | ❌ |
| 리팩토링 (구조 변경 + 모듈 분리) | ❌ | ✅ | ❌ | ✅ | ✅ | ❌ | ❌ |
| typo / 문구 변경 | ❌ | ❌ | ❌ | (조건부 — supervisor 직접) | ❌ | ❌ | ❌ |

조건부 = 요청 내용에 따라 supervisor 가 판단. 풀 파이프라인은 "신규 UI + 외부 API (디자인 시스템 미정)" 같은 복합 요청에서만 발생.

---

## 순차/병렬 규칙

### 순차 실행 (의존성 존재)

```
researcher → architect   : architect 가 research 결과를 설계에 반영
researcher → designer    : designer 가 research 를 브랜드 결정에 반영
developer → reviewer     : reviewer 가 작성된 코드를 검토
reviewer → design-review : design-review 는 동작하는 코드 + reviewer 통과를 전제
design-review → qa-browser : qa-browser 는 정적 감사 통과 후 동적 검증
```

### 병렬 spawn 가능 (의존성 없음)

```
architect ↔ designer     : 아키텍처 설계와 디자인 결정은 서로 독립 축
                           → Task 도구로 동시 spawn 가능
```

**기본은 순차** — single-host 컨텍스트 일관성 우선.
병렬은 **명백히 독립적일 때만** (architect ↔ designer 가 유일한 현재 후보).

### 전체 순서 요약

```
[리서치] → [아키텍처/디자인: 병렬 가능] → [개발] → [리뷰] → [디자인감사] → [QA]
```

---

## 실패·재작업 루프

| 단계 실패 | 대응 | 최대 횟수 | 초과 시 |
|---|---|---|---|
| reviewer NEEDS REVISION | developer 재호출 (review.md 지적 사항 인라인 주입) | 2 회 | architect 재호출 (설계 재검토) |
| qa FAIL | developer 재호출 (qa.md 실패 항목 인라인 주입) | 2 회 | architect 재호출 |
| design-review BLOCK | designer 재호출 (BLOCK 항목 인라인 주입) | 2 회 | 사용자 ESCALATE |
| 어떤 단계든 `[ESCALATION]` 태그 | 자동 진행 중단 + 사용자에게 보고 | — | final.md 에 `[ESCALATED]` 기록 |

**supervisor 가 flow.md 에 각 반복을 기록** — 재작업 횟수와 지적 사항을 추적.
plan-full 의 "Reviewer NEEDS REVISION 2 회 → Planner 재분해" 정신 일관.

---

## plan-full ↔ orchestrate 관계

상단 "plan-full 과의 차이" 비교표 참조. 통합 흐름:
`plan-full` (Feature + ADR 생성) → `orchestrate --feature=F0XX` (실행 라우팅).
orchestrate 가 설계 필요 판단 시 내부적으로 architect 호출 포함 가능 (plan-full 선행 없이도 자동 보완).

---

## single-host 원칙 (ADR-008 결정 5 — d-1)

모든 sub-agent 는 **같은 Claude Code 컨텍스트 풀**에서 spawn (Task 도구).
핸드오프는 컨텍스트 **전달**이지 **분리**가 아님 — 핸드오프 디렉토리는 감사 추적 + 인라인 주입은 실제 전달.

```
같은 컨텍스트 풀
┌──────────────────────────────────────────────┐
│  supervisor (메인 컨텍스트)                    │
│   │                                           │
│   ├─ Task: researcher  →  research.md          │
│   ├─ Task: designer    →  design.md            │
│   ├─ Task: developer   →  impl.md              │
│   └─ Task: reviewer    →  review.md            │
│                                               │
│  모든 sub-agent 가 같은 토크나이저·의미론 공유   │
└──────────────────────────────────────────────┘
```

### d-1 / d-2 / d-3 경계 (단일 소스)

| 단계 | 의미 | 전제 | 본 커맨드 범위 |
|---|---|---|:---:|
| **d-1 (본 커맨드)** | single-host supervisor + sub-agent 오케스트레이션 (Claude Code Task 도구) | GPU 무관, 즉시 가능 | **✅** |
| d-2 | 로컬 LLM 통합 (researcher 일부를 로컬 small model 에 위임) | GPU 필요, 별도 ADR-009 | ❌ |
| d-3 | 이종 호스트 분산 (Claude Code + Codex + OpenClaw 간 작업 라우팅) | 컨텍스트 전달 손실 감수, 별도 ADR-010 | ❌ |

**재귀 패턴 금지**: sub-agent 가 또 다른 sub-agent 를 spawn 하는 것 금지.
supervisor (메인 컨텍스트) 가 모든 단계를 직접 spawn 해 컨텍스트 깊이를 1 단계로 유지.

이종 호스트/모델 분산 (각 에이전트를 다른 LLM 으로) 은 d-3 후속 — ADR-008 결정 5 경계표.
d-1 은 GPU 무관, 지금 동작. d-2(로컬 LLM)/d-3(분산) 은 후속 phase.

---

## 핸드오프 디렉토리 규약 (ADR-008 결정 3)

```
.claude/state/orch/<task-id>/
├── request.md      # 원본 요청 + 라우팅 계획 (supervisor 작성)
├── plan.md         # 라우팅 판정 결과 (어떤 에이전트 어떤 순서로)
├── flow.md         # 재작업 루프 기록 (각 반복의 지적 사항 + 결과)
├── research.md     # researcher 산출물 (없으면 파일 없음)
├── adr.md          # architect 산출물 (없으면 파일 없음)
├── design.md       # designer 산출물 (없으면 파일 없음)
├── impl.md         # developer 산출물 요약 (실제 코드는 git diff)
├── review.md       # reviewer 산출물 (APPROVED / NEEDS REVISION)
├── qa.md           # qa 산출물 (있으면)
└── final.md        # supervisor 통합 리포트
```

**task-id 규칙**: `<ISO-8601-no-colon>-<slug>` (예: `2026-06-05T14-30-00-add-oauth-pkce`)
- slug: 요구사항 → kebab-case (40 자 cap, 한글 → romanize 또는 `task` fallback)
- 충돌 시 `-2`, `-3` suffix

**gitignore 정책**: `.claude/state/orch/*` 는 git 제외, `.gitkeep` 만 보존.
qa-browser 의 `.claude/state/qa-browser/` 패턴 100% 일관 (ADR-008 결정 3).

---

## 인라인 주입 패턴 (sub-agent 호출 시)

```
# researcher 호출 예시
Use the researcher agent to investigate:

RESEARCH_QUESTION: <원본 요구사항에서 추출>
SCOPE: <조사 범위>
CONSTRAINTS: <제약>
DEPTH: standard

산출물은 stdout 으로 반환. 저장: .claude/state/orch/<task-id>/research.md

---

# designer 호출 예시 (research.md 주입)
Use the designer agent to compare 4 brands for:

USE_CASE: <원본 요구사항에서 추출>
DESIRED_TONE: <톤·분위기>
RESEARCH_NOTES: |
  <research.md 의 "요약" + "다음 에이전트를 위한 권장 사항" 발췌>

---

# developer 호출 예시 (research + design + adr 주입)
Use the developer agent to implement:

FEATURE: <F0XX 또는 자연어 설명>
RESEARCH_NOTES: <research.md 발췌>
DESIGN_TOKENS: <design.md 의 tokens 시안>
ADR: <adr.md 의 결정·구현 가이드 발췌>

---

# reviewer 호출 예시 (review.md 재작업 루프)
Use the developer agent to revise based on reviewer feedback:

FEATURE: <F0XX>
REVIEWER_FEEDBACK: |
  <review.md 의 NEEDS REVISION 항목 전체 발췌>
PREVIOUS_IMPL_SUMMARY: <impl.md 요약>
```

→ supervisor 가 각 단계 산출물의 **관련 섹션만 발췌**해 다음 에이전트에 주입.
어떤 부분이 핵심인지 supervisor 가 판단 — sub-agent 의 불필요한 탐색 제거.

---

## 호출 기준

**orchestrate 사용이 적합한 경우**:
- 복합 요청 — 리서치 + 코딩 + 디자인이 동시에 필요
- 신규 도메인 / 모르는 외부 API / 학술 배경 필요한 변경
- plan-full 로 분해된 복잡 Feature 의 실행 라우팅
- UI 컴포넌트 + 새 디자인 시스템 토큰 동시 변경

**orchestrate 없이 직접 에이전트 호출이 효율적인 경우**:
- 단순 버그 수정 → developer 직접 호출
- typo / 문구 변경 → supervisor 가 직접 수정 (sub-agent 불필요)
- 리팩토링 (구조 미변경) → developer + reviewer

**orchestrate 는 옵셔널** — 호출 안 해도 하네스 동작에 영향 없음.

---

## 구현 예시 — supervisor 책임 수행 템플릿

```
# 1. task-id 발급
TASK_ID="$(date -u +%Y-%m-%dT%H-%M-%S)-<slug>"
mkdir -p .claude/state/orch/$TASK_ID

# 2. request.md 저장
cat > .claude/state/orch/$TASK_ID/request.md << 'EOF'
# 원본 요청
<사용자 요청 전문>

## 라우팅 판정
- researcher: 필요 (신규 도메인)
- architect: 필요 (외부 API 연동)
- designer: 필요 (UI 변경)
- developer: 필요
- reviewer: 필요
- qa: 필요 (acceptance_criteria 에 동작 기술)
- design-review: 필요 (UI 변경 + reviewer 통과 후)
EOF

# 3. researcher 호출
Use the researcher agent to investigate: ...

# 4. research.md 저장 (researcher 최종 메시지 → 파일)
cat > .claude/state/orch/$TASK_ID/research.md << 'EOF'
<researcher 최종 메시지 전문>
EOF

# 5. architect + designer 병렬 spawn (독립 축)
Use the architect agent to design: ... (RESEARCH_NOTES 인라인 주입)
Use the designer agent to compare 4 brands for: ... (RESEARCH_NOTES 인라인 주입)
→ 각 산출물 저장: adr.md, design.md

# 6. developer 호출 (모든 이전 산출물 인라인 주입)
Use the developer agent to implement:
FEATURE: <F0XX>
RESEARCH_NOTES: <research.md 발췌>
ADR: <adr.md 발췌>
DESIGN_TOKENS: <design.md 발췌>

# 7. reviewer 호출
Use the reviewer agent to review: ... → review.md

# 8. NEEDS REVISION 시 재작업 루프 (최대 2 회)
# flow.md 에 반복 기록

# 9. design-review (UI 변경 시)
/project:design-review --scope=downstream

# 10. qa 호출
Use the qa agent to verify: ... → qa.md

# 11. final.md 작성 (supervisor 통합 리포트)
```

---

## 시나리오 예시 참조

- `docs/orch-examples/01-ui-external-api.md` — UI + 외부 API (풀 파이프라인)
- `docs/orch-examples/02-simple-bug.md` — 단순 버그 (최소 라우팅)
- `docs/orch-examples/03-refactoring.md` — 리팩토링 (리뷰 집중형)

---

## 관련 참조

- `ADR-008-heterogeneous-agent-orchestration.md` — orch 변형 설계 근거 8 결정
- `.claude/agents/researcher.md` — 리서치 꼭짓점 에이전트
- `.claude/agents/designer.md` — 디자인 꼭짓점 에이전트 (F011)
- `.claude/commands/plan-full.md` — 설계 체인 (orchestrate 의 선행 또는 독립 사용)
- `.claude/state/orch/` — 핸드오프 디렉토리 (gitignore, .gitkeep 만 보존)
- `docs/orch-examples/` — 시나리오 예시 3 개 (세션 2 산출물)
