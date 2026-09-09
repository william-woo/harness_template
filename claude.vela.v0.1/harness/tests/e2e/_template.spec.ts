/**
 * tests/e2e/_template.spec.ts
 *
 * Playwright E2E 스크립트 템플릿 — 모든 슬롯이 채워진 Hello World 예시.
 *
 * 사용법:
 *   1. 이 파일을 복사: cp tests/e2e/_template.spec.ts tests/e2e/F012.spec.ts
 *   2. 또는 /project:qa-browser --feature=F012 으로 자동 생성
 *
 * 슬롯 카탈로그: docs/design/F008-qa-browser-templates.md
 * 생성 도구: /project:qa-browser (F008 QA 브라우저 자동화 스킬)
 * 설계 근거: docs/adr/ADR-003-qa-browser.md 결정 3
 *
 * 스크린샷 저장 위치: .claude/state/qa-browser/screenshots/<feature_id>/
 * 실행 로그 위치: .claude/state/qa-browser/runs/<ts>-<feature_id>.log
 */

import { test, expect } from '@playwright/test';

// ── 환경 변수 기반 설정 ───────────────────────────────────────
// 이 변수들을 환경변수로 주입하거나 아래 기본값을 수정하세요.
const TARGET_URL = process.env.QA_TARGET_URL || 'http://localhost:3000';
const TEST_EMAIL = process.env.QA_TEST_EMAIL || 'test@example.com';
const TEST_PASSWORD = process.env.QA_TEST_PASSWORD || 'password';
const TEST_NAME = process.env.QA_TEST_NAME || 'Test User';
const TEST_PHONE = process.env.QA_TEST_PHONE || '010-0000-0000';
const FEATURE_ID = process.env.QA_FEATURE_ID || '_template';
const SCREENSHOT_DIR = `.claude/state/qa-browser/screenshots/${FEATURE_ID}`;

// ── 실행 전 확인 ──────────────────────────────────────────────
test.beforeAll(async () => {
  console.log(`[qa-browser] Feature: ${FEATURE_ID}`);
  console.log(`[qa-browser] Target: ${TARGET_URL}`);
  console.log(`[qa-browser] Screenshots: ${SCREENSHOT_DIR}`);
});

