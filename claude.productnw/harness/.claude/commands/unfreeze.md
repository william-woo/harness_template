# /project:unfreeze — 편집 경계 해제

`/project:freeze`로 설정한 디렉토리 제한을 제거한다.

## 사용 방법

```
/project:unfreeze
```

## 동작

```bash
FREEZE_FILE="$CLAUDE_PROJECT_DIR/.claude/state/freeze-dir.txt"
if [ -f "$FREEZE_FILE" ]; then
  PREV=$(cat "$FREEZE_FILE")
  rm -f "$FREEZE_FILE"
  echo "✅ freeze 경계 해제됨 (이전: $PREV)"
  echo "   모든 디렉토리 Edit/Write 가능"
else
  echo "ℹ️  설정된 freeze 경계가 없음"
fi
```

해제 후 같은 세션 내에서도 즉시 효과 발생 (훅이 매 호출마다 파일을 읽음).
