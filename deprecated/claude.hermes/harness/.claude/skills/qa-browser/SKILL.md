---
name: qa-browser
description: |
  QA 브라우저 자동화 스킬. acceptance_criteria 자연어를 Playwright 스크립트 템플릿으로
  자동 번역하고, Playwright 가 설치된 경우 실제 브라우저 E2E 검증을 실행한다.
  옵셔널 의존성 (Playwright) — 미설치 시 차단 X, 템플릿 생성 + 안내 후 exit 0.
  호스트: claude-code
---

# QA Browser Skill

> 슬롯 카탈로그 단일 소스: `docs/design/F008-qa-browser-templates.md`
> 설계 근거: `docs/adr/ADR-003-qa-browser.md`
> 진입점: `/project:qa-browser`

> **SSoT 유지보수 주의**: 이 문서와 raw 정의 (`docs/design/F008-qa-browser-templates.md`) 는
> 단일 소스 원칙. 한 쪽 변경 시 반드시 다른 쪽 동기화 — diff 누락은 design-review
> --scope=self 에서 CON-S2 항목으로 자동 탐지된다.

---

## 호출 진입점

| 호출 | 설명 |
|---|---|
| `/project:qa-browser` | downstream 기본 (현재 in-progress Feature 자동 선택) |
| `/project:qa-browser --feature=F012` | 특정 Feature ID 의 acceptance 자동 번역 |
| `/project:qa-browser --target=http://localhost:3000` | URL 직접 지정 |
| `/project:qa-browser --scope=self` | 하네스 자체 정의 검증 (Playwright dry-run) |
| `/project:qa-browser --rerun=last` | 직전 실패 스크립트 재실행 |
| `/project:qa-browser --rerun=BLOCK-QA-2` | 특정 BLOCK 재실행 |

---

## QA 에이전트와의 역할 경계 (ADR-003 결정 4)

> **설계 원칙**: qa-browser 는 QA 에이전트가 사용하는 **도구**이지 **대체**가 아니다.
> F007 의 design-review 가 Reviewer 의 "도구" 역할을 한 것과 동일한 패턴.

| 영역 | QA 에이전트 | qa-browser (커맨드+스킬) |
|---|---|---|
| `passes: true` 권한 | ✅ **단독 보유** | ❌ 변경 권한 없음 |
| acceptance_criteria 최종 통과 판정 | ✅ 담당 | ❌ 결과 보고만 |
| 회귀 테스트 누적 (`tests/e2e/`) | ✅ 담당 | ✅ 스크립트 **생성만** (실행은 QA 가 활용) |
| 브라우저 자동화 도구 선택 | (자유 선택) | (Playwright 전용) |
| 도구 호출 흐름 | E2E 검증 → PASS/FAIL 판정 | 스크립트 템플릿 생성 + 실행 + 스크린샷 |

**호출 흐름**:
```
QA 에이전트 (PASS 판정 권한 보유)
  └→ /project:qa-browser --feature=Fxxx
        ├→ 성공 → QA 에이전트가 결과 검토 → passes: true
        └→ 실패 → BLOCK → Developer 원자적 수정 위임 → 재실행 → QA 최종 판정
```

---

## design-review 와의 역할 경계 (ADR-003 결정 6)

> **호출 순서**: design-review (정적, 빠름, 외부 의존성 0) → qa-browser (동적, Playwright 필요)
> design-review 가 먼저 통과하지 못한 코드를 qa-browser 로 검증하는 것은 비용 낭비.

| 영역 | design-review (F007) | qa-browser (F008) |
|---|---|---|
| 검사 방식 | **텍스트 정적 분석** (grep, 문자열 매칭) | **동적 브라우저 자동화** (실제 렌더 + 인터랙션) |
| 외부 의존성 | 0 (stdlib만) | Playwright (옵셔널) |
| 검사 대상 | 코드/문서 (파일) | 실행 중인 페이지 (URL) |
| 정보 구조 (IA) | ✅ 텍스트 | ❌ 위임 |
| 접근성 (A11Y) | ✅ 텍스트 정적 (alt, button 태그) | ✅ **동적 보강** (포커스 흐름, 색 대비 — axe-core) |
| 일관성 (CON) | ✅ 텍스트 | ❌ 위임 |
| 동작 검증 (E2E) | ❌ | ✅ **단독 담당** |
| 시각 회귀 (스냅샷) | ❌ | ✅ (옵션, F009 분리) |

