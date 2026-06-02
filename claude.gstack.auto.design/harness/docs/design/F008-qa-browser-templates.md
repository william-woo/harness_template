# F008 QA 브라우저 템플릿 & 슬롯 카탈로그 (raw 정의)

> 단일 소스: `.claude/skills/qa-browser/SKILL.md` 와 `.claude/commands/qa-browser.md` 가 이 문서를 참조한다.
> Feature: F008 — Phase 4 QA 브라우저 자동화 스킬
> 근거: `docs/adr/ADR-003-qa-browser.md` 결정 3

> **SSoT 유지보수 주의**: 이 문서와 SKILL.md 는 단일 소스 원칙. 한 쪽 변경 시 반드시
> 다른 쪽 동기화 — diff 누락은 design-review --scope=self 에서 CON-S2 항목으로 자동 탐지된다.

---

## 개요

이 문서는 `/project:qa-browser` 커맨드가 `feature_list.json` 의 `acceptance_criteria`
텍스트를 Playwright 스크립트 템플릿으로 변환할 때 사용하는 **슬롯 카탈로그** 의 공식 정의다.

**번역 흐름**:

```
1. feature_list.json 에서 --feature=Fxxx 의 acceptance_criteria 배열 읽기
2. 각 항목을 슬롯 카탈로그와 매칭 (정규식 + 키워드)
3. 매칭된 슬롯의 Playwright 코드 조각을 템플릿에 삽입
4. 매칭 실패 항목: TODO 주석 + 자연어 원문 보존 → 에이전트가 보강
5. 결과: tests/e2e/<feature_id>.spec.ts
6. Playwright 미설치: 템플릿 파일만 생성 + 안내, 종료 (exit 0)
7. 설치됨: npx playwright test tests/e2e/<feature_id>.spec.ts 실행
```

**매칭률 기준**:
- 매칭률 ≥ 50%: 자동 실행 진행
- 매칭률 < 50%: dry-run 모드 + TODO 주석 보존 + 사용자 검토 요청
- 매칭률 = 0%: 에이전트 보강 단계 진입 → 실패 시 수동 작성 권유

---

## 슬롯 카탈로그

| 슬롯 ID | 슬롯 키워드 | 매칭 정규식 | Playwright 동작 | 예시 acceptance |
|---|---|---|---|---|
| SLOT-LOGIN | 로그인 / 인증 / 로그인 가능 | `로그인|인증|login|signin|sign.?in` | 아래 LOGIN 코드 조각 | "이메일/비밀번호로 로그인 가능" |
| SLOT-GOTO | 페이지 진입 / 라우팅 / 화면 이동 | `페이지.*진입|화면.*진입|라우팅|goto|navigate|이동` | 아래 GOTO 코드 조각 | "메인 화면 진입" |
| SLOT-FORM | 폼 입력 / 양식 제출 / 입력 후 제출 | `폼.*입력|양식.*제출|입력.*제출|form.*submit|입력.*후` | 아래 FORM 코드 조각 | "이름·전화번호 입력 후 제출" |
| SLOT-CLICK | 클릭 / 버튼 클릭 / 선택 | `클릭|버튼.*클릭|클릭.*시|click|선택` | 아래 CLICK 코드 조각 | "버튼 클릭 시 모달 표시" |
| SLOT-TEXT | 텍스트 가시성 / 메시지 표시 / 텍스트 확인 | `텍스트.*표시|메시지.*표시|확인.*가능|visible|표시됨|나타남` | 아래 TEXT 코드 조각 | "성공 메시지 표시" |
| SLOT-VISIBLE | 가시성 / 렌더 / 렌더됨 | `가시성|렌더|렌더됨|visible|render|표시` | 아래 VISIBLE 코드 조각 | "컴포넌트 렌더됨" |
| SLOT-SCREENSHOT | 스크린샷 | `스크린샷|screenshot` | 아래 SCREENSHOT 코드 조각 | (자동 첨부 — 매 단계 종료 시) |

