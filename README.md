# harness_template — 변형(variant) 가이드

이 디렉토리는 다운스트림 프로젝트에 배포할 **Claude Code 하네스 템플릿**의 변형 모음입니다.
각 변형은 `<변형명>/harness/` 아래에 `.claude/`, `CLAUDE.md`, `docs/` 산출물을 담고 있습니다.

변형은 **누적식(cumulative overlay)** 으로 설계됐습니다 — 뒤로 갈수록 앞 변형에
오버레이를 하나씩 더합니다. 필요한 기능 수준만큼만 가져가세요.

```
claude (baseline, 동결)
  └─ claude.gstack (표준 — 승인 프롬프트 유지)
       └─ +auto (자율 모드)
            └─ +design (디자인 시스템)
                 └─ +wiki (지식 그래프, 외부 의존성 허용)
                      └─ +orch (이종 에이전트 오케스트레이션, d-1)
                           └─ claude.hermes (영속기억·자가진화)
                                └─ claude.productmgr (PM 주도 통합 SDLC)
                                     ├─ claude.productnw (분산 멀티팀 컨소시엄, d-3)
                                     └─ claude.loope ★ (검증 루프 — 메인과 1:1, SSOT)
                                          ├─ claude.vela.v0.1 🚀 (배포 단위 + Atlassian 연동)
                                          ├─ claude.aif (항목형 판정 — RLAIF/CAI 규율)
                                          └─ localllm (OpenCode + 로컬 LLM, d-2)
                                               ├─ localllm.aif (d-2 + 항목형 판정)
                                               └─ localllm.nem (d-2 + nemotron — 모델 축)
openai (.codex) — codex 호스트 정적 변형 (별도 계보)
```

> **★ SSOT 는 `claude.loope` 입니다** (F021 / ADR-015). 메인 하네스
> (`harness_update_agent/.claude/`)와 1:1 정합이며, 신규 개발은 **메인 → loope → 하위 변형**
> 순으로 미러됩니다. 구 SSOT(`main ≡ gstack.auto`)는 폐기됐습니다.

**축이 셋입니다** — 세 축을 구별하면 계보가 읽힙니다:

| 축 | 무엇이 달라지는가 | 예 |
|---|---|---|
| **기능 축** | 오버레이 누적 | baseline → gstack → auto → … → loope |
| **호스트 축** | 하네스를 구동하는 프로그램 | `localllm` (Claude Code → OpenCode + Ollama) |
| **모델 축** | 모델만 교체 (오버레이 동일) | `localllm.nem` (qwen2.5 → nemotron) |
| **배포 축** | 릴리스 스냅샷 — 다운스트림에 건네는 단위 | `claude.vela.v0.1` |

---

## 빠른 선택 가이드

| 이런 상황이면 | 추천 변형 |
|---|---|
| 하네스가 처음 / 최소 구성으로 시작 | `claude.gstack` |
| bash 승인 프롬프트 없이 자율 진행시키고 싶다 | `claude.gstack.auto` |
| UI 작업이 있어 디자인 토큰·감사가 필요하다 | `claude.gstack.auto.design` |
| 프로젝트 지식을 그래프(Obsidian/wikilink)로 관리하고 싶다 | `claude.gstack.auto.design.wiki` |
| 리서치+디자인+코딩을 한 흐름으로 지휘하고 싶다 | `claude.gstack.auto.design.wiki.orch` |
| 세션 기억 검색 + 스킬 자동생성/self-improve 가 필요하다 | `claude.hermes` |
| 제품 기획부터 배포까지 PM 주도로 통합 진행 | `claude.productmgr` |
| 여러 팀이 한 제품을 분담해 만든다 (팀 간 메시지 계약) | `claude.productnw` (d-3) |
| **전 기능 + 검증 루프를 명시·유계로 쓰고 싶다 (권장 기본)** | **`claude.loope`** ★ |
| **팀이 Jira·Confluence 로 일한다 — 배포 단위로 받고 싶다** | **`claude.vela.v0.1`** 🚀 |
| 판정(reviewer/qa)의 재현성이 낮아 채점을 정밀화하고 싶다 | `claude.aif` |
| 로컬 LLM(OpenCode+Ollama)으로 비용 0·오프라인 추론 | `localllm` (d-2) |
| 로컬 LLM + 항목형 판정을 **수치로 A/B** 하고 싶다 | `localllm.aif` |
| 로컬 LLM 을 nemotron 계열로 돌려 보고 싶다 | `localllm.nem` |
| OpenAI Codex 호스트에서 쓴다 | `openai/.codex` (stub) |
| Phase 0 원본 스냅샷이 필요하다 (참고용) | `claude` (baseline, 동결) |

