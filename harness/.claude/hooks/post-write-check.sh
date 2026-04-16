#!/usr/bin/env bash
# .claude/hooks/post-write-check.sh
# PostToolUse(Write|Edit|MultiEdit) 훅 — 파일 작성 후 검증
#
# Claude Code stdin 구조 (PostToolUse):
# {
#   "tool_name": "Write",
#   "tool_input": { "file_path": "...", "content": "..." },
#   ...
# }
# 차단: exit 2 + stderr  /  허용: exit 0

INPUT=$(cat)

# tool_input.file_path 추출
if command -v python3 >/dev/null 2>&1; then
  FILE=$(echo "$INPUT" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    ti = d.get('tool_input', {})
    # Write: file_path / Edit: path 또는 file_path
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

# ── feature_list.json 항목 삭제 감지 ──────────────
if echo "$FILE" | grep -q "feature_list.json"; then
  if git show HEAD:feature_list.json >/dev/null 2>&1; then
    PREV_COUNT=$(git show HEAD:feature_list.json | python3 -c "
import sys, json
try: print(len(json.load(sys.stdin)))
except: print(0)
" 2>/dev/null || echo "0")

    CURR_COUNT=$(python3 -c "
import json
try: print(len(json.load(open('feature_list.json'))))
except: print(0)
" 2>/dev/null || echo "0")

    if [ "$CURR_COUNT" -lt "$PREV_COUNT" ]; then
      echo "🚫 [harness] feature_list.json 항목 삭제 감지!" >&2
      echo "   이전: ${PREV_COUNT}개 → 현재: ${CURR_COUNT}개" >&2
      echo "   feature_list.json 항목은 삭제 금지입니다. passes 필드만 수정하세요." >&2
      exit 2
    fi
  fi
fi

# ── .env 파일 직접 수정 경고 ──────────────────────
if echo "$FILE" | grep -qE "^\.env$|/\.env$"; then
  echo "⚠️  [harness] .env 파일이 수정되었습니다." >&2
  echo "   시크릿 값이 git에 커밋되지 않도록 주의하세요." >&2
  # 경고만, 차단은 안 함 (exit 0)
fi

exit 0
