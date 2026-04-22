# 🧰 프로젝트 하네스 엔지니어링 템플릿 (OpenAI Codex CLI)

> **OpenAI Codex CLI** 멀티롤 프로젝트를 위한 재사용 가능한 하네스 구조.
> **한 번 셋업, 어떤 프로젝트에나 적용 가능.**

---

## 🎯 이 템플릿이 해결하는 문제

| 문제 | 해결 |
|---|---|
| 세션 간 컨텍스트 소실 | `codex-progress.txt`로 인계 |
| 한 번에 여러 기능을 건드림 | "한 번에 하나의 Feature" 규칙 |
| 반쯤 구현된 채 방치 | Clean State 유지 + `/handoff` |
| 테스트 없이 "완료" 선언 | QA 롤 필수 통과 게이트 |
| 매 프로젝트마다 하네스 재구성 | 이 템플릿 복사 즉시 시작 |
| 팀원과 설정 공유 어려움 | `.codex/` 폴더 통째로 git 포함 |

---

## 🔄 Claude Code 하네스와의 차이

이 템플릿은 원래 Claude Code용 하네스를 OpenAI Codex CLI에 맞게 포팅한 것입니다.

| 영역 | Claude Code | **Codex CLI (이 템플릿)** |
|---|---|---|
| 프로젝트 지침 파일 | `CLAUDE.md` | **`AGENTS.md`** (git 루트 → cwd 연결) |
| 설정 | `.claude/settings.json` | **`.codex/config.toml`** + `~/.codex/config.toml` |
| 슬래시 커맨드 | `.claude/commands/*.md` | **`.codex/prompts/*.md`** (또는 `~/.codex/prompts/`) |
| 서브 에이전트 | `.claude/agents/*.md` | 없음 → **`.codex/roles/*.md` + `/role <name>`** |
| PreToolUse 훅 | ✅ 차단 가능 | ❌ 없음 → **`sandbox_mode` + 에이전트 호출 검증 스크립트** |
| 진행 파일 | `claude-progress.txt` | **`codex-progress.txt`** |

**핵심 철학 차이**: Codex CLI는 훅 기반 "자동 차단"이 불가능합니다. 대신 ① 샌드박스·승인 정책, ② 에이전트가 명시적으로 호출하는 검증 스크립트(`.codex/scripts/*.sh`), ③ `AGENTS.md`에 박힌 강제 규칙, 이 3층으로 품질 게이트를 유지합니다.

---

## 📐 롤(Role) 워크플로우

```
                    ┌─────────────┐
                    │   Planner   │  /init-project
                    │             │  요구사항 분석
                    │  feature_   │  feature_list.json 생성
                    │  list.json  │
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │  Architect  │  설계 필요 시
                    │             │  ADR 작성
                    │  docs/adr/  │  구현 가이드 전달
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
  /start-session ──▶│  Developer  │  한 번에 하나의 Feature
                    │             │  코드 구현 + 단위 테스트
                    │  feat/F001  │  git commit
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │  Reviewer   │  코드 품질 검토
                    │             │  MUST/SHOULD/CONSIDER
                    │  리뷰 결과  │  APPROVED / NEEDS REVISION
                    └──────┬──────┘
                           │ APPROVED
                    ┌──────▼──────┐
                    │     QA      │  E2E 검증
                    │             │  acceptance_criteria 충족?
                    │  passes:true│  → PASS: passes = true
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │   다음      │  /status
                    │   Feature   │  다음 우선순위 Feature로
                    └─────────────┘
```

각 롤은 **단일 Codex 세션**에서 `/role <name>` 슬래시 프롬프트로 전환됩니다.

---

## 🚀 팀원 온보딩 (3분 셋업)

### 1단계: Codex CLI 설치

```bash
# npm
npm install -g @openai/codex
# 또는 brew
brew install --cask codex
```

### 2단계: 템플릿 복사

```bash
# 방법 A: 이 레포를 새 프로젝트에 복사
cp -r harness-template/ my-new-project/
cd my-new-project
git init

# 방법 B: GitHub Template (레포 설정에서 Template 활성화 후)
gh repo create my-project --template your-org/harness-template
```

### 3단계: 훅 실행 권한 + 프롬프트 등록

```bash
chmod +x .codex/scripts/*.sh
chmod +x init.sh

# 선택: 사용자 전역 프롬프트로도 등록
mkdir -p ~/.codex/prompts
cp -n .codex/prompts/*.md ~/.codex/prompts/ 2>/dev/null || true
```

### 4단계: 프로젝트 초기화

```bash
codex
```
Codex CLI 대화창에서:
```
/init-project
```

Planner 롤이 질문합니다:
- 프로젝트 목적이 무엇인가요?
- 주요 기능 목록은?
- 기술 스택은 무엇인가요?

→ 답변하면 `feature_list.json`, `AGENTS.md`, `init.sh`, `.env.example` 자동 생성.

### 5단계: 개발 시작

```
/start-session
```

---

## 📂 파일 구조 설명

