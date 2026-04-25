# 하네스 엔지니어링 템플릿 사용 가이드

> `harness-template-v3`를 사용해 Claude Code 멀티 에이전트 프로젝트를 시작하고 운영하는 방법을 단계별로 설명합니다.

---

## 목차

**기본 운영 (모든 프로젝트 공통)**
1. [하네스 엔지니어링이란](#1-하네스-엔지니어링이란)
2. [전체 워크플로우 한눈에 보기](#2-전체-워크플로우-한눈에-보기)
3. [파일 구조 이해하기](#3-파일-구조-이해하기)
4. [PHASE 1 — 프로젝트 최초 세팅 (1회만)](#4-phase-1--프로젝트-최초-세팅-1회만)
5. [PHASE 2 — 매 세션 시작](#5-phase-2--매-세션-시작)
6. [PHASE 3 — 기능 개발 사이클](#6-phase-3--기능-개발-사이클)
7. [PHASE 4 — 매 세션 종료](#7-phase-4--매-세션-종료)
8. [에이전트 역할과 호출 방법](#8-에이전트-역할과-호출-방법)
9. [핵심 파일 관리 규칙](#9-핵심-파일-관리-규칙)
10. [팀원 온보딩](#10-팀원-온보딩)

**업그레이드 — gstack 기반 추가 기능**
12. [PHASE 1 업그레이드 — Safety / Learn / Context](#12-phase-1-업그레이드--safety--learn--context)
13. [PHASE 2 업그레이드 — Autoplan / Ship / Retro](#13-phase-2-업그레이드--autoplan--ship--retro)
14. [PHASE 3 업그레이드 — Brain (Cross-project 영구 지식)](#14-phase-3-업그레이드--brain-cross-project-영구-지식)

**기타**
15. [자주 묻는 질문](#15-자주-묻는-질문)

---

## 1. 하네스 엔지니어링이란

**하네스(Harness)**는 AI 에이전트가 장시간 안정적으로 작동할 수 있도록 주변에 구축하는 환경과 규칙의 총체입니다. 에이전트 자체가 아니라, 에이전트를 둘러싼 시스템입니다.

이 템플릿이 해결하는 문제는 다음과 같습니다.

| 문제 | 해결 방법 |
|---|---|
| 새 세션마다 이전 맥락을 잃어버림 | `claude-progress.txt`로 세션 간 인계 |
| 에이전트가 여러 기능을 한꺼번에 시도 | 한 번에 Feature 하나 규칙 |
| 기능이 반쯤 구현된 채 방치됨 | `/project:handoff`로 항상 clean state 유지 |
| 테스트 없이 완료 선언 | QA 에이전트 필수 통과 게이트 |
| 매 프로젝트마다 처음부터 설정 | 이 템플릿을 복사해서 즉시 시작 |
| 팀원과 설정 공유가 어려움 | `.claude/` 폴더를 git에 포함해서 공유 |

---

## 2. 전체 워크플로우 한눈에 보기

```
┌─────────────────────────────────────────┐
│         PHASE 1 — 최초 1회              │
│                                         │
│  1. 템플릿 압축 해제                    │
│  2. Claude Code 실행                    │
│  3. /project:init  ← Planner 자동 처리 │
│     - 요구사항 질문에 답변              │
│     - init.sh, CLAUDE.md 자동 작성     │
│     - feature_list.json 자동 생성      │
└────────────────┬────────────────────────┘
                 │
                 ▼  (이후 반복)
┌─────────────────────────────────────────┐
│         PHASE 2 — 매 세션 시작          │
│                                         │
│  /project:start-session                 │
│  → 이전 인계 확인 → Feature 선택        │
└────────────────┬────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────┐
│      PHASE 3 — 기능 개발 사이클         │
│                                         │
│  [설계 필요 시] Architect 에이전트      │
│       ↓                                 │
│  Developer 에이전트 — 구현 + 테스트     │
│       ↓                                 │
│  Reviewer 에이전트 — 코드 리뷰          │
│       ↓ APPROVED                        │
│  QA 에이전트 — E2E 검증                 │
│       ↓ PASS (passes: true 자동 기록)   │
│  다음 Feature로 이동                    │
└────────────────┬────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────┐
│         PHASE 4 — 매 세션 종료          │
│                                         │
│  /project:handoff                       │
│  → 커밋 + status 업데이트               │
│  → claude-progress.txt 인계 기록        │
└─────────────────────────────────────────┘
```

---

## 3. 파일 구조 이해하기

```
project-root/
│
├── CLAUDE.md                  # Claude Code가 항상 읽는 프로젝트 가이드
├── claude-progress.txt        # 세션 간 인계 파일 — 에이전트가 자동 관리
├── feature_list.json          # 기능 목록 + 진행 상태 — 에이전트가 자동 관리
├── init.sh                    # 세션 시작 시 환경 점검 스크립트
│
└── .claude/
    ├── settings.json          # 훅 설정 (Claude Code 공식 위치)
    │
    ├── agents/                # 전문 에이전트 5개
    │   ├── planner.md         # 기획 — feature_list.json 생성/관리
    │   ├── architect.md       # 설계 — ADR 작성, 구조 설계 (Opus 모델)
    │   ├── developer.md       # 구현 — 코드 + 단위 테스트
    │   ├── reviewer.md        # 리뷰 — MUST/SHOULD/CONSIDER 분류
    │   └── qa.md              # 검증 — E2E, passes 권한 독점
    │
    ├── commands/              # 슬래시 커맨드 (Phase 1·2·3 적용 후 17개)
    │   ├── init-project.md    # /project:init       — 프로젝트 초기화
    │   ├── start-session.md   # /project:start-session — 세션 시작
    │   ├── handoff.md         # /project:handoff    — 세션 인계 (analytics append)
    │   ├── status.md          # /project:status     — 현황 대시보드
    │   ├── freeze.md          # /project:freeze     — 편집 경계 설정
    │   ├── unfreeze.md        # /project:unfreeze   — 편집 경계 해제
    │   ├── guard.md           # /project:guard      — 최대 안전 모드
    │   ├── learn.md           # /project:learn      — 프로젝트 학습 관리
    │   ├── context-save.md    # /project:context-save    — 구조화된 체크포인트
    │   ├── context-restore.md # /project:context-restore — 체크포인트 복원
    │   ├── plan-full.md       # /project:plan-full  — Autoplan 파이프라인
    │   ├── ship.md            # /project:ship       — 배포 전 리뷰 체크리스트
    │   ├── retro.md           # /project:retro      — 회고 + 통계
    │   ├── brain-sync.md      # /project:brain-sync — Cross-project 지식 동기화
    │   ├── brain-search.md    # /project:brain-search    — Cross-project 검색
    │   ├── brain-stats.md     # /project:brain-stats     — Brain 통계
    │   └── brain-list.md      # /project:brain-list      — 등록 프로젝트 목록
    │
    ├── hooks/                 # 자동 안전장치
    │   ├── pre-bash-check.sh        # 위험 명령어 차단 (rm -rf 등)
    │   ├── pre-write-check.sh       # 보호 파일 수정 경고
    │   ├── pre-edit-freeze-check.sh # freeze 경계 검증 (Phase 1)
    │   ├── post-write-check.sh      # feature_list.json 항목 삭제 차단
    │   └── session-end.sh           # 미커밋 경고 + analytics append (Phase 2)
    │
    ├── bin/                   # 헬퍼 스크립트 (Phase 3)
    │   └── brain.py           # SQLite 기반 cross-project 지식 헬퍼
    │
    ├── state/                 # 프로젝트 로컬 상태 (Phase 1·2)
    │   ├── learnings.jsonl    # 누적 학습 로그 (git 커밋)
    │   ├── analytics.jsonl    # handoff·session_end 이벤트 (git 커밋)
    │   ├── checkpoints/*.md   # 구조화된 세션 인계 (git 커밋)
    │   └── freeze-dir.txt     # 편집 경계 (gitignore — 세션 로컬)
    │
    ├── skills/                # 에이전트용 참조 스킬
    │   ├── planning/SKILL.md
    │   ├── coding/SKILL.md
    │   └── testing/SKILL.md
    │
    └── rules/                 # 팀 규칙 문서
        ├── coding-standards.md
        └── git-conventions.md
```

> **Phase 1·2·3 업그레이드 (gstack 기반)**: 17개 커맨드 중 13개는 Phase 1·2·3 추가분.
> 자세한 사용법은 §12 (Safety / Learn / Context), §13 (Autoplan / Ship / Retro),
> §14 (Brain) 참조.

### 사람이 직접 건드릴 파일 vs 에이전트가 관리하는 파일

| 파일 | 관리 주체 | 역할 |
|---|---|---|
| `CLAUDE.md` | `/project:init` 시 Planner가 작성 | Claude Code 동작 기준 |
| `init.sh` | `/project:init` 시 Planner가 작성 | 세션 시작 환경 점검 |
| `feature_list.json` | Planner(생성), 각 에이전트(status), QA(passes) | 기능 진행 현황 |
| `claude-progress.txt` | `/project:handoff` 시 자동 append | 세션 간 인계 내용 |
| `.claude/agents/*.md` | 사람이 필요 시 수정 | 에이전트 동작 정의 |
| `.claude/rules/*.md` | 사람이 필요 시 수정 | 팀 코딩 규칙 |

---

## 4. PHASE 1 — 프로젝트 최초 세팅 (1회만)

### Step 1. 템플릿 압축 해제

```bash
# 새 프로젝트 폴더 생성 후 압축 해제
mkdir my-project
cd my-project
unzip harness-template-v3.zip --strip-components=1
```

압축 해제 후 아래 구조가 나오면 정상입니다.

```
my-project/
├── CLAUDE.md
├── feature_list.json
├── claude-progress.txt
├── init.sh
├── .claude/
└── ...
```

### Step 2. 훅 실행 권한 부여

```bash
chmod +x .claude/hooks/*.sh
chmod +x init.sh
```

> **Windows 사용자**: WSL(Windows Subsystem for Linux) 환경에서 실행하거나, Git Bash를 사용하세요.

### Step 3. git 초기화

```bash
git init
git add .
git commit -m "chore: add harness template"
```

> `.gitignore`가 이미 포함되어 있어 `.env`, `node_modules` 등은 자동으로 제외됩니다.
> `.claude/` 폴더는 **반드시 git에 포함**해야 팀원과 공유됩니다.

### Step 4. Claude Code 실행 후 `/project:init`

Claude Code를 실행하고 아래를 입력합니다.

```
/project:init
```

Planner 에이전트가 질문을 시작합니다.

```
Planner: 프로젝트 목적이 무엇인가요?
         주요 기능을 알려주세요.
         기술 스택은 무엇인가요?
```

예시 답변:

```
FastAPI + PostgreSQL로 만드는 팀 할일 관리 앱입니다.
기능은 회원가입/로그인, 태스크 CRUD, 태스크 공유입니다.
```

이 답변 하나로 Planner 에이전트가 자동으로 처리합니다.

- `CLAUDE.md` — 프로젝트 정보, 기술 스택, 실제 명령어(`pytest`, `uvicorn` 등)로 채워짐
- `init.sh` — 프로젝트 언어에 맞는 빌드/테스트 명령어로 작성됨
- `feature_list.json` — 말한 기능들을 Feature로 분해해서 생성됨
- `claude-progress.txt` — 초기화 기록 작성
- 초기 git 커밋 완료

> **직접 수정이 필요한 경우**: `init.sh`를 실행해서 에러가 나면 에러 메시지를 Claude Code에 붙여넣고 "init.sh 고쳐줘"라고 하면 됩니다.

### Step 5. 초기화 결과 확인

```bash
bash init.sh
```

```
🚀 개발 환경 초기화 중...
📦 의존성 확인... ✅
🔑 환경변수 확인... ✅
🔨 빌드 확인... ✅
🧪 단위 테스트 실행... ✅
✅ 환경 준비 완료!
```

이 메시지가 나오면 세팅 완료입니다.

---

## 5. PHASE 2 — 매 세션 시작

Claude Code를 열 때마다 (다음 날, 다른 팀원이 이어받을 때 등) 가장 먼저 실행합니다.

```
/project:start-session
```

에이전트가 자동으로 다음 순서로 실행합니다.

1. `claude-progress.txt` 읽기 → 이전 세션에서 뭘 했는지 파악
2. `git log` 확인 → 최근 커밋 내역
3. `feature_list.json` 읽기 → 완료/미완료 기능 확인
4. `bash init.sh` 실행 → 빌드·테스트 정상 여부 확인
5. 다음 작업할 Feature 선택 → `status: "in-progress"`로 변경

결과 예시:

```
▶ 다음 작업: F002 사용자 로그인 기능 (priority: critical)
  의존성: F001 완료됨 ✅
  현재 status: todo → in-progress로 변경됨

  추천 에이전트:
  → 새 DB 테이블 필요 — Architect 에이전트 먼저 호출하세요
```

### Feature 선택 기준

에이전트는 `feature_list.json`에서 다음 조건을 모두 만족하는 것 중 우선순위 최상위를 선택합니다.

- `passes: false` — 아직 완료되지 않음
- `status: "todo"` — 작업 시작 전 (`"in-progress"`면 재개)
- 모든 `dependencies`가 `passes: true` — 선행 기능 완료
- `priority: critical → high → medium → low` 순서

---

## 6. PHASE 3 — 기능 개발 사이클

Feature 하나를 완료할 때까지 에이전트들이 순서대로 작업합니다.

### Step A. Architect 에이전트 — 설계 (조건부)

다음 중 하나라도 해당하면 Developer 시작 전에 먼저 호출합니다.

- 새로운 DB 테이블/스키마가 필요한 기능
- 새로운 외부 API 연동
- 기존 모듈 간 의존성 변경
- 3개 이상 파일에 걸친 구조적 변경
- 보안/인증 관련 기능

```
Use the architect agent to design the F002 login system
```

Architect 에이전트는 Opus 모델을 사용합니다 (설계 품질 우선).

에이전트가 `docs/adr/ADR-001-login-design.md`를 작성하고 Developer에게 구현 가이드를 전달합니다.

해당 사항 없는 단순 기능은 Architect를 건너뛰고 바로 Developer로 갑니다.

### Step B. Developer 에이전트 — 구현

```
Use the developer agent to implement F002
```

에이전트가 순서대로 실행합니다.

1. 설계 문서 확인 (`docs/adr/`, `docs/design/`)
2. `feature_list.json`에서 해당 항목 `status: "in-progress"` 확인
3. `git checkout -b feature/F002-login` 브랜치 생성
4. 코드 구현 (docstring 포함)
5. 단위 테스트 작성
6. 테스트 통과 확인
7. `status: "review"`로 변경
8. `git commit -m "feat(F002): 로그인 API 구현"`
9. Reviewer 에이전트 호출 안내

> **세션 중간에 끊겼다면**: 걱정하지 마세요. `/project:handoff`로 현재까지 저장하고, 다음 세션에서 `status: "in-progress"` 기준으로 자동 재개됩니다.

### Step C. Reviewer 에이전트 — 코드 리뷰

```
Use the reviewer agent to review the F002 implementation
```

에이전트가 자동화 도구를 먼저 실행합니다.

```bash
npm run lint       # 또는 flake8, golangci-lint 등
npm run typecheck  # 또는 mypy, tsc 등
npm audit          # 보안 취약점 스캔
npm test -- --coverage
```

그 다음 MUST / SHOULD / CONSIDER로 분류해서 피드백을 줍니다.

```markdown
## 코드 리뷰 결과: F002

### 결론
🔄 NEEDS REVISION

### MUST 수정사항
1. `src/auth/login.ts:42` — 비밀번호를 평문으로 저장하고 있음
   - 현재: `user.password = password`
   - 제안: `user.password = await bcrypt.hash(password, 10)`
   - 이유: 보안 취약점 (CWE-256)

### SHOULD 개선사항
1. 에러 메시지에 구체적인 이유 포함 필요

### 잘된 점
- JWT 토큰 만료 시간 설정이 적절함
```

**APPROVED** → `status: "qa"`로 변경 후 QA 에이전트로 넘어갑니다.

**NEEDS REVISION** → Developer 에이전트가 수정 후 다시 리뷰 요청합니다.

> **에스컬레이션**: 같은 Feature에서 NEEDS REVISION이 3회 이상 반복되면 `claude-progress.txt`에 `[ESCALATION]` 태그를 달고 Planner 에이전트에 Feature 재분해를 요청합니다.

### Step D. QA 에이전트 — 최종 검증

```
Use the qa agent to verify F002 is complete
```

에이전트가 `feature_list.json`의 `acceptance_criteria`를 기준으로 검증합니다.

```bash
bash init.sh                          # 환경 기동
npm test                              # 회귀 테스트
curl -X POST /api/auth/login \        # E2E 검증
  -d '{"email":"test@test.com","password":"pass123"}'
```

엣지 케이스도 확인합니다.

- 정상 케이스 (Happy Path)
- 잘못된 비밀번호 → 401 반환
- 존재하지 않는 이메일 → 404 반환
- 빈 입력 → 400 반환

**PASS** → 에이전트가 `feature_list.json`을 직접 수정합니다.

```json
"status": "qa"   →  "status": "done"
"passes": false  →  "passes": true
```

`passes: true`는 QA 에이전트만 변경할 수 있습니다. 훅이 다른 에이전트의 무단 변경을 감지하고 차단합니다.

**FAIL** → Developer 에이전트에 재작업을 요청합니다.

### Feature 상태 전환 전체 흐름

```
todo
  └─ in-progress  (Architect/Developer 시작)
       └─ review  (Developer 구현 완료)
            └─ qa  (Reviewer APPROVED)
                 └─ done  (QA PASS + passes: true)
```

---

## 7. PHASE 4 — 매 세션 종료

세션을 마무리할 때, 기능이 완료됐든 중간이든 **항상** 실행합니다.

```
/project:handoff
```

에이전트가 순서대로 처리합니다.

1. 테스트·린트 통과 확인
2. 모든 변경사항 커밋 (미완성이면 `wip` 커밋)
3. `feature_list.json` status 업데이트
4. `claude-progress.txt`에 인계 내용 기록

`claude-progress.txt`에 이런 형태로 남습니다.

```
============================================================
[2026-04-17 14:30] Developer: F002 로그인 API 구현 완료
============================================================
작업한 Feature: F002
작업 내용:
  - src/auth/login.ts 구현
  - tests/auth/login.test.ts 작성 (커버리지 95%)

현재 상태: review
feature status: in-progress → review

파일 변경:
  - 추가: src/auth/login.ts, tests/auth/login.test.ts
  - 수정: src/routes/index.ts

다음 세션 할 일:
  - [ ] Reviewer 에이전트 리뷰 요청

주의사항:
  - bcrypt salt rounds를 환경변수로 분리 예정
============================================================
```

다음 세션에서 `/project:start-session`을 실행하면 이 내용을 읽고 정확히 이어서 시작합니다.

---

## 8. 에이전트 역할과 호출 방법

### 에이전트 한눈에 보기

| 에이전트 | 모델 | 주요 권한 | 호출 시점 |
|---|---|---|---|
| **Planner** | Sonnet | feature_list.json 생성, status 관리 | 프로젝트 초기, 기능 추가 |
| **Architect** | Opus | ADR 작성, 설계 문서 | DB/API/보안 관련 기능 전 |
| **Developer** | Sonnet | 코드 작성, 테스트, 브랜치 | 실제 구현 |
| **Reviewer** | Sonnet | 읽기 전용 + Bash (lint/test) | 구현 완료 후 |
| **QA** | Sonnet | passes: true 변경 권한 | Reviewer APPROVED 후 |

### 에이전트 직접 호출

Claude Code에서 자연어로 에이전트를 지정할 수 있습니다.

```
# Planner — 기능 추가 요청
Use the planner agent to add a new feature: 알림 기능

# Architect — 특정 기능 설계
Use the architect agent to design the notification system

# Developer — 특정 Feature 구현
Use the developer agent to implement F005

# Reviewer — 구현 결과 리뷰
Use the reviewer agent to review the F005 implementation

# QA — 기능 검증
Use the qa agent to verify F005 is complete
```

### Architect를 호출해야 하는 경우

다음 중 하나라도 해당하면 Developer 시작 전 Architect를 먼저 호출합니다.

- 새로운 DB 테이블/스키마가 필요한 기능
- 새로운 외부 API 연동
- 기존 모듈 간 의존성 변경
- 3개 이상의 파일에 걸친 구조적 변경
- 보안/인증 관련 기능

해당 없으면 Developer가 바로 구현 시작해도 됩니다.

---

## 9. 핵심 파일 관리 규칙

### feature_list.json

기능 목록 파일입니다. 에이전트들이 자동으로 관리하지만, 규칙을 알고 있어야 합니다.

```json
{
  "id": "F002",
  "category": "functional",
  "priority": "critical",
  "title": "사용자 로그인",
  "description": "사용자가 이메일/비밀번호로 로그인하면 JWT 토큰을 받는다",
  "acceptance_criteria": [
    "올바른 자격증명으로 로그인 시 200 + JWT 반환",
    "잘못된 비밀번호 시 401 반환",
    "존재하지 않는 이메일 시 404 반환"
  ],
  "dependencies": ["F001"],
  "estimated_sessions": 2,
  "status": "todo",
  "passes": false
}
```

| 필드 | 변경 권한 | 규칙 |
|---|---|---|
| `passes` | **QA 에이전트만** | false → true만 허용. 삭제/되돌리기 절대 금지 |
| `status` | 각 에이전트 | todo→in-progress→review→qa→done 순서만 허용 |
| `acceptance_criteria` | Planner | 기준을 약화시키는 방향 변경 금지 |
| 항목 삭제 | **누구도 불가** | 취소된 기능은 status를 "cancelled"로만 표시 |

훅(`post-write-check.sh`)이 항목 수 감소를 자동 감지하고 차단합니다.

### claude-progress.txt

세션 간 인계 파일입니다. 에이전트가 `/project:handoff` 때마다 자동으로 append합니다.

- 직접 수정하지 마세요 — 에이전트가 관리합니다
- 파일이 200줄을 초과하면 `/project:start-session`이 자동으로 `docs/progress-archive.txt`로 아카이빙합니다
- git에 커밋되어야 팀원과 공유됩니다

### .claude/settings.json

훅 설정 파일입니다. Claude Code가 자동으로 읽습니다.

- 이 파일을 수정하면 훅 동작이 바뀝니다
- 기본 설정 그대로 사용하는 것을 권장합니다

### 훅이 자동으로 막는 것들

훅 스크립트들이 백그라운드에서 자동으로 동작합니다.

| 훅 | 차단 대상 |
|---|---|
| `pre-bash-check.sh` | `rm -rf /`, `DROP TABLE`, `git push --force`, `curl \| bash` 등 |
| `pre-bash-check.sh` | main/master 브랜치 직접 커밋 |
| `post-write-check.sh` | `feature_list.json` 항목 수 감소 (삭제 감지) |
| `pre-write-check.sh` | `.claude/settings.json` 수정 시 경고 |
| `session-end.sh` | 미커밋 변경사항 있을 때 경고 |

---

## 10. 팀원 온보딩

### 새 팀원이 합류할 때

팀원은 별도 설정 없이 git clone만 하면 됩니다.

```bash
git clone <repository-url>
cd project
chmod +x .claude/hooks/*.sh
chmod +x init.sh
```

그 다음 Claude Code를 열고 바로 시작합니다.

```
/project:start-session
```

`claude-progress.txt`를 읽고 현재까지의 진행 상황을 자동으로 파악합니다.

### 팀원과 작업을 나눌 때

`feature_list.json`의 `status` 필드로 현재 누가 뭘 하고 있는지 확인합니다.

```
/project:status
```

```
📊 전체 진행률: 3/10 (30%)
────────────────────────────────────────
  🔴 Critical : 1/3
  🟠 High     : 2/4
  🟡 Medium   : 0/3

📋 미완료 기능 (7개)
────────────────────────────────────────
  🔄 [CRITICAL ] F003: 태스크 생성 API (in-progress)
  ⬜ [CRITICAL ] F004: 태스크 목록 조회 (todo)
  👀 [HIGH     ] F005: 태스크 수정 (review)
  🧪 [HIGH     ] F006: 태스크 삭제 (qa)
```

`in-progress` 상태인 Feature는 이미 작업 중이므로 겹치지 않게 다른 Feature를 선택합니다.

### 기존 프로젝트에 하네스 적용

이미 진행 중인 프로젝트에도 적용할 수 있습니다.

```bash
# .claude/ 폴더만 복사
cp -r harness-template-v3/.claude your-project/
cp harness-template-v3/CLAUDE.md your-project/
cp harness-template-v3/init.sh your-project/
cp harness-template-v3/claude-progress.txt your-project/

# feature_list.json은 현재 남은 작업 기준으로 새로 작성
# Claude Code에서:
Use the planner agent to create feature_list.json based on our remaining work
```

---

## 12. PHASE 1 업그레이드 — Safety / Learn / Context

기본 4개 커맨드 외에, 세션 안전성과 지식 누적을 위한 9개 커맨드가 추가되었습니다.

### 12.1 안전 모드 — `/project:freeze` · `/project:unfreeze` · `/project:guard`

대규모 리팩토링 중 AI가 범위 밖 파일을 실수로 수정하는 사고를 막습니다.

```
/project:freeze                  # 디렉토리 입력 받아서 그 안만 Edit/Write 허용
/project:unfreeze                # 경계 해제
/project:guard                   # freeze + 파괴 명령 차단(이미 항상 켜진) 통합 인사이트
```

`pre-edit-freeze-check.sh` 훅이 매 Edit/Write 호출 전 `file_path`를 검사. 경계 밖이면
`exit 2`로 차단. 상태는 `.claude/state/freeze-dir.txt` (gitignore — 세션 로컬).

> **주의**: Bash로 sed/awk 쓰면 우회 가능. 보안 경계가 아닌 "실수 방지" 가드레일입니다.
> 자세한 동작은 `.claude/commands/freeze.md` 참조.

### 12.2 프로젝트 학습 누적 — `/project:learn`

세션을 거듭하면서 발견한 패턴·함정·결정 사항을 JSONL로 누적. 다음 세션의 Planner가
이를 조회해서 같은 실수를 반복하지 않습니다.

```
/project:learn                   # 최근 20개 표시 (type 별 그룹)
/project:learn search <키워드>    # key/insight 검색
/project:learn add               # 대화형 추가 (AskUserQuestion으로 type/key/insight 수집)
/project:learn prune             # stale·conflict 정리 (tombstone 추가 방식, append-only 유지)
/project:learn stats             # type 분포, 평균 confidence 등
/project:learn export            # CLAUDE.md용 Markdown 섹션 출력
```

스키마(JSONL 한 줄):
```json
{"ts":"2026-04-25T14:30:00+09:00","type":"pitfall","key":"jwt-expiry-1h",
 "insight":"...","confidence":8,"source":"reviewer","feature_id":"F002","files":[...]}
```

`type` 은 5개로 제한: `pattern` / `pitfall` / `preference` / `architecture` / `tool`.
저장 위치: `.claude/state/learnings.jsonl` (git 커밋 — 팀 공유).

**자동 기록 규칙**: 다른 에이전트들이 다음 시점에 자동 append:
- Reviewer가 MUST 이슈 → `pitfall`
- QA가 엣지케이스 회귀 → `pitfall`
- Architect가 ADR 확정 → `architecture`
- Planner가 Feature 재분해 → `preference`

### 12.3 구조화된 세션 인계 — `/project:context-save` · `/project:context-restore`

`claude-progress.txt` 의 평문 append 외에, **YAML frontmatter + 4 섹션** 의 구조화된
체크포인트를 추가로 저장합니다.

```
/project:context-save "<제목>"   # .claude/state/checkpoints/<TS>-<slug>.md 생성
/project:context-save list       # 현재 브랜치 체크포인트 목록
/project:context-restore         # 가장 최근 체크포인트 로드 (모든 브랜치 대상)
/project:context-restore list    # → /project:context-save list 안내
```

체크포인트 파일 포맷:
```markdown
---
status: in-progress | completed | blocked
branch: feature/F002-login
timestamp: 2026-04-25T14:30:00+09:00
feature_id: F002
agent: developer
files_modified: [src/auth/login.ts, ...]
---

## Working on: <제목>
### Summary           ← 3-5 문장
### Decisions Made    ← 결정 + 이유
### Remaining Work    ← 우선순위 번호 매김
### Notes             ← 함정 / 블로커 / 시도해본 것
```

파일명은 `YYYYMMDD-HHMMSS-<title-slug>.md` — mtime이 아닌 **파일명 prefix**로 정렬되므로
rsync·복사에도 안정적입니다. cross-branch resume 가능 (Conductor·worktree 작업 대응).

### 12.4 핸드오프와의 통합

`/project:handoff` 가 자동으로:
1. 위 `/project:context-save` 호출 → 구조화된 체크포인트 생성
2. `claude-progress.txt` 에 한 줄 요약 append (히스토리 로그)
3. `.claude/state/analytics.jsonl` 에 이벤트 기록 (Phase 2의 retro 용)

`/project:start-session` 은 자동으로:
1. `/project:context-restore` → 가장 최근 체크포인트 로드
2. `/project:learn stats` → 누적 학습 개수 출력
3. 선택한 Feature 키워드로 `/project:learn search` 자동 실행

---

## 13. PHASE 2 업그레이드 — Autoplan / Ship / Retro

자동화 파이프라인 3종.

### 13.1 `/project:plan-full <요구사항>` — Autoplan

Planner → Architect (조건부) → Reviewer(설계 감사) 를 자동 체이닝. Developer 시작 전에
설계 검증을 끝낸다.

```
/project:plan-full 결제 시스템 추가 — 토스페이먼츠 연동
```

내부 흐름:
1. **Step 0**: 관련 learnings 조회 (`/project:learn search`)
2. **Step 1**: Planner → Feature 분해 + feature_list.json 업데이트
3. **Step 2**: 각 Feature의 "설계 필요" 자동 판정. 다음 중 하나라도 매칭되면 Architect 호출:
   - 새 DB 스키마 / 외부 API / 보안 기능 / 3+ 파일 영향 / 모듈 의존성 변경
4. **Step 3**: Architect → ADR-XXX-*.md 작성
5. **Step 4**: Reviewer 설계 감사 → APPROVED / NEEDS REVISION
6. **Step 5**: 파이프라인 결과 요약 출력 + Developer 시작 가이드

**사용하지 말아야 할 때**: 단순 버그 수정, 1줄 typo, 긴급 hotfix — 오버헤드만 큼.

### 13.2 `/project:ship` — Review Readiness Dashboard

`git diff` 를 분석해 **이 변경에 필요한 리뷰만** 제안. 모든 리뷰를 매번 돌리지 않음.

```
/project:ship                    # 기본 브랜치(main/master) 와 비교
/project:ship develop            # 다른 base 브랜치
/project:ship --staged           # 스테이지된 변경만
```

8개 카테고리 자동 분류 (정규식, untracked 포함, `.claude/state/*` 제외):

| 카테고리 | 패턴 | 트리거되는 리뷰 |
|---|---|---|
| UI/디자인 | `*.tsx`, `*.css`, `components/` | design-review |
| 보안 | `auth/`, `*token*`, `.env*` | security audit |
| DB | `migrations/`, `*.sql`, `prisma/` | DB review |
| API | `routes/`, `/api/`, `controllers/` | API review |
| 인프라 | `Dockerfile`, `*.tf`, `.github/workflows/` | infra review |
| 테스트 | `*.test.*`, `tests/` | (스킵 가능) |
| 문서 | `*.md`, `docs/` | (스킵 가능) |
| 설정 | `package.json`, `tsconfig*` | 기본 |

출력: 필요한 리뷰 체크리스트 + 각 항목 실행 커맨드 + 차단 조건 점검 (미커밋·테스트 실패).

### 13.3 `/project:retro` — 회고 + 통계

`.claude/state/analytics.jsonl` 의 누적 이벤트를 기간별로 집계해 회고 리포트 생성.

```
/project:retro                   # 최근 7일
/project:retro --week
/project:retro --month
/project:retro --since F003      # 특정 Feature 이후
/project:retro --all
```

집계 항목:
- 완료 Feature 수
- 활동 Feature 수
- 평균 세션 시간
- 에이전트별 handoff 수
- 리뷰 반복 횟수 (3회+ 이면 ESCALATION 후보 표시)
- 최근 학습 (기간 내)

마지막에 회고 질문 3개 자동 생성. 답변은 `/project:learn add` 로 기록 권장.

이벤트는 `/project:handoff` Step 7 에서 자동 append되므로 별도 작업 불필요.

---

## 14. PHASE 3 업그레이드 — Brain (Cross-project 영구 지식)

여러 프로젝트를 오가며 작업할 때 학습·결정·기능을 통합 검색.

### 14.1 저장 위치와 격리

- **DB**: `~/.harness/brain.db` (사용자 홈, **git 미포함**)
- **백엔드**: Python stdlib `sqlite3` — 외부 의존성 0
- **헬퍼**: `.claude/bin/brain.py` (단일 파일, 568줄)
- **프로젝트별 데이터 격리**: 모든 테이블이 `project_slug` 로 분리

### 14.2 4개 커맨드

```
/project:brain-sync                          # 현재 프로젝트 → ~/.harness/brain.db
/project:brain-search <질의>                  # 모든 프로젝트 cross-search
/project:brain-search <질의> --project <slug> # 특정 프로젝트만
/project:brain-search <질의> --type pitfall   # 특정 type만
/project:brain-search "" --type architecture  # 빈 query + type 필터
/project:brain-stats                         # 전체/프로젝트별 통계
/project:brain-stats --project <slug>
/project:brain-list                          # 등록된 프로젝트 목록 + 마지막 sync 시각
```

**프로젝트 식별**: `git remote get-url origin` 의 repo basename 우선, 없으면 디렉토리명.

### 14.3 무엇을 동기화하는가

- `.claude/state/learnings.jsonl` → `learnings` 테이블 (tombstone 자동 제외)
- `feature_list.json` → `features` 테이블
- `docs/adr/ADR-*.md` → `adrs` 테이블 (제목·status·decision 파싱)

INSERT OR REPLACE 로 **idempotent** — 같은 프로젝트 재 sync 해도 중복 없음.

### 14.4 사용 시나리오

1. **새 프로젝트 시작 시**: 비슷한 문제를 다른 프로젝트에서 해결한 적 있는지 확인
   ```
   /project:brain-search "rate limit"
   ```
2. **함정 회피**: pitfall 만 골라서 검토
   ```
   /project:brain-search auth --type pitfall
   ```
3. **결정 참고**: 다른 프로젝트의 architecture 결정 확인
   ```
   /project:brain-search caching --type architecture
   ```

### 14.5 하네스 동작에 영향 없음

`/project:brain-*` 커맨드를 한 번도 호출하지 않으면 `~/.harness/` 디렉토리가 만들어지지
않습니다. brain.py 의 모든 핸들러는 try/except 로 exit 0을 보장 — 실패해도 호출자(handoff
등)를 차단하지 않습니다.

---

## 15. 자주 묻는 질문

**Q. `init.sh`와 `CLAUDE.md`를 내가 직접 수정해야 하나요?**

직접 수정하지 않아도 됩니다. `/project:init` 실행 후 Planner 에이전트가 질문에 답변하면 알아서 작성합니다. `init.sh` 실행 후 에러가 나면 에러 메시지를 Claude Code에 붙여넣고 "고쳐줘"라고 하면 됩니다.

**Q. `passes: true`를 직접 수정하고 싶어요.**

하지 마세요. 훅이 감지하고 차단하며, QA 에이전트를 통해야만 바뀝니다. 이 제약이 품질을 보장하는 핵심 메커니즘입니다.

**Q. Feature가 생각보다 너무 크면 어떻게 하나요?**

Planner 에이전트에게 분해를 요청합니다.

```
Use the planner agent to break down F003 into smaller features
```

또는 같은 Feature에서 NEEDS REVISION이 3회 반복되면 에스컬레이션이 자동으로 발동되어 분해를 권장합니다.

**Q. Architect 에이전트 없이 Developer만 써도 되나요?**

단순한 기능은 가능합니다. 단, DB 스키마·외부 API·보안 기능에서 Architect를 건너뛰면 나중에 큰 리팩토링이 필요해질 수 있습니다. `CLAUDE.md`의 "Architect 호출 기준" 섹션을 참고하세요.

**Q. oh-my-claudecode와 함께 써도 되나요?**

네. OMC의 `autopilot`이나 `ralph` 모드와 이 하네스를 함께 사용할 수 있습니다. OMC가 에이전트 병렬 실행을 담당하고, 이 하네스가 품질 게이트를 담당합니다.

**Q. 훅이 정상 명령어를 잘못 차단하면 어떻게 하나요?**

`.claude/hooks/pre-bash-check.sh`의 `DANGEROUS_PATTERNS` 배열에서 해당 패턴을 제거하거나 조건을 수정하면 됩니다. 또는 Claude Code에 "이 훅 패턴 수정해줘"라고 요청하세요.

**Q. 새 repo 첫 커밋이 main 브랜치 차단에 걸리는데요?**

수정되었습니다. `pre-bash-check.sh` 가 `git rev-parse HEAD` 로 HEAD 존재 여부를 먼저 확인하고,
없으면 (초기 커밋) 통과시킵니다. 첫 커밋 후부터 main 보호가 작동합니다.

**Q. `/project:freeze` 와 `/project:guard` 차이는?**

`/project:freeze` 는 편집 경계만 설정. `/project:guard` 는 freeze + 파괴 명령 차단(이미 항상
켜진 기본 동작)을 한 번에 알리는 메타 커맨드. 실제 다른 점은 사용자 의도 표현뿐 — 둘 다 같은
freeze hook 을 사용합니다.

**Q. `/project:learn` 과 `/project:brain-search` 차이는?**

| | learn | brain-search |
|---|---|---|
| 범위 | **현재 프로젝트만** | **모든 프로젝트** (cross) |
| 데이터 | `.claude/state/learnings.jsonl` | `~/.harness/brain.db` |
| 사전 작업 | 없음 | 한 번 이상 `/project:brain-sync` |
| 외부 의존 | Python stdlib | Python stdlib (sqlite3) |

같은 프로젝트의 학습이라면 `learn search` 가 항상 더 빠르고 항상 최신입니다.
다른 프로젝트의 결정이 궁금할 때만 `brain-search` 사용.

**Q. `/project:plan-full` 은 항상 써야 하나요?**

아닙니다. **단순 버그 수정·typo·hotfix 에는 오버헤드만 큽니다.** 새 Feature 추가나
구조적 변경이 있을 때만 권장. 기존 `/project:start-session` → Developer 직행 경로는
유지됩니다.

**Q. `~/.harness/brain.db` 가 만들어지지 않게 하려면?**

`/project:brain-*` 커맨드를 한 번도 호출하지 않으면 됩니다. brain 은 100% 옵션이며,
하네스 정상 동작과 분리되어 있습니다.

**Q. analytics·learnings·checkpoint 가 git history에 노이즈를 만들지 않을까요?**

`.claude/state/analytics.jsonl` 은 매 핸드오프마다 한 줄씩 늘어납니다 (1년 100세션 가정 시
~10KB). `learnings.jsonl` 도 비슷한 규모. checkpoints는 매 핸드오프마다 한 파일이라
1년 후 100개 파일 (~300KB). git에 부담 없는 수준입니다. 다만 `claude-progress.txt` 가
200줄 넘으면 `/project:start-session` 이 자동으로 `docs/progress-archive.txt` 로 이전합니다.

---

## 핵심 명령어 요약 (Phase 1·2·3 통합)

### 매 세션마다 사용하는 4가지

| 명령어 | 언제 | 무엇을 |
|---|---|---|
| `/project:init` | 프로젝트 처음 시작 시 1회 | 요구사항 수집 → 환경 자동 구성 |
| `/project:start-session` | Claude Code 열 때마다 | 컨텍스트 복원 + 학습 요약 + 다음 Feature 선택 |
| `/project:handoff` | 세션 끝낼 때마다 | 커밋 + 체크포인트 + analytics append |
| `/project:status` | 진행 상황 보고 싶을 때 | 전체 진행률 + 미완료 목록 |

### Phase 1 — 안전·학습·인계

| 명령어 | 언제 | 무엇을 |
|---|---|---|
| `/project:freeze` | 범위 제한이 필요할 때 | 디렉토리 외 Edit/Write 차단 |
| `/project:unfreeze` | 경계 해제 | freeze 상태 파일 삭제 |
| `/project:guard` | 프로덕션 디버깅 등 최대 안전 | freeze + 파괴 명령 차단 |
| `/project:learn` | 학습 누적/검색 | JSONL 기반 패턴·함정·결정 관리 |
| `/project:context-save` | 명시적 체크포인트 | YAML frontmatter + 4섹션 MD |
| `/project:context-restore` | 가장 최근 체크포인트 로드 | cross-branch resume |

### Phase 2 — 자동화 파이프라인

| 명령어 | 언제 | 무엇을 |
|---|---|---|
| `/project:plan-full <요구사항>` | 새 Feature·구조 변경 | Planner→Architect→Reviewer 체인 |
| `/project:ship` | PR 만들기 전 | diff 분석 → 필요한 리뷰만 추천 |
| `/project:retro [--week\|--month\|--since FXXX]` | 회고 시점 | 통계 + 학습 요약 + 회고 질문 |

### Phase 3 — Cross-project 영구 지식

| 명령어 | 언제 | 무엇을 |
|---|---|---|
| `/project:brain-sync` | Phase 완료, 큰 마일스톤 | 현재 프로젝트 → ~/.harness/brain.db |
| `/project:brain-search <q>` | 다른 프로젝트 지식 참고 | learnings + ADRs + features 검색 |
| `/project:brain-stats` | 전체 활동 점검 | 프로젝트별 학습·Feature·ADR 카운트 |
| `/project:brain-list` | 등록 프로젝트 확인 | first/last sync 시각 표시 |

---

*이 가이드는 `harness-template-v3` + Phase 1·2·3 (gstack 기반 업그레이드) 기준입니다.*
