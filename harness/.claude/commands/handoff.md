# /project:handoff — 세션 인계

작업 세션을 마무리하고 다음 에이전트/세션에 깔끔하게 인계한다.
구조화된 체크포인트 + `claude-progress.txt` 히스토리 로그를 모두 생성한다.

## 실행 순서

### Step 1. 코드 상태 확인

```bash
npm test              # 테스트 통과 (프로젝트 CLAUDE.md의 실제 명령어로 대체)
npm run lint          # 린트 통과
git status            # 커밋되지 않은 변경사항 확인
```

### Step 2. 변경사항 커밋

```bash
git add -A
# 미완성 상태면 wip, 완료면 feat/fix
git commit -m "wip(FXXX): [현재까지 작업 내용]"
# 또는
# git commit -m "feat(FXXX): [구현 내용]"
```

### Step 3. feature_list.json status 업데이트

상황에 맞는 status로 변경:

| 상황 | status |
|---|---|
| 구현 중 | `in-progress` |
| 구현 완료, Reviewer 대기 | `review` |
| 리뷰 통과, QA 대기 | `qa` |
| QA 통과 | `done` (동시에 `passes: true`) |

### Step 4. 구조화된 체크포인트 저장

```
/project:context-save "<현재 작업의 짧은 제목>"
```

이 커맨드가 자동으로 `.claude/state/checkpoints/<timestamp>-<title>.md` 를 생성하고 다음을 기록한다:
- git 상태 스냅샷 (branch, files_modified, recent log)
- Summary / Decisions Made / Remaining Work / Notes 4개 섹션
- frontmatter에 `branch`, `feature_id`, `agent` 포함

### Step 5. claude-progress.txt 에 요약 append

체크포인트 파일의 **경로와 한 줄 요약**을 `claude-progress.txt`에 다음 형식으로 append:

```
============================================================
[YYYY-MM-DD HH:MM] [에이전트명]: [작업 요약]
============================================================
작업한 Feature: [FXXX]
작업 내용:
  - [구체적으로 한 일 1]
  - [구체적으로 한 일 2]

현재 상태: [in-progress | review | qa | done]
feature status: [변경 전] → [변경 후]

체크포인트: .claude/state/checkpoints/<timestamp>-<title>.md

파일 변경:
  - 추가: [파일 목록]
  - 수정: [파일 목록]

다음 세션 할 일:
  - [ ] [구체적인 다음 작업]

주의사항:
  - [알아야 할 중요 정보나 함정]
============================================================
```

### Step 6. 학습 기록 (해당 시)

이 세션에서 발견한 비자명한 패턴·함정·결정이 있으면:

```
/project:learn add
```

자동 기록 예:
- Reviewer가 MUST 이슈 발견 → type: `pitfall`
- QA가 엣지케이스 회귀 발견 → type: `pitfall`
- Architect가 ADR 확정 → type: `architecture`
- Developer가 비자명한 구현 패턴 발견 → type: `pattern`

### Step 7. analytics 이벤트 append (자동)

회고(`/project:retro`)에서 통계로 활용할 수 있도록 핸드오프 이벤트를 기록.
**bash 환경변수 + Python os.environ 패턴** (heredoc 보간을 쓰지 않음 — 특수문자 안전):

```bash
mkdir -p .claude/state
export FEATURE_ID="${FEATURE_ID:-}"
export AGENT="${AGENT:-}"
export STATUS_FROM="${STATUS_FROM:-}"
export STATUS_TO="${STATUS_TO:-}"
export FILES_CHANGED=$(git diff --name-only HEAD 2>/dev/null | wc -l | tr -d ' ' || echo 0)

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

환경변수가 비어있어도 `event:handoff` + `ts` 만 있는 최소 이벤트가 기록됨.
장기적으로 누적되어 `/project:retro` 가 분석한다.

## 인계 조건

| 상황 | feature status | 다음 에이전트 |
|---|---|---|
| 구현 완료, 테스트 통과 | `review` | Reviewer |
| 리뷰 APPROVED | `qa` | QA |
| QA PASS | `done` + passes:true | Planner (다음 Feature) |
| 설계 필요 | `in-progress` | Architect |
| 리뷰 NEEDS REVISION | `in-progress` | Developer |

## 리뷰 반복 에스컬레이션

같은 Feature에서 NEEDS REVISION **3회 이상** 반복되면:
- `claude-progress.txt`에 `[ESCALATION]` 태그 기록
- Planner + Architect 에이전트를 호출하여 설계 재검토
- Feature를 더 작은 단위로 분해할지 검토
- 동시에 `/project:learn add` 로 `pitfall` 등록 권장

## 체크리스트

- [ ] 모든 변경사항 커밋됨
- [ ] 테스트 실패 없음
- [ ] feature_list.json status 업데이트 완료
- [ ] `/project:context-save` 로 구조화된 체크포인트 저장 완료
- [ ] `claude-progress.txt` 한 줄 요약 append 완료
- [ ] 다음 작업 명확히 기술됨
- [ ] (선택) 새 학습 `/project:learn add`
