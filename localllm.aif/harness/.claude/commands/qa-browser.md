# /project:qa-browser — QA 브라우저 자동화

다운스트림 프로젝트의 `acceptance_criteria` 를 Playwright 스크립트 템플릿으로 자동 번역하고,
Playwright 가 설치된 경우 실제 브라우저를 구동하여 E2E 검증한다. 실패한 테스트는
Developer 에 **원자적(1건씩)** 위임한다.

**HARD GATE: qa-browser 는 `passes: true` 를 설정하지 않는다. 최종 판정은 QA 에이전트 단독.**

## 사용법

```
/project:qa-browser                                  # downstream 기본 (현재 in-progress Feature 자동 선택)
/project:qa-browser --feature=F012                   # 특정 Feature ID 의 acceptance 자동 번역
/project:qa-browser --target=http://localhost:3000   # URL 직접 지정
/project:qa-browser --scope=self                     # 하네스 자체 정의 검증 (dry-run)
/project:qa-browser --rerun=last                     # 직전 실패한 스크립트 재실행
/project:qa-browser --rerun=BLOCK-QA-2               # 특정 BLOCK 재실행
```

### 플래그

| 플래그 | 기본값 | 설명 |
|---|---|---|
| `--scope` | `downstream` | `downstream` \| `self` |
| `--feature` | (in-progress Feature 자동 선택) | Feature ID (예: `F012`) |
| `--target` | `http://localhost:3000` | 실행 중인 앱 URL |
| `--rerun` | — | 재실행: `last` 또는 `BLOCK-QA-N` |

## QA 에이전트와의 역할 분리

| 영역 | QA 에이전트 | qa-browser (커맨드+스킬) |
|---|---|---|
| `passes: true` 권한 | ✅ **단독 보유** | ❌ 변경 권한 없음 |
| acceptance_criteria 최종 통과 판정 | ✅ 담당 | ❌ 결과 보고만 |
| 회귀 테스트 누적 (`tests/e2e/`) | ✅ 담당 | ✅ 스크립트 **생성만** (실행은 QA 가 활용) |
| 브라우저 자동화 도구 선택 | (자유 선택) | (Playwright 전용) |
| 도구 호출 흐름 | E2E 검증 → PASS/FAIL 판정 | 스크립트 템플릿 생성 + 실행 + 스크린샷 |

**핵심**: qa-browser 는 **QA 에이전트가 사용하는 도구**이지 **QA 에이전트의 대체**가 아니다.
design-review 가 Reviewer 의 "도구" 역할을 한 것과 동일한 패턴.

**호출 흐름 권장**:
```
QA 에이전트 (PASS 판정 권한 보유)
  └→ /project:qa-browser --feature=Fxxx (스크립트 생성 + 실행)
        ├→ 성공 → QA 에이전트가 결과 검토 → passes: true
        └→ 실패 → BLOCK 발견 → Developer 에이전트에 원자적 수정 위임
                            → 재실행 → QA 에이전트 최종 판정
```

## design-review 와의 역할 분리

| 영역 | design-review (F007) | qa-browser (F008) |
|---|---|---|
| 검사 방식 | **텍스트 정적 분석** (grep, 문자열 매칭) | **동적 브라우저 자동화** (실제 렌더 + 인터랙션) |
| 외부 의존성 | 0 (stdlib만) | Playwright (옵셔널) |
| 검사 대상 | 코드/문서 (파일) | 실행 중인 페이지 (URL) |
| 정보 구조 (IA) | ✅ 텍스트 | ❌ 위임 |
| 접근성 (A11Y) | ✅ 텍스트 정적 | ✅ **동적 보강** (실제 포커스 흐름, 색 대비) |
| 일관성 (CON) | ✅ 텍스트 | ❌ 위임 |
| 동작 검증 (E2E) | ❌ | ✅ **단독 담당** |

**호출 순서**: design-review (정적, 빠름) → qa-browser (동적, Playwright 필요)

## 실행 절차

**실제 헬퍼**: `.claude/bin/qa_browser.py` (Python stdlib 전용, Playwright 미설치 시 exit 0 보장)

### 1단계: Playwright 설치 감지

```bash
python3 .claude/bin/qa_browser.py detect
# 출력: [qa-browser] Playwright: <버전 또는 "미설치">
# 항상 exit 0 (hook-failure-tolerance 원칙)
```

### 2단계: acceptance → 슬롯 매칭 + 템플릿 생성

