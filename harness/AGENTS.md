# 🧰 프로젝트 하네스 가이드 (OpenAI Codex CLI)

> 이 파일은 **Codex CLI**가 프로젝트에 진입할 때 자동으로 읽는 최상위 지침서입니다.
> Codex는 git 루트부터 현재 디렉토리까지 내려오며 `AGENTS.md`를 연결(concat)합니다.
> 팀원 모두 이 파일을 먼저 읽고, `/init-project` 슬래시 프롬프트로 초기화하세요.

---

## 📋 프로젝트 개요

<!-- TODO: 프로젝트 시작 시 아래 항목을 채워주세요 (Planner 롤이 자동 작성) -->
- **프로젝트명**: [프로젝트명]
- **목적**: [한 줄 설명]
- **기술 스택**: [언어, 프레임워크, DB 등]
- **팀 규모**: [N명]
- **목표 완료일**: [YYYY-MM-DD]

---

## 🗂️ 디렉토리 구조

```
project-root/
├── AGENTS.md                    # ← 지금 읽는 파일 (Codex 루트 지침)
├── codex-progress.txt           # 세션 간 인계 파일 (자동 관리)
├── feature_list.json            # 기능 목록 및 진행 상태 (자동 관리)
├── init.sh                      # 환경 초기화 스크립트
│
├── .codex/
│   ├── config.toml              # Codex CLI 프로젝트 설정 (sandbox/approval)
│   │
│   ├── roles/                   # 전문 롤(페르소나) 정의 — 단일 에이전트가 롤 전환
│   │   ├── planner.md           # 기획 롤
│   │   ├── architect.md         # 아키텍처 롤
│   │   ├── developer.md         # 개발 롤
│   │   ├── reviewer.md          # 코드 리뷰 롤
│   │   └── qa.md                # QA/검증 롤
│   │
│   ├── prompts/                 # 커스텀 슬래시 프롬프트 (Codex CLI)
│   │   ├── init-project.md      # /init-project
│   │   ├── start-session.md     # /start-session
│   │   ├── handoff.md           # /handoff
│   │   ├── status.md            # /status
│   │   └── role.md              # /role <name> — 롤 전환
│   │
│   ├── scripts/                 # 에이전트가 직접 호출하는 검증 스크립트
│   │   ├── pre-bash-check.sh    # 위험 명령어 사전 검사
│   │   ├── pre-write-check.sh   # 보호 파일 경고
│   │   ├── post-write-check.sh  # feature_list.json 무결성 검증
│   │   └── session-end.sh       # 세션 종료 전 커밋 상태 점검
│   │
│   ├── skills/                  # 재사용 스킬 참조 문서
│   │   ├── planning/SKILL.md
│   │   ├── coding/SKILL.md
│   │   └── testing/SKILL.md
│   │
│   └── rules/                   # 팀 규칙
│       ├── coding-standards.md
│       └── git-conventions.md
│
├── src/                         # 소스 코드
├── tests/                       # 테스트
└── docs/                        # 문서 (ADR 포함)
```

---

## ⚡ 빠른 시작

### 새 프로젝트 시작 (초기화)
```
/init-project
```
→ Planner 롤이 요구사항 수집 → `feature_list.json`·`AGENTS.md`·`init.sh` 자동 작성 → 초기 커밋

### 작업 세션 시작
```
/start-session
```
→ 이전 인계 확인 → 다음 Feature 선택 → `status: in-progress` 전환

### 세션 마무리 (인계)
```
/handoff
```
→ 테스트·린트 확인 → 커밋 → `codex-progress.txt` 업데이트

### 현재 상태 확인
```
/status
```

### 롤 전환
```
/role planner       # 기획 모드로 전환
/role architect     # 설계 모드로 전환
/role developer     # 구현 모드로 전환
/role reviewer      # 리뷰 모드로 전환
/role qa            # 검증 모드로 전환
```

> 💡 Codex CLI는 **단일 에이전트**입니다. Claude Code처럼 여러 subagent를 병렬 호출할 수 없으므로, 각 롤(persona)은 현재 세션의 행동 규약을 전환하는 개념입니다. `.codex/roles/*.md`에 정의된 책임·금지사항을 따르세요.

---

## 🤖 롤(Role) 체계

| 롤 | 트리거 | 주요 책임 |
|---|---|---|
| **Planner** | 프로젝트 초기, 기능 추가 요청 | 요구사항 분석, `feature_list.json` 관리, 우선순위 결정 |
| **Architect** | 새 컴포넌트 설계, 구조 변경 | 시스템 설계, 기술 선택, ADR 작성 |
| **Developer** | 실제 구현 | 코드 작성, 단위 테스트, 버그 수정 |
| **Reviewer** | 구현 완료 후 | 코드 품질, 보안, 성능 리뷰 |
| **QA** | 리뷰 통과 후 | E2E 테스트, 인수 검증, 기능 완료 마킹 |

**롤 전환 방법:**
```
/role planner         # 현재 세션을 기획 모드로 전환
# 또는 평문으로
사용자: 지금부터 developer 롤로 F003을 구현해줘
```

롤이 전환되면 해당 `.codex/roles/<role>.md` 문서의 규약을 **명시적으로 재확인한 뒤** 작업을 시작합니다.

---

## 📏 필수 규칙 (모든 롤 공통)

### 진행 관리
- `codex-progress.txt`를 세션 시작 시 **반드시** 읽을 것
- `feature_list.json`의 `passes` 필드는 **QA 롤만** `true`로 변경
- 항목 삭제·`acceptance_criteria` 약화·`id` 변경 절대 금지 (취소된 기능은 `status: "cancelled"`)
- 작업 완료 시 반드시 git commit (설명적 메시지)
- 미완성 상태로 세션 종료 금지 — 최소 `wip` 커밋으로 clean state 유지

