# ADR-005: 다운스트림 백업 동기화 (`/project:backup-sync`)

> Feature: F010 — Phase 6 다운스트림 백업 동기화
> 작성: architect 에이전트 | 날짜: 2026-06-01

## 상태

`Accepted` — 본 ADR은 사용자가 확정한 두 가지 선택 (Q1=B 공유 백업 리포 + branch-per-project,
Q2=A 수동 트리거 전용) 위에 9개 결정을 명시한다. F005 Brain · F006 host_adapters ·
F009 lint 의 **외부 의존성 0 + hook-failure-tolerance + 옵셔널 보장 + 단일 파일 헬퍼 +
서브커맨드** 패턴을 그대로 일관 유지한다.

---

## 컨텍스트

### F010 의 본질적 질문 — "우리가 수동으로 해온 백업 워크플로우" 를 다운스트림에 어떻게 보급하는가

이 프로젝트(메타 하네스)는 `github.com:william-woo/harness_backup` 리포에 **프로젝트별
브랜치 (branch-per-project)** 로 엔지니어링 산출물을 백업해왔다. 핵심 흔적:

| 사실 | 위치 | 내용 |
|---|---|---|
| 백업 리포 구조 변경 | 2026-05-18 | 디렉토리 → 프로젝트별 브랜치로 재구성. main 브랜치는 index README. |
| 마지막 정합 백업 | 2026-05-22 | `harness_update_agent` 브랜치, 13 파일, 커밋 `718c36c` (F009 완료 시점) |
| 미반영 변경 누적 | 2026-05-28 ~ 현재 | `claude.gstack.auto/` 변형 + Gatekeeper 베이스라인 + v1.1/v1.2 조정 등 — 백업 미반영 |
| 동기화 도구 | 없음 | 매 세션 끝에 사람이 `rsync + git push` 수동 실행 |

→ **자동화의 필요성이 우리 자신의 사용 흔적에서 증명된다.** 다운스트림 프로젝트는 더더욱
수동 워크플로우를 따라하기 어렵다 (브랜치 구조 변경 감지, 미반영 파일 식별, 제외 목록
관리 등).

### 다운스트림 ≠ 메타 하네스의 차이

| 항목 | 메타 하네스 (우리) | 다운스트림 |
|---|---|---|
| 백업 대상 디렉토리 | `.claude/`, `docs/`, `src/harness_template/` 외 (가공물 모두) | `.claude/`, `docs/`, `CLAUDE.md`, claude-progress, feature_list 만 |
| 자기 코드 (`src/`) | 우리에겐 `harness_template` 만 있고 그건 별도 git repo (서브 git) — 제외 자연스러움 | **`src/` 가 사용자 코드** — 절대 백업 대상 아님 |
| 백업 리포 URL | `william-woo/harness_backup` 하드코딩 | **프로젝트마다 다름** — 초기화 시 입력 받아야 |
| 백업 브랜치명 | `harness_update_agent` (디렉토리명 기반) | 자동 추출 or 사용자 지정 |

### 제약 (F009 와 동일)

- **외부 의존성 0**: Python stdlib + bash + git CLI 만 (argparse + json + pathlib +
  subprocess + datetime — F005~F009 일관)
- **무회귀**: F001~F009 의 동작은 한 비트도 바뀌지 않는다
- **에이전트 신설 금지**: F007/F008/F009 일관
- **`feature_list.json` `passes` 필드 절대 수정 불가**: QA 에이전트 단독 권한
- **`.claude/settings.json` 무수정**: Claude Code 공식 스키마 격리 (F006 ADR-001 결정 1)
- **옵셔널 보장**: 호출하지 않으면 하네스 동작에 영향 없음 (F005/F009 패턴)
- **수동 트리거 전용**: 사용자 Q2=A 결정 — handoff hook 등에서 자동 호출 안 함

### 사용자 사전 결정 (확정)

- **Q1 → B 채택**: 공유 백업 리포 + 프로젝트별 브랜치 패턴. 우리 자신의 사용 패턴 일관.
  공유 리포 URL 은 **프로젝트 초기화 시 설정** 가능해야 함.
- **Q2 → A 채택**: 수동 트리거 전용. `/project:handoff` 산문에 "권장 안내" 1줄만 추가.

---

## 결정

### 결정 1 — `backup_repo` URL 저장 위치: **`.claude/host.json` 신규 필드** (F006 SSOT 확장)

**채택**: 신규 파일을 만들지 않고 `.claude/host.json` 에 `backup` 객체 추가.

| 옵션 | 장점 | 단점 | 결정 |
|---|---|---|---|
| **(A) `.claude/host.json` 신규 필드** | F006 패턴 100% 일관 (host.json 이 이미 호스트별 메타 SSOT), 파일 수 0 증가, `harness_version` 마이그레이션 경로 활용 | host.json 의 명칭이 "host" — backup 이 직관적으로 따라붙진 않음 (mitigation: notes 필드로 안내) | **채택** |
| (B) 신규 파일 `.claude/backup.json` | 책임 분리 명확 | 파일 1개 증가, host.json 과 동기 관리 부담 (둘 다 SSOT 가 됨), F006 격리 정책 (`host.json` 은 호스트별 메타) 와 묘하게 충돌 | 매력적이나 단점 우세 |
| (C) `.claude/state/backup-config.json` | 다른 state 와 같은 위치 | state 는 **세션 로컬** + gitignore 대상 — 팀 공유 불가, 브랜치 이름이 팀마다 달라지면 안 됨 | 부적합 |

**근거**: F006 ADR-001 결정 1 에서 host.json 을 "호스트별 메타 SSOT" 로 정의하고
`harness_version: 1` 로 마이그레이션 경로를 확보했다. backup 설정도 **프로젝트별
메타데이터** 이므로 같은 SSOT 에 합치는 게 자연스럽다. 향후 `harness_version: 2` 로
올리면서 backup 필드 부재 시 자동 마이그레이션 가능.

**확장 후 host.json 형식**:

```json
{
  "agent_type": "claude-code",
  "harness_version": 2,
  "notes": "agent_type 기본값. backup 은 옵셔널 — /project:backup-sync init 으로 설정.",
  "backup": {
    "repo": "git@github.com:william-woo/harness_backup.git",
    "branch": "my-project-name",
    "last_sync": "2026-06-01T14:30:00+09:00",
    "last_sync_commit": "abc1234"
  }
}
```

**필드 의미**:

| 필드 | 필수 | 의미 |
|---|---|---|
| `backup.repo` | ✅ (백업 사용 시) | git remote URL — SSH 형식 권장 (결정 4 참조) |
| `backup.branch` | ✅ (백업 사용 시) | 프로젝트별 브랜치명 — 자동 추출 + override (결정 2 참조) |
| `backup.last_sync` | 자동 갱신 | 마지막 성공 sync ISO 타임스탬프 |
| `backup.last_sync_commit` | 자동 갱신 | 마지막 성공 sync 시 백업 리포의 HEAD short SHA |

