# ADR-002: Design Review 강화 (단계 1) — 메타-하네스 제공 모델 결정

> Feature: F007 — Phase 4 Design Review 강화 (단계 1)
> 작성: architect 에이전트 | 날짜: 2026-04-30

## 상태

`Accepted` — 본 ADR은 **다운스트림 프로젝트 1차 대상 + 자체 하네스 산출물 2차 대상**의
이중 모드(C 변형) 설계 감사 도구를, **커맨드 + 스킬 2종 (에이전트 신설 X)** 형태로
도입한다. GPT Image API 등 비주얼 분석은 도입하지 않으며, 텍스트 기반 체크리스트
+ 원자적 수정 루프만 포함한다.

---

## 컨텍스트

### 메타-하네스 특성으로 인한 본질적 질문

이 프로젝트는 자체 UI를 가진 애플리케이션이 아니라, 다른 프로젝트가 사용할
**에이전트/스킬/커맨드/훅 모음**(메타-하네스)이다. 따라서 F007의 "Design Review"
대상이 **무엇을 검사하느냐**가 가장 본질적인 설계 판단이다.

가능한 해석:

| 해석 | 검사 대상 | 사용 시점 |
|---|---|---|
| (A) 다운스트림 모드 | 사용자 프로젝트의 UI 코드/문서 (HMI 화면, 디자인 시스템 컴포넌트, 마크다운 문서 IA) | 하네스가 이식된 프로젝트에서 |
| (B) 셀프 모드 | 이 하네스 자신의 ADR/문서/스킬 정합성 (CLAUDE.md ↔ 커맨드 ↔ 스킬 일관성) | 하네스 개발 시 (지금 프로젝트) |
| (C) 듀얼 모드 | 둘 다 (스코프 플래그로 분기) | 둘 다 |

F007 description의 "/design-review 스킬 추가"와 acceptance_criteria의 "정보 구조,
접근성, 일관성"은 (A) 의도가 강하다. 다만 메타-하네스 환경에서 (A)만 채택하면
**테스트 시 검증할 대상이 없다**(자체 UI 부재). 한편 (B)만 채택하면 acceptance의
"접근성"과 잘 안 맞는다 (하네스에는 키보드 네비/aria-label이 없다).

### 기존 Reviewer 에이전트와의 충돌 우려

`.claude/agents/reviewer.md` 의 Reviewer 에이전트는 이미 다음을 책임진다:

- 코드 품질 (네이밍, SRP, DRY, docstring)
- 보안 (SQL Injection, XSS, 시크릿 누출)
- 성능 (병목, N+1, 메모리)
- 자동화 도구 실행 (lint, typecheck, audit)

design-review가 동일한 영역을 중복 검사하면 사용자가 두 도구를 어떤 순서로 어떻게
호출해야 할지 혼동하게 된다. **역할 경계가 명확해야 한다.**

### 제약

- **외부 의존성 0**: F005/F006 정책 일관 (Python stdlib만, Playwright/Pillow/GPT 금지)
- **이번 phase는 텍스트만**: 이미지/스크린샷 처리 도구 도입 X
- **무회귀**: 기존 Reviewer 에이전트 정의는 변경하지 않는다
- **메타-하네스 적용 가능성**: 자체 UI가 없으므로 검증 시나리오를 명시해야 함
- **ship 커맨드(F003) 연동 호환성**: F003 ship.md가 이미 `design-review` 를 카테고리로
  언급하고 있으므로(grep 확인), 인터페이스가 깨지면 안 됨

---

## 결정

### 결정 1 — 검사 대상: (C) 듀얼 모드, 단 1차 시민은 다운스트림(A)

**채택**: 듀얼 모드. `--scope` 플래그로 분기.

| 스코프 | 의미 | 기본값 | 검사 산출물 |
|---|---|---|---|
| `downstream` | 사용자 프로젝트의 UI/문서 (1차 시민) | ✅ | `src/`, `docs/`, `components/`, `pages/` 등 사용자 코드 |
| `self` | 이 하네스 자신 (메타) | (옵션) | `.claude/`, `CLAUDE.md`, `docs/adr/`, `feature_list.json` |

**호출 예시**:

```
/project:design-review                       # downstream 기본
/project:design-review --scope=self          # 하네스 자체 정합성
/project:design-review --scope=downstream --target=src/components/
```

**근거**:

| 옵션 | 장점 | 단점 |
|---|---|---|
| (A) 다운스트림만 | F007 의도와 일치, "접근성" AC와 자연스러움 | 메타-하네스 환경에서 테스트할 대상 없음 → 검증 어려움 |
| (B) 셀프만 | 이 프로젝트에서 즉시 가치, 자체 검증 가능 | "접근성" AC 충족 어색, 하네스가 다른 프로젝트로 배포되면 가치 감소 |
| **(C) 듀얼** | 두 시나리오 모두 지원, 셀프 모드로 자체 검증 가능 ← 메타-하네스 한정 가치, 다운스트림 모드로 본래 의도 달성 | 체크리스트가 두 벌 필요 |

→ **(C) 채택**. 단, 다운스트림 모드(A)를 1차 시민(기본값)으로, 셀프 모드(B)는
2차(옵션)로 두어 의도 우선순위를 표현한다.

#### 다운스트림 사용 시나리오 (구체)

**시나리오 1 — HMI 앱의 화면 레이아웃 검사**:
> 자동차 인포테인먼트 HMI 프로젝트에 이 하네스가 이식되었다. 디자이너가
> `pages/Navigation.tsx` 의 정보 계층(헤더/지도/POI 카드)을 점검해 달라고 요청한다.
> `/project:design-review --target=pages/Navigation.tsx` 실행 → 정보 구조 표
> (요소 트리, 시각적 무게, 진입 동작) + 접근성 표 (터치 타깃 크기, 색 대비, 포커스
> 흐름) + 일관성 표 (디자인 토큰 사용, 컴포넌트 재사용 여부)를 출력한다.

