#!/usr/bin/env bash
# .claude/hooks/pre-bash-check.sh
# PreToolUse(Bash) 훅 — 위험한 명령어 실행 전 차단
#
# Claude Code stdin 구조:
# {
#   "hook_event_name": "PreToolUse",
#   "tool_name": "Bash",
#   "tool_input": { "command": "..." },
#   ...
# }
# 차단: exit 2 + stderr 메시지 → Claude가 메시지를 읽고 수정함
# 허용: exit 0

INPUT=$(cat)

# tool_input.command 추출 (python3 우선, jq fallback)
if command -v python3 >/dev/null 2>&1; then
  CMD=$(echo "$INPUT" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    print(d.get('tool_input', {}).get('command', ''))
except Exception:
    print('')
")
elif command -v jq >/dev/null 2>&1; then
  CMD=$(echo "$INPUT" | jq -r '.tool_input.command // ""')
else
  exit 0
fi

[ -z "$CMD" ] && exit 0

# ── 위험 명령어 패턴 차단 ──────────────────────────
DANGEROUS_PATTERNS=(
  "rm -rf /"
  "rm -rf ~"
  "rm -rf \$HOME"
  "DROP TABLE"
  "DROP DATABASE"
  "> /dev/sda"
  "mkfs"
  "dd if=/dev/zero"
  "dd if=/dev/urandom"
  "chmod -R 777 /"
  "curl.*\| *bash"
  "wget.*\| *bash"
)

for pattern in "${DANGEROUS_PATTERNS[@]}"; do
  if echo "$CMD" | grep -qE "$pattern"; then
    echo "🚫 [harness] 위험한 명령어 차단: '$pattern' 감지" >&2
    echo "   명령어: $CMD" >&2
    exit 2
  fi
done

# ── main/master 브랜치 직접 커밋 방지 ─────────────
if echo "$CMD" | grep -q "git commit"; then
  CURRENT_BRANCH=$(git branch --show-current 2>/dev/null || echo "")
  if [ "$CURRENT_BRANCH" = "main" ] || [ "$CURRENT_BRANCH" = "master" ]; then
    echo "🚫 [harness] main/master 직접 커밋 차단" >&2
    echo "   feature 브랜치 생성 후 커밋하세요: git checkout -b feature/FXXX-기능명" >&2
    exit 2
  fi
fi

# ── git push --force 차단 ─────────────────────────
if echo "$CMD" | grep -qE "git push.*(--force|-f)"; then
  echo "🚫 [harness] git push --force 차단" >&2
  echo "   강제 푸시는 팀 협업에 위험합니다. 팀원 협의 후 진행하세요." >&2
  exit 2
fi

exit 0
