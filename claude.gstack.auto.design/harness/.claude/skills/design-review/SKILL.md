---
name: design-review
description: |
  디자인 감사 스킬. 다운스트림 프로젝트의 UI/문서 또는 하네스 자체의 정합성을
  읽기 전용으로 검사한다. 정보 구조(IA), 접근성(A11Y), 일관성(CON) 3 카테고리.
  호스트: claude-code
---

# Design Review Skill

> 체크리스트 단일 소스: `docs/design/F007-design-review-checklist.md`
> 설계 근거: `docs/adr/ADR-002-design-review.md`
> 진입점: `/project:design-review`

> **SSoT 유지보수 주의**: 이 문서와 raw 정의 (`docs/design/F007-design-review-checklist.md`) 는
> 단일 소스 원칙. 한 쪽 변경 시 반드시 다른 쪽 동기화 — 루프 횟수(3회) 변경 시
> SKILL.md 의사코드와 `commands/design-review.md` 산문을 동시 수정할 것.
> diff 누락은 design-review --scope=self 에서 CON-S2 항목으로 자동 탐지된다.

---

## 호출 진입점

| 호출 | 설명 |
|---|---|
| `/project:design-review` | downstream 기본 (전체) |
| `/project:design-review --scope=downstream --target=<경로>` | 특정 파일/디렉토리 |
| `/project:design-review --scope=self` | 하네스 자체 정합성 |
| `/project:design-review --rerun=BLOCK-XX` | 특정 항목 재검사 |

---

## Reviewer 에이전트와의 역할 경계 (ADR-002 결정 2)

> **설계 원칙**: design-review와 Reviewer는 상호 보완 관계이지 대체 관계가 아니다.
> Reviewer가 먼저, design-review가 나중 (동작하는 코드의 디자인을 평가하는 것이 자연스럽다).

| 영역 | Reviewer | design-review |
|---|---|---|
| 코드 품질·SRP·DRY·docstring | ✅ 담당 | ❌ 위임 |
| 보안 (SQLi/XSS/시크릿) | ✅ 담당 | ❌ 위임 |
| 성능 (N+1, 알고리즘) | ✅ 담당 | ❌ 위임 |
| 린트·타입체크·테스트 통과 | ✅ 담당 | ❌ 위임 |
| **정보 구조 (IA)** — 요소 계층·명명·빈/로딩/에러 상태 | ❌ | ✅ **담당** |
| **접근성 (A11y)** — aria·키보드·터치 타깃·색 대비 | ❌ | ✅ **담당** (downstream만) |
| **일관성** — 디자인 토큰·컴포넌트 재사용·명명 규칙 | ❌ | ✅ **담당** |
| **셀프 정합성** — CLAUDE.md ↔ 커맨드 ↔ ADR | ❌ | ✅ **담당** (--scope=self) |

---

## 스코프 분기

### downstream 모드 (기본)

**대상**: 사용자 프로젝트의 UI 코드·페이지·문서  
**검사 범위**: A. 정보 구조 + B. 접근성 + C. 일관성 (3 카테고리 전부)  
**예시**: HMI 화면, React 컴포넌트, 마크다운 문서 IA

```
검사 우선순위:
1. --target 명시된 파일/디렉토리
2. 미명시 시: src/, pages/, components/, docs/ 순서
```

### self 모드 (`--scope=self`)

**대상**: 이 하네스 자신 (CLAUDE.md, .claude/, docs/adr/, feature_list.json)  
**검사 범위**: A. 정보 구조(IA-S 항목) + C. 일관성(CON-S 항목)  
**B. 접근성**: **N/A** — 하네스는 UI가 없으므로 전 항목 N/A 처리 후 보고하지 않음

---

## A. 정보 구조 체크리스트

### A-1. downstream 모드 (8개 항목)