**무회귀**: `backup` 객체 부재 시 `backup-sync` 가 친절히 안내 (결정 3 참조). 기존
host.json 만 가진 프로젝트는 어떤 영향도 없음.

**영향받는 AC**: AC1 (init 시 backup_repo 입력), AC2 (host.json 에 저장), AC8
(설정 조회·수정)

---

### 결정 2 — 백업 브랜치 명명 규칙: **하이브리드 (자동 추출 기본 + override)** (F005 brain 패턴 일관)

**채택**: F005 brain.py 의 `git_remote_as_project_slug` 패턴과 동일 — git remote URL
basename → 디렉토리명 → 사용자 입력 우선순위.

| 옵션 | 장점 | 단점 | 결정 |
|---|---|---|---|
| (A) 사용자 직접 입력 전용 | 단순, 명시적 | 매번 입력 부담, 오타·일관성 책임 사용자에게 | 부분적 채택 (override 경로) |
| (B) 자동 추출 전용 | 입력 0, 일관성 보장 | git remote 미설정 프로젝트, 모노레포 등 예외 처리 어려움 | 부분적 채택 (기본값) |
| **(C) 하이브리드 — 자동 추출 기본 + 사용자 override** | F005 brain 패턴 100% 일관, 일반 경우 입력 0, 예외 케이스도 명시적 override 가능 | 우선순위 규칙 1개 학습 비용 | **채택** |

**추출 우선순위 (높음 → 낮음)**:

1. **사용자 명시 입력** — `python3 .claude/bin/backup.py config set-branch <name>` 또는 init 시 입력
2. **git remote URL 의 repo basename** — `git remote get-url origin` 결과의 `repo.git` 에서 `.git` 제거
   - 예: `git@github.com:user/my-app.git` → `my-app`
   - 예: `https://github.com/user/my-app` → `my-app`
3. **디렉토리 basename** — `Path.cwd().name`
   - 예: `/home/user/projects/my-app` → `my-app`

**근거**: F005 brain.py 의 동일 추출 로직이 이미 검증됨 (cross-project 식별자 안정성).
하네스 일관성 ↑. 사용자가 override 하지 않는 한 brain slug 와 backup branch 가 자연스럽게 동일.

**충돌 처리**: 자동 추출 결과가 백업 리포에 이미 다른 프로젝트 브랜치로 존재할 가능성 →
**현 phase 에선 검사하지 않음**. 사용자 책임 (결정 5 의 친절한 에러 안내로 대응).

**영향받는 AC**: AC2 (브랜치명 결정), AC3 (init 시 자동 제안)

---

### 결정 3 — `/project:init-project` 와의 연동: **별도 init 서브커맨드 + 옵셔널 + idempotent**

**채택**: `init-project.md` 를 **수정하지 않고**, `backup.py init` 서브커맨드를 만들어
**별도 호출 경로**를 제공. `init-project` 내부에서 "백업 설정은 `/project:backup-sync
init` 으로 별도 설정 가능합니다 (옵셔널)" 안내 한 줄 추가.

| 옵션 | 장점 | 단점 | 결정 |
|---|---|---|---|
| (A) init-project 내부에 backup 입력 단계 추가 (필수) | 한 번에 끝, 발견성 ↑ | 백업 미사용 프로젝트에 강제 입력 부담, 기존 init 흐름 파괴 | 무회귀 위배 |
| (B) init-project 내부에 backup 입력 단계 추가 (스킵 가능) | 발견성 + 옵셔널 양립 | init-project.md 파일이 비대화 + AskUserQuestion 분기 → 복잡도 ↑ | 부분 채택 (안내만) |
| **(C) backup.py init 별도 서브커맨드 + init-project 산문에 한 줄 안내** | 무회귀 100% (init-project 미수정), idempotent (언제든 다시 호출), F009 lint.py `regenerate-index` 가 별도 서브커맨드인 패턴 일관 | 발견성 ↓ (사용자가 `/project:backup-sync init` 을 알아야 함 — mitigation: handoff 안내 + CLAUDE.md 빠른 시작) | **채택** |

**근거**: F006 ADR-001 결정 5 의 `/project:host set` 패턴 일관 — 호스트 전환도 별도
서브커맨드로 분리되어 있다. backup 도 같은 정신.

**`backup.py init` 동작**:

```
python3 .claude/bin/backup.py init
```

대화형 입력 (`input()` 또는 환경변수 fallback — Claude Code 환경에서 stdin 입력이
어려운 경우를 위해 `--repo=<url> --branch=<name>` 플래그 병행 지원):

```
백업 리포 URL (예: git@github.com:user/harness_backup.git, 빈 값은 백업 미사용):
> git@github.com:my-team/harness_backup.git

백업 브랜치명 (Enter 시 자동 추출: my-app):
> [Enter]

✅ host.json 의 backup 필드를 업데이트했습니다.
   - repo: git@github.com:my-team/harness_backup.git
   - branch: my-app

다음: /project:backup-sync 로 첫 백업을 실행하세요.
```

**비대화형 호출** (Claude Code 환경 + CI):

```
python3 .claude/bin/backup.py init \
  --repo=git@github.com:my-team/harness_backup.git \
  --branch=my-app
```

**빈 값 (백업 미사용) 허용**: 입력 시 빈 줄 또는 `--repo=""` 시 host.json 에 `backup`
객체를 만들지 않음. `/project:backup-sync` 호출 시 친절히 "아직 설정되지 않았습니다 —
`init` 먼저" 안내.

**idempotent**: 이미 설정된 상태에서 다시 `init` 호출 시 현재 값 표시 + 변경 여부 질문.
변경 사항 없으면 no-op.

**init-project.md 수정**: "추천 (선택) 단계" 섹션에 1줄 추가:

```markdown
8. **(선택) 백업 설정** — `/project:backup-sync init` 으로 공유 백업 리포·브랜치 설정
   - 자기 코드(src/)는 제외, 하네스 산출물만 백업
   - 빈 값으로 두면 백업 미사용 (옵셔널)
