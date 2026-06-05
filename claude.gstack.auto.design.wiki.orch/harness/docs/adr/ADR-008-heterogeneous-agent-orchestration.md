# ADR-008: 이종 에이전트 오케스트레이션 (supervisor pattern) + `claude.gstack.auto.design.wiki.orch` 변형 + d-1/d-2/d-3 경계

> Feature: F013 — Phase 9 claude.gstack.auto.design.wiki.orch 변형 (이종 에이전트 오케스트레이션, d-1)
> 작성: architect 에이전트 | 날짜: 2026-06-05

## 상태

`Proposed` — 사용자와의 깊은 논의 결과 (single-host 원칙 + d-1/d-2/d-3 단계 구분 +
OpenClaw 가 (d) 의 답이 아님 + 빠진 조각 = 리서치 에이전트) 위에 8 개 결정을 명시한다.
F012 (LLM Wiki + 외부 의존성 정책 예외) 의 단일 파일 헬퍼 + 변형별 격리 + 셀프 모드 +
graceful degrade + LINT-MR 자동 가드 패턴을 유지하되, **이종 에이전트 오케스트레이션 ≠
이종 호스트 분산** 이라는 새 의미론을 도입한다 — single-host 안에서 sub-agent 들이
같은 컨텍스트 풀을 공유하며 supervisor 가 작업을 분해·라우팅·통합하는 패턴.

---

## 컨텍스트

### F013 의 본질적 질문 — "(d) 장면의 진짜 이름은 무엇인가"

사용자 표현: "여러 다른 종류의 에이전트 (코딩 + 디자인 + 리서치) 를 한 흐름으로 잇고
싶다 — (d) 장면". 논의 결론:

1. **(d) 의 진짜 이름 = supervisor pattern** — 오케스트레이터 에이전트가 작업을 분해
   → 적합 에이전트에 배분 → 결과 통합. LangGraph / CrewAI / OpenAI Swarm 의 공통 패턴.
2. **OpenClaw 는 (d) 의 답이 아님** — OpenClaw 는 채널 게이트웨이 (메시지 라우팅 인프라)
   지 워크플로우 오케스트레이터가 아님. F006 host.py 가 OpenClaw stub 어댑터로
   다루는 영역과 본 ADR 의 supervisor pattern 은 카테고리가 다르다.
3. **우리 하네스의 (d) 원시형 이미 존재**: `/project:plan-full` (Planner → Architect →
   Reviewer 설계 체인) + designer (F011 디자인) + Developer (코딩). 빠진 조각 = **리서치
   에이전트** (현재 brain-search 정도뿐 — 웹 조사·출처 종합 없음).
4. **핵심 원칙: single-host** — 이종 호스트/모델 분산은 컨텍스트 전달 손실 + 오케스트레이션
   비용 폭증을 유발. 같은 컨텍스트 풀을 공유하는 single-host sub-agent (Claude Code 의
   Task 도구) 가 가장 잘 작동한다. F006 ADR-001 의 "single-host 격리" 와 정신 일관.
5. **단계 구분**:
   | 단계 | 정의 | 전제 |
   |---|---|---|
   | **d-1** | single-host (Claude Code 안) supervisor + sub-agent 오케스트레이션 | GPU 무관, 즉시 가능, **본 ADR 범위** |
   | d-2 | 로컬 LLM (researcher 의 본문 요약·웹 조사 결과 합성 등에 로컬 small model 활용) | GPU 필요, 후속 phase |
   | d-3 | 이종 호스트 분산 (Claude Code + Codex + OpenClaw 다른 모델/호스트 간 작업 분산) | 컨텍스트 전달 손실 감수, 먼 미래·어쩌면 불필요 |

본 ADR 은 **d-1 만** 다룬다.

### 현재 6 변형 매트릭스 (F012 완료 후)

| 변형 | 정체성 | 자율 | 디자인 | wiki |
|---|---|:---:|:---:|:---:|
| ⓐ `claude/` (baseline) | Phase 0 동결 + Karpathy 4원칙 | ❌ | ❌ | ❌ |
| ⓑ `claude.gstack/` (표준) | F001~F012 풀, 사용자 승인 | ❌ | ❌ | ❌ |
| ⓑ′ `claude.gstack.auto/` (자율) | ⓑ + 자율 오버레이 | ✅ | ❌ | ❌ |
| ⓑ″ `claude.gstack.auto.design/` | ⓑ′ + 디자인 오버레이 | ✅ | ✅ | ❌ |
| ⓑ‴ `claude.gstack.auto.design.wiki/` | ⓑ″ + wiki 오버레이 (외부 의존성 정책 예외 1호) | ✅ | ✅ | ✅ |
| ⓒ `openai/.codex/` (codex stub) | Karpathy 만 | ❌ | ❌ | ❌ |

F013 추가:

| 변형 | 정체성 |
|---|---|
| **ⓑ⁗ `claude.gstack.auto.design.wiki.orch/` (자율+디자인+wiki+orch)** | ⓑ‴ + orch 오버레이 (researcher 에이전트 + orchestrator 패턴 + 핸드오프 규약) — **이종 에이전트 오케스트레이션 (d-1) 변형 1호** |

### 제약 (F005~F012 일관 + 본 ADR 신설)

- **single-host 강제**: 모든 sub-agent 는 Claude Code 의 Task 도구로 spawn — 같은
  컨텍스트 풀 공유 (이종 호스트 분산 금지, d-3 후속)
- **외부 의존성 0 → wiki 변형만 예외 → orch 변형은 wiki 의 복사이므로 wiki 의 예외 상속
  + orch 자체는 stdlib only**: orch 오버레이 (researcher/orchestrator 에이전트 정의 +
  핸드오프 디렉토리 + 라우팅 규칙) 는 새 외부 도구 추가 X
- **무회규**: F001~F012 동작 무수정 — 7 에이전트 (planner/architect/developer/reviewer/
  qa/gatekeeper/designer) + brain.py + host.py + lint.py + backup.py + qa_browser.py +
  design_pick.py + wiki.py 어떤 비트도 변경 안 함
- **`feature_list.json` `passes` 절대 미수정**: QA 단독 권한
- **`.claude/settings.json` 무수정**: F006 ADR-001 결정 1 격리

---

## 결정

### 결정 1 — orchestrator 형태: **B. 신규 `/project:orchestrate` 커맨드 (plan-full 처럼 메타커맨드) + supervisor 책임은 Claude Code 메인 컨텍스트가 직접 수행 (별도 orchestrator.md 에이전트 없음)**

**채택**: orchestrator 는 **슬래시 커맨드** (`/project:orchestrate <요구사항>`) 로 신설.
plan-full 패턴 (메타커맨드 안에서 Planner/Architect/Reviewer Task spawn) 일관. supervisor
역할은 메인 Claude Code 컨텍스트가 직접 수행 — 별도 `orchestrator.md` 에이전트 정의는
**만들지 않음** (재귀 spawn 회피 + 메인 컨텍스트가 sub-agent 산출물을 직접 조립).

#### 옵션 비교

| 옵션 | 장점 | 단점 | 결정 |
|---|---|---|---|
| (A) 신규 `orchestrator.md` 에이전트 + `/project:orchestrate` 커맨드 (커맨드는 단순 진입점) | 에이전트 정의 파일 안에 supervisor 로직 캡슐화, 호출 형식 `Use the orchestrator agent to ...` 균일 | sub-agent 안에서 또 sub-agent 를 spawn — 재귀 깊이 + 컨텍스트 전달 손실 (sub-agent 의 context 가 메인보다 좁음), gatekeeper 패턴이 아닌 "지휘" 패턴은 메인이 직접 하는 게 자연스러움 | 부분 매력적이나 재귀 비용 우세 |
| **(B) `/project:orchestrate` 커맨드만 + supervisor 는 메인 컨텍스트가 수행** | plan-full 과 동일 패턴 (검증된 정신), 재귀 spawn 0, 메인 컨텍스트가 풀 정보 보유 → 라우팅 결정 품질 ↑, 별도 에이전트 정의 파일 1 개 절약 | 커맨드 본문에 supervisor 로직 (라우팅 규칙·핸드오프 형식) 이 산문으로 명시 — 분량 ↑ | **채택** |
| (C) `/project:plan-full` 확장 (리서치/디자인 분기 추가) | DRY (1 진입점), plan-full 사용자 학습 비용 ↓ | plan-full 의 정체성 (설계 체인) 이 흐려짐 — 단순 설계 vs 실행까지 라우팅의 구분 손실, 호출 인자로 분기 → 도움말 비대 | 의미론적 분리 우세 |

#### plan-full vs orchestrate 책임 분리

| 도구 | 범위 | 출력 | 후속 |
|---|---|---|---|
| `/project:plan-full` (F002) | **설계 체인** — 요구사항 → Feature 분해 → ADR 작성 → 설계 감사 | feature_list 추가 + ADR(s) | Developer 가 별도 실행 (커맨드 종료 후) |
| **`/project:orchestrate` (F013)** | **실행 라우팅** — 요구사항 → 리서치/디자인/코딩 분기 판별 → 적합 에이전트 순차/병렬 spawn → 산출물 통합 | 핸드오프 디렉토리 (`.claude/state/orch/<task-id>/`) + 최종 통합 리포트 | QA + 사용자 검수 |

→ 두 커맨드는 **호환 보완 관계**. 복잡 요청은 plan-full → orchestrate 순차 호출 가능:
plan-full 이 Feature + ADR 을 만들고, orchestrate 가 그 Feature 를 리서치+디자인+코딩으로
실행. orchestrate 가 plan-full 결과를 입력으로 받는 흐름이 라우팅 규칙에 명시됨 (결정 4).

**근거**:

- **plan-full 패턴 100% 일관**: 메타커맨드가 sub-agent 들을 차례로 호출하는 패턴은 F002
  로 검증됨. 본 결정은 그 정신을 확장 — 라우팅 분기만 추가.
- **재귀 spawn 회피**: sub-agent (orchestrator) 가 다시 sub-agent (researcher/designer/
  developer) 를 spawn 하면 컨텍스트 전달이 2 단계 — single-host 풀 공유의 이점 손실.
  메인 컨텍스트가 직접 spawn 하면 1 단계로 평탄화.
- **메인 컨텍스트가 풀 정보 보유**: 사용자 요구사항 / 진행 상황 / feature_list / 학습 등
  메인 풀이 모든 정보를 보유. orchestrator.md 에이전트로 위임하면 그 정보를 다시
  전달해야 함 — 손실 발생.
