# F011 tokens.json 스키마 정의

> Feature: F011 — Phase 7 Design-Pick
> 작성: developer 에이전트 | 날짜: 2026-06-02
> ADR-006 결정 4 — `tokens.json` 출력 스키마 단일 소스

---

## 개요

`.claude/design/tokens.json` 은 `/project:design-pick apply` 실행 시 `design_pick.py` 가
생성하는 정적 JSON 파일이다. 다운스트림 UI 프로젝트가 CSS 변수·Tailwind config·SCSS 변수 등으로
변환해 사용한다.

---

## 스키마 필드 정의

| 필드 | 타입 | 필수 여부 | 설명 |
|---|---|---|---|
| `$schema` | string | 권장 | 스키마 정의 문서 경로 (`docs/design/F011-tokens-schema.md`) |
| `version` | integer | 필수 | 스키마 버전 (현재 1). 향후 v2 마이그레이션 경로 |
| `brand` | string | 필수 | `apple` / `claude` / `spotify` / `tesla` / `custom` |
| `source_ref` | string | 필수 | 원본 디자인 명세 경로 (변형 내부 기준 — `docs/design-references/<brand>-design.md`) |
| `generated_at` | string | 자동 | ISO 8601 timestamp (design_pick.py 가 자동 기입) |
| `generated_by` | string | 자동 | 생성 명령어 (감사 추적용 — `design_pick.py apply --brand=<brand>`) |
| `colors` | object | 필수 | 색상 토큰. 키는 의미 기반 (primary/canvas/ink 등) |
| `typography` | object | 필수 | 폰트 패밀리 + 타이포 스케일 |
| `radius` | object | 필수 | 반경 토큰 (sm/md/lg/pill 최소 4개) |
| `spacing` | object | 필수 | 간격 토큰 (section/xl/lg/md/sm/xs 최소 6개) |
| `shadows` | object | 선택 | 그림자 토큰 (브랜드별 0~3 개) |
| `characteristics` | string[] | 권장 | 시그니처 정체성 태그 (design-review D.TOKEN 카테고리가 사용) |
| `anti_patterns` | string[] | 권장 | 피해야 할 패턴 (design-review CONCERN 감지에 사용) |

---

## typography 서브 스키마

`typography.font_display` / `typography.font_body` 는 CSS font-family 문자열.
타이포 스케일 각 항목:

```json
{
  "size": 17,
  "weight": 400,
  "line_height": 1.47,
  "letter_spacing": -0.374
}
```

| 키 | 단위 | 설명 |
|---|---|---|
| `size` | px (정수) | font-size |
| `weight` | 100~900 (정수) | font-weight |
| `line_height` | 배수 (소수) | line-height (unitless) |
| `letter_spacing` | px (소수) | letter-spacing (px 기준) |

### 권장 스케일 키 이름

| 키 | 대응 용도 |
|---|---|
| `hero_display` | 히어로 섹션 최상위 헤드라인 |
| `display_lg` | 큰 섹션 제목 |
| `display_md` | 중간 섹션 제목 |
| `lead` | 리드 텍스트 / 서브헤드 |
| `tagline` | 태그라인 / 캡션 헤드 |
| `body` | 본문 텍스트 |
| `caption` | 캡션 / 라벨 |
| `fine_print` | 주석 / 법적 고지 |

---

## colors 키 컨벤션

| 키 패턴 | 의미 |
|---|---|
| `primary` | 주 브랜드 색상 (CTA, 링크) |
| `primary_focus` | 주 브랜드 hover/focus 상태 |
| `primary_on_dark` | 다크 배경에서의 주 브랜드 색상 |
| `canvas` | 기본 배경 |
| `canvas_*` | 배경 변형 (parchment, warm 등) |
| `surface_*` | 카드·패널 표면 |
| `ink` | 주 텍스트 색상 |
| `ink_muted_*` | 투명도 기반 텍스트 변형 |
| `body` | 본문 텍스트 색상 |
| `body_on_dark` | 다크 배경 본문 텍스트 |
| `divider_*` | 구분선 색상 |
| `hairline` | 얇은 구분선 |

---

## 완전한 Apple 예시

