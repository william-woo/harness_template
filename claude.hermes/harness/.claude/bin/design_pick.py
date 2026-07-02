#!/usr/bin/env python3
"""F011 — Design-Pick helper.

4 브랜드 디자인 토큰 카탈로그 관리 + tokens.json 생성.
외부 의존성 없음 (Python stdlib only).

서브커맨드:
  compare              — 4 브랜드 비교표 출력 (LLM 호출 X, 정적)
  recommend            — designer 에이전트 호출 안내 (LLM-driven 추천은 에이전트가)
  apply <brand>        — 선택된 brand 의 BRAND_CATALOG 를 tokens.json 으로 결정론적 출력
  show                 — 현재 .claude/design/tokens.json 표시
  self                 — 의존성·정합 점검

옵션:
  --output PATH        — tokens.json 경로 override (기본: .claude/design/tokens.json)
  --force              — apply 시 기존 tokens.json 백업 없이 덮어쓰기 (기본 OFF)
  --strict             — BLOCK 1건이라도 있으면 exit 1 (F009 lint.py 일관)
  --format json|human  — 출력 포맷 (기본: human)

설계 원칙:
  - 실패해도 hook-failure-tolerance (exit 0 유지) — --strict 플래그 명시 시만 exit 1
  - 외부 의존성 0 (argparse + json + pathlib + datetime + tempfile)
  - F005/F009/F010 단일 파일 헬퍼 패턴 100% 일관
  - apply 는 결정론적 — 같은 brand 이면 항상 같은 tokens.json (generated_at 만 차이)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

# ─── 경로 상수 ────────────────────────────────────────────────────────────────

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_REFS_DIR = _PROJECT_ROOT / ".claude" / "design" / "references"
_DESIGN_DIR = _PROJECT_ROOT / ".claude" / "design"
_TOKENS_PATH_DEFAULT = _DESIGN_DIR / "tokens.json"
_REFS_ALT_DIR = _PROJECT_ROOT / "docs" / "design-references"  # 변형 경로

# 라벨 (F007 design-review / F009 lint 일관)
BLOCK = "BLOCK"
CONCERN = "CONCERN"
INFO = "INFO"
PASS_LABEL = "PASS"

# ─── 4 브랜드 정적 카탈로그 ──────────────────────────────────────────────────
# ADR-006 결정 3 — BRAND_CATALOG: design_pick.py 내부 상수
# ADR-006 결정 4 — tokens.json 스키마 (docs/design/F011-tokens-schema.md 단일 소스)
# 각 brand 는 F011-tokens-schema.md 의 정식 스키마를 따름

BRAND_CATALOG: dict = {
    "apple": {
        "version": 1,
        "brand": "apple",
        "source_ref": "docs/design-references/apple-design.md",
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
            "hairline": "#e0e0e0",
        },
        "typography": {
            "font_display": "SF Pro Display, system-ui, -apple-system, sans-serif",
            "font_body": "SF Pro Text, system-ui, -apple-system, sans-serif",
            "hero_display": {"size": 56, "weight": 600, "line_height": 1.07, "letter_spacing": -0.28},
            "display_lg": {"size": 40, "weight": 600, "line_height": 1.10, "letter_spacing": 0},
            "display_md": {"size": 34, "weight": 600, "line_height": 1.47, "letter_spacing": -0.374},
            "lead": {"size": 28, "weight": 400, "line_height": 1.14, "letter_spacing": 0.196},
            "tagline": {"size": 21, "weight": 600, "line_height": 1.19, "letter_spacing": 0.231},
            "body_strong": {"size": 17, "weight": 600, "line_height": 1.24, "letter_spacing": -0.374},
            "body": {"size": 17, "weight": 400, "line_height": 1.47, "letter_spacing": -0.374},
            "caption": {"size": 14, "weight": 400, "line_height": 1.43, "letter_spacing": -0.224},
            "fine_print": {"size": 12, "weight": 400, "line_height": 1.0, "letter_spacing": -0.12},
            "nav_link": {"size": 12, "weight": 400, "line_height": 1.0, "letter_spacing": -0.12},
        },
        "radius": {"sm": 4, "md": 8, "lg": 18, "xl": 24, "pill": 9999},
        "spacing": {"section": 96, "xl": 32, "lg": 24, "md": 16, "sm": 8, "xs": 4},
        "shadows": {
            "product_hero": "rgba(0, 0, 0, 0.22) 3px 5px 30px",
        },
        "characteristics": [
            "photography-first",
            "single-blue-accent",
            "no-decorative-gradients",
            "alternating-tile-sections",
            "tight-display-tracking",
        ],
        "anti_patterns": [
            "decorative-gradients",
            "second-brand-color",
            "shadows-on-headlines",
            "border-on-product-photo",
        ],
    },

    "claude": {
        "version": 1,
        "brand": "claude",
        "source_ref": "docs/design-references/claude-design.md",
        "colors": {
            "primary": "#cc785c",
            "primary_active": "#a9583e",
            "primary_disabled": "#e6dfd8",
            "accent_teal": "#5db8a6",
            "accent_amber": "#e8a55a",
            "canvas": "#faf9f5",
            "surface_soft": "#f5f0e8",
            "surface_card": "#efe9de",
            "surface_cream_strong": "#e8e0d2",
            "surface_dark": "#181715",
            "surface_dark_elevated": "#252320",
            "surface_dark_soft": "#1f1e1b",
            "ink": "#141413",
            "body_strong": "#252523",
            "body": "#3d3d3a",
            "muted": "#6c6a64",
            "muted_soft": "#8e8b82",
            "on_primary": "#ffffff",
            "on_dark": "#faf9f5",
            "on_dark_soft": "#a09d96",
            "success": "#5db872",
            "warning": "#d4a017",
            "error": "#c64545",
            "hairline": "#e6dfd8",
            "hairline_soft": "#ebe6df",
        },
        "typography": {
            "font_display": "Copernicus, Tiempos Headline, Garamond, 'Times New Roman', serif",
            "font_body": "StyreneB, Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
            "font_mono": "JetBrains Mono, monospace",
            "display_xl": {"size": 64, "weight": 400, "line_height": 1.05, "letter_spacing": -1.5},
            "display_lg": {"size": 48, "weight": 400, "line_height": 1.10, "letter_spacing": -1.0},
            "display_md": {"size": 36, "weight": 400, "line_height": 1.15, "letter_spacing": -0.5},
            "display_sm": {"size": 28, "weight": 400, "line_height": 1.20, "letter_spacing": -0.3},
            "title_lg": {"size": 22, "weight": 500, "line_height": 1.30, "letter_spacing": 0},
            "title_md": {"size": 18, "weight": 500, "line_height": 1.40, "letter_spacing": 0},
            "title_sm": {"size": 16, "weight": 500, "line_height": 1.40, "letter_spacing": 0},
            "body_md": {"size": 16, "weight": 400, "line_height": 1.55, "letter_spacing": 0},
            "body_sm": {"size": 14, "weight": 400, "line_height": 1.50, "letter_spacing": 0},
            "caption": {"size": 12, "weight": 400, "line_height": 1.40, "letter_spacing": 0},
        },
        "radius": {"md": 8, "lg": 12, "xl": 16, "pill": 9999},
        "spacing": {"section": 96, "xl": 32, "lg": 24, "md": 16, "sm": 8, "xs": 4},
        "shadows": {},
        "characteristics": [
            "warm-cream-canvas",
            "coral-primary-accent",
            "copernicus-slab-serif-display",
            "dark-navy-product-mockups",
            "alternating-cream-dark-rhythm",
        ],
        "anti_patterns": [
            "cool-gray-white-canvas",
            "saturated-cyan-or-blue-accents",
            "geometric-sans-display",
        ],
    },

    "spotify": {
        "version": 1,
        "brand": "spotify",
        "source_ref": "docs/design-references/spotify-design.md",
        "colors": {
            "primary": "#1ed760",
            "primary_border": "#1db954",
            "canvas": "#121212",
            "surface_card": "#181818",
            "surface_interactive": "#1f1f1f",
            "surface_card_alt": "#252525",
            "surface_card_alt2": "#272727",
            "surface_light": "#eeeeee",
            "ink": "#ffffff",
            "body": "#ffffff",
            "body_secondary": "#b3b3b3",
            "body_near_white": "#cbcbcb",
            "body_emphasis": "#fdfdfd",
            "border_dark": "#4d4d4d",
            "border_light": "#7c7c7c",
            "separator": "#b3b3b3",
            "error": "#f3727f",
            "warning": "#ffa42b",
            "info": "#539df5",
        },
        "typography": {
            "font_display": "SpotifyMixUITitle, CircularSp-Arab, CircularSp-Hebr, CircularSp-Cyrl, CircularSp-Grek, CircularSp-Deva, Helvetica Neue, helvetica, arial, Hiragino Sans, Hiragino Kaku Gothic ProN, Meiryo, MS Gothic, sans-serif",
            "font_body": "SpotifyMixUI, CircularSp-Arab, CircularSp-Hebr, CircularSp-Cyrl, CircularSp-Grek, CircularSp-Deva, Helvetica Neue, helvetica, arial, Hiragino Sans, Hiragino Kaku Gothic ProN, Meiryo, MS Gothic, sans-serif",
            "section_title": {"size": 24, "weight": 700, "line_height": 1.0, "letter_spacing": 0},
            "feature_heading": {"size": 18, "weight": 600, "line_height": 1.30, "letter_spacing": 0},
            "body_bold": {"size": 16, "weight": 700, "line_height": 1.0, "letter_spacing": 0},
            "body": {"size": 16, "weight": 400, "line_height": 1.0, "letter_spacing": 0},
            "button_uppercase": {"size": 14, "weight": 700, "line_height": 1.0, "letter_spacing": 1.4},
            "button": {"size": 14, "weight": 700, "line_height": 1.0, "letter_spacing": 0.14},
            "nav_link_bold": {"size": 14, "weight": 700, "line_height": 1.0, "letter_spacing": 0},
            "nav_link": {"size": 14, "weight": 400, "line_height": 1.0, "letter_spacing": 0},
            "caption_bold": {"size": 14, "weight": 700, "line_height": 1.52, "letter_spacing": 0},
            "caption": {"size": 14, "weight": 400, "line_height": 1.0, "letter_spacing": 0},
            "small_bold": {"size": 12, "weight": 700, "line_height": 1.50, "letter_spacing": 0},
            "small": {"size": 12, "weight": 400, "line_height": 1.0, "letter_spacing": 0},
            "badge": {"size": 11, "weight": 600, "line_height": 1.33, "letter_spacing": 0},
            "micro": {"size": 10, "weight": 400, "line_height": 1.0, "letter_spacing": 0},
        },
        "radius": {"minimal": 2, "subtle": 4, "standard": 6, "comfortable": 8, "large": 100, "pill": 500, "full_pill": 9999},
        "spacing": {"section": 20, "xl": 16, "lg": 12, "md": 8, "sm": 6, "xs": 4, "xxs": 2},
        "shadows": {
            "heavy": "rgba(0, 0, 0, 0.5) 0px 8px 24px",
            "medium": "rgba(0, 0, 0, 0.3) 0px 8px 8px",
            "inset_border": "rgb(18, 18, 18) 0px 1px 0px, rgb(124, 124, 124) 0px 0px 0px 1px inset",
        },
        "characteristics": [
            "near-black-immersive-dark-theme",
            "spotify-green-functional-only",
            "pill-and-circle-geometry",
            "uppercase-button-labels-wide-tracking",
            "album-art-as-primary-color-source",
            "heavy-shadows-on-dark",
        ],
        "anti_patterns": [
            "light-backgrounds-for-primary-surfaces",
            "green-decoratively-on-backgrounds",
            "square-buttons",
            "thin-subtle-shadows",
            "additional-brand-colors",
            "relaxed-line-heights",
        ],
    },

    "tesla": {
        "version": 1,
        "brand": "tesla",
        "source_ref": "docs/design-references/tesla-design.md",
        "colors": {
            "primary": "#3e6ae1",
            "canvas": "#ffffff",
            "canvas_ash": "#f4f4f4",
            "surface_dark": "#171a20",
            "surface_frosted": "rgba(255, 255, 255, 0.75)",
            "ink": "#171a20",
            "body": "#393c41",
            "body_tertiary": "#5c5e62",
            "placeholder": "#8e8e8e",
            "border_cloud": "#eeeeee",
            "border_pale": "#d0d1d2",
        },
        "typography": {
            "font_display": "Universal Sans Display, -apple-system, Arial, sans-serif",
            "font_body": "Universal Sans Text, -apple-system, Arial, sans-serif",
            "hero_display": {"size": 40, "weight": 500, "line_height": 1.20, "letter_spacing": 0},
            "promo": {"size": 22, "weight": 400, "line_height": 0.91, "letter_spacing": 0},
            "product_name": {"size": 17, "weight": 500, "line_height": 1.18, "letter_spacing": 0},
            "nav_item": {"size": 14, "weight": 500, "line_height": 1.20, "letter_spacing": 0},
            "body": {"size": 14, "weight": 400, "line_height": 1.43, "letter_spacing": 0},
            "button_label": {"size": 14, "weight": 500, "line_height": 1.20, "letter_spacing": 0},
            "sub_link": {"size": 14, "weight": 400, "line_height": 1.43, "letter_spacing": 0},
        },
        "radius": {"flat": 0, "sm": 4, "card": 12, "circle": None},
        "spacing": {"section": None, "xl": 21, "lg": 16, "md": 8, "sm": 4, "button_h": 40},
        "shadows": {},
        "characteristics": [
            "full-viewport-hero-photography",
            "near-zero-ui-decoration",
            "single-blue-cta-only",
            "universal-sans-font-family",
            "whitespace-as-luxury-signal",
            "no-gradients-no-shadows-no-borders",
        ],
        "anti_patterns": [
            "any-box-shadows",
            "more-than-one-chromatic-color",
            "gradients-patterns-decorative-backgrounds",
            "rounded-pill-buttons",
            "uppercase-text-transforms",
            "hover-scale-translate-animations",
        ],
    },
}

# ─── 브랜드 메타 요약 (compare 출력용) ────────────────────────────────────────

BRAND_SUMMARY: dict = {
    "apple": {
        "identity": "사진 우선, 단일 블루",
        "primary_color": "#0066cc",
        "canvas": "#ffffff (light)",
        "font": "SF Pro Display / Text",
        "radius": "sm(4) ~ pill(9999)",
        "shadows": "최소 (제품 이미지 1종)",
        "best_for": "제품 카탈로그, 마케팅, 미니멀 SaaS",
        "avoid": "콘텐츠 밀도 높은 대시보드, 다크 모드 우선",
    },
    "claude": {
        "identity": "따뜻한 편집물, 크림 + 코랄",
        "primary_color": "#cc785c",
        "canvas": "#faf9f5 (warm cream)",
        "font": "Copernicus (serif) / StyreneB",
        "radius": "md(8) ~ pill(9999)",
        "shadows": "없음 (flat)",
        "best_for": "AI 어시스턴트, 인터뷰/매거진, 대화형 UX",
        "avoid": "쿨-그레이 캔버스, 사이언/블루 어센트",
    },
    "spotify": {
        "identity": "다크 콘텐츠 우선, 그린 어센트",
        "primary_color": "#1ed760",
        "canvas": "#121212 (near-black)",
        "font": "SpotifyMixUI / CircularSp",
        "radius": "subtle(4) ~ full_pill(9999)",
        "shadows": "헤비 (0.3~0.5 불투명도)",
        "best_for": "미디어 플레이어, 콘텐츠 앱, 다크 모드 우선",
        "avoid": "라이트 배경, 스퀘어 버튼, 추가 브랜드 색상",
    },
    "tesla": {
        "identity": "급진적 미니멀, 사진이 디자인",
        "primary_color": "#3e6ae1",
        "canvas": "#ffffff (pure white)",
        "font": "Universal Sans Display / Text",
        "radius": "flat(0) ~ sm(4) (극도 절제)",
        "shadows": "없음 (zero shadow policy)",
        "best_for": "풀뷰포트 쇼케이스, 전시형 랜딩, 프리미엄 제품",
        "avoid": "그림자, 다중 색상, 그라데이션, 라운드 필 버튼",
    },
}


# ─── 유틸리티 ─────────────────────────────────────────────────────────────────


def _find_refs_dir() -> Path | None:
    """
    디자인 참조 파일 디렉토리를 탐지한다.

    Returns:
        Path: 디렉토리 경로 (존재 시), None (미존재 시)
    """
    candidates = [
        _REFS_DIR,      # 메인 SSoT: .claude/design/references/
        _REFS_ALT_DIR,  # 변형 경로: docs/design-references/
    ]
    for p in candidates:
        if p.is_dir():
            return p
    return None


def _tokens_path(args) -> Path:
    """
    tokens.json 저장 경로를 반환한다.

    Args:
        args: argparse Namespace (--output 옵션 처리)

    Returns:
        Path: tokens.json 절대 경로
    """
    if hasattr(args, "output") and args.output:
        return Path(args.output).resolve()
    return _TOKENS_PATH_DEFAULT


def _write_tokens_atomic(path: Path, data: dict) -> bool:
    """
    tokens.json 을 atomic write 로 저장한다 (tempfile + os.replace).

    Args:
        path: 저장 경로
        data: 저장할 dict (JSON 직렬화 가능)

    Returns:
        bool: 성공 여부
    """
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_fd, tmp_path = tempfile.mkstemp(
            dir=str(path.parent), prefix=".tokens-", suffix=".json"
        )
        try:
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, path)
            return True
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
    except Exception as e:
        print(f"[design-pick] tokens.json write 실패: {e}", file=sys.stderr)
        return False


def _count_tokens(catalog: dict) -> dict:
    """
    BRAND_CATALOG 항목의 토큰 수를 계산한다.

    Args:
        catalog: 단일 브랜드 카탈로그 dict

    Returns:
        dict: {colors: int, typography: int, radius: int, spacing: int, shadows: int}
    """
    return {
        "colors": len(catalog.get("colors", {})),
        "typography": len(catalog.get("typography", {})),
        "radius": len(catalog.get("radius", {})),
        "spacing": len(catalog.get("spacing", {})),
        "shadows": len(catalog.get("shadows", {})),
    }


# ─── 서브커맨드 핸들러 ────────────────────────────────────────────────────────


def cmd_compare(args) -> int:
    """
    4 브랜드 비교표를 정적으로 출력한다 (LLM 호출 없음).

    ADR-006 결정 3: compare 는 BRAND_CATALOG 내부 상수에서 정적 출력.
    --format=json 시 핵심 메타만 JSON 으로 반환.

    Args:
        args: argparse Namespace

    Returns:
        int: 종료 코드 (항상 0 — hook-failure-tolerance)
    """
    try:
        if hasattr(args, "format") and args.format == "json":
            output = {}
            for brand, meta in BRAND_SUMMARY.items():
                tc = _count_tokens(BRAND_CATALOG[brand])
                output[brand] = {**meta, "token_counts": tc}
            print(json.dumps(output, ensure_ascii=False, indent=2))
            return 0

        print("=" * 72)
        print("  Design-Pick — 4 브랜드 비교표")
        print("=" * 72)
        print()

        # 헤더
        headers = ["브랜드", "정체성", "주색상", "캔버스", "폰트", "radius", "shadows", "최적 용도"]
        col_widths = [10, 20, 12, 22, 28, 22, 22, 32]

        def _row(cells: list, widths: list) -> str:
            parts = []
            for cell, w in zip(cells, widths):
                cell_str = str(cell)
                if len(cell_str) > w:
                    cell_str = cell_str[:w-1] + "…"
                parts.append(cell_str.ljust(w))
            return "  " + " | ".join(parts)

        print(_row(headers, col_widths))
        print("  " + "-+-".join("-" * w for w in col_widths))

        for brand, meta in BRAND_SUMMARY.items():
            row = [
                brand,
                meta["identity"],
                meta["primary_color"],
                meta["canvas"],
                meta["font"],
                meta["radius"],
                meta["shadows"],
                meta["best_for"],
            ]
            print(_row(row, col_widths))

        print()
        print("  [토큰 카운트]")
        for brand in BRAND_CATALOG:
            tc = _count_tokens(BRAND_CATALOG[brand])
            print(
                f"  {brand:12s}: "
                f"colors={tc['colors']:2d}  "
                f"typography={tc['typography']:2d}  "
                f"radius={tc['radius']:2d}  "
                f"spacing={tc['spacing']:2d}  "
                f"shadows={tc['shadows']:2d}"
            )

        print()
        print("  [다음 단계]")
        print("  추천 받기:  .claude/bin/design_pick.py recommend")
        print("  바로 적용:  .claude/bin/design_pick.py apply <brand>")
        print("  (브랜드: apple | claude | spotify | tesla)")
        print()

    except Exception as e:
        print(f"[design-pick compare] 오류: {e}", file=sys.stderr)

    return 0


def cmd_recommend(args) -> int:
    """
    designer 에이전트 호출 안내를 출력한다 (직접 LLM 호출 없음).

    ADR-006 결정 3 참조: recommend 의 LLM-driven 추천은 designer 에이전트가 담당.
    이 헬퍼는 결정론적 — 에이전트 호출 방법 안내만 출력.

    Args:
        args: argparse Namespace

    Returns:
        int: 종료 코드 (항상 0)
    """
    try:
        print("=" * 72)
        print("  Design-Pick — 브랜드 추천 (designer 에이전트 위임)")
        print("=" * 72)
        print()
        print("  LLM-driven 브랜드 추천은 designer 에이전트가 담당합니다.")
        print("  다음 방법으로 designer 에이전트를 호출하세요:")
        print()
        print("  ─ 자유 산문 (추천):")
        print(
            "    Use the designer agent to recommend a design system for a"
            " dark media player project"
        )
        print()
        print("  ─ 브랜드 강제 지정:")
        print(
            "    Use the designer agent to analyze the apple brand and generate"
            " a tokens.json draft"
        )
        print()
        print("  ─ 비교표 + 추천 동시:")
        print(
            "    Use the designer agent to compare all 4 brands and recommend"
            " the best fit for [your project description]"
        )
        print()
        print("  [designer 에이전트 출력 4 단계]")
        print("  1. 비교표 — 4 브랜드를 색상·타이포·radius·접근성·복잡도 5 축으로 비교")
        print("  2. 추천 — 1~2 후보 + 추천 근거 (3~5 문장)")
        print("  3. tokens.json 시안 — F011-tokens-schema.md 스키마 준수")
        print("  4. 적용 단계 — .claude/bin/design_pick.py apply <brand>")
        print()
        print("  [비대화형 바로 적용 (designer 없이)]")
        print("  .claude/bin/design_pick.py compare              # 비교표만 확인")
        print("  .claude/bin/design_pick.py apply <brand>        # 바로 적용")
        print("  .claude/bin/design_pick.py apply apple --force  # 기존 덮어쓰기")
        print()

    except Exception as e:
        print(f"[design-pick recommend] 오류: {e}", file=sys.stderr)

    return 0


def cmd_apply(args) -> int:
    """
    brand 의 BRAND_CATALOG 를 tokens.json 으로 atomic write 저장한다.

    ADR-006 결정 3:
    - 기존 tokens.json 존재 시 --force 없으면 거부
    - --force 시 기존 파일을 .backup.<ISO>.json 으로 백업 후 덮어쓰기
    - generated_at ISO timestamp 자동 추가
    - 결정론적 — 같은 brand 이면 같은 tokens.json (generated_at 만 차이)

    Args:
        args: argparse Namespace (brand, output, force 속성 필요)

    Returns:
        int: 종료 코드
    """
    try:
        brand = getattr(args, "brand", None)
        if not brand:
            print("[design-pick apply] 브랜드 이름 필요: apply <brand>", file=sys.stderr)
            print("  사용 가능: apple | claude | spotify | tesla", file=sys.stderr)
            if getattr(args, "strict", False):
                return 1
            return 0

        if brand not in BRAND_CATALOG:
            print(
                f"[design-pick apply] 알 수 없는 브랜드: '{brand}'", file=sys.stderr
            )
            print(
                f"  사용 가능: {' | '.join(BRAND_CATALOG.keys())}", file=sys.stderr
            )
            if getattr(args, "strict", False):
                return 1
            return 0

        tokens_path = _tokens_path(args)
        force = getattr(args, "force", False)

        # 기존 tokens.json 처리
        if tokens_path.exists():
            if not force:
                print(f"[design-pick apply] 기존 tokens.json 존재: {tokens_path}")
                print("  덮어쓰려면 --force 플래그를 추가하세요:")
                print(f"  .claude/bin/design_pick.py apply {brand} --force")
                if getattr(args, "strict", False):
                    return 1
                return 0
            # --force: 기존 파일 백업
            ts_str = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            backup_path = tokens_path.parent / f"tokens.backup.{ts_str}.json"
            try:
                import shutil
                shutil.copy2(str(tokens_path), str(backup_path))
                print(f"[design-pick apply] 기존 tokens.json 백업: {backup_path}")
            except Exception as e:
                print(
                    f"[design-pick apply] 백업 실패 (계속 진행): {e}", file=sys.stderr
                )

        # 카탈로그 복사 + 메타 필드 추가
        catalog = BRAND_CATALOG[brand].copy()
        now_iso = datetime.now(tz=timezone.utc).astimezone().isoformat()
        tokens_data = {
            "$schema": "docs/design/F011-tokens-schema.md",
            "version": catalog.get("version", 1),
            "brand": brand,
            "source_ref": catalog.get("source_ref", f"docs/design-references/{brand}-design.md"),
            "generated_at": now_iso,
            "generated_by": f"design_pick.py apply --brand={brand}",
            "colors": catalog.get("colors", {}),
            "typography": catalog.get("typography", {}),
            "radius": catalog.get("radius", {}),
            "spacing": catalog.get("spacing", {}),
            "shadows": catalog.get("shadows", {}),
            "characteristics": catalog.get("characteristics", []),
            "anti_patterns": catalog.get("anti_patterns", []),
        }

        success = _write_tokens_atomic(tokens_path, tokens_data)
        if not success:
            print(f"[design-pick apply] 저장 실패: {tokens_path}", file=sys.stderr)
            if getattr(args, "strict", False):
                return 1
            return 0

        tc = _count_tokens(catalog)
        print(f"[design-pick apply] {brand} 토큰 적용 완료")
        print(f"  경로   : {tokens_path}")
        print(
            f"  토큰   : colors={tc['colors']} typography={tc['typography']}"
            f" radius={tc['radius']} spacing={tc['spacing']} shadows={tc['shadows']}"
        )
        print(f"  생성일 : {now_iso}")
        print()
        print("  [다음 단계]")
        print("  현재 tokens 확인  : .claude/bin/design_pick.py show")
        print("  디자인 일관성 점검 : /project:design-review (세션 3 이후 활성화)")
        print()

    except Exception as e:
        print(f"[design-pick apply] 오류: {e}", file=sys.stderr)
        if getattr(args, "strict", False):
            return 1

    return 0


def cmd_show(args) -> int:
    """
    현재 tokens.json 을 사람이 읽기 좋은 형식으로 표시한다.

    tokens.json 부재 시 안내 메시지 + 다음 단계 출력.

    Args:
        args: argparse Namespace

    Returns:
        int: 종료 코드 (항상 0)
    """
    try:
        tokens_path = _tokens_path(args)

        if not tokens_path.exists():
            print("[design-pick show] 아직 tokens.json 이 없습니다.")
            print(f"  기대 경로: {tokens_path}")
            print()
            print("  [다음 단계]")
            print("  1. 비교표 확인 : .claude/bin/design_pick.py compare")
            print("  2. 추천 요청   : designer 에이전트 호출 (recommend 서브커맨드 참조)")
            print("  3. 토큰 적용   : .claude/bin/design_pick.py apply <brand>")
            print("     예시: .claude/bin/design_pick.py apply apple")
            return 0

        try:
            with open(tokens_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            print(f"[design-pick show] tokens.json JSON 파싱 실패: {e}", file=sys.stderr)
            if getattr(args, "strict", False):
                return 1
            return 0

        fmt = getattr(args, "format", "human")
        if fmt == "json":
            print(json.dumps(data, ensure_ascii=False, indent=2))
            return 0

        # human 출력
        brand = data.get("brand", "unknown")
        generated_at = data.get("generated_at", "N/A")
        generated_by = data.get("generated_by", "N/A")

        print("=" * 72)
        print(f"  tokens.json — {brand}")
        print("=" * 72)
        print(f"  경로        : {tokens_path}")
        print(f"  생성일      : {generated_at}")
        print(f"  생성 명령   : {generated_by}")
        print()

        # Colors 표
        colors = data.get("colors", {})
        if colors:
            print(f"  [Colors] ({len(colors)} 항목)")
            for k, v in colors.items():
                print(f"    {k:<28s} {v}")
            print()

        # Typography 요약
        typography = data.get("typography", {})
        if typography:
            print(f"  [Typography] ({len(typography)} 항목)")
            font_d = typography.get("font_display", "N/A")
            font_b = typography.get("font_body", "N/A")
            print(f"    font_display : {font_d}")
            print(f"    font_body    : {font_b}")
            scales = {k: v for k, v in typography.items() if isinstance(v, dict)}
            if scales:
                print(f"    스케일 ({len(scales)} 종):")
                for k, v in scales.items():
                    size = v.get("size", "?")
                    weight = v.get("weight", "?")
                    lh = v.get("line_height", "?")
                    ls = v.get("letter_spacing", "?")
                    print(f"      {k:<20s} {size}px / w{weight} / lh{lh} / ls{ls}")
            print()

        # Radius
        radius = data.get("radius", {})
        if radius:
            print(f"  [Radius] ({len(radius)} 항목)")
            parts = [f"{k}={v}" for k, v in radius.items()]
            print(f"    {', '.join(parts)}")
            print()

        # Spacing
        spacing = data.get("spacing", {})
        if spacing:
            print(f"  [Spacing] ({len(spacing)} 항목)")
            parts = [f"{k}={v}" for k, v in spacing.items()]
            print(f"    {', '.join(parts)}")
            print()

        # Shadows
        shadows = data.get("shadows", {})
        if shadows:
            print(f"  [Shadows] ({len(shadows)} 항목)")
            for k, v in shadows.items():
                print(f"    {k}: {v}")
            print()

        # Characteristics + anti_patterns
        chars = data.get("characteristics", [])
        if chars:
            print(f"  [Characteristics]")
            for c in chars:
                print(f"    + {c}")
            print()

        anti = data.get("anti_patterns", [])
        if anti:
            print(f"  [Anti-patterns]")
            for a in anti:
                print(f"    - {a}")
            print()

    except Exception as e:
        print(f"[design-pick show] 오류: {e}", file=sys.stderr)

    return 0


def cmd_self(args) -> int:
    """
    의존성·정합 점검을 실행한다 (F007/F009/F010 self 모드 일관).

    점검 항목:
    - Python3 stdlib 사용 가능 (항상 통과 — 이 스크립트가 실행 중)
    - BRAND_CATALOG 4 brand 존재 + 필수 필드 보유
    - design 참조 파일 4종 존재 (.claude/design/references/ 또는 docs/design-references/)
    - tokens.json 유효성 (있다면 JSON 파싱 가능 + schema 필드 보유)
    - .claude/agents/designer.md 존재 (claude.gstack.auto.design 변형)

    Args:
        args: argparse Namespace

    Returns:
        int: 종료 코드 (--strict 시 BLOCK 있으면 1, 기본 0)
    """
    issues: list[dict] = []
    strict = getattr(args, "strict", False)
    fmt = getattr(args, "format", "human")

    def _add(label: str, target: str, msg: str) -> None:
        issues.append({"label": label, "target": target, "message": msg})

    try:
        # (1) BRAND_CATALOG 정합
        required_brands = {"apple", "claude", "spotify", "tesla"}
        missing_brands = required_brands - set(BRAND_CATALOG.keys())
        if missing_brands:
            _add(BLOCK, "BRAND_CATALOG", f"브랜드 미존재: {missing_brands}")
        else:
            _add(PASS_LABEL, "BRAND_CATALOG", f"4 브랜드 존재 ({', '.join(sorted(BRAND_CATALOG))})")

        required_fields = ["colors", "typography", "characteristics"]
        for brand in required_brands & set(BRAND_CATALOG.keys()):
            catalog = BRAND_CATALOG[brand]
            missing = [f for f in required_fields if not catalog.get(f)]
            if missing:
                _add(BLOCK, f"BRAND_CATALOG[{brand}]", f"필수 필드 미존재: {missing}")
            else:
                tc = _count_tokens(catalog)
                _add(
                    PASS_LABEL,
                    f"BRAND_CATALOG[{brand}]",
                    f"필수 필드 OK — colors={tc['colors']} typography={tc['typography']} chars={len(catalog.get('characteristics', []))}",
                )

        # (2) design 참조 파일 4종
        refs_dir = _find_refs_dir()
        ref_files = ["apple-design.md", "claude-design.md", "spotify-design.md", "tesla-design.md"]

        if refs_dir is None:
            _add(CONCERN, "refs_dir", "디자인 참조 디렉토리 미존재 (.claude/design/references/ 또는 docs/design-references/)")
        else:
            _add(PASS_LABEL, "refs_dir", f"디자인 참조 디렉토리 존재: {refs_dir}")
            for rf in ref_files:
                fpath = refs_dir / rf
                if fpath.exists():
                    _add(PASS_LABEL, f"refs/{rf}", f"존재 ({fpath.stat().st_size} bytes)")
                else:
                    _add(CONCERN, f"refs/{rf}", f"파일 미존재: {fpath}")

        # (3) tokens.json 유효성 (있다면)
        tokens_path = _tokens_path(args)
        if tokens_path.exists():
            try:
                with open(tokens_path, "r", encoding="utf-8") as f:
                    tdata = json.load(f)
                required_t = ["version", "brand", "colors", "typography"]
                missing_t = [k for k in required_t if k not in tdata]
                if missing_t:
                    _add(CONCERN, "tokens.json", f"필수 필드 누락: {missing_t}")
                else:
                    _add(
                        PASS_LABEL,
                        "tokens.json",
                        f"유효 — brand={tdata.get('brand')} version={tdata.get('version')}",
                    )
            except json.JSONDecodeError as e:
                _add(BLOCK, "tokens.json", f"JSON 파싱 실패: {e}")
        else:
            _add(INFO, "tokens.json", f"아직 생성 안 됨 (apply 실행 전) — {tokens_path}")

        # (4) designer.md 존재 여부 (claude.gstack.auto.design 변형 환경 감지)
        designer_md = _PROJECT_ROOT / ".claude" / "agents" / "designer.md"
        if designer_md.exists():
            _add(PASS_LABEL, "designer.md", f"존재: {designer_md}")
        else:
            _add(
                INFO,
                "designer.md",
                f"미존재 (claude.gstack.auto.design 변형에서만 사용) — {designer_md}",
            )

        # (5) design_pick.py 자체 실행 가능 여부 (shebang + chmod)
        self_path = Path(__file__).resolve()
        is_exec = os.access(str(self_path), os.X_OK)
        if is_exec:
            _add(PASS_LABEL, "design_pick.py", f"실행 권한 OK — {self_path}")
        else:
            _add(CONCERN, "design_pick.py", f"실행 권한 없음 (chmod +x 필요) — {self_path}")

    except Exception as e:
        _add(BLOCK, "self_check", f"점검 중 예외 발생: {e}")

    # 출력
    if fmt == "json":
        summary = {
            BLOCK: sum(1 for i in issues if i["label"] == BLOCK),
            CONCERN: sum(1 for i in issues if i["label"] == CONCERN),
            INFO: sum(1 for i in issues if i["label"] == INFO),
            PASS_LABEL: sum(1 for i in issues if i["label"] == PASS_LABEL),
        }
        print(json.dumps({"issues": issues, "summary": summary}, ensure_ascii=False, indent=2))
    else:
        print("=" * 72)
        print("  Design-Pick — self 점검")
        print("=" * 72)
        print()
        print(f"  {'#':<4} {'라벨':<8} {'항목':<36} {'메시지'}")
        print(f"  {'-'*4} {'-'*8} {'-'*36} {'-'*30}")
        for i, issue in enumerate(issues, 1):
            label = issue["label"]
            target = issue["target"]
            msg = issue["message"]
            # 긴 메시지 절삭
            if len(msg) > 55:
                msg = msg[:54] + "…"
            print(f"  {i:<4} {label:<8} {target:<36} {msg}")
        print()
        block_cnt = sum(1 for i in issues if i["label"] == BLOCK)
        concern_cnt = sum(1 for i in issues if i["label"] == CONCERN)
        info_cnt = sum(1 for i in issues if i["label"] == INFO)
        pass_cnt = sum(1 for i in issues if i["label"] == PASS_LABEL)
        print(
            f"  요약: {block_cnt} BLOCK, {concern_cnt} CONCERN,"
            f" {info_cnt} INFO, {pass_cnt} PASS"
        )
        print()

    block_count = sum(1 for i in issues if i["label"] == BLOCK)
    if strict and block_count > 0:
        return 1
    return 0


# ─── argparse + main ─────────────────────────────────────────────────────────


def _build_parser() -> argparse.ArgumentParser:
    """
    CLI 파서를 생성한다.

    Returns:
        argparse.ArgumentParser: 구성된 파서
    """
    parser = argparse.ArgumentParser(
        prog="design_pick.py",
        description="F011 — Design-Pick helper (4 brand token catalog)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
서브커맨드:
  compare              4 브랜드 비교표 (정적, LLM 호출 없음)
  recommend            designer 에이전트 호출 안내
  apply <brand>        brand 토큰을 tokens.json 으로 저장
  show                 현재 tokens.json 표시
  self                 의존성·정합 점검

예시:
  design_pick.py compare
  design_pick.py compare --format=json
  design_pick.py recommend
  design_pick.py apply apple
  design_pick.py apply claude --force
  design_pick.py show
  design_pick.py self --strict
""",
    )

    # 전역 옵션
    parser.add_argument(
        "--output",
        metavar="PATH",
        help="tokens.json 경로 override (기본: .claude/design/tokens.json)",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        default=False,
        help="BLOCK 1건이라도 있으면 exit 1 (기본: exit 0)",
    )
    parser.add_argument(
        "--format",
        choices=["human", "json"],
        default="human",
        dest="format",
        metavar="human|json",
        help="출력 포맷 (기본: human)",
    )
    # --format=json 형식 지원을 위해 add_argument 에서 = 로 전달 시 argparse 자동 처리됨
    parser.add_argument(
        "--force",
        action="store_true",
        default=False,
        help="apply 시 기존 tokens.json 백업 후 덮어쓰기",
    )

    subs = parser.add_subparsers(dest="subcmd", metavar="서브커맨드")

    # compare
    cmp_p = subs.add_parser("compare", help="4 브랜드 비교표 출력 (정적)")
    cmp_p.add_argument("--format", choices=["human", "json"], default=None, dest="subcmd_format", metavar="human|json")

    # recommend
    subs.add_parser("recommend", help="designer 에이전트 호출 안내")

    # apply
    apply_p = subs.add_parser("apply", help="brand 토큰을 tokens.json 으로 저장")
    apply_p.add_argument("brand", nargs="?", help="브랜드: apple | claude | spotify | tesla")
    apply_p.add_argument("--force", action="store_true", default=False, help="기존 tokens.json 백업 후 덮어쓰기")
    apply_p.add_argument("--output", metavar="PATH", help="tokens.json 경로 override")

    # show
    show_p = subs.add_parser("show", help="현재 tokens.json 표시")
    show_p.add_argument("--format", choices=["human", "json"], default=None, dest="subcmd_format", metavar="human|json")
    show_p.add_argument("--output", metavar="PATH", help="tokens.json 경로 override")

    # self
    self_p = subs.add_parser("self", help="의존성·정합 점검")
    self_p.add_argument("--strict", action="store_true", default=False, help="BLOCK 있으면 exit 1")
    self_p.add_argument("--format", choices=["human", "json"], default=None, dest="subcmd_format", metavar="human|json")

    return parser


def main() -> int:
    """
    진입점.

    Returns:
        int: 종료 코드
    """
    try:
        parser = _build_parser()
        args = parser.parse_args()

        subcmd = getattr(args, "subcmd", None)

        # 서브커맨드 전용 --format 이 전역보다 우선
        if hasattr(args, "subcmd_format") and args.subcmd_format is not None:
            args.format = args.subcmd_format

        if subcmd == "compare" or subcmd is None:
            return cmd_compare(args)
        elif subcmd == "recommend":
            return cmd_recommend(args)
        elif subcmd == "apply":
            return cmd_apply(args)
        elif subcmd == "show":
            return cmd_show(args)
        elif subcmd == "self":
            return cmd_self(args)
        else:
            parser.print_help()
            return 0

    except KeyboardInterrupt:
        print("\n[design-pick] 중단됨", file=sys.stderr)
        return 0
    except Exception as e:
        print(f"[design-pick] 예기치 못한 오류: {e}", file=sys.stderr)
        return 0


if __name__ == "__main__":
    sys.exit(main())