| # | 항목 | 검사 의사코드 | BLOCK 기준 | CONCERN 기준 |
|---|---|---|---|---|
| IA-1 | 요소 계층 명시 | `grep -n "<h[1-6]"` → 레벨 순서 분석 | h1 누락 또는 h2→h4 점프 | h1 2개 이상 |
| IA-2 | 1차 CTA 명확성 | `grep -n "primary\|btn-main\|cta"` 카운트 | CTA 부재 | 동등 CTA 3개 이상 |
| IA-3 | 정보 그룹핑 적절성 | 컨테이너 직접 자식 수 카운트 | — | 단일 컨테이너 자식 9개 이상 |
| IA-4 | 명명 일관성 | 동의어·유사 라벨 grep | — | 동일 의미 다른 라벨 혼용 |
| IA-5 | 빈 상태 처리 | `grep -n "empty\|빈 상태"` 분기 검사 | — | 목록에 empty state 분기 누락 |
| IA-6 | 로딩·에러 상태 처리 | `grep -n "isLoading\|error\|catch"` | 비동기 에러 처리 누락 | 로딩 표시 없음 |
| IA-7 | 진행 상황 가시화 | 스텝 수 + `grep -n "step\|progress"` | — | 3단계 이상 플로우에 표시기 없음 |
| IA-8 | URL·라우트 명명 | 라우트 정의 grep + 목적 비교 | — | 라우트명과 페이지 목적 불일치 |

### A-2. self 모드 (4개 항목)