**A11Y 중복 처리**: design-review A11Y 는 소스 코드의 정적 마커 (alt 속성 존재 등),
qa-browser A11Y 는 렌더링된 결과의 동적 측정 (실제 포커스 순서, axe-core 통합).

---

## 스코프 분기

### downstream 모드 (기본)

**대상**: 다운스트림 프로젝트의 실행 중인 앱 (URL)
**실행 흐름**:

```
1. feature_list.json 에서 acceptance_criteria 읽기
2. 슬롯 카탈로그 매칭 (정규식 + 키워드)
3. 매칭률 계산
   - ≥ 50%: 자동 실행 진행
   - < 50%: dry-run 모드 (TODO 주석 보존 + 검토 요청)
   - = 0%: 에이전트 보강 진입
4. tests/e2e/<feature_id>.spec.ts 생성
5. Playwright 설치 여부 감지
   - 미설치: 설치 안내 + 템플릿 경로 출력 + exit 0
   - 설치됨: npx playwright test 실행 → 스크린샷 캡처 → 결과 출력
```

### self 모드 (`--scope=self`)

**대상**: 하네스 자체 — qa-browser 정의 자체의 정합성 검증
**F007 self 와의 차이**: F007 self 는 텍스트 정합성 검사. F008 self 는 정의 검증 + Playwright dry-run.

**검사 항목**:

| # | 항목 | 방법 | BLOCK 기준 |
|---|---|---|---|
| QA-S1 | qa-browser 정의 파일 존재 | `pathlib.Path(f).exists()` | 필수 파일 누락 |
| QA-S2 | 슬롯 카탈로그 문서 존재 | `pathlib.Path('docs/design/F008-qa-browser-templates.md').exists()` | 단일 소스 누락 |
| QA-S3 | tests/e2e/_template.spec.ts 존재 | `pathlib.Path('tests/e2e/_template.spec.ts').exists()` | 템플릿 누락 |
| QA-S4 | Playwright 감지 (INFO) | `subprocess.run(['npx', 'playwright', '--version'])` | 차단 X (INFO만) |
| QA-S5 | 스크린샷 디렉토리 작성 가능 | `mkdir -p .claude/state/qa-browser/screenshots` | 작성 불가 |

**셀프 모드 A11Y**: 하네스에 UI 없음 — 동적 A11Y 검사 N/A.
F007 self 모드의 A11Y N/A 처리와 의미상 일관.

---

## Playwright 감지 + 분기 흐름 (ADR-003 결정 1)

```
의사코드:
  try:
    node_ok = subprocess.run(['node', '--version']).returncode == 0
  except:
    node_ok = False

  if not node_ok:
    → 미설치 분기 (설치 안내 + 템플릿 생성 + exit 0)

  try:
    pw_ok = subprocess.run(['npx', 'playwright', '--version']).returncode == 0
  except:
    pw_ok = False

  if pw_ok:
    → 설치됨 분기 (실제 실행 + 스크린샷)
  else:
    → 미설치 분기 (설치 안내 + 템플릿 생성 + exit 0)

  # 공통 원칙: "보조 도구는 어떤 경우에도 사용자의 작업을 막지 않는다"
  # F005 Brain hook-failure-tolerance 패턴과 동일
```

---

## acceptance → 슬롯 매칭 의사코드 (ADR-003 결정 3)

