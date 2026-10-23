# /project:context-save — 구조화된 컨텍스트 저장

현재 작업 상태(git 상태, 결정 사항, 남은 작업)를 구조화된 Markdown 파일로 `.claude/state/checkpoints/`에 저장한다.
`claude-progress.txt`의 평문 append 방식보다 **정확하고 검색 가능한** 세션 간 인계를 제공한다.

**HARD GATE: 이 커맨드는 코드 수정을 하지 않는다. 상태 기록만.**

## 서브커맨드

- `/project:context-save`             → **Save** (제목 자동 추론)
- `/project:context-save <제목>`      → **Save** with 제공된 제목
- `/project:context-save list`        → **List** (현재 브랜치 체크포인트)
- `/project:context-save list --all`  → **List** (모든 브랜치)

## Save 플로우

### Step 1: git 상태 수집

```bash
echo "=== BRANCH ==="
git branch --show-current 2>/dev/null

echo "=== STATUS ==="
git status --short 2>/dev/null

echo "=== DIFF STAT ==="
git diff --stat 2>/dev/null

echo "=== STAGED DIFF STAT ==="
git diff --cached --stat 2>/dev/null

echo "=== RECENT LOG ==="
git log --oneline -10 2>/dev/null

echo "=== CURRENT FEATURE ==="
# feature_list.json에서 in-progress 또는 review/qa 상태인 Feature 표시
python3 -c "
import json
try:
    with open('feature_list.json') as f:
        features = json.load(f)
    active = [f for f in features if f.get('status') in ('in-progress','review','qa')]
    for f in active:
        print(f\"{f['id']} ({f['status']}): {f['title']}\")
except Exception: pass
"
```

### Step 2: 컨텍스트 요약 작성

대화 히스토리 + 위 git 상태를 바탕으로 다음 4개 섹션을 채운다:

1. **Summary** — 고수준 목표·진행 상황 (3~5문장)
2. **Decisions Made** — 아키텍처 선택, 트레이드오프, 접근 방식과 이유
3. **Remaining Work** — 구체적인 다음 단계 (우선순위 순, 번호 매김)
4. **Notes** — 함정, 블로커, 열린 질문, 시도했지만 실패한 것들

제목은 사용자 제공값 또는 현재 작업에서 3~6단어로 추론.

### Step 3: 체크포인트 파일 작성

파일명 안전화(쉘 메타 문자 주입 방지):

```bash
CHECKPOINT_DIR="$CLAUDE_PROJECT_DIR/.claude/state/checkpoints"
mkdir -p "$CHECKPOINT_DIR"
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
RAW="${TITLE_RAW:-untitled}"
# 소문자화, 공백→하이픈, 허용 문자만, 연속 하이픈 단일화, 양끝 하이픈 제거, 60자 제한
TITLE_SLUG=$(printf '%s' "$RAW" | tr '[:upper:]' '[:lower:]' \
              | tr -s ' \t' '-' \
              | tr -cd 'a-z0-9.-' \
              | tr -s '-' \
              | sed 's/^-//;s/-$//' \
              | cut -c1-60)
TITLE_SLUG="${TITLE_SLUG:-untitled}"
FILE="$CHECKPOINT_DIR/${TIMESTAMP}-${TITLE_SLUG}.md"
# 동일 타임스탬프+제목 충돌 방지 (초 단위 이중 저장)
if [ -e "$FILE" ]; then
  SUFFIX=$(LC_ALL=C tr -dc 'a-z0-9' < /dev/urandom 2>/dev/null | head -c 4 || printf '%04x' $$)
  FILE="$CHECKPOINT_DIR/${TIMESTAMP}-${TITLE_SLUG}-${SUFFIX}.md"
fi
echo "FILE=$FILE"
```

이 `$FILE` 경로에 다음 포맷으로 Write:

```markdown
---
status: in-progress | completed | blocked
branch: <현재 브랜치명>
timestamp: 2026-04-25T14:30:00+09:00
feature_id: F002 | null
agent: developer | reviewer | qa | architect | planner | null
files_modified:
  - path/to/file1
  - path/to/file2
---

## Working on: <제목>

### Summary
<3-5 문장>

### Decisions Made
- <결정 1과 이유>
- <결정 2와 이유>

### Remaining Work
1. <우선순위 1 작업>
2. <우선순위 2 작업>

### Notes
- <함정/블로커/열린 질문>
```

`files_modified`는 `git status --short` 출력(both staged + unstaged)을 리포 루트 상대경로로 나열.

### Step 4: 확인 출력

```
✅ CONTEXT SAVED
════════════════════════════════════════
제목:       <title>
브랜치:     <branch>
파일:       <path>
수정파일:   N개
Feature:    F002 (in-progress)
════════════════════════════════════════

복원: /project:context-restore
```

## List 플로우

### Step 1: 체크포인트 수집

```bash
CHECKPOINT_DIR="$CLAUDE_PROJECT_DIR/.claude/state/checkpoints"
if [ -d "$CHECKPOINT_DIR" ]; then
  # 파일명 prefix YYYYMMDD-HHMMSS 기준 정렬 (mtime 보다 안정적)
  find "$CHECKPOINT_DIR" -maxdepth 1 -name "*.md" -type f 2>/dev/null | sort -r
else
  echo "NO_CHECKPOINTS"
fi
```

### Step 2: 테이블 출력

기본: **현재 브랜치의 체크포인트만** (각 파일 frontmatter의 `branch` 확인)

```
SAVED CONTEXTS (<current-branch> 브랜치)
════════════════════════════════════════
#  날짜         제목                    상태         Feature
─  ──────────  ───────────────────────  ───────────  ──────
1  2026-04-25  auth-refactor           in-progress  F002
2  2026-04-24  login-api-scaffold      completed    F002
3  2026-04-23  env-setup               completed    F001
════════════════════════════════════════
```

`--all` 플래그가 있으면 모든 브랜치 표시 + Branch 컬럼 추가.

체크포인트가 없으면: "저장된 컨텍스트가 없습니다. `/project:context-save`로 먼저 저장하세요."

## 중요 규칙

- **코드 수정 금지** — 이 스킬은 파일 쓰기(체크포인트 파일만)와 읽기만 한다
- **frontmatter에 항상 branch 포함** — cross-branch `/project:context-restore`의 핵심
- **Append-only** — 기존 체크포인트 덮어쓰기·삭제 금지. 매 save마다 새 파일 생성
- **추론하고 질문하지 말라** — git 상태와 대화 컨텍스트로 대부분 채움. 제목이 정말 추론 불가일 때만 AskUserQuestion
- **`claude-progress.txt`와 병행** — `/project:handoff`는 이 체크포인트를 만들고, 요약 한 줄을 `claude-progress.txt`에 append한다