---

## Playwright 코드 조각

### SLOT-LOGIN — 로그인 / 인증

```typescript
// [SLOT-LOGIN] 로그인 / 인증
// acceptance: "<원문 acceptance 텍스트>"
await page.fill('[name=email], input[type=email], #email', TEST_EMAIL);
await page.fill('[name=password], input[type=password], #password', TEST_PASSWORD);
await page.click('button[type=submit], button:has-text("로그인"), button:has-text("Login")');
await expect(page).not.toHaveURL(/login|signin/);
await page.screenshot({ path: `${SCREENSHOT_DIR}/login-pass.png` });
```

### SLOT-GOTO — 페이지 진입 / 라우팅

```typescript
// [SLOT-GOTO] 페이지 진입 / 라우팅
// acceptance: "<원문 acceptance 텍스트>"
await page.goto(TARGET_URL);
await expect(page).toHaveURL(TARGET_URL);
await page.screenshot({ path: `${SCREENSHOT_DIR}/goto-pass.png` });
```

### SLOT-FORM — 폼 입력 / 양식 제출

```typescript
// [SLOT-FORM] 폼 입력 / 제출
// acceptance: "<원문 acceptance 텍스트>"
// TODO: 아래 selector와 값을 실제 폼 필드에 맞게 수정하세요
await page.fill('input[name="name"], #name', TEST_NAME);
await page.fill('input[name="phone"], #phone', TEST_PHONE);
await page.click('button[type=submit], button:has-text("제출"), button:has-text("저장")');
await page.screenshot({ path: `${SCREENSHOT_DIR}/form-submit-pass.png` });
```

### SLOT-CLICK — 클릭 / 버튼 클릭

```typescript
// [SLOT-CLICK] 클릭 / 인터랙션
// acceptance: "<원문 acceptance 텍스트>"
// TODO: 아래 selector를 실제 버튼/요소에 맞게 수정하세요
await page.click('button, [role=button], [data-testid="target-button"]');
await page.screenshot({ path: `${SCREENSHOT_DIR}/click-pass.png` });
```

### SLOT-TEXT — 텍스트 가시성 / 메시지 표시

```typescript
// [SLOT-TEXT] 텍스트 가시성 / 메시지
// acceptance: "<원문 acceptance 텍스트>"
// TODO: 아래 텍스트를 실제 기대 메시지로 수정하세요
await expect(page.getByText('성공', { exact: false })).toBeVisible();
await page.screenshot({ path: `${SCREENSHOT_DIR}/text-visible-pass.png` });
```

### SLOT-VISIBLE — 가시성 / 렌더링

```typescript
// [SLOT-VISIBLE] 가시성 / 렌더링 확인
// acceptance: "<원문 acceptance 텍스트>"
// TODO: 아래 selector를 실제 컴포넌트/요소에 맞게 수정하세요
await expect(page.locator('[data-testid="target-component"], .target-component')).toBeVisible();
await page.screenshot({ path: `${SCREENSHOT_DIR}/visible-pass.png` });
```

### SLOT-SCREENSHOT — 스크린샷 (자동 첨부)

```typescript
// [SLOT-SCREENSHOT] 스크린샷 — 자동 첨부
const stepName = 'step-name';  // TODO: 단계 이름 수정
await page.screenshot({
  path: `${SCREENSHOT_DIR}/${stepName}-pass.png`,
  fullPage: true
});
```

---

## 예시: acceptance → spec 변환

### 예시 1 — 로그인 플로우 (F012 가상 시나리오)

**입력 acceptance_criteria** (feature_list.json):
```json
[
  "이메일/비밀번호로 로그인 가능",
  "로그인 후 메인 화면 진입",
  "잘못된 비밀번호 입력 시 에러 메시지 표시"
]
```

