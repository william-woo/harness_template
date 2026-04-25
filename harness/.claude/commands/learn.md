# /project:learn — 프로젝트 학습 관리

여러 세션에 걸쳐 누적된 프로젝트 학습(패턴·함정·의사결정)을 저장/검색/정리한다.
`.claude/state/learnings.jsonl` (git 커밋 대상, 팀 공유)에 append-only 로 기록된다.

## 서브커맨드

사용자 입력 파싱:

- `/project:learn`              → **show** (최근 20개)
- `/project:learn search <질의>` → **search**
- `/project:learn add`          → **add** (대화형 추가)
- `/project:learn prune`        → **prune** (중복·상충 정리)
- `/project:learn stats`        → **stats**
- `/project:learn export`       → **export** (CLAUDE.md 섹션 형식으로)

**HARD GATE: 이 커맨드는 코드 수정을 하지 않는다. 학습 관리 전용.**

## 스키마 (JSONL, 한 줄 = 한 학습)

```json
{
  "ts": "2026-04-25T14:30:00+09:00",
  "type": "pattern | pitfall | preference | architecture | tool",
  "key": "kebab-case-short-key",
  "insight": "한 문장 요약 (왜 이게 중요한지)",
  "confidence": 8,
  "source": "developer | reviewer | qa | planner | architect | user-stated",
  "feature_id": "F002",
  "files": ["src/auth/login.ts"]
}
```

필드 규칙:
- `ts`: ISO-8601 타임스탬프 (로컬 타임존 포함)
- `type`: 5개 중 하나로 제한
- `key`: 2~5 단어, kebab-case (중복 방지용 식별자)
- `insight`: 한 문장, 왜(why) 중심
- `confidence`: 1~10 (낮으면 실험적, 높으면 검증된 패턴)
- `source`: 어느 에이전트/컨텍스트에서 나온 학습인지
- `feature_id`, `files`: 선택 (관련 Feature·파일)

---

## show (기본)

최근 20개를 type 별로 그룹핑해서 출력:

```bash
LEARN_FILE="$CLAUDE_PROJECT_DIR/.claude/state/learnings.jsonl"
if [ ! -f "$LEARN_FILE" ] || [ ! -s "$LEARN_FILE" ]; then
  echo "ℹ️  아직 학습이 기록되지 않음"
  echo "   /project:learn add 로 수동 추가하거나"
  echo "   reviewer/qa/developer 에이전트가 자동으로 기록합니다."
  exit 0
fi

python3 - "$LEARN_FILE" <<'PY'
import sys, json
from collections import defaultdict
with open(sys.argv[1]) as f:
    entries = [json.loads(l) for l in f if l.strip()]
# dedup: 같은 key는 최신만 유지
by_key = {}
for e in entries:
    by_key[e.get('key', '?')] = e
# 최근 20개
recent = sorted(by_key.values(), key=lambda e: e.get('ts',''), reverse=True)[:20]
# type 별 그룹
groups = defaultdict(list)
for e in recent:
    groups[e.get('type', 'other')].append(e)
for t in ['pattern','pitfall','preference','architecture','tool','other']:
    if t not in groups: continue
    print(f"\n## {t.upper()}")
    for e in groups[t]:
        conf = e.get('confidence', '?')
        fid = e.get('feature_id', '')
        fid_str = f" [{fid}]" if fid else ''
        print(f"  • {e.get('key','?')}{fid_str} (conf {conf}/10)")
        print(f"    └─ {e.get('insight','')}")
PY
```

## search

```bash
LEARN_FILE="$CLAUDE_PROJECT_DIR/.claude/state/learnings.jsonl"
QUERY="<사용자 질의 — 소문자로 변환해서 grep>"

python3 - "$LEARN_FILE" "$QUERY" <<'PY'
import sys, json
path, q = sys.argv[1], sys.argv[2].lower()
try:
    with open(path) as f:
        entries = [json.loads(l) for l in f if l.strip()]
except FileNotFoundError:
    print("학습 파일 없음"); sys.exit(0)
# dedup
by_key = {}
for e in entries:
    by_key[e.get('key','?')] = e
# 검색: key/insight/type 중 하나라도 매칭
matches = [e for e in by_key.values()
           if q in e.get('key','').lower()
           or q in e.get('insight','').lower()
           or q in e.get('type','').lower()]
if not matches:
    print(f"'{q}'에 매칭되는 학습 없음"); sys.exit(0)
for e in sorted(matches, key=lambda e: e.get('ts',''), reverse=True)[:20]:
    print(f"[{e.get('type','?')}] {e.get('key','?')} (conf {e.get('confidence','?')}/10)")
    print(f"  └─ {e.get('insight','')}")
PY
```

## add (수동 추가)

AskUserQuestion으로 다음을 순차 수집:

1. **type** — 선택지: pattern / pitfall / preference / architecture / tool
2. **key** — 텍스트 입력, 2~5단어 kebab-case (예: `jwt-expires-in-1h`)
3. **insight** — 텍스트 입력, 한 문장 (왜 중요한지)
4. **confidence** — 선택지: 1, 3, 5, 7, 9, 10
5. **feature_id** — 선택 (생략 가능)
6. **files** — 선택 (쉼표로 구분된 경로, 생략 가능)

수집 후 JSONL 한 줄 append. 사용자 입력에 따옴표·줄바꿈 등 특수문자가 있어도
안전하도록 **bash 환경변수 + Python `os.environ` 패턴** 사용 (heredoc 보간 금지):