```
SLOT_CATALOG = [
  { id: "SLOT-LOGIN",   pattern: /로그인|인증|login|signin/i },
  { id: "SLOT-GOTO",    pattern: /페이지.*진입|화면.*진입|라우팅|goto|navigate/i },
  { id: "SLOT-FORM",    pattern: /폼.*입력|양식.*제출|입력.*제출|form.*submit/i },
  { id: "SLOT-CLICK",   pattern: /클릭|버튼.*클릭|클릭.*시|click|선택/i },
  { id: "SLOT-TEXT",    pattern: /텍스트.*표시|메시지.*표시|visible|표시됨/i },
  { id: "SLOT-VISIBLE", pattern: /가시성|렌더|렌더됨|render|표시/i },
]

for each acceptance in acceptance_criteria:
  slot = first slot where slot.pattern.matches(acceptance)
  if slot:
    matched++
    append slot.code_snippet to spec (acceptance 삽입)
  else:
    append TODO 주석 + 원문 자연어 보존

match_rate = matched / total * 100

if match_rate >= 50:
  generate spec → tests/e2e/<feature_id>.spec.ts
  if playwright_installed:
    run playwright test
  else:
    print install guide + exit 0

elif match_rate > 0:
  generate spec (dry-run 헤더 포함) → tests/e2e/<feature_id>.spec.ts
  print "[DRY-RUN] 매칭률 50% 미만 — 자동 실행하지 않음"
  print "파일을 검토하고 수동으로 실행하거나 에이전트에게 보강 요청하세요."
  exit 0

else:  # match_rate == 0
  agent_augmentation_step()  # 에이전트가 컨텍스트에서 자연어 → Playwright 변환 시도
  if augmentation_failed:
    print "수동 작성 권유" + exit 0
```

---

## Playwright 미설치 안내 메시지 양식

```
════════════════════════════════════════════════════════════
[qa-browser] Playwright 미설치 — 설치 안내
════════════════════════════════════════════════════════════

Playwright 가 설치되어 있지 않습니다. 아래 중 하나를 선택하세요:

  [옵션 1] Node.js 프로젝트에 설치 (권장):
    npm init -y
    npm install -D @playwright/test
    npx playwright install chromium

  [옵션 2] 전역 설치:
    npm install -g @playwright/test
    npx playwright install chromium

  설치 후 재호출: /project:qa-browser --feature=<FEATURE_ID>

  [지금 할 수 있는 것]
  - 생성된 스크립트 템플릿 확인: tests/e2e/<feature_id>.spec.ts
  - 슬롯 카탈로그 확인: docs/design/F008-qa-browser-templates.md

  [참고] Playwright 설치 없이도 스크립트 템플릿 생성은 완료됩니다.
════════════════════════════════════════════════════════════

[qa-browser] exit 0 — 미설치 환경에서도 정상 종료 (hook-failure-tolerance 원칙)
```

---

## 슬롯 카탈로그 (참조 — 단일 소스는 docs/design/F008-qa-browser-templates.md)

| 슬롯 ID | 슬롯 키워드 | 매칭 정규식 | 예시 acceptance |
|---|---|---|---|
| SLOT-LOGIN | 로그인 / 인증 | `로그인\|인증\|login\|signin` | "이메일/비밀번호로 로그인 가능" |
| SLOT-GOTO | 페이지 진입 / 라우팅 | `페이지.*진입\|화면.*진입\|라우팅\|goto\|navigate` | "메인 화면 진입" |
| SLOT-FORM | 폼 입력 / 양식 제출 | `폼.*입력\|양식.*제출\|입력.*제출\|form.*submit` | "이름·전화번호 입력 후 제출" |
| SLOT-CLICK | 클릭 / 버튼 클릭 | `클릭\|버튼.*클릭\|클릭.*시\|click\|선택` | "버튼 클릭 시 모달 표시" |
| SLOT-TEXT | 텍스트 가시성 / 메시지 표시 | `텍스트.*표시\|메시지.*표시\|visible\|표시됨` | "성공 메시지 표시" |
| SLOT-VISIBLE | 가시성 / 렌더 | `가시성\|렌더\|렌더됨\|render\|표시` | "컴포넌트 렌더됨" |

---

## 결과 양식

```markdown
## QA Browser 결과: [scope] — [feature_id 또는 target_url]

**실행 시각**: YYYY-MM-DD HH:MM
**스코프**: downstream | self
**슬롯 매칭률**: N/M (N%)
**Playwright**: 설치됨 (Version X.X.X) | 미설치 (템플릿만 생성)

### 결론
✅ PASS (N개 테스트 성공) | 🔄 BLOCK (B건) | ⚠️ CONCERN (C건)
← self 모드: PASS | BLOCK N건 (정의 파일 누락 등)

### 테스트 결과
| # | AC | 슬롯 | 결과 | 비고 |
|---|---|---|---|---|
| 1 | "이메일/비밀번호로 로그인 가능" | SLOT-LOGIN | PASS | — |
| 2 | "메인 화면 진입" | SLOT-GOTO | BLOCK | screenshots/F012/02-fail.png |
| 3 | "결제 처리" | TODO | — | 슬롯 매칭 실패 — 수동 작성 필요 |

### 원자적 수정 요청
1. [BLOCK-QA-2] F012 AC-2 — 메인 화면 진입 실패
   - 로그: .claude/state/qa-browser/runs/<ts>-F012.log
   - 스크린샷: .claude/state/qa-browser/screenshots/F012/02-fail.png
   → Developer 호출 1회 (해당 이슈만 수정, 다른 이슈 건드리지 않음)

### CONCERN 목록 (사용자 결정 사항)
- [CONCERN-QA-1] AC-3 슬롯 매칭 실패 — "결제 처리" 수동 작성 권유
```