```bash
# feature_list.json 의 Feature ID 로 변환
python3 .claude/bin/qa_browser.py convert <feature_id>

# 예시: 단일 acceptance 텍스트 직접 지정 (검증/테스트용)
python3 .claude/bin/qa_browser.py convert F012 \
  --acceptance "이메일/비밀번호로 로그인 가능" \
  --target http://localhost:3000

# 결과:
#   [qa-browser] 슬롯 매칭률: 100% (N/N)
#   [qa-browser] 스크립트 생성: tests/e2e/F012.spec.ts
#   [qa-browser] 매칭률 50% 이상 — 자동 실행 가능
#   (또는 [DRY-RUN] 매칭률 50% 미만 시)
```

**슬롯 매칭 로직** (`.claude/bin/qa_browser.py` 구현):
- 6개 슬롯 (SLOT-LOGIN/GOTO/FORM/CLICK/TEXT/VISIBLE) + 정규식 매칭
- 매칭률 ≥ 50%: 자동 실행 진행
- 매칭률 < 50%: dry-run 모드 + TODO 주석 보존 + 사용자 검토 요청
- 단일 소스: `docs/design/F008-qa-browser-templates.md`

### 3단계: Playwright 실행 (설치된 경우만)

```bash
# 설치 감지 후 자동 분기
python3 .claude/bin/qa_browser.py run tests/e2e/<feature_id>.spec.ts

# [Playwright 설치됨]:
#   npx playwright test 실행 → 스크린샷 캡처
#   실패 시 원자적 수정 루프 시작

# [Playwright 미설치]:
#   설치 안내 출력 + exit 0 (사용자 차단 없음)
```

### 4단계: 결과 출력 (SKILL.md 참조)

```
스킬 파일에 정의된 결과 양식으로 출력:
  .claude/skills/qa-browser/SKILL.md
원본 슬롯 정의:
  docs/design/F008-qa-browser-templates.md
```

### 5단계: 원자적 수정 루프 (BLOCK 이슈)

```
BLOCK 이슈가 있으면:
  for each BLOCK in [B1, B2, ...]:
    1. Developer 에이전트에 1건만 위임:
       "수정 대상 1건: [BLOCK 상세 설명]
        - BLOCK ID: B1
        - 실패 단계: [단계 설명]
        - 스크린샷: .claude/state/qa-browser/screenshots/<feature_id>/<step>-fail.png
        - 로그: .claude/state/qa-browser/runs/<ts>-<feature_id>.log
        - 다른 이슈는 건드리지 말 것"
    2. Developer 수정 완료 후:
       python3 .claude/bin/qa_browser.py rerun [BLOCK-ID]
       (또는 /project:qa-browser --rerun=[BLOCK-ID])
    3. PASS → 다음 BLOCK
       FAIL → 동일 BLOCK 재요청 (최대 3회)
       3회 실패 후 → [ESCALATION] 태그 + Planner에 Feature 재분해 요청

모든 BLOCK 처리 후:
  CONCERN 목록을 사용자에게 일괄 보고
  → QA 에이전트가 최종 판정 (passes: true 권한 행사)
```

**에스컬레이션**: 같은 BLOCK이 3회 실패 후에도 PASS 안 되면
`claude-progress.txt`에 `[ESCALATION]` 태그 기록 + Planner 에이전트에 Feature
분해 재검토 요청. (design-review 에스컬레이션 패턴과 동일)

## 셀프 모드 (`--scope=self`)

하네스 자체 정의 검증 (UI 없음 — "정의 정합성 + dry-run" 재정의):

```bash
python3 .claude/bin/qa_browser.py self

# 출력 예시:
# ## QA Browser 결과: self — 하네스 정의 검증
# | 항목 | 결과 | 비고 |
# |---|---|---|
# | [IA] QA Browser 커맨드 | PASS | qa-browser.md 존재 |
# | [IA] QA Browser SKILL.md | PASS | SKILL.md 존재 |
# ...
# 결론: PASS — 정의 정합성 확인됨
```

**셀프 모드 검사 항목** (F007 양식 일관 — PASS/CONCERN/BLOCK):
- [IA] 정의 파일 4개 존재 (커맨드/SKILL/슬롯카탈로그/템플릿)
- [IA] tests/e2e/ 디렉토리 존재
- [IA] 슬롯 카탈로그 항목 수 (≥6)
- [CON] Playwright 감지 dry-run (INFO — 차단 X)
- [CON] .claude/state/qa-browser/ 작성 가능성
- [CON] SKILL.md 슬롯 참조 일관성

## --rerun 재실행

특정 BLOCK 또는 직전 실패 재실행:

```bash
# 직전 실패 재실행
python3 .claude/bin/qa_browser.py rerun last

# 특정 BLOCK 재실행
python3 .claude/bin/qa_browser.py rerun BLOCK-QA-1
```

