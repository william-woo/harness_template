# ADR-003: QA 브라우저 자동화 (Playwright) — 옵셔널 의존성 + 메타-하네스 듀얼 모드

> Feature: F008 — Phase 4 QA 브라우저 자동화 스킬
> 작성: architect 에이전트 | 날짜: 2026-04-30

## 상태

`Accepted` — 본 ADR은 **옵셔널 의존성 패턴 (B)** + **메타-하네스 듀얼 모드 (셀프 모드는
정의 검증으로 한정)** + **커맨드 1개 + 스킬 1개 (에이전트 신설 X)** 형태로 QA 브라우저
자동화를 도입한다. Playwright 가 설치되어 있으면 실제 브라우저 실행 + 스크린샷, 없으면
설치 안내 + Playwright 스크립트 템플릿만 생성하고 정상 종료한다 (exit 0). F005 Brain·F006
host_adapters·F007 design-review 의 hook-failure-tolerance 원칙을 그대로 일관 유지한다.

---

## 컨텍스트

### F008 의 본질적 충돌 — 외부 의존성 정책 vs 명시된 Playwright 요구

이 하네스 프로젝트의 일관 정책은 **외부 패키지 0 (bash + Python stdlib만)** 이다:

| Feature | 정책 준수 방식 |
|---|---|
| F005 Brain | SQLite 선택 (PGLite/Node 회피) — Python stdlib `sqlite3` |
| F006 host_adapters | argparse + json + pathlib + re — stdlib만 |
| F007 design-review | 텍스트 정적 분석 (grep + Python stdlib) — Playwright/Pillow/GPT 비범위 |

그러나 F008 description 은 **"Playwright 기반 간단 QA 스킬 — 실제 브라우저 실행 +
스크린샷"** 이라 명시되어 있고, AC2 는 **"Playwright 설치 안내 (선택적 의존성)"** 이다.
"선택적 의존성" 이라는 표현이 결정의 방향을 시사한다.

### 기존 QA 에이전트와의 충돌 우려

`.claude/agents/qa.md` 의 QA 에이전트는 이미 다음을 책임진다:

- 인수 기준(acceptance_criteria) 검증 → `passes: true` 권한 단독 보유
- E2E 테스트 (curl, Puppeteer/Playwright 등 도구 자유 선택)
- 회귀 테스트 (`tests/e2e/` 누적)

새 도구 (qa-browser) 가 동일 영역을 중복 차지하면 사용자가 두 경로를 헷갈리게 된다.
**역할 경계가 명확해야 한다.** F007 의 "Reviewer ↔ design-review 분리" 와 동일한
설계 과제가 재현된다.

### F007 design-review 와의 중복 영역 우려

F007 의 design-review 는 **텍스트 정적 분석**으로 IA / A11Y / CON 을 검사한다. F008
qa-browser 는 **동적 브라우저 자동화**로 실제 동작을 검증한다. 두 도구가 같은 파일을
대상으로 호출되면 중복이 발생할 수 있다 (예: A11Y-1 alt 누락은 정적·동적 모두 검출
가능). 호출 순서와 영역 분리가 필요하다.

### 메타-하네스 적용성

이 프로젝트는 자체 UI 가 없는 메타-하네스이다. F007 에서 듀얼 모드 (downstream / self)
를 도입했지만, F008 의 셀프 모드는 의미가 다르다:

- F007 self: 하네스 자신의 텍스트 정합성 검사 (CLAUDE.md ↔ commands ↔ ADR)
- F008 self: 하네스 자신은 **렌더링되지 않는다** → 일반적인 의미의 셀프 모드 N/A

이 비대칭을 어떻게 해결할지가 결정 과제 중 하나다.

### 제약

- **외부 의존성 0 정책 일관 유지**: Playwright 강제 설치 X, 사용자 선택
- **무회귀**: F005~F007 의 동작은 한 비트도 바뀌지 않는다
- **기존 QA 에이전트 정의 무수정**: `.claude/agents/qa.md` 손대지 않는다
- **신규 에이전트 신설 금지** (F007 결정 3 일관)
- **F007 design-review 와 인터페이스 일관**: 커맨드+스킬 구조, 듀얼 모드, 원자적
  수정 루프, 에스컬레이션 규칙
- **F006 host_adapters 와의 미래 통합 가능성**: codex/openclaw 호스트에서도 호출
  가능해야 함 (현재 phase 에서는 토큰 치환 미적용, 후속에서)

---

## 결정

### 결정 1 — Playwright 외부 의존성 처리: **(B) 옵셔널 의존성 패턴 + 스크립트 템플릿 생성 fallback**

**채택**: Playwright 를 **옵셔널 의존성**으로 도입한다. 단, F005 Brain 의
hook-failure-tolerance 패턴을 그대로 적용:

| Playwright 설치 상태 | qa-browser 동작 |
|---|---|
| **설치됨** (Node.js + `@playwright/test` 확인) | 스크립트 템플릿 생성 → 실제 실행 → 스크린샷 캡처 → BLOCK 시 Developer 위임 루프 |
| **미설치** | 스크립트 템플릿 생성 + 설치 가이드 출력 + exit 0. 사용자가 설치 후 재호출하면 그 시점에 실행 |

**근거 — 5개 옵션 비교**:

| 옵션 | 장점 | 단점 | 결정 |
|---|---|---|---|
| (A) Playwright 직접 도입 (정책 변경) | 가장 단순 | 외부 의존성 0 정책 깨짐 → F005/F006/F007 일관성 파괴, 설치 안 한 사용자 차단 | ❌ |
| **(B) 옵셔널 의존성 + 템플릿 생성 fallback** | F005 Brain 패턴 일관, 미설치 사용자도 템플릿 받음, AC2 "선택적 의존성" 표현과 정확히 일치 | 동작 분기 로직 필요, "Playwright 있을 때만 실제 검증" 이 사용자 기대와 어긋날 가능성 | **채택** |
| (C) 다운스트림 책임 위임 (하네스는 템플릿만) | 가장 보수적, 정책 100% 준수 | "실제 브라우저 실행 + 스크린샷" description 미충족, 사용자 가치 ↓ | ❌ description 위배 |
| (D) puppeteer-core 등 더 가벼운 대안 | "가벼운" 환상 | 여전히 외부 의존성, 게다가 Playwright 가 description 에 명시됨 | ❌ description 위배 |
| (E) 텍스트 시뮬레이션 (다음 phase 에서 실제 도입) | F007 패턴 일관 | description "실제 브라우저 실행" 미충족, F008 가 F007 의 단순 복제로 전락 | ❌ description 위배 |