- **`orchestrator.md` 미생성으로 7 → 8 에이전트 폭증 회피**: 현재 7 에이전트 (planner/
  architect/developer/reviewer/qa/gatekeeper/designer) + researcher 1 추가 = 8 에이전트.
  orchestrator 까지 더하면 9 — 학습 비용 ↑ + 책임 경계 흐림.

**영향받는 AC**: AC3 (orchestrator 에이전트 또는 /project:orchestrate 커맨드 — 후자 채택)

---

### 결정 2 — researcher 에이전트 설계: **opus 모델 + Read/Glob/Grep/Bash/WebSearch/WebFetch 도구 + 리서치 노트 산출 (마크다운, 핸드오프 디렉토리에 저장)**

**채택**: researcher 는 신규 에이전트로 `.claude/agents/researcher.md` 추가. 모델
**claude-opus-4-7** (조사·합성 품질 ↑), 도구 **Read/Glob/Grep/Bash/WebSearch/WebFetch**
(내부 brain-search + 웹 조사 + 출처 종합). 산출물은 **마크다운 리서치 노트** (구조화 JSON
이 아닌) — 다음 에이전트가 자연어로 직접 인용 가능. 저장 위치는 핸드오프 디렉토리
`.claude/state/orch/<task-id>/research.md` (결정 3).

#### 옵션 비교 — 모델 선택

| 옵션 | 장점 | 단점 | 결정 |
|---|---|---|---|
| (A) `claude-sonnet-4-6` (planner/gatekeeper 일관) | 비용 ↓, 빠른 응답 | 합성·요약 품질 sonnet 한계 — 다출처 종합 시 누락 위험 | 부분 매력적 |
| **(B) `claude-opus-4-7` (designer/developer 일관)** | 다출처 합성·요약 품질 ↑, 본 ADR 의 "리서치 = 깊은 조사" 정의 충족, designer 와 같은 무게 — 양쪽이 동급 큐레이터 | 토큰 비용 ↑ | **채택** |
| (C) 사용자 선택 (sonnet/opus 모두 호환) | 유연 | 에이전트 정의 파일에서 모델 단일 명시 표준 위배 (F006 ~ F011 패턴) | 표준 어긋남 |

#### 옵션 비교 — 도구 선택

| 옵션 | 장점 | 단점 | 결정 |
|---|---|---|---|
| (A) Read/Glob/Grep/Bash 만 (내부 brain-search 한정) | 외부 의존성 0 정책 일관 (orch 자체는 stdlib only) | 웹 조사 불가 — researcher 본질 (외부 출처 종합) 50% 손실 | 약체 |
| **(B) Read/Glob/Grep/Bash + WebSearch + WebFetch (내부 + 외부 조사)** | researcher 본질 충족 (브레인+웹+종합), Claude Code 빌트인 도구라 변형 외부 의존성 추가 0 (도구는 Claude Code 가 제공) | 웹 조사 결과 신뢰성은 researcher 책임 — 출처 인용 의무 | **채택** |
| (C) 위 + WebFetch + Write (리서치 노트 직접 저장) | 핸드오프 디렉토리에 직접 저장 가능 | sub-agent 가 파일 시스템 변경 — 메인 컨텍스트의 통제 ↓ | 위임 안전 ↓ |

> **B 채택 후 Write 도구 제외 근거**: researcher 는 산출물을 stdout 으로 반환하고, 메인
> 컨텍스트 (orchestrate 커맨드 본문) 가 `.claude/state/orch/<task-id>/research.md` 로
> 저장한다. 이 패턴은 designer (F011) 가 tokens.json 을 직접 저장하지 않고 design_pick.py
> 가 저장하는 패턴과 일관 — sub-agent 의 부수 효과 제한.

#### researcher 책임 범위 (designer/developer 와의 분리)

| 에이전트 | 책임 | 입력 | 출력 |
|---|---|---|---|
| **researcher** (F013 신규) | 외부 자료·내부 brain·산출물에서 정보 수집 → 합성 → 리서치 노트 | 질의 (자연어) + 기존 컨텍스트 | 마크다운 리서치 노트 (출처 인용 포함) |
| **designer** (F011) | 디자인 시스템 비교·추천·tokens.json 시안 | 프로젝트 컨텍스트 + USE_CASE + DESIRED_TONE | 비교표 + 추천 + tokens 시안 (JSON) |
| **developer** | 실제 코드 작성 + 단위 테스트 | Feature + ADR + 핸드오프 산출물 | 코드 변경 + 테스트 |

→ 책임 3 분립. researcher 는 "정보 수집·합성", designer 는 "디자인 큐레이션", developer 는
"실행". orchestrate 커맨드 본문에서 라우팅 규칙 (결정 4) 으로 어떤 단계에 누구를 호출할지 결정.

#### 빌트인 deep-research 스킬과의 관계

- Claude Code 빌트인 `deep-research` 스킬이 있다면 researcher 에이전트의 **도구**로 활용
  가능 (sub-agent 도 빌트인 스킬에 접근). researcher 에이전트 정의 파일에서 deep-research
  사용 권장을 명시.
- 빌트인 스킬 없으면 WebSearch + WebFetch 조합으로 fallback (graceful degrade — F012 의
  외부 도구 정책 일관).
- 본 ADR 에서 빌트인 스킬의 정확한 인터페이스를 가정하지 않음 — researcher.md 본문에서
  "deep-research 빌트인 스킬이 있으면 활용한다" 정도의 가이드만.

#### 리서치 노트 형식

```markdown
# Research Note — <task-id>

> 작성: researcher 에이전트 | 질의: <원본 질의>
> 호출자: /project:orchestrate (F013)

## 핵심 발견

- (3~5 bullet — 종합 결론)

## 출처별 발견

### 내부 brain (brain-search "...")
- 학습 #NN — ...
- ADR-XXX — ...
- Feature F0XX — ...

### 외부 웹 (WebSearch "...", WebFetch <url>)
- <출처 1 — URL, 발췌, 발견>
- <출처 2>

### 산출물 (Grep / Glob 결과)
- <파일 경로:줄번호> — 발견

## 다음 에이전트를 위한 권장 사항

(designer / developer / architect 가 이 노트를 입력으로 받았을 때 참고할 액션)

## 한계 / 미확인

- (정보 부족·신뢰도 낮은 출처 명시)
```

→ 다음 에이전트가 자연어로 직접 인용. 구조화 JSON 보다 LLM 컨텍스트 친화적.

**영향받는 AC**: AC2 (researcher 에이전트 신규), AC4 (이종 에이전트 간 컨텍스트 전달
규약 — 리서치 노트 형식 부분)

---

### 결정 3 — 이종 에이전트 간 컨텍스트 전달 규약: **C. 구조화 핸드오프 디렉토리 (`.claude/state/orch/<task-id>/`) + 단계별 마크다운 산출물 + orchestrate 커맨드 본문이 각 단계 산출물을 다음 에이전트 입력으로 인라인 주입**

**채택**: 각 orchestrate 실행마다 **task-id** (timestamp + slug) 발급 → `.claude/state/orch/
<task-id>/` 디렉토리 신설 → 단계별 산출물 (`research.md`, `design.md`, `impl.md`,
`review.md`, `final.md`) 을 마크다운으로 저장. orchestrate 커맨드 본문이 supervisor 로서
각 단계 산출물을 읽어 다음 에이전트 호출 시 **인라인 주입** (Task 도구의 prompt 인자에
직접 포함) — sub-agent 컨텍스트 부족 우려 해소.

#### 옵션 비교

| 옵션 | 장점 | 단점 | 결정 |
|---|---|---|---|
| (A) 인라인 전달만 (디스크 저장 X — 메인 컨텍스트 메모리에서만) | 단순, 부수 효과 0 | 세션 종료 후 산출물 사라짐 → 재실행·디버그·QA 검증 불가능 | 약체 |
| (B) 구조화 디렉토리만 (sub-agent 가 알아서 읽어옴) | 단순 (메인 컨텍스트 부담 ↓) | sub-agent context 가 좁아 디렉토리 탐색에 토큰 낭비 + 산출물 누락 위험 | sub-agent 효율 ↓ |
| **(C) 구조화 디렉토리 + 인라인 주입 병행** | 디스크 저장으로 디버그·QA 검증 가능 + sub-agent 는 메인이 주입한 텍스트만 보면 됨 (context 효율 ↑) + task-id 로 동시 실행 격리 | 메인 컨텍스트 토큰 사용 ↑ (각 산출물 인라인 주입) — 단 산출물이 마크다운 산문 (수십 KB 이내) 이라 감당 가능 | **채택** |

#### `.claude/state/orch/<task-id>/` 구조

```
.claude/state/orch/
└── 2026-06-05T14-30-00-add-payment-flow/   # <task-id> = ISO ts + slug
    ├── request.md                            # 원본 사용자 요구사항 + orchestrate 인자
    ├── plan.md                               # supervisor 의 라우팅 계획 (어떤 에이전트 순서로)
    ├── research.md                           # researcher 산출물 (없으면 생략)
    ├── design.md                             # designer 산출물 (UI 무관이면 생략)
    ├── adr.md                                # architect 산출물 (설계 불필요면 생략)
    ├── impl.md                               # developer 산출물 요약 (실제 코드는 git diff)
    ├── review.md                             # reviewer 산출물
    ├── qa.md                                 # qa 산출물 (Playwright 결과 등)
    └── final.md                              # supervisor 의 통합 리포트
```

#### task-id 발급 규칙

- 형식: `<ISO-8601-no-colon>-<slug>` (예: `2026-06-05T14-30-00-add-payment-flow`)
- slug: 원본 요구사항을 kebab-case 로 자동 변환 (40 자 cap, 한글 → romanize 또는
  `task` fallback)
- 충돌 시: timestamp 가 초 단위 — 동시 실행 가능성 낮음. 충돌 시 `-2`, `-3` suffix.

#### 인라인 주입 패턴 (sub-agent 호출 시)

