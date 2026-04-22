#!/usr/bin/env bash
# .codex/scripts/session-end.sh
# 세션 종료(= /handoff 실행) 전에 에이전트가 호출하는 점검 스크립트.
# Codex CLI에는 Stop 훅이 없으므로 `/handoff` 프롬프트가 이 스크립트를 직접 호출합니다.
#
# 사용법:
#   bash .codex/scripts/session-end.sh
#
# 반환:
#   - 미커밋 변경 있음: exit 1 + stderr 경고 (차단 아님, 에이전트가 안내)
#   - 깨끗함:           exit 0

set -eo pipefail

UNCOMMITTED=$(git status --porcelain 2>/dev/null | wc -l | tr -d ' ')

if [ "$UNCOMMITTED" -gt 0 ]; then
  echo "" >&2
  echo "⚠️  [harness] 세션 종료 전 체크리스트:" >&2
  echo "   - 미커밋 변경사항 ${UNCOMMITTED}개 존재" >&2
  echo "   - /handoff 프롬프트를 계속 진행하세요" >&2
  echo "   - 최소한 wip 커밋 권장: git commit -am 'wip(FXXX): 작업 내용'" >&2
  echo "" >&2

  echo "── git status --short ──" >&2
  git status --short >&2 2>/dev/null || true
  echo "────────────────────────" >&2

  exit 1
fi

echo "✅ [harness] 미커밋 변경 없음 — 세션 종료 OK"
exit 0
