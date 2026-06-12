# harness_template — 변형(variant) 가이드

이 디렉토리는 다운스트림 프로젝트에 배포할 **Claude Code 하네스 템플릿**의 변형 모음입니다.
각 변형은 `<변형명>/harness/` 아래에 `.claude/`, `CLAUDE.md`, `docs/` 산출물을 담고 있습니다.

변형은 **누적식(cumulative overlay)** 으로 설계됐습니다 — 뒤로 갈수록 앞 변형에
오버레이를 하나씩 더합니다. 필요한 기능 수준만큼만 가져가세요.

```
claude (baseline)
  └─ claude.gstack (표준)
       └─ +auto (자율 모드)
            └─ +design (디자인 시스템)
                 └─ +wiki (지식 그래프, 외부 의존성 허용)
                      └─ +orch (이종 에이전트 오케스트레이션, d-1)
                           ├─ localllm (OpenCode + 로컬 LLM, d-2)
                           └─ claude.hermes (영속기억·자가진화 — Hermes 패턴)
openai (.codex) — codex 호스트 정적 변형 (별도 계보)
```

---

## 빠른 선택 가이드

| 이런 상황이면 | 추천 변형 |
|---|---|
| 하네스가 처음 / 최소 구성으로 시작 | `claude.gstack` |
| bash 승인 프롬프트 없이 자율 진행시키고 싶다 | `claude.gstack.auto` |
| UI 작업이 있어 디자인 토큰·감사가 필요하다 | `claude.gstack.auto.design` |
| 프로젝트 지식을 그래프(Obsidian/wikilink)로 관리하고 싶다 | `claude.gstack.auto.design.wiki` |
| 리서치+디자인+코딩을 한 흐름으로 지휘하고 싶다 | `claude.gstack.auto.design.wiki.orch` |
| 로컬 LLM(OpenCode+Ollama)으로 비용·보안 최적화 | `localllm` (PoC) |
| 세션 기억 검색 + 스킬 자동생성/self-improve 가 필요하다 | `claude.hermes` |
| OpenAI Codex 호스트에서 쓴다 | `openai/.codex` (stub) |
| Phase 0 원본 스냅샷이 필요하다 (참고용) | `claude` (baseline, 동결) |

> **외부 의존성 0** 이 필요하면 `wiki` 이전 변형까지(`claude` ~ `auto.design`)를 쓰세요.
> `wiki`/`orch`/`localllm` 은 외부 도구(Obsidian/qmd/Marp, OpenCode/Ollama)를 **선택적으로** 허용합니다.

---

## 변형별 상세

### ⓐ `claude/` — baseline (동결)
- **무엇**: Phase 0 (F001 시작 전) 스냅샷. 하네스의 최소 원형.
- **포함**: 기본 에이전트(planner/architect/developer/reviewer/qa), 기본 커맨드, 기본 훅, 코딩/git 규칙.
- **정책**: **수정 금지(동결)**. 신규 phase 산출물은 반영하지 않음. 단 Karpathy 4원칙 같은
  phase-agnostic 보편 디시플린만 예외적으로 동기화.
- **언제**: 하네스가 어떻게 시작했는지 참고하거나, 가장 가벼운 베이스가 필요할 때.
- **외부 의존성**: 0

### ⓑ `claude.gstack/` — 표준 (★ 메인 정합 사본)
- **무엇**: 모든 phase 산출물(F001~F015)의 정합 사본. autonomous 오버레이만 제외한 표준 버전.
- **포함**: Safety Guards/Learn/Context(F001), Autoplan·Ship·Retro(F002~4), Brain(F005),
  멀티호스트(F006), Design-Review(F007), QA-Browser(F008), Lint(F009), Backup-Sync(F010),
  거버넌스 헬스체크 등 — **승인 프롬프트는 표준 동작(작업 디렉토리 액션도 사용자 확인)**.
- **제외(autonomous 오버레이 4 파일)**: gatekeeper.md, pre-bash-auto-boundary-check.sh,
  settings.json 의 `Bash(*)` 권한, CLAUDE.md 의 "Autonomous Mode" 섹션.
- **언제**: 표준적이고 안전한(매 단계 확인) 하네스를 원할 때. 대부분 프로젝트의 기본 선택.
- **외부 의존성**: 0