```
harness-template/
│
├── AGENTS.md                    # 핵심 가이드 (Codex가 세션 시작 시 자동 로드)
├── codex-progress.txt           # 세션 인계 파일 (자동 관리)
├── feature_list.json            # 기능 진행 현황 (자동 관리)
├── init.sh                      # 환경 초기화 스크립트
│
└── .codex/
    ├── config.toml              # Codex CLI 프로젝트 설정 (sandbox/approval/profiles)
    │
    ├── roles/                   # 롤(페르소나) 정의
    │   ├── planner.md           # 기획: 요구사항 → feature_list
    │   ├── architect.md         # 설계: ADR, 컴포넌트 설계
    │   ├── developer.md         # 구현: 코드 + 단위 테스트
    │   ├── reviewer.md          # 리뷰: MUST/SHOULD/CONSIDER
    │   └── qa.md                # 검증: E2E, passes 권한 보유
    │
    ├── prompts/                 # 커스텀 슬래시 프롬프트
    │   ├── init-project.md      # /init-project
    │   ├── start-session.md     # /start-session
    │   ├── handoff.md           # /handoff
    │   ├── status.md            # /status
    │   └── role.md              # /role <name>
    │
    ├── scripts/                 # 에이전트 호출형 검증 스크립트
    │   ├── pre-bash-check.sh    # 위험 명령 전 검사 (exit 2 차단)
    │   ├── pre-write-check.sh   # 보호 파일 경고 (exit 1 경고)
    │   ├── post-write-check.sh  # feature_list.json 무결성 (exit 2 차단)
    │   └── session-end.sh       # 세션 종료 전 미커밋 점검
    │
    ├── skills/                  # 재사용 스킬 문서
    │   ├── planning/SKILL.md
    │   ├── coding/SKILL.md
    │   └── testing/SKILL.md
    │
    └── rules/                   # 팀 규칙
        ├── coding-standards.md
        └── git-conventions.md
```

---

## 🔧 프로젝트별 커스터마이징

### 기술 스택 변경 시 수정 파일

| 변경 사항 | 수정 파일 |
|---|---|
| 언어 변경 (Python, Go 등) | `.codex/rules/coding-standards.md` |
| 빌드/테스트 명령어 | `AGENTS.md` 주요 명령어 섹션, `init.sh` |
| 롤 추가 (예: DevOps) | `.codex/roles/devops.md` 새로 생성 |
| 스킬 추가 | `.codex/skills/새스킬/SKILL.md` |
| 위험 명령 패턴 추가 | `.codex/scripts/pre-bash-check.sh` |
| 모델/샌드박스 정책 | `.codex/config.toml` |

### 팀 규모별 권장 설정

**1인 프로젝트**
- Planner + Developer + QA 3개 롤만 사용
- Reviewer는 Developer가 자체 리뷰로 대체 가능

**소규모 팀 (2-5인)**
- 전체 5개 롤 사용
- 각 팀원이 세션별로 롤 담당
- `codex-progress.txt`가 팀 내 비동기 커뮤니케이션 역할

**대규모 팀**
- 도메인별 롤 추가 (frontend, backend, data 등)
- `feature_list.json`을 팀별로 분리 가능

---

## 🔒 샌드박스 & 승인 정책 빠른 참조

Codex CLI의 "차단" 안전장치 핵심은 `sandbox_mode` + `approval_policy`:

| `sandbox_mode` | 설명 | 용도 |
|---|---|---|
| `read-only` | 쓰기·네트워크 차단 | Reviewer 롤, 조사 세션 |
| `workspace-write` *(기본)* | 워크스페이스 내 쓰기 허용, 네트워크 차단 | 일반 개발 |
| `danger-full-access` | 전면 허용 | 특수 상황만 |

| `approval_policy` | 설명 |
|---|---|
| `untrusted` | 거의 모든 작업에 승인 요청 |
| `on-request` *(기본)* | 잠재 위험 작업만 승인 요청 |
| `never` | 승인 요청 안 함 (CI 배치 실행용) |

세션 중 변경: `/permissions`, `/approvals <policy>`
프로파일 지정 실행: `codex --profile review`

---

## ❓ 자주 묻는 질문

**Q: `feature_list.json`의 항목을 변경하고 싶어요**
A: 새 항목 추가는 Planner 롤, `passes: true` 변경은 QA 롤만 가능. 기존 항목 삭제는 절대 금지 — 취소는 `status: "cancelled"`로. 편집 직후 `.codex/scripts/post-write-check.sh` 실행 필수.

**Q: Codex CLI에 훅이 없는데 어떻게 위험 명령을 막나요?**
A: 3중 방어: ① `sandbox_mode = "workspace-write"`로 OS 레벨 차단, ② `approval_policy = "on-request"`로 사용자 확인, ③ 에이전트가 위험 명령 직전 `.codex/scripts/pre-bash-check.sh`를 스스로 호출하도록 `AGENTS.md`에 강제. 세 번째는 모델이 규칙을 따라야 동작합니다.

**Q: 하네스를 기존 프로젝트에 적용할 수 있나요?**
A: 네. `.codex/` 폴더를 기존 프로젝트에 복사하고, `AGENTS.md`를 프로젝트에 맞게 수정하세요. `feature_list.json`에 현재 남은 작업을 추가하면 됩니다.

**Q: Claude Code용 원본 하네스에서 옮겨왔어요. 무엇이 바뀌었나요?**
A: README 상단 "Claude Code 하네스와의 차이" 표 참고. 가장 큰 차이는 PreToolUse/PostToolUse 훅이 없어 `.codex/scripts/*.sh`를 **에이전트가 명시적으로 호출**해야 한다는 점입니다.

**Q: 롤 전환을 잊으면요?**
A: `/role`을 호출하지 않아도 AGENTS.md의 "필수 규칙"은 항상 적용됩니다. 다만 롤별 세부 체크리스트는 누락될 수 있으니 Feature 단위 작업 시작 전에는 `/role <name>`으로 명시 전환하세요.

---

## 📚 참고 자료

- [Anthropic: Effective harnesses for long-running agents](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents)
- [Anthropic: Harness design for long-running apps](https://www.anthropic.com/engineering/harness-design-long-running-apps)
- [OpenAI Codex CLI 공식 문서](https://developers.openai.com/codex)
- [OpenAI Codex GitHub](https://github.com/openai/codex)

---

*MIT License — 자유롭게 수정, 팀 내 공유, 개선하여 사용하세요.*
