# /project:ship — 배포 전 리뷰 준비도 검사

`git diff`를 분석해 **이 변경에 필요한 리뷰만** 제안한다. 모든 변경에 모든 리뷰를
돌리는 비용을 줄이면서도 중요한 리뷰는 놓치지 않는 균형점.

gstack의 `/ship` 의 "Review Readiness Dashboard" 아이디어에서 영감을 얻었다.

## 사용

```
/project:ship                     # 기본: 현재 브랜치 vs 기본 브랜치(main/master)
/project:ship <base-branch>       # 명시: 지정 브랜치와 비교
/project:ship --staged            # 스테이징된 변경만
```

## 실행 순서

### Step 1: diff 수집 + 파일 분류

```bash
# 기본 브랜치 자동 감지
BASE=$(git symbolic-ref refs/remotes/origin/HEAD 2>/dev/null | sed 's@^refs/remotes/origin/@@')
BASE="${BASE:-main}"

# diff 대상 결정
if [ "$1" = "--staged" ]; then
  DIFF_FILES=$(git diff --cached --name-only)
elif [ -n "$1" ] && [ "$1" != "--staged" ]; then
  BASE="$1"
  DIFF_FILES=$(git diff --name-only "$BASE...HEAD")
else
  DIFF_FILES=$(git diff --name-only "$BASE...HEAD"; git diff --name-only)
fi

echo "=== 변경 파일 (${BASE}과 비교) ==="
echo "$DIFF_FILES" | sort -u
```

### Step 2: 카테고리 분류 (자동)

각 변경 파일을 아래 카테고리로 태그:

| 카테고리 | 패턴 (파일 경로) | 트리거되는 리뷰 |
|---|---|---|
| **UI/디자인** | `*.tsx`, `*.jsx`, `*.vue`, `*.svelte`, `*.css`, `*.scss`, `tailwind*`, `components/` | design-review |
| **보안** | `auth/`, `authz/`, `*permission*`, `*session*`, `*token*`, `*.key`, `*.pem`, `.env*` | security audit |
| **DB/마이그레이션** | `migrations/`, `schema*`, `prisma/`, `*.sql`, `models/` | DB review |
| **API/백엔드** | `routes/`, `api/`, `controllers/`, `handlers/`, `*Service.*` | API review |
| **인프라** | `Dockerfile*`, `*.tf`, `k8s/`, `deploy/`, `.github/workflows/`, `.gitlab-ci.yml` | infra review |
| **테스트** | `*.test.*`, `*.spec.*`, `tests/`, `__tests__/` | (리뷰 스킵 가능) |
| **문서** | `*.md`, `docs/`, `README*` | (리뷰 스킵 가능) |
| **설정/빌드** | `package.json`, `tsconfig*`, `*.config.*` | 기본 리뷰만 |

Python으로 분류 로직 실행:

```bash
python3 - <<'PY'
import subprocess, re, sys
files = subprocess.check_output(['git','diff','--name-only','HEAD'], text=True).strip().split('\n')
files = [f for f in files if f]

rules = [
  ('UI',          r'\.(tsx|jsx|vue|svelte|css|scss|sass|less)$|tailwind|components/'),
  ('SECURITY',    r'(auth|authz|permission|session|token)|\.(key|pem)$|\.env'),
  ('DB',          r'migrations/|schema|prisma/|\.sql$|/models/'),
  ('API',         r'routes/|/api/|controllers/|handlers/|Service\.'),
  ('INFRA',       r'Dockerfile|\.tf$|k8s/|deploy/|\.github/workflows/|\.gitlab-ci\.yml'),
  ('TEST',        r'\.(test|spec)\.|tests/|__tests__/'),
  ('DOCS',        r'\.md$|^docs/|README'),
  ('CONFIG',      r'package\.json|tsconfig|\.config\.|Makefile'),
]
cats = {}
for f in files:
    tagged = []
    for name, pat in rules:
        if re.search(pat, f, re.IGNORECASE):
            tagged.append(name)
    if not tagged: tagged = ['OTHER']
    for t in tagged: cats.setdefault(t, []).append(f)

for cat in ['UI','SECURITY','DB','API','INFRA','CONFIG','TEST','DOCS','OTHER']:
    if cat in cats:
        print(f"\n[{cat}] {len(cats[cat])}개")
        for f in cats[cat]:
            print(f"  - {f}")
PY
```

### Step 3: 리뷰 체크리스트 생성

분류 결과를 바탕으로 필요한 리뷰만 리스트:

