# /project:start-session — 작업 세션 시작

새 작업 세션을 시작할 때 실행. 이전 진행 상황을 파악하고 다음 작업을 선택한다.

## 실행 순서

```bash
# 1. claude-progress.txt 아카이빙 (200줄 초과 시)
LINE_COUNT=$(wc -l < claude-progress.txt 2>/dev/null || echo 0)
if [ "$LINE_COUNT" -gt 200 ]; then
  cat claude-progress.txt >> docs/progress-archive.txt
  tail -60 claude-progress.txt > /tmp/progress-tmp.txt
  mv /tmp/progress-tmp.txt claude-progress.txt
  echo "📁 claude-progress.txt 아카이브 완료 (docs/progress-archive.txt)"
fi

# 2. 현재 상태 파악
cat claude-progress.txt
git log --oneline -15
cat feature_list.json

# 3. 환경 확인
bash init.sh
```

## 다음 Feature 선택 규칙

feature_list.json에서 다음 조건을 모두 만족하는 것 중 우선순위 최상위:

1. `passes: false` — 아직 완료되지 않음
2. `status: "todo"` — 아직 작업 시작 안 됨 (in-progress는 재개)
3. 모든 `dependencies`의 `passes: true` — 선행 조건 완료
4. `priority: critical → high → medium → low` 순서

```
선택 즉시: feature_list.json의 해당 항목 status를 "in-progress"로 변경
```

## 세션 시작 후 안내

선택한 기능의 정보를 출력하고, 상태에 따라 에이전트를 추천:

| 상태 | 추천 에이전트 |
|---|---|
| 설계 문서 없음 | Architect 에이전트 먼저 |
| 설계 완료, 구현 필요 | Developer 에이전트 |
| 구현 완료 (`status: review`) | Reviewer 에이전트 |
| 리뷰 통과 (`status: qa`) | QA 에이전트 |