```

→ 강제 X, init 본 흐름 무변화.

**영향받는 AC**: AC1 (init 연동), AC3 (init 시 자동 제안 — 안내 형태)

---

### 결정 4 — 인증 정책: **SSH 기본 + HTTPS URL 시 친절한 안내** (보안·자동 모드 일관)

**채택**: SSH 형식 (`git@github.com:user/repo.git`) 을 정식 지원. HTTPS URL 도 거부하지
않되, `.netrc` / `GH_TOKEN` 안내 메시지 출력.

| 옵션 | 장점 | 단점 | 결정 |
|---|---|---|---|
| **(A) SSH 키 가정** | 우리 작업 패턴 일관, 자동 모드 자격증명 노출 0, 키 관리는 ssh-agent 가 담당 (하네스 책임 외) | HTTPS 만 쓰는 사용자엔 진입 장벽 ↑ | **채택 (정식)** |
| (B) HTTPS + token | 환경변수로 간편 | `GH_TOKEN` 환경변수가 로그·screenshot 으로 누출 위험, `.netrc` 권한 관리 추가 부담, **자동 모드에서 자격증명 노출 우려** (사용자 강조) | 부적합 |
| **(C) 양쪽 허용 — URL 자동 감지로 분기** | 사용자 자유도 ↑ | 두 코드 경로 유지 부담, 인증 실패 진단 메시지 분기 필요 | 부분 채택 (HTTPS 도 거부 X, 안내만) |

**근거**: 사용자 의견에서 명시적으로 "SSH 패턴 일관 + 자동 모드의 자격증명 노출 우려" 가
지목됨. F008 qa-browser 의 외부 의존성 0 정책 + F005 brain hook-failure-tolerance 와도
일관 — 자격증명 환경변수에 의존하는 도구는 운영 부담이 크다.

**URL 자동 감지**:

```python
def detect_auth_mode(repo_url: str) -> str:
    if repo_url.startswith("git@") or repo_url.startswith("ssh://"):
        return "ssh"
    elif repo_url.startswith("https://"):
        return "https"
    return "unknown"
```

**HTTPS 입력 시 안내** (차단 X, 진행):

```
⚠️  HTTPS URL 이 입력되었습니다.
   - SSH 형식 권장: git@github.com:user/repo.git
   - HTTPS 사용 시 인증 방법:
     1) .netrc 파일에 credential 등록
     2) GH_TOKEN 환경변수 (또는 git credential helper)
   - 자동 모드에서 자격증명 노출에 주의하세요.
   - 계속 진행하려면 git 인증이 사전 설정되어 있어야 합니다.
```

**SSH 인증 실패 시 안내** (결정 5 의 친절한 에러 처리):

```
❌ SSH 인증 실패 — git@github.com:.../...
   확인 사항:
   1) ssh-agent 실행 중인지: ssh-add -l
   2) SSH 키가 등록되었는지: ssh -T git@github.com
   3) 리포 권한이 있는지: GitHub Settings → SSH keys
```

**영향받는 AC**: AC4 (인증 정책), AC5 (오류 안내)

---

### 결정 5 — 충돌·오류 처리: **친절한 안내 + exit 0 + ff-only + 재시도 0 + force-push 절대 금지**

**채택**: F005~F009 hook-failure-tolerance 일관 — 모든 오류는 친절한 안내 후 exit 0
(단 `--strict` 플래그 시 exit 1). git merge 는 fast-forward only, 재시도 없음, force-push
절대 금지.

| 시나리오 | 처리 | exit code |
|---|---|---|
| `backup` 객체 부재 (init 안 함) | "먼저 `/project:backup-sync init`" 안내 | 0 |
| 네트워크 실패 (git fetch timeout) | "네트워크 연결 확인 후 재시도하세요" | 0 |
| SSH 인증 실패 | 결정 4 의 SSH 안내 메시지 | 0 |
| 백업 브랜치 미존재 (원격) | "브랜치 없음 — 초기 push 로 생성합니다" → orphan 브랜치 push | 0 |
| 백업 브랜치가 ahead (원격이 더 새 커밋) | "ff-only merge 시도 → 실패 시 사용자에게 보고" | 0 (단 `--strict` 시 1) |
| 백업 브랜치 ahead + 로컬 변경도 있음 (3-way) | "수동 해결 필요 — 다음 메시지 참고" + 안내 | 0 |
| 제외 목록 누락 (예: .env 누출 직전) | **즉시 차단 + 에러** (보안 — 결정 6 참조) | 1 (보안 예외) |
| disk full / permission denied | "임시 디렉토리 쓰기 실패" 안내 | 0 |

**재시도 횟수**: **0회** (한 번 실패하면 즉시 보고). 근거: 재시도가 진단을 흐림 — 인증
실패가 일시적 네트워크 글리치인지 키 문제인지 사용자가 즉시 판단해야 함. 운영 부담 ↑
의 가치보다 낮음.

**force-push 절대 금지**: `git push --force` / `--force-with-lease` 모두 backup.py 코드에
포함시키지 않음. 사용자가 강제로 push 하고 싶으면 수동으로 git CLI 사용 (하네스는
도와주지 않음). 근거: 백업의 본질은 "복원 가능한 이력" — force push 는 이력 손실을 야기.

**ff-only merge 동작 의사코드**:

```bash
git fetch origin <backup-branch>
local_head=$(git -C $TMP_DIR rev-parse HEAD)
remote_head=$(git -C $TMP_DIR rev-parse origin/<backup-branch>)

if [ "$local_head" = "$remote_head" ]; then
    # 변경 없음 — skip
elif git -C $TMP_DIR merge-base --is-ancestor "$remote_head" "$local_head"; then
    # local 이 ahead — push 만 하면 됨
    git push origin <backup-branch>
else
    # 원격이 ahead 또는 diverged — 사용자에게 보고
    echo "⚠️  원격이 ahead 또는 diverged — 수동 해결 필요"
    exit 0  # 차단하지 않음
fi
```

**근거**: F005 hook-failure-tolerance + F008 qa-browser 의 Playwright 미설치 시 안내 ·
F009 lint 의 BLOCK 발견 시 exit 0 (`--strict` 옵션) 패턴 100% 일관.

**영향받는 AC**: AC5 (오류 안내), AC6 (force-push 금지), AC9 (옵셔널 보장)

---

### 결정 6 — 기본 제외 목록: **사용자 제안 목록 + `.git/` 명시 + harness_template 서브 git 보호**

**채택**: 사용자가 제안한 목록을 그대로 채택 + 두 가지 보강:

1. `src/harness_template/` (메타 하네스 자기 자신만 해당 — 다운스트림엔 무관) — **다운스트림
   감지 시 자동 무시** (조건부 제외)
2. **모든 `.git/` 디렉토리 (재귀)** — 백업 리포 자체의 `.git` 과 충돌 방지 + 다운스트림이
   `src/` 하위에 서브 git 을 두면 자동 보호

**전체 제외 목록**:

| 카테고리 | 패턴 | 근거 |
|---|---|---|
| **사용자 코드** | `src/` | 다운스트림 자기 코드 — 절대 백업 대상 X |
| **빌드 산출물** | `node_modules/`, `__pycache__/`, `*.pyc`, `.venv/`, `venv/`, `dist/`, `build/`, `target/`, `.next/`, `out/` | 재생성 가능 + 사이즈 ↑ |
| **보안 (BLOCK)** | `.env`, `.env.*`, `*.pem`, `*.key`, `credentials.json`, `.aws/credentials` | **자격증명 노출 방지 — 누락 시 즉시 차단 (결정 5 예외). 단, `.example/.template/.sample` 접미사는 화이트리스트 (양식 파일 — BLOCK 면제)** |
| **IDE / OS** | `.vscode/`, `.idea/`, `.DS_Store`, `Thumbs.db`, `*.swp`, `*.swo` | 환경별 차이 |
| **로그** | `*.log`, `logs/`, `npm-debug.log*` | 세션 로컬 |
| **세션 로컬 상태** | `.claude/state/freeze-dir.txt`, `.claude/state/lint-last.json` | gitignore 와 동기 (CLAUDE.md 상태 파일 표 참조) |
| **Binary state** | `.claude/state/qa-browser/screenshots/*`, `.claude/state/qa-browser/runs/*` | gitignore 일관 |
| **서브 git 보호** | `**/.git/` (재귀 — `.claude/.git/` 같은 case도) | 백업 리포의 git 과 충돌 방지 |
| **메타 하네스 한정** | `src/harness_template/` (조건부) | 다운스트림 감지 시 자동 무시 |

**메타 하네스 vs 다운스트림 감지**:

```python
def is_meta_harness() -> bool:
    """src/harness_template/ 디렉토리가 있고 그 안에 claude.gstack/ 가 있으면 메타 하네스."""
    p = Path.cwd() / "src" / "harness_template" / "claude.gstack"
    return p.is_dir()