### ⓑ′ `claude.gstack.auto/` — 자율 모드 (+auto)
- **추가 오버레이**: **Autonomous Mode**.
  - 규칙 #1: 작업 디렉토리 내부는 **승인 없이 자율 진행** (`Bash(*)`/`Edit(*)`/`Write(*)`).
  - 규칙 #2: 모호하면 **Gatekeeper 에이전트**가 PROCEED/CONSULT/ESCALATE 판정.
  - 규칙 #3: 계정/인증·외부 디렉토리·비가역 외부통신은 **반드시 사용자 승인**.
  - 안전망: `pre-bash-auto-boundary-check.sh` 훅 + gatekeeper.md.
- **언제**: 신뢰된 작업 디렉토리에서 반복 승인 프롬프트 없이 빠르게 진행하고 싶을 때.
- **외부 의존성**: 0

### ⓑ″ `claude.gstack.auto.design/` — 디자인 시스템 (+design)
- **추가 오버레이**: **디자인 시스템** (F011).
  - `designer.md` 에이전트, `design_pick.py` (4 브랜드: Apple/Claude/Spotify/Tesla),
    `/project:design-pick` 커맨드, `docs/design-references/`.
  - 출력 `tokens.json` (color/typography/radius/...) → design-review 가 D.TOKEN 카테고리로 감사.
- **언제**: UI 컴포넌트/페이지를 만들고 브랜드 디자인 토큰을 선택·일관성 관리해야 할 때.
- **외부 의존성**: 0

### ⓑ‴ `claude.gstack.auto.design.wiki/` — LLM 지식 그래프 (+wiki)
- **추가 오버레이**: **Wiki 지식 그래프** (F012, F014 멱등성 수정 포함).
  - `wiki.py`(ingest/query/lint/graph), `wiki-setup.sh`, `/project:wiki` 커맨드, `wiki/` vault.
  - 산출물(ADR/feature/외부자료)을 `.md` + `[[wikilink]]` 노드로 관리, mermaid/DOT 그래프 출력.
- **외부 의존성**: **허용** (Obsidian graph view / qmd BM25검색 / Marp 슬라이드) — **선택적, graceful degrade**.
  외부 도구 없으면 stdlib(grep 검색 등)으로 동작.
- **언제**: 프로젝트 지식을 그래프로 누적·시각화하고 cross-reference 를 관리하고 싶을 때.

### ⓑ⁗ `claude.gstack.auto.design.wiki.orch/` — 이종 에이전트 오케스트레이션 (+orch, d-1)
- **추가 오버레이**: **오케스트레이션** (F013).
  - `researcher.md` 에이전트, `/project:orchestrate` 커맨드, `.claude/state/orch/` 핸드오프,
    `docs/orch-examples/`.
  - **single-host d-1**: 모든 sub-agent 를 Claude Code Task 도구로 spawn(같은 컨텍스트 풀 공유).
    리서치(researcher)→디자인(designer)→코딩(developer) 삼각형 + reviewer/qa supervisor.
  - supervisor 로직은 메인 컨텍스트가 직접 수행(별도 orchestrator 에이전트 없음, plan-full 패턴).
- **언제**: 리서치+디자인+코딩이 함께 필요한 **복합 요청**, 신규 기능 end-to-end, 모르는 외부 API 도입
  (researcher 가 먼저 조사 후 developer 에 전달). 단일 역할이면 해당 에이전트 직접 호출.
- **plan-full 과 관계**: plan-full=설계 체인(Feature+ADR 생성), orchestrate=실행 라우팅. 보완 관계.
- **외부 의존성**: 허용 (wiki 상속). orch 자체는 stdlib only.

### ⓑ⁵ `localllm/` — OpenCode + 로컬 LLM (d-2 PoC)
- **무엇**: orch 변형 복사본 + **d-2 오버레이**. Claude Code 가 아니라
  **OpenCode(오픈소스 agent framework) + 로컬 LLM(Ollama)** 으로 하네스를 구동하는 PoC 샌드박스 (F015).
- **추가 오버레이**:
  - `opencode.py` 호스트 어댑터 — `.claude/agents/*.md` → `.opencode/agent/*.md`(`mode: all` +
    permission deny-list) 변환. `host.py render-agents` 로 실행.
  - `.opencode/AGENTS.md`(OpenCode 컨텍스트), `opencode-setup.sh`(설치+Ollama provider),
    `docs/poc/`(측정 01~04 + SUMMARY + MODEL-GRADES), coding 스킬 "상대경로 우선" 보강.
  - `host.json` agent_type=**opencode**.
- **모델 등급**: 단일역할(developer/reviewer/qa)은 로컬 **14B**(qwen2.5)로 즉시 가능,
  멀티스텝 오케스트레이션은 **32B+** 필요 (측정 04 / `docs/poc/MODEL-GRADES.md`).
