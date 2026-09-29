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

set -eo pipefail

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

if [ -z "$CMD" ]; then
  exit 0
fi

# 공백 정규화: 연속 공백/탭을 단일 공백으로, 앞뒤 공백 제거
NORMALIZED=$(echo "$CMD" | tr -s ' \t' ' ' | sed 's/^ *//;s/ *$//')
NORMALIZED_LOWER=$(echo "$NORMALIZED" | tr '[:upper:]' '[:lower:]')

# ── Safe exceptions ──────────────────────────────────
# 개발 중 정상적으로 지우는 빌드 산출물·캐시는 통과
# (정규식: rm -r[f] <safe-target> 만 있는 경우)
SAFE_RM_TARGETS='(node_modules|\.next|dist|build|coverage|__pycache__|\.cache|\.turbo|\.nyc_output|htmlcov|out|\.venv|venv)'
if echo "$NORMALIZED" | grep -qE "^(sudo[[:space:]]+)?rm[[:space:]]+-[-a-zA-Z]*[rRfF][-a-zA-Z]*[[:space:]]+([^/[:space:]]*/)?$SAFE_RM_TARGETS/?([[:space:]]|$)"; then
  # 안전한 빌드 산출물 삭제 → 통과
  :
else
  # ── 위험 명령어 패턴 차단 (ERE 정규식) ────────────────
  # 플래그 순서 변형, 공백 변형, sudo 변형 모두 커버
  DANGEROUS_PATTERNS=(
    # rm 변형: -rf / -fr / -Rf / 다양한 플래그 조합 (루트/홈 파괴)
    'rm[[:space:]]+(-[-a-zA-Z]*[rRfF][-a-zA-Z]*[[:space:]]+)+/([[:space:]]|$|\*)'
    'rm[[:space:]]+(-[-a-zA-Z]*[rRfF][-a-zA-Z]*[[:space:]]+)+(~|\$HOME|\$\{HOME\})'
    'rm[[:space:]]+(-[-a-zA-Z]*[rRfF][-a-zA-Z]*[[:space:]]+)+/\*'
    'sudo[[:space:]]+rm[[:space:]]+-[-a-zA-Z]*[rRfF]'
    # 파일시스템/디스크 파괴
    '(^|[[:space:];|&])mkfs\.'
    'dd[[:space:]]+if=/dev/(zero|urandom|random)[[:space:]]+of=/dev/'
    '>[[:space:]]*/dev/sd[a-z]'
    # DB 파괴 (따옴표·괄호로 감싼 쿼리도 잡아야 함)
    '\b(drop|truncate)[[:space:]]+(table|database|schema)'
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
    'git[[:space:]]+checkout[[:space:]]+\.([[:space:]]|$)'
    'git[[:space:]]+restore[[:space:]]+\.([[:space:]]|$)'
    'git[[:space:]]+branch[[:space:]]+-D'
    'git[[:space:]]+update-ref[[:space:]]+-d'
    # Kubernetes 파괴 (네임스페이스/디플로이먼트 삭제)
    'kubectl[[:space:]]+delete[[:space:]]+(ns|namespace|deployment|deploy|all)'
    # Docker 파괴 (강제 제거/prune -a/볼륨)
    'docker[[:space:]]+rm[[:space:]]+-[a-zA-Z]*f'
    'docker[[:space:]]+system[[:space:]]+prune'
    'docker[[:space:]]+volume[[:space:]]+prune'
    'docker[[:space:]]+image[[:space:]]+prune[[:space:]]+.*-a'
  )

  for pattern in "${DANGEROUS_PATTERNS[@]}"; do
    # SQL 패턴은 소문자 비교, 나머지는 원본 비교
    case "$pattern" in
      *"(drop|truncate)"*) TARGET="$NORMALIZED_LOWER" ;;
      *) TARGET="$NORMALIZED" ;;
    esac
    if echo "$TARGET" | grep -qE "$pattern"; then
      echo "🚫 [harness] 위험한 명령어 차단" >&2
      echo "   패턴: $pattern" >&2
      echo "   명령어: $CMD" >&2
      echo "   필요하면 팀 합의 후 .claude/hooks/pre-bash-check.sh를 수정하세요." >&2
      exit 2
    fi
  done
fi