→ **(B) 채택**. AC2 의 "선택적 의존성" 이 옵션 (B) 를 명시적으로 가리킨다.

**Brain 패턴과의 일관성**:

- Brain 은 sqlite3 (stdlib) 만 쓰지만 호출 실패 시 차단 X, exit 0 유지 → 호출자 (handoff
  훅 등) 에 영향 없음
- qa-browser 는 Playwright (외부) 를 쓰지만 미설치 시 차단 X, exit 0 유지 → 호출자에
  영향 없음
- **공통 원칙**: "보조 도구는 어떤 경우에도 사용자의 작업을 막지 않는다"

차이는 **의존성 위치**:
- Brain: stdlib 만 사용 → 미설치 케이스 자체가 없음 (Python 자체 부재 시만 fallback)
- qa-browser: 외부 패키지 사용 → 미설치 케이스가 일반적, 친절한 안내 + 템플릿 생성으로
  보강

**Playwright 감지 방법** (정책: stdlib subprocess 만):

```
1. node --version  → 미설치면 미설치로 판정
2. npx playwright --version  → 미설치면 미설치로 판정
3. (선택) package.json 에 @playwright/test 존재 확인
모두 try/except, 실패 시 미설치 분기로
```

---

### 결정 2 — 메타-하네스 적용 방식: **다운스트림 1차 시민 + 셀프 모드는 "정의 검증" 으로 재정의**

**채택**: F007 처럼 듀얼 모드 (`--scope=downstream|self`) 를 형식적으로 일관 유지하되,
**셀프 모드의 의미를 재정의**한다.

| 스코프 | 의미 | 기본값 | 동작 |
|---|---|---|---|
| `downstream` | 다운스트림 프로젝트의 UI 동적 검증 (1차 시민) | ✅ | 실제 브라우저 실행 (또는 템플릿 생성) |
| `self` | 하네스 자체 — **qa-browser 정의 자체의 정합성** 검증 | (옵션) | 스크립트 템플릿 syntax 검사 + Playwright 감지 dry-run + exit 0 |

**셀프 모드 재정의 근거**: 하네스에는 렌더링할 UI 가 없다. 그러나 다음 두 가지는 검증
가능하다:

1. **자기 자신 dry-run**: qa-browser 가 스크립트 템플릿을 생성하는 로직 자체가 작동하는지
2. **인터페이스 정합성**: F007 의 self 모드 (CON-S1~S3) 와 같은 형태로, qa-browser 의
   템플릿/커맨드/스킬이 자체 일관성을 갖추었는지 (예: 템플릿 파일이 실제로 생성되는지,
   스크린샷 디렉토리가 작성 가능한지)

이로써 F007 self 와 의미상 일관 유지: "하네스 자신을 검사한다" = "정적 정합성 + 동적
부트스트래핑 검증".

**다운스트림 사용 시나리오 (구체)**:

**시나리오 1 — HMI 앱 로그인 흐름 E2E**:
> 자동차 인포테인먼트 HMI 프로젝트에서 `feature_list.json` F012 의 acceptance_criteria
> 에 "이메일/비밀번호 로그인 → 메인 화면 진입" 이 있다. 사용자가
> `/project:qa-browser --feature=F012` 호출 → acceptance_criteria 텍스트 →
> Playwright 스크립트 템플릿 (이메일 입력 → 비밀번호 입력 → 로그인 클릭 → 메인 화면
> URL 검증) 생성 → 실행 → 성공 스크린샷 또는 실패 스크린샷 + Developer 재작업 위임.

**시나리오 2 — React 컴포넌트 렌더링 검증**:
> 디자인 시스템 라이브러리에서 `Storybook` 같은 환경에 새 컴포넌트가 렌더링되는지
> 검증. `/project:qa-browser --target=http://localhost:6006/?path=/story/button` 호출
> → 스크립트 템플릿 (페이지 로드 → 컴포넌트 가시성 → 스냅샷) 생성 → 실행 → 회귀
> baseline 비교는 후속 phase 로 분리 (F009 가칭).

**호출 예시**:

```
/project:qa-browser                                  # downstream 기본 (현재 in-progress F 자동 선택)
/project:qa-browser --feature=F012                   # 특정 Feature ID 의 acceptance 자동 번역
/project:qa-browser --target=http://localhost:3000   # URL 직접 지정
/project:qa-browser --scope=self                     # 하네스 자체 정의 검증 (Playwright dry-run)
/project:qa-browser --rerun=last                     # 직전 실패한 스크립트 재실행
```

---

### 결정 3 — acceptance_criteria → Playwright 스크립트 템플릿 자동 번역: **템플릿 슬롯 기반 + LLM 보강**

**채택**: 구조화된 텍스트(acceptance_criteria) 를 슬롯 기반 Playwright 템플릿에
주입한다. 자연어 acceptance 가 슬롯에 매칭되지 않으면 **LLM (= 호출하는 에이전트
자신) 이 보강**한다. 변환 실패 시 사용자 수동 작성으로 fallback.

**왜 LLM 직접 호출이 아니라 "템플릿 슬롯 + 에이전트 보강" 인가**:

- 템플릿: stdlib 으로 작성 가능, 결정론적, 디버깅 용이
- 에이전트 보강: Claude Code 자체가 LLM 이므로 외부 API 호출 없이 컨텍스트에서 처리
- 두 단계 분리로 실패 지점 명확 (템플릿 매칭 실패 vs 에이전트 보강 실패)

**번역 입력 형식**: 자연어 (`feature_list.json` 의 `acceptance_criteria` 배열 그대로).
구조화된 형식 (Given-When-Then BDD 등) 을 강제하지 않음 — 기존 feature_list.json 을
바꿀 필요 없음.

**슬롯 카탈로그 (초안)** — `docs/design/F008-qa-browser-templates.md` 에 정의:

| 슬롯 키워드 | Playwright 동작 | 예시 acceptance |
|---|---|---|
| 로그인 / 인증 | `page.fill('[name=email]', ...)` + `page.fill('[name=password]', ...)` + `page.click('button[type=submit]')` | "이메일/비밀번호로 로그인 가능" |
| 페이지 진입 / 라우팅 | `page.goto(url)` + `expect(page).toHaveURL(...)` | "메인 화면 진입" |
| 폼 입력 | `page.fill(...)` 슬롯 N 개 | "이름·전화번호 입력 후 제출" |
| 클릭 / 인터랙션 | `page.click(selector)` | "버튼 클릭 시 모달 표시" |
| 텍스트 가시성 | `expect(page.getByText(...)).toBeVisible()` | "성공 메시지 표시" |
| 가시성 / 렌더 | `expect(page.locator(...)).toBeVisible()` | "컴포넌트 렌더됨" |
| 스크린샷 | `await page.screenshot({ path: ... })` | (자동 첨부 — 매 단계 종료 시) |

