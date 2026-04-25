# /start-session — 작업 세션 시작 (Codex CLI)

새 작업 세션을 시작할 때 호출. 이전 진행 상황을 파악하고 다음 작업을 선택한다.

---

아래 순서대로 자동으로 실행하세요.

## 실행 순서

```bash
# 1. codex-progress.txt 아카이빙 (200줄 초과 시)
LINE_COUNT=$(wc -l < codex-progress.txt 2>/dev/null || echo 0)
if [ "$LINE_COUNT" -gt 200 ]; then
  mkdir -p docs
  cat codex-progress.txt >> docs/progress-archive.txt
  tail -60 codex-progress.txt > /tmp/progress-tmp.txt
  mv /tmp/progress-tmp.txt codex-progress.txt
  echo "📁 codex-progress.txt 아카이브 완료 (docs/progress-archive.txt)"
fi

# 2. 현재 상태 파악
echo "── 최근 인계 내용 ──"
tail -40 codex-progress.txt

echo "── 최근 커밋 ──"
git log --oneline -15

echo "── 기능 목록 ──"
cat feature_list.json

# 3. 환경 확인
bash init.sh
```

## 다음 Feature 선택 규칙

`feature_list.json`에서 다음 조건을 모두 만족하는 것 중 우선순위 최상위를 선택:

1. `passes: false` — 아직 완료되지 않음
2. `status: "todo"` — 아직 작업 시작 안 됨 (`in-progress`는 재개)
3. 모든 `dependencies`의 `passes: true` — 선행 조건 완료
4. `priority: critical → high → medium → low` 순서

```
선택 즉시: feature_list.json의 해당 항목 status를 "in-progress"로 변경
↓ 그 직후:
bash .codex/scripts/post-write-check.sh
```

## 세션 시작 후 안내

선택한 기능의 정보를 출력하고, 상태에 따라 롤을 추천:

| 상태 | 권장 다음 명령 |
|---|---|
| 설계 문서 없음 | `/role architect` 먼저 |
| 설계 완료, 구현 필요 | `/role developer` |
| 구현 완료 (`status: review`) | `/role reviewer` |
| 리뷰 통과 (`status: qa`) | `/role qa` |

**출력 형식 예시:**
```
▶ 다음 작업: F002 사용자 로그인 기능 (priority: critical)
  의존성: F001 완료됨 ✅
  현재 status: todo → in-progress 로 변경됨

  권장 다음 명령:
  → /role architect   (새 DB 스키마가 필요한 기능)
```
