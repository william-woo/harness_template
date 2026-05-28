# /project:context-restore — 저장된 컨텍스트 복원

`/project:context-save`로 저장한 체크포인트 중 가장 최근 것(기본: 모든 브랜치 중)을 읽어, 이전 세션을 그대로 이어 받을 수 있도록 요약을 제시한다.

**HARD GATE: 이 커맨드는 코드 수정을 하지 않는다. 체크포인트 읽기만.**

**기본: 모든 브랜치의 최근 체크포인트 로드.** 브랜치가 달라도 컨텍스트를 넘겨받을 수 있도록 설계 (git worktree나 멀티 브랜치 작업 대응).

## 서브커맨드

- `/project:context-restore`                     → 가장 최근 체크포인트 로드
- `/project:context-restore <제목-조각-또는-번호>` → 특정 체크포인트 로드
- `/project:context-restore list`                → "`/project:context-save list` 를 사용하세요" 안내 후 종료

## 복원 플로우

### Step 1: 체크포인트 찾기

```bash
CHECKPOINT_DIR="$CLAUDE_PROJECT_DIR/.claude/state/checkpoints"
if [ ! -d "$CHECKPOINT_DIR" ]; then
  echo "NO_CHECKPOINTS"
else
  # 파일명 YYYYMMDD-HHMMSS prefix 기준 역정렬, 최근 20개만
  FILES=$(find "$CHECKPOINT_DIR" -maxdepth 1 -name "*.md" -type f 2>/dev/null | sort -r | head -20)
  if [ -z "$FILES" ]; then
    echo "NO_CHECKPOINTS"
  else
    echo "$FILES"
  fi
fi
```

**모든 브랜치 대상.** frontmatter의 `branch` 필드로 필터링하지 않는다 — cross-branch 이어받기가 이 커맨드의 핵심 기능.

### Step 2: 올바른 파일 로드

- 사용자가 제목 조각 또는 번호 제공 시: 후보 중 매칭되는 파일 선택
- 그렇지 않으면: `sort -r` 결과의 첫 파일 (파일명 prefix 기준 가장 최근)

Read로 파일 내용을 읽고, 요약을 다음과 같이 제시:

```
🔄 RESUMING CONTEXT
════════════════════════════════════════
제목:       <title>
브랜치:     <frontmatter의 branch>
저장 시각:  <timestamp — 사람이 읽기 쉬운 형식>
Feature:    <feature_id, 있으면>
마지막 에이전트: <agent, 있으면>
상태:       <status>
════════════════════════════════════════

### Summary
<frontmatter 아래의 Summary 섹션>

### Decisions Made
<Decisions 섹션>

### Remaining Work
<Remaining Work 섹션>

### Notes
<Notes 섹션>
```

현재 브랜치가 체크포인트의 브랜치와 다르면 추가 경고:

```
⚠️  이 체크포인트는 `<saved-branch>` 브랜치에서 저장되었습니다.
    현재 브랜치: `<current-branch>`
    이어서 작업하려면 브랜치 전환을 고려하세요:
    git checkout <saved-branch>
```

### Step 3: 다음 단계 제안

AskUserQuestion으로 다음 3가지 중 선택:

- A) **이어서 작업** — Remaining Work의 첫 번째 항목 요약 + 시작 제안
- B) **전체 파일 보기** — 체크포인트 파일 전문 출력
- C) **컨텍스트만 필요했음** — 종료

A 선택 시: Remaining Work 첫 항목을 구체적 TODO로 풀어 제시하고, 해당 작업에 어떤 에이전트가 적합한지 추천 (feature_list.json의 status 참고).

## 체크포인트가 없을 때

Step 1에서 `NO_CHECKPOINTS` 출력 시:

```
ℹ️  저장된 컨텍스트가 없습니다.
    `/project:context-save` 로 현재 상태를 먼저 저장하면
    다음 세션에서 `/project:context-restore` 로 이어받을 수 있습니다.

대체 방법: `claude-progress.txt` 를 수동으로 읽어 이전 세션 파악
```

## 중요 규칙

- **코드 수정 금지** — 체크포인트 파일 읽기와 사용자에게 요약 제시만
- **기본적으로 모든 브랜치 검색** — cross-branch 이어받기가 핵심 기능
- **"가장 최근"은 파일명 prefix `YYYYMMDD-HHMMSS` 기준** — mtime은 파일 복사·rsync로 바뀔 수 있음
- **체크포인트 파일 삭제·수정 금지** — Append-only 원칙 유지
- **`claude-progress.txt`와 보완 관계** — 체크포인트는 구조화된 상태, claude-progress는 히스토리 로그. 둘 다 읽는 것이 이상적
