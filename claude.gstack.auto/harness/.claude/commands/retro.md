# /project:retro — 회고 + 분석

`.claude/state/analytics.jsonl`에 기록된 이벤트와 최근 학습을 토대로 회고 리포트 생성.
gstack `/retro` 의 "주간 배포 통계 + 교차 분석" 아이디어에서 가져왔다.

## 사용

```
/project:retro                    # 최근 7일 회고
/project:retro --week             # 명시적으로 주간
/project:retro --month            # 최근 30일
/project:retro --since F002       # 특정 Feature ID 이후
/project:retro --all              # 전체 누적
```

## 사전 조건

### analytics.jsonl 스키마

매 `/project:handoff` 호출마다 다음 이벤트가 `.claude/state/analytics.jsonl` 에 append:

```json
{"ts":"2026-04-25T14:30:00+09:00","event":"handoff","feature_id":"F002","agent":"developer","status_from":"in-progress","status_to":"review","files_changed":7}
```

세션 종료 시 (`session-end.sh`):

```json
{"ts":"2026-04-25T14:35:00+09:00","event":"session_end","uncommitted":0}
```

리뷰 반복 시 (Reviewer가 NEEDS REVISION 출력 시 수동으로 추가):

```json
{"ts":"2026-04-25T14:40:00+09:00","event":"review_iteration","feature_id":"F002","iteration":1,"verdict":"needs_revision"}
```

## 실행 순서

### Step 1: 기간 결정

```bash
case "$1" in
  --week|"") SINCE=$(date -d '7 days ago' +%Y-%m-%dT%H:%M:%S 2>/dev/null || date -v-7d +%Y-%m-%dT%H:%M:%S);;
  --month)   SINCE=$(date -d '30 days ago' +%Y-%m-%dT%H:%M:%S 2>/dev/null || date -v-30d +%Y-%m-%dT%H:%M:%S);;
  --all)     SINCE="1970-01-01T00:00:00";;
  --since)
    FEAT_ID="$2"
    SINCE=$(python3 -c "
import json
try:
    with open('.claude/state/analytics.jsonl') as f:
        events = [json.loads(l) for l in f if l.strip()]
    first = next((e for e in events if e.get('feature_id')=='$FEAT_ID'), None)
    print(first['ts'] if first else '1970-01-01T00:00:00')
except FileNotFoundError:
    print('1970-01-01T00:00:00')
")
    ;;
esac
echo "SINCE: $SINCE"
```

### Step 2: 통계 집계

```bash
python3 - "$SINCE" <<'PY'
import sys, json
from collections import Counter, defaultdict

since = sys.argv[1]
try:
    with open('.claude/state/analytics.jsonl') as f:
        events = [json.loads(l) for l in f if l.strip()]
except FileNotFoundError:
    print("NO_ANALYTICS — /project:handoff 호출이 아직 없음. 핸드오프부터 한 번 실행해 보세요.")
    sys.exit(0)

events = [e for e in events if e.get('ts','') >= since]
if not events:
    print(f"기간 내 이벤트 없음 (since {since})")
    sys.exit(0)

handoffs = [e for e in events if e.get('event')=='handoff']
reviews  = [e for e in events if e.get('event')=='review_iteration']
sessions = [e for e in events if e.get('event')=='session_end']

by_feat = defaultdict(list)
for e in handoffs:
    by_feat[e.get('feature_id','?')].append(e)

done_feats = set(e.get('feature_id') for e in handoffs if e.get('status_to')=='done')

durations = [e.get('session_duration_s',0) for e in handoffs if e.get('session_duration_s')]
avg_dur = sum(durations)/max(len(durations),1) if durations else 0

review_counts = Counter(e.get('feature_id') for e in reviews if e.get('verdict')=='needs_revision')
by_agent = Counter(e.get('agent','?') for e in handoffs)

print("════════════════════════════════════════")
print(f"📊 RETRO ({since} ~ now)")
print("════════════════════════════════════════")
print(f"\n이벤트 총수: {len(events)}  (handoff {len(handoffs)}, review {len(reviews)}, session_end {len(sessions)})")
print(f"완료 Feature: {len(done_feats)}  — {sorted(done_feats)}")
print(f"활동 Feature: {len(by_feat)}")
if durations:
    print(f"평균 세션 시간: {avg_dur/60:.1f}분  ({len(durations)}개 세션 측정)")
if by_agent:
    print(f"\n에이전트별 handoff:")
    for agent, n in by_agent.most_common():
        print(f"  {agent:12s}: {n}")

if review_counts:
    print(f"\n리뷰 반복 (NEEDS REVISION):")
    for fid, n in review_counts.most_common():
        mark = " ⚠️ ESCALATION 후보" if n >= 3 else ""
        print(f"  {fid}: {n}회{mark}")
PY
```

