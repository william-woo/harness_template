# 🧰 프로젝트 하네스 가이드

> 이 파일은 Claude Code가 이 프로젝트를 이해하고 올바르게 작동하기 위한 핵심 가이드입니다.
> **팀원 모두 이 파일을 읽고 프로젝트 시작 전 반드시 설정을 완료하세요.**

---

## 📋 프로젝트 개요

<!-- TODO: 프로젝트 시작 시 아래 항목을 채워주세요 -->
- **프로젝트명**: [프로젝트명]
- **목적**: [한 줄 설명]
- **기술 스택**: [언어, 프레임워크, DB 등]
- **팀 규모**: [N명]
- **목표 완료일**: [YYYY-MM-DD]

---

## 🗂️ 디렉토리 구조

```
project-root/
├── CLAUDE.md                 # ← 지금 읽는 파일 (하네스 루트)
├── claude-progress.txt       # 에이전트 세션 간 인계 파일 (자동 관리)
├── feature_list.json         # 기능 목록 및 진행 상태 (자동 관리)
├── .claude/
│   ├── settings.json         # 훅 설정 (Claude Code 공식 위치)
│   ├── agents/               # 전문 에이전트 정의
│   │   ├── planner.md        # 기획 에이전트
│   │   ├── architect.md      # 아키텍처 에이전트
│   │   ├── developer.md      # 개발 에이전트
│   │   ├── reviewer.md       # 코드 리뷰 에이전트
│   │   └── qa.md             # QA/검증 에이전트
│   ├── skills/               # 재사용 스킬
│   │   ├── planning/SKILL.md
│   │   ├── coding/SKILL.md
│   │   ├── testing/SKILL.md
│   │   ├── design-review/SKILL.md  # 디자인 감사 스킬 (F007)
│   │   └── qa-browser/SKILL.md     # QA 브라우저 자동화 스킬 (F008)
│   ├── host.json             # 멀티 호스트 SSOT — agent_type 저장 (F006)
│   ├── commands/             # 커스텀 슬래시 커맨드
│   │   ├── init-project.md
│   │   ├── start-session.md
│   │   ├── handoff.md
│   │   ├── host.md           # /project:host — 호스트 전환/조회 (F006)
│   │   ├── design-review.md  # /project:design-review — 디자인 감사 (F007)
│   │   ├── qa-browser.md     # /project:qa-browser — QA 브라우저 자동화 (F008)
│   │   └── status.md
│   ├── hooks/                # 훅 스크립트 (settings.json에서 참조)
│   │   ├── pre-bash-check.sh
│   │   ├── pre-write-check.sh
│   │   ├── post-write-check.sh
│   │   └── session-end.sh
│   ├── bin/                  # Python 헬퍼 스크립트
│   │   ├── brain.py          # cross-project 지식 베이스 (F005)
│   │   ├── host.py           # 멀티 호스트 CLI: current/info/set/render-skills/check (F006)
│   │   └── host_adapters/    # 호스트별 어댑터 모듈 (F006)
│   │       ├── __init__.py   # 패키지 마커
│   │       ├── base.py       # HostAdapter 추상 베이스 + 토큰 카탈로그
│   │       ├── claude_code.py  # 기본 어댑터 (실동작)
│   │       ├── openclaw.py   # stub 어댑터
│   │       └── codex.py      # stub 어댑터
│   └── rules/                # 팀 규칙
│       ├── coding-standards.md
│       └── git-conventions.md
├── src/                      # 소스 코드
│   └── harness_template/     # 배포용 하네스 템플릿 (별도 git repo)
│       ├── claude/           #   ⓐ baseline — Phase 0 스냅샷 (수정 X)
│       ├── claude.gstack/    #   ⓑ ★ 메인 — 모든 phase 산출물의 정합 사본
│       └── openai/           #   ⓒ Codex 호스트 변형 (.codex/ 구조)
├── tests/                    # 테스트
│   └── e2e/                  # E2E 테스트 스크립트 (Playwright — F008)
│       └── _template.spec.ts # qa-browser 스크립트 템플릿 예시
└── docs/                     # 문서
    ├── adr/                  # 아키텍처 결정 기록 (ADR-NNN-*.md)
    └── design/               # 상세 설계 문서 (FNNN-*.md)
```