> **외부 의존성 0** 이 필요하면 `wiki` 이전 변형까지(`claude` ~ `auto.design`)를 쓰세요.
> `wiki` 이후 변형은 외부 도구(Obsidian/qmd/Marp, OpenCode/Ollama)를 **선택적으로** 허용합니다.

---

## 변형별 상세

### ⓐ `claude/` — baseline (동결)
- **무엇**: Phase 0 (F001 시작 전) 스냅샷. 하네스의 최소 원형.
- **포함**: 기본 에이전트(planner/architect/developer/reviewer/qa), 기본 커맨드, 기본 훅, 코딩/git 규칙.
- **정책**: **수정 금지(동결)**. 신규 phase 산출물은 반영하지 않음. 단 Karpathy 4원칙 같은
  phase-agnostic 보편 디시플린만 예외적으로 동기화.
- **언제**: 하네스가 어떻게 시작했는지 참고하거나, 가장 가벼운 베이스가 필요할 때.
- **외부 의존성**: 0

### ⓑ `claude.gstack/` — 표준 (승인 프롬프트 유지)
- **무엇**: 기능 산출물의 정합 사본에서 **autonomous 오버레이만 제외**한 표준 버전.
- **포함**: Safety Guards/Learn/Context(F001), Autoplan·Ship·Retro(F002~4), Brain(F005),
  멀티호스트(F006), Design-Review(F007), QA-Browser(F008), Lint(F009), Backup-Sync(F010) 등 —
  **승인 프롬프트는 표준 동작**(작업 디렉토리 액션도 사용자 확인).
- **제외(autonomous 오버레이 4 파일)**: `gatekeeper.md`, `pre-bash-auto-boundary-check.sh`,
  `settings.json` 의 `Bash(*)` 권한, `CLAUDE.md` 의 "Autonomous Mode" 섹션.
- **언제**: 표준적이고 안전한(매 단계 확인) 하네스를 원할 때.
- **외부 의존성**: 0

### ⓑ′ `claude.gstack.auto/` — 자율 모드 (+auto)
- **추가 오버레이**: **Autonomous Mode**.
  - 규칙 #1: 작업 디렉토리 내부는 **승인 없이 자율 진행** (`Bash(*)`/`Edit(*)`/`Write(*)`).
  - 규칙 #2: 모호하면 **Gatekeeper 에이전트**가 PROCEED/CONSULT/ESCALATE 판정.
  - 규칙 #3: **삭제**(`rm`/`git clean`/`find … -delete` 등)와 **PR 생성·병합**만 사용자 승인.
    `rm -rf /`·`~`·`$HOME` 류는 `deny` 로 완전 차단. (2026-08-16 축소 — 이전에는 계정·인증·
    외부 디렉토리·`git push` 도 승인 대상이었으나, 장시간 자율 작업이 끊기는 비용이 더 컸다.)
  - 안전망: `permissions.ask`(선언) + `pre-bash-auto-boundary-check.sh`(패턴) + gatekeeper(컨텍스트).
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
- **추가 오버레이**: **오케스트레이션** (F013, ADR-008).
  - `researcher.md` 에이전트, `/project:orchestrate` 커맨드, `.claude/state/orch/` 핸드오프,
    `docs/orch-examples/`.
  - **single-host d-1**: 모든 sub-agent 를 Claude Code Agent 도구로 spawn(같은 컨텍스트 풀 공유).
    리서치(researcher)→디자인(designer)→코딩(developer) 삼각형 + reviewer/qa supervisor.
  - supervisor 로직은 메인 컨텍스트가 직접 수행(별도 orchestrator 에이전트 없음, plan-full 패턴).
- **언제**: 리서치+디자인+코딩이 함께 필요한 **복합 요청**, 신규 기능 end-to-end, 모르는 외부 API 도입.
  단일 역할이면 해당 에이전트 직접 호출.
- **plan-full 과 관계**: plan-full=설계 체인(Feature+ADR 생성), orchestrate=실행 라우팅. 보완 관계.
- **외부 의존성**: 허용 (wiki 상속). orch 자체는 stdlib only.

