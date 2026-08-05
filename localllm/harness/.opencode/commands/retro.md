---
description: "회고 + 분석"
---

# /retro — 회고 + 분석

`.claude/state/analytics.jsonl`에 기록된 이벤트와 최근 학습을 토대로 회고 리포트 생성.
gstack `/retro` 의 "주간 배포 통계 + 교차 분석" 아이디어에서 가져왔다.

## 사용

```
/retro                    # 최근 7일 회고
/retro --week             # 명시적으로 주간
/retro --month            # 최근 30일
/retro --since F002       # 특정 Feature ID 이후
/retro --all              # 전체 누적
```

## 사전 조건

### analytics.jsonl 스키마

매 `/handoff` 호출마다 다음 이벤트가 `.claude/state/analytics.jsonl` 에 append:

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
    print("NO_ANALYTICS — /handoff 호출이 아직 없음. 핸드오프부터 한 번 실행해 보세요.")
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

답변을 /learn add 로 기록하면 다음 retro에서 반영됨.
════════════════════════════════════════
```

답변 받으면 `/learn add` 형식으로 학습 기록 제안.

### Step 5: Loop 4 개선안 초안 (claude.loope — hill-climb 연동)

> LangChain loop engineering 의 **Loop 4(Hill-Climbing)** 를 닫는 hop. retro 는 회고에 더해
> `hill_climb.py` 의 신호로 **harness 개선안을 초안**한다. **단, auto-apply 금지 — 사람 승인 후에만 반영.**

```bash
python3 .claude/bin/hill_climb.py analyze --json    # 결정론 신호 + 개선 후보 (Loop 2 트레이스 포함)
```

에이전트는 이 JSON 을 받아 **각 후보를 구체 harness-config 변경안으로 번역**한다 (helper=신호 / agent=판단):

```
════════════════════════════════════════
🧗 LOOP 4 개선안 초안 (사람 승인 필요)
════════════════════════════════════════
후보: grader 'reviewer' revision율 80%
  → 제안: rubrics/code-review.md 의 MUST '테스트 포함' 을 Developer 사전 체크리스트로 승격
  → 대상 파일: .claude/rubrics/code-review.md, .claude/agents/developer.md
  → 근거: verify-loop 트레이스 N건 중 M건이 테스트 누락으로 revision

후보: 에스컬레이션 feature [F0XX]
  → 제안: 해당 유형에 Architect 선행 검토 트리거 추가 (CLAUDE.md Architect 호출 기준)
════════════════════════════════════════
```

**게이트 규칙 (반드시)**:
- 에이전트는 **초안만** 낸다. CLAUDE.md/rubric/에이전트 정의를 **자동 수정하지 않는다**.
- 트레이스가 얇으면(예: verify-loop 0건, handoff < 3) 초안을 **생략**한다 (성급한 변경·노이즈 방지).
- 오탐 인지: 후보는 heuristic — 예) 변형 통째 복사의 대량 변경파일은 정당하므로 사람이 기각.
- 사람이 채택한 변경만 반영 → 다음 사이클 트레이스로 재검증 (hill climb 반복).

> 다른 변형에는 `hill_climb.py` 가 없으므로 Step 5 는 스킵된다 (claude.loope 전용).

## handoff.md 통합 (analytics append)

`/handoff` 마지막 단계에서 자동 append (`/handoff` 문서의 Step 5 참고):

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

- **주간**: 매주 `/retro --week`
- **Feature 완료 직후**: `/retro --since F00X`
- **월간**: 큰 그림 점검 + 학습 export

## 체크리스트

- [ ] analytics.jsonl 존재 여부 확인
- [ ] 기간 파라미터 정상 파싱 (--week/--month/--since F-ID)
- [ ] 통계 출력 (완료 수, 평균 세션, 리뷰 반복, 에이전트 분포)
- [ ] 최근 학습 요약 출력
- [ ] 회고 질문 3개 생성 (답변 → /learn add 유도)
- [ ] (claude.loope) Step 5 — hill_climb `--json` 개선안 초안 (트레이스 충분 시), **auto-apply 금지·사람 승인**

---

사용자 인자 (없으면 무시): $ARGUMENTS

---

> **로컬 LLM 실행 힌트**: 이 커맨드의 동작은 위 문서의 bash 명령을 **그대로 실행**하는 것이다. 문서에 `python3 .claude/bin/...` 또는 bash 블록이 있으면 추측·재해석하지 말고 그 명령을 bash 도구로 즉시 실행하고, 그 출력을 요약해 보고하라. bash 도구 호출 시 `command` 와 `description` **두 인자를 모두** 채워라 (description 누락 = 스키마 에러). 파일이 없거나 실패하면 문서의 안내 문구를 따르고 사용자에게 질문하지 마라.