**시나리오 2 — 디자인 시스템 컴포넌트 일관성 점검**:
> React 컴포넌트 라이브러리 프로젝트에서 `src/components/Button/` 의 변형(primary,
> secondary, ghost) 정의가 디자인 토큰과 일관되는지 검사한다. design-review가
> 코드를 읽고 "Button.tsx에서 padding이 토큰이 아닌 하드코딩된 12px임 (CONCERN —
> theme.spacing.sm 사용 권장)" 식의 발견을 텍스트로 출력 → 원자적 수정 루프로 인계.

#### 셀프 사용 시나리오

**시나리오 3 — 자체 정합성 점검**:
> `/project:design-review --scope=self` 실행 → CLAUDE.md의 디렉토리 트리에 적힌
> 파일들이 실제로 존재하는지, `.claude/commands/*.md` 18개가 모두 CLAUDE.md "빠른
> 시작" 섹션에 노출되는지, ADR에서 참조한 파일 경로가 유효한지, feature_list.json의
> id가 ADR/checkpoints에서 일관되게 쓰이는지를 검사. 본 ADR을 다음 메타 단계에서
> 검증할 때도 사용 가능.

---

### 결정 2 — Reviewer 에이전트와의 역할 분리

기존 Reviewer는 **건드리지 않는다**(reviewer.md 무수정). 새 design-review 산출물은
다음 경계를 명시적으로 선언한다.

| 영역 | Reviewer | design-review |
|---|---|---|
| 코드 품질·SRP·DRY·docstring | ✅ 담당 | ❌ 위임 |
| 보안 (SQLi/XSS/시크릿) | ✅ 담당 | ❌ 위임 |
| 성능 (N+1, 알고리즘) | ✅ 담당 | ❌ 위임 |
| 린트·타입체크·테스트 통과 | ✅ 담당 | ❌ 위임 |
| **정보 구조 (IA)** — 요소 계층, 시각적 무게, 명명 | ❌ | ✅ **담당** |
| **접근성 (A11y)** — 키보드/aria/대비/터치 타깃 | ❌ | ✅ **담당** |
| **일관성** — 디자인 토큰, 컴포넌트 재사용, 명명 | ❌ | ✅ **담당** |
| **셀프 정합성** — CLAUDE.md ↔ 커맨드 ↔ ADR | ❌ | ✅ **담당** (--scope=self) |

**중복 호출 시 우선순위**:
- `/project:ship` (F003) 이 두 카테고리(예: UI + 보안)에 걸친 diff를 발견하면,
  **Reviewer를 먼저, design-review를 나중에** 제안한다. 코드 동작이 보장된 후
  디자인을 평가하는 것이 자연스럽기 때문 (= 깨진 코드의 IA를 평가하는 것은 무의미).
- 두 도구가 **같은 파일에서 동일 발견**을 보고하면, design-review가 출력에서 중복
  제거 후 "Reviewer에서 동일 사항 보고됨, 우선순위는 Reviewer를 따름" 메모만
  남긴다. design-review는 자신의 영역에 한정해 추가 발견만 보고.

**왜 새 에이전트를 만들지 않는가** — 결정 3 참조.

---

### 결정 3 — 노출 형태: **커맨드 1개 + 스킬 1개** (에이전트 신설 X)

**채택**: 다음 2개 산출물.

```
.claude/commands/design-review.md         # /project:design-review 슬래시 커맨드
.claude/skills/design-review/SKILL.md     # 체크리스트·결과 양식·원자적 루프 가이드
```

**채택하지 않은 것**:

```
.claude/agents/design-reviewer.md         # ❌ 신설 안 함
```

**근거 비교**:

| 옵션 | 장점 | 단점 | 결정 |
|---|---|---|---|
| (i) 커맨드만 | 가장 단순, 진입점 명확 | 체크리스트가 커맨드 본문에 묶여 재사용 어려움 | 부족 |
| (ii) 에이전트만 | 에이전트 위임 패턴 일관 (Planner/Architect/...) | 에이전트가 늘어날수록 호출자 인지 부하 ↑, Reviewer와 역할 충돌 위험 ↑, 메타-하네스에서 자체 코드를 평가할 진짜 페르소나가 부재 | 과함 |
| (iii) 스킬만 | 재사용성 최고 | 진입점이 없어 사용자가 호출 방법 모름 | 부족 |
| **(iv) 커맨드 + 스킬** | 진입점 명확 + 체크리스트·양식 재사용 + 에이전트 수 증가 없음 + Reviewer와 역할 분리 자연스러움 | 산출물 2개 | **채택** |
| (v) 커맨드 + 에이전트 + 스킬 | 모든 패턴 일관 | 과도, F007 estimated_sessions=2 와 안 맞음 | 과함 |

**핵심 통찰**: design-review는 **검사 절차**이지 **위임 대상**이 아니다. Reviewer
에이전트가 이미 코드 리뷰의 페르소나를 차지하고 있고, 디자인 검사는 동일 페르소나가
다른 체크리스트로 검사하는 행위로 모델링하는 것이 자연스럽다. 호출자가 발견된
이슈를 Developer에 인계하는 흐름은 **커맨드 본문**이 오케스트레이션하고, **상세
체크리스트와 결과 양식**은 스킬이 제공한다.

**결론**: F008 QA 브라우저 자동화에서 별도 에이전트가 필요해질 가능성은 있으나,
F007 단계에서는 에이전트 신설을 보류한다. 향후 시각 분석(스크린샷 OCR/diff)이
도입되면 그때 design-reviewer 에이전트 신설을 재검토 (확장 포인트, 결정 6 참조).

