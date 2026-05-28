# /project:design-review — 디자인 감사

다운스트림 프로젝트의 UI 코드·문서, 또는 하네스 자신의 정합성을 **읽기 전용**으로
감사한다. 발견된 BLOCK 이슈는 Developer에 **원자적(1건씩)** 위임한다.

**HARD GATE: design-review 자체는 코드를 수정하지 않는다. 수정은 Developer 에 위임.**

## 사용법

```
/project:design-review                                        # downstream 기본 (전체)
/project:design-review --scope=downstream --target=<경로>    # 특정 파일/디렉토리
/project:design-review --scope=self                          # 하네스 자체 정합성
/project:design-review --rerun=BLOCK-IA-6                    # 특정 항목 재검사
```

### 플래그

| 플래그 | 기본값 | 설명 |
|---|---|---|
| `--scope` | `downstream` | `downstream` \| `self` |
| `--target` | 현재 디렉토리 | 검사할 파일 또는 디렉토리 경로 |
| `--rerun` | — | 재검사할 항목 ID (예: `BLOCK-IA-6`, `BLOCK-A11Y-8`) |

## Reviewer 에이전트와의 역할 분리

| 영역 | Reviewer | design-review |
|---|---|---|
| 코드 품질·SRP·DRY·docstring | ✅ 담당 | ❌ 위임 |
| 보안 (SQLi/XSS/시크릿) | ✅ 담당 | ❌ 위임 |
| 성능 (N+1, 알고리즘) | ✅ 담당 | ❌ 위임 |
| 린트·타입체크·테스트 통과 | ✅ 담당 | ❌ 위임 |
| **정보 구조 (IA)** | ❌ | ✅ **담당** |
| **접근성 (A11y)** | ❌ | ✅ **담당** (downstream만) |
| **일관성** | ❌ | ✅ **담당** |
| **셀프 정합성** | ❌ | ✅ **담당** (--scope=self) |

**두 도구가 동시에 필요할 때**: Reviewer를 먼저, design-review를 나중에 실행한다
(동작하는 코드의 디자인을 평가하는 것이 자연스럽기 때문).

## 실행 절차

### 1단계: 스코프 결정

```bash
# downstream (기본) — 사용자 UI/문서 감사
python3 -c "
import sys, os, subprocess, json

scope = 'downstream'
target = sys.argv[1] if len(sys.argv) > 1 else '.'
print(f'[design-review] scope={scope} target={target}')
" "${TARGET:-src/}"

# self — 하네스 자체 정합성 감사
python3 -c "print('[design-review] scope=self — 하네스 정합성 검사 시작')"
```

### 2단계: 검사 실행

스킬 파일에 정의된 체크리스트를 항목별로 실행한다:

```bash
# 체크리스트 참조: .claude/skills/design-review/SKILL.md
# 원본 정의: docs/design/F007-design-review-checklist.md

# 예: A11Y-1 (img alt 누락)
grep -rn "<img" "${TARGET}" 2>/dev/null | grep -v 'alt=' | head -20

# 예: A11Y-8 (div onClick)
grep -rn "div.*onClick\|span.*onClick" "${TARGET}" 2>/dev/null | head -20

# 예: IA-S3 (ADR 경로 유효성 — self 모드)
python3 -c "
import re, os
for adr in ['docs/adr/ADR-001-multi-host.md', 'docs/adr/ADR-002-design-review.md']:
    print(f'  {adr}: {\"존재\" if os.path.exists(adr) else \"누락 — BLOCK\"}')
"
```

### 3단계: 결과 출력

결과는 아래 양식으로 출력한다 (상세 양식: SKILL.md 참조):

```markdown
## Design Review 결과: [scope] — [target]

### 결론
✅ APPROVED | 🔄 NEEDS REVISION (BLOCK N건) | ⚠️ ADVISORY (CONCERN N건)

### A. 정보 구조
### B. 접근성   ← self 모드는 "N/A — 하네스 UI 없음"
### C. 일관성

### 원자적 수정 요청
1. [BLOCK-XX] 파일:줄 — 설명 → Developer 호출 1회
```

### 4단계: 원자적 수정 루프 (BLOCK 이슈)

```
BLOCK 이슈가 있으면:
  for each BLOCK in [B1, B2, ...]:
    1. Developer 에이전트에 1건만 위임:
       "수정 대상 1건: [BLOCK 상세 설명, 파일:줄번호]
        다른 이슈는 건드리지 말 것"
    2. Developer 수정 완료 후:
       /project:design-review --rerun=[BLOCK-ID]
    3. PASS → 다음 BLOCK
       FAIL → 동일 BLOCK 재요청 (최대 3회)
       3회 실패 후 → [ESCALATION] 태그 + Planner에 Feature 재분해 요청

모든 BLOCK 처리 후:
  CONCERN 목록을 사용자에게 일괄 보고
  → 사용자가 처리 여부 결정
```

**에스컬레이션**: 같은 BLOCK이 3회 재요청 후에도 PASS 안 되면
`claude-progress.txt`에 `[ESCALATION]` 태그 기록 + Planner 에이전트에 Feature
분해 재검토 요청. (Reviewer 에이전트 에스컬레이션 패턴과 동일)

## 셀프 모드 상세 (`--scope=self`)