| # | 항목 | 검사 의사코드 | BLOCK 기준 | CONCERN 기준 |
|---|---|---|---|---|
| IA-S1 | CLAUDE.md 트리 ↔ 실제 파일 | `find . -type f` + CLAUDE.md 코드블록 비교 | 기재 경로 실제 없음 | — |
| IA-S2 | commands/*.md 전체 CLAUDE.md 노출 | `ls .claude/commands/*.md` + CLAUDE.md grep | 커맨드 파일 노출 누락 | — |
| IA-S3 | ADR 참조 경로 유효성 | ADR 내 경로 추출 + `os.path.exists()` | 참조 경로 실제 없음 | — |
| IA-S4 | feature_list.json id 일관 | `grep -r "F0[0-9][0-9]"` 교차 비교 | 참조되나 목록에 없는 ID | — |

---

## B. 접근성 체크리스트

### B-1. downstream 모드 (8개 항목)

| # | 항목 | 검사 의사코드 | BLOCK 기준 | CONCERN 기준 |
|---|---|---|---|---|
| A11Y-1 | img alt 존재 | `grep -n "<img"` → `alt=` 없는 행 | alt 누락 img 존재 | — |
| A11Y-2 | 인터랙티브 요소 라벨 | `grep -n "<button\|<a "` → 라벨 없는 행 | 라벨 없는 button·a 존재 | — |
| A11Y-3 | tabindex 사용 패턴 | `grep -n "tabindex"` → 양수값 필터 | — | tabindex 값 1 이상 |
| A11Y-4 | 폼 input ↔ label 연결 | `grep -n "<input"` + `htmlFor` 매칭 | input에 label 없음 | — |
| A11Y-5 | 색만으로 의미 전달 금지 | error·success 색 패턴 → 텍스트 병용 여부 | — | 색만으로 에러·성공 구별 |
| A11Y-6 | 터치 타깃 ≥ 44×44px | `grep -n "width.*px\|height.*px"` → 44px 미만 | — | 44px 미만 인터랙티브 스타일 |
| A11Y-7 | aria-live 영역 | toast·alert 패턴 → `aria-live` 없는 행 | — | 동적 알림에 aria-live 미적용 |
| A11Y-8 | 의미적 HTML | `grep -n "div.*onClick\|span.*onClick"` | div·span onClick 존재 | — |

### B-2. self 모드

**전체 N/A** — 하네스는 UI가 없으므로 접근성 항목을 검사하지 않는다.  
결과 출력 시 섹션에 `N/A — 하네스 UI 없음 (self 모드)`만 기재.

---

## C. 일관성 체크리스트

### C-1. downstream 모드 (7개 항목)

| # | 항목 | 검사 의사코드 | BLOCK 기준 | CONCERN 기준 |
|---|---|---|---|---|
| CON-1 | 디자인 토큰 사용 | `grep -rn "#[0-9a-fA-F]{3,6}\|[0-9]+px"` → 하드코딩값 | — | 하드코딩 색·간격 5개 이상 |
| CON-2 | 컴포넌트 재사용 (DRY) | 동형 마크업 블록 중복 탐지 | — | 동일 마크업 3개 이상 중복 |
| CON-3 | 명명 규칙 일관 | 파일명 목록 → 규칙 혼용 탐지 | — | 동일 디렉토리 2가지 이상 규칙 혼용 |
| CON-4 | 타이포그래피 스케일 | `grep -rn "font-size"` → 고유값 카운트 | — | 토큰 외 고유값 7개 이상 |
| CON-5 | 간격 스케일 | `grep -rn "margin:\|padding:"` → 토큰 외 값 | — | 토큰 외 고유값 5개 이상 |
| CON-6 | 아이콘 라이브러리 | `grep -rn "from.*icon"` → 라이브러리 목록 | — | 2개 이상 아이콘 라이브러리 혼용 |
| CON-7 | 응답 메시지 어조 | 존댓말·평어 혼용 grep | — | 동일 파일 내 어조 혼용 |

### C-2. self 모드 (3개 항목)

| # | 항목 | 검사 의사코드 | BLOCK 기준 | CONCERN 기준 |
|---|---|---|---|---|
| CON-S1 | ADR 형식 일관 | `grep -n "^## "` → 5개 섹션 헤딩 확인 | — | 필수 섹션 누락 |
| CON-S2 | commands 헤딩 구조 | `grep -n "^# /project:"` → 패턴 확인 | — | `/project:` 패턴 없는 커맨드 |
| CON-S3 | gstack 미러 동기화 | `diff -r .claude/ src/harness_template/claude.gstack/harness/.claude/` | 원본·미러 불일치 | — |

---

## 결과 양식

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

### B. 접근성 (N/M 통과)
← self 모드는 "N/A — 하네스 UI 없음"

### C. 일관성 (N/M 통과)
| # | 항목 | 라벨 | 발견 |
|---|---|---|---|
| CON-1 | 디자인 토큰 | CONCERN | 하드코딩 색상 3건 |

### 원자적 수정 요청
1. **[BLOCK-IA-6]** `파일명:줄번호` — 에러 분기 누락
   → Developer 호출 1회 (수정만, 다른 이슈 건드리지 않음)
2. **[BLOCK-A11Y-8]** `파일명:줄번호` — div onClick
   → Developer 호출 1회

### CONCERN 목록 (사용자 결정 사항)
- [CONCERN-CON-1] 하드코딩 색상 3건 — 디자인 토큰 권장
```

---

## 원자적 수정 루프 (ADR-002 결정 5)

**원칙**: BLOCK 1건 = Developer 호출 1회 (직렬). 절대 일괄 위임하지 않는다.
동일 BLOCK은 **최대 3회** 재요청 후에도 PASS 안 되면 ESCALATION.

```
의사코드:
  blocks = [B1, B2, B3, ...]
  concerns = [C1, C2, ...]

  for block in blocks:
    attempt = 0
    while attempt < 3:  # 최대 3회
      Developer 위임:
        "수정 대상 1건만: [block 상세]
         파일: [파일명:줄번호]
         다른 이슈는 건드리지 않음"
      Developer 수정 완료 후 재검사:
        /project:design-review --rerun=[block.id]
      if PASS:
        break
      else:
        attempt += 1

    if attempt == 3:
      [ESCALATION] 태그를 claude-progress.txt에 기록
      Planner 에이전트에 Feature 분해 재검토 요청

  모든 blocks 처리 후:
    CONCERN 목록 사용자에게 일괄 보고
```

**왜 원자적인가**: 여러 이슈를 한 번에 수정하면 어느 수정이 회귀를 일으켰는지
추적이 불가능하다. 1건씩 처리하면 각 수정의 영향 범위가 명확하다.

---

## 체크리스트 (실행 전 확인)

- [ ] `--scope` 플래그 확인 (기본: downstream)
- [ ] `--target` 경로 존재 확인
- [ ] Reviewer 리뷰가 먼저 완료되었는지 확인 (동시 필요 시)
- [ ] design-review 자체는 파일을 수정하지 않음 (읽기 전용)
- [ ] BLOCK 이슈는 원자적으로 1건씩 Developer 위임
- [ ] 셀프 모드에서 A11Y는 N/A 처리
