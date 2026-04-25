#!/usr/bin/env bash
# .claude/hooks/pre-write-check.sh
# PreToolUse(Write|Edit|MultiEdit) 훅 — 민감 파일 보호
#
# Claude Code stdin 구조:
# { "tool_input": { "file_path": "...", ... }, ... }

set -eo pipefail

INPUT=$(cat)

if command -v python3 >/dev/null 2>&1; then
  FILE=$(echo "$INPUT" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    ti = d.get('tool_input', {})
    print(ti.get('file_path') or ti.get('path') or '')
except Exception:
    print('')
")
elif command -v jq >/dev/null 2>&1; then
  FILE=$(echo "$INPUT" | jq -r '(.tool_input.file_path // .tool_input.path) // ""')
else
  exit 0
fi

[ -z "$FILE" ] && exit 0

# ── 절대 수정 금지 파일 ────────────────────────────
PROTECTED_FILES=(
  ".claude/settings.json"
  ".gitignore"
)

for protected in "${PROTECTED_FILES[@]}"; do
  if echo "$FILE" | grep -q "$protected"; then
    echo "⚠️  [harness] 보호 파일 수정: $FILE" >&2
    echo "   하네스 핵심 파일은 의도적 변경인지 확인하세요." >&2
    # 차단하지 않고 경고만 (팀이 필요시 수정할 수 있어야 함)
  fi
done

exit 0