하네스 자체를 검사할 때 실행하는 항목:

```bash
# IA-S1: CLAUDE.md 트리 ↔ 실제 파일 일치
python3 -c "
import os, re
claude_md = open('CLAUDE.md').read()
# 코드블록 내 파일 경로 추출
paths = re.findall(r'├── (\S+\.(?:md|json|sh|py|txt))', claude_md)
for p in paths:
    print(f'  {p}: {\"OK\" if os.path.exists(p) else \"누락\"}')
"

# IA-S2: commands/*.md 전체가 CLAUDE.md에 노출되는지
python3 -c "
import os, glob
claude_md = open('CLAUDE.md').read()
cmds = glob.glob('.claude/commands/*.md')
for cmd in sorted(cmds):
    name = os.path.basename(cmd).replace('.md', '')
    found = name in claude_md
    print(f'  {name}: {\"OK\" if found else \"CONCERN — CLAUDE.md 미노출\"}')
"

# CON-S3: gstack 미러 동기화
diff -r .claude/ src/harness_template/claude.gstack/harness/.claude/ \
  --exclude="state" --exclude="host.json" 2>/dev/null \
  | head -30 | sed 's/^/  /'
```

## --rerun 재검사

특정 항목만 재실행할 때:

```bash
# BLOCK-A11Y-8 재검사
RERUN_ID="A11Y-8"
TARGET_FILE="src/components/Button.tsx"

python3 -c "
import subprocess, sys

rerun_id = '$RERUN_ID'
target = '$TARGET_FILE'

# 항목별 검사 로직 (항목 ID로 분기)
if rerun_id == 'A11Y-8':
    result = subprocess.run(
        ['grep', '-n', r'div.*onClick\|span.*onClick', target],
        capture_output=True, text=True
    )
    if result.stdout.strip():
        print(f'BLOCK — div/span onClick 여전히 존재:')
        print(result.stdout)
    else:
        print(f'PASS — {rerun_id} 해결 확인')
"
```

## 출력 예시

### downstream 예시

```
[design-review] scope=downstream target=src/components/Button.tsx
실행 시각: 2026-04-30 10:00

## Design Review 결과: downstream — src/components/Button.tsx

### 결론
🔄 NEEDS REVISION (BLOCK 1건, CONCERN 1건)

### A. 정보 구조 (N/A — 단일 컴포넌트)
모든 항목 해당 없음 (단일 컴포넌트 파일)

### B. 접근성 (7/8 통과)
| # | 항목 | 라벨 | 발견 |
|---|---|---|---|
| A11Y-1 | img alt | N/A | img 요소 없음 |
| A11Y-2 | 인터랙티브 라벨 | PASS | — |
| A11Y-8 | 의미적 HTML | BLOCK | Button.tsx:12 — div onClick 사용 |

### C. 일관성 (6/7 통과)
| # | 항목 | 라벨 | 발견 |
|---|---|---|---|
| CON-1 | 디자인 토큰 | CONCERN | 하드코딩 #ff6b35 (1건) |
| CON-3 | 명명 규칙 | PASS | — |

### 원자적 수정 요청
1. [BLOCK-A11Y-8] Button.tsx:12 — div onClick → button 태그 변경
   → Developer 호출 1회

### CONCERN 목록 (사용자 결정)
- [CONCERN-CON-1] Button.tsx 하드코딩 색상 #ff6b35 → 디자인 토큰 권장
```

### self 예시

```
[design-review] scope=self
실행 시각: 2026-04-30 10:00

## Design Review 결과: self — 하네스 자체 정합성

### 결론
✅ APPROVED

### A. 정보 구조 (IA-S1~S4)
| IA-S1 | CLAUDE.md 트리 일치 | PASS | — |
| IA-S2 | 커맨드 CLAUDE.md 노출 | PASS | 19개 모두 노출 |
| IA-S3 | ADR 경로 유효성 | PASS | — |
| IA-S4 | feature_list.json id 일관 | PASS | — |

### B. 접근성
N/A — 하네스 UI 없음 (self 모드)

### C. 일관성 (CON-S1~S3)
| CON-S1 | ADR 형식 | PASS | — |
| CON-S2 | commands 헤딩 | PASS | — |
| CON-S3 | gstack 미러 동기화 | PASS | diff 0 |
```

## 파일 위치

| 파일 | 역할 |
|---|---|
| `.claude/commands/design-review.md` | 이 파일 — 진입점·실행 절차 |
| `.claude/skills/design-review/SKILL.md` | 체크리스트·결과 양식·원자적 루프 상세 |
| `docs/design/F007-design-review-checklist.md` | 체크리스트 raw 정의 (단일 소스) |
| `docs/adr/ADR-002-design-review.md` | 설계 결정 근거 |

## 안전성

- design-review는 파일을 **읽기만** 한다 (Write/Edit 도구 사용 금지)
- 외부 패키지 없음 (grep, find, diff, python3 stdlib만)
- GPT Image API / Playwright / Pillow / cv2 미사용 (F007 비범위 — ADR-002 결정 6)
- 셀프 모드 A11Y는 N/A 처리 (하네스 UI 없음)
- 모든 처리는 try/except → 에러 시에도 검사 계속 진행 (hook-failure-tolerance 원칙)