**번역 흐름**:

```
1. feature_list.json 에서 --feature=Fxxx 의 acceptance_criteria 배열 읽기
2. 각 항목을 슬롯 카탈로그와 매칭 (정규식 + 키워드)
3. 매칭된 슬롯의 Playwright 코드 조각을 템플릿에 삽입
4. 매칭 실패 항목: TODO 주석 + 자연어 원문 보존 → 에이전트가 보강
5. 결과: tests/e2e/<feature_id>.spec.ts (또는 .py — 호스트 무관 — 결정 4 참조)
6. Playwright 미설치: 템플릿 파일만 생성 + 안내, 종료
7. 설치됨: npx playwright test tests/e2e/<feature_id>.spec.ts 실행
```

**결과물 위치**:

- 스크립트: `tests/e2e/<feature_id>.spec.ts` (TypeScript 기본 — Playwright 권장)
- 스크린샷: `.claude/state/qa-browser/screenshots/<feature_id>/<step>-<status>.png`
- 실행 로그: `.claude/state/qa-browser/runs/<ts>-<feature_id>.log`

`.claude/state/qa-browser/` 는 새 하위 디렉토리. `.claude/state/` 는 이미 git 포함
대상 (CLAUDE.md L266) 이지만 스크린샷은 binary + 빈번한 변경 → **`.gitignore` 에
`.claude/state/qa-browser/screenshots/` 와 `runs/` 추가** (학습 + 분석 jsonl 은 계속
git 포함).

**변환 실패 시 fallback** (3단계):

1. 매칭 실패 항목은 **TODO 주석으로 원문 자연어 보존** → 사용자가 수동 작성 가능
2. 매칭률이 50% 미만이면 자동 실행하지 않고 **드라이런 모드** 로 출력 → 사용자 검토
   후 수동 실행 권유
3. 매칭률이 0% 면 **에이전트 보강 단계 진입** — 호출자 에이전트가 컨텍스트에서
   자연어 → Playwright 변환 시도, 실패 시 "수동 작성 권유" 메시지로 종료

---

### 결정 4 — 노출 형태: **커맨드 1개 + 스킬 1개 (F007 패턴 일관, 에이전트 신설 X)**

**채택**: 다음 2개 산출물.

```
.claude/commands/qa-browser.md        # /project:qa-browser 슬래시 커맨드
.claude/skills/qa-browser/SKILL.md    # 슬롯 카탈로그·실행 흐름·결과 양식
```

**채택하지 않은 것**:

```
.claude/agents/qa-browser.md          # ❌ 신설 안 함
```

**근거**:

| 옵션 | 장점 | 단점 | 결정 |
|---|---|---|---|
| (i) 커맨드만 | 가장 단순 | 슬롯 카탈로그·템플릿이 커맨드 본문에 묶여 비대 | 부족 |
| (ii) 에이전트만 | 위임 패턴 일관 | 기존 QA 에이전트와 역할 충돌, 에이전트 수 증가 | 과함 |
| (iii) 스킬만 | 재사용성 | 진입점 없음 | 부족 |
| **(iv) 커맨드 + 스킬 (F007 패턴)** | 진입점 명확 + 슬롯 카탈로그 재사용 + 에이전트 수 증가 없음 + QA 에이전트와 분리 자연스러움 | 산출물 2개 | **채택** |
| (v) 기존 QA 에이전트에 통합 | 에이전트 수 0 증가 | qa.md 정의 변경 → 무회귀 위배, QA 에이전트의 단일 책임(passes: true 권한) 희석 | ❌ 제약 위배 |

**기존 QA 에이전트와의 관계**:

| 영역 | QA 에이전트 | qa-browser (커맨드+스킬) |
|---|---|---|
| `passes: true` 권한 | ✅ **단독 보유** | ❌ 변경 권한 없음 |
| acceptance_criteria 최종 통과 판정 | ✅ 담당 | ❌ 결과 보고만 |
| 회귀 테스트 누적 (`tests/e2e/`) | ✅ 담당 | ✅ 스크립트 **생성만** (실행은 QA 가 활용) |
| 브라우저 자동화 도구 선택 | (자유 선택) | (Playwright 전용) |
| 도구 호출 흐름 | E2E 검증 → PASS/FAIL 판정 | 스크립트 템플릿 생성 + 실행 + 스크린샷 |

**핵심 통찰**: qa-browser 는 **QA 에이전트가 사용하는 도구** 이지 **QA 에이전트의 대체**가
아니다. F007 의 design-review 가 Reviewer 의 "도구" 역할을 한 것과 동일한 패턴.

**호출 흐름 권장**:

```
QA 에이전트 (PASS 판정 권한 보유)
  └→ /project:qa-browser --feature=Fxxx (스크립트 생성 + 실행)
        ├→ 성공 → QA 에이전트가 결과 검토 → passes: true
        └→ 실패 → BLOCK 발견 → Developer 에이전트에 원자적 수정 위임
                            → 재실행 → QA 에이전트 최종 판정
```

---

### 결정 5 — 스크린샷 + 실패 시 Developer 재작업 요청: **F007 의 원자적 수정 루프 인터페이스 100% 일관**

**채택**: F007 design-review 의 원자적 수정 루프를 그대로 차용한다. **이슈 1건 =
Developer 호출 1회 (직렬)**. 동시에 스크린샷을 BLOCK 본문에 첨부하여 Developer 가
시각적으로 컨텍스트를 받는다.

**스크린샷 저장 정책**:

```
.claude/state/qa-browser/
├── screenshots/
│   └── <feature_id>/
│       ├── <step>-pass.png          # 단계 성공
│       ├── <step>-fail.png          # 단계 실패 (BLOCK 트리거)
│       └── <step>-baseline.png      # (옵션) 회귀 비교용 baseline
└── runs/
    └── <ts>-<feature_id>.log        # Playwright 실행 로그
```

**원자적 수정 루프 (F007 결정 5 차용)**:

```
1. /project:qa-browser --feature=Fxxx
2. Playwright 실행 결과: BLOCK [B1, B2, B3], CONCERN [C1] (CONCERN 은 시각적 회귀 등 비치명)
3. for each block in [B1, B2, B3]:
     a. Developer 위임: "수정 대상 1건만:
          - BLOCK ID: B1
          - 실패 단계: 로그인 폼 제출 후 메인 화면 진입 실패
          - 스크린샷: .claude/state/qa-browser/screenshots/F012/03-fail.png
          - 로그: .claude/state/qa-browser/runs/2026-04-30T10-00-00-F012.log
          - 다른 이슈는 건드리지 말 것"
     b. Developer 수정 + 단위 테스트
     c. /project:qa-browser --rerun=last (또는 --feature=Fxxx)
     d. PASS 면 다음 BLOCK, 실패면 동일 BLOCK 재요청 (최대 3회)
4. 모든 BLOCK 처리 후: CONCERN 일괄 보고
5. QA 에이전트가 최종 판정 (passes: true 권한 행사)
```

**에스컬레이션 룰** (F007 과 일관, 단 표현 수정):
- 같은 BLOCK 이 **3회 실패 후** [ESCALATION] 태그 + Planner 호출 (F007 Nit 1 의 표현
  보정과 동일하게 "3회 초과" → "3회 실패 후" 채택)

**스크린샷 git 정책**:
- `.gitignore` 에 `.claude/state/qa-browser/screenshots/` + `runs/` 추가
- 학습 jsonl·analytics jsonl 은 계속 git 포함
- 회귀 baseline 은 별도 결정 (F009 가칭으로 분리)

---

### 결정 6 — F007 design-review 와의 역할 분리

| 영역 | design-review (F007) | qa-browser (F008) |
|---|---|---|
| 검사 방식 | **텍스트 정적 분석** (grep, 문자열 매칭) | **동적 브라우저 자동화** (실제 렌더 + 인터랙션) |
| 외부 의존성 | 0 (stdlib만) | Playwright (옵셔널) |
| 검사 대상 | 코드/문서 (파일) | 실행 중인 페이지 (URL) |
| 정보 구조 (IA) | ✅ 텍스트 (헤딩 레벨, CTA grep) | ❌ 위임 |
| 접근성 (A11Y) | ✅ 텍스트 (alt grep, div onClick grep) | ✅ **동적 보강** (실제 포커스 흐름, 색 대비 측정 — Playwright accessibility scanner) |
| 일관성 (CON) | ✅ 텍스트 (디자인 토큰 grep) | ❌ 위임 |
| 동작 검증 (E2E) | ❌ 위임 | ✅ **단독 담당** |
| 시각 회귀 (스냅샷) | ❌ | ✅ (옵션, F009 분리) |

**중복 영역 (A11Y) 처리**:

A11Y 는 두 도구 모두 검사 가능하나 관점이 다르다:

- design-review A11Y: **소스 코드의 정적 마커** (alt 속성 존재, button 태그 사용 등)
- qa-browser A11Y: **렌더링된 결과의 동적 측정** (실제 포커스 순서, 키보드 트랩, 색
  대비 비율, axe-core 통합 — Playwright 권장)

**중복 호출 시 우선순위**:

```
1. design-review (정적, 빠름, 외부 의존성 0)
2. qa-browser (동적, Playwright 필요, 정적에서 못 잡는 항목 보강)
```

design-review 가 먼저 통과하지 못한 코드를 qa-browser 로 검증하는 것은 비용 낭비.
F007 의 "Reviewer 먼저, design-review 나중" 패턴과 일관.

**ship 커맨드(F003) 연동**:

F003 ship.md 에 qa-browser 카테고리를 추가 (UI 변경 + 동작 검증 필요 시 제안).
형식은 design-review 카테고리와 동일.

---

### 결정 7 — F008 의 phase 분할 (estimated_sessions=3)

**권장 분할**:

| 세션 | 범위 | 산출물 | AC 충족 |
|---|---|---|---|
| **세션 1** | ADR + 슬롯 카탈로그 + 커맨드/스킬 골격 + 미설치 분기 + 템플릿 생성 | ADR-003, `docs/design/F008-qa-browser-templates.md`, `commands/qa-browser.md`, `skills/qa-browser/SKILL.md`, `tests/e2e/_template.spec.ts` 예시 | AC1, AC2, AC3 (텍스트 번역 부분) |
| **세션 2** | Playwright 설치된 환경에서 실제 실행 + 스크린샷 + 원자적 수정 루프 + 셀프 모드 | 실제 실행 검증, 셀프 모드 dry-run, 스크린샷 디렉토리 구조, F003 ship.md 카테고리 추가, `.gitignore` 업데이트 | AC3 (전체), AC4 |
| **세션 3** | 통합 검증 + F007 와의 우선순위 흐름 + Brain·analytics 연동 + 미러링·문서·핸드오프 | 셀프 dry-run + 가짜 다운스트림 시나리오 검증, claude.gstack 미러, CLAUDE.md 업데이트, learnings.jsonl, feature_list.json review→done 전이 | 회귀 검증, 문서 |

**분할 근거**:
- 세션 1 은 외부 의존성 없이 완전 종료 가능 (Playwright 미설치 환경에서도 검증 가능)
- 세션 2 는 Playwright 설치된 환경에서만 검증 가능 → 의존성 분리 명확
- 세션 3 은 통합/문서/핸드오프 — F007 세션 분할과 동일 패턴

**Nit 4건 동시 처리** (부록 A 참조): **세션 1 마지막 단계** (커맨드/스킬 골격 작성
직후) 에 끼워 넣기를 권장. 모두 가벼운 변경 (1줄 수정·1줄 추가) 이므로 세션 1 핸드오프
직전이 자연스럽다. 별도 정리는 비효율 — 세션 1 의 미러링 단계에서 함께 처리.

---

## 대안 검토

| 대안 | 장점 | 단점 | 제외 이유 |
|---|---|---|---|
| 기존 QA 에이전트에 통합 | 에이전트 수 0 증가 | qa.md 정의 변경 → 제약 위배. QA 에이전트의 단일 책임 희석 | 제약 위배 |
| qa-browser 에이전트 신설 | 위임 패턴 일관 | F007 결정 3 일관성 깨짐, 메타-하네스 페르소나 부재 | 결정 4 |
| Playwright 강제 설치 | 가장 단순 | 외부 의존성 0 정책 깨짐 | 결정 1 |
| 텍스트 시뮬레이션만 | F007 패턴 일관 | description 위배 ("실제 브라우저 실행") | 결정 1 |
| acceptance → Playwright 변환을 LLM 외부 API 로 | 자연어 처리 강력 | 외부 API 의존 (OpenAI 등), 비용·정책 위배 | 결정 3 |
| 스크린샷을 git 에 포함 | 회귀 baseline 즉시 사용 | 저장소 비대화, binary diff 무의미 | 결정 5 |
| F007 design-review 에 동적 검사 추가 | 도구 1개로 통합 | F007 외부 의존성 0 결정 6 위배 | F007 ADR 결정 6 |
| `tests/e2e/` 가 아닌 `.claude/skills/qa-browser/templates/` 에 스크립트 저장 | 하네스 내부에 격리 | 사용자가 회귀 테스트로 활용 어려움, QA 에이전트 회귀 누적 위배 | 결정 3 |