### ⓑ⁵ `claude.hermes/` — 영속 기억 + 자가 진화 (Hermes Agent 패턴 이식)
- **무엇**: orch 변형 복사본 + **hermes 오버레이** (F016, ADR-010). NousResearch/hermes-agent
  ("the agent that grows with you") 의 3가지를 SDLC 하네스에 이식.
- **추가 오버레이**:
  - `session_search.py` — **FTS5 세션 검색**: claude-progress.txt + 체크포인트를 SQLite FTS5 로
    색인/검색 (cross-session recall). `/project:session-search`.
  - `skill_forge.py` — **스킬 자동생성/self-improve + agentskills.io 검증**: 스킬 scaffold,
    사용 추적(`record-use`)→개선 후보 `nudge`, 표준 적합성 `validate`. `/project:skill-forge`.
- **설계**: 헬퍼는 **결정론 부분**(구조·메타데이터·검증·사용추적)만, 스킬 **본문은 에이전트**가 작성
  (Karpathy 추측 자동화 금지). hermes 3종 기능은 **stdlib only**.
- **미이식**(의도): Hermes 의 메시징 게이트웨이/유저모델링 등 — 개인비서 영역, SDLC 목적과 불일치.
- **언제**: "예전에 어떻게 했더라" 과거 세션 회상 / 반복 절차를 재사용 스킬로 승격·관리.
- **외부 의존성**: wiki 상속분(Obsidian/qmd/Marp) 허용, hermes 기능 자체는 0.

### ⓑ⁶ `claude.productmgr/` — Product Manager 주도 통합 SDLC
- **무엇**: hermes 변형 복사 + **pm 오버레이** (F018, ADR-011). PM 이 사용자와 협력해 제품을
  기획부터 배포까지 한 흐름으로 조율하는 통합 에이전트.
- **추가 오버레이**:
  - `product-manager.md` — 제품 발견·요구·우선순위·**성공지표**·로드맵 정의 + 라이프사이클 supervisor.
    PM=why·what(제품 brief) / planner=feature 분해(how-much). PM 은 passes·코드 직접수정 안 함(조율자).
  - `/project:product-cycle` — **기획→설계→개발→검증→배포** 5단계 PM 주도 통합 흐름.
    `--from`/`--to` 로 중간 진입·조기 종료 가능.
  - `.claude/state/product-cycle/` 사이클 핸드오프 디렉토리.
- **배포 정의**: 하네스 게이트(`lint --strict` → `/project:ship` → `backup.py sync`). 실제 prod CI/CD 는 다운스트림.
- **언제**: 아이디어→출시를 한 흐름으로, 제품 관점(사용자·가치·성공지표)이 중요한 신규 기능.
- **외부 의존성**: hermes 상속분 허용, pm 오버레이는 stdlib/문서뿐.

### ⓑ⁷ `claude.productnw/` — 분산 멀티팀 컨소시엄 (d-3)
- **무엇**: productmgr 변형 복사 + **nw(컨소시엄) 오버레이** (F019, ADR-012). 여러 팀이 각자
  멀티 에이전트 하네스를 두고 **팀 간 메시지 계약**으로 통신하며 통합 제품을 만드는 분산 구성.
- **추가 오버레이**:
  - `consortium.py` — ① 메시지 계약(JSON: from/to-team·role·cycle-id) ② 로스터(팀·에이전트 등록)
    ③ 로컬 큐(inbox/outbox). **stdlib 로 실재 동작**.
  - `/project:consortium` 커맨드, `.claude/state/consortium/`(roster.json + 큐).
- **정직한 범위**: 프로토콜·로스터·로컬 큐는 **동작**하고, Teams/Slack/Telegram 게이트웨이는
  **stub** 입니다 — 실제 봇 transport·자격증명은 다운스트림 책임 (codex/openclaw stub 와 같은 패턴).
  팀 **내부**는 single-host(d-1), 팀 **사이**만 계약으로 연결됩니다.
- **언제**: 단계별로 다른 팀이 담당하는 멀티팀 product-cycle. 한 팀 내부 통합 흐름이면 `productmgr`.
- **외부 의존성**: productmgr 상속분 허용, nw 오버레이는 stdlib/문서뿐.

