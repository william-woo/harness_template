# 시나리오 1: UI + 외부 API — 결제 페이지에 Stripe 연동 추가

> 참조: ADR-008 결정 4 (조건부 라우팅), orchestrate.md 라우팅 매트릭스
> 패턴: 풀 파이프라인 (모든 단계 활성)

---

## 요청

```
/project:orchestrate "결제 페이지에 Stripe 연동 추가 — 카드 결제 UI + 서버 사이드 결제 처리"
```

---

## 라우팅 판정

supervisor 가 요청을 분석해 각 단계의 필요 여부를 결정한다.

| 단계 | 판정 | 이유 |
|---|:---:|---|
| **researcher** | ✅ 활성 | Stripe API 를 처음 쓰는 경우 — 외부 서비스, best practice 필요 (PCI-DSS 처리, webhook 보안) |
| **architect** | ✅ 활성 | 외부 API 연동 + 서버 사이드 결제 로직 = Architect 호출 기준 충족 |
| **designer** | ✅ 활성 | 결제 페이지 UI — 사용자 대면 화면 변경 |
| **developer** | ✅ 활성 | 코드 변경 발생 |
| **reviewer** | ✅ 활성 | 보안 중요 (API 키 처리, 카드 정보 전송) |
| **qa + qa-browser** | ✅ 활성 | acceptance_criteria: "카드 입력 → 결제 완료 화면 이동" — 동작 기술 포함 |
| **design-review** | ✅ 활성 | UI 변경 + reviewer 통과 후 정보 구조·접근성 감사 |

**라우팅 매트릭스 분류**: "신규 외부 API 연동 (모르는 서비스)" + "신규 UI 컴포넌트 (디자인 시스템 있음)" → 풀 파이프라인.

---

## 핸드오프 디렉토리 상태

```
.claude/state/orch/2026-06-05T14-30-00-add-stripe-payment/
├── request.md      ← 원본 요청 + 라우팅 판정 기록
├── plan.md         ← 단계 순서: researcher → architect/designer(병렬) → developer → reviewer → design-review → qa
├── flow.md         ← 재작업 루프 기록 (1차 NEEDS REVISION 후 재작업 포함)
├── research.md     ← Stripe API best practice, PCI-DSS 요약, webhook 보안 패턴
├── adr.md          ← 결제 아키텍처 결정 (서버 사이드 처리, webhook 처리, API 키 환경변수)
├── design.md       ← 결제 페이지 디자인 비교 + tokens.json 적용 시안
├── impl.md         ← 구현 요약 (stripe.js + 서버 라우트 + DB 스키마 변경)
├── review.md       ← APPROVED (2차 — 1차 NEEDS REVISION: API 키 하드코딩 지적)
├── qa.md           ← Playwright 결제 플로우 E2E PASS
└── final.md        ← 통합 리포트 (전 단계 요약 + 다음 액션)
```

---

## 단계별 실행 흐름

### Step 0: task-id 발급

```bash
TASK_ID="2026-06-05T14-30-00-add-stripe-payment"
mkdir -p .claude/state/orch/$TASK_ID
```

request.md 에 라우팅 판정 기록:
```markdown
## 라우팅 판정
- researcher: 필요 (Stripe API 모름, PCI-DSS best practice 조사 필요)
- architect: 필요 (외부 API 연동 + 서버 사이드 처리)
- designer: 필요 (결제 페이지 UI)
- developer: 필요
- reviewer: 필요 (보안 중요)
- qa: 필요 (카드 결제 플로우 E2E)
- design-review: 필요 (UI 변경)

## 단계 순서
1. researcher
2. architect + designer (병렬 spawn — 독립 축)
3. developer
4. reviewer
5. design-review
6. qa
```

### Step 1: researcher 호출

```
Use the researcher agent to investigate:

RESEARCH_QUESTION: Stripe 카드 결제 연동 best practice — PCI-DSS 준수, webhook 보안, 서버 사이드 처리 패턴
SCOPE: Stripe Elements (프론트엔드), PaymentIntents API (서버), webhook 검증
CONSTRAINTS: Node.js 서버, React 프론트엔드
DEPTH: standard
```