// ── 테스트 수트 ───────────────────────────────────────────────
test.describe(`${FEATURE_ID} — QA Browser 자동화 템플릿`, () => {

  // ────────────────────────────────────────────────────────────
  // [SLOT-GOTO] 페이지 진입 / 라우팅
  // acceptance: "메인 화면 진입 가능"
  // ────────────────────────────────────────────────────────────
  test('SLOT-GOTO: 페이지 진입 가능', async ({ page }) => {
    await page.goto(TARGET_URL);
    await expect(page).toHaveURL(TARGET_URL);
    await page.screenshot({ path: `${SCREENSHOT_DIR}/goto-pass.png` });
  });

  // ────────────────────────────────────────────────────────────
  // [SLOT-LOGIN] 로그인 / 인증
  // acceptance: "이메일/비밀번호로 로그인 가능"
  // ────────────────────────────────────────────────────────────
  test('SLOT-LOGIN: 이메일/비밀번호로 로그인 가능', async ({ page }) => {
    await page.goto(`${TARGET_URL}/login`);
    // TODO: selector 를 실제 로그인 폼에 맞게 수정하세요
    await page.fill('[name=email], input[type=email], #email', TEST_EMAIL);
    await page.fill('[name=password], input[type=password], #password', TEST_PASSWORD);
    await page.click('button[type=submit], button:has-text("로그인"), button:has-text("Login")');
    await expect(page).not.toHaveURL(/login|signin/);
    await page.screenshot({ path: `${SCREENSHOT_DIR}/login-pass.png` });
  });

  // ────────────────────────────────────────────────────────────
  // [SLOT-FORM] 폼 입력 / 양식 제출
  // acceptance: "이름·전화번호 입력 후 제출 가능"
  // ────────────────────────────────────────────────────────────
  test('SLOT-FORM: 폼 입력 및 제출', async ({ page }) => {
    await page.goto(`${TARGET_URL}/form`);
    // TODO: selector 와 값을 실제 폼 필드에 맞게 수정하세요
    await page.fill('input[name="name"], #name', TEST_NAME);
    await page.fill('input[name="phone"], #phone', TEST_PHONE);
    await page.click('button[type=submit], button:has-text("제출"), button:has-text("저장")');
    await page.screenshot({ path: `${SCREENSHOT_DIR}/form-submit-pass.png` });
  });

  // ────────────────────────────────────────────────────────────
  // [SLOT-CLICK] 클릭 / 버튼 클릭 / 인터랙션
  // acceptance: "버튼 클릭 시 모달 표시"
  // ────────────────────────────────────────────────────────────
  test('SLOT-CLICK: 버튼 클릭 시 반응', async ({ page }) => {
    await page.goto(TARGET_URL);
    // TODO: selector 를 실제 버튼에 맞게 수정하세요
    await page.click('button, [role=button], [data-testid="target-button"]');
    await page.screenshot({ path: `${SCREENSHOT_DIR}/click-pass.png` });
  });

  // ────────────────────────────────────────────────────────────
  // [SLOT-TEXT] 텍스트 가시성 / 메시지 표시
  // acceptance: "성공 메시지 표시"
  // ────────────────────────────────────────────────────────────
  test('SLOT-TEXT: 성공 메시지 표시', async ({ page }) => {
    await page.goto(TARGET_URL);
    // TODO: 실제 기대 메시지 텍스트로 수정하세요
    await expect(page.getByText('성공', { exact: false })).toBeVisible();
    await page.screenshot({ path: `${SCREENSHOT_DIR}/text-visible-pass.png` });
  });

  // ────────────────────────────────────────────────────────────
  // [SLOT-VISIBLE] 가시성 / 렌더링 확인
  // acceptance: "컴포넌트 렌더됨"
  // ────────────────────────────────────────────────────────────
  test('SLOT-VISIBLE: 컴포넌트 렌더링 확인', async ({ page }) => {
    await page.goto(TARGET_URL);
    // TODO: selector 를 실제 컴포넌트에 맞게 수정하세요
    await expect(
      page.locator('[data-testid="target-component"], .target-component')
    ).toBeVisible();
    await page.screenshot({ path: `${SCREENSHOT_DIR}/visible-pass.png` });
  });

  // ────────────────────────────────────────────────────────────
  // [SLOT-SCREENSHOT] 전체 페이지 스크린샷 (자동 첨부)
  // acceptance: (자동 — 매 단계 종료 시)
  // ────────────────────────────────────────────────────────────
  test('SLOT-SCREENSHOT: 전체 페이지 스냅샷', async ({ page }) => {
    await page.goto(TARGET_URL);
    await page.screenshot({
      path: `${SCREENSHOT_DIR}/full-page-pass.png`,
      fullPage: true,
    });
  });

  // ────────────────────────────────────────────────────────────
  // [매칭 없음] — TODO 주석 형식 예시
  // acceptance: "결제 PG 연동 후 카드 승인 완료"
  // ────────────────────────────────────────────────────────────
  test('TODO: 슬롯 매칭 실패 예시', async ({ page }) => {
    // TODO(슬롯 매칭 실패): "결제 PG 연동 후 카드 승인 완료"
    // 이 테스트는 자동 매칭되지 않았습니다.
    // 아래 중 하나를 선택하세요:
    //   1. 수동으로 테스트 로직을 작성하세요
    //   2. /project:qa-browser 에게 에이전트 보강 요청하세요
    //      ("이 acceptance를 Playwright 코드로 변환해 주세요: ...")
    //   3. 슬롯 카탈로그에 새 슬롯을 추가하세요: docs/design/F008-qa-browser-templates.md

    await page.goto(TARGET_URL);
    // TODO: 실제 결제 플로우 테스트 로직 작성 필요
    // await page.goto(`${TARGET_URL}/payment`);
    // await page.fill('[name=cardNumber]', '...');
    // ...
  });

});