```
# 메인 컨텍스트 (orchestrate 본문) — researcher 호출
Use the researcher agent to investigate:

QUERY: <원본 요구사항>
CONTEXT: <feature_list 발췌 + 관련 learnings + 사용자 추가 정보>

산출물은 stdout 으로 반환. 메인이 .claude/state/orch/<task-id>/research.md 에 저장한다.

# researcher 종료 후 — designer 호출 (research.md 인라인 주입)
Use the designer agent to compare 4 brands for:

USE_CASE: <원본 요구사항에서 추출>
RESEARCH_NOTES: <research.md 의 "핵심 발견" + "다음 에이전트를 위한 권장 사항" 발췌>

# designer 종료 후 — developer 호출 (research.md + design.md 인라인 주입)
Use the developer agent to implement:

FEATURE: <F0XX>
RESEARCH_NOTES: <research.md 발췌>
DESIGN_TOKENS: <design.md 의 tokens 시안>
ADR: <adr.md 의 결정·구현 가이드 발췌>
```

→ 각 sub-agent 는 **직전 단계 산출물의 발췌**를 입력으로 받음. supervisor 가 발췌 책임을
짐 — 어떤 부분이 다음 단계에 핵심인지 supervisor 가 판단.

#### gitignore 정책

- `.claude/state/orch/*` → **gitignore** (실행마다 새 task-id, 영구 보관 부담 ↑)
- 단, `.claude/state/orch/.gitkeep` 은 커밋 (디렉토리 보존)
- 사용자가 특정 task 를 영구 보관하려면 수동으로 `.claude/state/orch/<task-id>/` 를
  `docs/orch-archive/` 같은 위치로 복사 (별도 정책 — 본 ADR 범위 외)

→ qa-browser 의 `.claude/state/qa-browser/{screenshots,runs}/` 패턴 100% 일관.

**근거**:

- **qa-browser 패턴 100% 일관**: F008 의 `.claude/state/qa-browser/runs/` 가 실행 로그
  보존 + gitignore 패턴. 본 결정은 같은 정신 확장.
- **single-host 컨텍스트 효율**: sub-agent 가 받는 토큰을 supervisor 가 통제 → 컨텍스트
  전달 손실을 supervisor 의 발췌 품질로 보정. d-3 (이종 호스트 분산) 와 달리 같은
  컨텍스트 풀이라 발췌 품질이 곧 손실 최소화.
- **디버그·QA 검증 가능성**: 핸드오프 디렉토리가 디스크에 남으면 QA 가 "왜 designer 가
  spotify 를 골랐나" 같은 질문에 design.md 를 직접 읽어 답할 수 있음.
- **동시 실행 격리**: task-id 분리로 두 orchestrate 가 동시 실행되어도 핸드오프 충돌 없음.

**영향받는 AC**: AC4 (이종 에이전트 간 컨텍스트 전달 규약)

---

### 결정 4 — 오케스트레이션 흐름·라우팅 규칙: **A. 조건부 라우팅 — supervisor 가 요구사항 분석 → 필요 단계만 spawn (모든 요청이 풀 파이프라인 X) + 의심스러우면 단계 추가 (보수적 기본값)**

**채택**: orchestrate 는 정해진 파이프라인을 강제하지 않는다. 요구사항을 분석해 **필요한
단계만** spawn — 단순 버그 수정은 developer + reviewer 만, 복합 UI 신기능은 researcher
+ designer + architect + developer + reviewer + qa 풀 파이프라인. 의심스러우면 단계 추가
(실수 비용이 더 크다 — plan-full 의 "설계 필요 판정" 정신 일관).

#### 옵션 비교

| 옵션 | 장점 | 단점 | 결정 |
|---|---|---|---|
| **(A) 조건부 라우팅 (필요 단계만 spawn)** | 토큰·시간 효율 ↑, 단순 요청은 가벼움, plan-full "설계 필요 판정" 일관, 복잡 요청은 풀 파이프라인 | 라우팅 판정 규칙 학습 비용 1 — 본 ADR + orchestrate.md 본문이 단일 소스 | **채택** |
| (B) 풀 파이프라인 강제 (모든 요청이 R→D→A→Dev→R→QA) | 일관 단순 | 단순 버그 수정도 researcher 호출 — 토큰 낭비 + 사용자 신뢰 ↓ | 비효율 |
| (C) 사용자가 명시 (`--steps=research,design,dev`) | 사용자 통제 ↑ | 사용자가 단계 선택 학습 부담 — orchestrate 의 자동화 가치 ↓ | 자동화 의도 어긋남 |

#### 라우팅 판정 규칙 (supervisor 가 요구사항 분석 시 적용)

| 조건 | 필요한 단계 | 비고 |
|---|---|---|
| 신규 도메인 / 모르는 외부 API / 학술적 배경 필요 | **researcher 호출** | 키워드: "조사", "왜", "어떻게 X 가 작동", "X 의 비교", 외부 라이브러리·서비스 이름 |
| UI 컴포넌트 / 화면 / 디자인 시스템 / 토큰 변경 | **designer 호출** | 키워드: "디자인", "UI", "스타일", "색", "폰트", "레이아웃", 화면 이름 |
| 신규 DB 테이블 / 외부 API 연동 / 모듈 의존성 변경 / 3+ 파일 구조 변경 / 보안·인증 | **architect 호출 (ADR 작성)** | plan-full Step 2 의 "설계 필요 판정" 그대로 |
| 코드 변경 (거의 모든 요청) | **developer 호출** | 단순 1 줄 변경이면 직접 호출 안 하고 supervisor 가 메인 컨텍스트에서 변경할 수도 있음 — 단 본 ADR 은 sub-agent 호출 표준 권장 |
| 코드 변경 후 (거의 모든 요청) | **reviewer 호출** | 보안·성능·품질 |
| acceptance_criteria 가 동작 기술 (로그인, 폼 제출, 라우팅 등) | **qa 호출 (+ qa-browser)** | F008 호출 기준 일관 |
| UI 변경 + design-review 가 의미 있을 때 | **design-review 커맨드 호출 (reviewer 통과 후)** | F007 호출 기준 일관 |

#### 라우팅 매트릭스 (의도 vs 호출 단계)

| 요청 카테고리 | researcher | designer | architect | developer | reviewer | qa | design-review |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| 신규 UI 컴포넌트 (디자인 시스템 있음) | ❌ | ✅ | ❌ | ✅ | ✅ | ✅ | ✅ |
| 신규 UI 컴포넌트 (디자인 시스템 미정) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| 신규 외부 API 연동 (모르는 서비스) | ✅ | ❌ | ✅ | ✅ | ✅ | (조건부) | ❌ |
| 신규 DB 스키마 | (조건부) | ❌ | ✅ | ✅ | ✅ | ❌ | ❌ |
| 단순 버그 수정 | ❌ | ❌ | ❌ | ✅ | ✅ | ❌ | ❌ |
| 리팩토링 (구조 변경) | ❌ | ❌ | ✅ | ✅ | ✅ | ❌ | ❌ |
| typo / 문구 변경 | ❌ | ❌ | ❌ | (조건부 — 메인 직접) | ❌ | ❌ | ❌ |

→ 풀 파이프라인은 "신규 UI 컴포넌트 (디자인 시스템 미정) + 외부 API 연동" 같은 복합
요청. 대부분의 요청은 일부 단계만 활성.

#### 순차 vs 병렬

| 단계 쌍 | 의존성 | 병렬 가능? |
|---|---|---|
| researcher → architect | architect 가 research 결과 참조 | ❌ 순차 |
| researcher → designer | designer 가 research 결과 참조 | ❌ 순차 |
| architect ↔ designer | 일반적으로 독립 (아키텍처와 디자인은 다른 축) | ✅ 병렬 (Task 도구로 동시 spawn) |
| developer → reviewer | reviewer 가 code 검토 | ❌ 순차 |
| reviewer → design-review | design-review 가 동작하는 코드 + reviewer 통과 가정 (F007) | ❌ 순차 |
| design-review → qa-browser | qa-browser 가 정적 디자인 통과 후 동적 검증 (F008) | ❌ 순차 |

→ **architect ↔ designer 만 병렬 후보**. 나머지는 순차. 본 ADR 은 병렬 강제하지 않음 —
supervisor 가 판단 (병렬 spawn 은 단일 Task 도구 호출에 여러 sub-agent prompt 를 포함하는
패턴).

#### 실패·재작업 루프

| 단계 실패 | 대응 |
|---|---|
| reviewer NEEDS REVISION | developer 재호출 (최대 2 회) — 그래도 실패 시 architect 재호출 (설계 재검토) |
| qa FAIL | developer 재호출 (최대 2 회) — 그래도 실패 시 architect 재호출 |
| design-review BLOCK | designer 재호출 (최대 2 회) — 그래도 실패 시 사용자 ESCALATE |
| 어떤 단계든 ESCALATION 태그 | supervisor 가 final.md 에 `[ESCALATED]` 기록 + 사용자에게 보고 — 자동 진행 중단 |

→ plan-full "Reviewer NEEDS REVISION 2 회 반복 → Planner 재분해" 패턴 일관.

#### plan-full 과의 통합 흐름 (선택적)

```
사용자: "결제 시스템 추가" (복합 요청)
  ↓
[선택] /project:plan-full 결제 시스템 추가
  → feature_list F0XX 추가 + ADR-NNN 작성
  ↓
/project:orchestrate F0XX
  → supervisor 가 F0XX 의 acceptance_criteria 분석
  → researcher (결제 API 비교) + designer (결제 페이지 디자인) 병렬 spawn
  → developer 구현
  → reviewer + design-review + qa
  → final.md 통합 리포트
```

→ orchestrate 가 `--feature=F0XX` 인자 지원 (선택). 인자 없으면 자연어 요구사항을 직접
받음 — 가벼운 1 회성 요청에도 사용 가능.

**근거**:

- **plan-full 패턴 일관**: 조건부 판정 (설계 필요 vs 불필요) 정신 그대로 확장.
- **토큰 효율**: 풀 파이프라인 강제는 단순 버그 수정에 토큰 5~10 배 낭비 — d-1 의 "비용
  최적" 정신 위배.
- **보수적 기본값**: 의심스러우면 단계 추가 — gatekeeper 의 "50/50 이면 ESCALATE" 정신
  일관. 누락 비용이 추가 비용보다 큼.
- **사용자 통제 vs 자동화 균형**: 라우팅은 자동, 단 사용자가 `--steps=` 인자로
  override 가능 (옵션).

**영향받는 AC**: AC3 (orchestrator 커맨드 — 라우팅 본체), AC5 (오케스트레이션 흐름 예시
— 라우팅 매트릭스 표 + plan-full 통합 흐름)

---