산출물 `research.md` 핵심:
- Stripe Elements 로 카드 정보를 Stripe 에 직접 전송 (PCI-DSS 준수)
- PaymentIntents 생성은 서버에서만 (API 키 노출 금지)
- webhook 서명 검증 (`stripe.webhooks.constructEvent`) 필수
- 환경변수 `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET` 분리

### Step 2: architect + designer 병렬 spawn

```
# architect 호출 (research.md 발췌 주입)
Use the architect agent to design payment integration:

FEATURE: 결제 페이지 Stripe 연동
RESEARCH_NOTES: |
  - Stripe Elements: 카드 정보 Stripe 직접 전송
  - PaymentIntents: 서버 생성 필수
  - webhook 검증 필수
ADR_NUMBER: ADR-012

# designer 호출 (동시 병렬 spawn)
Use the designer agent to compare 4 brands for:

USE_CASE: 결제 페이지 — 신뢰감·안전감 표현
DESIRED_TONE: professional, trustworthy
RESEARCH_NOTES: |
  - 결제 UI 는 신뢰 신호 (보안 배지, 명확한 버튼) 중요
```

### Step 3: developer 호출

```
Use the developer agent to implement:

FEATURE: 결제 페이지 Stripe 연동
RESEARCH_NOTES: <research.md 핵심 발견 발췌>
ADR: <adr.md 결정 발췌 — 서버/클라이언트 분리, 환경변수 패턴>
DESIGN_TOKENS: <design.md 의 선택된 토큰 시안>
```

구현 범위: `stripe.js` 설치, `PaymentForm` 컴포넌트, `/api/create-payment-intent` 라우트, webhook 핸들러.

### Step 4: reviewer (1차 NEEDS REVISION)

reviewer 가 `STRIPE_SECRET_KEY` 하드코딩 발견 → NEEDS REVISION.

flow.md 기록:
```markdown
## 재작업 1회차 (2026-06-05T15-10-00)
- 지적: STRIPE_SECRET_KEY 하드코딩 → 환경변수로 이전
- developer 재호출 (review.md 지적 인라인 주입)
```

developer 재작업 후 reviewer 2차 → APPROVED.

### Step 5: design-review + qa

```
/project:design-review --scope=downstream --target=src/components/PaymentForm
```

```
Use the qa agent to verify:
acceptance_criteria:
  - 카드 번호/만료일/CVC 입력 가능
  - "결제하기" 버튼 클릭 시 Stripe 처리 진행
  - 성공 시 /payment/success 페이지로 이동
  - 실패 시 에러 메시지 표시
```

qa-browser Playwright 스크립트: 카드 입력 → 제출 → 성공 페이지 URL 확인.

### Step 6: final.md 통합 리포트

```markdown
# 오케스트레이션 완료 — 2026-06-05T14-30-00-add-stripe-payment

## 요약
결제 페이지 Stripe 연동 구현 완료.
1차 리뷰 NEEDS REVISION (API 키 하드코딩) → 재작업 → APPROVED.
E2E 결제 플로우 PASS.

## 단계별 결과
- researcher: Stripe best practice 조사 완료
- architect: ADR-012 APPROVED
- designer: claude 브랜드 토큰 적용 (신뢰감 표현)
- developer: 구현 완료 (재작업 1회)
- reviewer: APPROVED (2차)
- design-review: PASS
- qa: PASS (Playwright 결제 플로우)

## 다음 액션
- QA 에이전트의 passes: true 마킹 대기
- Stripe 프로덕션 키 교체 (환경변수 배포팀 공유)
```

---

## 학습 포인트

- **병렬 spawn** 은 architect ↔ designer 처럼 독립 축일 때만 적용 — 결제 아키텍처 설계와 UI 디자인 결정은 서로 무관.
- **보안 민감 요청** 은 researcher → architect 순차 필수 — architect 가 research 결과 없이 API 키 처리 패턴 결정하면 누락 위험.
- **재작업 루프 기록** (flow.md) 은 QA 가 "왜 2차 리뷰가 필요했나" 를 추적할 수 있게 함.