```

다운스트림 (`is_meta_harness() == False`) 에서 `src/harness_template/` 패턴 매칭이
호출되어도 디렉토리 자체가 없으니 영향 없음.

**커밋 대상 (포함 패턴)** — 명시:

| 카테고리 | 경로 |
|---|---|
| 하네스 디렉토리 | `.claude/` (단 위 제외 패턴 제외) |
| 문서 | `docs/`, `CLAUDE.md`, `README.md` (있다면) |
| 진행/기능 | `claude-progress.txt`, `feature_list.json`, `init.sh` |
| 테스트 (있다면) | `tests/` (E2E 스크립트 — F008 qa-browser 산출물) |

**왜 .gitignore 를 그대로 따르지 않는가**: .gitignore 는 다운스트림 자기 git 리포의
무시 패턴 — 백업 리포의 무시 패턴과 다를 수 있음 (예: 다운스트림 자기 코드를 자기 git
에는 커밋하지만 백업엔 보내지 않아야 함). **backup.py 내부 제외 목록은 독립**.

**보안 BLOCK 예외 (결정 5 의 예외)**:

```
❌ BLOCK — .env 파일이 백업 대상에 포함되었습니다.
   파일: ./api/.env
   동작: 백업 중단 (자격증명 노출 위험).
   해결: 파일을 다른 위치로 이동하거나 backup.py 의 EXCLUDE_PATTERNS 에 명시 추가.
```

→ 이 한 가지만 exit 1 (다른 모든 에러는 exit 0).

**영향받는 AC**: AC7 (제외 목록), AC10 (보안)

---

### 결정 7 — `backup.py` 서브커맨드 구조: **5 서브커맨드 + F005/F009 일관**

**채택**: F005 brain.py · F009 lint.py 의 verb-based 서브커맨드 패턴 100% 일관.

| 옵션 | 장점 | 단점 | 결정 |
|---|---|---|---|
| (A) 단일 동작 (`backup.py` 만) | 호출 단순 | 설정·상태·디버그 분리 불가, 헬프 메시지 비대화 | F005/F009 패턴 일관성 깨짐 |
| **(B) 서브커맨드 (F005/F009 패턴)** | 진입점 일관, 향후 확장 (예: restore) 자연스러움 | 서브커맨드명 1개 학습 비용 | **채택** |

**서브커맨드 (5개)**:

| 서브커맨드 | 동작 | 비고 |
|---|---|---|
| `init` | host.json 의 backup 필드 초기 설정 (대화형 또는 `--repo --branch` 플래그) | 결정 3 |
| `sync` | **기본 동작** — 백업 실행. host.json 읽기 → tmp 디렉토리에 clone/checkout → rsync → commit → push | `/project:backup-sync` 가 호출하는 핵심 |
| `status` | 마지막 sync 정보 표시 (last_sync, last_sync_commit, 현재 변경 사항 미리보기) | 호출 부담 0 |
| `config` | backup 필드 조회/수정 (`config get`, `config set-repo`, `config set-branch`, `config show`) | F006 host.py `current`/`info` 패턴 일관 |
| `self` | 셀프 dry-run — 의존성 체크 (git 존재, ssh 키, host.json 파싱, 제외 목록 검증) | F007/F008/F009 셀프 모드 일관 |

**옵션** (전역):

| 옵션 | 의미 | 기본값 |
|---|---|---|
| `--strict` | 에러 발생 시 exit 1 (CI gate) | OFF (exit 0) |
| `--dry-run` | sync 시 실제 push 안 함, 미리보기만 | OFF |
| `--message=<text>` | sync 시 커밋 메시지 override | 자동 ("backup-sync: <ISO timestamp>") |
| `--format=human\|json` | 출력 형식 (F009 lint 일관) | human |

**근거**: F005 brain.py (`init/sync/search/stats/list/prune`) + F009 lint.py
(`check/regenerate-index/report/self`) 패턴 100% 일관. 단일 동작은 향후 `restore` 같은
역방향 명령 추가 시 자연스럽지 못함.

**커맨드 파일** (`/project:backup-sync`):

```
/project:backup-sync          # → backup.py sync
/project:backup-sync init     # → backup.py init
/project:backup-sync status   # → backup.py status
/project:backup-sync config show
/project:backup-sync self
```

→ `.claude/commands/backup-sync.md` 한 파일에서 위 서브커맨드 위임.

**영향받는 AC**: AC1 (커맨드), AC8 (config 조회/수정)

---

### 결정 8 — 변형 미러 전략: **`claude.gstack/` + `claude.gstack.auto/` 만 미러, baseline + openai 비동기 (F009 일관)**

**채택**: F009 ADR-004 결정 5 정신 그대로 — 거버넌스/운영 도구는 phase-agnostic 보편
디시플린이 아님. baseline (ⓐ) 동결 + openai (ⓒ) codex stub 정책 유지.

| 변형 | 동기화 여부 | 근거 |
|---|---|---|
| ⓑ `src/harness_template/claude.gstack/harness/` | ✅ **전체 미러** | 메인. F005/F006/F007/F008/F009 의 bin/ 파일 모두 여기에 있음. backup.py 도 동일. |
| ⓑ′ `src/harness_template/claude.gstack.auto/harness/` | ✅ **전체 미러** | 자율 모드 변형 (2026-05-28 신규 도입). 메인과 정합 유지. |
| ⓐ `src/harness_template/claude/harness/` (baseline) | ❌ **동기화 안 함** | Phase 0 동결. F005~F009 모두 baseline 비동기 — 일관성. (Karpathy 4원칙 같은 보편 디시플린은 예외였지만 backup-sync 는 운영 도구) |
| ⓒ `src/harness_template/openai/harness/.codex/` | ❌ **동기화 안 함** | codex 어댑터 stub (F006 ADR-001 결정 4). codex 어댑터 실구현 후속 phase 에서 자동 재생성. |

**근거**:

- **F009 결정 5 패턴 일관**: "lint 는 거버넌스 도구 — Karpathy 4원칙 같은 사고 원칙이
  아님" → backup-sync 도 운영 도구로 같은 카테고리. baseline + openai 비동기 패턴 그대로.
- **claude.gstack.auto 도 ⓑ 와 같은 메인 미러**: 2026-05-28 도입 이후 ⓑ′ 도 메인 변형으로 격상.
  체크포인트 트레일에 "claude.gstack.auto 변형 자체가 부재" 라는 문구가 있어 이번 phase 부터
  미러 정합 유지 필요.

**미러링 명령** (F009 와 동일 구조 + auto 추가):

```bash
# claude.gstack (ⓑ)
rsync -a --exclude='__pycache__' --exclude='*.pyc' --exclude='state/' \
  .claude/ src/harness_template/claude.gstack/harness/.claude/