### 결정 5 — single-host 강제 + d-1/d-2/d-3 경계 명시: **모든 sub-agent 는 Claude Code Task 도구로 spawn (같은 컨텍스트 풀) + 본 ADR 은 d-1 한정 + d-2/d-3 은 별도 ADR (지금 안 함)**

**채택**: orch 변형은 **single-host 만**. 모든 sub-agent (researcher/designer/architect/
developer/reviewer/qa) 는 Claude Code 의 Task 도구로 spawn 되어 같은 컨텍스트 풀을
공유한다. 이종 호스트 분산 (Codex / OpenClaw 다른 모델로 라우팅) 은 d-3 후속 phase, 본
ADR 범위 외. d-2 (로컬 LLM, GPU 필요) 도 별도 ADR.

#### 옵션 비교

| 옵션 | 장점 | 단점 | 결정 |
|---|---|---|---|
| **(A) single-host 만 (d-1)** | 컨텍스트 풀 공유 → 전달 손실 최소, 비용 예측 가능, 즉시 가능, F006 ADR-001 single-host 격리 정신 일관 | 다른 모델 강점 활용 불가 (단 d-1 가치가 우선) | **채택** |
| (B) 이종 호스트 분산 옵션 (d-3 일부 포함) | 다른 모델 강점 활용 | 컨텍스트 전달 손실 + 호스트 간 호출 인프라 필요 (host.py 의 stub 어댑터 실구현 필수) — 본 phase 부담 ↑ | d-3 후속 |
| (C) 로컬 LLM 통합 (d-2 일부 포함) | researcher 의 본문 요약·검색 결과 합성을 로컬 small model 로 위임 → 비용 ↓ | GPU 필요 + 로컬 LLM 모델 관리 부담 ↑ + 본 phase 의 "(d) 즉시 가능" 가치 손실 | d-2 후속 |

#### d-1 / d-2 / d-3 경계표 (단일 소스)

| 단계 | 의미 | 호스트 | 컨텍스트 | GPU | 본 ADR 범위 | 후속 ADR |
|---|---|---|---|:---:|:---:|---|
| **d-1** | single-host supervisor + sub-agent 오케스트레이션 (Claude Code Task 도구) | Claude Code 만 | 같은 풀 (전달 손실 최소) | ❌ | **✅ 본 ADR** | — |
| d-2 | 로컬 small LLM 통합 (researcher 요약·검색 합성 등 일부 단계만 로컬) | Claude Code + 로컬 LLM (Ollama/llama.cpp 등) | 부분 분리 (로컬 LLM 출력만 hand-off) | ✅ | ❌ | ADR-009 가칭 — 로컬 LLM 어댑터 + 도구·메모리 분리 |
| d-3 | 이종 호스트 분산 (Claude Code + Codex + OpenClaw 다른 모델로 작업 라우팅) | 다중 (host.py 실어댑터 활용) | 풀 분리 (호스트 간 메시지 전달) | (선택) | ❌ | ADR-010 가칭 — 호스트 간 라우팅·메시지 규약·OpenClaw 어댑터 실구현 |

#### d-2 / d-3 을 지금 안 하는 근거

- **d-2 (로컬 LLM)**: GPU 전제 — 사용자 환경 (개발 머신 + downstream 사용자) 의 GPU
  가용성 불확실. 본 phase 의 "즉시 가능 + 비용 무관" 가치 손실. 또한 로컬 small model 의
  품질이 opus 4.7 + sonnet 4.6 보다 낮을 가능성 ↑ — researcher 품질 손실 위험.
- **d-3 (이종 호스트 분산)**: 컨텍스트 전달 손실이 본질적. 같은 컨텍스트 풀에서 supervisor
  가 발췌·인라인 주입할 때조차 손실이 있는데, 다른 호스트로 메시지 전달 시 손실 ↑.
  또한 host.py 의 codex/openclaw 어댑터가 stub 인 상태 — 실구현 부담 ↑. 진짜 가치가
  분명한 use case 가 나오기 전엔 보류.

#### orch 변형의 host.py 와의 관계

orch 변형도 F006 host.py 의 다중 호스트 지원을 보유. 단, 본 ADR 에서는 **single-host 가
정상 모드**. 사용자가 `/project:host set codex` 한 상태에서 `/project:orchestrate` 호출
시 → 동작은 하되 codex stub 어댑터의 안내 메시지가 먼저 출력됨 (F006 정신 일관). d-3
실구현 후엔 codex/openclaw 어댑터가 sub-agent spawn 을 호스트별로 분기 — 그건 ADR-010
가칭 범위.

**근거**:

- **컨텍스트 전달 손실 최소화 = single-host 가 답**: same context pool = sub-agent 가
  메인의 발췌만 보더라도 같은 토크나이저·동일 의미론. 호스트 분산 시 의미 손실 (다른
  모델은 다른 토크나이저·다른 학습 분포).
- **즉시 가능 (GPU 무관)**: d-1 은 Claude Code 기본 도구만 사용 — 사용자가 추가 인프라
  구축 0 으로 즉시 활용. wiki 변형의 외부 도구 도입과 달리 orch 는 의존성 0.
- **점진적 진화 경로 명시**: d-1 (지금) → d-2 (필요 시) → d-3 (먼 미래·어쩌면 불필요)
  명확한 단계로 미래 결정 비용 ↓. wiki 변형의 후속 phase 분리 (qmd MCP, Marp 자동 변환,
  enrich-llm) 와 같은 정신.

**영향받는 AC**: AC6 (single-host 원칙), AC9 (ADR-008 d-2/d-3 경계)

---

### 결정 6 — F012 멱등성 결함 처리 방침: **B. 별도 트랙 (F013 후속 chore 로 분리) — orch 변형에서 함께 fix 하지 않음**

**채택**: F012 wiki.py 의 ingest `created` timestamp 멱등성 결함 (학습 #54
`wiki-ingest-created-timestamp-non-idempotent`) 은 wiki.orch 변형에 그대로 복사된 상태.
**orch 변형에서 함께 fix 하지 않는다** — 별도 chore (F014 가칭) 로 분리. orch 의 책임
경계 (이종 에이전트 오케스트레이션) 와 wiki 결함 (벨류 직렬화 부수 효과) 은 카테고리가
다름. orch 가 wiki 코드를 건드리면 변형 격리 가드 (LINT-MR-6) 가 흐려지고, 두 변형의
미러 정합이 한 phase 안에 두 가지 변경을 포함하게 됨 — Surgical Changes 위배.

#### 옵션 비교

| 옵션 | 장점 | 단점 | 결정 |
|---|---|---|---|
| (A) orch 변형에서 함께 fix (orch 작업 중) | 한 번에 fix — 사용자 입장 효율 | orch 의 책임 (오케스트레이션) 밖 변경 → Surgical Changes 위배, wiki/orch 두 변형의 wiki.py 가 동시 변경 → mirror diff 복잡도 ↑, F012 가 closed (passes=true) 상태인데 closed feature 의 코드 수정 → 거버넌스 흐림 (closed feature 는 chore 로만 수정) | Surgical Changes 위배 |
| **(B) 별도 트랙 (F013 후속 chore F014 가칭)** | 한 phase 당 한 가지 책임 (Karpathy Surgical Changes), wiki 변형도 같이 fix 가능 (single SSoT), F012 closed feature 의 코드 수정은 chore 카테고리로 자연스러움 | 사용자 입장에서 fix 가 미뤄짐 — 단 학습 #54 가 이미 기록되어 잊히지 않음 | **채택** |
| (C) orch 변형에서 무시 (wiki 기능 부차적) | 작업 부담 0 | 결함이 누적된 상태로 wiki/orch 두 변형에 존재 → 추후 fix 시 두 변형 동시 미러 부담 ↑ | 누적 부담 |

#### 후속 chore F014 가칭 설계 가이드 (간단)

- F014 (가칭): "wiki.py ingest 멱등성 fix — created 보존 + updated 별도 필드"
- 영향 변형: wiki, wiki.orch (둘 다 wiki.py 보유)
- 검증: 같은 입력 2 회 ingest → frontmatter `created` 동일, `updated` 만 갱신, git diff 0
  (created), nonzero (updated 만)
- learnings.jsonl 학습 #54 가 본 ADR 의 후속 액션 단일 소스
- F013 closed 직후 즉시 chore 로 처리 권장 (잊히기 전)

#### orch phase 안에서의 명시적 제약

orch phase (F013) 작업 중 wiki.py 수정 절대 금지. wiki.py 는 wiki/orch 두 변형 모두에서
F012 시점 그대로 유지. 본 ADR 의 "피해야 할 패턴" 섹션에 명시.

**근거**:

- **Karpathy Surgical Changes 원칙**: 한 phase 는 한 가지 책임. orch (이종 에이전트
  오케스트레이션) 와 wiki 멱등성 fix 는 다른 책임 — 묶지 않는다.
- **closed feature 보호**: F012 는 passes=true 로 closed. closed feature 의 코드 수정은
  별도 chore 로만 — 거버넌스 정합 (lint.py LINT-FL 의 status×passes 가드 정신 일관).
- **변형 미러 단순성**: orch phase 가 wiki.py 미수정 → wiki/orch 의 wiki.py 가 F012 시점
  과 동일 → LINT-MR-6 의 "wiki 오버레이 일관성" 검증이 단순. F014 후속에서 두 변형의
  wiki.py 동시 fix → 한 번에 양쪽 미러 → 단순.
- **학습 #54 가 단일 소스**: 잊힐 위험 0. handoff 직후 사용자가 F014 chore 진행 가능.

**영향받는 AC**: AC10 ((주의) wiki 변형 복사로 따라온 F012 멱등성 결함 처리 방침 결정 —
"orch 변형에선 fix 하지 않음, F014 후속 chore" 명시)

---

### 결정 7 — LINT-MR 7 변형 확장: **MR-1 ~ MR-7 검사 대상에 ⓑ⁗ (orch) 추가 + 신규 MR-8 (orch 오버레이 격리, researcher 에이전트 + orchestrate 커맨드 + 핸드오프 디렉토리 wiki 변형까지에는 부재 / orch 변형에는 존재)**

**채택**: 기존 MR-1 ~ MR-7 (F011/F012) 의 검사 대상 변수에 `claude.gstack.auto.design.
wiki.orch` 추가. 신규 **MR-8 (orch 오버레이 격리)** 를 추가 — orch 오버레이 (researcher
에이전트 정의 + orchestrate 커맨드 + 핸드오프 디렉토리 골격) 가 ⓑ⁗ 변형에만 존재하고
ⓐ/ⓑ/ⓑ′/ⓑ″/ⓑ‴ 5 변형에 부재함을 자동 검증.