---

## 🔁 harness_template 동기화 정책

이 프로젝트는 자기 자신이 곧 "배포할 하네스"입니다. 따라서 `.claude/`,
`docs/adr/`, `CLAUDE.md` 같은 산출물을 변경할 때마다 메인 템플릿
`src/harness_template/claude.gstack/harness/`에 **즉시 미러링** 해야 합니다.

**동기화 대상:**
- `.claude/{agents,commands,hooks,skills,bin,rules}/` — 전체 미러
- `CLAUDE.md`, `docs/adr/*.md` — 전체 미러

**동기화 제외:**
- `.claude/state/` (checkpoints, learnings.jsonl, analytics.jsonl, freeze-dir.txt)
  — 프로젝트 로컬 상태이므로 템플릿에 들어가면 안 됨
- `feature_list.json` — 프로젝트별로 다르므로 템플릿엔 데모 샘플 유지
- `claude-progress.txt` — 세션 인계용
- `__pycache__/`, `*.pyc` — Python 캐시 — 환경별로 다르므로 미러에 들어가면 안 됨

**권장 미러링 명령**:

```bash
rsync -a --exclude='__pycache__' --exclude='*.pyc' --exclude='state/' \
  .claude/ src/harness_template/claude.gstack/harness/.claude/
```

**`claude/` (baseline)은 의도적으로 동결**: Phase 0 (F001 시작 전) 스냅샷.
변경 금지. 신규 phase는 `claude.gstack/`에만 반영.
> **예외**: Karpathy 4원칙(Think Before Coding / Simplicity First / Surgical Changes / Goal-Driven Execution) 같은 phase-agnostic 보편 디시플린은 baseline에도 동기화한다.

**`openai/` 변형**: F006 세션 2에서 수동 생성된 정적 산출물 (Codex 호스트용 .codex/ 구조).
직접 손대지 말 것 — codex 어댑터가 실구현되는 후속 phase에서 render-skills로 자동 재생성 가능해진다.
> **예외**: Karpathy 4원칙처럼 phase-agnostic 보편 디시플린은 openai/.codex/에도 수동 동기화 (코드 어댑터 실구현 전까지 일관성 확보).

---

## ⚡ 빠른 시작

### 새 프로젝트 시작 (초기화)
```
/project:init
```
→ Planner 에이전트가 기능 목록 생성, 환경 셋업, 초기 커밋까지 자동 진행

### 작업 세션 시작
```
/project:start-session
```
→ 이전 진행 상황 파악 → 다음 작업 선택 → 개발 시작

### 세션 마무리 (인계)
```
/project:handoff
```
→ 진행 파일 업데이트 → git 커밋 → 다음 세션을 위한 컨텍스트 저장

### 현재 상태 확인
```
/project:status
```

### 구조화된 세션 저장/복원 (Phase 1 업그레이드)
```
/project:context-save "<제목>"   # 현재 상태를 checkpoint 파일로 저장
/project:context-restore         # 가장 최근 checkpoint 복원
```

### 프로젝트 학습 누적 (Phase 1 업그레이드)
```
/project:learn                   # 최근 학습 20개 표시
/project:learn search <키워드>    # 학습 검색
/project:learn add               # 수동 학습 추가
/project:learn prune             # stale/conflict 정리
/project:learn stats             # 통계
/project:learn export            # CLAUDE.md 형식으로 내보내기
```

### 안전 모드 (Phase 1 업그레이드)
```
/project:freeze                  # 편집을 특정 디렉토리로 제한
/project:unfreeze                # 편집 경계 해제
/project:guard                   # 파괴 명령 차단 + 편집 경계 (통합)
```

### 자동화 파이프라인 (Phase 2 업그레이드)
```
/project:plan-full <요구사항>    # Planner→Architect→Reviewer 설계 체인
/project:ship                    # diff 분석 → 필요한 리뷰만 제안
/project:retro [--week|--month|--since FXXX]  # 회고 + 통계 + 학습 요약
```

### Cross-project 영구 지식 (Phase 3 업그레이드 — F005 Brain)
```
/project:brain-sync              # 현재 프로젝트를 ~/.harness/brain.db 에 동기화
/project:brain-search <질의>      # 모든 프로젝트의 learnings/ADRs/features 검색
/project:brain-search <질의> --project <slug> --type pitfall
/project:brain-stats             # 전체/프로젝트별 통계
/project:brain-list              # 등록된 프로젝트 목록
```

