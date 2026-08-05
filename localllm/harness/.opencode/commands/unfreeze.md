---
description: "편집 경계 해제"
---

# /unfreeze — 편집 경계 해제

`/freeze`로 설정한 디렉토리 제한을 제거한다.

## 사용 방법

```
/unfreeze
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

---

사용자 인자 (없으면 무시): $ARGUMENTS

---

> **로컬 LLM 실행 힌트**: 이 커맨드의 동작은 위 문서의 bash 명령을 **그대로 실행**하는 것이다. 문서에 `python3 .claude/bin/...` 또는 bash 블록이 있으면 추측·재해석하지 말고 그 명령을 bash 도구로 즉시 실행하고, 그 출력을 요약해 보고하라. bash 도구 호출 시 `command` 와 `description` **두 인자를 모두** 채워라 (description 누락 = 스키마 에러). 파일이 없거나 실패하면 문서의 안내 문구를 따르고 사용자에게 질문하지 마라.