#### LINT-MR 항목 전체 (F012 의 7 → F013 의 8)

| # | 항목 | 검사 방법 | 본 phase 변경 |
|---|---|---|---|
| MR-1 | (F011) ⓑ 표준 변형에 자율 오버레이 부재 | (변경 없음) | (변경 없음) |
| MR-2 | (F011) ⓑ 표준 변형의 settings.json Bash(*) 미사용 | (변경 없음) | (변경 없음) |
| MR-3 | (F011) ⓑ 표준 변형의 CLAUDE.md Autonomous Mode 헤딩 부재 | (변경 없음) | (변경 없음) |
| MR-4 | (F011/F012) ⓐ/ⓑ/ⓑ′ 변형에 디자인 오버레이 부재 | **검사 대상 추가**: ⓑ‴ + ⓑ⁗ 는 디자인 오버레이 보유 (변수 `_VARIANTS_NO_DESIGN` 무수정 — 이미 3 변형 한정) | (변경 없음) |
| MR-5 | (F011/F012) ⓑ″ + ⓑ‴ 디자인 변형에 디자인 오버레이 존재 | **검사 대상 추가**: ⓑ⁗ 도 디자인 오버레이 보유 — 변수 `_VARIANTS_WITH_DESIGN` 에 `"claude.gstack.auto.design.wiki.orch"` 추가 | **수정** |
| MR-6 | (F012) ⓐ/ⓑ/ⓑ′/ⓑ″ 4 변형에 wiki 오버레이 부재 | **검사 대상 변경 없음** — orch 변형은 wiki 오버레이 보유 (wiki 의 1:1 복사) — `_VARIANTS_NO_WIKI` 무수정. wiki 변형 보유 검사는 명시적으로 `_VARIANTS_WITH_WIKI = ["claude.gstack.auto.design.wiki", "claude.gstack.auto.design.wiki.orch"]` 신설 | **수정** |
| MR-7 | (F012) 5 변형 (ⓐ/ⓑ/ⓑ′/ⓑ″/ⓒ) 에 외부 의존성 매니페스트 부재 | **검사 대상 변경 없음** — orch 변형은 wiki 의 1:1 복사라 wiki-setup.sh 존재 (정상) — `_VARIANTS_NO_EXTERNAL_DEPS` 무수정 (5 변형 그대로). 외부 의존성 허용 검사 대상도 ⓑ⁗ 포함 (wiki 변형 외부 의존성 정책 상속) | (변경 없음 — 변수 의미만 갱신) |
| **MR-8** | **ⓐ/ⓑ/ⓑ′/ⓑ″/ⓑ‴ 5 변형에 orch 오버레이 부재** | researcher.md, orchestrate.md, `.claude/state/orch/.gitkeep` 디렉토리 존재 여부 — 5 변형에 있으면 BLOCK | **신규** |
| **MR-8 (이어서)** | **ⓑ⁗ 변형에 orch 오버레이 모두 존재** | `_VARIANTS_WITH_ORCH = ["claude.gstack.auto.design.wiki.orch"]` 에 모두 존재 — 누락 시 CONCERN | **신규** |

#### lint.py 변경 범위 (추가 + 변수 갱신만)

```python
# .claude/bin/lint.py — F013 추가/수정 (예상)
_ORCH_OVERLAY_FILES = [
    "harness/.claude/agents/researcher.md",
    "harness/.claude/commands/orchestrate.md",
]
_ORCH_OVERLAY_DIRS = [
    "harness/.claude/state/orch",   # .gitkeep 보존
]
_VARIANTS_NO_ORCH = [
    "claude",
    "claude.gstack",
    "claude.gstack.auto",
    "claude.gstack.auto.design",
    "claude.gstack.auto.design.wiki",
]
_VARIANTS_WITH_ORCH = ["claude.gstack.auto.design.wiki.orch"]
_VARIANTS_WITH_WIKI = [
    "claude.gstack.auto.design.wiki",
    "claude.gstack.auto.design.wiki.orch",
]
_VARIANTS_WITH_DESIGN = [
    "claude.gstack.auto.design",
    "claude.gstack.auto.design.wiki",
    "claude.gstack.auto.design.wiki.orch",
]

# check_mirror_regression() 에 MR-8 블록 추가 + MR-5/MR-6 변수 갱신
# 기존 MR-1 ~ MR-7 본문 무수정 — 변수 의미만 확장
```

#### 변형 매트릭스 (7 변형, 본 결정 기준)

| 변형 | 자율 | 디자인 | wiki | **orch** | 외부 의존성 |
|---|:---:|:---:|:---:|:---:|---|
| ⓐ `claude/` | ❌ | ❌ | ❌ | ❌ | 0 |
| ⓑ `claude.gstack/` | ❌ | ❌ | ❌ | ❌ | 0 |
| ⓑ′ `claude.gstack.auto/` | ✅ | ❌ | ❌ | ❌ | 0 |
| ⓑ″ `claude.gstack.auto.design/` | ✅ | ✅ | ❌ | ❌ | 0 |
| ⓑ‴ `claude.gstack.auto.design.wiki/` | ✅ | ✅ | ✅ | ❌ | 허용 (Obsidian/qmd/Marp) |
| **ⓑ⁗ `claude.gstack.auto.design.wiki.orch/`** | ✅ | ✅ | ✅ | **✅** | 허용 (wiki 상속) |
| ⓒ `openai/.codex/` | ❌ | ❌ | ❌ | ❌ | 0 |

→ 누적형 7 변형. orch 변형은 wiki 변형의 모든 자산을 상속하고 orch 오버레이 추가.

**근거**:

- **F011/F012 LINT-MR 패턴 일관**: MR-1 ~ MR-7 의 정신 그대로 — 본 phase 가 8 번째 가드
  추가.
- **MR-8 의 의의**: orch 변형의 격리를 자동 검증 — orch 오버레이가 다른 6 변형에 잘못
  미러되는 회귀 자동 차단.
- **변수 의미 확장만**: lint.py 본체 함수 무수정 (MR-5/MR-6 의 _VARIANTS_WITH_DESIGN /
  _VARIANTS_WITH_WIKI 만 갱신) — Surgical Changes.

**영향받는 AC**: AC7 (LINT-MR 7 변형 확장 — orch 오버레이 격리 검사)

---

### 결정 8 — F013 세션 분할: **3 세션 (사용자 estimated_sessions=3 일치)**

**채택**: feature_list.estimated_sessions=3 일관. 세션 1 이 researcher 에이전트 + orchestrate
커맨드 골격 + 핸드오프 규약, 세션 2 가 라우팅 규칙 + 흐름 예시 + 컨텍스트 전달 구현, 세션 3
이 LINT-MR 확장 + CLAUDE.md + 미러 + F012 멱등성 처리 방침 명시. F011/F012 3 세션 분할
패턴 일관.

#### 세션 분할 표

| 세션 | 범위 | 산출물 | AC 충족 |
|---|---|---|---|
| **세션 1** — 에이전트 + 커맨드 골격 + 핸드오프 규약 | `claude.gstack.auto.design.wiki.orch/` 변형은 이미 cp -r 완료 (사용자 사전 작업), `.claude/agents/researcher.md` 신규 (opus + WebSearch/WebFetch + 리서치 노트 형식), `.claude/commands/orchestrate.md` 신규 (커맨드 본문 — supervisor 책임·라우팅 판정 가이드·인라인 주입 패턴), `.claude/state/orch/.gitkeep` 신규 + gitignore 갱신, ADR-008 미러 (ⓑ + ⓑ′ + ⓑ″ + ⓑ‴ + ⓑ⁗ 5 변형 — 거버넌스 ADR 은 baseline 외 모두 미러) | researcher.md, orchestrate.md, 핸드오프 디렉토리, gitignore, ADR-008 | AC1 (변형 신설 — 이미 완료), AC2 (researcher 에이전트), AC3 (orchestrate 커맨드 골격), AC4 (핸드오프 규약 — 디렉토리 + 리서치 노트 형식) |
| **세션 2** — 라우팅 규칙 본체 + 흐름 예시 + 컨텍스트 전달 구현 | orchestrate.md 본문 완성 (라우팅 매트릭스 + 순차/병렬 표 + 실패·재작업 루프 + plan-full 통합 흐름), `docs/orch-examples/` 디렉토리 신설 + 예시 시나리오 3 개 ("신규 UI + 외부 API" / "단순 버그 수정" / "리팩토링") .md 산출물, learnings 1~2 개 append (오케스트레이션 결정 + single-host 원칙 강화) | orchestrate.md 완성, docs/orch-examples/3 개 시나리오, learnings | AC3 (orchestrate 라우팅 본체), AC5 (흐름 예시), AC6 (single-host 원칙 — 매뉴얼 명시) |
| **세션 3** — LINT-MR + CLAUDE.md + 미러 정합 + F012 멱등성 처리 방침 | `.claude/bin/lint.py` MR-5/MR-6 변수 갱신 + MR-8 신규 + helper test (현재 변형 7 매트릭스 검증), CLAUDE.md 빠른 시작 + 호출 기준 + 7 변형 매트릭스 + 디렉토리 트리 갱신, learnings 2~3 개 append, **F012 멱등성 결함 별도 트랙 명시 (claude-progress.txt + F014 가칭 placeholder 또는 README), 최종 미러 동기화 (ⓑ + ⓑ′ + ⓑ″ + ⓑ‴ + ⓑ⁗ 5 변형) | lint.py MR-8, CLAUDE.md, learnings, F014 placeholder, 최종 미러 | AC7 (LINT-MR 7 변형 확장), AC8 (CLAUDE.md 7 변형 매트릭스), AC9 (ADR-008 — 본 ADR 자체), AC10 (F012 멱등성 처리 방침 — F014 후속 chore 명시) |

#### 세션 분할 근거

- **세션 1 의 응집도**: researcher 에이전트 + orchestrate 커맨드 + 핸드오프 디렉토리는
  모두 "이종 에이전트 오케스트레이션 인프라" 카테고리. 한 세션 응집도 ↑.
- **세션 2 의 응집도**: 라우팅 규칙 + 흐름 예시 + 컨텍스트 전달은 모두 "오케스트레이션
  동작 정의" 카테고리. orchestrate.md 본문 완성 + 시연 가능한 흐름 예시.