---

## 결과

### 긍정적 영향

- **F008 모든 AC 충족**:
  - AC1 (커맨드 파일) — 결정 4
  - AC2 (Playwright 설치 안내, 선택적 의존성) — 결정 1
  - AC3 (acceptance 자동 번역 → Playwright 템플릿) — 결정 3
  - AC4 (실패 시 스크린샷 + Developer 재작업 요청) — 결정 5
- **외부 의존성 0 정책 일관 유지** (설치된 경우만 사용, 미설치 시 차단 X)
- **무회귀**: F005~F007 의 동작 무수정, QA 에이전트 정의 무수정
- **명확한 역할 경계**: QA 에이전트 (passes 권한) ↔ qa-browser (도구), design-review
  (정적) ↔ qa-browser (동적)
- **F007 패턴 일관**: 듀얼 모드, 커맨드+스킬, 원자적 수정 루프, 에스컬레이션 룰
- **메타-하네스 자체 검증 가능**: 셀프 모드 (재정의된 의미) 로 정의 정합성 + dry-run
- **F006 미래 통합 경로 명시**: 후속에서 SKILL.md.template 으로 마이그레이션 가능

### 부정적 영향 / 트레이드오프

- 산출물 2개 신규 (commands + skills) + 1개 설계 문서 (`docs/design/F008-qa-browser-templates.md`)
- 새 상태 디렉토리 `.claude/state/qa-browser/` 도입 (스크린샷·로그용)
- `.gitignore` 1행 추가 (스크린샷·실행 로그)
- Playwright 설치된 환경과 그렇지 않은 환경에서 동작이 분기 → 사용자 인지 부하 (단,
  `host.py` stub 안내 메시지 패턴 차용으로 완화)
- estimated_sessions=3 — 다른 phase 4 features 보다 다소 길지만 외부 의존성 분기 +
  실제 실행 검증 + 통합으로 정당화
- LLM 보강 단계 (결정 3 fallback 3 단계) 는 결정론적이지 않음 → 동일 입력에 다른 결과
  가능. 트레이드오프 의도적 (자연어 다양성 처리)

### 후속 조치

- [ ] (F008 세션 1) 슬롯 카탈로그 + 커맨드/스킬 골격
- [ ] (F008 세션 2) Playwright 실제 실행 + 스크린샷 + 원자적 루프
- [ ] (F008 세션 3) 통합 검증 + 미러링 + 핸드오프
- [ ] (F009 가칭 — 후속) 시각 회귀 baseline 비교 (`expect(page).toHaveScreenshot()`),
      design-reviewer 에이전트 신설 재검토 (F007 결정 6 와 합류)
- [ ] (F006 후속) SKILL.md 토큰화 (`.template` 마이그레이션) — qa-browser 도 함께
- [ ] (F003 ship.md) qa-browser 카테고리 추가 — 세션 2

---

## 구현 가이드 (Developer 인계용)

### 변경/신규 파일 목록

**신규 생성 (세션 1)**:

```
.claude/commands/qa-browser.md                       # /project:qa-browser 슬래시 커맨드
.claude/skills/qa-browser/SKILL.md                   # 슬롯 카탈로그·실행 흐름·결과 양식
docs/design/F008-qa-browser-templates.md             # 슬롯 카탈로그 raw 정의 (단일 소스)
tests/e2e/_template.spec.ts                          # Playwright 스크립트 템플릿 예시
```

**신규 생성 (세션 2)**:

```
.claude/state/qa-browser/                            # 디렉토리 (런타임 생성, gitignore 일부)
.claude/state/qa-browser/screenshots/.gitkeep        # 디렉토리 보존 마커
.claude/state/qa-browser/runs/.gitkeep               # 디렉토리 보존 마커
```

**수정 (세션 1~2)**:

```
CLAUDE.md                                            # "빠른 시작" 섹션에 /project:qa-browser
                                                     # "에이전트 역할 분담" 표 아래에 qa-browser 도구 분리 박스
                                                     # "상태 파일" 표에 .claude/state/qa-browser/ 행
                                                     # 디렉토리 트리에 commands/qa-browser.md, skills/qa-browser/, docs/design/F008 추가
                                                     # design-review 호출 기준과 같은 형식의 qa-browser 호출 기준
.gitignore                                           # .claude/state/qa-browser/screenshots/ 와 runs/ 추가
.claude/commands/ship.md                             # qa-browser 카테고리 추가 (F003 연동)
feature_list.json                                    # F008 status: in-progress → review (Developer 작업 끝)
.claude/state/learnings.jsonl                        # 새 학습 append (architecture 1 + pattern 1 + pitfall 1)
```

**Nit 4건 (세션 1 미러링 단계에 동시 처리)**:

```
.claude/commands/design-review.md                    # L111 "3회 초과" → "3회 실패 후"
CLAUDE.md                                            # 디렉토리 트리에 docs/adr/ + docs/design/ 추가
.claude/skills/design-review/SKILL.md                # SSoT 유지보수 주의 한 줄 추가
docs/design/F007-design-review-checklist.md         # 동일 (체크리스트 SSoT 표시)
src/harness_template/claude.gstack/harness/...      # 모든 변경 미러
```

**의도적 미수정 (제약 준수)**:

```
.claude/agents/qa.md                                 # 손대지 않는다 (제약: 기존 정의 보존)
.claude/agents/*.md                                  # 다른 에이전트도 손대지 않는다
.claude/settings.json                                # 손대지 않는다 (Claude Code 스키마 격리)
.claude/bin/host_adapters/*.py                       # 손대지 않는다 (F006 격리)
.claude/bin/brain.py                                 # 손대지 않는다 (F005 격리)
docs/adr/ADR-001*.md, ADR-002*.md                    # 기존 ADR 무수정
src/harness_template/claude/                         # baseline 동결 (CLAUDE.md L83)
```

