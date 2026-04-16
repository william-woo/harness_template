#!/usr/bin/env bash
# .claude/hooks/session-end.sh
# Stop 훅 — 세션 종료 시 미커밋 변경사항 경고

UNCOMMITTED=$(git status --porcelain 2>/dev/null | wc -l | tr -d ' ')

if [ "$UNCOMMITTED" -gt "0" ]; then
  echo "" >&2
  echo "⚠️  [harness] 세션 종료 전 체크리스트:" >&2
  echo "   - 미커밋 변경사항 ${UNCOMMITTED}개 존재" >&2
  echo "   - /project:handoff 실행을 권장합니다" >&2
  echo "   - 최소한 wip 커밋: git commit -am 'wip: 작업 내용'" >&2
fi

# Stop 훅은 exit 0으로 종료 허용, exit 2로 종료 차단 가능
# 미커밋이 있어도 강제 차단하지 않음 (경고만)
exit 0