### ⓑ⁸ `claude.loope/` ★ — 검증 루프 (Loop 2 + Loop 4) · **메인과 1:1 SSOT**
- **무엇**: productmgr 변형 복사 + **loop 오버레이** (F020, ADR-014). LangChain 의
  "loop engineering"(the art of stacking loops)에서 **Loop 2(검증 루프)** 와
  **Loop 4(hill-climbing)** 의 *규율만* 하네스에 이식했습니다.
- **왜**: 기존 하네스의 Reviewer→NEEDS REVISION→재시도 흐름은 **rubric 이 암묵적**이고
  **재시도 상태가 코드화되지 않았습니다**. 같은 산출물이 라운드마다 다르게 판정되고,
  몇 번 왕복했는지 아무도 세지 않았습니다.
- **추가 오버레이**:
  - `verify_loop.py` — 판정을 **상태로 기록**(`record … --verdict pass|revision|fail`),
    재시도 유계화, **revision 3회 자동 에스컬레이션**(산문 규칙의 코드화).
  - `.claude/rubrics/{code-review,qa-acceptance}.md` — **명시 rubric**.
  - `/project:verify-loop`, `/project:hill-climb`, `.claude/state/verify-loop/`.
- **핵심 구분**: **grader(결정론)** vs **judge(모델)**.
  lint·design-review·qa-browser·테스트는 stdlib 스크립트라 **모델 무관 100% 신뢰**이고,
  판정(reviewer/qa)만 모델 몫입니다. *결정론으로 판정할 수 있는 것은 모델에게 묻지 않습니다.*
- **라이브러리 미채택**: LangChain/LangGraph 는 zero-dep 정책·실행 모델(호스트가 루프를 소유)·
  LangSmith(SaaS) 이유로 부적합 → **규율만** 가져왔습니다.
- **미러 지위**: **메인 하네스와 1:1 정합(SSOT — F021/ADR-015)**. 로컬 파일
  (`settings.json`/`settings.local.json`/`host.json`/`.claude/state/`)만 제외합니다.
  신규 개발은 메인 → loope → 하위 변형 순으로 미러됩니다.
- **언제**: **전 스택을 쓰면서 검증을 명시·유계로 돌리고 싶을 때 — 사실상 권장 기본값**입니다.
- **외부 의존성**: productmgr 상속분 허용, loop 오버레이는 stdlib/문서뿐.

### ⓑ⁹ `claude.vela.v0.1/` 🚀 — 배포 단위 + Atlassian 연동
- **무엇**: `claude.loope` 1:1 복사 + **Atlassian 오버레이** (F032, ADR-023).
  **배포 단위**로 건네는 릴리스 스냅샷입니다.
- **이름 규약**: 앞으로 배포 단위 변형은 **`claude.vela.v<major>.<minor>`** 로 명명합니다.
  기능 서술 이름(`claude.gstack.auto.design.wiki.orch`)과 축 접미사(`.aif`·`.nem`)는
  **개명하지 않습니다** — ADR·측정 문서의 참조가 전부 깨집니다.
- **SSOT 관계**: v0.1 에서 SSOT 는 **여전히 `claude.loope`** 이고 vela 는 그 위의 스냅샷입니다.
  장기 관계(매 릴리스 복사 vs SSOT 이관)는 v0.2 착수 시 재검토합니다.
- **추가 오버레이** (Atlassian):
  - `atlassian_map.py` — 하네스 산출물 ↔ Atlassian 객체 매핑. **API 래퍼가 아닙니다.**
  - `.claude/skills/atlassian/SKILL.md` — 방향 규약·번역 규칙
  - `/project:atlassian` — `check` / `import` / `pending` / `publish` / `comment`
- **핵심 설계 — 만들지 않은 것이 요점입니다**:
  Atlassian **공식 MCP 커넥터**가 41개 도구를 이미 제공하므로 자체 MCP 도, API 래퍼도
  만들지 않습니다. MCP 도구는 **에이전트가 직접** 부릅니다. 코드가 필요한 곳은 하나뿐 —
  **"이걸 이미 발행했는가"** 입니다. 모델에게 그 기억을 맡기면 중복 페이지·중복 이슈가
  생기고 되돌리기 어렵습니다. `atlassian_map.py` 가 digest 비교로 종료 코드를 냅니다
  (`0` 최신 / `2` 신규 / `3` 갱신). **판단은 모델이, 멱등성은 코드가** — loope 의
  grader/judge 분리를 발행 경로에 적용한 것입니다.