# claude.gstack.auto (ⓑ′)
rsync -a --exclude='__pycache__' --exclude='*.pyc' --exclude='state/' \
  .claude/ src/harness_template/claude.gstack.auto/harness/.claude/
```

`docs/adr/ADR-005-*.md` 도 동일하게 두 변형에 cp.

**왜 baseline 에 Karpathy 같이 예외 동기화 안 하는가**: backup-sync 는 운영 도구이지 사고
원칙이 아님. F005 brain.py · F009 lint.py 도 baseline 에 없음 — 패턴 일관성 우선.

**영향받는 AC**: AC11 (변형 미러)

---

### 결정 9 — F010 세션 분할: **3 세션** (사용자 제안 그대로 채택)

**채택**: 사용자 제안 3 세션 분할 채택. 세션 1 이 핵심 가치 (backup-sync 실행 가능),
세션 2 가 운영 편의 (config / status / init 연동), 세션 3 이 통합 가이드.

| 세션 | 범위 | 산출물 | AC 충족 |
|---|---|---|---|
| **세션 1** | `backup.py` 코어 + `sync` 서브커맨드 + 기본 제외 목록 + `.claude/commands/backup-sync.md` 골격 + ADR-005 미러 (ⓑ + ⓑ′) | `.claude/bin/backup.py` (sync 만), `.claude/commands/backup-sync.md`, 자체 dry-run, claude.gstack + claude.gstack.auto 미러 | AC1 (커맨드 + sync), AC2 (host.json backup 객체 — 읽기만), AC4 (SSH), AC5 (오류 안내), AC6 (force-push 금지), AC7 (제외 목록), AC9 (옵셔널), AC10 (보안 BLOCK), AC11 (ⓑ + ⓑ′ 미러) |
| **세션 2** | `init` / `status` / `config` / `self` 서브커맨드 + `init-project.md` 안내 한 줄 + `handoff.md` 안내 한 줄 + `host.json` 신규 필드 문서화 | backup.py 확장 (4 서브커맨드), init-project.md 1줄, handoff.md 1줄, host.json 스키마 문서 | AC2 (host.json 쓰기 — init + config), AC3 (init 연동), AC8 (config 조회·수정) |
| **세션 3 (선택)** | CLAUDE.md 빠른 시작 + 호출 기준 박스 + 디렉토리 트리 + `docs/design/F010-backup-sync.md` 작성 (선택) + 학습 jsonl + 에러 시나리오 dry-run 테스트 + 최종 미러 정합 | CLAUDE.md 업데이트, learnings 3개 (architecture/pattern/pitfall), 미러 동기화 | AC12 (CLAUDE.md 통합), 최종 QA 준비 |

**분할 근거**:

- **세션 1 의 응집도**: `sync` 만으로도 핵심 가치 (수동 백업 자동화) 제공. host.json 의
  `backup` 객체가 없으면 친절히 안내만 — `init` 없이도 디버그 가능 (단, 실제 sync 는
  init 후에 가능). 사용자가 명시적으로 host.json 을 손으로 편집해서 첫 sync 실행 가능.
- **세션 2 의 응집도**: 4 서브커맨드 모두 운영 편의 (init/status/config/self) — 한 세션에
  몰아넣어 응집도 ↑. init-project.md / handoff.md 의 안내 1줄 추가도 함께 (작은 변경
  모음).
- **세션 3 의 선택성**: CLAUDE.md 통합·학습·design 문서·에러 dry-run — F009 세션 2 의
  "통합 단계" 가 분리된 형태. 만약 시간 부족 시 세션 3 의 일부는 QA 단계로 이관 가능
  (단, CLAUDE.md 통합은 필수 — design-review 가 self 모드로 잡을 수 있음).

**대안 — 2 세션 분할 (F009 패턴)**:

| 옵션 | 장점 | 단점 | 결정 |
|---|---|---|---|
| (A) 2 세션 (F009 패턴) | feature_list estimated 와 일관 가능 | sync + 4 부속 서브커맨드 모두 세션 1 에 몰아넣으면 세션 부하 ↑, init-project / handoff 안내까지 세션 1 에 끼면 응집도 ↓ | 부담 ↑ |
| **(B) 3 세션 (사용자 제안)** | 응집도 ↑, 세션 3 의 선택성으로 시간 유연성 ↑ | feature_list estimated_sessions 가 3 으로 명시 필요 | **채택** |
| (C) 4 세션 (각 서브커맨드 분리) | 세션 부하 최소 | 과도 분할 — init/status/config 가 모두 host.json 만 다루는 작은 변경 | 과함 |

**영향받는 AC**: 전체 세션 진행 계획 — feature_list.json 의 `estimated_sessions: 3`
필요 (Planner 가 F010 정의 시 반영).

---

## 대안 검토 (요약)

| 대안 | 장점 | 단점 | 제외 이유 |
|---|---|---|---|
| backup_repo URL 을 `.env` 같은 별도 파일로 | 자격증명 분리 자연스러움 | URL 자체는 자격증명이 아님 (SSH 키 별도 관리), 파일 1개 추가 + git 미추적 불일치 | 결정 1 |
| 브랜치명 자동 추출 안 하고 매번 입력 | 명시적 | 입력 부담 + brain 일관성 깨짐 | 결정 2 |
| init-project 내부에 백업 입력 분기 (필수) | 발견성 ↑ | 무회귀 위배, 백업 미사용 프로젝트 부담 | 결정 3 |
| HTTPS + GH_TOKEN 정식 지원 | 사용자 자유도 ↑ | 자동 모드 자격증명 노출 우려 (사용자 강조) | 결정 4 |
| 재시도 3회 (네트워크 글리치 대비) | 일시적 실패 복구 | 진단 흐림 + 운영 부담 ↑ | 결정 5 |
| force-push 옵션 추가 (`--force-with-lease`) | 충돌 시 강제 push 편의 | 백업 이력 손실 위험 — 백업의 본질 위배 | 결정 5 |
| 제외 목록을 `.backupignore` 외부 파일로 | 사용자 커스터마이징 ↑ | 파일 1개 추가 + .gitignore 와 동기 부담, F005~F009 패턴 (내부 하드코딩) 깨짐 | 결정 6 |
| 단일 동작 (서브커맨드 없음) | 호출 단순 | F005/F009 패턴 깨짐, 향후 restore 추가 어려움 | 결정 7 |
| baseline (ⓐ) + openai (ⓒ) 도 미러 | 일관성 100% | baseline 동결 + codex stub 정책 위배, F005~F009 비일관 | 결정 8 |
| 2 세션 분할 | feature_list 일관 | 세션 부하 ↑ | 결정 9 |
| 4 세션 분할 | 부하 최소 | 과도 분할 | 결정 9 |
| handoff hook 에서 backup-sync 자동 호출 | 빠뜨림 방지 | 옵셔널 보장 위배 (Q2=A 사용자 결정 위배) | 사용자 사전 결정 |

---

## 결과

### 긍정적 영향

- **F010 모든 AC 충족 예정** (AC1~AC12, 세션별 매핑은 결정 9 표 참조)
- **외부 의존성 0 정책 100% 일관** — git CLI 는 OS 표준, Python stdlib 만
- **무회귀**: F001~F009 의 동작 무수정. `.claude/settings.json` / agents/*.md / hook
  스크립트 / brain.py / host.py / lint.py 모두 그대로
- **F005/F006/F009 패턴 100% 일관**: 단일 파일 헬퍼 + 서브커맨드 + 옵셔널 + exit 0 +
  hook-failure-tolerance + 변형 미러 (ⓑ + ⓑ′)
- **사용자 경험 우선**: SSH 인증 실패 시 친절한 진단, 보안 BLOCK 만 exit 1 (자격증명
  노출 방지), force-push 절대 금지 (백업 이력 보호)
- **우리 자신의 사용 흔적이 자동화로 결정**: 2026-05-22 ~ 2026-05-28 동안 누적된 수동
  백업 부담이 본 Feature 의 가치 증명

### 부정적 영향 / 트레이드오프

- 신규 파일 3개 (`.claude/bin/backup.py`, `.claude/commands/backup-sync.md`,
  `docs/adr/ADR-005-*.md`) + 선택 1개 (`docs/design/F010-backup-sync.md`)
- host.json 스키마 확장 (`harness_version: 1 → 2`) — 기존 host.json 만 가진 프로젝트는
  자동 마이그레이션 (backup 객체 부재 시 새로 생성)
- 발견성 낮음 (`/project:backup-sync init` 을 사용자가 알아야 함) — mitigation: handoff
  + init-project 안내 + CLAUDE.md 빠른 시작
- 백업 리포 자체의 관리 책임은 사용자에게 (브랜치 충돌, 사이즈 관리, 정리) — 하네스는
  push 만 도와줌
- SSH 키 미설정 사용자 진입 장벽 — mitigation: 결정 4 의 친절한 안내 메시지
- 메타 하네스 자신 (`src/harness_template/` 보유) 의 백업 패턴이 다운스트림과 다름 →
  결정 6 의 `is_meta_harness()` 분기로 처리, 한 가지 분기 학습 비용

### 후속 조치

- [ ] (F010 세션 1) backup.py 코어 + sync 서브커맨드 + 제외 목록 + `/project:backup-sync` 골격 + ⓑ + ⓑ′ 미러
- [ ] (F010 세션 2) init / status / config / self 서브커맨드 + init-project / handoff 안내 + host.json 스키마 문서
- [ ] (F010 세션 3 선택) CLAUDE.md 통합 + 디렉토리 트리 + 학습 jsonl + 에러 dry-run + 최종 미러
- [ ] (F010 QA) `/project:backup-sync self` dry-run 1회 실행 → 모든 의존성 확인
- [ ] (F011 가칭 — 후속) `restore` 서브커맨드 — 백업 브랜치에서 특정 시점 복원
- [ ] (F012 가칭 — 후속) `diff` 서브커맨드 — 마지막 sync 와 현재 상태 비교
- [ ] (F013 가칭 — 후속) codex 어댑터 실구현 시 ⓒ 변형에도 backup.py 자동 재생성

---

## 구현 가이드 (Developer 인계용)

### 변경/신규 파일 목록

**신규 생성 (세션 1)**:

```
.claude/bin/backup.py                                # 단일 파일 헬퍼 (sync 서브커맨드)
.claude/commands/backup-sync.md                      # /project:backup-sync 슬래시 커맨드
```

**신규 생성 (세션 3 선택)**:

```
docs/design/F010-backup-sync.md                      # (선택) 제외 목록 정의 + 에러 시나리오 카탈로그 — 단일 소스
```

**수정 (세션 1~3)**:

```
.claude/bin/backup.py                                # 세션 1 → sync, 세션 2 → init/status/config/self 추가
.claude/host.json                                    # 세션 2 → harness_version 2 + backup 객체 (없으면 자동 생성)
.claude/commands/init-project.md                     # 세션 2 → "(선택) 백업 설정" 1줄 추가
.claude/commands/handoff.md                          # 세션 2 → "backup-sync 권장" 1줄 추가
CLAUDE.md                                            # 세션 3 → 빠른 시작 + 호출 기준 박스 + 디렉토리 트리
feature_list.json                                    # F010 status: todo → in-progress → review (Developer 작업 끝)
.claude/state/learnings.jsonl                        # 세션 3 → 새 학습 3개 (architecture/pattern/pitfall)
```

**미러링 (ⓑ + ⓑ′ — 결정 8)**:

```
src/harness_template/claude.gstack/harness/.claude/bin/backup.py
src/harness_template/claude.gstack/harness/.claude/commands/backup-sync.md
src/harness_template/claude.gstack/harness/.claude/commands/init-project.md
src/harness_template/claude.gstack/harness/.claude/commands/handoff.md
src/harness_template/claude.gstack/harness/CLAUDE.md
src/harness_template/claude.gstack/harness/docs/adr/ADR-005-downstream-backup-sync.md
src/harness_template/claude.gstack/harness/docs/design/F010-backup-sync.md (있다면)