---

### 결정 4 — 체크리스트 구조: 3 카테고리 × PASS/CONCERN/BLOCK 라벨

체크리스트는 마크다운 표 형식, 카테고리당 8~12개 항목. 각 항목은 **PASS / CONCERN
/ BLOCK** 셋 중 하나로 라벨링 (Reviewer의 MUST/SHOULD/CONSIDER와 의도적으로
다른 라벨 — 영역 구분이 시각적으로 즉시 보이도록).

| Reviewer 라벨 | design-review 라벨 | 의미 |
|---|---|---|
| MUST | **BLOCK** | 머지 차단 — Developer 즉시 수정 필요 |
| SHOULD | **CONCERN** | 권장 — 우선순위 따라 수정 |
| CONSIDER | (해당 없음 — 불필요한 카테고리는 제거) | — |
| (해당 없음) | **PASS** | 검사 항목 명시적 통과 (체크리스트 가시성) |

**3 카테고리 상세**:

#### A. 정보 구조 (Information Architecture)

다운스트림 모드 (UI 코드/페이지 대상):

| # | 항목 | 검사 방법 | 라벨 기준 |
|---|---|---|---|
| IA-1 | 요소 계층(visual hierarchy)의 명시적 표현 | 헤딩 레벨/시맨틱 태그 검사 | h1 누락 또는 h2 → h4 점프 시 BLOCK |
| IA-2 | 진입점 1차 액션이 페이지당 1개 명확 | primary CTA 식별 | CTA 부재 또는 3개+ 동등 비중 시 CONCERN |
| IA-3 | 정보 그룹핑(시각적 청크) 적절성 | 컨테이너/섹션 구조 | 단일 컨테이너에 9+ 자식 시 CONCERN |
| IA-4 | 명명 일관성 (라벨, 메뉴 항목) | 중복/유사 라벨 검사 | 동일 의미 다른 라벨 시 CONCERN |
| IA-5 | 빈 상태(empty state) 처리 명시 | 분기 처리 검사 | 누락 시 CONCERN |
| IA-6 | 로딩/에러 상태 처리 | 분기 처리 검사 | 누락 시 BLOCK |
| IA-7 | 진행 상황(progress) 가시화 | 멀티스텝 플로우의 표시기 | 3+ 스텝 플로우에 표시기 없음 시 CONCERN |
| IA-8 | URL/라우트 명명의 의도 일치 | 라우트 ↔ 페이지 목적 | 불일치 시 CONCERN |

셀프 모드 (하네스 자신 대상):

| # | 항목 | 검사 방법 | 라벨 기준 |
|---|---|---|---|
| IA-S1 | CLAUDE.md 디렉토리 트리 ↔ 실제 파일 일치 | `find . -type f` 비교 | 불일치 시 BLOCK |
| IA-S2 | `.claude/commands/*.md` 18개 모두 CLAUDE.md "빠른 시작" 섹션에 노출 | grep 매칭 | 누락 시 CONCERN |
| IA-S3 | ADR에서 참조한 파일 경로 유효성 | path 추출 + exists | 무효 경로 시 BLOCK |
| IA-S4 | feature_list.json id ↔ ADR/checkpoints id 일관 | grep | 불일치 시 BLOCK |

#### B. 접근성 (Accessibility)

WCAG 2.1 AA 일부 차용 + 자체 정의. **전체 준수가 아닌 핵심 항목만** (외부 검사
도구 미도입 원칙).

| # | 항목 | 검사 방법 | 라벨 기준 |
|---|---|---|---|
| A11Y-1 | 모든 image에 alt 속성 | grep `<img.*alt=` | 누락 시 BLOCK |
| A11Y-2 | 인터랙티브 요소에 aria-label 또는 visible label | button/a 검사 | 라벨 부재 시 BLOCK |
| A11Y-3 | 키보드 포커스 흐름 (tabindex) | tabindex 사용 검사 | tabindex > 0 시 CONCERN (anti-pattern) |
| A11Y-4 | 폼 input ↔ label 연결 (`htmlFor`/`for`) | label-input 매칭 | 누락 시 BLOCK |
| A11Y-5 | 색만으로 의미 전달 금지 | error/success가 색만으로 구별되는지 | 색 only 시 CONCERN |
| A11Y-6 | 터치 타깃 ≥ 44×44px (HMI/모바일) | 인라인 스타일/css 검사 | 작은 타깃 시 CONCERN |
| A11Y-7 | aria-live 영역 (동적 변경) | toast/alert 패턴 | 동적 변경에 미적용 시 CONCERN |
| A11Y-8 | 의미적 HTML (button vs div onClick) | div onClick 검사 | div onClick 시 BLOCK |

셀프 모드에서는 A11Y 카테고리를 **N/A 라벨로 일괄 표시**하고 보고하지 않는다
(하네스에는 UI 없음).

#### C. 일관성 (Consistency)

| # | 항목 | 검사 방법 | 라벨 기준 |
|---|---|---|---|
| CON-1 | 디자인 토큰 사용 (color/spacing/font) | 하드코딩 hex/px 탐지 | 토큰 미사용 시 CONCERN |
| CON-2 | 컴포넌트 재사용 (DRY) | 동형 마크업 중복 | 3+ 중복 시 CONCERN |
| CON-3 | 명명 규칙 (kebab/camel/Pascal 일관) | 파일명/식별자 검사 | 혼용 시 CONCERN |
| CON-4 | 타이포그래피 스케일 일관 | font-size 값 카운트 | 7+ 고유값 시 CONCERN |
| CON-5 | 간격 스케일 일관 | margin/padding 값 카운트 | 토큰 외 값 5+ 시 CONCERN |
| CON-6 | 아이콘 라이브러리 일관 | 라이브러리 import 검사 | 2+ 라이브러리 시 CONCERN |
| CON-7 | 응답 메시지 어조 일관 (한국어 존댓말 등) | 사용자 메시지 grep | 혼용 시 CONCERN |