- **방향 규약**: **우리 리포가 SSOT**, Atlassian 은 발행 대상입니다.
  Atlassian 에서 편집한 내용을 리포로 **역반영하지 않습니다** — 두 SSOT 는 반드시 어긋납니다.
- **승인 층위**: 발행은 외부 공개이고 팀에 알림이 갑니다. **PR 과 같은 층위**로 다루며
  자동 발행하지 않습니다 (handoff·lint 가 부르지 않음).
- **검증 범위 (정직하게)**: 커넥터 실측(사이트·권한·Jira 81 프로젝트)과 매핑 왕복 시험은
  완료했습니다. **실제 발행(Confluence 페이지·Jira 코멘트)은 미검증**입니다.
- **언제**: 팀이 Jira·Confluence 로 일하고, 하네스를 배포 단위로 받고 싶을 때.
- **외부 의존성**: loope 상속분 + **Atlassian 공식 MCP 커넥터** (선택적 — 미연결 시 안내만
  하고 하네스는 정상 동작). 사용자별 인증이라 다운스트림은 각자 연결해야 합니다.
  `localllm` 계열(OpenCode 호스트)에는 이 커넥터가 없습니다.

### ⓑ¹⁰ `claude.aif/` — 항목형 판정 (RLAIF/CAI 규율)
- **무엇**: loope 1:1 복사 + **aif 오버레이** (F028, ADR-020). RLAIF·Constitutional AI·
  Rubrics-as-Rewards 문헌의 **판정 설계 규율**을 judge 에 이식했습니다.
- **왜**: 측정 09 의 결론이 **"판정 분산이 개선 신호를 덮는다"** 였습니다 — 같은 취지의 정책이
  4/4 와 1/4 로 갈리고, 챔피언 정책과 **빈 정책**이 3/6 대 3/6 동률이었습니다.
- **추가 오버레이**:
  - `aif_judge.py` — judge 에게 종합 판단이 아니라 **항목별 met/unmet/na + 증거**를 요구.
    `met` 인데 `파일:행`이나 인용이 없으면 그 항목은 **무효(UNCERTAIN)**.
    N회 판정을 **앙상블 집계**하고, 표가 갈리면 억지로 정하지 않고 **에스컬레이션**합니다.
  - `.claude/rubrics/{_items-schema,code-review.items,qa-acceptance.items}.md` (RaR 형식 채점표),
    `/project:aif-judge`, `.claude/state/aif/`.
- **설계 원칙**: **판정은 모델이, 집계는 결정론이.** `aif_judge.py` 는 모델을 호출하지 않습니다
  (`auto` 모드만 예외 — cycle_driver 보유 변형에서만).
- **검증 범위**: `claude.aif` 는 적합도 함수(무인 스위트)가 없어 **구조 이식까지**입니다.
  수치 A/B 는 `localllm.aif` 에서만 가능합니다 (ADR-019 결정 5 와 같은 비대칭).
- **언제**: 판정 재현성이 낮을 때 / 판정자가 약한 모델일 때 / 통과 여부가 중요한 게이트일 때.
  판정 호출이 N배로 늘어나므로 그 외에는 산문형 rubric + verify-loop 로 충분합니다.
- **외부 의존성**: loope 상속분 허용, aif 오버레이는 stdlib/문서뿐.

### ⓑ¹¹ `localllm/` — OpenCode + 로컬 LLM (호스트 축, d-2)
- **무엇**: **loope 계보** 복사 + **d-2 오버레이** (F015 신설 → F023 승격, ADR-009/017).
  Claude Code 가 아니라 **OpenCode(오픈소스 agent framework) + 로컬 LLM(Ollama)** 으로
  하네스를 구동합니다. **호스트 축**의 변형입니다.
- **추가 오버레이**:
  - `opencode.py` 호스트 어댑터 — `.claude/agents/*.md` → `.opencode/agent/*.md`
    (`mode: all` + permission **deny-list 역변환**), `.claude/commands/*.md` → `.opencode/commands/*.md`.
    `host.py render-agents` / `render-commands` 로 실행.
  - `cycle_driver.py` — **결정론 supervisor**: 무인 SDLC 사이클 드라이버 (F025, ADR-018).
    모델 보고를 믿지 않고 **파일시스템·테스트로 검증**합니다.
  - `autoresearch.py` — **자가 실험 루프**: 무인 스위트를 적합도 함수로 (F027, ADR-019).
    게이트·oracle·시나리오는 해시로 불변 강제, **자동 채택은 실험 원장까지 — 하네스 반영은
    `promote --yes`(사람 승인)로만**.
  - `.opencode/AGENTS.md`, `opencode-setup.sh`, `.claude/policy/`(역할 지시 — 사람 승인분만),
    `docs/poc/`(측정 01~09 · 11 + SUMMARY + MODEL-GRADES — 측정 10 은 aif 전용).
  - `host.json` agent_type=**opencode**.