**슬롯 매칭 결과**:
```
항목 1 "이메일/비밀번호로 로그인 가능"  → SLOT-LOGIN (매칭: "로그인" 패턴)
항목 2 "로그인 후 메인 화면 진입"       → SLOT-GOTO  (매칭: "화면.*진입" 패턴)
항목 3 "잘못된 비밀번호 입력 시 에러 메시지 표시" → SLOT-TEXT  (매칭: "메시지.*표시" 패턴)
매칭률: 3/3 = 100% → 자동 실행 진행
```

**생성 결과** (`tests/e2e/F012.spec.ts` 초안):
```typescript
import { test, expect } from '@playwright/test';

// F012: [Feature 제목]
// 생성 시각: YYYY-MM-DDTHH:MM:SS
// 슬롯 매칭률: 100% (3/3)
// 참고: tests/e2e/_template.spec.ts

const TARGET_URL = process.env.QA_TARGET_URL || 'http://localhost:3000';
const TEST_EMAIL = process.env.QA_TEST_EMAIL || 'test@example.com';
const TEST_PASSWORD = process.env.QA_TEST_PASSWORD || 'password';
const SCREENSHOT_DIR = '.claude/state/qa-browser/screenshots/F012';
const FEATURE_ID = 'F012';

test.describe(`F012 — [Feature 제목]`, () => {

  // AC-1: 이메일/비밀번호로 로그인 가능
  // [SLOT-LOGIN] 매칭
  test('AC-1: 이메일/비밀번호로 로그인 가능', async ({ page }) => {
    await page.goto(TARGET_URL);
    await page.fill('[name=email], input[type=email], #email', TEST_EMAIL);
    await page.fill('[name=password], input[type=password], #password', TEST_PASSWORD);
    await page.click('button[type=submit], button:has-text("로그인"), button:has-text("Login")');
    await expect(page).not.toHaveURL(/login|signin/);
    await page.screenshot({ path: `${SCREENSHOT_DIR}/login-pass.png` });
  });

  // AC-2: 로그인 후 메인 화면 진입
  // [SLOT-GOTO] 매칭
  test('AC-2: 로그인 후 메인 화면 진입', async ({ page }) => {
    // 로그인 선행 필요 — 필요 시 beforeEach 또는 storageState 사용
    await page.goto(`${TARGET_URL}/main`);
    await expect(page).toHaveURL(`${TARGET_URL}/main`);
    await page.screenshot({ path: `${SCREENSHOT_DIR}/goto-pass.png` });
  });

  // AC-3: 잘못된 비밀번호 입력 시 에러 메시지 표시
  // [SLOT-TEXT] 매칭
  test('AC-3: 잘못된 비밀번호 입력 시 에러 메시지 표시', async ({ page }) => {
    await page.goto(`${TARGET_URL}/login`);
    await page.fill('[name=email], input[type=email], #email', TEST_EMAIL);
    await page.fill('[name=password], input[type=password], #password', 'wrong_password');
    await page.click('button[type=submit], button:has-text("로그인")');
    // TODO: 실제 에러 메시지 텍스트로 수정하세요
    await expect(page.getByText('에러', { exact: false })).toBeVisible();
    await page.screenshot({ path: `${SCREENSHOT_DIR}/text-visible-pass.png` });
  });

});
```

---

### 예시 2 — 매칭률 50% 미만 (dry-run 모드)

**입력 acceptance_criteria**:
```json
[
  "결제 PG 연동 후 카드 승인 완료",
  "결제 실패 시 롤백 처리",
  "결제 영수증 이메일 발송"
]
```

**슬롯 매칭 결과**:
```
항목 1 "결제 PG 연동 후 카드 승인 완료" → 매칭 없음 → TODO 보존
항목 2 "결제 실패 시 롤백 처리"         → 매칭 없음 → TODO 보존
항목 3 "결제 영수증 이메일 발송"         → 매칭 없음 → TODO 보존
매칭률: 0/3 = 0% → 에이전트 보강 단계 진입
```