셀프 모드:

| # | 항목 | 검사 방법 | 라벨 기준 |
|---|---|---|---|
| CON-S1 | ADR 형식 일관 (상태/컨텍스트/결정/대안/결과 5섹션) | grep 헤딩 | 누락 시 CONCERN |
| CON-S2 | commands/*.md 헤딩 구조 일관 (`# /project:` + 사용법 + 실행) | 헤딩 패턴 | 불일치 시 CONCERN |
| CON-S3 | claude.gstack 미러 ↔ 원본 동기화 | diff | 불일치 시 BLOCK |

**결과 양식 (마크다운 표 + 라벨)**:

```markdown
## Design Review 결과: [scope] [target]

### 결론
✅ APPROVED | 🔄 NEEDS REVISION (BLOCK N건) | ⚠️ ADVISORY (CONCERN N건)

### A. 정보 구조 (8/8 통과)
| # | 항목 | 라벨 | 발견 |
|---|---|---|---|
| IA-1 | 요소 계층 | PASS | — |
| IA-6 | 로딩/에러 상태 | BLOCK | `pages/Navigation.tsx:42` 에러 분기 누락 |

### B. 접근성 (3건 CONCERN, 1건 BLOCK)
...

### C. 일관성 (2건 CONCERN)
...

### 원자적 수정 요청
1. **[BLOCK-IA-6]** `pages/Navigation.tsx:42` — 에러 상태 분기 누락
   → Developer 호출 1회 (수정만)
2. **[BLOCK-A11Y-1]** `pages/Navigation.tsx:88` — `<img>` alt 누락
   → Developer 호출 1회 (수정만)
```

---

### 결정 5 — "원자적 수정 요청" 메커니즘: **이슈 1건 = Developer 호출 1회 (직렬)**

**채택**: 발견된 BLOCK 이슈 N건을 Developer에 **순차로 N번** 위임. CONCERN은 일괄
보고만 하고 자동 위임하지 않는다 (사용자가 결정).

**왜 원자적 (1건씩)인가?**

| 옵션 | 장점 | 단점 |
|---|---|---|
| (a) 일괄 (모든 BLOCK 한 번에) | 호출 횟수 적음 | Developer가 여러 이슈를 동시에 만지면 컨텍스트 충돌, 한 수정이 다른 검사에 영향 → 재검사 신뢰성 ↓ |
| **(b) 원자적 (1건씩 직렬)** | 한 번에 한 수정 → 변경 범위 명확, 재검사 용이, 회귀 시 어느 수정이 원인인지 명확 | 호출 횟수 많음 |
| (c) 카테고리별 묶음 (IA 한 번, A11Y 한 번) | 절충 | 카테고리 내 이슈 간 영향이 카테고리 간보다 크다고 보장 못 함 |

→ **(b) 채택**. F007 description의 "원자적 수정 루프" 표현과도 일치.

**루프 구조**:

```
1. /project:design-review --scope=X --target=Y
2. 결과: BLOCK [I1, I2, I3], CONCERN [C1, C2]
3. for each block in [I1, I2, I3]:
     a. Developer 위임: "수정 대상 1건만: [block 상세]"
     b. Developer가 수정 + 단위 테스트
     c. /project:design-review --rerun (해당 항목만 재검사)
     d. PASS면 다음 block, 실패면 동일 block 재요청 (최대 3회)
4. 모든 BLOCK 처리 후: CONCERN을 사용자에게 일괄 보고
5. 사용자가 CONCERN 처리 여부 결정
```

**재검사 효율**: 전체 design-review를 매번 다시 돌리지 않고, `--rerun=BLOCK-IA-6`
처럼 특정 항목만 재실행. 구현은 체크리스트 항목별 검사 함수를 모듈화하여 가능
(Developer 단계에서 결정).

**에스컬레이션**: 같은 BLOCK이 3회 재요청 후에도 PASS 안 되면 Reviewer 에이전트의
에스컬레이션 패턴(reviewer.md L95)과 동일하게 `[ESCALATION]` 태그를 progress에 기록
+ Planner 에이전트에 Feature 분해 재검토 요청.

---

### 결정 6 — GPT Image API 미사용 명시 + 향후 확장 포인트

**현 phase (F007) 의 명시적 비범위**:

- ❌ GPT Image API / Vision API 호출
- ❌ 스크린샷 생성 (Playwright/Puppeteer 도입은 F008 별도 Feature)
- ❌ 이미지 파일 OCR/diff
- ❌ Pillow/cv2 등 이미지 라이브러리

→ 이번 phase는 **텍스트 기반(코드/마크다운/JSON 정적 분석)만**. 외부 의존성 0 원칙
유지.

**향후 확장 포인트**:

1. **F009 (가칭) — 시각 design-review 강화 (단계 2)**:
   - F008 (QA 브라우저 자동화)이 도입한 Playwright 스크린샷을 design-review가 입력으로 받는다
   - GPT Image API 또는 다른 비전 모델로 색 대비, 시각적 무게 자동 측정
   - 그때 별도 에이전트 `.claude/agents/design-reviewer.md` 신설을 재검토
2. **컴포넌트 단위 design-review**:
   - 현재는 파일 단위. 컴포넌트 단위(예: `Button` 모든 사용처) 검사로 확장
3. **디자인 토큰 사전(dictionary) 자동 추론**:
   - 현재는 토큰 외 값 카운트만. 사용 빈도가 높은 값을 자동 토큰 후보로 제안
4. **acceptance_criteria 직접 매핑**:
   - feature_list.json의 acceptance에 "정보 구조" 키워드 있을 시 자동 호출
5. **다른 호스트(F006 codex/openclaw) 지원**:
   - host_adapters를 통해 도구명 토큰 치환 — design-review SKILL.md.template로
     마이그레이션 (F006 후속과 함께)

---

## 대안 검토

| 대안 | 장점 | 단점 | 제외 이유 |
|---|---|---|---|
| Reviewer 에이전트에 디자인 체크리스트 추가 | 새 산출물 0 | 기존 정의 변경 → 무회귀 위배. Reviewer 부하 폭증, 단일 책임 위반 | 명시적 제약 위배 |
| design-reviewer 에이전트 신설 (위 결정 3 옵션 ii) | 패턴 일관 | 메타-하네스에 새 페르소나 부재, 호출자 인지 부하 ↑ | 결정 3 참조 |
| 스킬 없이 커맨드만 | 단순 | 체크리스트 60+ 항목이 커맨드 본문에 들어가면 비대해짐 | 가독성 저하 |
| 셀프 모드만 (B) | 자체 즉시 가치 | "접근성" AC 충족 어색, 배포 시 가치 ↓ | F007 의도 미반영 |
| 다운스트림 모드만 (A) | F007 의도 정합 | 메타-하네스 자체 검증 불가 | 검증 시나리오 부재 |
| Playwright + GPT Image API 도입 (시각 분석) | 진짜 디자인 감사 | 외부 의존성 폭증, F007 estimated 2 세션과 안 맞음 | 명시적 제약 위배 — F009로 분리 |
| MUST/SHOULD/CONSIDER 라벨 재사용 (Reviewer와 동일) | 사용자 학습 비용 ↓ | Reviewer와 시각적 구분 불가, 결과 통합 시 혼동 | 영역 구분 우선 |

---

## 결과

### 긍정적 영향

- **F007 모든 AC 충족**: AC1(커맨드 파일), AC2(체크리스트), AC3(원자적 수정 요청),
  AC4(GPT Image 미사용)
- **무회귀**: Reviewer 에이전트 정의 무수정, 기존 18개 커맨드/3개 스킬 무수정
- **명확한 역할 경계**: Reviewer(코드/보안/성능) ↔ design-review(IA/A11Y/일관성)
- **메타-하네스 자체 검증 가능**: 셀프 모드로 본 ADR 작성 후 즉시 정합성 검증
- **확장 경로 명시**: F009 시각 분석, F008 Playwright 연동 포인트 미리 식별
- **F003 ship.md 호환**: ship의 `design-review` 카테고리 언급이 실제 호출로 연결됨

### 부정적 영향 / 트레이드오프

- 산출물 2개 신규 (`commands/design-review.md`, `skills/design-review/SKILL.md`)
- 체크리스트 60+ 항목이 SKILL.md 한 파일에 들어가 길어짐 (~400줄 예상)
- 듀얼 모드(C)로 인한 체크리스트 두 벌 — 셀프 모드는 다운스트림 모드의 **부분
  대체** (모든 항목 적용 X) 이므로 사용자가 모드 차이를 인지해야 함
- 원자적 수정 루프가 BLOCK N건 시 N회 Developer 호출 → 토큰 사용량 ↑ (트레이드오프
  의도적 — 신뢰성 우선)
- 셀프 모드 IA-S 항목들은 일종의 "린터" 역할 — 본격 린터로 발전하면 별도 도구로
  분리 검토 필요

### 후속 조치

- [ ] (F007 구현) Developer 에이전트가 본 ADR을 기반으로 commands + skills 작성
- [ ] (F007 QA) 자체 정합성 검증 — `/project:design-review --scope=self` 1회 dry run
- [ ] (F008 와 결합) Playwright 도입 시 design-review가 스크린샷을 입력으로 받도록 인터페이스 확장 검토
- [ ] (F009 후속) 시각 분석 도입 시 design-reviewer 에이전트 신설 재검토
- [ ] (F006 후속) `.template` 마이그레이션 시 design-review 스킬도 함께 변환

---

## 구현 가이드 (Developer 인계용)

### 변경/신규 파일 목록

**신규 생성**:

```
.claude/commands/design-review.md                    # /project:design-review 슬래시 커맨드
.claude/skills/design-review/SKILL.md                # 체크리스트 + 결과 양식 + 원자적 루프 가이드
docs/design/F007-design-review-checklist.md          # (선택) 체크리스트 raw 정의 (SKILL.md가 참조)
```

**수정**:

```
CLAUDE.md                                            # "빠른 시작" 섹션에 /project:design-review 추가
                                                     # "에이전트 역할 분담" 표 아래 design-review 도구 행 추가
                                                     # "Architect 호출 기준" 같은 형식의 "design-review 호출 기준" 박스 추가
                                                     # 92-93줄 openai/ 설명 표현 보정 (Nit 1, 부록 §A)
.claude/skills/planning/SKILL.md                     # 헤더 주석 통일 (Nit 2, 부록 §B)
.claude/skills/testing/SKILL.md                      # 헤더 주석 통일 (Nit 2, 부록 §B)
.claude/bin/host_adapters/base.py                    # stub_info 추상 인터페이스 선언 (Nit 3, 부록 §C)
src/harness_template/openai/harness/.codex/skills/planning/SKILL.md   # 헤더 주석 통일
src/harness_template/openai/harness/.codex/skills/testing/SKILL.md    # 헤더 주석 통일
feature_list.json                                    # F007 status: in-progress → review (Developer 작업 끝)
.claude/state/learnings.jsonl                        # 새 학습 append (architecture 1건 + pattern 1건)
```

**의도적 미수정 (제약 준수)**:

```
.claude/agents/reviewer.md                           # 손대지 않는다 (제약: 기존 정의 보존)
.claude/agents/*.md                                  # 다른 에이전트도 손대지 않는다
.claude/settings.json                                # 손대지 않는다 (Claude Code 스키마 격리)
```

**미러링 (CLAUDE.md 동기화 정책)**:

`.claude/`, `CLAUDE.md`, `docs/adr/` 의 모든 변경은 다음 위치에 미러:

```
src/harness_template/claude.gstack/harness/CLAUDE.md
src/harness_template/claude.gstack/harness/docs/adr/ADR-002-design-review.md
src/harness_template/claude.gstack/harness/.claude/commands/design-review.md
src/harness_template/claude.gstack/harness/.claude/skills/design-review/SKILL.md
src/harness_template/claude.gstack/harness/.claude/skills/planning/SKILL.md  (Nit 2)
src/harness_template/claude.gstack/harness/.claude/skills/testing/SKILL.md   (Nit 2)
src/harness_template/claude.gstack/harness/.claude/bin/host_adapters/base.py (Nit 3)
```

`claude/` (baseline)은 동결 — 손대지 않는다.
`openai/` 의 SKILL.md는 정적 산출물 — `.codex/skills/{planning,testing}/SKILL.md` 의
헤더 주석만 통일 (Nit 2 동기화 미러).

### 단계별 작업 순서

**Step 1 — 체크리스트 raw 정의 작성** (`docs/design/F007-design-review-checklist.md`)
- 본 ADR 결정 4의 3 카테고리 × 다운스트림/셀프 표를 그대로 옮겨 정형화
- 각 항목별 grep 패턴/정규식/검사 의사코드 명시
- SKILL.md가 이 문서를 참조 (단일 소스)
- 인수 기준 충족: **AC2 (체크리스트)**

**Step 2 — `commands/design-review.md` 작성**
- 다른 commands/*.md 와 동일 구조: `# /project:design-review` + 사용법 + 실행 + 출력 예시
- `--scope`, `--target`, `--rerun` 플래그 명세
- 본문에서 SKILL.md 참조 + 호출 흐름(스킬 → 검사 → 발견 → Developer 위임 루프) 설명
- `host` 커맨드와 마찬가지로 `python3` 헬퍼를 호출하는 구조 권장 (단, 헬퍼 신설은
  필수 아님 — 본 phase는 텍스트 검사이므로 grep + python3 inline 으로 충분)
- 인수 기준 충족: **AC1 (커맨드 파일)**

**Step 3 — `skills/design-review/SKILL.md` 작성**
- frontmatter: `name: design-review`, `description`, `host: claude-code`
- 본문 구성:
  1. 호출 진입점 (커맨드 호출 표)
  2. 스코프 분기 (downstream / self)
  3. 3 카테고리 체크리스트 (raw 정의 참조 + 요약)
  4. 결과 양식 (마크다운 표 + 라벨 PASS/CONCERN/BLOCK)
  5. 원자적 수정 루프 (의사코드)
  6. Reviewer 에이전트와의 역할 경계 (결정 2 표 그대로 인용)
- 인수 기준 충족: **AC2 (체크리스트), AC3 (원자적 수정 요청)**

**Step 4 — CLAUDE.md 업데이트**
- "빠른 시작" 섹션에 신규 블록 추가:
  ```
  ### 디자인 감사 (Phase 4 — F007)
  /project:design-review                       # 다운스트림 UI/문서 감사
  /project:design-review --scope=self          # 하네스 자체 정합성 감사
  ```
- "에이전트 역할 분담" 표 바로 아래에 박스:
  ```
  > **Reviewer vs design-review 분리**:
  > Reviewer는 코드 품질·보안·성능을, design-review는 정보 구조·접근성·일관성을 담당한다.
  > 두 도구가 동시 호출되면 Reviewer를 먼저, design-review를 나중에 실행한다.
  ```
- "Architect 호출 기준"과 같은 형식의 "design-review 호출 기준" 추가:
  ```
  ## design-review 호출 기준
  - UI 컴포넌트/페이지 추가·수정
  - 디자인 시스템 토큰·컴포넌트 변경
  - 정보 구조 재배치
  - 셀프 모드: ADR 작성 후 자체 정합성 점검 시
  ```
- 인수 기준 충족: **AC1 노출 보강**

**Step 5 — 자체 dry run (셀프 정합성 검증)**
- Developer가 작성을 마친 직후 `/project:design-review --scope=self` 를 시연
- IA-S1~S4, CON-S1~S3 항목 검사 → 본 ADR 자체가 결과 양식대로 출력되는지 확인
- 메타-하네스이므로 **자체 검증이 곧 다운스트림 시뮬레이션**의 일부 역할

**Step 6 — Nit 3건 동시 처리** (부록 §A, §B, §C 참조)
- §A: CLAUDE.md 92-93줄 표현 보정
- §B: openai/ planning·testing SKILL.md 헤더 주석 통일
- §C: base.py에 `stub_info` 추상 인터페이스 선언
- 각 변경은 `claude.gstack/harness/` 미러까지 동기화

**Step 7 — 미러링 동기화**
- 위 §변경 목록의 미러링 경로에 `cp` 또는 `rsync`로 복제
- `diff -r` 로 동기화 누락 없는지 확인

**Step 8 — 핸드오프**
- `feature_list.json` F007: `status: "in-progress" → "review"`
- `/project:context-save "F007 design-review 단계 1 — 커맨드+스킬 작성 완료"` 체크포인트
- `/project:learn add` 로 다음 학습 후보 기록:
  - **architecture**: "design-review는 Reviewer를 보완하는 별도 영역(IA/A11Y/일관성)
    검사 — 에이전트가 아니라 커맨드+스킬로 노출 (메타-하네스 페르소나 부재 회피)"
  - **pattern**: "원자적 수정 루프 — BLOCK N건 = Developer N회 호출 (직렬, 한 번에
    한 수정으로 회귀 원인 명확화)"
  - **pitfall**: "design-review 셀프 모드 vs 다운스트림 모드 — 체크리스트 항목이
    부분 대체이므로 모드 명시 없이 호출 시 혼동 가능"

### 인수 기준 매핑

| AC | 충족 단계 | 비고 |
|---|---|---|
| **AC1** /project:design-review 커맨드 파일 | Step 2 + Step 4 | commands/design-review.md 신규 + CLAUDE.md 노출 |
| **AC2** 읽기 전용 설계 감사 체크리스트 (정보 구조, 접근성, 일관성) | Step 1 + Step 3 | raw 정의 + SKILL.md 본문. **읽기 전용** = design-review 자체는 코드 수정 안 함 (수정은 Developer 위임) |
| **AC3** 이슈 발견 시 Developer에 원자적 수정 요청 | Step 3 | SKILL.md "원자적 수정 루프" 섹션 + 결정 5의 의사코드 |
| **AC4** GPT Image API는 아직 미사용 (다음 phase) | 결정 6 | ADR에 명시적 비범위 선언 + 확장 포인트로 F009 분리 |

### 테스트 방법

메타-하네스 특성상 자체 UI가 없으므로 다음 3 방식으로 검증:

**방식 1 — 셀프 모드 dry run (즉시 가능)**

```
/project:design-review --scope=self
```

기대 결과:
- 결과 양식대로 마크다운 출력
- IA-S1~S4 항목 모두 검사 (CLAUDE.md 트리, commands 노출, ADR 경로, feature id)
- CON-S1~S3 항목 모두 검사 (ADR 형식, commands 헤딩, gstack 미러 동기화)
- 본 ADR 작성 직후라면 IA-S3 (ADR 참조 경로)에서 본 ADR이 PASS 되어야 함

**방식 2 — 다운스트림 시뮬레이션 (가짜 프로젝트)**

```
mkdir -p /tmp/design-review-test/src/components
cat > /tmp/design-review-test/src/components/Button.tsx <<'EOF'
export const Button = () => (
  <div onClick={() => alert('hi')}>클릭</div>  {/* A11Y-8 BLOCK 트리거 */}
);
EOF