- **F023 loope 계보 승격**: hermes(session_search/skill_forge) + pm(product-cycle) +
  loop(verify_loop/hill_climb) 오버레이를 모두 보유합니다 — 전부 stdlib.
- **Loop 2 × 로컬 LLM 시너지**: verify-loop 의 **결정론 grader 우선** 원칙이 로컬 LLM 의
  검증 약점을 구조적으로 보완합니다 — 게이트는 모델 무관이고, judge 만 상위 모델이 필요합니다.
- **모델 등급**: 단일역할은 로컬 **14B**(qwen2.5)로 가능, 다중파일·판정은 **32B+** 권장
  (`docs/poc/MODEL-GRADES.md`).
- **언제**: API 비용 0 · 오프라인 내부망 추론이 목적일 때.
- **외부 의존성**: 허용 (OpenCode/Ollama) — 어댑터·헬퍼 자체는 stdlib only.

### ⓑ¹² `localllm.aif/` — d-2 + 항목형 판정
- **무엇**: `localllm` 1:1 복사 + aif 오버레이 (F028).
- **왜 별도 변형인가**: **수치 A/B 가 가능한 유일한 aif 변형**입니다. 무인 스위트(적합도 함수)와
  `cycle_driver`(무인 드라이버)를 함께 갖췄고, 로컬 GPU라 실험당 추가 과금이 0 입니다.
- **추가분**: `cycle_driver` 의 `_aif_findings` — 항목형 앙상블 결과를 judge 입력에 주입.
  `tests/judge_variance.py` + `docs/poc/measurements/10-aif-judgment.md`(실측).
- **실측 요약** (측정 10, 로컬 32B): 형식 준수 50%→**100%**,
  오탐 케이스(`clean`, ground truth=pass) 정답률 16%→**66%**.
  미탐 케이스(`no_docstring`)는 양쪽 6/6 동률.
  단 **스위트 통과율은 3/6 대 3/6 동률**이고 완주 비용은 **2.4배**(334s 대 142s)입니다 —
  **판정 품질 향상이 곧 완주율 상승은 아닙니다.**
- **외부 의존성**: localllm 상속분 + OpenCode/Ollama.

### ⓑ¹³ `localllm.nem/` — d-2 + nemotron (모델 축)
- **무엇**: `localllm` 1:1 복사 + **모델 축만 교체** (F030, ADR-021).
  오버레이 추가가 없는 **형제 변형**입니다 — 전 9 역할이 `nemotron-3-nano:30b` 단일.
- **왜 부모를 갈아끼우지 않는가**: 부모 `localllm` 은 qwen2.5 기준으로 **불변 유지**합니다.
  모델을 바꾸면 측정 01~09 의 **대조군이 사라져** 기존 실측이 해석 불가가 됩니다.
- **추론 모델 관문** (필수 주의): nemotron·gemma 같은 추론 모델은 도구를 호출하기 **전에**
  추론 토큰을 씁니다. 전역 설정에 `limit:{context,output}` 이 없으면 추론 중간에 잘려
  도구 호출이 **0건**이 됩니다 (`finish=length`). `opencode-setup.sh` 가 등재·보정을 자동 처리합니다.
  `limit` 은 두 필드를 **모두** 요구합니다 — 하나만 넣으면 OpenCode 가
  `Configuration is invalid` 로 **전 실행을 거부**합니다.
- **부수 성과 (F031, ADR-022)**: 이 변형을 만들다가 하네스가 오래 품고 있던 결함이 드러났습니다 —
  파일 생성에 `edit` 도구를 지목하면서 `content` 를 넘기라 지시했는데, `edit` 스키마에는
  `content` 가 없어 **만족 불가능한 지시**였습니다. qwen 은 지시를 무시하고 `write` 를 불러
  통과했고, 문자 그대로 따르는 모델만 실패했습니다. 이후 도구 지시를
  **스키마 스냅샷에서 파생**시키고(`.claude/schema/opencode-tools.json`),
  `schema_check.py` 로 회귀를 막습니다.
