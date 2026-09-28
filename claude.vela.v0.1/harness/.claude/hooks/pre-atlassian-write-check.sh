#!/usr/bin/env bash
# pre-atlassian-write-check.sh — Atlassian 쓰기 대상 제한 (철칙)
#
# claude.vela 계열 전용 훅. **허락한 Confluence 스페이스·Jira 프로젝트에만** 쓴다.
#
# 왜 이 훅이 필요한가:
#   `permissions.ask` 는 쓰기 도구를 호출할 때마다 사람에게 묻는다. 그러나 그것은
#   "이 호출을 허용하는가" 일 뿐 **"이 대상이 허용 목록에 있는가" 가 아니다**.
#   긴 자율 작업 끝의 승인 피로 한 번이면 엉뚱한 스페이스에 발행된다.
#   되돌려도 알림과 이력은 남는다.
#
#   그리고 MCP 도구 호출은 모델 → 커넥터로 **곧장** 간다 — `atlassian_map.py` 는
#   그 경로에 없다. 파이썬 코드로는 아무것도 막지 못한다 (CLAUDE.md 규칙 #1 이
#   경고하는 바로 그 간극). PreToolUse 훅만이 실제 차단 지점이다.
#
# 규약:
#   - 허용 목록: `.claude/atlassian-targets.json`
#   - 목록이 없거나·비었거나·손상이면 **전면 거부** (fail-closed)
#   - 대상을 판별할 수 없으면 **거부** — 확인 못 한 것을 통과시키지 않는다
#   - exit 0 통과 / exit 2 차단(사유는 stderr)
#
# 호출 환경: settings.json 의 PreToolUse matcher
#   `mcp__claude_ai_Atlassian_Rovo__(create|update|edit|add|transition|delete).*`
#   훅은 stdin 으로 `{"tool_name": ..., "tool_input": {...}}` 를 받는다.

set -u

ROOT="${CLAUDE_PROJECT_DIR:-$(pwd)}"
PAYLOAD="$(cat 2>/dev/null || true)"

# 훅 자신의 실패가 쓰기를 허용해서는 안 된다 — python3 가 없으면 거부한다.
if ! command -v python3 >/dev/null 2>&1; then
  echo "❌ Atlassian 쓰기 차단: python3 없음 — 대상 검증 불가 (fail-closed)" >&2
  exit 2
fi

ATLASSIAN_PAYLOAD="$PAYLOAD" ATLASSIAN_ROOT="$ROOT" python3 - <<'PY'
import json, os, re, sys

root = os.environ["ATLASSIAN_ROOT"]
raw = os.environ.get("ATLASSIAN_PAYLOAD", "")

def block(msg: str, hint: str = "") -> None:
    print(f"❌ Atlassian 쓰기 차단 — {msg}", file=sys.stderr)
    if hint:
        print(f"   {hint}", file=sys.stderr)
    print("   허용 목록: .claude/atlassian-targets.json (사람이 직접 넣는다)", file=sys.stderr)
    sys.exit(2)

# ── 1. 도구 호출 payload ──────────────────────────────────────────────────
try:
    payload = json.loads(raw) if raw.strip() else {}
except ValueError:
    block("훅 입력을 해석할 수 없음", "검증하지 못한 호출은 통과시키지 않는다")
# 파싱 성공 ≠ 형태 정상. `[1,2]` 는 파싱되지만 `.get` 이 없어 traceback 으로 죽었다 —
# exit 1 은 차단이 아니라 **훅 오류**이고, 메시지도 쓸모없다. (이 리포가 아홉 번 만난 결함)
if not isinstance(payload, dict):
    block(f"훅 입력 형태 오류: {type(payload).__name__}")
tool = payload.get("tool_name") or payload.get("tool") or ""
args = payload.get("tool_input") or payload.get("input") or {}
if not isinstance(args, dict):
    block(f"도구 인자 형태 오류: {type(args).__name__}")

# ── 2. 허용 목록 (fail-closed) ────────────────────────────────────────────
path = os.path.join(root, ".claude", "atlassian-targets.json")
try:
    with open(path, encoding="utf-8") as fh:
        allow = json.load(fh)
except FileNotFoundError:
    block("허용 목록 파일이 없음", f"{path} 를 만들고 대상을 등재하십시오")
except (ValueError, OSError) as exc:
    block(f"허용 목록을 읽을 수 없음 ({type(exc).__name__})")
if not isinstance(allow, dict):
    block("허용 목록 형태 오류 — 최상위가 객체가 아님")

def names(key: str) -> set:
    v = allow.get(key)
    return {str(x).strip().upper() for x in v if str(x).strip()} if isinstance(v, list) else set()

spaces, projects = names("confluence_spaces"), names("jira_projects")
if not spaces and not projects:
    block("허용 목록이 비어 있음 — 기본값은 전면 거부다",
          "쓰려면 허락한 스페이스 키·프로젝트 키를 사람이 직접 등재해야 한다")

# ── 3. 호출에서 대상 키를 뽑는다 ──────────────────────────────────────────
# 값이 어디 들어오든 찾도록 전체를 훑되, **찾지 못하면 거부**한다.
flat = {}
def walk(node, prefix=""):
    if isinstance(node, dict):
        for k, v in node.items():
            walk(v, f"{prefix}.{k}" if prefix else k)
    elif isinstance(node, (str, int)):
        flat[prefix] = str(node)
walk(args)

ISSUE_KEY = re.compile(r"^([A-Z][A-Z0-9_]+)-\d+$")
found, where = set(), []
for key, val in flat.items():
    low = key.lower()
    v = val.strip()
    if not v:
        continue
    if low.endswith(("spacekey", "space", "spaceid")) and not v.isdigit():
        found.add(v.upper()); where.append(f"{key}={v}")
    elif low.endswith(("projectkey", "project")) and not v.isdigit():
        found.add(v.upper()); where.append(f"{key}={v}")
    elif low.endswith(("issuekey", "issueidorkey", "issueid")):
        m = ISSUE_KEY.match(v.upper())
        if m:
            found.add(m.group(1)); where.append(f"{key}={v}")
    elif "url" in low or low.endswith("link"):
        m = re.search(r"/wiki/spaces/([^/]+)/", v)
        if m:
            found.add(m.group(1).upper()); where.append(f"{key}(space)={m.group(1)}")
        m = re.search(r"/browse/([A-Z][A-Z0-9_]+)-\d+", v.upper())
        if m:
            found.add(m.group(1)); where.append(f"{key}(project)={m.group(1)}")

if not found:
    block(f"'{tool}' 호출에서 대상 스페이스·프로젝트를 판별하지 못함",
          "숫자 id 나 URL 대신 스페이스 키 / 이슈 키(PROJ-123)로 호출하십시오 — "
          "확인하지 못한 대상에는 쓰지 않는다")

allowed = spaces | projects
denied = sorted(found - allowed)
if denied:
    block(f"허용되지 않은 대상: {denied}  (호출: {tool})",
          f"근거 {', '.join(where[:4])} / 허용됨: Confluence {sorted(spaces)} · Jira {sorted(projects)}")

print(f"[atlassian] 대상 확인 — {sorted(found)} (허용 목록 통과)")
PY
