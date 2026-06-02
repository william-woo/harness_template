# /project:design-pick — 디자인 토큰 선택·적용

4 브랜드 디자인 시스템 (Apple / Claude / Spotify / Tesla) 중 프로젝트에 맞는 토큰을
선택하고 `.claude/design/tokens.json` 으로 저장한다.

**사용 가능 변형**: `claude.gstack.auto.design` 만 (ADR-006 결정 6).
**외부 의존성 없음**: Python stdlib only.
**옵셔널**: 호출하지 않으면 하네스 동작에 영향 없음 (F005/F009/F010 일관).

---

## 사용법

```
/project:design-pick                              # = compare (인자 없음 → 비교표)
/project:design-pick compare                      # 4 브랜드 비교표 (정적, LLM 없음)
/project:design-pick compare --format=json        # JSON 출력
/project:design-pick recommend                    # designer 에이전트 호출 안내
/project:design-pick apply apple                  # .claude/design/tokens.json 생성
/project:design-pick apply claude --force         # 기존 tokens.json 백업 후 덮어쓰기
/project:design-pick show                         # 현재 tokens.json 표시
/project:design-pick show --format=json           # JSON raw 출력
/project:design-pick self                         # 의존성·정합 점검
/project:design-pick self --strict                # BLOCK 있으면 exit 1
```

직접 Python 실행:

```bash
python3 .claude/bin/design_pick.py compare
python3 .claude/bin/design_pick.py apply apple
python3 .claude/bin/design_pick.py show
python3 .claude/bin/design_pick.py self --strict
```

---

## 5 서브커맨드

| 서브커맨드 | 동작 | LLM 호출 |
|---|---|---|
| **compare** (기본) | 4 브랜드 비교표 — 정체성·색상·폰트·radius·권장 용도 | 없음 (정적) |
| **recommend** | designer 에이전트 호출 방법 안내 + 예시 프롬프트 | 없음 (안내만) |
| **apply `<brand>`** | BRAND_CATALOG 를 `.claude/design/tokens.json` 으로 atomic write | 없음 (결정론적) |
| **show** | 현재 tokens.json 을 사람 읽기 좋은 표로 출력 | 없음 |
| **self** | 의존성·파일 존재·BRAND_CATALOG 정합 점검 | 없음 |

브랜드 이름: `apple` | `claude` | `spotify` | `tesla`

---

## 전역 옵션

| 옵션 | 기본값 | 설명 |
|---|---|---|
| `--output PATH` | `.claude/design/tokens.json` | tokens.json 경로 override |
| `--force` | OFF | apply 시 기존 tokens.json 백업 후 덮어쓰기 |
| `--strict` | OFF | BLOCK 1건이라도 있으면 exit 1 (CI gate) |
| `--format human\|json` | human | 출력 포맷 |

---

## 4 브랜드 요약

| 브랜드 | 정체성 | 캔버스 | 주색상 | 최적 용도 |
|---|---|---|---|---|
| **apple** | 사진 우선, 단일 블루 | `#ffffff` (light) | `#0066cc` | 제품 카탈로그, 미니멀 SaaS |
| **claude** | 따뜻한 편집물, 크림+코랄 | `#faf9f5` (warm cream) | `#cc785c` | AI 어시스턴트, 대화형 UX |
| **spotify** | 다크 콘텐츠 우선, 그린 | `#121212` (near-black) | `#1ed760` | 미디어 플레이어, 다크 모드 |
| **tesla** | 급진적 미니멀, 사진=디자인 | `#ffffff` (pure white) | `#3e6ae1` | 풀뷰포트 쇼케이스, 프리미엄 |

---

## 출력 예시

### compare

```
========================================================================
  Design-Pick — 4 브랜드 비교표
========================================================================

  브랜드     | 정체성               | 주색상      | ...
  -----------+---------------------+-------------+---
  apple      | 사진 우선, 단일 블루  | #0066cc     | ...
  claude     | 따뜻한 편집물        | #cc785c     | ...
  spotify    | 다크 콘텐츠 우선     | #1ed760     | ...
  tesla      | 급진적 미니멀        | #3e6ae1     | ...

  [토큰 카운트]
  apple    : colors=18  typography=12  radius=5  spacing=6  shadows=1
  claude   : colors=23  typography=12  radius=4  spacing=6  shadows=0
  spotify  : colors=17  typography=15  radius=7  spacing=7  shadows=3
  tesla    : colors=11  typography= 9  radius=4  spacing=6  shadows=0
```

### apply apple

```
[design-pick apply] apple 토큰 적용 완료
  경로   : /project/.claude/design/tokens.json
  토큰   : colors=18 typography=12 radius=5 spacing=6 shadows=1
  생성일 : 2026-06-02T14:30:00+09:00

  [다음 단계]
  현재 tokens 확인  : .claude/bin/design_pick.py show
  디자인 일관성 점검 : /project:design-review
```

### show

