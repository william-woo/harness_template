#!/usr/bin/env bash
# .claude/hooks/pre-edit-freeze-check.sh
# PreToolUse(Write|Edit|MultiEdit) 훅 — freeze 경계 검증
#
# /project:freeze 또는 /project:guard 로 활성화되면
# .claude/state/freeze-dir.txt 에 저장된 디렉토리 밖의 Edit/Write는 차단한다.
#
# 차단: exit 2 + stderr 메시지
# 허용: exit 0

set -eo pipefail

# 프로젝트 루트 결정 (훅 실행 컨텍스트에서 CLAUDE_PROJECT_DIR 사용 가능)
PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$(pwd)}"
FREEZE_FILE="$PROJECT_DIR/.claude/state/freeze-dir.txt"

# freeze 비활성 → 통과
if [ ! -f "$FREEZE_FILE" ]; then
  exit 0
fi

# freeze 디렉토리 읽기 (공백 제거, 빈 값이면 통과)
FREEZE_DIR=$(tr -d '[:space:]' < "$FREEZE_FILE" 2>/dev/null || echo "")
if [ -z "$FREEZE_DIR" ]; then
  exit 0
fi

# tool_input.file_path 추출
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

# 파일 경로 추출 실패 시 통과 (파싱 실패로 차단하지 않음)
[ -z "$FILE" ] && exit 0

# 상대경로를 절대경로로 변환
case "$FILE" in
  /*) ;;                                 # 이미 절대
  *)  FILE="$PROJECT_DIR/$FILE" ;;
esac

# 경로 정규화: 연속 슬래시 제거, 트레일링 슬래시 제거
FILE=$(echo "$FILE" | sed 's|/\+|/|g;s|/$||')
FREEZE_DIR=$(echo "$FREEZE_DIR" | sed 's|/\+|/|g;s|/$||')

# freeze 경계 검사: FILE이 FREEZE_DIR 로 시작하는가?
case "$FILE" in
  "$FREEZE_DIR"/*|"$FREEZE_DIR")
    exit 0  # 경계 내 → 통과
    ;;
  *)
    echo "🚫 [harness/freeze] 경계 밖 Edit/Write 차단" >&2
    echo "   대상 파일: $FILE" >&2
    echo "   freeze 경계: $FREEZE_DIR" >&2
    echo "   경계를 풀려면: /project:unfreeze" >&2
    exit 2
    ;;
esac
