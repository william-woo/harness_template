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
│   │   └── testing/SKILL.md
│   ├── commands/             # 커스텀 슬래시 커맨드
│   │   ├── init-project.md
│   │   ├── start-session.md
│   │   ├── handoff.md
│   │   └── status.md
│   ├── hooks/                # 훅 스크립트 (settings.json에서 참조)
│   │   ├── pre-bash-check.sh
│   │   ├── pre-write-check.sh
│   │   ├── post-write-check.sh
│   │   └── session-end.sh
│   └── rules/                # 팀 규칙
│       ├── coding-standards.md
│       └── git-conventions.md
├── src/                      # 소스 코드
├── tests/                    # 테스트
└── docs/                     # 문서
```

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

---

## 📂 상태 파일 (.claude/state/)

Phase 1·2 업그레이드로 추가된 프로젝트 로컬 상태:

| 파일/디렉토리 | 용도 | git 포함 여부 |
|---|---|---|
| `.claude/state/checkpoints/*.md` | 구조화된 세션 인계 (`/project:context-save` 생성) | ✅ 커밋 대상 |
| `.claude/state/learnings.jsonl` | 프로젝트 학습 누적 로그 (JSONL) | ✅ 커밋 대상 |
| `.claude/state/analytics.jsonl` | handoff·session_end·review 이벤트 로그 (`/project:retro` 분석용) | ✅ 커밋 대상 |
| `.claude/state/freeze-dir.txt` | `/project:freeze` 경계 (세션 로컬) | ❌ gitignore |

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

## 🔗 참고 문서

- [아키텍처 결정 기록](./docs/adr/)
- [코딩 컨벤션](.claude/rules/coding-standards.md)
- [Git 컨벤션](.claude/rules/git-conventions.md)