# ── main/master 브랜치 직접 커밋 방지 ────────────────
# 단, 초기 커밋(아직 HEAD 없음)은 허용 — repo 초기 셋업 시 필요
#
# 두 가지를 정확히 정해야 한다: **정말 커밋인가**, 그리고 **어느 저장소인가**.
#
#  · 어느 저장소인가 — 예전에는 훅의 cwd 에서 브랜치를 읽었다. 그러나 명령은
#    `cd src/harness_template && git commit …` 처럼 다른 저장소로 옮겨가서 커밋할 수
#    있고, 이 리포에는 실제로 중첩 저장소가 있다. cwd 기준 판정은 두 방향으로 틀린다:
#      미탐 — 바깥이 feature 브랜치면 안쪽 main 직접 커밋이 통과한다
#      오탐 — 바깥이 main 이면 안쪽 feature 브랜치 커밋이 막힌다
#  · 정말 커밋인가 — 좁은 정규식 `git[[:space:]]+commit` 은 `git -C <path> commit`,
#    `git -c k=v commit`, `git --no-pager commit` 을 **통째로 놓친다**(실측). 전역
#    옵션이 끼면 차단 블록 자체가 돌지 않았다.
#
# 그래서 게이트는 넓게 잡고, 판정은 python 이 토큰 단위로 한다 (따옴표·전역 옵션·
# cd 체인을 다 따라간다). python 이 없으면(jq 폴백) 좁은 정규식 + cwd 라는 예전
# 판정으로 물러난다 — 기능을 잃되 거짓 차단을 만들지는 않는다.
COMMIT_REPO=""
if echo "$NORMALIZED" | grep -qE '(^|[[:space:];|&(])git([[:space:]]|$)' \
   && echo "$NORMALIZED" | grep -qE '(^|[[:space:]])commit([[:space:]]|$)'; then
  if command -v python3 >/dev/null 2>&1; then
    COMMIT_REPO=$(CMD_FOR_DIR="$CMD" python3 - <<'PYEOF' 2>/dev/null
import os, re, shlex

cmd = os.environ.get("CMD_FOR_DIR", "")
cwd = os.getcwd()

# 값을 따로 받는 git 전역 옵션 — 서브커맨드를 찾으려면 인자까지 건너뛰어야 한다.
VALUED = {"-C", "-c", "--git-dir", "--work-tree", "--exec-path", "--namespace"}


def resolve(base, path):
    """상대경로를 현재 추적 중인 디렉토리 기준으로 절대화한다."""
    path = os.path.expanduser(path)
    return path if os.path.isabs(path) else os.path.normpath(os.path.join(base, path))


cur, target = cwd, None
# 연결자 기준으로 쪼갠다. 파이프(|)는 cd 를 이어받지 않으므로 분리자에 넣지 않는다.
for seg in re.split(r"&&|\|\||;|\n", cmd):
    s = seg.strip().lstrip("({").strip()
    if not s:
        continue
    try:
        toks = shlex.split(s)
    except ValueError:      # 따옴표가 안 닫힌 조각 — 추측하지 않고 넘어간다
        continue
    if not toks:
        continue

    if toks[0] == "cd":
        # `cd -` 나 인자 없는 `cd` 는 목적지를 알 수 없다 — 직전 디렉토리를 유지한다
        if len(toks) > 1 and toks[1] != "-":
            cur = resolve(cur, toks[1])
        continue

    # `FOO=1 git …` 처럼 환경변수가 앞설 수 있고, 절대경로로 부를 수도 있다
    gi = next((i for i, t in enumerate(toks) if os.path.basename(t) == "git"), None)
    if gi is None:
        continue
    j, repo = gi + 1, cur
    while j < len(toks) and toks[j].startswith("-"):
        if toks[j] in VALUED and j + 1 < len(toks):
            if toks[j] == "-C":
                repo = resolve(repo, toks[j + 1])
            j += 2
        else:
            j += 1
    if j < len(toks) and toks[j] == "commit":
        target = repo
        break

# 커밋이 아니면 아무것도 출력하지 않는다 — 호출측이 검사를 건너뛴다
if target is not None:
    print(target)
PYEOF
) || COMMIT_REPO=""
  elif echo "$NORMALIZED" | grep -qE '(^|[[:space:];|&])git[[:space:]]+commit([[:space:]]|$)'; then
    COMMIT_REPO="$PWD"
  fi
fi

if [ -n "$COMMIT_REPO" ]; then
  CURRENT_BRANCH=$(git -C "$COMMIT_REPO" branch --show-current 2>/dev/null || echo "")
  if [ "$CURRENT_BRANCH" = "main" ] || [ "$CURRENT_BRANCH" = "master" ]; then
    # HEAD 존재 여부 확인. 없으면(초기 커밋) 허용 — 판정한 그 저장소에서 본다
    if git -C "$COMMIT_REPO" rev-parse --verify HEAD >/dev/null 2>&1; then
      echo "🚫 [harness] main/master 직접 커밋 차단" >&2
      echo "   대상 저장소: $COMMIT_REPO (브랜치: $CURRENT_BRANCH)" >&2
      echo "   feature 브랜치 생성 후 커밋하세요: git checkout -b feature/FXXX-기능명" >&2
      exit 2
    fi
  fi
fi

# ── git push --force 차단 (워드 바운더리) ─────────
if echo "$NORMALIZED" | grep -qE 'git[[:space:]]+push[[:space:]].*(--force([[:space:]]|=|$)|[[:space:]]-f([[:space:]]|$))'; then
  echo "🚫 [harness] git push --force 차단" >&2
  echo "   강제 푸시는 팀 협업에 위험합니다. --force-with-lease도 팀 합의 후 사용." >&2
  exit 2
fi

exit 0