### 검증 스크립트 의무 실행
Codex CLI에는 Claude Code의 PreToolUse/PostToolUse 훅이 없으므로, **에이전트가 스스로** 검증 스크립트를 호출해야 합니다.

| 시점 | 실행 스크립트 | 실패 시 행동 |
|---|---|---|
| 위험 가능성 있는 `bash` 명령 직전 | `bash .codex/scripts/pre-bash-check.sh '<CMD>'` | 실행 중단, 안전한 대안 검토 |
| `.env`·`AGENTS.md`·`.codex/config.toml` 수정 직전 | `bash .codex/scripts/pre-write-check.sh '<PATH>'` | 사용자 승인 요청 |
| `feature_list.json` 편집 직후 | `bash .codex/scripts/post-write-check.sh` | 무결성 실패 시 `git checkout -- feature_list.json`으로 되돌림 |
| `/handoff` 직전 | `bash .codex/scripts/session-end.sh` | 미커밋 변경 경고 표시 |

> 이 규칙을 어기면 하네스 품질이 무너집니다. **스크립트 실행 결과를 사용자에게 반드시 보고**하세요.

### 코드 품질
- 모든 함수/클래스에 docstring
- 새 기능에는 단위 테스트 필수
- PR 전 Reviewer 롤 리뷰 필수
- 기능 완료 전 QA 롤 E2E 검증 필수

### 금지 사항
- ❌ `feature_list.json` 항목 삭제
- ❌ 테스트 없이 기능 완료 마킹
- ❌ 미완성 코드를 main 브랜치에 직접 커밋
- ❌ 한 세션에서 여러 Feature 동시 구현 (한 번에 하나씩)
- ❌ `git push --force`, `git reset --hard`, `rm -rf /` 류 파괴적 명령
- ❌ `passes: true` 직접 설정 (QA 롤 전용)

---

## 🔒 Codex CLI 샌드박스 · 승인 정책

이 하네스의 기본 설정 (`.codex/config.toml`):

```toml
sandbox_mode     = "workspace-write"   # 워크스페이스 내 쓰기만 허용
approval_policy  = "on-request"        # 위험 작업 시 사용자 승인 요청
```

- **read-only**: 조사/탐색 세션에서 사용. Reviewer 롤이 실수로 파일을 수정하는 것을 방지.
- **workspace-write** *(기본)*: 정상 개발 세션. 네트워크·외부 쓰기 차단.
- **danger-full-access**: 사용하지 않을 것을 권장. 필요 시 `/permissions`로 세션별 전환.

샌드박스 확인·변경:
```
/permissions                # 현재 승인 모드 보기
/approvals on-request       # 승인 모드 변경
```

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

세션을 시작할 때 **반드시** 다음 순서로 진행:

1. `codex-progress.txt` 읽기 (이전 세션 내용 파악)
2. `git log --oneline -10` 실행 (최근 변경 확인)
3. `feature_list.json` 읽기 (완료/미완료 기능 확인)
4. `bash init.sh` 실행 (빌드·테스트 정상 여부 확인)
5. 가장 높은 우선순위의 미완료 기능 선택 → `status: in-progress`로 전환
6. **한 번에 하나의 기능만** 구현

---

## 📊 feature_list.json 필드 설명

| 필드 | 관리 주체 | 값 |
|---|---|---|
| `passes` | **QA 롤만** | `false` → `true` (절대 삭제 금지) |
| `status` | 각 롤 | `todo` → `in-progress` → `review` → `qa` → `done` |
| `dependencies` | Planner | 선행 Feature ID 목록 |
| `acceptance_criteria` | Planner | 약화 금지 (기준 강화/추가만 허용) |

**status 전환 규칙:**
- `todo` → `in-progress`: Developer/Architect 세션 시작 시
- `in-progress` → `review`: Developer 구현 + 테스트 완료 시
- `review` → `qa`: Reviewer APPROVED 시
- `qa` → `done`: QA PASS 시 (`passes: true`와 동시)
- `review` → `in-progress`: Reviewer NEEDS REVISION 시 (유일한 역행 허용)
- `* → cancelled`: 기능 취소 (삭제 대신)

---

## 🏗️ Architect 롤 호출 기준

다음 중 하나라도 해당되면 Developer 시작 전 Architect로 먼저 전환:

- 새로운 DB 테이블/스키마가 필요한 기능
- 새로운 외부 API 연동
- 기존 모듈 간 의존성 변경
- 3개 이상의 파일에 걸친 구조적 변경
- 보안/인증 관련 기능

해당 없으면 Developer가 바로 구현 시작 가능.

---

## 🧩 MCP 서버 (선택)

Puppeteer, PostgreSQL, Slack 등 추가 도구가 필요하면 `~/.codex/config.toml`에 MCP 서버를 등록하세요. 프로젝트별 MCP 권장값은 `.codex/config.toml`에 예시로 코멘트되어 있습니다.

```toml
[mcp_servers.puppeteer]
command = "npx"
args    = ["-y", "@modelcontextprotocol/server-puppeteer"]
```

---

## 🔗 참고 문서

- [아키텍처 결정 기록](./docs/adr/)
- [코딩 컨벤션](.codex/rules/coding-standards.md)
- [Git 컨벤션](.codex/rules/git-conventions.md)
- [OpenAI Codex 공식 문서](https://developers.openai.com/codex)