---

## 원자적 수정 루프 (ADR-003 결정 5 — F007 결정 5 차용)

**원칙**: BLOCK 1건 = Developer 호출 1회 (직렬). 절대 일괄 위임하지 않는다.
동일 BLOCK은 **최대 3회** 재요청 후에도 PASS 안 되면 ESCALATION.

```
의사코드:
  blocks = [B1, B2, B3, ...]  # 실패한 테스트 목록
  concerns = [C1, C2, ...]

  for block in blocks:
    attempt = 0
    while attempt < 3:  # 최대 3회
      Developer 위임:
        "수정 대상 1건만:
         - BLOCK ID: [block.id]
         - 실패 단계: [block.step]
         - 스크린샷: .claude/state/qa-browser/screenshots/<fid>/<step>-fail.png
         - 로그: .claude/state/qa-browser/runs/<ts>-<fid>.log
         - 다른 이슈는 건드리지 않음"
      Developer 수정 완료 후 재검사:
        /project:qa-browser --rerun=[block.id]
      if PASS:
        break
      else:
        attempt += 1

    if attempt == 3:
      [ESCALATION] 태그를 claude-progress.txt에 기록
      Planner 에이전트에 Feature 분해 재검토 요청

  모든 blocks 처리 후:
    CONCERN 목록을 사용자에게 일괄 보고
    → QA 에이전트가 최종 판정 (passes: true 권한 행사)
```

**에스컬레이션 룰**: 같은 BLOCK 이 **3회 실패 후** `[ESCALATION]` 태그 +
Planner 에이전트 호출. F007 에스컬레이션 패턴과 동일.

**왜 원자적인가**: 여러 이슈를 한 번에 수정하면 어느 수정이 회귀를 일으켰는지
추적이 불가능하다. 1건씩 처리하면 각 수정의 영향 범위가 명확하다.
스크린샷을 Developer 에게 첨부하면 시각적 컨텍스트가 명확해진다.

---

## 스크린샷 저장 정책 (ADR-003 결정 5)

```
.claude/state/qa-browser/
├── screenshots/
│   └── <feature_id>/
│       ├── <step>-pass.png     # 단계 성공
│       ├── <step>-fail.png     # 단계 실패 (BLOCK 트리거)
│       └── <step>-baseline.png # (옵션) 회귀 비교용 — F009 가칭
└── runs/
    └── <ts>-<feature_id>.log   # Playwright 실행 로그
```

**git 정책**:
- `.claude/state/qa-browser/screenshots/` — gitignore (binary + 빈번한 변경)
- `.claude/state/qa-browser/runs/` — gitignore (실행 로그)
- `.claude/state/qa-browser/screenshots/.gitkeep` — git 포함 (디렉토리 보존)
- `tests/e2e/*.spec.ts` — git 포함 (회귀 테스트 누적 — QA 에이전트 활용)

---

## 체크리스트 (실행 전 확인)

- [ ] `--scope` 플래그 확인 (기본: downstream)
- [ ] `--feature` ID 또는 현재 in-progress Feature 확인
- [ ] Playwright 설치 여부 무관하게 실행 가능 (미설치 시 템플릿 생성 + exit 0)
- [ ] BLOCK 이슈는 원자적으로 1건씩 Developer 위임
- [ ] `passes: true` 설정하지 않음 (QA 에이전트 단독 권한)
- [ ] 스크린샷은 git에 포함하지 않음 (`.gitignore` 확인)
- [ ] 셀프 모드에서 실제 브라우저 실행하지 않음