cd /tmp/design-review-test
# 하네스 환경에서 호출 — 실제로는 사용자 프로젝트에 설치된 하네스가 실행
/project:design-review --scope=downstream --target=src/components/Button.tsx
```

기대 결과:
- A11Y-8 (의미적 HTML — div onClick) BLOCK 발견
- A11Y-2 (인터랙티브 요소 라벨) PASS or CONCERN (텍스트는 있으므로)
- IA, CON 카테고리는 단일 컴포넌트라 대부분 N/A 또는 PASS

**방식 3 — 원자적 수정 루프 검증 (Developer 인계 흐름)**

```
# Step 1: design-review 호출 → BLOCK 1건 발견
# Step 2: Developer 에이전트에 1건만 인계 ("Button.tsx의 div onClick → button 변경")
# Step 3: Developer 수정 + 단위 테스트
# Step 4: /project:design-review --rerun=BLOCK-A11Y-8
# Step 5: PASS 확인 → 다음 BLOCK 없으면 종료, CONCERN 일괄 보고
```

**모든 단계가 exit 0 으로 종료되는지** 확인 (Brain hook-failure-tolerance 원칙
일관).

### 피해야 할 패턴

- ❌ 새 에이전트 `.claude/agents/design-reviewer.md` 신설 (결정 3 위배)
- ❌ Reviewer 에이전트 정의 변경 (제약 위배)
- ❌ Playwright/Pillow/cv2/GPT Image API 도입 (결정 6 비범위)
- ❌ 외부 Python 패키지 추가 (stdlib만)
- ❌ design-review가 코드 직접 수정 (읽기 전용 — 수정은 Developer 위임)
- ❌ BLOCK 일괄 위임 (결정 5 — 원자적 1건씩)
- ❌ 셀프 모드에서 A11Y 카테고리 보고 (UI 없음 — N/A 처리)
- ❌ 체크리스트 raw 정의를 SKILL.md에 직접 인라인 (Step 1의 별도 문서로 단일 소스)
- ❌ host.json/settings.json 수정 (F006 격리 정책 위배)

---

## 부록 A — Nit 1: CLAUDE.md 92-93줄 openai/ 설명 표현 보정

### 현재 표현 (CLAUDE.md L92-93)

```
**`openai/` 변형**: F006 멀티 호스트 작업의 어댑터/SKILL 렌더링 대상.
직접 손대지 말고 host_adapters/codex.py + render-skills 로직으로 생성.
```

### 문제

`codex.py` 는 stub 어댑터이고 `render_skill_md()` 가 None 반환한다. 즉 실제로는
`render-skills` 로직이 openai/ 변형을 **생성하지 않는다**. 현재 openai/ 의 3개
SKILL.md 는 F006 세션 2에서 **수동으로 작성된 정적 산출물**이다.

### 권장 표현 (1~2줄)

```
**`openai/` 변형**: F006 세션 2에서 수동 생성된 정적 산출물 (Codex 호스트용 .codex/ 구조).
직접 손대지 말 것 — codex 어댑터가 실구현되는 후속 phase에서 render-skills로 자동 재생성 가능해진다.
```

**근거**: codex.py 의 docstring (L11-16) 이 이미 동일한 표현을 사용하고 있으므로
표현 일관성도 달성된다.

---

## 부록 B — Nit 2: openai/ planning·testing SKILL.md 헤더 주석 통일

### 현재 상태

| 파일 | 헤더 주석 |
|---|---|
| `openai/.../coding/SKILL.md` | ✅ 3줄 자동 생성 주석 (L1-3) |
| `openai/.../planning/SKILL.md` | ❌ 주석 없음, 바로 본문 시작 |
| `openai/.../testing/SKILL.md` | ❌ 주석 없음, 바로 본문 시작 |

### coding/SKILL.md 의 현재 주석 (참고)

```html
<!-- 자동 생성 파일 — 직접 수정 금지 -->
<!-- 생성: F006 세션 2 (codex 어댑터 최소 실구현 단계) -->
<!-- codex 어댑터가 실구현되면 render-skills --output-root 로 재생성 가능 -->
```

### 권장 통일된 헤더 주석 템플릿

```html
<!-- 자동 생성 파일 — 직접 수정 금지 -->
<!-- 원본: src/harness_template/claude.gstack/harness/.claude/skills/<NAME>/SKILL.md -->
<!-- 생성 컨텍스트: F006 세션 2 (codex 호스트용 정적 산출물) -->
<!-- codex 어댑터가 실구현되는 후속 phase에서 render-skills 로 자동 재생성 가능 -->
```

**개선점**:
- 원본 경로 명시 (역추적 가능)
- 정적 산출물임을 명시 ("최소 실구현 단계" → "정적 산출물" — Nit 1과 표현 일치)
- "재생성 가능 시점" 명시 (= 사용자가 언제 자동화될지 안다)

**적용 대상**:
- `.claude/skills/{planning,testing}/SKILL.md` (단, 이건 claude-code용이므로
  실제로는 openai/ 만 적용 — claude-code SKILL.md 는 정적 산출물이 아님)

→ **재정리**: 헤더 주석은 **openai/ 변형 3개만** 통일 적용. claude-code 측
SKILL.md (`.claude/skills/`) 는 손대지 않는다.

**최종 적용 경로**:
- `src/harness_template/openai/harness/.codex/skills/coding/SKILL.md` — 기존 주석 위 템플릿으로 교체
- `src/harness_template/openai/harness/.codex/skills/planning/SKILL.md` — 본문 첫 줄 위에 신규 추가
- `src/harness_template/openai/harness/.codex/skills/testing/SKILL.md` — 본문 첫 줄 위에 신규 추가

각 파일에서 `<NAME>` 토큰을 해당 스킬명(coding/planning/testing)으로 치환.

---

## 부록 C — Nit 3: base.py 에 `stub_info` 추상 인터페이스 선언

### 현재 상태

- `host.py` 가 4곳에서 `getattr(adapter, "stub_info", "")` 방어 코드로 호출
- `openclaw.py`, `codex.py` 의 stub 어댑터에는 `stub_info` 속성이 정의되어 있음
- **`base.py` 의 `HostAdapter` 추상 베이스에는 선언이 없음** → 향후 새 stub 어댑터
  추가 시 누락 위험. 누락되어도 `getattr` fallback이 빈 문자열을 반환하므로
  **사일런트 실패** (사용자에게 안내 메시지 안 나타남).

### 권장 구현

`base.py` 의 `HostAdapter` 클래스에 다음 **선택적 메서드 (concrete with default)**
추가:

```python
@property
def stub_info(self) -> str:
    """
    stub 어댑터 안내 메시지를 반환한다.

    실구현 어댑터는 이 메서드를 재정의할 필요가 없다 (기본값 빈 문자열 반환).
    stub 어댑터 (is_stub=True) 는 반드시 재정의하여 다음을 안내해야 한다:
      - stub 상태임을 명시
      - 실구현이 어느 phase에서 가능한지
      - claude-code 로 fallback 하는 방법

    Returns:
        str: 안내 메시지. 실구현 어댑터는 빈 문자열 ("").
    """
    return ""