- **검증 범위 (정직하게)**: 도구 호출 성립·코드 품질·격리 단일과제(5/5)는 확인됐습니다.
  **사이클 완주율은 부모 대비 우위가 확인되지 않았고**, 판정 기록 누락과 빈 응답이 미해결입니다.
  호출당 150~220초로 부모(30~77초)보다 느려 **시나리오 예산을 모델 속도에 비례해 산정**해야
  합니다(`SUITE_DRIVER_TIMEOUT`). 자세한 수치는 `docs/poc/measurements/11-host-comparison.md`.
- **언제**: nemotron 계열을 평가할 때. **성능 우위를 근거로 채택하지는 마세요** — 미검증입니다.
- **외부 의존성**: localllm 상속분 + OpenCode/Ollama.

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
| `claude.hermes` | **허용**(wiki 상속) | Obsidian/qmd/Marp (hermes 기능은 stdlib) |
| `claude.productmgr` | **허용**(hermes 상속) | Obsidian/qmd/Marp (pm 오버레이는 stdlib/문서) |
| `claude.productnw` | **허용**(productmgr 상속) | Obsidian/qmd/Marp (nw 오버레이는 stdlib/문서) |
| **`claude.loope`** ★ | **허용**(productmgr 상속) | Obsidian/qmd/Marp (loop 오버레이는 stdlib/문서) |
| **`claude.vela.v0.1`** 🚀 | **허용**(loope 상속) | 위 + **Atlassian 공식 MCP 커넥터** (선택적 — 미연결 시 안내만) |
| `claude.aif` | **허용**(loope 상속) | Obsidian/qmd/Marp (aif 오버레이는 stdlib/문서) |
| `localllm` | **허용**(loope 상속 + 호스트) | 위 + OpenCode / Ollama |
| `localllm.aif` | **허용**(localllm 상속) | 위 + OpenCode / Ollama |
| `localllm.nem` | **허용**(localllm 상속) | 위 + OpenCode / Ollama |
| `openai/.codex` | 0 | — |

> 핵심 기능은 모두 **stdlib(bash + Python 표준)** 으로 동작하며, 외부 도구는 *향상*만 합니다(graceful degrade).
> `wiki` 이전 변형은 이 예외를 상속하지 않습니다 (`lint.py check --only=LINT-MR` 이 격리 강제).

---

## 미러·정합성

- 변형 간 오버레이 격리는 `python3 .claude/bin/lint.py check --only=LINT-MR` 로 자동 가드됩니다
  (**MR-1~15**). 신규 변형은 이 목록에 등재해야 하며, 등재 누락은 BLOCK 으로 잡힙니다.
- **미러 방향**: 메인(`harness_update_agent/.claude/`) → **`claude.loope`(1:1)** → 하위 변형은
  오버레이 규칙대로 제외 미러 (F021 / ADR-015).
- **미러링 주의 (실제로 겪은 회귀)**: `CLAUDE.md` 를 **통째로 복사하지 마세요**.
  변형마다 고유 헤더(변형 정체·모델 배정·특이사항)가 있어 전체 복사는 그것을 파괴합니다.
  변경은 **절 단위**로 반영하세요. 변형별 `settings.json`/`host.json` 도 덮어쓰지 마세요 (F010 교훈).
- 설계 근거는 각 변형의 `harness/docs/adr/` 에 있습니다:

| ADR | 주제 |
|---|---|
| ADR-001 | 멀티 호스트 어댑터 |
| ADR-006 · 007 · 008 | design-pick · wiki · orch(d-1) |
| ADR-009 · 017 | OpenCode 어댑터 · localllm loope 계보 승격 |
| ADR-010 · 011 · 012 | hermes · pm · consortium(d-3) |
| **ADR-014 · 015** | **loop 오버레이 · 미러 SSOT(main ≡ loope)** |
| ADR-018 · 019 | 결정론 supervisor(cycle_driver) · autoresearch |
| ADR-020 | aif 판정 오버레이 |
| ADR-021 · 022 | 모델 축 분기 · 모델의 선의에 기대지 않는 도구 지시 |
| **ADR-023** | **vela 버전 계보 · Atlassian(Jira·Confluence) 연동** |