src/harness_template/claude.gstack.auto/harness/.claude/bin/backup.py
src/harness_template/claude.gstack.auto/harness/.claude/commands/backup-sync.md
src/harness_template/claude.gstack.auto/harness/.claude/commands/init-project.md
src/harness_template/claude.gstack.auto/harness/.claude/commands/handoff.md
src/harness_template/claude.gstack.auto/harness/CLAUDE.md
src/harness_template/claude.gstack.auto/harness/docs/adr/ADR-005-downstream-backup-sync.md
src/harness_template/claude.gstack.auto/harness/docs/design/F010-backup-sync.md (있다면)
```

**의도적 미수정 (제약 준수)**:

```
.claude/settings.json                                # Claude Code 스키마 격리 (F006)
.claude/agents/*.md                                  # 모든 에이전트 정의 무수정
.claude/bin/brain.py                                 # F005 격리
.claude/bin/host.py, host_adapters/*.py              # F006 격리 (단, host.json 의 backup 필드는 backup.py 가 직접 읽고 씀)
.claude/bin/lint.py                                  # F009 격리
.claude/bin/qa_browser.py                            # F008 격리
.claude/skills/*/SKILL.md                            # 무수정
docs/adr/ADR-001*.md ~ ADR-004*.md                   # 기존 ADR 무수정
src/harness_template/claude/                         # baseline 동결 (결정 8)
src/harness_template/openai/                         # codex stub (결정 8)
```

### 단계별 작업 순서

#### 세션 1 — backup.py 코어 + sync + /project:backup-sync

**Step 1.1 — `.claude/bin/backup.py` 코어 골격**
- F005 brain.py 헤더 docstring 형식 모방 (서브커맨드 카탈로그 + 옵션 표 + 설계 원칙)
- argparse 서브커맨드 골격: `init`, `sync`, `status`, `config`, `self` 등록 (세션 1 에서는 `sync` 만 구현, 나머지는 NotImplementedError 또는 "세션 2 에서 구현" 안내)
- 옵션: `--strict`, `--dry-run`, `--message`, `--format=human|json`
- 경로 상수: `_PROJECT_ROOT`, `_HOST_JSON`, `_BACKUP_TMP_DIR`, `_EXCLUDE_PATTERNS`

**Step 1.2 — `EXCLUDE_PATTERNS` 상수 정의 (결정 6 그대로)**
- 카테고리별 리스트 7개 (사용자 코드 / 빌드 / 보안 / IDE / 로그 / 세션 로컬 / 서브 git)
- 보안 패턴은 별도 `SECURITY_BLOCK_PATTERNS` 로 분리 (BLOCK 시 exit 1 — 결정 5 예외)

**Step 1.3 — `cmd_sync()` 핸들러 구현**

```python
def cmd_sync(args) -> int:
    # 1. host.json 로드 + backup 객체 검증
    backup_cfg = load_backup_config()
    if not backup_cfg:
        print("⚠️  백업 미설정 — 먼저 /project:backup-sync init 실행")
        return 0

    # 2. 보안 BLOCK 패턴 사전 검사
    blocked = scan_security_blocks(_PROJECT_ROOT)
    if blocked and not args.dry_run:
        print_security_block_error(blocked)
        return 1  # 결정 5 예외 — 보안만 exit 1

    # 3. tmp 디렉토리에 백업 리포 clone (shallow, branch-only)
    tmp = setup_tmp_clone(backup_cfg["repo"], backup_cfg["branch"])

    # 4. rsync (제외 목록 적용)
    rsync_to_tmp(_PROJECT_ROOT, tmp, EXCLUDE_PATTERNS)

    # 5. git add/commit/push (ff-only)
    if args.dry_run:
        print_preview(tmp)
        return 0

    success = git_commit_and_push_ff_only(tmp, args.message)

    # 6. host.json 갱신 (last_sync + last_sync_commit)
    if success:
        update_host_json(last_sync=now_iso(), last_sync_commit=get_head_sha(tmp))

    return 0  # 항상 exit 0 (단 --strict + 실패 시 1)