```

### 권장 강도: 추상(@abstractmethod) 아님 — 기본값 있는 concrete 메서드

**비교**:

| 방식 | 장점 | 단점 |
|---|---|---|
| `@abstractmethod` (강제 구현) | 누락 시 인스턴스 생성 단계에서 실패 → 즉시 발견 | 실구현 어댑터(claude_code.py) 도 빈 문자열 반환을 명시적으로 작성해야 함 (보일러플레이트) |
| **concrete with default `""`** | 실구현 어댑터는 무수정, stub 어댑터만 재정의. host.py의 getattr 방어 코드를 제거할 수 있음 (속성이 항상 존재 보장) | 누락이 사일런트 (단, is_stub=True인 어댑터에서 빈 문자열이면 코드 리뷰에서 드러남) |
| `@abstractmethod` + 기본 구현 | 양쪽 장점 | Python에서는 추상이면 기본 구현 우선순위가 모호함 |

→ **concrete with default 채택**. is_stub=True 어댑터 코드 리뷰 시 stub_info
재정의를 체크리스트에 추가 (design-review CON 카테고리에서 자체 점검 가능).

### 부수 정리

- `host.py` 의 4곳 `getattr(adapter, "stub_info", "")` 호출은 그대로 유지해도 무방
  (방어 코드 + 속성 정의 양쪽 = 더 안전). 다만 코드 통일성을 위해 직접 `adapter.stub_info`
  접근으로 변경하는 것을 권장 (Developer가 결정).

### 적용 미러링

```
.claude/bin/host_adapters/base.py
src/harness_template/claude.gstack/harness/.claude/bin/host_adapters/base.py
```

---

*작성: architect 에이전트 | 날짜: 2026-04-30 | 상태: Accepted*
