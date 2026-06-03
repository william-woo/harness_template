# F007 Design Review 체크리스트 (raw 정의)

> 단일 소스: `.claude/skills/design-review/SKILL.md` 가 이 문서를 참조한다.
> Feature: F007 — Phase 4 Design Review 강화 (단계 1)
> 근거: ADR-002-design-review.md 결정 4

> **SSoT 유지보수 주의**: 이 문서와 SKILL.md 는 단일 소스 원칙. 한 쪽 변경 시 반드시
> 다른 쪽 동기화 — 루프 횟수(3회) 변경 시 SKILL.md 의사코드와 `commands/design-review.md`
> 산문을 동시 수정할 것. diff 누락은 design-review --scope=self CON-S2 에서 자동 탐지.

---

## 개요

이 체크리스트는 `/project:design-review` 커맨드가 실행하는 검사 항목의 **공식 정의**다.
3개 카테고리 × (다운스트림 / 셀프) 두 모드로 구성된다.

**라벨 체계**:

| 라벨 | 의미 | Reviewer 대응 |
|---|---|---|
| `BLOCK` | 머지 차단 — Developer 즉시 수정 필요 | MUST |
| `CONCERN` | 권장 수정 — 우선순위 따라 처리 | SHOULD |
| `PASS` | 명시적 통과 (체크리스트 가시성 확보) | — |
| `N/A` | 해당 없음 (self 모드의 A11Y 등) | — |

---

## A. 정보 구조 (Information Architecture)

### A-1. 다운스트림 모드 (UI 코드·페이지 대상)

| # | 항목 | 검사 방법 (의사코드 / grep 패턴) | BLOCK 조건 | CONCERN 조건 |
|---|---|---|---|---|
| IA-1 | 요소 계층(visual hierarchy) 명시 | `grep -n "<h[1-6]"` 추출 → 레벨 순서 분석 | h1 누락 또는 h2→h4 점프 | h1이 2개 이상 |
| IA-2 | 1차 액션(CTA)이 페이지당 1개 명확 | `grep -n "primary\|btn-main\|cta"` 카운트 | CTA 부재 | 동등 비중 CTA 3개 이상 |
| IA-3 | 정보 그룹핑(시각적 청크) 적절성 | 최상위 컨테이너 직접 자식 수 카운트 | — | 단일 컨테이너 자식 9개 이상 |
| IA-4 | 명명 일관성 (라벨·메뉴 항목) | 동의어 목록 비교 (`grep -i "삭제\|제거\|지우기"`) | — | 동일 의미에 다른 라벨 혼용 |
| IA-5 | 빈 상태(empty state) 처리 명시 | `grep -n "empty\|비어\|데이터 없"` 분기 검사 | — | 목록/표에 empty state 분기 누락 |
| IA-6 | 로딩·에러 상태 처리 | `grep -n "loading\|isLoading\|error\|catch"` 분기 검사 | 비동기 데이터 로드에 에러 처리 누락 | 로딩 표시 없음 |
| IA-7 | 진행 상황(progress) 가시화 | 스텝 수 카운트 + `grep -n "step\|progress\|단계"` | — | 3단계 이상 플로우에 표시기 없음 |
| IA-8 | URL·라우트 명명의 의도 일치 | 라우트 정의 grep + 페이지 목적 비교 | — | 라우트명과 페이지 목적 불일치 |

### A-2. 셀프 모드 (하네스 자신 대상)

| # | 항목 | 검사 방법 | BLOCK 조건 | CONCERN 조건 |
|---|---|---|---|---|
| IA-S1 | CLAUDE.md 디렉토리 트리 ↔ 실제 파일 일치 | `find . -type f` 결과와 CLAUDE.md 코드블록 비교 | 트리에 기재되었으나 존재하지 않는 경로 있음 | — |
| IA-S2 | `.claude/commands/*.md` 전체가 CLAUDE.md "빠른 시작"에 노출 | `ls .claude/commands/*.md` 파일명 추출 → CLAUDE.md grep | 커맨드 파일은 존재하나 CLAUDE.md에 없음 | — |
| IA-S3 | ADR에서 참조한 파일 경로 유효성 | ADR 본문에서 경로 패턴 추출 → `os.path.exists()` | 참조 경로가 실제로 없음 | — |
| IA-S4 | feature_list.json id ↔ ADR/checkpoints id 일관 | `grep -r "F0[0-9][0-9]"` 결과 교차 비교 | 다른 문서에서 참조되지만 feature_list에 없는 ID | — |

---

## B. 접근성 (Accessibility)

### B-1. 다운스트림 모드

WCAG 2.1 AA 일부 차용 + 텍스트 정적 분석 한도 내 핵심 항목.