```

**Step 1.4 — `rsync_to_tmp()` 구현 (제외 목록 정확히 적용)**
- Python 내장 `subprocess.run(["rsync", "-a", ...])` 사용
- `--exclude` 플래그를 EXCLUDE_PATTERNS 마다 동적 생성
- `is_meta_harness()` 검사 후 메타 하네스인 경우 `--exclude='src/harness_template'` 추가
- 보안 BLOCK 패턴 (.env 등) 도 rsync exclude 에 포함 (사전 검사 fallback)

**Step 1.5 — `git_commit_and_push_ff_only()` 구현**
- 결정 5 의 의사코드 그대로
- `git fetch origin <branch>` → 원격 존재 확인
- 브랜치 없으면 orphan branch 생성 (`git checkout --orphan <branch>`)
- ff-only merge 시도, 실패 시 친절 안내 + exit 0
- **force-push 절대 호출 안 함** (코드에 `--force` 문자열 자체 부재 검증)

**Step 1.6 — `commands/backup-sync.md` 작성**
- 다른 commands/*.md 와 동일 구조
- 본문에서 `python3 .claude/bin/backup.py <subcmd>` 호출
- 옵셔널 보장 명시: "백업 미설정 또는 호출하지 않으면 하네스 동작에 영향 없음"
- 서브커맨드 카탈로그 (세션 1 에선 `sync` 만 작동, 나머지는 "세션 2 에서 활성화" 표기)

**Step 1.7 — ADR-005 + backup.py + commands/backup-sync.md 미러링 (ⓑ + ⓑ′)**
- 결정 8 의 rsync 명령 2번 실행 (ⓑ, ⓑ′)
- 단, .claude/state/ 는 미러 제외 (CLAUDE.md 정책)

**Step 1.8 — 세션 1 자체 검증**
- `python3 .claude/bin/backup.py sync --dry-run` → host.json 에 backup 없으면 친절 안내 + exit 0
- `python3 .claude/bin/backup.py self` (세션 2 에서 활성화 안내 출력) → exit 0
- 메타 하네스 (`src/harness_template/` 존재) 에서 dry-run 시 제외 목록에 자동 포함되는지 확인

**Step 1.9 — 세션 1 핸드오프**
- `feature_list.json` F010: `status` 그대로 `in-progress`
- `/project:context-save "F010 세션 1 — backup.py sync + commands 골격 완료"`

#### 세션 2 — init / status / config / self + init-project 안내

**Step 2.1 — `cmd_init()` 구현**
- 대화형 입력 (`input()`) + `--repo`/`--branch` 플래그 병행
- HTTPS URL 입력 시 결정 4 의 안내 출력 (차단 X)
- host.json 로드 → harness_version 1 → 2 마이그레이션 (backup 객체 생성)
- 자동 추출 (결정 2 우선순위): 사용자 입력 → git remote basename → 디렉토리 basename
- idempotent: 이미 설정된 경우 현재 값 표시 + 변경 여부 질문

**Step 2.2 — `cmd_status()` 구현**
- host.json 의 backup.last_sync + last_sync_commit 출력
- `git status` 로 현재 변경 사항 미리보기 (제외 패턴 적용 후 변경된 파일 수)
- 백업 미설정 시 친절 안내

**Step 2.3 — `cmd_config()` 구현**
- 서브 액션: `show`, `get-repo`, `get-branch`, `set-repo`, `set-branch`
- F006 host.py `current`/`info` 패턴 일관
- set-* 액션은 host.json 의 backup 필드 직접 수정

**Step 2.4 — `cmd_self()` 구현 (셀프 dry-run, F007/F008/F009 일관)**
- 의존성 체크:
  - `git --version` 호출 가능 확인
  - `rsync --version` 호출 가능 확인
  - `ssh -V` 호출 가능 확인 (SSH 인증용)
  - host.json 파싱 가능 확인
  - 제외 목록 충돌 검사 (보안 패턴이 일반 제외 패턴에도 있는지)
- 모두 try/except → 결과 양식대로 출력 → exit 0

**Step 2.5 — `init-project.md` 안내 1줄 추가**
- 결정 3 의 형식 그대로
- 기존 init-project 흐름 무변화

**Step 2.6 — `handoff.md` 안내 1줄 추가**
- 예: `> 인계 후 변경이 크다면 \`/project:backup-sync\` 1회 권장 (옵셔널).`

