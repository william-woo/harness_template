#!/usr/bin/env python3
"""
qa_browser.py — QA 브라우저 자동화 헬퍼 (F008)

Python stdlib 만 사용. 외부 의존성 없음.
Playwright 는 subprocess 호출로만 감지 — 미설치 시 안내 + exit 0 (hook-failure-tolerance).

서브커맨드:
  detect                     Playwright 설치 여부 감지 (항상 exit 0)
  convert <feature_id>       acceptance_criteria → spec.ts (슬롯 매칭)
  run <spec>                 Playwright 실행 (미설치 시 안내 + exit 0)
  self                       하네스 자체 정합성 dry-run (F007 self 양식 일관)
  screenshot-list            저장된 스크린샷 목록
  rerun <block_id>           특정 BLOCK 또는 "last" 재실행

옵션:
  --acceptance <text>        단일 acceptance 텍스트 (convert 에서 feature_list.json 대신)
  --target <url>             대상 URL (기본: http://localhost:3000)
  --dry-run                  실제 실행하지 않고 생성만

설계 원칙:
  - 실패해도 절대 호출자를 차단하지 않음 (exit 0 유지)
  - 모든 핸들러 try/except 로 감싸 항상 exit 0
  - Playwright 미설치 시 차단 X — 안내 + 템플릿 생성 후 정상 종료
  - passes: true 권한 없음 — QA 에이전트 단독 권한
  - feature_list.json passes 필드 절대 수정 불가
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# 경로 상수
# ---------------------------------------------------------------------------

_SCRIPT_DIR = Path(__file__).parent.resolve()
_PROJECT_ROOT = _SCRIPT_DIR.parent.parent  # .claude/bin/ → project root
_FEATURE_LIST = _PROJECT_ROOT / "feature_list.json"
_TESTS_E2E_DIR = _PROJECT_ROOT / "tests" / "e2e"
_STATE_DIR = _PROJECT_ROOT / ".claude" / "state" / "qa-browser"
_SCREENSHOTS_DIR = _STATE_DIR / "screenshots"
_RUNS_DIR = _STATE_DIR / "runs"
_TEMPLATE_SPEC = _TESTS_E2E_DIR / "_template.spec.ts"
_SKILL_MD = _PROJECT_ROOT / ".claude" / "skills" / "qa-browser" / "SKILL.md"
_SLOT_CATALOG_DOC = _PROJECT_ROOT / "docs" / "design" / "F008-qa-browser-templates.md"
_COMMANDS_QA = _PROJECT_ROOT / ".claude" / "commands" / "qa-browser.md"

DEFAULT_TARGET_URL = "http://localhost:3000"

# ---------------------------------------------------------------------------
# 슬롯 카탈로그 (단일 소스: docs/design/F008-qa-browser-templates.md 참조)
# SSoT 주의: 이 목록과 F008-qa-browser-templates.md 는 항상 동기화 유지
# ---------------------------------------------------------------------------

SLOT_CATALOG = [
    {
        "id": "SLOT-LOGIN",
        "pattern": re.compile(r"로그인|인증|login|signin|sign.?in", re.IGNORECASE),
        # TypeScript 템플릿 리터럴: ${...} 는 raw 문자열로 보존 ({ACCEPTANCE} 플레이스홀더만 치환)
        "code": (
            "    // [SLOT-LOGIN] 로그인 / 인증\n"
            "    // acceptance: \"{ACCEPTANCE}\"\n"
            "    await page.fill('[name=email], input[type=email], #email', TEST_EMAIL);\n"
            "    await page.fill('[name=password], input[type=password], #password', TEST_PASSWORD);\n"
            "    await page.click('button[type=submit], button:has-text(\"로그인\"), button:has-text(\"Login\")');\n"
            "    await expect(page).not.toHaveURL(/login|signin/);\n"
            "    await page.screenshot({ path: `${SCREENSHOT_DIR}/login-pass.png` });"
        ),
    },
    {
        "id": "SLOT-GOTO",
        "pattern": re.compile(
            r"페이지.*진입|화면.*진입|라우팅|goto|navigate|이동", re.IGNORECASE
        ),
        "code": (
            "    // [SLOT-GOTO] 페이지 진입 / 라우팅\n"
            "    // acceptance: \"{ACCEPTANCE}\"\n"
            "    await page.goto(TARGET_URL);\n"
            "    await expect(page).toHaveURL(TARGET_URL);\n"
            "    await page.screenshot({ path: `${SCREENSHOT_DIR}/goto-pass.png` });"
        ),
    },
    {
        "id": "SLOT-FORM",
        "pattern": re.compile(
            r"폼.*입력|양식.*제출|입력.*제출|form.*submit|입력.*후", re.IGNORECASE
        ),
        "code": (
            "    // [SLOT-FORM] 폼 입력 / 제출\n"
            "    // acceptance: \"{ACCEPTANCE}\"\n"
            "    // TODO: selector 와 값을 실제 폼 필드에 맞게 수정하세요\n"
            "    await page.fill('input[name=\"name\"], #name', TEST_NAME || 'Test Name');\n"
            "    await page.click('button[type=submit], button:has-text(\"제출\"), button:has-text(\"저장\")');\n"
            "    await page.screenshot({ path: `${SCREENSHOT_DIR}/form-submit-pass.png` });"
        ),
    },
    {
        "id": "SLOT-CLICK",
        "pattern": re.compile(
            r"클릭|버튼.*클릭|클릭.*시|click|선택", re.IGNORECASE
        ),
        "code": (
            "    // [SLOT-CLICK] 클릭 / 인터랙션\n"
            "    // acceptance: \"{ACCEPTANCE}\"\n"
            "    // TODO: selector 를 실제 버튼/요소에 맞게 수정하세요\n"
            "    await page.click('button, [role=button], [data-testid=\"target-button\"]');\n"
            "    await page.screenshot({ path: `${SCREENSHOT_DIR}/click-pass.png` });"
        ),
    },
    {
        "id": "SLOT-TEXT",
        "pattern": re.compile(
            r"텍스트.*표시|메시지.*표시|확인.*가능|visible|표시됨|나타남", re.IGNORECASE
        ),
        "code": (
            "    // [SLOT-TEXT] 텍스트 가시성 / 메시지\n"
            "    // acceptance: \"{ACCEPTANCE}\"\n"
            "    // TODO: 텍스트를 실제 기대 메시지로 수정하세요\n"
            "    await expect(page.getByText('성공', { exact: false })).toBeVisible();\n"
            "    await page.screenshot({ path: `${SCREENSHOT_DIR}/text-visible-pass.png` });"
        ),
    },
    {
        "id": "SLOT-VISIBLE",
        "pattern": re.compile(
            r"가시성|렌더|렌더됨|render|표시", re.IGNORECASE
        ),
        "code": (
            "    // [SLOT-VISIBLE] 가시성 / 렌더링 확인\n"
            "    // acceptance: \"{ACCEPTANCE}\"\n"
            "    // TODO: selector 를 실제 컴포넌트/요소에 맞게 수정하세요\n"
            "    await expect(page.locator('[data-testid=\"target-component\"]')).toBeVisible();\n"
            "    await page.screenshot({ path: `${SCREENSHOT_DIR}/visible-pass.png` });"
        ),
    },
]

# ---------------------------------------------------------------------------
# Playwright 감지 (결정 1 — 옵셔널 의존성 패턴)
# ---------------------------------------------------------------------------


def detect_playwright() -> tuple[bool, str]:
    """
    Playwright 설치 여부를 감지한다.

    1. node --version 확인
    2. npx playwright --version 확인
    모두 try/except 로 감싸 실패 시 미설치 분기 (exit 0 보장).

    Returns:
        (is_installed: bool, detail: str)
    """
    # 1. Node.js 확인
    try:
        r = subprocess.run(
            ["node", "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if r.returncode != 0:
            return False, "node 미설치"
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return False, "node 미설치"

    # 2. Playwright 확인
    try:
        r = subprocess.run(
            ["npx", "playwright", "--version"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if r.returncode == 0:
            version = r.stdout.strip()
            return True, f"Playwright {version}"
        else:
            return False, "Playwright 미설치"
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return False, "Playwright 미설치"


def print_install_guide(feature_id: str = "F008") -> None:
    """Playwright 미설치 시 친절한 설치 안내를 출력한다."""
    print("")
    print("=" * 60)
    print("[qa-browser] Playwright 미설치 — 설치 안내")
    print("=" * 60)
    print("")
    print("Playwright 가 설치되어 있지 않습니다. 아래 중 하나를 선택하세요:")
    print("")
    print("  [옵션 1] Node.js 프로젝트에 설치 (권장):")
    print("    npm init -y")
    print("    npm install -D @playwright/test")
    print("    npx playwright install chromium")
    print("")
    print("  [옵션 2] 전역 설치:")
    print("    npm install -g @playwright/test")
    print("    npx playwright install chromium")
    print("")
    print(f"  설치 후 재호출: python3 .claude/bin/qa_browser.py convert {feature_id}")
    print("")
    print("  [지금 할 수 있는 것]")
    print(f"  - 생성된 스크립트 템플릿 확인: tests/e2e/{feature_id}.spec.ts")
    print("  - 슬롯 카탈로그 확인: docs/design/F008-qa-browser-templates.md")
    print("")
    print("  [참고] Playwright 설치 없이도 스크립트 템플릿 생성은 완료됩니다.")
    print("=" * 60)
    print("")
    print("[qa-browser] exit 0 — 미설치 환경에서도 정상 종료 (hook-failure-tolerance 원칙)")


# ---------------------------------------------------------------------------
# 슬롯 매칭 + spec 생성 (결정 3)
# ---------------------------------------------------------------------------


def match_slot(acceptance_text: str) -> dict | None:
    """
    acceptance 텍스트를 슬롯 카탈로그와 매칭한다.

    Args:
        acceptance_text: 자연어 acceptance 항목

    Returns:
        매칭된 슬롯 dict (id, pattern, code) 또는 None
    """
    for slot in SLOT_CATALOG:
        if slot["pattern"].search(acceptance_text):
            return slot
    return None


def generate_spec(
    feature_id: str,
    acceptance_list: list[str],
    target_url: str = DEFAULT_TARGET_URL,
    dry_run_override: bool = False,
) -> tuple[str, float, bool]:
    """
    슬롯 매칭 결과로 Playwright spec 파일 내용을 생성한다.

    Args:
        feature_id: Feature ID (예: F012)
        acceptance_list: acceptance_criteria 텍스트 목록
        target_url: 대상 URL
        dry_run_override: True 면 매칭률에 무관하게 dry-run

    Returns:
        (spec_content: str, match_rate: float, is_dry_run: bool)
    """
    matched = 0
    test_blocks: list[str] = []
    now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

    for i, ac in enumerate(acceptance_list, 1):
        slot = match_slot(ac)
        if slot:
            matched += 1
            code = slot["code"].replace("{ACCEPTANCE}", ac)
            test_blocks.append(
                f"\n  // AC-{i}: {ac}\n"
                f"  // [{slot['id']}] 매칭\n"
                f"  test('AC-{i}: {ac}', async ({{ page }}) => {{\n"
                f"    await page.goto(TARGET_URL);\n"
                f"{code}\n"
                f"  }});"
            )
        else:
            test_blocks.append(
                f"\n  // AC-{i}: {ac}\n"
                f"  // [매칭 없음] → TODO 보존\n"
                f"  test('AC-{i}: {ac}', async ({{ page }}) => {{\n"
                f"    // TODO(슬롯 매칭 실패): \"{ac}\"\n"
                f"    // 아래 코드를 수동으로 작성하거나 에이전트에게 보강 요청하세요.\n"
                f"    // 슬롯 카탈로그: docs/design/F008-qa-browser-templates.md\n"
                f"    await page.goto(TARGET_URL);\n"
                f"    // TODO: 실제 테스트 로직 작성 필요\n"
                f"  }});"
            )

    total = len(acceptance_list)
    match_rate = (matched / total * 100) if total > 0 else 0.0
    is_dry_run = dry_run_override or (match_rate < 50)

    dry_run_comment = (
        "// [DRY-RUN] 매칭률 50% 미만 — 자동 실행하지 않음. 검토 후 수동 실행 권유\n"
        if is_dry_run
        else ""
    )

    spec_content = (
        f"import {{ test, expect }} from '@playwright/test';\n\n"
        f"// {feature_id}: [Feature 제목 — feature_list.json 참조]\n"
        f"// 생성 시각: {now}\n"
        f"// 슬롯 매칭률: {matched}/{total} ({match_rate:.0f}%)\n"
        f"// 참고: tests/e2e/_template.spec.ts\n"
        f"// 슬롯 카탈로그: docs/design/F008-qa-browser-templates.md\n"
        f"{dry_run_comment}\n"
        f"const TARGET_URL = process.env.QA_TARGET_URL || '{target_url}';\n"
        f"const TEST_EMAIL = process.env.QA_TEST_EMAIL || 'test@example.com';\n"
        f"const TEST_PASSWORD = process.env.QA_TEST_PASSWORD || 'password';\n"
        f"const TEST_NAME = process.env.QA_TEST_NAME || 'Test Name';\n"
        f"const SCREENSHOT_DIR = '.claude/state/qa-browser/screenshots/{feature_id}';\n\n"
        f"test.describe(`{feature_id} — [Feature 제목]`, () => {{"
        f"{''.join(test_blocks)}\n"
        f"}});\n"
    )

    return spec_content, match_rate, is_dry_run


# ---------------------------------------------------------------------------
# 원자적 수정 루프 (결정 5 — F007 패턴 차용)
# ---------------------------------------------------------------------------


def simulate_atomic_loop(block_ids: list[str], feature_id: str) -> None:
    """
    원자적 수정 루프를 시뮬레이션한다.

    BLOCK 1건 = Developer 호출 1회 (직렬).
    3회 실패 후 ESCALATION 태그 출력.

    Args:
        block_ids: BLOCK ID 목록 (예: ['BLOCK-QA-1', 'BLOCK-QA-2'])
        feature_id: Feature ID
    """
    ts = datetime.now().strftime("%Y%m%dT%H%M%S")
    log_path = _RUNS_DIR / f"{ts}-{feature_id}.log"

    print(f"\n[qa-browser] 원자적 수정 루프 시뮬레이션 — {len(block_ids)}건")
    print(f"[qa-browser] 실행 로그 경로 (Playwright 설치 시): {log_path}")
    print("")

    for block_id in block_ids:
        screenshot_path = _SCREENSHOTS_DIR / feature_id / f"{block_id.lower()}-fail.png"
        print(f"--- {block_id} ---")
        print(f"Developer 위임 메시지 (1건만 수정 요청):")
        print(f"  수정 대상 1건만:")
        print(f"    - BLOCK ID: {block_id}")
        print(f"    - 실패 단계: [acceptance 항목 실패 — 상세는 로그 참조]")
        print(f"    - 스크린샷: {screenshot_path}")
        print(f"    - 로그: {log_path}")
        print(f"    - 다른 이슈는 건드리지 말 것")
        print("")
        print(f"  재실행: python3 .claude/bin/qa_browser.py rerun {block_id}")
        print("")
        print("  [시뮬레이션] 3회 실패 시 ESCALATION 예시:")
        print(f"  [ESCALATION] {block_id} — 3회 실패 후 Planner에 Feature 재분해 요청")
        print(f"  claude-progress.txt 에 [ESCALATION] 태그 기록 필요")
        print("")


# ---------------------------------------------------------------------------
# 서브커맨드 핸들러
# ---------------------------------------------------------------------------


def cmd_detect(args: argparse.Namespace) -> None:
    """
    Playwright 설치 여부를 감지하고 결과를 출력한다.
    항상 exit 0 — hook-failure-tolerance 원칙.
    """
    try:
        is_installed, detail = detect_playwright()
        if is_installed:
            print(f"[qa-browser] Playwright: {detail} (설치됨)")
            print("[qa-browser] 실제 브라우저 실행 가능")
        else:
            print(f"[qa-browser] Playwright: {detail} (미설치)")
            print("[qa-browser] 미설치 환경 — 템플릿 생성 + 안내 모드로 동작")
            print("[qa-browser] Playwright 설치 없이도 스크립트 템플릿 생성은 완료됩니다.")
        print("[qa-browser] detect 완료 — exit 0")
    except Exception as e:
        print(f"[qa-browser] detect 오류 (계속 진행): {e}")


def cmd_convert(args: argparse.Namespace) -> None:
    """
    acceptance_criteria → Playwright spec.ts 변환.

    --acceptance 옵션: 단일 acceptance 텍스트 직접 지정.
    없으면 feature_list.json 에서 읽기.
    매칭률 50% 미만 시 dry-run 모드.
    """
    try:
        feature_id = args.feature_id
        target_url = getattr(args, "target", DEFAULT_TARGET_URL) or DEFAULT_TARGET_URL
        dry_run_override = getattr(args, "dry_run", False)

        # acceptance 목록 결정
        if getattr(args, "acceptance", None):
            acceptance_list = [args.acceptance]
            print(f"[qa-browser] --acceptance 옵션으로 단일 항목 처리")
        else:
            # feature_list.json 에서 읽기
            if not _FEATURE_LIST.exists():
                print(f"[qa-browser] feature_list.json 없음 (경로: {_FEATURE_LIST})")
                print("[qa-browser] --acceptance 옵션을 사용하거나 feature_list.json 를 준비하세요.")
                return
            with open(_FEATURE_LIST, encoding="utf-8") as f:
                features = json.load(f)
            feature = next((ft for ft in features if ft["id"] == feature_id), None)
            if not feature:
                print(f"[qa-browser] Feature {feature_id} 를 feature_list.json 에서 찾을 수 없습니다.")
                return
            acceptance_list = feature.get("acceptance_criteria", [])
            if not acceptance_list:
                print(f"[qa-browser] {feature_id} 에 acceptance_criteria 가 없습니다.")
                return

        # 슬롯 매칭 + spec 생성
        spec_content, match_rate, is_dry_run = generate_spec(
            feature_id, acceptance_list, target_url, dry_run_override
        )

        matched_count = sum(1 for ac in acceptance_list if match_slot(ac) is not None)
        total_count = len(acceptance_list)

        print(f"[qa-browser] 슬롯 매칭률: {match_rate:.0f}% ({matched_count}/{total_count})")

        # tests/e2e/ 디렉토리 생성
        _TESTS_E2E_DIR.mkdir(parents=True, exist_ok=True)
        spec_path = _TESTS_E2E_DIR / f"{feature_id}.spec.ts"
        spec_path.write_text(spec_content, encoding="utf-8")
        print(f"[qa-browser] 스크립트 생성: {spec_path}")

        if is_dry_run:
            print(f"[qa-browser] [DRY-RUN] 매칭률 50% 미만 — 자동 실행하지 않음")
            print(f"[qa-browser] 파일을 확인하고 수동으로 실행하거나 에이전트에게 보강 요청하세요.")
        else:
            print(f"[qa-browser] 매칭률 50% 이상 — 자동 실행 가능")
            is_installed, pw_detail = detect_playwright()
            print(f"[qa-browser] Playwright: {pw_detail}")
            if not is_installed:
                print_install_guide(feature_id)
            else:
                print(f"[qa-browser] 실행 명령: npx playwright test {spec_path}")

    except Exception as e:
        print(f"[qa-browser] convert 오류 (계속 진행): {e}")


def cmd_run(args: argparse.Namespace) -> None:
    """
    Playwright 실행 (설치된 경우만).
    미설치 시 안내 + exit 0.
    """
    try:
        spec_file = getattr(args, "spec", None)
        is_installed, pw_detail = detect_playwright()
        print(f"[qa-browser] Playwright: {pw_detail}")

        if not is_installed:
            feature_id = Path(spec_file).stem if spec_file else "FXXX"
            print_install_guide(feature_id)
            return

        if not spec_file:
            print("[qa-browser] 실행할 spec 파일을 지정하세요: qa_browser.py run <spec.ts>")
            return

        spec_path = Path(spec_file)
        if not spec_path.exists():
            print(f"[qa-browser] spec 파일 없음: {spec_path}")
            print(f"[qa-browser] 먼저 convert 를 실행하세요: qa_browser.py convert <feature_id>")
            return

        feature_id = spec_path.stem
        ts = datetime.now().strftime("%Y%m%dT%H%M%S")
        log_path = _RUNS_DIR / f"{ts}-{feature_id}.log"

        # 실행 디렉토리 생성
        _RUNS_DIR.mkdir(parents=True, exist_ok=True)
        (_SCREENSHOTS_DIR / feature_id).mkdir(parents=True, exist_ok=True)

        print(f"[qa-browser] 실행 중: npx playwright test {spec_path}")
        print(f"[qa-browser] 로그: {log_path}")

        result = subprocess.run(
            ["npx", "playwright", "test", str(spec_path), "--reporter=list"],
            capture_output=True,
            text=True,
            timeout=120,
        )

        # 로그 저장
        log_content = f"=== stdout ===\n{result.stdout}\n=== stderr ===\n{result.stderr}\n"
        log_path.write_text(log_content, encoding="utf-8")

        print(result.stdout)
        if result.stderr:
            print(f"[qa-browser] stderr:\n{result.stderr}")

        if result.returncode == 0:
            print(f"[qa-browser] 실행 성공 — PASS")
        else:
            print(f"[qa-browser] 실행 실패 — BLOCK 발견. 원자적 수정 루프 시작.")
            # 시뮬레이션: 실패 시 BLOCK 1건 Developer 위임
            simulate_atomic_loop([f"BLOCK-QA-1"], feature_id)

    except subprocess.TimeoutExpired:
        print("[qa-browser] Playwright 실행 타임아웃 (120s) — 계속 진행")
    except Exception as e:
        print(f"[qa-browser] run 오류 (계속 진행): {e}")


def cmd_self(args: argparse.Namespace) -> None:
    """
    하네스 자체 정합성 dry-run.

    F007 design-review --scope=self 양식과 일관:
    PASS / CONCERN / BLOCK 라벨 사용.
    실제 브라우저 실행 X (하네스에 UI 없음 — 정의 검증만).
    """
    try:
        print("[qa-browser] scope=self — 하네스 정의 정합성 검증 시작")
        print("")

        checks: list[tuple[str, str, str]] = []  # (항목, 라벨, 비고)

        # IA 카테고리: 정의 파일 존재 확인
        required_files = [
            (_COMMANDS_QA, "QA Browser 커맨드", "IA"),
            (_SKILL_MD, "QA Browser SKILL.md", "IA"),
            (_SLOT_CATALOG_DOC, "슬롯 카탈로그 raw 정의", "IA"),
            (_TEMPLATE_SPEC, "Playwright 템플릿 예시", "IA"),
        ]

        for file_path, label, category in required_files:
            if file_path.exists():
                checks.append((f"[{category}] {label}", "PASS", f"{file_path.name} 존재"))
            else:
                checks.append((f"[{category}] {label}", "BLOCK", f"파일 없음: {file_path}"))

        # IA: tests/e2e/ 디렉토리 존재
        if _TESTS_E2E_DIR.exists():
            checks.append(("[IA] tests/e2e/ 디렉토리", "PASS", "존재"))
        else:
            checks.append(("[IA] tests/e2e/ 디렉토리", "CONCERN", "디렉토리 없음 (convert 시 자동 생성됨)"))

        # IA: 슬롯 카탈로그 슬롯 수 일관성
        slot_count = len(SLOT_CATALOG)
        if slot_count >= 6:
            checks.append(("[IA] 슬롯 카탈로그 항목 수", "PASS", f"{slot_count}개 슬롯 (기준: ≥6)"))
        else:
            checks.append(("[IA] 슬롯 카탈로그 항목 수", "CONCERN", f"{slot_count}개 슬롯 (기준: ≥6 — ADR-003 결정 3)"))

        # CON 카테고리: Playwright 감지 dry-run (INFO — 차단 X)
        is_installed, pw_detail = detect_playwright()
        pw_label = "PASS" if is_installed else "INFO"
        pw_note = f"{pw_detail} ({'실제 실행 가능' if is_installed else '미설치 — 미설치 분기 동작'})"
        checks.append(("[CON] Playwright 감지 dry-run", pw_label, pw_note))

        # CON: 스크린샷 디렉토리 작성 가능성
        try:
            _SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
            _RUNS_DIR.mkdir(parents=True, exist_ok=True)
            checks.append(("[CON] .claude/state/qa-browser/ 작성 가능", "PASS", "디렉토리 생성 확인"))
        except Exception as e:
            checks.append(("[CON] .claude/state/qa-browser/ 작성 가능", "BLOCK", f"작성 불가: {e}"))

        # CON: SKILL.md 에 슬롯 카탈로그 참조 언급 존재
        if _SKILL_MD.exists():
            skill_content = _SKILL_MD.read_text(encoding="utf-8")
            if "SLOT-LOGIN" in skill_content and "SLOT-GOTO" in skill_content:
                checks.append(("[CON] SKILL.md 슬롯 참조 일관성", "PASS", "SLOT-LOGIN, SLOT-GOTO 참조 확인"))
            else:
                checks.append(("[CON] SKILL.md 슬롯 참조 일관성", "CONCERN", "주요 슬롯 ID 미참조"))

        # 출력 (F007 양식 일관)
        print("## QA Browser 결과: self — 하네스 정의 검증")
        print("")
        print("| 항목 | 결과 | 비고 |")
        print("|---|---|---|")
        for item, label, note in checks:
            print(f"| {item} | {label} | {note} |")

        blocks = [c for c in checks if c[1] == "BLOCK"]
        concerns = [c for c in checks if c[1] == "CONCERN"]
        passes = [c for c in checks if c[1] == "PASS"]

        print("")
        if blocks:
            print(f"결론: BLOCK {len(blocks)}건, CONCERN {len(concerns)}건 — 위 BLOCK 항목 수정 필요")
        elif concerns:
            print(f"결론: PASS (PASS {len(passes)}건) | CONCERN {len(concerns)}건 (비치명 — 참고용)")
        else:
            print(f"결론: PASS — 정의 정합성 확인됨 (PASS {len(passes)}건)")

        print("")
        print("[qa-browser] self 완료 — exit 0")

    except Exception as e:
        print(f"[qa-browser] self 오류 (계속 진행): {e}")


def cmd_screenshot_list(args: argparse.Namespace) -> None:
    """저장된 스크린샷 목록을 출력한다."""
    try:
        if not _SCREENSHOTS_DIR.exists():
            print("[qa-browser] 스크린샷 디렉토리 없음 (아직 스크린샷 없음)")
            print(f"  경로: {_SCREENSHOTS_DIR}")
            return

        screenshots = list(_SCREENSHOTS_DIR.rglob("*.png"))
        if not screenshots:
            print(f"[qa-browser] 스크린샷 없음 (디렉토리: {_SCREENSHOTS_DIR})")
            return

        print(f"[qa-browser] 스크린샷 목록 ({len(screenshots)}개):")
        for sc in sorted(screenshots):
            relative = sc.relative_to(_PROJECT_ROOT)
            print(f"  - {relative}")

    except Exception as e:
        print(f"[qa-browser] screenshot-list 오류 (계속 진행): {e}")


def cmd_rerun(args: argparse.Namespace) -> None:
    """
    특정 BLOCK 또는 "last" 재실행.

    Args:
        args.block_id: BLOCK ID (예: BLOCK-QA-1) 또는 "last"
    """
    try:
        block_id = args.block_id
        print(f"[qa-browser] 재실행: {block_id}")

        is_installed, pw_detail = detect_playwright()
        print(f"[qa-browser] Playwright: {pw_detail}")

        if not is_installed:
            print("[qa-browser] Playwright 미설치 — 재실행 불가")
            print("[qa-browser] Playwright 설치 후 재호출하세요.")
            print_install_guide("재실행 대상")
            return

        if block_id == "last":
            # 가장 최근 log 파일 찾기
            if not _RUNS_DIR.exists():
                print("[qa-browser] 실행 로그 없음 — 먼저 run 을 실행하세요.")
                return
            logs = sorted(_RUNS_DIR.glob("*.log"))
            if not logs:
                print("[qa-browser] 실행 로그 없음 — 먼저 run 을 실행하세요.")
                return
            latest = logs[-1]
            # 로그 이름에서 feature_id 추출
            feature_id = latest.stem.split("-", 1)[-1] if "-" in latest.stem else "FXXX"
            spec_path = _TESTS_E2E_DIR / f"{feature_id}.spec.ts"
            print(f"[qa-browser] 직전 실행: {feature_id} ({latest.name})")
        else:
            print(f"[qa-browser] BLOCK {block_id} 재실행 — Developer 수정 후 실행")
            # BLOCK ID 에서 feature_id 추론 어려움 → 사용자 안내
            print(f"[qa-browser] 힌트: python3 .claude/bin/qa_browser.py run tests/e2e/<feature_id>.spec.ts")
            return

        if not spec_path.exists():
            print(f"[qa-browser] spec 파일 없음: {spec_path}")
            return

        # 실제 재실행
        mock_args = argparse.Namespace(spec=str(spec_path))
        cmd_run(mock_args)

    except Exception as e:
        print(f"[qa-browser] rerun 오류 (계속 진행): {e}")


# ---------------------------------------------------------------------------
# argparse + main
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    """argparse 파서를 구성한다."""
    parser = argparse.ArgumentParser(
        prog="qa_browser.py",
        description=(
            "QA 브라우저 자동화 헬퍼 (F008). "
            "acceptance_criteria → Playwright 스크립트 자동 번역 + 실행."
        ),
    )
    sub = parser.add_subparsers(dest="command", help="서브커맨드")

    # detect
    sub.add_parser("detect", help="Playwright 설치 여부 감지 (항상 exit 0)")

    # convert
    p_convert = sub.add_parser(
        "convert", help="acceptance_criteria → spec.ts (슬롯 매칭)"
    )
    p_convert.add_argument("feature_id", help="Feature ID (예: F012)")
    p_convert.add_argument(
        "--acceptance", "-a", default=None,
        help="단일 acceptance 텍스트 직접 지정 (feature_list.json 대신)"
    )
    p_convert.add_argument(
        "--target", default=DEFAULT_TARGET_URL,
        help=f"대상 URL (기본: {DEFAULT_TARGET_URL})"
    )
    p_convert.add_argument(
        "--dry-run", action="store_true",
        help="실제 실행하지 않고 생성만 (매칭률 무관)"
    )

    # run
    p_run = sub.add_parser("run", help="Playwright 실행 (미설치 시 안내 + exit 0)")
    p_run.add_argument("spec", help="실행할 spec 파일 경로")

    # self
    sub.add_parser("self", help="하네스 자체 정합성 dry-run (F007 self 양식 일관)")

    # screenshot-list
    sub.add_parser("screenshot-list", help="저장된 스크린샷 목록")

    # rerun
    p_rerun = sub.add_parser(
        "rerun", help="특정 BLOCK 또는 직전 실행 재실행"
    )
    p_rerun.add_argument(
        "block_id", help="BLOCK ID (예: BLOCK-QA-1) 또는 'last'"
    )

    return parser


def main() -> None:
    """
    qa_browser.py 진입점.

    모든 서브커맨드는 try/except 로 감싸 항상 exit 0 보장.
    hook-failure-tolerance 원칙 준수.
    """
    parser = build_parser()
    args = parser.parse_args()

    try:
        if args.command == "detect":
            cmd_detect(args)
        elif args.command == "convert":
            cmd_convert(args)
        elif args.command == "run":
            cmd_run(args)
        elif args.command == "self":
            cmd_self(args)
        elif args.command == "screenshot-list":
            cmd_screenshot_list(args)
        elif args.command == "rerun":
            cmd_rerun(args)
        else:
            parser.print_help()
    except Exception as e:
        # 최상위 예외 — 절대 차단하지 않음
        print(f"[qa-browser] 예기치 않은 오류 (계속 진행): {e}")

    sys.exit(0)  # 항상 exit 0 — hook-failure-tolerance 원칙


if __name__ == "__main__":
    main()