| # | 항목 | 검사 방법 (grep 패턴) | BLOCK 조건 | CONCERN 조건 |
|---|---|---|---|---|
| A11Y-1 | 모든 `<img>`에 `alt` 속성 존재 | `grep -n "<img"` → `alt=` 없는 행 필터 | `alt` 누락 img 존재 | — |
| A11Y-2 | 인터랙티브 요소에 aria-label 또는 visible label | `grep -n "<button\|<a "` → label/aria-label 없는 행 | 라벨 없는 button·a 태그 존재 | — |
| A11Y-3 | tabindex 사용 패턴 | `grep -n "tabindex"` → 양수값 필터 | — | `tabindex` 값이 1 이상 (anti-pattern) |
| A11Y-4 | 폼 input ↔ label 연결 | `grep -n "<input"` + `htmlFor\|for=` 매칭 | input에 연결된 label 없음 | — |
| A11Y-5 | 색만으로 의미 전달 금지 | `grep -n "color.*error\|error.*color"` → 아이콘·텍스트 병용 여부 | — | 에러·성공을 색만으로 구별하는 패턴 |
| A11Y-6 | 터치 타깃 크기 ≥ 44×44px | `grep -n "width.*px\|height.*px"` → 44px 미만값 탐지 | — | 44px 미만 인터랙티브 요소 스타일 |
| A11Y-7 | aria-live 영역 (동적 변경) | `grep -n "toast\|alert\|notification\|snackbar"` → `aria-live` 없는 패턴 | — | 동적 알림에 aria-live 미적용 |
| A11Y-8 | 의미적 HTML (`button` vs `div onClick`) | `grep -n "div.*onClick\|span.*onClick"` | `div`/`span` onClick 인터랙션 존재 | — |

### B-2. 셀프 모드

셀프 모드에서는 A11Y 카테고리 전체를 **N/A**로 표시한다.
(하네스는 UI가 없으므로 접근성 항목 불적용 — ADR-002 결정 4)

---

## C. 일관성 (Consistency)

### C-1. 다운스트림 모드

| # | 항목 | 검사 방법 | BLOCK 조건 | CONCERN 조건 |
|---|---|---|---|---|
| CON-1 | 디자인 토큰 사용 (color·spacing·font) | `grep -rn "#[0-9a-fA-F]\{3,6\}\|[0-9]\+px"` → 토큰 변수가 아닌 하드코딩값 탐지 | — | 하드코딩된 색·간격 5개 이상 |
| CON-2 | 컴포넌트 재사용 (DRY) | 동형 마크업 블록 중복 탐지 (`diff`·유사 패턴 비교) | — | 3개 이상 동일 마크업 중복 |
| CON-3 | 명명 규칙 (kebab·camel·Pascal 일관) | 파일명 목록 추출 → 규칙 혼용 탐지 | — | 동일 디렉토리 내 두 가지 이상 규칙 혼용 |
| CON-4 | 타이포그래피 스케일 일관 | `grep -rn "font-size"` → 고유값 카운트 | — | 토큰 외 font-size 고유값 7개 이상 |
| CON-5 | 간격 스케일 일관 | `grep -rn "margin:\|padding:"` → 토큰 외 값 카운트 | — | 토큰 외 margin·padding 고유값 5개 이상 |
| CON-6 | 아이콘 라이브러리 일관 | `grep -rn "import.*icon\|from.*icons"` → 라이브러리 목록 | — | 2개 이상 아이콘 라이브러리 혼용 |
| CON-7 | 응답 메시지 어조 일관 (존댓말·평어 혼용) | `grep -rn "합니다\|해요\|해라\|하세요"` → 혼용 탐지 | — | 동일 파일 내 존댓말·평어 혼용 |

### C-2. 셀프 모드

| # | 항목 | 검사 방법 | BLOCK 조건 | CONCERN 조건 |
|---|---|---|---|---|
| CON-S1 | ADR 형식 일관 (상태·컨텍스트·결정·대안·결과 5섹션) | `grep -n "^## "` → 5개 섹션 헤딩 존재 여부 | — | 필수 섹션 누락 |
| CON-S2 | `commands/*.md` 헤딩 구조 일관 | `grep -n "^# /project:"` → 각 파일 첫 헤딩 패턴 확인 | — | `/project:` 패턴 없는 커맨드 파일 |
| CON-S3 | claude.gstack 미러 ↔ 원본 동기화 | `diff -r .claude/ src/harness_template/claude.gstack/harness/.claude/` (state/ 제외) | 원본과 미러 불일치 존재 | — |

---

## D. TOKEN (디자인 토큰 정합 — F011 신설)

`tokens.json` 부재 시 카테고리 전체 **N/A** (점검 안 함).
`tokens.json` 존재 시 아래 6 항목 추가 점검.