```
========================================================================
  tokens.json — apple
========================================================================
  경로        : /project/.claude/design/tokens.json
  생성일      : 2026-06-02T14:30:00+09:00
  생성 명령   : design_pick.py apply --brand=apple

  [Colors] (18 항목)
    primary                      #0066cc
    primary_focus                #0071e3
    ...

  [Typography] (12 항목)
    font_display : SF Pro Display, system-ui, ...
    font_body    : SF Pro Text, system-ui, ...
    스케일 (10 종):
      hero_display         56px / w600 / lh1.07 / ls-0.28
      ...

  [Characteristics]
    + photography-first
    + single-blue-accent
    ...
```

---

## 권장 호출 흐름

```
1. 비교표 확인
   /project:design-pick compare

2. LLM 추천 원할 때
   /project:design-pick recommend
   → 안내에 따라 designer 에이전트 호출

3. 브랜드 결정 후 토큰 적용
   /project:design-pick apply apple

4. 적용 확인
   /project:design-pick show

5. (선택) 디자인 일관성 점검 — 세션 3 이후
   /project:design-review
```

---

## 안전 보장

- **읽기 전용 서브커맨드**: compare / recommend / show / self 는 파일을 수정하지 않음
- **apply atomic write**: tempfile + os.replace — 저장 실패 시 기존 파일 유지
- **apply --force 백업**: 기존 tokens.json 을 `.backup.<ISO>.json` 으로 보존 후 덮어쓰기
- **hook-failure-tolerance**: 모든 핸들러 try/except → exit 0. `--strict` 명시 시만 BLOCK 발생 시 exit 1
- **외부 의존성 0**: Python stdlib only (argparse + json + pathlib + datetime + tempfile)
- **결정론적 apply**: 같은 brand 이면 항상 같은 tokens.json (generated_at 만 차이)

---

## tokens.json 스키마

`docs/design/F011-tokens-schema.md` 단일 소스. 핵심 필드:

| 필드 | 필수 | 설명 |
|---|---|---|
| `$schema` | 권장 | 스키마 문서 경로 |
| `version` | 필수 | 스키마 버전 (현재 1) |
| `brand` | 필수 | `apple` / `claude` / `spotify` / `tesla` / `custom` |
| `source_ref` | 필수 | 원본 디자인 명세 경로 |
| `generated_at` | 자동 | ISO 8601 timestamp |
| `generated_by` | 자동 | 생성 명령어 |
| `colors` | 필수 | 색상 토큰 dict |
| `typography` | 필수 | 폰트 + 스케일 dict |
| `radius` | 필수 | 반경 토큰 dict |
| `spacing` | 필수 | 간격 토큰 dict |
| `shadows` | 선택 | 그림자 토큰 dict |
| `characteristics` | 권장 | 시그니처 정체성 태그 (design-review 활용) |
| `anti_patterns` | 권장 | 피해야 할 패턴 (design-review CONCERN 감지) |

---

## 호출 기준

다음 중 하나라도 해당되면 `/project:design-pick` 실행을 권장한다:

- 새 UI 프로젝트 시작 시 디자인 정체성을 결정해야 할 때
- tokens.json 없는 상태에서 `/project:design-review` 실행 전
- 브랜드 방향성 재검토 (apply --force 로 재적용)
- design-review D. TOKEN 카테고리 CONCERN 수정 후 tokens.json 갱신 시

해당 없으면 (예: 순수 로직·API·테스트만 변경) 스킵 가능.

---

## 다른 도구와의 역할 경계

| 도구 | 책임 |
|---|---|
| **designer 에이전트** | LLM-driven 브랜드 분석 + 추천 + tokens.json 시안 생성 |
| **design-pick** (이 커맨드) | 정적 비교표 + 에이전트 안내 + 결정론적 tokens.json 생성 |
| **design-review** | tokens.json 기반 UI 일관성 감사 (D. TOKEN 카테고리 — 세션 3) |
| **lint** | 거버넌스 정합성 (LINT-MR: 변형 미러 정합 — 세션 3) |

**호출 순서**: designer(추천) → design-pick apply(확정) → 개발 → design-review(감사)

---

## 파일 위치

| 파일 | 역할 |
|---|---|
| `.claude/commands/design-pick.md` | 이 파일 — 슬래시 커맨드 진입점 |
| `.claude/bin/design_pick.py` | 헬퍼 구현 (BRAND_CATALOG + 5 서브커맨드) |
| `.claude/design/tokens.json` | apply 시 생성 (런타임 산출물) |
| `.claude/agents/designer.md` | LLM 브랜드 분석 에이전트 |
| `docs/design/F011-tokens-schema.md` | tokens.json 스키마 단일 소스 |
| `docs/design-references/*.md` | 4 브랜드 디자인 명세 (변형 내부) |

---

## 관련 참조

- ADR-006 결정 3 (5 서브커맨드 인터페이스)
- ADR-006 결정 4 (tokens.json 스키마)
- ADR-006 결정 6 (변형 미러 매트릭스 — claude.gstack.auto.design 만)
- `docs/design/F011-tokens-schema.md` (스키마 상세)