## 출력 예시

### downstream 예시 (Playwright 미설치)

```
[qa-browser] Playwright: 미설치
[qa-browser] 슬롯 매칭률: 75% (3/4)
[qa-browser] 스크립트 생성: tests/e2e/F012.spec.ts

════════════════════════════════════════════════════════════
[qa-browser] Playwright 미설치 — 설치 안내
════════════════════════════════════════════════════════════

Playwright 가 설치되어 있지 않습니다. 아래 중 하나를 선택하세요:

  [옵션 1] Node.js 프로젝트에 설치 (권장):
    npm init -y
    npm install -D @playwright/test
    npx playwright install chromium

  설치 후 재호출: /project:qa-browser --feature=F012

  [지금 할 수 있는 것]
  - 생성된 스크립트 템플릿 확인: tests/e2e/F012.spec.ts
  - 슬롯 카탈로그 확인: docs/design/F008-qa-browser-templates.md

  [참고] Playwright 설치 없이도 스크립트 템플릿 생성은 완료됩니다.
════════════════════════════════════════════════════════════

[qa-browser] exit 0 — 미설치 환경에서도 정상 종료 (hook-failure-tolerance 원칙)
```

### downstream 예시 (Playwright 설치됨 — 세션 2에서 완성)

```
[qa-browser] Playwright: Version 1.44.0
[qa-browser] 슬롯 매칭률: 100% (4/4)
[qa-browser] 스크립트 생성: tests/e2e/F012.spec.ts
[qa-browser] 실행 중...

## QA Browser 결과: downstream — F012

실행 시각: 2026-04-30 10:00
슬롯 매칭률: 100% (4/4)
Playwright: 설치됨 (Version 1.44.0)

### 결론
🔄 BLOCK 1건, CONCERN 0건

### 테스트 결과
| # | AC | 슬롯 | 결과 | 비고 |
|---|---|---|---|---|
| 1 | "이메일/비밀번호로 로그인 가능" | SLOT-LOGIN | PASS | — |
| 2 | "로그인 후 메인 화면 진입" | SLOT-GOTO | BLOCK | screenshots/F012/02-fail.png |

### 원자적 수정 요청
1. [BLOCK-QA-2] F012 AC-2 — 메인 화면 진입 실패
   - 로그: .claude/state/qa-browser/runs/20260430T100000-F012.log
   - 스크린샷: .claude/state/qa-browser/screenshots/F012/02-fail.png
   → Developer 호출 1회
```

### self 예시

```
[qa-browser] scope=self — 하네스 정의 정합성 검증 시작

## QA Browser 결과: self — 하네스 정의 검증

| 항목 | 결과 | 비고 |
|---|---|---|
| .claude/commands/qa-browser.md | PASS | 존재 |
| .claude/skills/qa-browser/SKILL.md | PASS | 존재 |
| docs/design/F008-qa-browser-templates.md | PASS | 존재 |
| tests/e2e/_template.spec.ts | PASS | 존재 |
| node | INFO | 미설치 |
| playwright | INFO | 미설치 |
| .claude/state/qa-browser/ | PASS | 작성 가능 |

결론: PASS — 정의 정합성 확인됨
```

## 파일 위치

| 파일 | 역할 |
|---|---|
| `.claude/commands/qa-browser.md` | 이 파일 — 진입점·실행 절차 |
| `.claude/skills/qa-browser/SKILL.md` | 슬롯 카탈로그·실행 흐름·결과 양식·원자적 루프 상세 |
| `docs/design/F008-qa-browser-templates.md` | 슬롯 카탈로그 raw 정의 (단일 소스) |
| `docs/adr/ADR-003-qa-browser.md` | 설계 결정 근거 |
| `tests/e2e/_template.spec.ts` | Playwright 스크립트 템플릿 예시 |
| `.claude/state/qa-browser/` | 스크린샷·실행 로그 (gitignore 일부) |

## 안전성

- qa-browser 는 `passes: true` 를 설정하지 않는다 (QA 에이전트 단독 권한)
- Playwright 미설치 시 차단하지 않음 — 템플릿 생성 + 안내 후 exit 0
- 외부 API 호출 없음 (OpenAI Vision 등 미사용)
- 스크린샷은 git 에 포함하지 않음 (`.gitignore` 처리 — 세션 2)
- 셀프 모드에서 실제 브라우저 실행하지 않음 (하네스에 UI 없음 — 정의 검증만)
- 모든 처리는 try/except → 에러 시에도 exit 0 (hook-failure-tolerance 원칙)
- GPT Image API / Pillow / cv2 미사용 (F008 비범위)
