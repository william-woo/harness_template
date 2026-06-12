# ADR-010: `claude.hermes` 변형 — 영속 기억·자가 진화 오버레이 (Hermes Agent 패턴 이식)

> Feature: F016 — Phase 12 `claude.hermes` 변형
> 상태: `Accepted` (구현 완료 — session_search.py + skill_forge.py + 커맨드 2종)
> 관련: ADR-007(wiki), ADR-008(orch), ADR-009(opencode/d-2), NousResearch/hermes-agent 검토

## 맥락

NousResearch 의 **hermes-agent**("the agent that grows with you") 검토에서, 우리 하네스와
같은 빌딩블록(메모리·스킬·게이트웨이·모델무관)을 "영속 개인 비서" 목적으로 조립한 형제
프로젝트임을 확인했다. 그중 우리 하네스(개발 SDLC 거버넌스)에 **직접 이식 가치가 높은 3가지**를
새 변형 `claude.hermes` 에 적용한다:

1. **스킬 자동 생성 / self-improve** — Hermes 는 복잡 작업 후 재사용 스킬을 자동 생성하고 사용 중 개선
2. **FTS5 세션 검색** — Hermes 의 cross-session recall (FTS5 + 요약)
3. **agentskills.io 표준** — Anthropic 원작 개방 스킬 표준 (Hermes 가 채택)

## 결정

### 결정 1 — 새 변형 `claude.hermes` = orch 변형 복사 + hermes 오버레이

`claude.gstack.auto.design.wiki.orch` 를 복사해 `claude.hermes` 로 만든다. 따라서
auto+design+wiki+orch 오버레이를 **모두 상속**한다 (8 에이전트 + wiki + orch 포함).

> **명명 주의**: 누적 명명 규칙대로면 `…orch.hermes` 이지만, 사용자 요청대로 짧은
> `claude.hermes` 를 채택한다. 이름이 상속 계보(auto/design/wiki/orch)를 드러내지 않으므로
> 본 ADR + CLAUDE.md 매트릭스가 계보를 명시한다.

### 결정 2 — FTS5 세션 검색 (`session_search.py`): stdlib only, wiki/brain 과 책임 분리

- SQLite **FTS5**(Python stdlib sqlite3) 로 `claude-progress.txt`(신규 `## [..]` + 레거시
  `====` 형식 모두) + `.claude/state/checkpoints/*.md` 를 색인/검색.
- FTS5 미지원 빌드 → `grep` 대체 안내 (graceful degrade, 차단 X).
- DB `.claude/state/sessions.db` 는 **gitignore** (로컬 캐시, 언제든 재색인).
- **책임 분리**: `session-search`=세션 **이력** 검색 / `wiki query`=지식 **노드** 검색 /
  `brain`=**cross-project** 지식. 셋은 대상이 달라 중복이 아니다.

### 결정 3 — 스킬 자동 생성/self-improve (`skill_forge.py`): 결정론 부분만 자동화

Karpathy "추측 자동화 금지" 원칙에 따라 역할을 분리한다:
- **헬퍼(결정론)**: 폴더 구조 scaffold, frontmatter/메타데이터 생성, agentskills.io 적합성
  검증, 사용 카운터(`metadata.uses`) 추적, 개선 후보 `nudge`.
- **에이전트(LLM)**: 스킬 **본문**(단계/예시/엣지케이스) 작성 및 개선.
- **self-improve 루프**: `record-use` 로 사용 누적 → `nudge --threshold N` 이 자주 쓰였는데
  오래 개선 안 된 스킬을 짚음 → 에이전트가 본문 개선 + `version`/`last_improved` 갱신.
  (Hermes 의 "사용 중 self-improve" 를 nudge 기반으로 단순화 — 완전 자동 재작성은 하지 않음.)

### 결정 4 — agentskills.io 표준 적합성

- 표준(spec): 스킬 = `SKILL.md`(필수 `name`+`description`) + 선택 `scripts/`/`references/`/`assets/`,
  progressive disclosure(name+description → 본문 → 리소스).
- **기존 하네스 스킬(coding/testing/planning/design-review/qa-browser)은 이미 호환** —
  `skill_forge.py validate` 로 6/6 PASS 확인 (name+description frontmatter 보유).
- 신규 스킬은 scaffold 시 표준 구조로 생성. `validate` 가 name 규칙(1-64, 소문자·숫자·하이픈,
  디렉토리명 일치) + description(1-1024) 을 강제 (skills-ref validate 동등).

### 결정 5 — 외부 의존성: hermes 오버레이 자체는 stdlib only

- Hermes Agent 본체는 Python+Node+ripgrep+ffmpeg 등 무거운 스택이지만, 우리는 **패턴만
  이식**한다. `session_search.py`/`skill_forge.py` 는 **Python stdlib only**.
- 변형 외부 의존성 정책: wiki/orch 상속분(Obsidian/qmd/Marp) 은 그대로 허용되나,
  **hermes 3종 기능은 외부 의존성 0**. (게이트웨이·메시징 등 Hermes 의 무거운 부분은 이식 안 함.)

### 결정 6 — 격리: LINT-MR-10

hermes 오버레이(`session_search.py`, `skill_forge.py`, `commands/session-search.md`,
`commands/skill-forge.md`)는 **claude.hermes 에만** 존재해야 한다. 다른 8 변형에 누수 시 BLOCK.
`lint.py check --only=LINT-MR` (MR-10) 가 자동 가드.

## 대안 검토

| 옵션 | 장점 | 단점 |
|---|---|---|
| (A) **새 변형 claude.hermes (채택)** | 기존 변형 무회귀, 실험 격리 | 9번째 변형 — 매트릭스 증가 |
| (B) orch 변형에 직접 추가 | 변형 수 유지 | orch 변형 사용자에게 미요청 기능 강제, 회귀 위험 |
| (C) Hermes 본체 채택 | 완성된 구현 | 목적 불일치(개인 비서 vs SDLC), 무거운 의존성, 우리 거버넌스와 충돌 |

→ **(A) 채택**. 우리 하네스의 변형 격리 패턴(wiki/orch/localllm)과 일관.

## 결과

- 신규: `session_search.py`, `skill_forge.py`, 커맨드 2종, LINT-MR-10, 이 ADR.
- 기존 스킬은 변경 없이 agentskills.io 호환 확인 (validate 6/6 PASS).
- **이식 안 한 것**(의도): Hermes 의 메시징 게이트웨이(Telegram/Discord/…), Honcho 유저모델링,
  멀티플랫폼 — 개인 비서 영역이라 SDLC 하네스 목적과 불일치 (결정 5).

## 후속 (가칭)

- 스킬 간 의존성 그래프(wiki 연계), 세션 검색 결과의 brain.db 승격, agentskills.io Skills Hub 퍼블리시.