> Brain DB 는 사용자 홈 (`~/.harness/brain.db`, SQLite, Python stdlib) 에 저장된다.
> 외부 의존성 0, 옵셔널 — 호출하지 않으면 하네스 동작에 영향 없음.

### 디자인 감사 (Phase 4 업그레이드 — F007)

```
/project:design-review                       # 다운스트림 UI·문서 감사 (기본)
/project:design-review --scope=downstream --target=<경로>  # 특정 경로만
/project:design-review --scope=self          # 하네스 자체 정합성 감사
/project:design-review --rerun=BLOCK-XX      # 특정 BLOCK 항목 재검사
```

> design-review는 **읽기 전용** 감사 도구다. 코드를 수정하지 않으며, BLOCK 이슈는
> Developer 에이전트에 1건씩 원자적으로 위임한다.
> Reviewer(코드·보안·성능) → design-review(IA·A11Y·일관성) 순서로 실행한다.

### QA 브라우저 자동화 (Phase 4 업그레이드 — F008)

```
/project:qa-browser                        # 현재 호스트 + Playwright 감지
/project:qa-browser --scope=downstream     # downstream 프로젝트 QA (기본)
/project:qa-browser --feature=F001         # 특정 feature acceptance_criteria → Playwright 변환
/project:qa-browser --scope=self           # 하네스 자체 커맨드 IA·일관성 점검
/project:qa-browser --rerun=BLOCK-01       # 특정 BLOCK 재실행
```

> **필요 조건**: `npx playwright install` (선택적 의존성)
> 미설치 시 `python3 .claude/bin/qa_browser.py detect` → 안내 메시지 출력, 하네스 정상 동작.
> 스크린샷: `.claude/state/qa-browser/screenshots/` (gitignore)
> 실행 로그: `.claude/state/qa-browser/runs/` (gitignore)

### 산출물 정합성 헬스체크 (Phase 5 — F009)

```
/project:lint                              # 모든 검사기 실행
/project:lint --only=LINT-FL               # 특정 검사기만
/project:lint --strict                     # BLOCK 1건이라도 있으면 exit 1
/project:lint regenerate-index             # docs/index.md 갱신
/project:lint report                       # 마지막 실행 결과 재출력
```

> **호출 시점**: handoff 직전, 또는 새 feature 추가 후, 또는 ADR 작성 후.
> lint는 **거버넌스 정합성** (메타데이터·연결성) 만 검사. design-review (IA/A11Y/CON) 와 qa-browser (E2E) 와 책임 분리됨.
> 호출 안 하면 하네스 동작에 영향 없음 (옵셔널, hook-failure-tolerance).

---

### 멀티 호스트 관리 (Phase 3 업그레이드 — F006)

```
/project:host                    # 현재 호스트 정보 표시
/project:host set claude-code    # claude-code 설정 (기본값)
/project:host set openclaw       # openclaw 설정 (stub 안내 표시)
/project:host set codex          # codex 설정 (stub 안내 표시)
/project:host check              # 무결성 점검 (무회귀 확인)
```

> 호스트 감지 우선순위: 환경변수 `HARNESS_AGENT_TYPE` > `.claude/host.json` > 기본값 `claude-code`
> `.claude/settings.json` 은 절대 수정하지 않음 — Claude Code 공식 스키마 격리.
> stub 어댑터(openclaw/codex)는 차단하지 않고 안내만 출력.
> **[주의]** 현재 codex/openclaw는 stub 어댑터. `/project:host set` 으로 전환해도 `.claude/skills/SKILL.md` 본문은 변경되지 않음 (의도된 무회귀). openai/ 변형 자동 재생성은 codex 어댑터 실구현 후속 phase에서 가능.

---

## 📂 상태 파일 (.claude/state/)

Phase 1·2 업그레이드로 추가된 프로젝트 로컬 상태:

| 파일/디렉토리 | 용도 | git 포함 여부 |
|---|---|---|
| `.claude/state/checkpoints/*.md` | 구조화된 세션 인계 (`/project:context-save` 생성) | ✅ 커밋 대상 |
| `.claude/state/learnings.jsonl` | 프로젝트 학습 누적 로그 (JSONL) | ✅ 커밋 대상 |
| `.claude/state/analytics.jsonl` | handoff·session_end·review 이벤트 로그 (`/project:retro` 분석용) | ✅ 커밋 대상 |
| `.claude/state/freeze-dir.txt` | `/project:freeze` 경계 (세션 로컬) | ❌ gitignore |
| `.claude/state/qa-browser/` | qa-browser 스크린샷·실행 로그 (`/project:qa-browser` 생성) | ❌ gitignore |
| `.claude/state/qa-browser/screenshots/` | qa-browser 스크린샷 (binary — F008) | ❌ gitignore |
| `.claude/state/qa-browser/runs/` | qa-browser 실행 로그 (F008) | ❌ gitignore |
| `.claude/state/qa-browser/screenshots/.gitkeep` | 스크린샷 디렉토리 보존 마커 | ✅ 커밋 대상 |
| `.claude/state/qa-browser/runs/.gitkeep` | 실행 로그 디렉토리 보존 마커 | ✅ 커밋 대상 |
| `.claude/state/lint-last.json` | `/project:lint check` 결과 캐시 (`/project:lint report` 재출력용) | ❌ gitignore |

---

## 📝 claude-progress.txt 로그 컨벤션 (F009)

**신규 항목부터** 다음 prefix 형식을 권장:

```
## [YYYY-MM-DD HH:MM] <agent> | <짧은 제목>
... 본문 ...
```

예: `## [2026-05-21 14:30] developer | F009 세션 2 — 검사기 3종 + index`

이렇게 하면:
- `grep "^## \[" claude-progress.txt | tail -10` 으로 최근 10건 추출
- `/project:retro` 통계 향상

기존 `============================================================` 블록 형식도 호환 (마이그레이션 불필요).

---

## 🤖 에이전트 역할 분담

| 에이전트 | 트리거 | 주요 책임 |
|---|---|---|
| **Planner** | 프로젝트 초기, 기능 추가 요청 | 요구사항 분석, feature_list.json 관리, 우선순위 결정 |
| **Architect** | 새 컴포넌트 설계, 구조 변경 | 시스템 설계, 기술 선택, ADR 작성 |
| **Developer** | 실제 구현 | 코드 작성, 단위 테스트, 버그 수정 |
| **Reviewer** | 구현 완료 후 | 코드 품질, 보안, 성능 리뷰 |
| **QA** | 리뷰 통과 후 | E2E 테스트, 인수 검증, 기능 완료 마킹 |

**에이전트 호출 방법:**
```
# 특정 에이전트에게 위임
Use the planner agent to break down this feature: [기능 설명]
Use the developer agent to implement: [구현 내용]
Use the qa agent to verify: [검증 대상]
```

> **Reviewer vs design-review 분리**:
> Reviewer는 코드 품질·보안·성능을, design-review는 정보 구조·접근성·일관성을 담당한다.
> 두 도구가 동시에 필요한 경우 **Reviewer를 먼저, design-review를 나중에** 실행한다
> (동작하는 코드의 디자인을 평가하는 것이 자연스럽기 때문).

---

## 📏 필수 코딩 규칙

> **이 규칙들은 모든 에이전트가 반드시 따라야 합니다.**

### 진행 관리
- `claude-progress.txt`를 세션 시작 시 반드시 읽을 것
- `feature_list.json`의 기능 상태는 `passes` 필드만 수정 (삭제/편집 금지)
- 작업 완료 시 반드시 git commit (설명적인 커밋 메시지 사용)
- 미완성 상태로 세션 종료 금지 — 항상 mergeable 상태 유지

### 코드 품질
- 함수/클래스에 반드시 docstring 작성
- 새 기능에는 반드시 단위 테스트 포함
- PR 전 `Reviewer` 에이전트 리뷰 필수
- 기능 완료 전 `QA` 에이전트 E2E 검증 필수

### 금지 사항
- ❌ feature_list.json에서 테스트 항목 삭제
- ❌ 테스트 없이 기능 완료 마킹
- ❌ 미완성 코드를 main 브랜치에 커밋
- ❌ 한 세션에서 여러 기능 동시 구현 (한 번에 하나씩)