### Step 3: 최근 학습 요약

```bash
echo ""
echo "=== 최근 학습 ==="
LEARN_FILE=".claude/state/learnings.jsonl"
if [ -f "$LEARN_FILE" ]; then
  python3 - "$LEARN_FILE" "$SINCE" <<'PY'
import sys, json
path, since = sys.argv[1], sys.argv[2]
with open(path) as f:
    entries = [json.loads(l) for l in f if l.strip()]
by_key = {}
for e in entries:
    if e.get('type')=='tombstone': continue
    by_key[e.get('key','?')] = e
recent = [e for e in by_key.values() if e.get('ts','') >= since]
recent.sort(key=lambda e: e.get('ts',''), reverse=True)
if not recent:
    print("기간 내 신규 학습 없음")
else:
    for e in recent[:10]:
        print(f"  [{e.get('type','?'):12s}] {e.get('key','?')} — {e.get('insight','')[:80]}")
PY
fi
```

### Step 4: 회고 프롬프트

통계 기반 3문항 자동 생성 (LLM이 위 통계를 보고 구체적 숫자로 채운다):

```
════════════════════════════════════════
🤔 RETRO 질문 (선택적)
════════════════════════════════════════

1. 완료한 <N>개 Feature 중 가장 어려웠던 것은? 왜?
2. 평균 세션 <N>분 — 이상적인 길이인가? (짧으면 컨텍스트 손실 잦고, 길면 집중 저하)
3. 리뷰 반복 <N>회 발생 — 패턴이 있는가? (인수기준 모호? 설계 부족? 테스트 부족?)

답변을 /project:learn add 로 기록하면 다음 retro에서 반영됨.
════════════════════════════════════════
```

답변 받으면 `/project:learn add` 형식으로 학습 기록 제안.

## handoff.md 통합 (analytics append)

`/project:handoff` 마지막 단계에서 자동 append (`/project:handoff` 문서의 Step 5 참고):

```bash
mkdir -p .claude/state
python3 - <<'PY' >> .claude/state/analytics.jsonl
import json, datetime, os
entry = {
  "ts": datetime.datetime.now().astimezone().isoformat(timespec='seconds'),
  "event": "handoff",
  "feature_id": os.environ.get("FEATURE_ID",""),
  "agent": os.environ.get("AGENT",""),
  "status_from": os.environ.get("STATUS_FROM",""),
  "status_to": os.environ.get("STATUS_TO",""),
  "files_changed": int(os.environ.get("FILES_CHANGED","0") or 0),
}
print(json.dumps({k:v for k,v in entry.items() if v not in (None,"",0)}, ensure_ascii=False))
PY
```

환경변수가 없어도 `event:handoff` + `ts` 만 있는 최소 이벤트라도 기록됨.

## session-end.sh 통합

`session-end.sh` 훅이 매 세션 종료 시 한 줄 append (실패해도 세션 종료 막지 않음).

## 추천 사용 빈도

- **주간**: 매주 `/project:retro --week`
- **Feature 완료 직후**: `/project:retro --since F00X`
- **월간**: 큰 그림 점검 + 학습 export

## 체크리스트

- [ ] analytics.jsonl 존재 여부 확인
- [ ] 기간 파라미터 정상 파싱 (--week/--month/--since F-ID)
- [ ] 통계 출력 (완료 수, 평균 세션, 리뷰 반복, 에이전트 분포)
- [ ] 최근 학습 요약 출력
- [ ] 회고 질문 3개 생성 (답변 → /project:learn add 유도)