```bash
LEARN_FILE="$CLAUDE_PROJECT_DIR/.claude/state/learnings.jsonl"
mkdir -p "$(dirname "$LEARN_FILE")"

# AskUserQuestion 답변을 환경변수로 export 한 뒤 호출
export TYPE KEY INSIGHT CONFIDENCE FEATURE_ID FILES

python3 - <<'PY' >> "$LEARN_FILE"
import json, datetime, os
files = os.environ.get("FILES","")
entry = {
  "ts": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
  "type": os.environ.get("TYPE",""),
  "key": os.environ.get("KEY",""),
  "insight": os.environ.get("INSIGHT",""),
  "confidence": int(os.environ.get("CONFIDENCE","0") or 0),
  "source": "user-stated",
  "feature_id": os.environ.get("FEATURE_ID") or None,
  "files": [s.strip() for s in files.split(",")] if files else []
}
entry = {k:v for k,v in entry.items() if v not in (None,"",0)}
# confidence=0 은 의미 없는 값 — 제거된 채로 저장됨
print(json.dumps(entry, ensure_ascii=False))
PY

echo "✅ 학습 추가됨: $KEY"
```

`<<'PY'` (단일 인용 heredoc)는 bash 보간을 끄고, Python 안에서 `os.environ` 으로 값을
읽으므로 `INSIGHT="he said \"hi\""` 같은 입력도 안전하다.

## prune (중복·상충 정리)

모든 학습을 순회하며 다음을 감지:

1. **파일 누락 (stale)** — `files` 필드에 적힌 경로가 실제로 없으면 "STALE" 플래그
2. **상충 (conflict)** — 같은 `key` + 같은 `type`에 다른 `insight` 가 있으면 "CONFLICT" 플래그

각 항목별로 AskUserQuestion:
- A) 제거
- B) 유지
- C) 업데이트 (새 insight 입력)

Append-only이므로 "제거"는 실제로는 **tombstone 엔트리** 추가로 구현:

```bash
# 제거 시 tombstone append
python3 - <<PY >> "$CLAUDE_PROJECT_DIR/.claude/state/learnings.jsonl"
import json, datetime
tombstone = {
  "ts": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
  "type": "tombstone",
  "key": "$KEY",
  "insight": "removed via /project:learn prune",
  "source": "user-stated"
}
print(json.dumps(tombstone, ensure_ascii=False))
PY
```

검색·표시 시 `type: "tombstone"` 엔트리가 있는 key는 제외한다.

## stats

```bash
LEARN_FILE="$CLAUDE_PROJECT_DIR/.claude/state/learnings.jsonl"
python3 - "$LEARN_FILE" <<'PY'
import sys, json
from collections import Counter
try:
    with open(sys.argv[1]) as f:
        entries = [json.loads(l) for l in f if l.strip()]
except FileNotFoundError:
    print("NO_LEARNINGS"); sys.exit(0)

# dedup + tombstone 처리
by_key = {}
tombstoned = set()
for e in entries:
    if e.get('type') == 'tombstone':
        tombstoned.add(e.get('key'))
        continue
    by_key[e.get('key','?')] = e
active = [e for k,e in by_key.items() if k not in tombstoned]

total_raw = len(entries)
unique = len(active)
by_type = Counter(e.get('type','?') for e in active)
by_source = Counter(e.get('source','?') for e in active)
avg_conf = sum(e.get('confidence',0) for e in active) / max(unique,1)

print(f"TOTAL_ENTRIES: {total_raw}")
print(f"ACTIVE_UNIQUE: {unique}  (dedup + tombstone 제외)")
print(f"BY_TYPE: {dict(by_type)}")
print(f"BY_SOURCE: {dict(by_source)}")
print(f"AVG_CONFIDENCE: {avg_conf:.1f}/10")
PY
```

## export

활성 학습들을 CLAUDE.md에 붙여넣기 좋은 Markdown 섹션으로 출력:

```markdown
## Project Learnings

### Patterns
- **[key]**: [insight] (conf N/10)

### Pitfalls
- **[key]**: [insight] (conf N/10)

### Preferences
- **[key]**: [insight]

### Architecture
- **[key]**: [insight] (conf N/10)
```

출력 후 사용자에게 질문: "CLAUDE.md에 붙일까요, 별도 파일로 저장할까요?"

---

## 에이전트 자동 기록 규칙

다른 에이전트(developer/reviewer/qa/architect/planner)는 다음 순간에 학습을 **자동 append** 해야 한다:

| 에이전트 | 언제 | type | 예시 key |
|---|---|---|---|
| Reviewer | MUST 수정사항 발견 시 | pitfall | `bcrypt-salt-hardcoded` |
| QA | 엣지 케이스 회귀 발견 시 | pitfall | `empty-string-validation-missing` |
| Architect | ADR 작성 후 핵심 결정 | architecture | `use-jwt-over-session` |
| Developer | 비자명한 패턴 발견 | pattern | `retry-exponential-backoff` |
| Planner | Feature 재분해 시 | preference | `split-auth-from-authz` |

자동 기록 시 `source`는 에이전트 이름, `feature_id`는 현재 Feature ID.

## 시작 세션에서 조회

`/project:start-session`은 자동으로 `/project:learn stats`를 실행해서 지식 양을 표시한다. 선택한 Feature와 유사한 key를 가진 학습이 있으면 planner 에이전트가 조회·참고한다 (`.claude/agents/planner.md` 참고).