- **언제**: 비용 절감(API 0)·보안(오프라인 내부망 추론)이 목적이고 단일역할 코딩 작업을 로컬로 돌리고 싶을 때.
- **상태**: **PoC 변형 유지**(정식 졸업 보류, ADR-009 결정 6). 후속: 커맨드 미러링/hook plugin/32B 측정/정식 승격.
- **외부 의존성**: 허용 (OpenCode/Ollama) — 선택적, graceful degrade.

### ⓑ⁶ `claude.hermes/` — 영속 기억 + 자가 진화 (Hermes Agent 패턴 이식)
- **무엇**: orch 변형 복사본 + **hermes 오버레이** (F016, ADR-010). NousResearch/hermes-agent
  ("the agent that grows with you") 의 3가지를 SDLC 하네스에 이식.
- **추가 오버레이**:
  - `session_search.py` — **FTS5 세션 검색**: claude-progress.txt + 체크포인트를 SQLite FTS5 로
    색인/검색 (cross-session recall). `/project:session-search`.
  - `skill_forge.py` — **스킬 자동생성/self-improve + agentskills.io 검증**: 스킬 scaffold,
    사용 추적(`record-use`)→개선 후보 `nudge`, 표준 적합성 `validate`. `/project:skill-forge`.
  - **agentskills.io 표준**(Anthropic 원작): 기존 스킬은 이미 호환(name+description). validate 6/6 PASS.
- **설계**: 헬퍼는 **결정론 부분**(구조·메타데이터·검증·사용추적)만, 스킬 **본문은 에이전트**가 작성
  (Karpathy 추측 자동화 금지). hermes 3종 기능은 **stdlib only**.
- **미이식**(의도): Hermes 의 메시징 게이트웨이/유저모델링 등 — 개인비서 영역, SDLC 목적과 불일치.
- **언제**: "예전에 어떻게 했더라" 과거 세션 회상 / 반복 절차를 재사용 스킬로 승격·관리.
- **외부 의존성**: wiki 상속분(Obsidian/qmd/Marp) 허용, hermes 기능 자체는 0.

### ⓒ `openai/` — Codex 호스트 (stub, 별도 계보)
- **무엇**: OpenAI Codex 호스트용 `.codex/` 구조의 **정적 산출물**.
- **정책**: F006 세션 2에서 수동 생성. 직접 손대지 말 것 — codex 어댑터가 실구현되는 후속 phase에서
  `render-skills` 로 자동 재생성 가능해짐. 현재 codex 는 **stub 어댑터**.
- **언제**: Codex 호스트에서의 하네스 형태를 참고할 때.
- **외부 의존성**: 0

---

## 외부 의존성 정책 요약

| 변형 | 외부 의존성 | 허용 카탈로그 |
|---|:-:|---|
| `claude` (baseline) | 0 | — |
| `claude.gstack` | 0 | — |
| `claude.gstack.auto` | 0 | — |
| `claude.gstack.auto.design` | 0 | — |
| `claude.gstack.auto.design.wiki` | **허용** | Obsidian / qmd / Marp |
| `claude.gstack.auto.design.wiki.orch` | **허용**(wiki 상속) | Obsidian / qmd / Marp |
| `localllm` | **허용** | OpenCode / Ollama |
| `claude.hermes` | **허용**(wiki 상속) | Obsidian/qmd/Marp (hermes 기능은 stdlib) |
| `openai/.codex` | 0 | — |

> 핵심 기능은 모두 **stdlib(bash + Python 표준)** 으로 동작하며, 외부 도구는 *향상*만 합니다(graceful degrade).
> wiki/orch/localllm 외 변형은 이 예외를 상속하지 않습니다 (`lint.py check --only=LINT-MR` 이 격리 강제).

---

## 미러·정합성

- 변형 간 오버레이 격리는 `python3 .claude/bin/lint.py check --only=LINT-MR` 로 자동 가드됩니다 (MR-1~8).
- 메인 하네스(`harness_update_agent/.claude/`)가 변경되면 정책에 따라 각 변형에 미러됩니다.
  자세한 미러 매트릭스는 각 변형의 `CLAUDE.md` "메인 ↔ 변형 미러 정책" 섹션을 참조하세요.
- 설계 근거는 `harness/docs/adr/` (ADR-001 멀티호스트, ADR-006 design-pick, ADR-007 wiki,
  ADR-008 orch/d-1, ADR-009 opencode/d-2 등) 에 있습니다.