**Step 2.7 — 세션 2 미러링 + 자체 검증**
- ⓑ + ⓑ′ 미러 재실행
- `python3 .claude/bin/backup.py init --repo=git@github.com:test/test.git --branch=test` → host.json 정상 갱신 확인
- `python3 .claude/bin/backup.py config show` → 출력 확인
- 정리 (테스트 후 backup 객체 제거 또는 실제 값으로 갱신)

#### 세션 3 (선택) — CLAUDE.md 통합 + 학습 + 최종 정합

**Step 3.1 — CLAUDE.md 빠른 시작 + 호출 기준 박스 + 디렉토리 트리**

신규 블록 (빠른 시작):

```markdown
### 다운스트림 백업 동기화 (Phase 6 업그레이드 — F010)

/project:backup-sync                     # 백업 실행 (기본 동작 = sync)
/project:backup-sync init                # 백업 리포·브랜치 초기 설정
/project:backup-sync status              # 마지막 sync 정보 + 변경 미리보기
/project:backup-sync config show         # 현재 설정 조회
/project:backup-sync self                # 셀프 dry-run (의존성 체크)
/project:backup-sync --dry-run           # sync 미리보기 (실제 push 안 함)

> backup-sync 는 옵셔널 — 호출 안 하면 하네스 동작에 영향 없음.
> 자기 코드 (src/) 는 제외, 하네스 산출물만 백업.
> 인증: SSH 권장 (git@github.com:user/repo.git). HTTPS 도 허용 (자격증명 사전 설정 필요).
```

호출 기준 박스 (design-review/qa-browser/lint 호출 기준과 같은 형식):

```markdown
### backup-sync 호출 기준

- 세션 인계 전 누적 변경이 큰 경우 (큰 ADR/feature 완료 직후)
- 백업 미반영 일수가 3일 이상
- 마지막 sync 이후 .claude/ 또는 docs/ 에 의미 있는 변경
- 옵셔널 — 호출 안 해도 하네스 동작에 영향 없음
```

**Step 3.2 — `docs/design/F010-backup-sync.md` (선택)**
- 제외 목록 정의 (결정 6 표 그대로) — 단일 소스
- 에러 시나리오 카탈로그 (결정 5 표 그대로)
- F007/F008/F009 패턴 일관

**Step 3.3 — 학습 jsonl append (3개)**
- `architecture`: "backup_repo URL 은 별도 파일이 아닌 host.json 의 backup 객체 — F006 SSOT 확장 일관성"
- `pattern`: "ff-only merge + 재시도 0 + force-push 절대 금지 — 백업 이력 보호가 자동화 편의보다 우선"
- `pitfall`: "메타 하네스 (src/harness_template/ 보유) 와 다운스트림 (src/ = 사용자 코드) 의 제외 패턴이 다름 — is_meta_harness() 분기 필수"

**Step 3.4 — 에러 시나리오 dry-run 테스트**
- backup 미설정 상태 → friendly 안내
- HTTPS URL 입력 → 안내 출력 + 계속 진행
- 보안 BLOCK 패턴 (.env 임시 생성 → dry-run → 차단 확인 → .env 삭제)
- 브랜치 미존재 → orphan branch 생성 시뮬레이션

**Step 3.5 — 최종 미러 정합 + feature_list.json 갱신**
- ⓑ + ⓑ′ 미러 최종 동기화
- `feature_list.json` F010: `status: "in-progress" → "review"`
- `/project:context-save "F010 완료 — backup-sync 5 서브커맨드 + 미러 정합"`

### 인수 기준 매핑 (잠정 — Planner 의 F010 정의 후 확정)

| AC (추정) | 충족 단계 | 비고 |
|---|---|---|
| AC1 — `/project:backup-sync` 커맨드 + `.claude/bin/backup.py` | 세션 1 Step 1.1, 1.6 | 5 서브커맨드 카탈로그 |
| AC2 — host.json backup 객체 (repo / branch / last_sync) | 세션 1 (읽기), 세션 2 (쓰기) | 결정 1 |
| AC3 — init-project 연동 (안내 1줄) | 세션 2 Step 2.5 | 결정 3 |
| AC4 — 인증 정책 (SSH 권장, HTTPS 안내) | 세션 1 (URL 검증), 세션 2 (init 안내) | 결정 4 |
| AC5 — 오류 처리 (친절 안내 + exit 0) | 세션 1 Step 1.3 | 결정 5 |
| AC6 — force-push 절대 금지 | 세션 1 Step 1.5 (코드 검증) | 결정 5 |
| AC7 — 기본 제외 목록 | 세션 1 Step 1.2 | 결정 6 |
| AC8 — config 서브커맨드 (조회·수정) | 세션 2 Step 2.3 | 결정 7 |
| AC9 — 옵셔널 보장 (자동 호출 트리거 0) | 세션 1~3 전체 | 결정 5 / 사용자 Q2=A |
| AC10 — 보안 BLOCK (.env 누출 방지) | 세션 1 Step 1.2, 1.4 | 결정 5/6 예외 |
| AC11 — 변형 미러 (ⓑ + ⓑ′) | 세션 1 Step 1.7, 세션 2 Step 2.7, 세션 3 Step 3.5 | 결정 8 |
| AC12 — CLAUDE.md 통합 + 호출 기준 + 디렉토리 트리 | 세션 3 Step 3.1 | 일관성 |

### 피해야 할 패턴

- `git push --force` / `--force-with-lease` 어떤 형태든 코드에 포함 (결정 5 위배)
- `.gitignore` 를 그대로 따라가기 (결정 6 — backup.py 는 독립 제외 목록 보유)
- `.env` 또는 `*.key` 가 rsync 결과에 들어간 채 commit (결정 5 예외 — 보안 BLOCK)
- 재시도 루프 (결정 5 — 재시도 0회)
- `HARNESS_BACKUP_TOKEN` 같은 환경변수 자격증명 의존 (결정 4 — SSH 우선)
- `.claude/settings.json` 수정 (F006 격리 — host.json 만)
- baseline (ⓐ) 또는 openai (ⓒ) 변형에 backup.py 미러 (결정 8 위배)
- `init-project.md` 본 흐름 분기 추가 (결정 3 — 안내 1줄만)
- handoff hook 에서 backup.py 자동 호출 (결정 5 / 사용자 Q2=A 위배)

---

*작성: architect 에이전트 | 날짜: 2026-06-01 | 상태: Accepted*