- **세션 3 의 응집도**: LINT-MR + CLAUDE.md + 미러 + F012 처리 방침은 모두 "통합 +
  거버넌스 가드 + 문서화" 카테고리. F011/F012 세션 3 정신 일관.

#### 대안 비교

| 옵션 | 장점 | 단점 | 결정 |
|---|---|---|---|
| **(A) 3 세션** | feature_list 일관, F011/F012 와 같은 호흡, 응집도 ↑ | 세션 1 의 researcher.md + orchestrate.md 골격 작성이 부담 — 단 본 ADR 의 모든 결정이 가이드 | **채택** |
| (B) 2 세션 (압축) | 세션 수 ↓ | 세션 1 부하 ↑ + 회귀 위험 ↑ | 부담 ↑ |
| (C) 4 세션 (라우팅/흐름 분리) | 부하 최소 | feature_list 와 불일치, 과도 분할 | 과함 |

**근거**: F011 (디자인 변형) + F012 (wiki 변형) 의 3 세션 분할 성공 패턴 100% 일관. F013
도 변형 인프라 → 동작 정의 → 통합 거버넌스 가 자연스러움.

**영향받는 AC**: 전체 진행 계획 (feature_list.estimated_sessions=3 유지)

---

## 대안 검토 (요약)

| 대안 | 장점 | 단점 | 제외 이유 |
|---|---|---|---|
| orchestrator.md 에이전트 신설 (결정 1 A) | 에이전트 정의 캡슐화 | sub-agent 안에서 재귀 spawn — 컨텍스트 전달 손실 ↑ | 결정 1 |
| plan-full 확장 (결정 1 C) | DRY 진입점 1 | plan-full 정체성 흐려짐, 도움말 비대 | 결정 1 |
| researcher 모델 sonnet (결정 2 A) | 비용 ↓ | 합성·요약 품질 ↓ | 결정 2 |
| researcher 도구 Read/Glob/Grep/Bash 만 (결정 2 A) | 외부 의존성 0 | 본질 (외부 출처 종합) 50% 손실 | 결정 2 |
| researcher 도구에 Write 추가 (결정 2 C) | 직접 저장 가능 | sub-agent 부수 효과 ↑ — 메인 통제 ↓ | 결정 2 |
| 인라인 전달만 (결정 3 A) | 단순 | 세션 종료 후 산출물 사라짐 — 디버그 불가 | 결정 3 |
| 구조화 디렉토리만 (결정 3 B) | 메인 부담 ↓ | sub-agent context 비효율 | 결정 3 |
| 풀 파이프라인 강제 (결정 4 B) | 일관 | 단순 요청에도 토큰 낭비 | 결정 4 |
| 사용자 명시 단계 (결정 4 C) | 통제 ↑ | 자동화 가치 ↓ | 결정 4 |
| 이종 호스트 분산 옵션 포함 (결정 5 B) | 다른 모델 활용 | 컨텍스트 손실 + host.py stub 실구현 부담 | 결정 5 |
| 로컬 LLM 통합 (결정 5 C) | 비용 ↓ | GPU 전제 + 품질 위험 | 결정 5 |
| orch 변형에서 멱등성 fix (결정 6 A) | 한 번에 fix | Surgical Changes 위배 + closed feature 코드 수정 | 결정 6 |
| 멱등성 무시 (결정 6 C) | 작업 0 | 두 변형에 결함 누적 | 결정 6 |
| 2 세션 분할 (결정 8 B) | 세션 수 ↓ | 세션 1 부하 ↑ | 결정 8 |
| 4 세션 분할 (결정 8 C) | 부하 최소 | feature_list 불일치 | 결정 8 |

---

## 결과

### 긍정적 영향

- **F013 모든 AC 충족 예정** (AC1~AC10, 세션별 매핑은 결정 8 표 참조)
- **(d) 장면의 진짜 이름 = supervisor pattern 명시화**: 사용자와의 깊은 논의 결론을 ADR
  로 동결. 향후 "OpenClaw 가 (d) 의 답이냐" 같은 혼동 방지
- **빠진 조각 보충**: researcher 에이전트 신규 — 7 → 8 에이전트 라인업 (planner/architect/
  developer/reviewer/qa/gatekeeper/designer/researcher). 코딩+디자인+리서치 삼각형 완성
- **single-host 정신 강화**: F006 ADR-001 의 single-host 격리 정신을 오케스트레이션
  레이어로 확장 — 컨텍스트 전달 손실 최소화 원칙이 변형/호스트/에이전트 3 레벨에서 일관
- **d-1/d-2/d-3 경계 명시**: 미래 분산 확장의 단계 구분이 명확. d-2/d-3 의 후속 ADR
  (ADR-009/010 가칭) 가이드라인이 본 ADR 에 단일 소스로 존재
- **무회규**: F001~F012 동작 무수정. 7 에이전트 + 기존 헬퍼·커맨드·훅 그대로
- **F005~F012 패턴 100% 일관**: 단일 파일 신규 헬퍼 0 (orchestrate 는 메타커맨드 — 별도
  Python 헬퍼 없음, 사용자에게 가벼움), 핸드오프 디렉토리는 qa-browser state 패턴 일관,
  변형 미러 + LINT-MR 가드 + ADR + CLAUDE.md 매트릭스 일관
- **7 변형 매트릭스**: F012 의 6 변형 → 7 변형 누적. LINT-MR-8 가드로 자동 격리
- **plan-full 과의 통합 흐름 명시**: 두 메타커맨드의 역할 분리 + 조합 가능성 (plan-full
  → orchestrate) 매뉴얼 명시 — 사용자 학습 비용 ↓
- **F012 멱등성 결함의 후속 액션 명시**: F014 가칭 chore 로 분리 — 잊힐 위험 0, 학습 #54
  단일 소스

### 부정적 영향 / 트레이드오프

- **신규 변형 1 개** (`claude.gstack.auto.design.wiki.orch/`) — wiki 변형의 1:1 복사 +
  orch 오버레이 ≈ 디스크 사용량 ↑ (≈ 1.4MB 추가) + 미러링 시간 ↑
- **신규 파일 3 개** (`.claude/agents/researcher.md`, `.claude/commands/orchestrate.md`,
  `docs/adr/ADR-008-*.md`) — `docs/orch-examples/*.md` 추가 시 3~6 개로 증가
- **`.gitignore` 추가** (`.claude/state/orch/*` 단 `.gitkeep` 예외) — 1 줄 추가
- **`.claude/bin/lint.py` 수정** (LINT-MR-8 추가 + MR-5/MR-6 변수 갱신) — F009/F011/F012
  산출물 변경. 단, 추가 + 변수 교체만 — 본 ADR-008 결정 7 의 격리 강제 일관
- **CLAUDE.md 갱신** (빠른 시작 + 호출 기준 + 7 변형 매트릭스 표 + 디렉토리 트리) — 분량
  ↑ 약 30~50 줄
