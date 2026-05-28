#!/usr/bin/env bash
# pre-bash-auto-boundary-check.sh
#
# claude.gstack.auto 변형 전용 훅.
# Autonomous Mode 의 3 규칙 중 "3번" (사용자 승인이 필요한 경계) 을 강제한다.
#
# 차단 (exit 2 — 사용자 승인 요청) 대상:
#   1. 인증/계정 관련 명령 (ssh-keygen, gh auth login, gcloud auth, aws configure 등)
#   2. 작업 디렉토리 (CLAUDE_PROJECT_DIR) 밖에서 부수 효과를 일으키는 명령
#      (cd/rm/mv/cp/chmod/chown 가 절대 경로로 외부를 가리키는 경우)
#
# 허용 (exit 0) 대상:
#   - 작업 디렉토리 내부 모든 명령
#   - /tmp, /var/tmp 의 임시 파일 작업
#   - 시스템 경로 read-only 조회 (cat /etc/..., ls /usr/...)
#
# 호출 환경:
#   - settings.json 의 PreToolUse:Bash matcher 에 등록되어 Bash 호출 직전 실행
#   - 표준 출력은 사용자에게, 표준 에러는 차단 사유 안내
#
# 다른 차단 훅(pre-bash-check.sh) 과 병행 동작. 양쪽 다 통과해야 명령 실행.

set -u

CMD="${CLAUDE_TOOL_INPUT_command:-}"
WORKDIR="${CLAUDE_PROJECT_DIR:-$(pwd)}"

# 빈 명령은 통과 (다른 훅이 처리)
[ -z "$CMD" ] && exit 0

# 정규화: 소문자, 공백 압축 (패턴 매칭용)
NORMALIZED=$(echo "$CMD" | tr '[:upper:]' '[:lower:]' | tr -s '[:space:]' ' ')

# ────────────────────────────────────────────────────────────
# 1) 인증/계정 관련 명령 — 사용자 승인 필요
# ────────────────────────────────────────────────────────────
# 정규식 단어 경계로 매칭 (false positive 최소화)

AUTH_PATTERNS=(
  '\bssh-keygen\b'
  '\bssh-add\b'
  '\bgpg[[:space:]]+--gen-key\b'
  '\bgpg[[:space:]]+--full-generate-key\b'
  '\bgpg[[:space:]]+--import\b'
  '\baws[[:space:]]+configure\b'
  '\baws[[:space:]]+sso[[:space:]]+login\b'
  '\bgcloud[[:space:]]+auth\b'
  '\bgcloud[[:space:]]+init\b'
  '\bgh[[:space:]]+auth[[:space:]]+login\b'
  '\bgh[[:space:]]+auth[[:space:]]+refresh\b'
  '\bglab[[:space:]]+auth[[:space:]]+login\b'
  '\bnpm[[:space:]]+login\b'
  '\bnpm[[:space:]]+adduser\b'
  '\byarn[[:space:]]+login\b'
  '\bpnpm[[:space:]]+login\b'
  '\bdocker[[:space:]]+login\b'
  '\bop[[:space:]]+signin\b'
  '\bop[[:space:]]+sign-in\b'
  '\bkeyring[[:space:]]+set\b'
  '\bsecret-tool[[:space:]]+store\b'
  '\bgit[[:space:]]+config[[:space:]]+--global\b'
  '\bgit[[:space:]]+credential\b'
  '\bcurl[[:space:]]+.*[[:space:]]+-u[[:space:]]'
  '\bcurl[[:space:]]+.*[[:space:]]+--user[[:space:]]'
  '\bwget[[:space:]]+.*[[:space:]]+--user[[:space:]]'
  '\bsudo\b'
  '\bsu\b'
  '\bsignup\b'
  '\bregister-account\b'
  '\bcreate-user\b'
)

for pat in "${AUTH_PATTERNS[@]}"; do
  if echo "$NORMALIZED" | grep -qE "$pat"; then
    echo "🔒 [auto] 인증/계정 관련 명령 감지 — 사용자 승인 필요" >&2
    echo "   매칭 패턴: $pat" >&2
    echo "   원본 명령: $CMD" >&2
    echo "" >&2
    echo "   자동 모드 규칙 #3: 계정 생성 / 인증 / 외부 시스템 로그인은" >&2
    echo "   에이전트끼리 결정할 수 없고 사용자 명시 승인이 필요합니다." >&2
    exit 2
  fi
done

# ────────────────────────────────────────────────────────────
# 2) 작업 디렉토리 외부 부수 효과 명령
# ────────────────────────────────────────────────────────────
# 다음 동사로 시작하는 명령이 절대 경로 인자를 가지면 WORKDIR 외부인지 검사
#   cd, rm, mv, cp, chmod, chown, ln, install, dd, tar (-C), make (-C)
#
# 정책:
#   - WORKDIR 하위 경로:  허용 (exit 0)
#   - /tmp, /var/tmp:    허용 (임시 작업용)
#   - 그 외 절대 경로:   차단 (exit 2)
#
# 상대 경로 명령은 항상 WORKDIR 내부이므로 통과.

MUTATING_VERBS='cd|rm|mv|cp|chmod|chown|ln|install|dd'

if echo "$CMD" | grep -qE "(^|[;|&[:space:]])($MUTATING_VERBS)[[:space:]]"; then
  # 명령에 등장하는 절대 경로들을 모두 추출
  ABS_PATHS=$(echo "$CMD" | grep -oE '(^|[[:space:]])/[A-Za-z0-9._/-]+' | tr -d ' ')

  if [ -n "$ABS_PATHS" ]; then
    # 정규화 — WORKDIR 의 trailing slash 제거
    WD_NORM="${WORKDIR%/}"

    while IFS= read -r path; do
      [ -z "$path" ] && continue
      case "$path" in
        "$WD_NORM"|"$WD_NORM"/*) : ;;  # WORKDIR 또는 그 하위 — OK
        /tmp|/tmp/*|/var/tmp|/var/tmp/*) : ;;  # 임시 작업 — OK
        /dev/null|/dev/stdin|/dev/stdout|/dev/stderr) : ;;  # 디바이스 read/write — OK
        *)
          echo "🔒 [auto] 작업 디렉토리 밖 경로에 부수 효과 명령 — 사용자 승인 필요" >&2
          echo "   감지된 경로: $path" >&2
          echo "   WORKDIR:    $WD_NORM" >&2
          echo "   원본 명령:  $CMD" >&2
          echo "" >&2
          echo "   자동 모드 규칙 #3: WORKDIR 밖 변경은 에이전트끼리 결정할 수 없습니다." >&2
          exit 2
          ;;
      esac
    done <<< "$ABS_PATHS"
  fi
fi

# 모든 검사 통과 — autonomous 모드 자동 진행
exit 0
