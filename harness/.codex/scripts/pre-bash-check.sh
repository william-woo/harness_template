#!/usr/bin/env bash
# .codex/scripts/pre-bash-check.sh
# Codex CLI에는 PreToolUse 훅이 없으므로 에이전트가 직접 호출하는 검증 스크립트.
#
# 사용법:
#   bash .codex/scripts/pre-bash-check.sh '<실행할 명령 전체>'
#
# 예:
#   bash .codex/scripts/pre-bash-check.sh 'git reset --hard HEAD~1'
#
# 반환:
#   - 위험 패턴 감지: exit 2 + stderr 메시지  → 에이전트는 즉시 명령 실행을 중단하고 사용자에게 보고
#   - 안전:             exit 0

set -eo pipefail

CMD="${1:-}"
if [ -z "$CMD" ]; then
  echo "⚠️  [harness] pre-bash-check.sh에 명령 인자가 필요합니다." >&2
  echo "     예: bash .codex/scripts/pre-bash-check.sh 'git push --force'" >&2
  exit 2
fi

# 공백 정규화: 연속 공백/탭을 단일 공백으로, 앞뒤 공백 제거
NORMALIZED=$(printf '%s' "$CMD" | tr -s ' \t' ' ' | sed 's/^ *//;s/ *$//')

# ── 위험 명령어 패턴 차단 (ERE 정규식) ────────────────
DANGEROUS_PATTERNS=(
  # rm 변형: -rf / -fr / -Rf / 다양한 플래그 조합
  'rm[[:space:]]+(-[-a-zA-Z]*[rRfF][-a-zA-Z]*[[:space:]]+)+/([[:space:]]|$|\*)'
  'rm[[:space:]]+(-[-a-zA-Z]*[rRfF][-a-zA-Z]*[[:space:]]+)+(~|\$HOME|\$\{HOME\})'
  'rm[[:space:]]+(-[-a-zA-Z]*[rRfF][-a-zA-Z]*[[:space:]]+)+/\*'
  'sudo[[:space:]]+rm[[:space:]]+-[-a-zA-Z]*[rRfF]'
  # 파일시스템/디스크 파괴
  '(^|[[:space:];|&])mkfs\.'
  'dd[[:space:]]+if=/dev/(zero|urandom|random)[[:space:]]+of=/dev/'
  '>[[:space:]]*/dev/sd[a-z]'
  # DB 파괴
  '(^|[[:space:];])(DROP|TRUNCATE)[[:space:]]+(TABLE|DATABASE|SCHEMA)'
  # 권한 파괴
  'chmod[[:space:]]+-R[[:space:]]+777[[:space:]]+/'
  # 원격 스크립트 실행 (curl/wget | bash)
  '(curl|wget)[^|]*\|[[:space:]]*(sudo[[:space:]]+)?(bash|sh|zsh|fish)'
  # 시스템 종료/재부팅
  '(^|[[:space:];|&])(shutdown|reboot|halt|poweroff)([[:space:]]|$)'
  # 전체 프로세스 종료
  'kill[[:space:]]+-9?[[:space:]]+-1([[:space:]]|$)'
  # git 파괴적 명령
  'git[[:space:]]+reset[[:space:]]+--hard'
  'git[[:space:]]+clean[[:space:]]+-[a-zA-Z]*[fdx][a-zA-Z]*'
  'git[[:space:]]+checkout[[:space:]]+--[[:space:]]+\.'
  'git[[:space:]]+branch[[:space:]]+-D'
  'git[[:space:]]+update-ref[[:space:]]+-d'
)

for pattern in "${DANGEROUS_PATTERNS[@]}"; do
  if printf '%s' "$NORMALIZED" | grep -qE "$pattern"; then
    echo "🚫 [harness] 위험한 명령어 감지 — 실행 중단" >&2
    echo "   패턴: $pattern" >&2
    echo "   명령: $CMD" >&2
    echo "   에이전트는 이 명령 실행을 멈추고, 사용자에게 대안을 제안해야 합니다." >&2
    echo "   정말 필요하면 팀 합의 후 .codex/scripts/pre-bash-check.sh를 수정하세요." >&2
    exit 2
  fi
done

# ── main/master 브랜치 직접 커밋 방지 ────────────────
if printf '%s' "$NORMALIZED" | grep -qE '(^|[[:space:];|&])git[[:space:]]+commit([[:space:]]|$)'; then
  CURRENT_BRANCH=$(git branch --show-current 2>/dev/null || echo "")
  if [ "$CURRENT_BRANCH" = "main" ] || [ "$CURRENT_BRANCH" = "master" ]; then
    echo "🚫 [harness] main/master 직접 커밋 차단" >&2
    echo "   feature 브랜치 생성 후 커밋하세요: git checkout -b feature/FXXX-기능명" >&2
    exit 2
  fi
fi

# ── git push --force 차단 ─────────────────────────────
if printf '%s' "$NORMALIZED" | grep -qE 'git[[:space:]]+push[[:space:]].*(--force([[:space:]]|=|$)|[[:space:]]-f([[:space:]]|$))'; then
  echo "🚫 [harness] git push --force 차단" >&2
  echo "   강제 푸시는 팀 협업에 위험합니다. --force-with-lease도 팀 합의 후 사용." >&2
  exit 2
fi

exit 0
