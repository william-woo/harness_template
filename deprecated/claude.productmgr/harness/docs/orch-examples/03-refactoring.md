# 시나리오 3: 리팩토링 — 인증 모듈 A/B 두 서비스로 분리

> 참조: ADR-008 결정 4 (조건부 라우팅), orchestrate.md 라우팅 매트릭스
> 패턴: 리뷰 집중형 (Surgical Changes 강조, architect 포함, qa-browser 스킵)

---

## 요청

```
/project:orchestrate "인증 모듈을 AuthService (사용자 인증) 와 TokenService (토큰 관리) 두 서비스로 분리 — 단일 책임 원칙 적용"
```

---

## 라우팅 판정

supervisor 가 요청을 분석해 각 단계의 필요 여부를 결정한다.

| 단계 | 판정 | 이유 |
|---|:---:|---|
| **researcher** | ⚠ 조건부 | 팀이 서비스 분리 패턴을 알면 스킵. 모르면 포함. 이 예시에서는 스킵 (익숙한 패턴) |
| **architect** | ✅ 활성 | 모듈 의존성 변경 + 3+ 파일 구조 변경 = Architect 호출 기준 충족. 인터페이스 경계 결정 필요 |
| **designer** | ❌ 스킵 | UI 무관 — 서비스 레이어 리팩토링 |
| **developer** | ✅ 활성 | 코드 변경 발생 |
| **reviewer** | ✅ 활성 | Surgical Changes 검증 필수 — 범위 외 변경 점검 중요 |
| **qa + qa-browser** | ✅ 활성 (단위 테스트) | 기존 테스트 전 통과 확인. qa-browser 는 스킵 (UI 무관) |
| **design-review** | ❌ 스킵 | UI 변경 없음 |

**라우팅 매트릭스 분류**: "리팩토링 (구조 변경)" → architect + developer + reviewer + qa (design-review/qa-browser 스킵).

---

## 핸드오프 디렉토리 상태

```
.claude/state/orch/2026-06-05T10-00-00-split-auth-token-service/
├── request.md      ← 원본 요청 + 라우팅 판정
├── plan.md         ← 단계 순서: architect → developer → reviewer → qa (단위 테스트)
├── flow.md         ← 재작업 기록 없음 (reviewer 1차 APPROVED)
├── adr.md          ← 서비스 분리 인터페이스 결정 (ADR-013)
├── impl.md         ← 구현 요약 (AuthService/TokenService 분리, 테스트 갱신)
├── review.md       ← APPROVED (Surgical Changes 확인 포함)
├── qa.md           ← 단위 테스트 전 통과 확인
└── final.md        ← 통합 리포트
```

research.md, design.md 없음 (해당 단계 스킵).

---

## 단계별 실행 흐름

### Step 0: task-id 발급 + 라우팅 판정 기록

request.md:
```markdown
# 원본 요청
인증 모듈 AuthService + TokenService 분리 — 단일 책임 원칙

## 라우팅 판정
- researcher: 스킵 (서비스 분리 패턴 익숙)
- architect: 필요 (모듈 의존성 변경, 3+ 파일 구조 변경)
- designer: 스킵 (UI 무관)
- developer: 필요
- reviewer: 필요 (Surgical Changes — 범위 외 변경 점검)
- qa: 필요 (기존 테스트 전 통과 확인)
- qa-browser: 스킵 (UI 무관)
- design-review: 스킵 (UI 무관)

## 단계 순서
1. architect
2. developer
3. reviewer
4. qa (단위 테스트)
```

### Step 1: architect 호출

```
Use the architect agent to design:

TASK: AuthService 를 AuthService (사용자 인증) + TokenService (토큰 관리) 로 분리
CURRENT_STRUCTURE: |
  src/services/auth.service.ts — 사용자 인증 + JWT 생성·검증·갱신 혼재
  src/controllers/auth.controller.ts — auth.service 의존
  src/middleware/auth.middleware.ts — auth.service 의존
ADR_NUMBER: ADR-013
```

adr.md 핵심 결정:
- `AuthService`: 사용자 인증 (validateCredentials, register) 담당
- `TokenService`: JWT 생성·검증·갱신 담당 (AuthService 는 TokenService 에 의존)
- `auth.controller` + `auth.middleware` 는 TokenService 직접 의존으로 변경
- 인터페이스 (`ITokenService`) 정의로 테스트 격리
- 기존 외부 API 시그니처 무변경 (Surgical Changes 원칙)

### Step 2: developer 호출

```
Use the developer agent to implement:

TASK: AuthService → AuthService + TokenService 분리
ADR: <adr.md 인터페이스 결정·의존성 방향 발췌>
CONSTRAINTS: |
  - 외부 API 시그니처 무변경 (기존 클라이언트 코드 수정 없음)
  - 기존 단위 테스트 전 통과 유지
  - 새 서비스에 단위 테스트 추가
```