```json
{
  "$schema": "docs/design/F011-tokens-schema.md",
  "version": 1,
  "brand": "apple",
  "source_ref": "docs/design-references/apple-design.md",
  "generated_at": "2026-06-02T14:30:00+09:00",
  "generated_by": "design_pick.py apply --brand=apple",
  "colors": {
    "primary": "#0066cc",
    "primary_focus": "#0071e3",
    "primary_on_dark": "#2997ff",
    "canvas": "#ffffff",
    "canvas_parchment": "#f5f5f7",
    "surface_pearl": "#fafafc",
    "surface_tile_1": "#272729",
    "surface_tile_2": "#2a2a2c",
    "surface_tile_3": "#252527",
    "surface_black": "#000000",
    "ink": "#1d1d1f",
    "body": "#1d1d1f",
    "body_on_dark": "#ffffff",
    "body_muted": "#cccccc",
    "ink_muted_80": "#333333",
    "ink_muted_48": "#7a7a7a",
    "divider_soft": "#f0f0f0",
    "hairline": "#e0e0e0"
  },
  "typography": {
    "font_display": "SF Pro Display, system-ui, -apple-system, sans-serif",
    "font_body": "SF Pro Text, system-ui, -apple-system, sans-serif",
    "hero_display": { "size": 56, "weight": 600, "line_height": 1.07, "letter_spacing": -0.28 },
    "display_lg":   { "size": 40, "weight": 600, "line_height": 1.10, "letter_spacing": 0 },
    "display_md":   { "size": 34, "weight": 600, "line_height": 1.47, "letter_spacing": -0.374 },
    "lead":         { "size": 28, "weight": 400, "line_height": 1.14, "letter_spacing": 0.196 },
    "tagline":      { "size": 21, "weight": 600, "line_height": 1.19, "letter_spacing": 0.231 },
    "body":         { "size": 17, "weight": 400, "line_height": 1.47, "letter_spacing": -0.374 },
    "caption":      { "size": 14, "weight": 400, "line_height": 1.43, "letter_spacing": -0.224 },
    "fine_print":   { "size": 12, "weight": 400, "line_height": 1.0,  "letter_spacing": -0.12 }
  },
  "radius": {
    "sm": 4,
    "md": 8,
    "lg": 18,
    "pill": 9999
  },
  "spacing": {
    "section": 96,
    "xl": 32,
    "lg": 24,
    "md": 16,
    "sm": 8,
    "xs": 4
  },
  "shadows": {
    "product_hero": "rgba(0, 0, 0, 0.22) 3px 5px 30px"
  },
  "characteristics": [
    "photography-first",
    "single-blue-accent",
    "no-decorative-gradients",
    "alternating-tile-sections",
    "tight-display-tracking"
  ],
  "anti_patterns": [
    "decorative-gradients",
    "second-brand-color",
    "shadows-on-headlines",
    "border-on-product-photo"
  ]
}
```

---

## brand: "custom" 지원

4 브랜드 외 디자인을 사용하는 다운스트림 프로젝트:

```json
{
  "$schema": "docs/design/F011-tokens-schema.md",
  "version": 1,
  "brand": "custom",
  "source_ref": "docs/design-references/my-brand-design.md",
  ...
}
```

`custom` 브랜드는 `design_pick.py apply` 의 `--brand=custom` 으로 직접 파일을 작성하거나,
designer 에이전트가 시안을 생성한 후 사용자가 수동으로 tokens.json 을 저장.

---

## 버전 마이그레이션 경로

현재 `version: 1`. 향후 스키마 변경 시:

- `version: 2`: `design_pick.py apply` 가 `version: 1` 파일을 자동 마이그레이션 또는 경고
- 마이그레이션 스크립트: `design_pick.py migrate --from=1 --to=2` (후속 phase)

---

## 관련 참조

- ADR-006 결정 4 — tokens.json 출력 스키마
- `.claude/bin/design_pick.py` (세션 2 신설 — apply 서브커맨드가 이 스키마로 파일 생성)
- `.claude/agents/designer.md` (tokens.json 시안 출력 형식)
- `.claude/skills/design-review/SKILL.md` (세션 3 갱신 — D. TOKEN 카테고리)
