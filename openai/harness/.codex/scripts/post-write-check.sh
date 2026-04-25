#!/usr/bin/env bash
# .codex/scripts/post-write-check.sh
# feature_list.json 무결성 검증. 에이전트가 feature_list.json을 편집한 직후
# 반드시 호출해야 합니다 (Codex CLI는 PostToolUse 훅이 없음).
#
# 사용법:
#   bash .codex/scripts/post-write-check.sh
#
# 검증 항목:
#   1) 항목 삭제 금지 (cancelled status로만 표시)
#   2) passes: true → false/null 되돌리기 금지 (QA 재검증 없이)
#   3) acceptance_criteria 개수 감소 금지 (기준 약화)
#   4) status 역행 금지 (done→todo 등, review→in-progress만 예외)
#   5) 필수 필드 누락 / 중복 id / 배열 타입 검증
#
# 반환:
#   - 위반:  exit 2 + stderr 메시지  → 에이전트는 즉시 `git checkout -- feature_list.json`으로 되돌려야 함
#   - 정상:  exit 0

set -eo pipefail

if [ ! -f feature_list.json ]; then
  echo "🚫 [harness] feature_list.json 파일을 찾을 수 없음" >&2
  exit 2
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "⚠️  [harness] python3가 없어 feature_list.json 심층 검증을 건너뜁니다." >&2
  exit 0
fi

PREV_TMP=$(mktemp)
CURR_TMP=$(mktemp)
trap 'rm -f "$PREV_TMP" "$CURR_TMP"' EXIT

# HEAD 버전 (없으면 빈 파일 = 초기 생성으로 간주)
git show HEAD:feature_list.json > "$PREV_TMP" 2>/dev/null || : > "$PREV_TMP"
cp feature_list.json "$CURR_TMP"

VIOLATION=$(python3 - "$PREV_TMP" "$CURR_TMP" <<'PYEOF'
import json, sys, os

prev_path, curr_path = sys.argv[1], sys.argv[2]

def load(path):
    try:
        if os.path.getsize(path) == 0:
            return None
        with open(path) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return "PARSE_ERROR"

curr = load(curr_path)
if curr == "PARSE_ERROR":
    print("현재 feature_list.json JSON 파싱 실패")
    sys.exit(0)
if curr is None:
    print("feature_list.json이 비어있음")
    sys.exit(0)
if not isinstance(curr, list):
    print("feature_list.json은 배열이어야 합니다")
    sys.exit(0)

# 필수 필드 검증
required = ("id", "status", "passes")
for i, f in enumerate(curr):
    if not isinstance(f, dict):
        print(f"[{i}] 객체가 아님")
        sys.exit(0)
    for req in required:
        if req not in f:
            print(f"[{i}] '{req}' 필드 누락 (id={f.get('id','?')})")
            sys.exit(0)

# 중복 id 검증
ids = [f["id"] for f in curr]
dups = {x for x in ids if ids.count(x) > 1}
if dups:
    print(f"중복 id 감지: {sorted(dups)}")
    sys.exit(0)

# 이전 버전과 비교 (HEAD 없으면 스킵)
prev = load(prev_path)
if prev is None or prev == "PARSE_ERROR":
    sys.exit(0)
if not isinstance(prev, list):
    sys.exit(0)

prev_by_id = {f["id"]: f for f in prev if isinstance(f, dict) and "id" in f}
curr_by_id = {f["id"]: f for f in curr if isinstance(f, dict) and "id" in f}

# 1) 항목 삭제 감지
missing = set(prev_by_id) - set(curr_by_id)
if missing:
    print(f"항목 삭제 감지: {sorted(missing)} — 삭제 금지, status를 'cancelled'로 표시하세요")
    sys.exit(0)

status_order = {"todo": 0, "in-progress": 1, "review": 2, "qa": 3, "done": 4}

for fid, prev_f in prev_by_id.items():
    curr_f = curr_by_id.get(fid)
    if curr_f is None:
        continue

    # 2) passes: true → 다른 값 되돌리기
    if prev_f.get("passes") is True and curr_f.get("passes") is not True:
        print(f"{fid}: passes 되돌리기 감지 (true → {curr_f.get('passes')}) — QA 재검증 필요")
        sys.exit(0)

    # 3) acceptance_criteria 개수 감소
    prev_ac = prev_f.get("acceptance_criteria") or []
    curr_ac = curr_f.get("acceptance_criteria") or []
    if isinstance(prev_ac, list) and isinstance(curr_ac, list):
        if len(curr_ac) < len(prev_ac):
            print(f"{fid}: acceptance_criteria 감소 감지 ({len(prev_ac)} → {len(curr_ac)}) — 기준 약화 금지")
            sys.exit(0)

    # 4) status 역행 (done → 다른 상태, review → todo 등)
    #    예외: review → in-progress (NEEDS REVISION 시 허용)
    #    예외: * → cancelled (취소는 허용)
    p_st = prev_f.get("status")
    c_st = curr_f.get("status")
    if c_st == "cancelled":
        continue
    if p_st in status_order and c_st in status_order:
        if status_order[c_st] < status_order[p_st]:
            if not (p_st == "review" and c_st == "in-progress"):
                print(f"{fid}: status 역행 감지 ({p_st} → {c_st})")
                sys.exit(0)
PYEOF
)

if [ -n "$VIOLATION" ]; then
  echo "🚫 [harness] feature_list.json 무결성 위반" >&2
  echo "   $VIOLATION" >&2
  echo "   되돌리기: git checkout -- feature_list.json" >&2
  exit 2
fi

echo "✅ [harness] feature_list.json 무결성 OK"
exit 0
