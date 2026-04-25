# 하네스 엔지니어링 템플릿 사용 가이드 (Codex CLI 버전)

> `harness-template-codex`를 사용해 **OpenAI Codex CLI** 멀티롤 프로젝트를 시작하고 운영하는 방법을 단계별로 설명합니다.

---

## 목차

1. [하네스 엔지니어링이란](#1-하네스-엔지니어링이란)
2. [전체 워크플로우 한눈에 보기](#2-전체-워크플로우-한눈에-보기)
3. [파일 구조 이해하기](#3-파일-구조-이해하기)
4. [PHASE 1 — 프로젝트 최초 세팅 (1회만)](#4-phase-1--프로젝트-최초-세팅-1회만)
5. [PHASE 2 — 매 세션 시작](#5-phase-2--매-세션-시작)
6. [PHASE 3 — 기능 개발 사이클](#6-phase-3--기능-개발-사이클)
7. [PHASE 4 — 매 세션 종료](#7-phase-4--매-세션-종료)
8. [롤 역할과 호출 방법](#8-롤-역할과-호출-방법)
9. [핵심 파일 관리 규칙](#9-핵심-파일-관리-규칙)
10. [팀원 온보딩](#10-팀원-온보딩)
11. [자주 묻는 질문](#11-자주-묻는-질문)

---

## 1. 하네스 엔지니어링이란

**하네스(Harness)**는 AI 에이전트가 장시간 안정적으로 작동할 수 있도록 주변에 구축하는 환경과 규칙의 총체입니다. 에이전트 자체가 아니라, 에이전트를 둘러싼 시스템입니다.

Codex CLI는 **단일 에이전트** 모델이므로 Claude Code의 서브에이전트 병렬 호출이 불가능합니다. 대신 이 템플릿은 **롤(persona) 전환** + **에이전트 호출형 검증 스크립트** + **샌드박스/승인 정책**의 3층 구조로 품질을 유지합니다.

이 템플릿이 해결하는 문제:

| 문제 | 해결 방법 |
|---|---|
| 새 세션마다 이전 맥락을 잃어버림 | `codex-progress.txt`로 세션 간 인계 |
| 에이전트가 여러 기능을 한꺼번에 시도 | 한 번에 Feature 하나 규칙 |
| 기능이 반쯤 구현된 채 방치됨 | `/handoff`로 항상 clean state 유지 |
| 테스트 없이 완료 선언 | QA 롤 필수 통과 게이트 |
| 매 프로젝트마다 처음부터 설정 | 이 템플릿을 복사해서 즉시 시작 |
| 팀원과 설정 공유가 어려움 | `.codex/` 폴더를 git에 포함해서 공유 |
| Codex에 훅이 없음 | 샌드박스 + 에이전트 호출 검증 스크립트 |

---

## 2. 전체 워크플로우 한눈에 보기

```
┌─────────────────────────────────────────┐
│         PHASE 1 — 최초 1회              │
│                                         │
│  1. 템플릿 복사                          │
│  2. codex 실행                           │
│  3. /init-project  ← Planner 롤 자동     │
│     - 요구사항 질문에 답변               │
│     - init.sh, AGENTS.md 자동 작성      │
│     - feature_list.json 자동 생성       │
└────────────────┬────────────────────────┘
                 │
                 ▼  (이후 반복)
┌─────────────────────────────────────────┐
│         PHASE 2 — 매 세션 시작          │
│                                         │
│  /start-session                         │
│  → 이전 인계 확인 → Feature 선택        │
└────────────────┬────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────┐
│      PHASE 3 — 기능 개발 사이클         │
│                                         │
│  [설계 필요 시] /role architect         │
│       ↓                                 │
│  /role developer — 구현 + 테스트        │
│       ↓                                 │
│  /role reviewer — 코드 리뷰             │
│       ↓ APPROVED                        │
│  /role qa — E2E 검증                    │
│       ↓ PASS (passes: true 자동 기록)   │
│  다음 Feature로 이동                    │
└────────────────┬────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────┐
│         PHASE 4 — 매 세션 종료          │
│                                         │
│  /handoff                               │
│  → 커밋 + status 업데이트               │
│  → codex-progress.txt 인계 기록         │
└─────────────────────────────────────────┘
```

---

## 3. 파일 구조 이해하기

```
project-root/
│
├── AGENTS.md                  # Codex CLI가 항상 읽는 프로젝트 가이드
├── codex-progress.txt         # 세션 간 인계 파일 — 에이전트가 자동 관리
├── feature_list.json          # 기능 목록 + 진행 상태 — 에이전트가 자동 관리
├── init.sh                    # 세션 시작 시 환경 점검 스크립트
│
└── .codex/
    ├── config.toml            # 샌드박스·승인·MCP·프로파일 설정
    │
    ├── roles/                 # 전문 롤 5개
    │   ├── planner.md         # 기획 — feature_list.json 생성/관리
    │   ├── architect.md       # 설계 — ADR 작성, 구조 설계
    │   ├── developer.md       # 구현 — 코드 + 단위 테스트
    │   ├── reviewer.md        # 리뷰 — MUST/SHOULD/CONSIDER 분류
    │   └── qa.md              # 검증 — E2E, passes 권한 독점
    │
    ├── prompts/               # 슬래시 프롬프트 5개
    │   ├── init-project.md    # /init-project
    │   ├── start-session.md   # /start-session
    │   ├── handoff.md         # /handoff
    │   ├── status.md          # /status
    │   └── role.md            # /role <name>
    │
    ├── scripts/               # 에이전트 호출형 검증 스크립트
    │   ├── pre-bash-check.sh      # 위험 명령어 차단
    │   ├── pre-write-check.sh     # 보호 파일 수정 경고
    │   ├── post-write-check.sh    # feature_list.json 무결성
    │   └── session-end.sh         # 미커밋 변경사항 경고
    │
    ├── skills/                # 롤용 참조 스킬
    │   ├── planning/SKILL.md
    │   ├── coding/SKILL.md
    │   └── testing/SKILL.md
    │
    └── rules/                 # 팀 규칙 문서
        ├── coding-standards.md
        └── git-conventions.md
```

### 사람이 직접 건드릴 파일 vs 에이전트가 관리하는 파일

| 파일 | 관리 주체 | 역할 |
|---|---|---|
| `AGENTS.md` | `/init-project` 시 Planner 롤이 작성 | Codex CLI 동작 기준 |
| `init.sh` | `/init-project` 시 Planner 롤이 작성 | 세션 시작 환경 점검 |
| `feature_list.json` | Planner(생성), 각 롤(status), QA(passes) | 기능 진행 현황 |
| `codex-progress.txt` | `/handoff` 시 자동 append | 세션 간 인계 내용 |
| `.codex/roles/*.md` | 사람이 필요 시 수정 | 롤 행동 정의 |
| `.codex/rules/*.md` | 사람이 필요 시 수정 | 팀 코딩 규칙 |
| `.codex/config.toml` | 사람 (민감) | 샌드박스·승인 정책 |

---

## 4. PHASE 1 — 프로젝트 최초 세팅 (1회만)

### Step 1. Codex CLI 설치

```bash
npm install -g @openai/codex
# 또는
brew install --cask codex
```

### Step 2. 템플릿 복사

```bash
mkdir my-project
cd my-project
cp -r /path/to/harness-template/. ./
```

### Step 3. 스크립트 실행 권한

```bash
chmod +x .codex/scripts/*.sh
chmod +x init.sh
```

### Step 4. (선택) 전역 슬래시 프롬프트 등록

프로젝트별 `.codex/prompts/`도 동작하지만, 자주 쓰는 프로젝트라면 사용자 홈에도 복사해두면 편리합니다.

```bash
mkdir -p ~/.codex/prompts
cp -n .codex/prompts/*.md ~/.codex/prompts/
```

### Step 5. git 초기화

```bash
git init
git add .
git commit -m "chore: add Codex CLI harness template"
```

> `.codex/` 폴더, `AGENTS.md`, `codex-progress.txt`, `feature_list.json`은 **반드시 git에 포함** (팀 공유).

### Step 6. Codex CLI 실행 후 `/init-project`

```bash
codex
```

Codex 세션에서:
```
/init-project
```

Planner 롤이 질문을 시작합니다.
```
Planner: 프로젝트 목적이 무엇인가요?
         주요 기능을 알려주세요.
         기술 스택은 무엇인가요?
```

답변 예시:
```
FastAPI + PostgreSQL로 만드는 팀 할일 관리 앱입니다.
기능은 회원가입/로그인, 태스크 CRUD, 태스크 공유입니다.
```

Planner 롤이 자동으로 처리합니다.
- `AGENTS.md` — 프로젝트 정보, 기술 스택, 실제 명령어(`pytest`, `uvicorn` 등)로 채워짐
- `init.sh` — 프로젝트 언어에 맞는 빌드/테스트 명령어로 작성됨
- `feature_list.json` — 말한 기능들을 Feature로 분해해서 생성됨
- `codex-progress.txt` — 초기화 기록 작성
- 초기 git 커밋 완료

### Step 7. 초기화 결과 확인

```bash
bash init.sh
```

정상 완료되면 세팅 끝.

---

## 5. PHASE 2 — 매 세션 시작

Codex CLI를 열 때마다 가장 먼저 실행합니다.

```
/start-session
```

에이전트가 자동으로 다음 순서로 실행합니다.

1. `codex-progress.txt` 읽기 → 이전 세션에서 뭘 했는지 파악
2. `git log --oneline -15` 확인
3. `feature_list.json` 읽기 → 완료/미완료 기능 확인
4. `bash init.sh` 실행 → 빌드·테스트 정상 여부 확인
5. 다음 작업할 Feature 선택 → `status: "in-progress"`로 변경 → `post-write-check.sh` 실행

결과 예시:

```
▶ 다음 작업: F002 사용자 로그인 기능 (priority: critical)
  의존성: F001 완료됨 ✅
  현재 status: todo → in-progress로 변경됨

  권장 다음 명령:
  → /role architect   (새 DB 테이블 필요)
```

### Feature 선택 기준

에이전트는 `feature_list.json`에서 다음 조건을 모두 만족하는 것 중 우선순위 최상위를 선택합니다.

- `passes: false` — 아직 완료되지 않음
- `status: "todo"` — 작업 시작 전 (`"in-progress"`면 재개)
- 모든 `dependencies`가 `passes: true`
- `priority: critical → high → medium → low` 순서

---

## 6. PHASE 3 — 기능 개발 사이클

Feature 하나를 완료할 때까지 롤을 순서대로 전환합니다.

### Step A. Architect 롤 — 설계 (조건부)

다음 중 하나라도 해당하면 Developer 시작 전에 먼저 호출합니다.

- 새로운 DB 테이블/스키마가 필요한 기능
- 새로운 외부 API 연동
- 기존 모듈 간 의존성 변경
- 3개 이상 파일에 걸친 구조적 변경
- 보안/인증 관련 기능

```
/role architect
설계: F002 로그인 시스템
```

설계 품질이 중요한 작업이라면 `.codex/config.toml`에서 `model_reasoning_effort = "high"`로 세션을 열거나, 더 큰 모델로 프로파일 전환.

에이전트가 `docs/adr/ADR-001-login-design.md`를 작성하고 Developer에게 구현 가이드를 전달합니다.

해당 사항 없는 단순 기능은 Architect를 건너뛰고 바로 Developer로 갑니다.

### Step B. Developer 롤 — 구현

```
/role developer F002
```

에이전트가 순서대로 실행합니다.

1. 설계 문서 확인 (`docs/adr/`, `docs/design/`)
2. `feature_list.json`에서 해당 항목 `status: "in-progress"` 확인 (+ `post-write-check.sh`)
3. `git checkout -b feature/F002-login` 브랜치 생성
4. 코드 구현 (docstring 포함)
5. 단위 테스트 작성
6. 테스트 통과 확인
7. `status: "review"`로 변경 (+ `post-write-check.sh`)
8. `git commit -m "feat(F002): 로그인 API 구현"`
9. `/role reviewer` 안내

> **세션 중간에 끊겼다면**: 걱정하지 마세요. `/handoff`로 현재까지 저장하고, 다음 세션에서 `status: "in-progress"` 기준으로 자동 재개됩니다.

### Step C. Reviewer 롤 — 코드 리뷰

```
/role reviewer F002
```

리뷰 세션은 `--profile review` (read-only 샌드박스)로 시작하는 것이 안전합니다. 도구 실행이 필요하면 `/permissions`로 일시 전환.

에이전트가 자동화 도구를 먼저 실행합니다.

```bash
npm run lint
npm run typecheck
npm audit
npm test -- --coverage
```

그 다음 MUST / SHOULD / CONSIDER로 분류해서 피드백을 줍니다.

**APPROVED** → `status: "qa"`로 변경 후 QA 롤로 전환.
**NEEDS REVISION** → Developer 롤로 돌아가 수정 후 다시 리뷰.

> **에스컬레이션**: 같은 Feature에서 NEEDS REVISION이 3회 이상 반복되면 `codex-progress.txt`에 `[ESCALATION]` 태그를 달고 Planner 롤에 Feature 재분해를 요청.

### Step D. QA 롤 — 최종 검증

```
/role qa F002
```

에이전트가 `feature_list.json`의 `acceptance_criteria`를 기준으로 검증합니다.

```bash
bash init.sh
npm test
curl -X POST /api/auth/login \
  -d '{"email":"test@test.com","password":"pass123"}'
```

엣지 케이스도 확인합니다.
- 정상 케이스 (Happy Path)
- 잘못된 비밀번호 → 401
- 존재하지 않는 이메일 → 404
- 빈 입력 → 400

**PASS** → 에이전트가 `feature_list.json`을 직접 수정합니다.

```json
"status": "qa"   →  "status": "done"
"passes": false  →  "passes": true
```

→ 반드시 `.codex/scripts/post-write-check.sh` 실행해 무결성 확인.

`passes: true`는 QA 롤만 변경해야 합니다. `post-write-check.sh`가 다른 롤의 무단 변경(되돌리기)을 감지하고 차단합니다.

**FAIL** → Developer 롤에 재작업을 요청합니다.

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
/handoff
```

에이전트가 순서대로 처리합니다.

1. `bash .codex/scripts/session-end.sh` — 미커밋 변경 점검
2. 테스트·린트 통과 확인
3. 모든 변경사항 커밋 (미완성이면 `wip` 커밋)
4. `feature_list.json` status 업데이트 (`post-write-check.sh` 포함)
5. `codex-progress.txt`에 인계 내용 기록

`codex-progress.txt`에 이런 형태로 남습니다.

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
  - [ ] /role reviewer F002

권장 다음 명령:
  - /role reviewer

주의사항:
  - bcrypt salt rounds를 환경변수로 분리 예정
============================================================
```

다음 세션에서 `/start-session`을 실행하면 이 내용을 읽고 정확히 이어서 시작합니다.

---

## 8. 롤 역할과 호출 방법

### 롤 한눈에 보기

| 롤 | 권한 | 호출 시점 | 권장 실행 모드 |
|---|---|---|---|
| **Planner** | `feature_list.json` 생성, status 관리 | 프로젝트 초기, 기능 추가 | `workspace-write` / `on-request` |
| **Architect** | ADR 작성, 설계 문서 | DB/API/보안 관련 기능 전 | `workspace-write` + `reasoning=high` |
| **Developer** | 코드 작성, 테스트, 브랜치 | 실제 구현 | `workspace-write` / `on-request` |
| **Reviewer** | 읽기 전용 + 린트/테스트 | 구현 완료 후 | `read-only` (프로파일 `review`) |
| **QA** | `passes: true` 변경 권한 | Reviewer APPROVED 후 | `workspace-write` / `on-request` |

### 롤 직접 호출

Codex CLI 세션에서:

```
/role planner
/role architect
/role developer F003
/role reviewer F005
/role qa F005
```

또는 평문으로:
```
지금부터 developer 롤로 F003 구현을 시작해줘.
```

### Architect를 호출해야 하는 경우

다음 중 하나라도 해당하면 Developer 시작 전 Architect로 먼저 전환:
- 새로운 DB 테이블/스키마가 필요한 기능
- 새로운 외부 API 연동
- 기존 모듈 간 의존성 변경
- 3개 이상의 파일에 걸친 구조적 변경
- 보안/인증 관련 기능

---

## 9. 핵심 파일 관리 규칙

### feature_list.json

기능 목록 파일입니다. 롤들이 자동으로 관리하지만, 규칙을 알고 있어야 합니다.

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
| `passes` | **QA 롤만** | `false → true`만 허용. 되돌리기 절대 금지 |
| `status` | 각 롤 | `todo→in-progress→review→qa→done` 순서만 허용 |
| `acceptance_criteria` | Planner | 기준 약화 금지 |
| 항목 삭제 | **누구도 불가** | 취소된 기능은 status를 "cancelled"로만 표시 |

편집 직후 반드시:
```bash
bash .codex/scripts/post-write-check.sh
```
실패 시 즉시 `git checkout -- feature_list.json`.

### codex-progress.txt

세션 간 인계 파일입니다. 에이전트가 `/handoff` 때마다 자동으로 append합니다.

- 직접 수정하지 마세요 — 에이전트가 관리합니다
- 파일이 200줄을 초과하면 `/start-session`이 자동으로 `docs/progress-archive.txt`로 아카이빙합니다
- git에 커밋되어야 팀원과 공유됩니다

### .codex/config.toml

Codex CLI 프로젝트 설정. `~/.codex/config.toml`과 병합됩니다.

| 핵심 키 | 권장값 | 용도 |
|---|---|---|
| `sandbox_mode` | `workspace-write` | 워크스페이스 외부 쓰기 차단 |
| `approval_policy` | `on-request` | 위험 작업에 사용자 승인 |
| `[profiles.review]` | `read-only` | 리뷰 세션 실수 방지 |
| `[profiles.exec]` | `never` | CI 배치 실행 |

### 에이전트가 반드시 호출해야 하는 스크립트

Codex CLI에는 자동 훅이 없으므로, 에이전트가 스스로 호출해야 합니다.

| 스크립트 | 호출 시점 | 반환 |
|---|---|---|
| `pre-bash-check.sh '<CMD>'` | 위험 가능성 있는 `bash` 전 | exit 2 → 실행 중단 |
| `pre-write-check.sh <PATH>` | `.env`·`AGENTS.md`·`.codex/config.toml` 쓰기 전 | exit 1 → 승인 요청 |
| `post-write-check.sh` | `feature_list.json` 편집 직후 | exit 2 → `git checkout`으로 되돌리기 |
| `session-end.sh` | `/handoff` 직전 | exit 1 → 미커밋 경고 |

`AGENTS.md`의 "필수 규칙" 섹션이 이 호출을 강제합니다.

---

## 10. 팀원 온보딩

### 새 팀원이 합류할 때

```bash
git clone <repository-url>
cd project
chmod +x .codex/scripts/*.sh init.sh

# Codex CLI 설치 (한 번만)
npm install -g @openai/codex
# 또는 brew install --cask codex
```

그 다음 Codex 실행 후 바로 시작:

```bash
codex
```
```
/start-session
```

`codex-progress.txt`를 읽고 현재까지의 진행 상황을 자동으로 파악합니다.

### 팀원과 작업을 나눌 때

```
/status
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

`in-progress` 상태인 Feature는 이미 작업 중이므로 겹치지 않게 다른 Feature를 선택.

### 기존 프로젝트에 하네스 적용

```bash
# .codex/ 폴더만 복사
cp -r harness-template-codex/.codex your-project/
cp harness-template-codex/AGENTS.md your-project/
cp harness-template-codex/init.sh your-project/
cp harness-template-codex/codex-progress.txt your-project/

# feature_list.json은 현재 남은 작업 기준으로 새로 작성
# Codex 세션에서:
/role planner
현재 남은 작업으로 feature_list.json을 만들어줘.
```

---

## 11. 자주 묻는 질문

**Q. `init.sh`와 `AGENTS.md`를 내가 직접 수정해야 하나요?**

직접 수정하지 않아도 됩니다. `/init-project` 실행 후 Planner 롤이 질문에 답변하면 알아서 작성합니다. `init.sh` 실행 후 에러가 나면 에러 메시지를 Codex에 붙여넣고 "고쳐줘"라고 하면 됩니다.

**Q. `passes: true`를 직접 수정하고 싶어요.**

하지 마세요. `post-write-check.sh`가 감지하고 차단하며(exit 2), QA 롤을 통해야만 바뀝니다. 이 제약이 품질을 보장하는 핵심 메커니즘입니다.

**Q. Feature가 생각보다 너무 크면 어떻게 하나요?**

Planner 롤에게 분해를 요청합니다.
```
/role planner
F003을 더 작은 Feature로 분해해줘.
```
또는 같은 Feature에서 NEEDS REVISION이 3회 반복되면 에스컬레이션이 자동으로 발동되어 분해를 권장합니다.

**Q. Architect 롤 없이 Developer만 써도 되나요?**

단순한 기능은 가능합니다. 단, DB 스키마·외부 API·보안 기능에서 Architect를 건너뛰면 나중에 큰 리팩토링이 필요해질 수 있습니다. `AGENTS.md`의 "Architect 롤 호출 기준" 섹션을 참고하세요.

**Q. Codex CLI에 훅이 없어서 위험 명령이 걸러지지 않아요.**

3중 방어를 사용합니다:
1. `.codex/config.toml`의 `sandbox_mode = "workspace-write"` — OS 레벨 차단
2. `approval_policy = "on-request"` — 사용자 승인
3. `AGENTS.md`의 강제 규칙 — 에이전트가 `.codex/scripts/pre-bash-check.sh`를 위험 명령 전 스스로 호출

모델이 규칙을 무시하는 경우엔 `approval_policy = "untrusted"`로 올려 승인 빈도를 높일 수 있습니다.

**Q. 훅이 정상 명령어를 잘못 차단하면 어떻게 하나요?**

`.codex/scripts/pre-bash-check.sh`의 `DANGEROUS_PATTERNS` 배열에서 해당 패턴을 제거하거나 조건을 수정하면 됩니다. 또는 Codex에 "이 스크립트 패턴 수정해줘"라고 요청하세요.

**Q. 여러 Codex 세션을 병렬로 쓸 수 있나요?**

Codex CLI는 단일 에이전트 모델이므로 한 세션에서 동시 작업은 불가능합니다. 다만 서로 다른 Feature를 다른 터미널에서 진행할 수는 있습니다. 이 경우 `/status`로 겹치지 않는 Feature만 선택하세요.

---

## 핵심 명령어 5개 요약

| 명령어 | 언제 | 무엇을 |
|---|---|---|
| `/init-project` | 프로젝트 처음 시작 시 1회 | 요구사항 수집 → 환경 자동 구성 |
| `/start-session` | Codex CLI 열 때마다 | 이전 인계 확인 + 다음 Feature 선택 |
| `/role <name>` | 작업 단계가 바뀔 때마다 | 현재 세션의 행동 규약 전환 |
| `/handoff` | 세션 끝낼 때마다 | 커밋 + 인계 기록 |
| `/status` | 진행 상황 보고 싶을 때 | 전체 진행률 + 미완료 목록 |

---

*이 가이드는 `harness-template-codex` 기준으로 작성되었습니다. 원본 Claude Code 버전에서 포팅됨.*