**dry-run 출력 (에이전트 보강 결과)**:
```typescript
// F___ 결제 플로우 — 에이전트 보강 (슬롯 매칭률 0%)
// [DRY-RUN] 자동 실행하지 않음 — 사용자 검토 후 수동 실행 권유

// TODO(에이전트 보강): "결제 PG 연동 후 카드 승인 완료"
// 아래 코드는 에이전트가 컨텍스트에서 추론한 초안입니다. 검토 후 사용하세요.
test('AC-1: 결제 PG 연동 후 카드 승인 완료', async ({ page }) => {
  // TODO: PG 연동 엔드포인트 + 카드 정보 확인 후 수정 필요
  await page.goto(`${TARGET_URL}/payment`);
  await page.fill('[name=cardNumber]', '1234-5678-9012-3456');
  // ... (에이전트 보강 미완성 — 수동 작성 권유)
});
```

---

## 검사 도구 의존성

| 단계 | 도구 | 필수 여부 |
|---|---|---|
| 슬롯 매칭 | Python3 stdlib (`re`, `json`, `pathlib`) | 필수 (항상 사용) |
| 템플릿 생성 | Python3 stdlib (`string.Template`) | 필수 (항상 사용) |
| 실제 실행 | `npx playwright test` | 옵셔널 (설치된 경우만) |
| 스크린샷 캡처 | Playwright 내장 | 옵셔널 (설치된 경우만) |

**명시적 비범위 (F008 세션 1)**:
- 실제 Playwright 실행 (세션 2에서 구현)
- 스크린샷 캡처 및 원자적 수정 루프 (세션 2에서 구현)
- Brain·analytics 연동 (세션 3에서 구현)

---

## 스크린샷 저장 정책

```
.claude/state/qa-browser/
├── screenshots/
│   └── <feature_id>/
│       ├── <step>-pass.png     # 단계 성공
│       ├── <step>-fail.png     # 단계 실패 (BLOCK 트리거)
│       └── <step>-baseline.png # (옵션) 회귀 비교용 baseline
└── runs/
    └── <ts>-<feature_id>.log   # Playwright 실행 로그
```

**git 정책** (세션 2에서 .gitignore 추가):
- `.claude/state/qa-browser/screenshots/` — gitignore (binary + 빈번한 변경)
- `.claude/state/qa-browser/runs/` — gitignore (실행 로그)
- `.claude/state/qa-browser/screenshots/.gitkeep` — git 포함 (디렉토리 보존)
- `.claude/state/qa-browser/runs/.gitkeep` — git 포함

---

## 결과 양식

```markdown
## QA Browser 결과: [feature_id] — [target_url]

**실행 시각**: YYYY-MM-DD HH:MM
**스코프**: downstream | self
**슬롯 매칭률**: N/M (N%)
**Playwright**: 설치됨 | 미설치 (템플릿만 생성)

### 결론
✅ PASS (N개 테스트 성공) | 🔄 BLOCK (B건) | ⚠️ CONCERN (C건)

### 테스트 결과
| # | AC | 슬롯 | 결과 | 비고 |
|---|---|---|---|---|
| 1 | "이메일/비밀번호로 로그인 가능" | SLOT-LOGIN | PASS | — |
| 2 | "메인 화면 진입" | SLOT-GOTO | BLOCK | 스크린샷: screenshots/F012/02-fail.png |

### 원자적 수정 요청
1. [BLOCK-QA-1] F012 AC-2 — 메인 화면 진입 실패
   - 로그: .claude/state/qa-browser/runs/<ts>-F012.log
   - 스크린샷: .claude/state/qa-browser/screenshots/F012/02-fail.png
   → Developer 호출 1회 (해당 이슈만 수정, 다른 이슈 건드리지 않음)
```