- **에이전트 8 개 = 학습 비용 1**: planner/architect/developer/reviewer/qa/gatekeeper/
  designer/**researcher** — 에이전트 카탈로그 표 갱신 필요 (CLAUDE.md 에이전트 역할
  분담 섹션)
- **orchestrate 커맨드 본문 분량 ↑**: 라우팅 매트릭스 + 인라인 주입 패턴 + 시나리오 예시
  포함 → 본문 200~300 줄 예상. plan-full (175 줄) 보다 분량 ↑ — 단 본 ADR 의 모든 표가
  단일 소스
- **F013 작업 중 wiki.py 미수정 강제**: orch 가 wiki 변형의 1:1 복사라 wiki.py 멱등성
  결함이 그대로 복사됨. 본 phase 안에서 fix 안 함 — F014 후속 chore 로 분리 (결정 6).
  학습 #54 가 단일 소스
- **researcher 의 외부 도구 (WebSearch/WebFetch)**: 외부 의존성 정책상 wiki 변형의 외부
  도구 정책 예외 카테고리에 들어감. 단 도구 자체는 Claude Code 빌트인 — 변형 외부 의존성
  추가 0 (사용자가 별도 설치 안 함). 본 ADR 의 결정 2 가 명시
- **d-2/d-3 가 미정 상태**: 본 ADR 은 d-1 한정 — 향후 d-2 (로컬 LLM) / d-3 (이종 호스트
  분산) 의 본격 설계는 ADR-009/010 가칭. 사용자가 "왜 지금 d-3 안 하나" 묻는 경우 결정
  5 의 근거표가 단일 소스

### 후속 조치

- [ ] (F013 세션 1) researcher.md + orchestrate.md 골격 + 핸드오프 디렉토리 + ADR-008 미러
- [ ] (F013 세션 2) orchestrate.md 라우팅 본체 + docs/orch-examples/ 시나리오 + learnings
- [ ] (F013 세션 3) lint.py LINT-MR-8 + CLAUDE.md 7 변형 + F014 placeholder + 최종 미러
- [ ] (F013 QA) `/project:orchestrate` smoke test (간단 요청 1 회) + `/project:lint
  --only=LINT-MR` 통과 + 핸드오프 디렉토리 생성 검증
- [ ] **(F014 가칭 — 후속 chore)** wiki.py ingest 멱등성 fix (`created` 보존 + `updated`
  별도) — wiki/orch 두 변형 동시 미러
- [ ] (F015 가칭 — 후속) d-2 로컬 LLM 어댑터 + researcher 의 부분 위임 (ADR-009 가칭)
- [ ] (F016 가칭 — 후속·어쩌면 영영 안 함) d-3 이종 호스트 분산 + host.py codex/openclaw
  실어댑터 + 호스트 간 메시지 규약 (ADR-010 가칭)
- [ ] (F017 가칭 — 후속) `--enrich-llm` 류 orchestrate 옵션 (sub-agent 산출물의 LLM 후
  처리 — researcher 노트의 다국어 번역 등)

---

## 구현 가이드 (Developer 인계용)

### 변경/신규 파일 목록

**신규 생성 (세션 1)**:

```
.claude/agents/researcher.md                                                # opus + WebSearch/WebFetch + 리서치 노트 형식
.claude/commands/orchestrate.md                                             # 커맨드 본문 골격 (supervisor 책임 + 인라인 주입 패턴)
.claude/state/orch/.gitkeep                                                 # 핸드오프 디렉토리 보존 마커
docs/adr/ADR-008-heterogeneous-agent-orchestration.md                       # 본 ADR
```

**수정 (세션 1)**:

```
.gitignore                                                                  # .claude/state/orch/* (gitkeep 제외) 추가
feature_list.json                                                           # F013 status: in-progress (그대로)
```

**신규 생성 (세션 2)**:

```
docs/orch-examples/01-ui-with-external-api.md                               # 시나리오 1
docs/orch-examples/02-simple-bugfix.md                                      # 시나리오 2 (라우팅 최소 단계 예시)
docs/orch-examples/03-refactor.md                                           # 시나리오 3
```

**수정 (세션 2)**:

```
.claude/commands/orchestrate.md                                             # 라우팅 매트릭스 + 순차/병렬 + 실패 루프 + plan-full 통합 흐름
.claude/state/learnings.jsonl                                               # 학습 1~2 개 append
```

**신규 생성 (세션 3)**:

```
(없음 — 모두 수정만)
```

**수정 (세션 3)**:

```
.claude/bin/lint.py                                                         # LINT-MR-8 추가 + MR-5/MR-6 변수 갱신
CLAUDE.md                                                                   # 빠른 시작 + 호출 기준 + 7 변형 매트릭스 + 8 에이전트
feature_list.json                                                           # F013 status: in-progress → review
.claude/state/learnings.jsonl                                               # 새 학습 2~3 개
claude-progress.txt                                                         # F014 가칭 chore placeholder 명시 (F012 멱등성 결함)
```

**미러링 (ⓑ + ⓑ′ + ⓑ″ + ⓑ‴ + ⓑ⁗ — 결정 7 의 선별 미러)**:

```
# ⓑ (claude.gstack) — 자율 + 디자인 + wiki + orch 오버레이 제외 (거버넌스만)
src/harness_template/claude.gstack/harness/.claude/bin/lint.py              # LINT-MR-8 추가
src/harness_template/claude.gstack/harness/CLAUDE.md                        # 7 변형 매트릭스
src/harness_template/claude.gstack/harness/docs/adr/ADR-008-*.md

# ⓑ′ (claude.gstack.auto) — 디자인 + wiki + orch 오버레이 제외 (자율 유지)
(상동)

# ⓑ″ (claude.gstack.auto.design) — wiki + orch 오버레이 제외 (디자인 유지)
(상동)

# ⓑ‴ (claude.gstack.auto.design.wiki) — orch 오버레이만 제외 (wiki 유지)
(상동)

# ⓑ⁗ (claude.gstack.auto.design.wiki.orch) — 모든 오버레이 포함 (자율 + 디자인 + wiki + orch)
src/harness_template/claude.gstack.auto.design.wiki.orch/harness/.claude/agents/researcher.md
src/harness_template/claude.gstack.auto.design.wiki.orch/harness/.claude/commands/orchestrate.md
src/harness_template/claude.gstack.auto.design.wiki.orch/harness/.claude/state/orch/.gitkeep
src/harness_template/claude.gstack.auto.design.wiki.orch/harness/docs/orch-examples/
(나머지 상동)
```

**의도적 미수정 (제약 준수)**:

```
.claude/settings.json                                                       # Claude Code 스키마 격리 (F006)
.claude/agents/{planner,architect,developer,reviewer,qa,gatekeeper,designer}.md  # 기존 7 에이전트 무수정
.claude/bin/{brain,host,backup,qa_browser,design_pick,wiki}.py              # F005/F006/F010/F008/F011/F012 격리
.claude/bin/wiki-setup.sh                                                   # F012 격리 — orch phase 에서 미수정 (결정 6)
.claude/hooks/*.sh                                                          # 무수정
.claude/commands/{init-project,handoff,start-session,plan-full,...}.md (F013 무관)  # 무수정
.claude/skills/*/SKILL.md                                                   # 무수정
docs/adr/ADR-001*.md ~ ADR-007*.md                                          # 기존 ADR 무수정
src/harness_template/claude/                                                # baseline 동결
src/harness_template/openai/                                                # codex stub
wiki/                                                                       # F012 vault 골격 무수정
```

### 인수 기준 매핑

| AC | 충족 단계 | 비고 |
|---|---|---|
| AC1 — `claude.gstack.auto.design.wiki.orch` 변형 신설 (wiki 변형 1:1 + orch 오버레이) | 사용자 사전 cp -r + 세션 1 (orch 오버레이) + 세션 3 (최종 미러 정합) | 결정 7 |
| AC2 — researcher 에이전트 신규 (brain-search + 웹 조사 + 출처 종합) | 세션 1 (researcher.md) | 결정 2 |
| AC3 — orchestrator 에이전트 또는 /project:orchestrate 커맨드 | 세션 1 (orchestrate.md 골격) + 세션 2 (라우팅 본체) | 결정 1 + 결정 4 |
| AC4 — 이종 에이전트 간 컨텍스트 전달 규약 | 세션 1 (핸드오프 디렉토리 + 리서치 노트 형식) + 세션 2 (인라인 주입 패턴) | 결정 3 |
| AC5 — 오케스트레이션 흐름 예시 (복합 요청 → R→D→Dev→Rev→QA 라우팅) | 세션 2 (docs/orch-examples/ 시나리오 3 개) | 결정 4 |
| AC6 — single-host 원칙 (같은 컨텍스트 풀, 이종 호스트 분산 X) | 세션 1 (orchestrate.md 본문 명시) + 세션 2 (시나리오에 반영) | 결정 5 |
| AC7 — LINT-MR 7 변형 확장 (orch 오버레이 격리) | 세션 3 (lint.py MR-8 + MR-5/MR-6 변수 갱신) | 결정 7 |
| AC8 — CLAUDE.md 7 변형 미러 매트릭스 + orchestrate 호출 기준 | 세션 3 (CLAUDE.md 갱신) | 결정 1 + 결정 5 |
| AC9 — ADR-008 (supervisor pattern, d-2/d-3 경계) | 본 문서 + 세션 1 미러 | 본 ADR (결정 5) |
| AC10 — wiki 변형 복사로 따라온 F012 멱등성 결함 처리 방침 | 세션 3 (claude-progress.txt + F014 placeholder) | 결정 6 |

### 피해야 할 패턴

- ❌ `.claude/settings.json` 수정 (F006 격리)
- ❌ `claude/` (baseline) 또는 `openai/.codex/` 에 orch 오버레이 미러 (결정 7 위배 —
  Karpathy 만)
- ❌ `claude.gstack/` / `claude.gstack.auto/` / `claude.gstack.auto.design/` /
  `claude.gstack.auto.design.wiki/` 에 researcher.md / orchestrate.md / `.claude/state/
  orch/` 미러 (결정 7 위배 — orch 변형 한정)
- ❌ orch 변형에서 wiki.py 의 멱등성 결함 fix (결정 6 — F014 후속 chore 분리)
- ❌ orchestrator.md 에이전트 신설 (결정 1 — 커맨드만, supervisor 는 메인 컨텍스트 직접)
- ❌ /project:plan-full 확장으로 orchestrate 흡수 (결정 1 — 의미론 분리)
- ❌ researcher 도구에 Write 추가 (결정 2 — 메인 통제 유지, 핸드오프 디렉토리 저장은
  orchestrate 본문 책임)
- ❌ researcher 모델 sonnet 선택 (결정 2 — opus 일관)
- ❌ 인라인 전달만 (디스크 미저장) (결정 3 — 디버그·QA 검증 가능성 손실)
- ❌ 풀 파이프라인 강제 (결정 4 — 조건부 라우팅 정신 위배)
- ❌ 이종 호스트 분산 옵션 본 phase 도입 (결정 5 — d-3 후속)
- ❌ 로컬 LLM 통합 본 phase 도입 (결정 5 — d-2 후속)
- ❌ 1 phase 안에 orch + 멱등성 fix 동시 진행 (결정 6 — Surgical Changes 위배)
- ❌ `.claude/state/orch/` 를 git 추적 (결정 3 — gitignore, .gitkeep 만 보존)
- ❌ 같은 task-id 로 동시 실행 (결정 3 — timestamp + slug 로 고유성 보장, 충돌 시 suffix)
- ❌ sub-agent 가 또 다른 sub-agent 를 spawn (결정 1 — supervisor 는 메인 직접, 재귀 회피)
- ❌ F013 작업 중 `feature_list.json` 의 `passes` 필드 수정 (QA 단독 권한)
- ❌ host.py 의 codex/openclaw 어댑터 실어댑터로 전환 (결정 5 — d-3 후속, 본 phase 외)
- ❌ researcher 의 외부 의존성 (qmd / Obsidian / Marp 외 도구) 추가 (결정 5 + F012 정책)
- ❌ orch phase 산출물을 baseline `claude/` 미러 (Karpathy 4원칙만)

---

## 부록 A — d-1/d-2/d-3 경계 매트릭스 (단일 소스)

| 단계 | 범위 | 호스트 | 컨텍스트 풀 | GPU | 책임 ADR | 상태 |
|---|---|---|---|:---:|---|---|
| **d-1** | single-host supervisor + sub-agent 오케스트레이션 | Claude Code 만 | 같은 풀 (메인 + sub-agent Task) | ❌ | **ADR-008 (본)** | **Proposed → 본 phase 완료 시 Accepted** |
| d-2 | 로컬 small LLM 통합 (researcher 일부 단계 로컬 위임) | Claude Code + 로컬 LLM | 부분 분리 (로컬 출력만 hand-off) | ✅ | ADR-009 가칭 | 미작성 (후속 phase) |
| d-3 | 이종 호스트 분산 (Claude Code + Codex + OpenClaw 다른 모델로 라우팅) | 다중 (host.py 실어댑터) | 풀 분리 (호스트 간 메시지) | (선택) | ADR-010 가칭 | 미작성 (먼 미래·어쩌면 불필요) |

→ 본 ADR 은 d-1 한정. d-2/d-3 도입 시 본 ADR 의 결정들 (특히 결정 3 핸드오프 규약 + 결정
5 single-host 원칙) 이 재검토 대상 — 단 d-1 산출물을 그대로 폐기하지 않고 확장하는 패턴
권장.

---

## 부록 B — 7 변형 매트릭스 산출물 분포표 (Developer / QA 참고)

| 산출물 | ⓐ `claude/` | ⓑ `claude.gstack/` | ⓑ′ `claude.gstack.auto/` | ⓑ″ `claude.gstack.auto.design/` | ⓑ‴ `claude.gstack.auto.design.wiki/` | **ⓑ⁗ `claude.gstack.auto.design.wiki.orch/`** | ⓒ `openai/.codex/` |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| `.claude/agents/{planner,architect,developer,reviewer,qa}.md` | ❌ | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ |
| `.claude/agents/gatekeeper.md` | ❌ | ❌ | ✅ | ✅ | ✅ | ✅ | ❌ |
| `.claude/agents/designer.md` (F011) | ❌ | ❌ | ❌ | ✅ | ✅ | ✅ | ❌ |
| **`.claude/agents/researcher.md` (F013)** | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ | ❌ |
| `.claude/commands/{handoff,start-session,...}.md` (공통) | ❌ | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ |
| `.claude/commands/design-pick.md` (F011) | ❌ | ❌ | ❌ | ✅ | ✅ | ✅ | ❌ |
| `.claude/commands/wiki.md` (F012) | ❌ | ❌ | ❌ | ❌ | ✅ | ✅ | ❌ |
| **`.claude/commands/orchestrate.md` (F013)** | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ | ❌ |
| `.claude/commands/design-review.md` (F007) | ❌ | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ |
| `.claude/bin/{brain,host,lint,backup,qa_browser}.py` | ❌ | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ |
| `.claude/bin/design_pick.py` (F011) | ❌ | ❌ | ❌ | ✅ | ✅ | ✅ | ❌ |
| `.claude/bin/wiki.py` (F012) | ❌ | ❌ | ❌ | ❌ | ✅ | ✅ | ❌ |
| `.claude/bin/wiki-setup.sh` (F012) | ❌ | ❌ | ❌ | ❌ | ✅ | ✅ | ❌ |
| **`.claude/state/orch/.gitkeep` (F013)** | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ | ❌ |
| **`docs/orch-examples/*.md` (F013)** | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ | ❌ |
| `wiki/` (vault, F012) | ❌ | ❌ | ❌ | ❌ | ✅ | ✅ | ❌ |
| `docs/adr/ADR-006-*.md` (F011) | ❌ | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ |
| `docs/adr/ADR-007-*.md` (F012) | ❌ | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ |
| **`docs/adr/ADR-008-*.md` (F013)** | ❌ | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ |
| 외부 의존성 (Obsidian/qmd/Marp) | ❌ | ❌ | ❌ | ❌ | ✅ (허용) | ✅ (wiki 상속) | ❌ |
| **외부 의존성 (WebSearch/WebFetch)** | ❌ | ❌ | ❌ | ❌ | ❌ | **✅ (researcher 도구 — Claude Code 빌트인)** | ❌ |
| Karpathy 4원칙 (think/simplicity/surgical/goal) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |

→ orch 오버레이는 **ⓑ⁗ 에만 존재**. researcher 에이전트 + orchestrate 커맨드 + 핸드오프
디렉토리 + 시나리오 예시 4 종이 핵심. wiki 오버레이는 ⓑ‴ + ⓑ⁗ 둘 다 (orch 는 wiki 의 1:1
복사). ADR-008 본체는 ⓑ + ⓑ′ + ⓑ″ + ⓑ‴ + ⓑ⁗ 5 변형에 미러 (거버넌스 — Karpathy 4원칙·
F006 single-host 격리·F012 외부 의존성 정책과 같은 의미).

---

## 부록 C — orchestrate 라이프사이클 (Developer / QA / 사람 흐름)

| 단계 | 도구/에이전트 | 책임 | 호출 빈도 |
|---|---|---|---|
| **요청 수신** | 사용자 → `/project:orchestrate <요구사항>` 또는 `--feature=F0XX` | 자연어 요구사항 또는 기존 feature 입력 | 복합 요청 시 |
| **task-id 발급** | orchestrate 본문 (메인 컨텍스트) | timestamp + slug → `.claude/state/orch/<task-id>/` 디렉토리 신설 | 자동 |
| **라우팅 판정** | orchestrate 본문 | 요구사항 분석 → 필요 단계 결정 (researcher / designer / architect / developer / reviewer / qa / design-review / qa-browser) → plan.md 저장 | 자동 |
| **조사** (선택) | researcher 에이전트 (opus + WebSearch/WebFetch) | brain-search + 웹 조사 + 출처 종합 → research.md 산출 (마크다운, 출처 인용) | 신규 도메인 시 |
| **설계** (선택) | architect 에이전트 | research.md 발췌 입력 → ADR 작성 → adr.md 저장 | 결정 4 라우팅 규칙 충족 시 |
| **디자인** (선택) | designer 에이전트 (opus) | research.md + USE_CASE 입력 → 4 브랜드 비교 + 추천 + tokens 시안 → design.md 저장 | UI 변경 시 |
| **구현** | developer 에이전트 | research.md + design.md + adr.md 발췌 입력 → 코드 변경 + 단위 테스트 → impl.md (요약) | 거의 모든 요청 |
| **리뷰** | reviewer 에이전트 | 코드 검토 (보안·성능·품질) → review.md → APPROVED / NEEDS REVISION | 거의 모든 요청 |
| **재작업 루프** (조건부) | developer (재호출) | NEEDS REVISION 시 최대 2 회 재시도, 그래도 실패 시 architect 재호출 | 실패 시만 |
| **디자인 감사** (조건부) | `/project:design-review` (커맨드) | reviewer 통과 후 IA/A11Y/TOKEN 검사 | UI 변경 시 |
| **QA** | qa 에이전트 + 필요 시 `/project:qa-browser` | acceptance_criteria 검증 + 동작 검증 → qa.md | passes=true 직전 |
| **통합 리포트** | orchestrate 본문 | 모든 단계 산출물 종합 → final.md → 사용자 출력 | 자동 (종료 시) |
| **셀프 점검** (선택) | 사용자 → `/project:lint --only=LINT-MR` | 7 변형 미러 정합 + 외부 의존성 격리 + orch 오버레이 격리 확인 | handoff 직전 |
| **핸드오프 보관** (선택) | 사용자 수동 cp | `.claude/state/orch/<task-id>/` → `docs/orch-archive/` 영구 보관 | 중요 task 한정 |

이 13 단계가 orchestrate 라이프사이클을 단일 SSoT 흐름으로 보장. 매 호출은 task-id 분리로
독립 실행 가능.

---

## 부록 D — orch 변형 사용자 안내 메시지 (CLAUDE.md 빠른 시작 + 호출 기준 단일 소스)

CLAUDE.md 갱신 분량 (세션 3):

```markdown
### 이종 에이전트 오케스트레이션 (Phase 9 — F013)

> 사용 가능 변형: **claude.gstack.auto.design.wiki.orch/** 만.
> single-host (Claude Code 안) — 이종 호스트 분산은 d-3 후속, 본 phase 범위 외.

/project:orchestrate <요구사항>                  # 자연어 요구사항 → 자동 라우팅
/project:orchestrate --feature=F0XX              # 기존 feature 실행 (plan-full 후 연계)
/project:orchestrate --steps=research,design,dev # 사용자 명시 단계 (override)

> 핸드오프 디렉토리: .claude/state/orch/<task-id>/ (gitignore, .gitkeep 만 보존)
> 통합 리포트: final.md (커맨드 종료 시 stdout + 디스크 저장)

### orchestrate 호출 기준

다음 중 하나라도 해당되면 `/project:orchestrate` 실행 권장:
- 복합 요청 (코딩+디자인+리서치가 동시에 필요)
- 신규 도메인 / 모르는 외부 API / 학술 배경 필요한 변경
- UI 컴포넌트 + 새 디자인 시스템 토큰 동시 변경
- plan-full 로 분해된 복잡 Feature 의 실행 라우팅

해당 없으면 (예: 단순 버그 수정, typo) 직접 Developer 호출이 효율적.
**orchestrate 는 옵셔널** — 호출 안 해도 하네스 동작에 영향 없음.

### 8 에이전트 역할 분담 (F013 완료 후)

| 에이전트 | 트리거 | 주요 책임 | 변형 |
|---|---|---|---|
| planner | 프로젝트 초기, 기능 추가 | 요구사항 분석, feature_list 관리 | ⓑ+ |
| architect | 설계 필요 시 | ADR 작성, 기술 선택 | ⓑ+ |
| developer | 실제 구현 | 코드 작성, 단위 테스트 | ⓑ+ |
| reviewer | 구현 완료 후 | 코드 품질·보안·성능 | ⓑ+ |
| qa | 리뷰 통과 후 | acceptance_criteria 검증 | ⓑ+ |
| gatekeeper | 자율 모드 경계 결정 | PROCEED/CONSULT/ESCALATE | ⓑ′+ |
| designer | 디자인 시스템 결정 | 4 브랜드 비교, tokens 시안 | ⓑ″+ |
| **researcher** | **신규 도메인/외부 자료 조사** | **brain-search + 웹 조사 + 출처 종합** | **ⓑ⁗ 만** |

### 7 변형 매트릭스 (F013 완료 후)

| 변형 | F005~F012 | 자율 | 디자인 | wiki | **orch** | 외부 의존성 | 미러 정책 |
|---|---|---|---|---|---|---|---|
| ⓐ `claude/` | ❌ | ❌ | ❌ | ❌ | ❌ | 0 | Karpathy 만 |
| ⓑ `claude.gstack/` | ✅ | ❌ | ❌ | ❌ | ❌ | 0 | 표준 SSoT |
| ⓑ′ `claude.gstack.auto/` | ✅ | ✅ | ❌ | ❌ | ❌ | 0 | 자율 |
| ⓑ″ `claude.gstack.auto.design/` | ✅ | ✅ | ✅ | ❌ | ❌ | 0 | 자율+디자인 |
| ⓑ‴ `claude.gstack.auto.design.wiki/` | ✅ | ✅ | ✅ | ✅ | ❌ | 허용 (Obsidian/qmd/Marp) | 자율+디자인+wiki |
| **ⓑ⁗ `claude.gstack.auto.design.wiki.orch/`** | ✅ | ✅ | ✅ | ✅ | ✅ | 허용 (wiki 상속 + WebSearch/WebFetch) | 자율+디자인+wiki+orch |
| ⓒ `openai/.codex/` | ❌ | ❌ | ❌ | ❌ | ❌ | 0 | Karpathy 만 (stub) |

> 미러 회귀 + 외부 의존성 격리 + orch 격리 자동 감지: `/project:lint --only=LINT-MR` (F013)
```

---

*작성: architect 에이전트 | 날짜: 2026-06-05 | 상태: Proposed*