```
📋 SHIP READINESS
════════════════════════════════════════
변경: 12 파일 (UI 4, API 3, DB 1, TEST 4)

필요한 리뷰:
  [ ] 1. Reviewer 에이전트 (기본 코드 품질)
       → Use the reviewer agent to review this branch
  [ ] 2. 디자인 리뷰 (UI 변경 있음)
       → Use the reviewer agent with focus: design
       → (또는 /project:design-review — F007 완료 후)
  [ ] 3. API 리뷰 (routes/api 변경 있음)
       → Use the reviewer agent with focus: api-contracts
  [ ] 4. DB 마이그레이션 리뷰 (schema 변경 있음)
       → Use the reviewer agent with focus: migration-safety
       → 추가: 마이그레이션 롤백 계획 확인

스킵됨:
  ✗ 보안 리뷰 (auth/authz 변경 없음)
  ✗ 인프라 리뷰 (Dockerfile/CI 변경 없음)

선택적:
  ? QA 에이전트 (E2E 검증) — acceptance_criteria 확인 필요 시
════════════════════════════════════════
```

### Step 4: Feature 상태 검증

변경에 연관된 Feature를 feature_list.json에서 조회:

```bash
python3 - <<'PY'
import json, subprocess
with open('feature_list.json') as f: features = json.load(f)
# 커밋 메시지에서 F-ID 추출
log = subprocess.check_output(['git','log','--format=%s','main..HEAD'], text=True)
import re
fids = set(re.findall(r'F\d{3}', log))
if fids:
    print("\n연관 Feature:")
    for fid in sorted(fids):
        feat = next((f for f in features if f['id']==fid), None)
        if feat:
            print(f"  - {fid} [{feat['status']}] {feat['title']}")
            if feat['status'] not in ('review','qa','done'):
                print(f"    ⚠ status가 '{feat['status']}' — Developer/Reviewer 미완료")
else:
    print("\n⚠ 커밋 메시지에 F-ID가 없음 (feat(FXXX): 형식 권장)")
PY
```

### Step 5: 차단 조건 체크

다음 중 하나라도 해당하면 ship 중단 권장:

```bash
# 미커밋 변경
UNCOMMITTED=$(git status --porcelain | wc -l)
if [ "$UNCOMMITTED" -gt 0 ]; then
  echo "🚫 미커밋 변경 $UNCOMMITTED개 — /project:handoff 먼저"
fi

# 테스트 실패 (프로젝트 CLAUDE.md의 실제 테스트 명령어 사용)
# npm test / pytest / go test 등

# 관련 Feature 중 passes:false인 것이 있으면 경고
python3 - <<'PY'
import json
with open('feature_list.json') as f: features = json.load(f)
not_ready = [f for f in features if f.get('status')=='done' and not f.get('passes')]
if not_ready:
    print(f"⚠ status=done인데 passes:false인 Feature {len(not_ready)}개")
    for f in not_ready: print(f"  - {f['id']} {f['title']}")
PY
```

### Step 6: 요약 출력 + 다음 단계

```
════════════════════════════════════════
  배포 준비 상태: ✅ READY | ⚠ NEEDS ATTENTION | 🚫 BLOCKED
════════════════════════════════════════

  미커밋: 0
  테스트: PASS (gate 기준)
  필요한 리뷰: 4 (1 완료, 3 대기)
  연관 Feature: F002 (in-progress), F003 (review)

  다음 단계:
    1. 위 리뷰 체크리스트 수행
    2. 모든 체크 완료 후 PR 생성
    3. 병합 후 /project:retro 고려
```

## 통합 포인트

- **handoff.md와 중복 방지**: `/project:handoff`는 세션 종료(wip 가능), `/project:ship`은 
  "배포 가능 상태인가" 검사. 둘은 다른 시점에 호출.
- **Reviewer 에이전트와 관계**: `/project:ship`은 무엇을 리뷰해야 하는지 제안만.
  실제 리뷰는 기존 Reviewer 에이전트 호출.
- **analytics 기록**: 실행 시 `.claude/state/analytics.jsonl`에 이벤트 append
  (F004 완료 후 활성화).

## 체크리스트

- [ ] git base 브랜치 올바르게 감지
- [ ] 파일 카테고리 분류 정확 (False positive 최소화)
- [ ] 스킵된 리뷰 근거 명시 (왜 불필요한지)
- [ ] 연관 Feature 상태 검증
- [ ] 차단 조건 체크 (미커밋·테스트 실패·status 불일치)
