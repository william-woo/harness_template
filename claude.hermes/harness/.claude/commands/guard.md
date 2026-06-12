# /project:guard — 최대 안전 모드

`/project:freeze` (편집 경계) + 기본 탑재된 `pre-bash-check.sh` (파괴 명령 차단)를 **모두 활성화**한 상태로 만든다.

현재 하네스에서 파괴 명령 차단(`rm -rf`, `DROP TABLE`, `git push --force` 등)은 항상 켜져 있으므로, `/project:guard`의 핵심 기능은 **편집 경계 설정**이다. 이름이 따로 있는 이유는 "프로덕션 건드릴 때 명시적으로 최대 보호 모드를 켠다"는 의도를 표현하기 위함.

## 언제 쓰나

- 프로덕션 환경 디버깅 중
- 라이브 시스템·공유 인프라 조작 중
- 심볼릭 리팩토링 범위가 한 디렉토리로 제한되어야 할 때

## 사용 방법

```
/project:guard
```

AskUserQuestion으로 편집 허용 디렉토리를 묻는다.
받은 경로로 `/project:freeze`와 동일한 절차 실행 후 요약 출력:

```bash
FREEZE_DIR=$(cd "<사용자-입력-경로>" 2>/dev/null && pwd)
if [ -z "$FREEZE_DIR" ]; then
  echo "❌ 존재하지 않는 경로"
  exit 1
fi
mkdir -p "$CLAUDE_PROJECT_DIR/.claude/state"
echo "$FREEZE_DIR" > "$CLAUDE_PROJECT_DIR/.claude/state/freeze-dir.txt"

cat <<EOF
🛡️  [harness/guard] 최대 안전 모드 활성화

  1. 파괴 명령 차단 (항상 켜져 있음)
     rm -rf /, DROP TABLE, git push --force, kubectl delete, docker system prune 등
  2. 편집 경계: $FREEZE_DIR
     이 밖의 Edit/Write는 차단됨

  해제: /project:unfreeze (편집 경계만 해제)
  파괴 명령 차단은 세션 내내 유지
EOF
```

## 해제

```
/project:unfreeze
```

편집 경계만 해제된다. 파괴 명령 차단은 하네스 훅의 기본 동작이라 세션 종료 전까지 계속 작동.
