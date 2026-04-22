#!/usr/bin/env bash
# .codex/scripts/pre-write-check.sh
# 민감/보호 파일을 쓰기 전에 에이전트가 호출하는 경고 스크립트.
# Codex CLI는 PreToolUse 훅이 없으므로, 에이전트가 직접 호출해야 합니다.
#
# 사용법:
#   bash .codex/scripts/pre-write-check.sh <파일경로>
#
# 예:
#   bash .codex/scripts/pre-write-check.sh .env
#   bash .codex/scripts/pre-write-check.sh .codex/config.toml
#
# 반환:
#   - 보호 파일: exit 1 + stderr 경고 (차단하지는 않음, 사용자 승인 필요)
#   - 일반 파일: exit 0

set -eo pipefail

FILE="${1:-}"
if [ -z "$FILE" ]; then
  echo "⚠️  [harness] pre-write-check.sh에 파일 경로 인자가 필요합니다." >&2
  exit 1
fi

# ── 절대 수정 금지 / 경고 대상 파일 ────────────────────
# Codex CLI에서 이 목록 파일을 수정하려면 사용자에게 명시적 승인을 받아야 합니다.
PROTECTED_FILES=(
  ".codex/config.toml"
  ".codex/scripts/"
  "AGENTS.md"
  ".gitignore"
)

HIT=0
for protected in "${PROTECTED_FILES[@]}"; do
  if [[ "$FILE" == *"$protected"* ]]; then
    echo "⚠️  [harness] 보호 파일 수정 시도: $FILE" >&2
    echo "   이유: 하네스 핵심 파일 (패턴: $protected)" >&2
    echo "   에이전트는 반드시 사용자에게 변경 이유를 설명하고 승인을 받은 뒤 진행하세요." >&2
    HIT=1
  fi
done

# .env 계열 — 시크릿 노출 위험
if [[ "$FILE" =~ (^|/)\.env(\.[^/]+)?$ ]]; then
  echo "🔐 [harness] .env 파일 수정: $FILE" >&2
  echo "   실제 시크릿 값이 들어간다면 .gitignore에 포함되어 있는지 반드시 확인하세요." >&2
  HIT=1
fi

# feature_list.json 편집 시 사후 검증 리마인드
if [[ "$FILE" == *"feature_list.json" ]]; then
  echo "ℹ️  [harness] feature_list.json 편집 직후 반드시:" >&2
  echo "     bash .codex/scripts/post-write-check.sh" >&2
fi

if [ "$HIT" -eq 1 ]; then
  # exit 1: 경고 신호 (차단 아님). 에이전트는 사용자 승인 후 write 진행.
  exit 1
fi

exit 0
