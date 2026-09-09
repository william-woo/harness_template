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

## 📖 문서 인덱스

처음이면 위에서 아래로 읽으면 된다.

| 문서 | 무엇이 들어 있나 | 언제 보나 |
|---|---|---|
| **README.md** (지금 이 문서) | 변형 계보 · 온보딩 · 파일 구조 | 시작할 때 |
| [CLAUDE.md](./CLAUDE.md) | 하네스 운영 규칙 — 각 도구의 **호출 기준**, Autonomous Mode, 14 변형 미러 정책 | 작업 중 늘 |
| [docs/agents.md](./docs/agents.md) | **에이전트 9종** 역할·권한·파이프라인·호출법 | 누구에게 맡길지 정할 때 |
| [docs/tools.md](./docs/tools.md) | **도구 인벤토리** — 자체 도구 5계층 + 외부 도구 + 변형별 매트릭스 | 무엇을 쓸 수 있는지 볼 때 |
| [.claude/rules/coding-standards.md](./.claude/rules/coding-standards.md) | 코딩 표준 · 변형별 외부 의존성 계약 · 프롬프트 규율 | 코드 쓸 때 |
| [.claude/rules/git-conventions.md](./.claude/rules/git-conventions.md) | 브랜치·커밋·PR 컨벤션 | 커밋할 때 |
| [docs/adr/](./docs/adr/) | 아키텍처 결정 기록 (ADR-001~020) — **왜** 그렇게 만들었나 | 설계 배경이 궁금할 때 |
| [docs/index.md](./docs/index.md) | 산출물 자동 인덱스 (feature · ADR 목록) | 전체 진행 상황 볼 때 |

> `docs/index.md` 는 자동 생성이다 — `python3 .claude/bin/lint.py regenerate-index` 로 갱신한다.
> `docs/agents.md` · `docs/tools.md` 는 수동 문서이나 각 문서 끝에 **재생성 명령**이 있어
> 낡았는지 대조할 수 있다.

---

## 🧬 변형 계보 (14 변형) — 무엇을 고를 것인가

이 템플릿은 하나가 아니라 **계보(lineage)** 다. 각 변형은 부모를 그대로 상속하고 오버레이 하나를
얹는다. 그래서 "필요한 기능이 있는 가장 낮은 변형"을 고르면 된다 — 위로 갈수록 강력하지만
표면적도 커진다.

```
claude                                   baseline (Phase 0 스냅샷 — 동결)
└─ claude.gstack                         표준: 에이전트 5종 + 훅 + 스킬 + brain/lint/backup
   └─ claude.gstack.auto                 자율 모드 (승인 프롬프트 없이 진행 + Gatekeeper)
      └─ …auto.design                    디자인 시스템 (4 브랜드 토큰 + designer)
         └─ …auto.design.wiki            지식 그래프 (wikilink vault) ← 외부 의존성 허용 시작
            └─ …auto.design.wiki.orch    이종 에이전트 오케스트레이션 (d-1)
               └─ claude.hermes          영속 기억 (FTS5 세션검색) + 스킬 자동생성
                  └─ claude.productmgr   PM 주도 통합 SDLC (기획→설계→개발→검증→배포)
                     ├─ claude.productnw 분산 멀티팀 컨소시엄 (d-3)
                     └─ claude.loope ★   검증 루프 (Loop 2+4) — 메인과 1:1 SSOT
                        ├─ claude.aif    판정 설계 (RLAIF/CAI 규율)          ← 신규
                        └─ localllm      d-2: OpenCode + 로컬 LLM 구동
                           └─ localllm.aif  d-2 + 판정 설계                 ← 신규

openai/.codex                            Codex 호스트 변형 (정적 stub)
```

### 변형별로 무엇이 추가되나