---

## 🔨 주요 명령어

<!-- TODO: 프로젝트에 맞게 수정 -->
```bash
# 개발 서버 시작
npm run dev

# 테스트 실행
npm test

# 빌드
npm run build

# 린트
npm run lint

# 타입 체크
npm run typecheck
```

---

## 📝 세션 시작 체크리스트

에이전트가 새 세션을 시작할 때 **반드시** 다음 순서로 진행:

1. `claude-progress.txt` 읽기 (이전 세션 내용 파악)
2. `git log --oneline -10` 실행 (최근 변경 확인)
3. `feature_list.json` 읽기 (완료/미완료 기능 확인)
4. 개발 서버 실행 및 기본 동작 확인 (`init.sh`)
5. 가장 높은 우선순위의 미완료 기능 선택
6. **한 번에 하나의 기능만** 구현

---

## 📊 feature_list.json 필드 설명

| 필드 | 관리 주체 | 값 |
|---|---|---|
| `passes` | **QA 에이전트만** | `false` → `true` (절대 삭제 금지) |
| `status` | 각 에이전트 | `todo` → `in-progress` → `review` → `qa` → `done` |
| `dependencies` | Planner | 선행 Feature ID 목록 |

**status 전환 규칙:**
- `todo` → `in-progress`: Developer/Architect 세션 시작 시
- `in-progress` → `review`: Developer 구현 + 테스트 완료 시
- `review` → `qa`: Reviewer APPROVED 시
- `qa` → `done`: QA PASS 시 (passes: true와 동시)

---

## 🏗️ Architect 에이전트 호출 기준

다음 중 하나라도 해당되면 Developer 시작 전 Architect를 먼저 호출:

- 새로운 DB 테이블/스키마가 필요한 기능
- 새로운 외부 API 연동
- 기존 모듈 간 의존성 변경
- 3개 이상의 파일에 걸친 구조적 변경
- 보안/인증 관련 기능

해당 없으면 Developer가 바로 구현 시작 가능.

---

## 🎨 design-review 호출 기준

다음 중 하나라도 해당되면 `/project:design-review` 실행을 권장한다:

- UI 컴포넌트·페이지 추가 또는 수정
- 디자인 시스템 토큰·컴포넌트 변경
- 정보 구조(IA) 재배치 또는 내비게이션 변경
- 새로운 폼·인터랙션 패턴 도입
- 셀프 모드: ADR 작성·수정 후 하네스 자체 정합성 점검 시

해당 없으면 (예: 순수 로직·API·테스트만 변경) design-review 스킵 가능.
**Reviewer 리뷰가 선행**되어야 design-review가 의미 있다.

---

## 🌐 qa-browser 호출 기준

다음 중 하나라도 해당되면 `/project:qa-browser` 실행을 권장한다:

- UI 컴포넌트·페이지의 E2E 동작 검증 (로그인, 폼 제출, 라우팅 등)
- acceptance_criteria 가 "이메일/비밀번호로 로그인 가능" 같은 동작 기술 포함
- design-review (정적) 통과 후 동적 렌더링·인터랙션 추가 검증 시
- 셀프 모드: ADR-003 관련 파일 변경 후 정의 정합성 점검

해당 없으면 (예: 순수 로직·API·테스트만 변경) qa-browser 스킵 가능.
**design-review 가 먼저** 통과되어야 qa-browser 가 의미 있다.
**QA 에이전트가 qa-browser 를 호출**하는 패턴이 권장된다 (passes 권한은 QA 단독).

### QA 브라우저 호출 기준

feature의 `acceptance_criteria`에 다음 중 하나가 있으면 `/project:qa-browser` 호출:
- URL 방문 / 페이지 탐색
- 버튼 클릭 / 폼 입력 / 제출
- 화면에 텍스트 노출 여부 확인
- 스크린샷 비교
- 라우팅·네비게이션 확인

해당 없으면 단위 테스트 + Reviewer로 충분 — Playwright 불필요.

---

## 🔗 참고 문서

- [아키텍처 결정 기록](./docs/adr/)
- [코딩 컨벤션](.claude/rules/coding-standards.md)
- [Git 컨벤션](.claude/rules/git-conventions.md)