**미러링 (CLAUDE.md 동기화 정책)**:

`.claude/`, `CLAUDE.md`, `docs/adr/`, `docs/design/` 의 모든 변경은 다음 위치에 미러:

```
src/harness_template/claude.gstack/harness/CLAUDE.md
src/harness_template/claude.gstack/harness/docs/adr/ADR-003-qa-browser.md
src/harness_template/claude.gstack/harness/docs/design/F008-qa-browser-templates.md
src/harness_template/claude.gstack/harness/.claude/commands/qa-browser.md
src/harness_template/claude.gstack/harness/.claude/commands/design-review.md  (Nit 1)
src/harness_template/claude.gstack/harness/.claude/commands/ship.md
src/harness_template/claude.gstack/harness/.claude/skills/qa-browser/SKILL.md
src/harness_template/claude.gstack/harness/.claude/skills/design-review/SKILL.md  (Nit 3)
src/harness_template/claude.gstack/harness/tests/e2e/_template.spec.ts
src/harness_template/claude.gstack/harness/.gitignore
```

`claude/` (baseline) 은 동결 — 손대지 않는다.
`openai/` 는 정적 산출물 — qa-browser 는 후속 phase 에서 codex 어댑터 실구현 후 자동
재생성 (현재 phase 에서는 openai/ 미러링 X, codex 어댑터가 stub 이므로).

**`__pycache__` 제외 처리** (Nit 4):
- 미러링 시 `rsync --exclude='__pycache__' --exclude='*.pyc'` 사용 권장
- 또는 `.gitignore` 의 글로벌 패턴으로 충분 (이미 git 추적 안 함)
- claude.gstack 미러에 실수로 들어가지 않도록 미러링 스크립트나 수동 명령에 명시

### 단계별 작업 순서

#### 세션 1 — ADR + 골격 + 미설치 분기 + 템플릿

**Step 1.1 — 슬롯 카탈로그 raw 정의 작성** (`docs/design/F008-qa-browser-templates.md`)
- 결정 3 의 슬롯 표를 그대로 옮겨 정형화
- 각 슬롯별 매칭 정규식 + Playwright 코드 조각 + 예시 acceptance
- TypeScript 기본 (Playwright 권장), Python 변형은 후속 phase
- 단일 소스 (SKILL.md, commands 가 모두 이 문서를 참조)
- 인수 기준 충족: **AC3 raw 정의**

