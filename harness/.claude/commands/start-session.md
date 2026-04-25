# /project:start-session — 작업 세션 시작

새 작업 세션을 시작할 때 실행. 이전 진행 상황 파악 + 학습 조회 + 다음 작업 선택.

## 실행 순서

### Step 1. 이전 세션 컨텍스트 복원

```
/project:context-restore
```

`.claude/state/checkpoints/` 의 **가장 최근** 체크포인트를 읽어 요약 제시.
체크포인트가 없으면 아래 Step 2의 `claude-progress.txt`만 참고.

### Step 2. 히스토리 로그 확인 + 아카이빙

```bash
# claude-progress.txt 200줄 초과 시 아카이빙
LINE_COUNT=$(wc -l < claude-progress.txt 2>/dev/null || echo 0)
if [ "$LINE_COUNT" -gt 200 ]; then
  cat claude-progress.txt >> docs/progress-archive.txt
  tail -60 claude-progress.txt > /tmp/progress-tmp.txt
  mv /tmp/progress-tmp.txt claude-progress.txt
  echo "📁 claude-progress.txt 아카이브 완료 (docs/progress-archive.txt)"
fi

# 최근 히스토리 읽기
cat claude-progress.txt
git log --oneline -15
cat feature_list.json
```

### Step 3. 프로젝트 학습 요약

```
/project:learn stats
```

축적된 학습 개수와 type 별 분포를 표시. 개수가 많으면 최근 3개를 보여주고,
선택한 Feature와 관련된 키워드가 있으면 `learn search`를 권장.

### Step 4. 환경 점검

```bash
bash init.sh
```

빌드·테스트 정상 여부 확인. 실패 시 에러 메시지를 토대로 원인 분석.

### Step 5. 다음 Feature 선택

feature_list.json에서 다음 조건을 모두 만족하는 것 중 우선순위 최상위 선택:

1. `passes: false` — 아직 완료되지 않음
2. `status: "todo"` — 작업 시작 전 (`"in-progress"` 면 재개)
3. 모든 `dependencies` 의 `passes: true` — 선행 완료
4. `priority: critical → high → medium → low` 순서

선택 즉시 해당 Feature의 `status`를 `"in-progress"` 로 변경.

### Step 6. 관련 학습 사전 조회

선택한 Feature의 title/category 키워드로 학습 검색:

```
/project:learn search <키워드>
```

매칭되는 pattern/pitfall/architecture가 있으면 요약 출력. Planner 에이전트가 이를 참고해 구현 가이드에 반영.

## 에이전트 추천

선택한 Feature의 상태·특성에 따라:

| 상태/특성 | 추천 에이전트 |
|---|---|
| 설계 문서 없음 + (DB/API/보안/3+ 파일 변경) | Architect 먼저 |
| 설계 완료, 구현 필요 | Developer |
| 구현 완료 (`status: review`) | Reviewer |
| 리뷰 통과 (`status: qa`) | QA |
| 재작업 필요 (NEEDS REVISION) | Developer (재구현) |

## 출력 예시

```
🔄 RESUMING CONTEXT (from .claude/state/checkpoints/20260424-1430-login-api.md)
  제목: login-api-scaffold
  브랜치: feature/F002-login
  Feature: F002 (in-progress)
  마지막 에이전트: developer

📊 LEARNINGS: 12 entries (patterns: 5, pitfalls: 4, architecture: 3)
  최근: jwt-expiry-1h (conf 8/10), bcrypt-salt-env-var (conf 9/10)

▶ 다음 작업: F002 사용자 로그인 (status: review → Reviewer 대기)
  관련 학습 2건 매칭됨 — /project:learn search login

  추천: Reviewer 에이전트 호출
```
