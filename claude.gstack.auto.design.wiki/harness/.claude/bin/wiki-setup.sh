#!/usr/bin/env bash
# wiki-setup.sh — LLM Wiki 외부 도구 설치 (claude.gstack.auto.design.wiki 변형 전용)
#
# ADR-007 결정 6 B: 최초 1회 사용자 승인 후 자동 설치.
# autonomous 모드의 pre-bash-auto-boundary-check.sh 가 설치 명령을 ESCALATE →
# 사용자 승인 → 그 세션 내 자동 설치. 거부/실패/비대화 → graceful degrade.
#
# 설치 대상:
#   - qmd: 로컬 markdown 검색엔진 (BM25/vector) — cargo install
#   - marp-cli: 슬라이드 생성 — npm install -g
#   - Obsidian: GUI 앱 — CLI 자동설치 불가, 다운로드 링크 안내만
#
# 설계 원칙 (ADR-007):
#   - 도구 없거나 설치 실패해도 graceful — exit 0
#   - cargo/npm install -g 는 autonomous 모드 boundary 훅이 ESCALATE (3-B)
#   - 이 스크립트는 ESCALATE 메시지 없이 설치 명령을 실행하면 안 됨 (보안)
#     → 명령 실행 전 echo 로 무엇을 왜 설치하는지 명시
#   - 1회 사용자 승인은 세션 내 유지 (캐시 파일 불필요 — autonomous 정책 준수)
#   - cargo/npm 미설치 시 설치 스킵 (연쇄 의존성 자동 설치 금지)
#
# 사용법:
#   bash .claude/bin/wiki-setup.sh
#   또는: bash <project-root>/.claude/bin/wiki-setup.sh

set -u

echo "=== LLM Wiki 외부 도구 설치 ==="
echo ""
echo "이 스크립트는 다음 외부 도구를 설치합니다 (선택적 — 미설치 시 graceful degrade):"
echo "  1. qmd       — vault 검색 향상 (BM25/vector). 없으면 stdlib grep fallback."
echo "  2. marp-cli  — wiki .md → 슬라이드. 없으면 .md 직접 제공."
echo "  3. Obsidian  — graph view (GUI, 수동 설치 안내만)."
echo ""
echo "  [autonomous 모드 안내]"
echo "  cargo install / npm install -g 는 외부 패키지 설치로 boundary 훅이 ESCALATE 합니다."
echo "  사용자가 1회 승인하면 이 세션 내에서 자동 진행됩니다 (ADR-007 결정 6 B)."
echo ""

# ── qmd 설치 ──────────────────────────────────────────────────────────────────
if command -v qmd >/dev/null 2>&1; then
    echo "[qmd] 이미 설치됨 ($(command -v qmd)) — 스킵"
else
    echo "[qmd] 미설치 감지."
    if command -v cargo >/dev/null 2>&1; then
        echo "[qmd] 설치 시도: cargo install qmd"
        echo "      cargo 는 Rust 패키지 관리자. qmd 는 로컬 Markdown BM25/vector 검색엔진."
        echo "      출처: https://github.com/tobi/qmd"
        if cargo install qmd; then
            echo "[qmd] 설치 성공 — wiki.py query 가 BM25/vector 검색 모드로 전환됩니다."
        else
            echo "[WARN][qmd] 설치 실패 — stdlib grep fallback 유지 (wiki 기능 정상)."
            echo "            수동 설치: cargo install qmd"
        fi
    else
        echo "[WARN][qmd] cargo 미설치 — qmd 스킵."
        echo "       qmd 수동 설치: https://github.com/tobi/qmd"
        echo "       Rust/cargo 설치: https://rustup.rs"
    fi
fi

echo ""

# ── marp-cli 설치 ─────────────────────────────────────────────────────────────
if command -v marp >/dev/null 2>&1; then
    echo "[marp] 이미 설치됨 ($(command -v marp)) — 스킵"
else
    echo "[marp] 미설치 감지."
    if command -v npm >/dev/null 2>&1; then
        echo "[marp] 설치 시도: npm install -g @marp-team/marp-cli"
        echo "       npm -g 는 글로벌 패키지 설치 (시스템 node_modules 또는 ~/.npm-global)."
        echo "       출처: https://github.com/marp-team/marp-cli"
        if npm install -g @marp-team/marp-cli; then
            echo "[marp] 설치 성공 — wiki .md → 슬라이드 변환 가능."
        else
            echo "[WARN][marp] 설치 실패 — 슬라이드 기능 비활성 (wiki 기능 정상)."
            echo "             수동 설치: npm install -g @marp-team/marp-cli"
        fi
    else
        echo "[WARN][marp] npm 미설치 — marp 스킵."
        echo "       npm 설치: https://nodejs.org"
    fi
fi

echo ""

# ── Obsidian 안내 (GUI 앱 — 자동 설치 불가) ───────────────────────────────────
if command -v obsidian >/dev/null 2>&1; then
    echo "[Obsidian] CLI 감지됨 ($(command -v obsidian))"
else
    echo "[Obsidian] GUI 앱이라 자동 설치 불가 — 수동 설치 안내:"
    echo "  다운로드: https://obsidian.md/download"
    echo "  설치 후 wiki/ 디렉토리를 vault 로 열기."
    echo "  graph view 로 [[wikilink]] 기반 지식 그래프 시각화 가능."
fi

echo ""
echo "=== 설치 완료 ==="
echo "  wiki.py self 로 현재 상태 확인: python3 .claude/bin/wiki.py self"
echo "  ingest 실행: python3 .claude/bin/wiki.py ingest"
echo ""
exit 0