**Step 1.2 — `commands/qa-browser.md` 작성**
- 다른 commands/*.md 와 동일 구조: `# /project:qa-browser` + 사용법 + 실행 + 출력 예시
- 플래그: `--feature`, `--target`, `--scope`, `--rerun`
- 본문에서 SKILL.md 참조
- Playwright 감지 → 미설치 시 안내 + 템플릿 생성, 설치 시 실제 실행 분기
- 인수 기준 충족: **AC1, AC2 (안내 메시지 부분)**

**Step 1.3 — `skills/qa-browser/SKILL.md` 작성**
- frontmatter: `name: qa-browser`, `description`, `host: claude-code`
- 본문 구성:
  1. 호출 진입점
  2. Playwright 감지 + 분기 흐름
  3. acceptance → 슬롯 매칭 의사코드
  4. Playwright 미설치 안내 메시지 양식
  5. 결과 양식 (BLOCK/CONCERN/PASS — design-review 와 같은 라벨 사용)
  6. 원자적 수정 루프 (의사코드)
  7. QA 에이전트와의 역할 경계 (결정 4 표 그대로 인용)
  8. design-review 와의 역할 경계 (결정 6 표 그대로 인용)
- 인수 기준 충족: **AC2, AC3, AC4**

**Step 1.4 — Playwright 스크립트 템플릿 예시** (`tests/e2e/_template.spec.ts`)
- 모든 슬롯이 채워진 hello-world 예시 (로그인 + 페이지 진입 + 텍스트 검증 + 스크린샷)
- TODO 주석 형식 명시 (매칭 실패 항목 보존용)
- 스크린샷 저장 경로: `.claude/state/qa-browser/screenshots/<feature_id>/`

**Step 1.5 — Nit 4건 처리** (세션 1 미러링 직전)
- Nit 1: `commands/design-review.md` L111 "3회 초과" → "3회 실패 후"
- Nit 2: CLAUDE.md 디렉토리 트리에 `docs/adr/` + `docs/design/` 추가
- Nit 3: `skills/design-review/SKILL.md` + `docs/design/F007-...md` 에 SSoT 유지보수
  주의 한 줄 추가 ("이 파일과 raw 정의는 동기화 유지 필요")
- Nit 4: 미러링 명령에 `--exclude='__pycache__' --exclude='*.pyc'` 추가

**Step 1.6 — 미러링 동기화**
- `claude.gstack/harness/` 에 모든 신규/수정 파일 복제
- `diff -r` 로 동기화 누락 없는지 확인
- `__pycache__` 제외 적용 확인

**Step 1.7 — 세션 1 핸드오프**
- `feature_list.json` F008 은 그대로 `in-progress` 유지 (세션 2 진행 표시)
- `/project:context-save "F008 세션 1 — 골격 + Nit 4건 완료"`

#### 세션 2 — 실제 실행 + 스크린샷 + 셀프 모드

**Step 2.1 — Playwright 감지 헬퍼 작성** (커맨드 본문 또는 `.claude/bin/qa_browser.py` — 결정은 Developer 재량)
- subprocess 로 `node --version`, `npx playwright --version` 호출
- 모두 try/except, exit 0 유지

**Step 2.2 — 슬롯 매칭 로직 작성** (커맨드 본문 또는 헬퍼)
- 정규식 + 키워드 매칭
- 매칭 실패 시 TODO 주석 보존

**Step 2.3 — 실제 실행 + 스크린샷 캡처**
- `npx playwright test tests/e2e/<feature_id>.spec.ts` 실행
- stdout/stderr → `.claude/state/qa-browser/runs/<ts>-<feature_id>.log`
- 스크린샷 자동 저장 (Playwright 설정으로 매 step 종료 시)

**Step 2.4 — 원자적 수정 루프 구현**
- BLOCK 발견 → Developer 위임 메시지 (스크린샷 경로 첨부)
- 3회 실패 후 [ESCALATION] 태그

**Step 2.5 — 셀프 모드 구현**
- `--scope=self`: Playwright 감지 dry-run + 스크립트 템플릿 생성 검증 + 스크린샷
  디렉토리 작성 가능성 확인 + exit 0
- 메타-하네스 정의 정합성 검증

**Step 2.6 — F003 ship.md 카테고리 추가**
- UI 변경 + 동작 검증 필요 시 qa-browser 제안 항목 추가

**Step 2.7 — `.gitignore` 업데이트**
- `.claude/state/qa-browser/screenshots/` + `runs/` 추가
- `.gitkeep` 은 git 포함

**Step 2.8 — 세션 2 핸드오프**
- `/project:context-save "F008 세션 2 — 실제 실행 + 셀프 모드 완료"`

#### 세션 3 — 통합·문서·핸드오프

**Step 3.1 — CLAUDE.md 업데이트**
- "빠른 시작" 섹션에 `/project:qa-browser` 블록 추가
- "에이전트 역할 분담" 표 아래 박스 (QA ↔ qa-browser, design-review ↔ qa-browser
  분리 명시)
- "상태 파일" 표에 `.claude/state/qa-browser/` 행 추가
- 디렉토리 트리 업데이트
- "qa-browser 호출 기준" 박스 추가 (design-review 호출 기준과 같은 형식)

**Step 3.2 — 자체 dry run (셀프 모드 검증)**
- `/project:qa-browser --scope=self` 호출 → 정의 정합성 출력
- 본 ADR 작성 직후라면 모든 자체 검사 PASS 되어야 함

**Step 3.3 — 다운스트림 시뮬레이션 (가짜 프로젝트)**
- 임시 디렉토리 (`/tmp/qa-browser-test/`) 에 가짜 acceptance 가진 가짜 feature 생성
- 슬롯 매칭 → 템플릿 생성 → (Playwright 설치 시) 실제 실행
- 미설치 환경에서도 템플릿 생성 + 안내까지 검증 (분기 양쪽 모두)

**Step 3.4 — Brain·analytics 연동**
- analytics.jsonl 에 qa-browser 이벤트 append (선택, F004 와 일관)
- learnings.jsonl 에 다음 후보 기록:
  - **architecture**: "qa-browser 는 옵셔널 의존성 (Playwright) — Brain hook-failure-tolerance
    패턴 준수, 미설치 시 차단 X + 템플릿 생성 fallback"
  - **pattern**: "acceptance_criteria 자연어 → Playwright 템플릿 = 슬롯 카탈로그 +
    LLM 보강 (3 단계 fallback)"
  - **pitfall**: "qa-browser 는 QA 에이전트의 도구이지 대체 아님 — passes: true 권한은
    QA 에이전트 단독 보유 (역할 경계 SKILL.md 명시)"

**Step 3.5 — 미러링 최종 동기화**
- 세션 1·2 의 모든 변경이 `claude.gstack/harness/` 에 반영되었는지 `diff -r` 로 확인
- `__pycache__` 제외 (Nit 4)

**Step 3.6 — 핸드오프**
- `feature_list.json` F008: `status: "in-progress" → "review"`
- Reviewer 에이전트 호출 → APPROVED → `status: "review" → "qa"`
- QA 에이전트 호출 → 본 도구를 활용하여 자체 검증 (메타) → `passes: true`
- `/project:context-save "F008 세션 3 — 통합 + 핸드오프 완료"`

### 인수 기준 매핑

| AC | 충족 단계 | 비고 |
|---|---|---|
| **AC1** /project:qa-browser 커맨드 | 세션 1 Step 1.2 | commands/qa-browser.md 신규 + CLAUDE.md 노출 (세션 3) |
| **AC2** Playwright 설치 안내 (선택적 의존성) | 세션 1 Step 1.2~1.3, 세션 2 Step 2.1 | 결정 1 옵셔널 의존성 패턴. 미설치 분기 + 안내 메시지 양식 |
| **AC3** acceptance_criteria 자동 번역 → Playwright 스크립트 템플릿 | 세션 1 Step 1.1, 세션 2 Step 2.2 | 슬롯 카탈로그 + 매칭 + LLM 보강 fallback. 결과물: tests/e2e/<feature_id>.spec.ts |
| **AC4** 실패 시 스크린샷 저장 + Developer 재작업 요청 | 세션 2 Step 2.3~2.4 | .claude/state/qa-browser/screenshots/ + F007 의 원자적 수정 루프 인터페이스 |

### 테스트 방법

메타-하네스 + 옵셔널 의존성 특성상 다음 4 방식으로 검증:

**방식 1 — Playwright 미설치 환경 (즉시 가능, 정책 일관 검증)**

```
# (1) Playwright 가 없는 환경에서 호출
which node || echo "node 미설치 — 시뮬레이션 시작"
/project:qa-browser --feature=F008

# 기대:
#   - "Playwright 미설치 안내" 메시지 출력
#   - tests/e2e/F008.spec.ts 템플릿 파일 생성
#   - exit 0 (차단 없음 — Brain hook-failure-tolerance 일관)
```

**방식 2 — 셀프 모드 dry run (즉시 가능)**

```
/project:qa-browser --scope=self

# 기대:
#   - Playwright 감지 결과 출력 (설치 여부)
#   - 스크립트 템플릿 생성 로직 dry-run (실제 파일 생성 X 또는 임시 위치)
#   - .claude/state/qa-browser/ 디렉토리 작성 가능성 확인
#   - 결과 양식대로 마크다운 출력
#   - exit 0
```

**방식 3 — Playwright 설치된 환경 (선택, 검증 강화)**

```
# (3) Playwright 설치
npm init -y
npm install -D @playwright/test
npx playwright install chromium

# (4) 가짜 다운스트림 시나리오
mkdir -p /tmp/qa-browser-test
cd /tmp/qa-browser-test
# (간단한 정적 HTML 페이지 + 가짜 feature_list.json 작성)
# 하네스 환경에서 호출
/project:qa-browser --feature=Ftest --target=http://localhost:8000

# 기대:
#   - 슬롯 매칭 → 스크립트 생성
#   - npx playwright test 실행
#   - 성공·실패 스크린샷 저장
#   - 실패 시 Developer 위임 메시지 (스크린샷 경로 첨부)
```

**방식 4 — 원자적 수정 루프 검증**

```
# (5) 의도적 BLOCK 트리거하는 가짜 acceptance 작성
# (6) /project:qa-browser --feature=Ffail
# (7) BLOCK 1건 감지 → Developer 위임 메시지 확인
# (8) "수정" 시뮬레이션 (가짜 코드 변경)
# (9) /project:qa-browser --rerun=last
# (10) PASS 확인
# (11) 3회 연속 실패 시뮬레이션 → [ESCALATION] 태그 확인
```

**모든 단계가 exit 0 으로 종료되는지** 확인 (호출자 차단 방지 원칙).

### 피해야 할 패턴

- ❌ Playwright 강제 설치 또는 미설치 시 차단 (결정 1 — 옵셔널 의존성 정책)
- ❌ 새 에이전트 `.claude/agents/qa-browser.md` 신설 (결정 4 — F007 일관)
- ❌ QA 에이전트 정의 변경 (제약 — qa.md 무수정)
- ❌ `passes: true` 권한 행사 (QA 에이전트 단독)
- ❌ design-review 와 동일한 정적 검사 중복 수행 (결정 6 — A11Y 만 동적 보강)
- ❌ 외부 API 호출 (OpenAI Vision 등 — 결정 3, 슬롯 매칭은 stdlib + LLM 컨텍스트만)
- ❌ 스크린샷 git 포함 (결정 5 — `.gitignore` 처리)
- ❌ 셀프 모드에서 실제 브라우저 실행 시도 (하네스에 UI 없음 — 정의 검증만)
- ❌ BLOCK 일괄 위임 (결정 5 — 원자적 1건씩, F007 일관)
- ❌ 슬롯 카탈로그를 SKILL.md 에 직접 인라인 (Step 1.1 의 별도 문서로 단일 소스)
- ❌ `host.json`/`settings.json` 수정 (F006 격리 정책 위배)
- ❌ baseline (`src/harness_template/claude/`) 수정 (CLAUDE.md L83 동결 정책)
- ❌ openai/ 변형 수정 (codex 어댑터 stub — 후속 phase 에서 자동 재생성)

---

## 부록 A — Nit 4건 처리 가이드

F007 Reviewer 가 F008 으로 이관한 항목 4건. 모두 가벼운 변경 (1줄 수정·1줄 추가) 이므로
F008 **세션 1 의 Step 1.5 (미러링 직전)** 에 동시 처리 권장. 이유:

1. **세션 1 은 외부 의존성 없이 종료 가능** → Nit 작업도 동일한 의존성 프로파일
2. **미러링 단계가 한 번** → Nit 변경도 같은 미러링 사이클에 포함, 작업 효율 ↑
3. **별도 정리는 비효율** → 세션 분리하면 미러링 사이클을 추가로 돌려야 함

### Nit 1 — `commands/design-review.md:111` "3회 초과" → "3회 실패 후"

**위치**: `.claude/commands/design-review.md` L111

```
변경 전: 3회 초과 → [ESCALATION] 태그 + Planner에 Feature 재분해 요청
변경 후: 3회 실패 후 → [ESCALATION] 태그 + Planner에 Feature 재분해 요청
```

**근거**: "3회 초과" 는 4회째부터 발동하는 의미로 오해 가능. "3회 실패 후" 가 의도
명확. F008 결정 5 의 에스컬레이션 룰도 동일 표현 채택 — 표현 일관성 확보.

### Nit 2 — CLAUDE.md 디렉토리 트리에 `docs/adr/` + `docs/design/` 동시 추가

**위치**: CLAUDE.md 의 "🗂️ 디렉토리 구조" 섹션

**현재 표현**: `docs/` 만 단일 항목으로 표시

**권장 표현**:

```
├── docs/                     # 문서
│   ├── adr/                  # 아키텍처 결정 기록 (ADR-NNN-*.md)
│   └── design/               # 상세 설계 문서 (FNNN-*.md)
```

**근거**: ADR 3개 (001/002/003) + design 문서 2개 (F007/F008) 가 누적되었는데 트리에서
보이지 않음 → 사용자 발견성 ↓.

### Nit 3 — SKILL.md / 체크리스트에 SSoT 유지보수 주의 한 줄

**위치**:
- `.claude/skills/design-review/SKILL.md` (헤더 주변)
- `docs/design/F007-design-review-checklist.md` (헤더 주변)
- (F008 도 같은 패턴 적용) `.claude/skills/qa-browser/SKILL.md` + `docs/design/F008-qa-browser-templates.md`

**권장 한 줄**:

```
> **SSoT 유지보수 주의**: 이 문서와 raw 정의 (docs/design/F007-...) 는 단일 소스 원칙.
> 한 쪽 변경 시 반드시 다른 쪽 동기화 — diff 누락은 design-review --scope=self 에서
> CON-S2 항목으로 자동 탐지된다.
```

**근거**: F007 ADR-002 결정 4 에서 raw 정의 + SKILL.md 분리 도입. SSoT 가 둘로 나뉘면
일관성이 항상 수동 관리 필요 → 명시 한 줄로 잊지 않게 함.

### Nit 4 — claude.gstack 미러에 `__pycache__` 제외 처리

**위치**: 미러링 명령 (CLAUDE.md "harness_template 동기화 정책" 섹션)

**현재 상태**: 미러링 명령이 명시되지 않아 사용자가 `cp -r` 또는 `rsync -a` 사용 시
`__pycache__` 가 함께 복사될 수 있음.

**권장 보강** (CLAUDE.md "동기화 제외" 항목에 추가):

```
**동기화 제외:**
- `.claude/state/` (checkpoints, learnings.jsonl, ...)
- `feature_list.json`
- `claude-progress.txt`
- `__pycache__/`, `*.pyc`  ← 신규 추가 (Python 캐시 — 미러에 들어가면 안 됨)
```

**미러링 명령 권장**:

```bash
rsync -a --exclude='__pycache__' --exclude='*.pyc' --exclude='state/' \
  .claude/ src/harness_template/claude.gstack/harness/.claude/
```

**근거**: F006 에서 `host_adapters/` 가 도입되어 Python 모듈이 늘었음. `__pycache__`
는 환경별로 다르고 미러에 들어가면 baseline 과 차이가 발생 → IA-S3 (셀프 모드) 에서
거짓 BLOCK.

### 권장 처리 순서 (세션 1 Step 1.5)

1. Nit 1: `design-review.md` L111 1줄 수정 → 미러
2. Nit 2: `CLAUDE.md` 트리 2줄 추가 → 미러
3. Nit 3: `SKILL.md` + raw 정의 한 줄 추가 (F007·F008 양쪽) → 미러
4. Nit 4: `CLAUDE.md` 동기화 정책 보강 + 미러링 명령에 exclude 적용 → 미러

총 5~10분 작업. 세션 1 의 미러링 사이클 1회로 흡수.

---

*작성: architect 에이전트 | 날짜: 2026-04-30 | 상태: Accepted*
