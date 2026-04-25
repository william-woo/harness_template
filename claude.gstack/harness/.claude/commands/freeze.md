# /project:freeze — 편집 경계 설정

지정한 디렉토리 **안쪽**에서만 Edit/Write가 허용되도록 세션 경계를 설정한다.
대규모 리팩토링 중 범위 밖 파일이 실수로 수정되는 사고를 막는 데 쓴다.

## 언제 쓰나

- 여러 개의 Feature가 맞물려 있어 AI가 "관련 없는 코드까지 고치려" 할 때
- 한 모듈만 수정해야 하는 작은 수정 작업
- 샌드박스로 제한된 실험적 변경

## 사용 방법

```
/project:freeze
```

사용자에게 AskUserQuestion으로 제한할 디렉토리 경로를 묻는다(텍스트 입력).
예: `src/auth` 또는 `/home/obigo/project/.../src/auth`

받은 경로를 처리한다:

```bash
# 사용자가 입력한 경로를 절대경로로 해석
FREEZE_DIR=$(cd "<사용자-입력-경로>" 2>/dev/null && pwd)
if [ -z "$FREEZE_DIR" ]; then
  echo "❌ 존재하지 않는 경로"
  exit 1
fi

# 상태 파일에 저장 (프로젝트 로컬, .gitignore 처리됨)
mkdir -p "$CLAUDE_PROJECT_DIR/.claude/state"
echo "$FREEZE_DIR" > "$CLAUDE_PROJECT_DIR/.claude/state/freeze-dir.txt"
echo "✅ freeze 경계 설정: $FREEZE_DIR"
```

## 동작 원리

- `.claude/hooks/pre-edit-freeze-check.sh` 훅이 모든 Edit/Write/MultiEdit 호출 전 경로를 검사
- `file_path`가 `FREEZE_DIR` 밖이면 `exit 2`로 차단 + stderr 메시지
- Read, Bash, Glob, Grep은 영향 받지 않음 (읽기·탐색은 자유)

## 주의

- **Bash로 sed/awk를 쓰면 우회 가능** — 이건 "실수 방지"용 가드레일이지 보안 경계가 아님
- 세션 종료 시 수동으로 `/project:unfreeze` 실행하거나 파일을 삭제해야 해제됨
- 한 번 더 실행하면 경계를 재설정한다

## 해제

```
/project:unfreeze
```

또는 파일 직접 삭제:

```bash
rm "$CLAUDE_PROJECT_DIR/.claude/state/freeze-dir.txt"
```