**라벨 체계**: BLOCK 없음. CONCERN / PASS / INFO 만 사용. 점진적 도입 정신 — 거짓 양성 위험 최소화.

| # | 항목 | 검사 방법 (의사코드 / grep 패턴) | 라벨 조건 |
|---|---|---|---|
| TOKEN-1 | `tokens.json` `colors` 외 hex 색상 직접 사용 | `grep -rn "#[0-9a-fA-F]\{3,6\}"` → `tokens.json` 의 hex 값과 대조, 미등록값 추출 | CONCERN (미등록 hex 존재) / PASS |
| TOKEN-2 | `tokens.json` `typography.font_body` 외 폰트 패밀리 직접 사용 | `grep -rn "font-family"` → `tokens.json` 폰트 목록 대조, 미등록 폰트 추출 | CONCERN (미등록 폰트 존재) / PASS |
| TOKEN-3 | `tokens.json` `radius` 외 임의 `border-radius` 값 | `grep -rn "border-radius"` → `tokens.json` radius 값 대조 | INFO (미등록 radius 존재) / PASS |
| TOKEN-4 | `tokens.json` `spacing` 외 임의 `padding`/`margin` 값 (8px 그리드 위반) | `grep -rn "padding:\|margin:"` → `tokens.json` spacing 값 대조 | INFO (8px 그리드 외 값 존재) / PASS |
| TOKEN-5 | `tokens.json` `anti_patterns` 에 명시된 패턴 등장 | `anti_patterns` 목록 추출 → grep 전수 탐색 | CONCERN (anti_pattern 발견) / PASS |
| TOKEN-6 | `tokens.json` 자체 유효성 (필수 필드 존재) | `colors`, `typography`, `radius`, `spacing` 필드 존재 여부 확인 | CONCERN (필수 필드 누락) / PASS |

**다운스트림·셀프 공통**: 두 모드 모두 `tokens.json` 존재 시 TOKEN 카테고리 추가 점검.
토큰 기반 점검은 선택된 brand 외 스타일 혼입을 감지하여 디자인 시스템 일관성을 보조한다.

---

## 결과 양식 템플릿

```markdown
## Design Review 결과: [scope] — [target 또는 "전체"]

**실행 시각**: YYYY-MM-DD HH:MM
**스코프**: downstream | self

### 결론
✅ APPROVED | 🔄 NEEDS REVISION (BLOCK N건) | ⚠️ ADVISORY (CONCERN N건)

### A. 정보 구조 (N/M 통과)

| # | 항목 | 라벨 | 발견 |
|---|---|---|---|
| IA-1 | 요소 계층 | PASS | — |
| IA-6 | 로딩·에러 상태 | BLOCK | `파일명:줄번호` 에러 분기 누락 |

### B. 접근성 (N/M 통과)  ← self 모드는 "N/A — 하네스 UI 없음"

| # | 항목 | 라벨 | 발견 |
|---|---|---|---|
| A11Y-1 | img alt | PASS | — |
| A11Y-8 | 의미적 HTML | BLOCK | `Button.tsx:12` div onClick |

### C. 일관성 (N/M 통과)

| # | 항목 | 라벨 | 발견 |
|---|---|---|---|
| CON-1 | 디자인 토큰 | CONCERN | 하드코딩 색상 3건 |
| CON-3 | 명명 규칙 | PASS | — |

### D. TOKEN (N/M 통과 — tokens.json 없으면 N/A)

| # | 항목 | 라벨 | 발견 |
|---|---|---|---|
| TOKEN-1 | hex 색상 직접 사용 | CONCERN | `App.css:14` `#ff0000` |
| TOKEN-6 | tokens.json 유효성 | PASS | 필수 필드 모두 존재 |

### 원자적 수정 요청

1. **[BLOCK-IA-6]** `파일명:줄번호` — 에러 상태 분기 누락
   → Developer 호출 1회 (수정만, 다른 이슈 건드리지 않음)
2. **[BLOCK-A11Y-8]** `Button.tsx:12` — `<div onClick>` → `<button>` 변경
   → Developer 호출 1회

### CONCERN 목록 (사용자 결정 사항)

- [CONCERN-CON-1] 하드코딩 색상 3건 — 디자인 토큰으로 교체 권장
```

---

## 검사 도구 의존성

이 체크리스트는 **텍스트 기반 정적 분석**만 사용한다. 모든 검사는 표준 유닉스 도구
(`grep`, `find`, `diff`)와 Python stdlib만으로 실행 가능하다.

**명시적 비범위 (F007)**:
- GPT Image API / Vision API
- Playwright / Puppeteer (스크린샷)
- Pillow / cv2 (이미지 분석)
- ESLint/axe-core 등 외부 도구 (선택적 보조는 가능하나 의존하지 않음)

확장 포인트는 ADR-002 결정 6 참조.
