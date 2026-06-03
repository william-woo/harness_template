# 🧰 프로젝트 하네스 엔지니어링 템플릿

> Claude Code 멀티 에이전트 프로젝트를 위한 재사용 가능한 하네스 구조.
> **한 번 셋업, 어떤 프로젝트에나 적용 가능.**

---

## 🎯 이 템플릿이 해결하는 문제

| 문제 | 해결 |
|---|---|
| 에이전트가 컨텍스트를 잃고 처음부터 시작 | `claude-progress.txt`로 세션 간 인계 |
| 에이전트가 너무 많은 것을 한 번에 시도 | 한 번에 하나의 Feature 규칙 |
| 기능이 반쯤 구현된 채 방치됨 | Clean State 유지 + handoff 커맨드 |
| 테스트 없이 완료 선언 | QA 에이전트 필수 통과 게이트 |
| 매 프로젝트마다 하네스를 처음부터 구성 | 이 템플릿을 복사해서 바로 시작 |
| 팀원과 에이전트 설정 공유 어려움 | `.claude/` 폴더째로 git에 포함 |

---

## 📐 에이전트 워크플로우

```
                    ┌─────────────┐
                    │   Planner   │  /project:init
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
  /project:         │  Developer  │  한 번에 하나의 Feature
  start-session ───▶│             │  코드 구현 + 단위 테스트
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
                    │   다음      │  /project:status
                    │   Feature   │  다음 우선순위 Feature로
                    └─────────────┘
```

---

## 🚀 팀원 온보딩 (3분 셋업)

### 1단계: 템플릿 복사

```bash
# 방법 A: 이 레포를 새 프로젝트에 복사
cp -r harness-template/ my-new-project/
cd my-new-project
git init

# 방법 B: GitHub Template으로 사용 (레포 설정에서 Template 활성화 후)
gh repo create my-project --template your-org/harness-template
```

### 2단계: 프로젝트 초기화

Claude Code 실행 후:
```
/project:init
```

Planner 에이전트가 질문합니다:
- 프로젝트 목적이 무엇인가요?
- 주요 기능 목록을 알려주세요
- 기술 스택은 무엇인가요?

→ 답변하면 `feature_list.json`, `CLAUDE.md` 자동 생성

### 3단계: CLAUDE.md 확인 및 기술 스택 설정

```bash
# 코딩 표준을 프로젝트 언어에 맞게 수정
vi .claude/rules/coding-standards.md

# 빌드/테스트 명령어를 실제 명령어로 교체
vi CLAUDE.md  # "주요 명령어" 섹션
vi init.sh    # 실제 서버 시작 명령어로 교체
```

### 4단계: 훅 실행 권한 부여

```bash
chmod +x .claude/hooks/*.sh
chmod +x init.sh
```

### 5단계: 개발 시작

```
/project:start-session
```

---

## 📂 파일 구조 설명

```
harness-template/
│
├── CLAUDE.md                    # 핵심 가이드 (항상 열려있어야 함)
├── claude-progress.txt          # 세션 인계 파일 (자동 관리)
├── feature_list.json            # 기능 진행 현황 (자동 관리)
├── init.sh                      # 환경 초기화 스크립트
│
└── .claude/
    ├── settings.json             ← 훅 설정 (Claude Code가 읽는 공식 위치)
    ├── agents/                  # 전문 에이전트
    │   ├── planner.md           # 기획: 요구사항 → feature_list
    │   ├── architect.md         # 설계: ADR, 컴포넌트 설계 (Opus 모델)
    │   ├── developer.md         # 구현: 코드 + 단위 테스트
    │   ├── reviewer.md          # 리뷰: MUST/SHOULD/CONSIDER
    │   └── qa.md                # 검증: E2E, passes 권한 보유
    │
    ├── skills/                  # 재사용 스킬
    │   ├── planning/SKILL.md    # 기획 방법론
    │   ├── coding/SKILL.md      # 구현 패턴
    │   └── testing/SKILL.md     # 테스트 전략
    │
    ├── commands/                # 슬래시 커맨드
    │   ├── init-project.md      # /project:init
    │   ├── start-session.md     # /project:start-session
    │   ├── handoff.md           # /project:handoff
    │   └── status.md            # /project:status
    │
    ├── hooks/                   # 자동화 안전장치
    │   ├── pre-bash-check.sh    # 위험 명령어 차단 (exit 2 방식)
    │   ├── pre-write-check.sh   # 민감 파일 보호
    │   ├── post-write-check.sh  # feature_list 항목 삭제 감지
    │   └── session-end.sh       # 미커밋 경고
    │
    └── rules/                   # 팀 규칙
        ├── coding-standards.md  # 코딩 표준
        └── git-conventions.md   # Git 컨벤션
```

---

## 🔧 프로젝트별 커스터마이징

### 기술 스택 변경 시 수정 파일

| 변경 사항 | 수정 파일 |
|---|---|
| 언어 변경 (Python, Go 등) | `.claude/rules/coding-standards.md` |
| 빌드/테스트 명령어 | `CLAUDE.md` 주요 명령어 섹션, `init.sh` |
| 에이전트 추가 (예: DevOps) | `.claude/agents/devops.md` 새로 생성 |
| 스킬 추가 | `.claude/skills/새스킬/SKILL.md` |
| 보안 규칙 강화 | `.claude/hooks/pre-bash-check.sh` |

### 팀 규모별 권장 설정

**1인 프로젝트**
- Planner + Developer + QA 3개 에이전트만 사용
- Reviewer는 Developer가 자체 리뷰로 대체 가능

**소규모 팀 (2-5인)**
- 전체 5개 에이전트 사용
- 각 팀원이 특정 에이전트 역할 담당 가능
- `claude-progress.txt`가 팀 내 비동기 커뮤니케이션 역할

**대규모 팀**
- 도메인별 에이전트 추가 (frontend, backend, data 등)
- `feature_list.json`을 팀별로 분리 가능

---

## ❓ 자주 묻는 질문

**Q: feature_list.json의 항목을 변경하고 싶어요**
A: 새 항목 추가는 Planner 에이전트가, `passes: true` 변경은 QA 에이전트만 가능합니다.
   기존 항목 삭제는 절대 금지 — 히스토리 보존이 중요합니다.

**Q: 하네스를 기존 프로젝트에 적용할 수 있나요?**
A: 네. `.claude/` 폴더를 기존 프로젝트에 복사하고, `CLAUDE.md`를 프로젝트에 맞게 수정하세요.
   `feature_list.json`에 현재 남은 작업을 추가하면 됩니다.

**Q: 에이전트가 rules를 무시하면 어떻게 하나요?**
A: `CLAUDE.md`의 해당 규칙을 더 강하게 작성하고, hooks로 자동 차단을 추가하세요.

**Q: oh-my-claudecode와 함께 사용 가능한가요?**
A: 네. OMC의 `autopilot`이나 `ralph` 모드와 이 하네스를 함께 사용하면 더 강력합니다.
   OMC가 에이전트 병렬화를 담당하고, 이 하네스가 품질 게이트를 담당합니다.

---

## 📚 참고 자료

- [Anthropic: Effective harnesses for long-running agents](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents)
- [Anthropic: Harness design for long-running apps](https://www.anthropic.com/engineering/harness-design-long-running-apps)
- [Claude Code 공식 문서](https://docs.anthropic.com/claude-code)
- [revfactory/harness](https://github.com/revfactory/harness) — 도메인별 하네스 자동 생성

---

*MIT License — 자유롭게 수정, 팀 내 공유, 개선하여 사용하세요.*