| 변형 | 추가되는 것 | 핵심 자산 | 근거 |
|---|---|---|---|
| `claude` | — (Phase 0 스냅샷, 수정 금지) | — | 회귀 비교 기준선 |
| `claude.gstack` | 에이전트·훅·스킬·커맨드 전체 스택 | `brain.py` `lint.py` `backup.py` `qa_browser.py` | ADR-001~005 |
| `claude.gstack.auto` | **자율 모드** — 워크디렉토리 내부는 무프롬프트, 경계는 훅+Gatekeeper | `gatekeeper.md`, `pre-bash-auto-boundary-check.sh` | — |
| `…auto.design` | 디자인 토큰 선택 (Apple/Claude/Spotify/Tesla) | `design_pick.py`, `designer.md` | ADR-006 |
| `…auto.design.wiki` | 산출물을 wikilink 노드로 관리 (**외부 의존성 허용**) | `wiki.py`, `wiki/` vault | ADR-007 |
| `…auto.design.wiki.orch` | 리서치·디자인·코딩 삼각형 오케스트레이션 (d-1) | `researcher.md`, `orchestrate.md` | ADR-008 |
| `claude.hermes` | 세션 검색(FTS5) + 스킬 자동생성 (**활성화는 승인**) | `session_search.py`, `skill_forge.py` | ADR-010 |
| `claude.productmgr` | PM 이 성공지표로 각 단계를 게이트하는 통합 사이클 | `product-manager.md`, `product-cycle.md` | ADR-011 |
| `claude.productnw` | 팀 간 메시지 계약·로스터·큐 (전송은 stub, d-3) | `consortium.py` | ADR-012 (변형 내) |
| **`claude.loope`** ★ | 검증 루프 명시·유계화 + hill-climbing 신호 | `verify_loop.py`, `hill_climb.py`, `.claude/rubrics/` | ADR-014·015 |
| **`claude.aif`** | **판정 설계** — 항목형 rubric + 증거 강제 + 앙상블 + UNCERTAIN | `aif_judge.py`, `*.items.md` | ADR-020 |
| `localllm` | **로컬 LLM 구동** + 결정론 supervisor + 무인 스위트 + 자가 실험 | `cycle_driver.py`, `autoresearch.py`, `tests/suite/` | ADR-009·017·018·019 |
| **`localllm.aif`** | localllm + 판정 설계 (여기서만 A/B 수치 비교 가능) | 위 둘의 합집합 | ADR-020 |
| `openai/.codex` | Codex 호스트 구조 (정적 산출물) | `.codex/` | ADR-001 |

### 기능 × 변형 누적 매트릭스

| 기능 | gstack | auto | design | wiki | orch | hermes | productmgr | productnw | loope | aif | localllm | localllm.aif |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| 에이전트·훅·스킬 스택 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| 자율 모드 | ❌ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| 디자인 토큰 | ❌ | ❌ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| wiki 지식 그래프 | ❌ | ❌ | ❌ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| 오케스트레이션 (d-1) | ❌ | ❌ | ❌ | ❌ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| 세션검색·스킬생성 | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| PM 통합 사이클 | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| 멀티팀 컨소시엄 (d-3) | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ |
| 검증 루프 (Loop 2+4) | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ | ✅ | ✅ | ✅ |
| 항목형 판정 (AIF) | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ | ❌ | ✅ |
| 로컬 LLM 구동 (d-2) | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ | ✅ |
| 무인 스위트 + 자가 실험 | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ | ✅ |
| 외부 의존성 | 0 | 0 | 0 | 허용 | 허용 | 허용 | 허용 | 허용 | 허용 | 허용 | 허용 | 허용 |

### 고르는 법

- **처음이면 `claude.gstack`** — 외부 의존성 0, 표준 스택. 대부분의 다운스트림은 여기서 시작한다.
- 승인 프롬프트가 번거로우면 `claude.gstack.auto`.
- UI 작업이 있으면 `…design`, 산출물이 많아 검색이 필요하면 `…wiki`.
- **리뷰·QA 게이트를 엄격하게** 하고 싶으면 `claude.loope` (메인과 동일).
- 판정이 흔들리는 게 문제라면 `claude.aif` — 항목형 rubric + 증거 강제.
- **API 비용 0 / 오프라인**이 필요하면 `localllm` (로컬 GPU 필수).

> **메인 리포와의 관계**: 이 리포의 `.claude/` 는 `claude.loope` 와 1:1 정합(SSOT, ADR-015)이다.
> 신규 개발은 메인 → loope 미러 → 하위 변형 오버레이 제외 미러 순으로 흐르고,
> `python3 .claude/bin/lint.py check --only=LINT-MR` (MR-1~14) 이 그 정합을 자동 검사한다.


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