impl.md:
```markdown
## 구현 요약

### 신규 파일
- src/services/token.service.ts — TokenService (ITokenService 구현)
- src/services/token.service.spec.ts — 토큰 생성·검증·갱신 단위 테스트

### 수정 파일
- src/services/auth.service.ts — 토큰 로직 제거, TokenService 주입
- src/services/auth.service.spec.ts — TokenService mock 주입으로 격리 테스트
- src/controllers/auth.controller.ts — TokenService 직접 주입
- src/middleware/auth.middleware.ts — TokenService 직접 주입

### 변경 없는 파일 (Surgical Changes 확인)
- src/routes/auth.routes.ts — 변경 없음 (외부 API 시그니처 보존)
- src/models/user.model.ts — 변경 없음
- 결제/상품 서비스 — 변경 없음 (관련 없음)
```

### Step 3: reviewer 호출 (Surgical Changes 집중)

```
Use the reviewer agent to review:

TASK: 인증 모듈 서비스 분리 리팩토링
IMPL_SUMMARY: <impl.md 전체>
ADR: <adr.md 결정 발췌>

FOCUS: Surgical Changes — 범위 외 변경이 없는지 집중 점검
```

reviewer 체크리스트:
- 외부 API 시그니처 변경 없음 확인
- auth.routes.ts 무변경 확인
- 관련 없는 서비스 변경 없음 확인
- 새 인터페이스 `ITokenService` 적절한 추상화 수준인지
- 의존성 방향 ADR 결정과 일치하는지

review.md → APPROVED (1차).

> **reviewer 의 Surgical Changes 역할**: 리팩토링은 "범위 밖" 변경이 가장 위험.
> reviewer 가 `git diff` 를 읽으며 의도치 않은 변경 (관련 없는 파일 수정, 외부 API 변경) 을 차단.

### Step 4: qa (단위 테스트 전 통과 확인)

```
Use the qa agent to verify:

TASK: 기존 단위 테스트 전 통과 확인 + 신규 테스트 확인
VERIFICATION:
  - 기존 auth.service.spec.ts 전 통과
  - 신규 token.service.spec.ts 전 통과
  - 통합 테스트 (auth.controller + TokenService mock) 전 통과
```

qa.md:
```markdown
## QA 결과 — 단위 테스트

### 기존 테스트
- auth.service.spec.ts: 12/12 PASS (TokenService mock 주입)
- auth.controller.spec.ts: 8/8 PASS

### 신규 테스트
- token.service.spec.ts: 9/9 PASS (생성·검증·만료·갱신)

### qa-browser
- 스킵 (UI 무관 — 로그인 페이지 외관 변경 없음)

## 결론
기존 동작 보존 확인. 리팩토링 성공.
```

### Step 5: final.md

```markdown
# 오케스트레이션 완료 — split-auth-token-service

## 요약
인증 모듈 서비스 분리 완료. architect 의 인터페이스 결정 → developer 구현 → reviewer Surgical Changes 확인 → qa 단위 테스트 전 통과.

## 스킵 단계
- researcher: 서비스 분리 패턴 익숙
- designer: UI 무관
- design-review: UI 무관
- qa-browser: UI 무관

## 결과
- architect: ADR-013 APPROVED (TokenService 인터페이스 결정)
- developer: 구현 완료 (TokenService 분리 + 테스트)
- reviewer: APPROVED (Surgical Changes 확인 — 외부 API 무변경)
- qa: PASS (29/29 단위 테스트)

## 총 소요 단계
4 / 7 (researcher/designer/design-review/qa-browser 스킵)
```

---

## 학습 포인트

- **리팩토링에서 Surgical Changes 는 reviewer 의 핵심 역할**: 코드가 "동작" 하는지 보다 "의도치 않은 변경이 없는지" 가 더 중요. reviewer 에게 `FOCUS: Surgical Changes` 를 명시 주입.
- **architect 가 인터페이스 경계를 결정**: developer 가 직접 결정하면 tokenService.ts 의 공개 API 가 임의로 커질 위험. architect 의 ADR 이 경계 계약 역할.
- **qa-browser 스킵 근거 명시**: "UI 무관" — plan.md 에 이유를 적어야 QA 가 나중에 "왜 E2E 를 안 했나" 를 이해.
- **조건부 researcher**: researcher 판정이 "팀 경험치" 에 따라 달라지는 대표적 예시. 서비스 분리 패턴이 처음이면 포함 (DDD, hexagonal 아키텍처 리서치), 익숙하면 스킵.
