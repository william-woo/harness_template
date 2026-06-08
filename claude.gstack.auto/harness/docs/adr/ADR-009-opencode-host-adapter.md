# ADR-009: OpenCode 호스트 어댑터 (d-2 로컬 LLM 실구현)

> Feature: F015 — Phase 11 OpenCode 호스트 어댑터
> 작성: architect 에이전트 | 날짜: 2026-06-07
> 선행: ADR-001 (멀티 호스트 아키텍처), ADR-008 (이종 에이전트 오케스트레이션, d-1)

## 상태

`Accepted` — 본 ADR은 F006 의 stub 어댑터 패턴(codex/openclaw)을 OpenCode 에 대해 **실구현**한다. 결정은 PoC 측정 01·02·03·03b 5회 실측(2026-06-06 ~ 06-07, `src/harness_template/localllm/harness/docs/poc/`)과 `opencode 1.16.2` CLI 동작 직접 확인에 근거한다. 추측 0.

---

## 컨텍스트

### PoC 측정으로 드러난 본질

5회 측정(`docs/poc/SUMMARY.md`)의 핵심 결론:

| 측정 | 항목 | 결과 |
|---|---|---|
| 01 | 지시 따르기 (Surgical/status/권한/컨텍스트) | ✅ PASS (qwen2.5:14b) |
| 02 | 도구 호출 (OpenCode Write tool) | ✅ PASS |
| 03 | `.claude/agents/*.md` 인식 | ❌ **미인식 — 어댑터 변환 필요** |
| 03 | subagent spawn 메커니즘 (general) | ✅ PASS |
| 03b | 멀티스텝 값 전달 (subagent 결과 치환) | ❌ **FAIL (14B 한계)** |

3분류로 정밀화된 결론:

| 분류 | 항목 | 로컬 LLM(OpenCode) 상태 |
|---|---|---|
| 모델 무관 | Python 헬퍼 7종, 훅, git, 거버넌스 파일 | ✅ 그대로 작동 |
| 모델 의존 | 지시 따르기, 도구 호출 | ✅ 14B PASS |
| **호스트 의존** | 에이전트 정의, 커맨드, 스킬 로딩 | ⚠️ **포맷 변환 필요** |
| 모델 의존 (멀티스텝) | orchestrate 같은 2-홉 추론 | ❌ 14B 한계 — 32B+ 필요 |

→ **d-2 어댑터의 본질은 모델 문제가 아니라 호스트 포맷 변환.**

### OpenCode 1.16.2 실측 사실 (어댑터 설계의 진실 공급원)

`opencode --help`, `opencode agent --help`, `opencode agent create --help`, `opencode agent create` 실행 결과로 확인된 사실:

| 영역 | OpenCode 실측 | Claude Code 대비 |
|---|---|---|
| agent 파일 위치 | `<dir>/agents/<name>.md` (CLI 기본) | `.claude/agents/<name>.md` |
| agent frontmatter | `description:`, `mode: all\|primary\|subagent`, `permission: { <tool>: allow\|ask\|deny }` | `name:`, `description:`, `model:`, `tools: A,B,C` |
| agent 본문 | 평문 시스템 프롬프트 (frontmatter 아래) | 평문 시스템 프롬프트 (frontmatter 아래) |
| 도구명 (CLI 권한 옵션) | `bash, read, edit, glob, grep, webfetch, task, todowrite, websearch, lsp, skill` (lowercase) | `Bash, Read, Write, Edit, MultiEdit, Glob, Grep, WebFetch, Task, TodoWrite, WebSearch` (PascalCase) |
| 도구명 차이 (실측) | **`write` 도구 없음** — `edit` 가 신규 파일 생성 + 수정 겸용 (측정 02 PASS 가 증명) | `Write` 와 `Edit` 분리 |
| 도구명 차이 (실측) | **`multiedit` 도구 없음** | `MultiEdit` 존재 |
| 모델 지정 | frontmatter 에 `model:` 필드 **없음** (실측: `--model` CLI 인자가 frontmatter 에 안 들어감). 모델은 (a) `opencode.jsonc` provider 기본, (b) `opencode run --model`, (c) `opencode --agent <name> --model` 로 호출시 지정 | frontmatter `model:` 필수 |
| 슬래시 커맨드 | TUI 내부 슬래시 + `opencode run --command <name>` (community 패턴: `.opencode/command/<name>.md`) | `.claude/commands/<name>.md` → `/project:<name>` |
| 훅 메커니즘 | `opencode plugin <npm-module>` (TypeScript 플러그인) | `.claude/settings.json` + bash 훅 |
| 프로젝트 env var | (관찰 안 됨 — 어댑터 placeholder 유지) | `$CLAUDE_PROJECT_DIR` |
| AGENTS.md | OpenCode 공식 컨벤션 — CLAUDE.md 와 동등 역할 | CLAUDE.md |

**핵심 비대칭** (어댑터 설계가 흡수해야 할 것):

1. `Write` 도구 부재 → canonical `write` 를 `edit` 로 매핑 (측정 02 가 이 패턴 PASS 확인)
2. `MultiEdit` 도구 부재 → canonical `multiedit` 를 `edit` 로 매핑 (성능 차이 있지만 동작 가능)
3. 모델은 frontmatter 가 아닌 호출 시점 지정 → 어댑터가 모델을 결정하지 않고 **호출자가 결정**하는 모델
4. `permission` 모델이 deny-list (생략 시 allow) — Claude Code 의 `tools:` allow-list 와 반대 방향

### 제약

- **무회귀가 최우선** (ADR-001 결정 6 유지): claude-code 경로 동작은 한 비트도 안 바뀐다
- **외부 의존성 0**: 어댑터 코어는 Python stdlib only (claude_code.py / codex.py 와 동일)
- **`.claude/settings.json` 절대 수정 안 함** (ADR-001 결정 1): Claude Code 공식 스키마 격리
- **단방향 변환만**: `.claude/` → `.opencode/` 렌더링 (역방향 없음 — SSOT 는 `.claude/`)
- **graceful degrade**: opencode CLI 미설치 환경에서도 어댑터 import 는 성공 (안내만 출력)

---

## 결정

### 결정 1 — OpenCode agent 포맷 변환: **정적 렌더링 (호출 시점 파일 생성)**

`opencode.py` 어댑터가 `.claude/agents/<name>.md` 7개를 읽어 `.opencode/agent/<name>.md` 7개를 **명시적 CLI 호출 시점에** 생성한다. on-demand TUI 후킹이 아닌, F006 `render-skills` 와 동일한 정적 변환 모델을 채택한다.

**변환 매핑 (확정)**:

| 항목 | Claude Code frontmatter | OpenCode frontmatter |
|---|---|---|
| `name:` | (있음) | (드롭 — 파일명이 곧 agent name) |
| `description:` | 그대로 | 그대로 (단 줄바꿈 시 `>-` block scalar) |
| `model:` | `claude-opus-4-7` 등 | **드롭** (호출 시점 `--model` 또는 `opencode.jsonc` 가 결정) |
| `tools: Bash,Read,Edit,Write` | allow-list | `permission:` deny-list 로 **역변환**: 명시 안 된 tool 을 deny |
| 본문 시스템 프롬프트 | 그대로 | 그대로 (단 본문 내 `{{HOST.*}}` 토큰은 base.py `_replace_tokens` 로 치환) |

**permission 역변환 알고리즘** (Claude Code allow-list → OpenCode deny-list):

```
opencode_all_tools = {bash, read, edit, glob, grep, webfetch, task, todowrite, websearch, lsp, skill}
claude_tools_lower = {t.lower() for t in claude_frontmatter.tools}  # 정규화
# write → edit, multiedit → edit (도구명 매핑, 결정 2 참조)
mapped = {tool_map(t) for t in claude_tools_lower}
denied = opencode_all_tools - mapped
opencode_permission = {tool: "deny" for tool in denied}
```

`tools:` 가 비어 있거나 명시 안 됐으면 `permission:` 도 생략 (= 전체 허용).

**Mode 매핑**:

| 우리 에이전트 | OpenCode mode | 근거 |
|---|---|---|
| developer, reviewer, qa, designer, researcher, planner, architect, gatekeeper | `all` | **측정 04 보정** (아래) — primary 직접 진입 + subagent spawn 겸용 |
| (없음) | `primary` | 우리는 별도 primary agent 없음 — OpenCode 빌트인 `build` 가 primary 역할 수행 |

> **측정 04 보정 (2026-06-08, F015 세션 3)**: 최초엔 8 에이전트를 `mode: subagent` 로 변환했으나,
> OpenCode 에서 **subagent 는 `opencode run --agent <name>` 직접 진입점이 될 수 없다**
> ("not a primary agent → fallback"). d-2 의 주 사용 사례인 **단일역할 직접 호출**이 막힌다.
> → `mode: all` 로 변경. `all` 은 primary(직접 진입) + subagent(task spawn) 겸용 **상위집합**이라
> 단일역할 직접 호출과 orchestrate task spawn 을 모두 만족한다. (opencode.py `_format_opencode_agent`)
> 실측: mode:all 직접 호출 시 헤더 `> developer`, fallback 경고 소멸 — docs/poc/measurements/04-single-role-e2e.md

**대안 검토**:

| 옵션 | 장점 | 단점 |
|---|---|---|
| (A) **정적 렌더링** (채택) | 단순, 검증 가능, F006 render-skills 패턴 재사용, claude_code.py 무회귀 보장 | `.opencode/` 디렉토리 추가 (gitignore 가능) |
| (B) opencode.json 의 `agent` 키에 통합 | 파일 수 적음 | OpenCode 가 외부 디렉토리 agent 도 인식 (실측) — 굳이 통합할 이유 없음. JSON 안에 7개 시스템 프롬프트를 박는 가독성 손실 |
| (C) `opencode agent create` 매번 호출 | "공식" 경로 | 18초 + 인터랙티브 (실측 — LLM 호출 포함). 결정론 손실. 배치 변환 불가 |

→ **(A) 채택**. 우리 어댑터가 frontmatter 를 직접 생성한다. opencode CLI 의 `agent create` 는 신규 agent 를 LLM 으로 작성하는 도구이지, 우리처럼 기존 7 agent 를 결정론적으로 변환하는 용도가 아니다.

**산출 위치**: `<project_root>/.opencode/agent/<name>.md` (7 파일)

---

### 결정 2 — tool_name 매핑: 호스트 비대칭 흡수

`base.py` 의 토큰 카탈로그 (`{{HOST.TOOL.*}}`) 를 OpenCode 도구명으로 치환한다. 단 **OpenCode 에 없는 도구(`write`, `multiedit`)는 `edit` 로 융합**한다.

**확정 매핑 테이블** (`host_adapters/opencode.py` 의 `_TOOL_MAP`):

```python
_TOOL_MAP = {
    "bash": "bash",
    "read": "read",
    "write": "edit",      # OpenCode 의 edit 가 신규 파일 생성 겸용 (측정 02 PASS)
    "edit": "edit",
    "multiedit": "edit",  # OpenCode 에 multiedit 없음 — edit 로 다회 호출 권고를 스킬에 명시
    "glob": "glob",
    "grep": "grep",
}
```

**근거**:
- 측정 02 (`02-tool-calling.md`) 가 OpenCode `edit` 도구로 신규 파일 작성 PASS 를 확인 — `write → edit` 융합은 실측 기반 안전.
- `multiedit → edit` 융합은 성능 손실 (1회 → N회 호출) 이 있지만 동작은 보장. 측정 02 가 단일 `edit` PASS 만 확인했으므로 성능 차이는 후속 측정(05)에서 정량화.

**스킬 보강** (결정 5 와 연계): `multiedit` 가 가능한 사용자 시나리오를 만났을 때, OpenCode 모드에서는 "edit 을 여러 번 호출" 하라는 가이드를 코딩 스킬에 명시.

---

### 결정 3 — command_invocation: `opencode run --command <name>` 표기 (관찰 가능 패턴)

OpenCode 의 슬래시 커맨드는 TUI 전용이고, headless/scripted 경로는 `opencode run --command <name>` (community 패턴: `.opencode/command/<name>.md`). 우리 어댑터는 후자 표기를 채택한다.

```python
def command_invocation(self, name: str) -> str:
    return f"opencode run --command {name}"
```

**근거**:
- `opencode run --help` 가 `--command` 인자를 명시적으로 지원 (실측).
- 우리 24 commands (handoff, plan-full, host, design-review, qa-browser, lint, wiki, orchestrate 등) 를 `.opencode/command/<name>.md` 로 미러링하면 TUI/스크립트 양쪽에서 호출 가능.
- 단, **이 매핑은 결정 1 의 후속 작업**: 커맨드 미러링은 F015 본 phase 의 범위에서 제외 (시간 박싱). 토큰 치환만 정확하면 사용자가 `opencode run --command handoff` 표기를 읽을 때 의미가 통한다. 실제 `.opencode/command/*.md` 생성은 후속 phase (F016 가칭) 에서 작업.

**대안 검토**:

| 옵션 | 장점 | 단점 |
|---|---|---|
| (A) `opencode run --command <name>` 표기 (채택) | CLI 가 지원, headless 호환, 스크립트 가능 | TUI 슬래시 표기와 다름 |
| (B) `/<name>` (TUI 슬래시) | UX 친숙 | headless 미지원, `opencode --demo` 의존 |
| (C) placeholder | 시간 절약 | 무의미 — 어댑터가 실구현 되는데 표기가 안내문이면 모순 |

→ **(A) 채택**.

---

### 결정 4 — 모델 등급 분기 정책: **어댑터가 모델을 결정하지 않음** (호출자 책임)

OpenCode 의 model 은 frontmatter 가 아니라 호출 시점 또는 `opencode.jsonc` 가 결정한다 (실측). 따라서 어댑터는 **모델 선택 로직을 포함하지 않는다**. 대신:

1. **단일 역할 (developer/reviewer/qa/designer/researcher/planner/architect/gatekeeper)**:
   - 권장: `ollama/qwen2.5:14b-instruct-q8_0` (측정 01·02 PASS)
   - 호출 예: `opencode run --agent developer --model ollama/qwen2.5:14b-instruct-q8_0 "..."` 또는 `opencode.jsonc` 의 default model
2. **멀티스텝 오케스트레이션 (orchestrate.md)**:
   - 권장: 32B+ (측정 03b FAIL 근거). 현재 서버 (172.16.10.217) 엔 14B 만 — orchestrate E2E 는 보류 또는 흐름 단순화.
   - 호출 예: `opencode run --agent orchestrate --model ollama/<32B-model> "..."` (32B 모델 도입 후)

**산출물**: `docs/poc/MODEL-GRADES.md` (1페이지) — 등급표 + 호출 패턴 + 측정 근거 링크. host.json 에 model 등급을 박지 않는다 (모델 변경이 잦을 것이므로 ADR + 문서로 가이드).

**대안 검토**:

| 옵션 | 장점 | 단점 |
|---|---|---|
| (A) **어댑터는 모델 미관여, 문서로 가이드** (채택) | OpenCode 실제 모델 모델과 일치, 유연 | host.json 에 등급 명시 안 됨 |
| (B) `host.json` 에 `model_grades: { single: "...", multi: "..." }` 추가 | 한 곳에 정책 집중 | OpenCode 가 안 읽음 — 어댑터가 환경변수/CLI 옵션으로 주입해야 (복잡도↑) |
| (C) agent frontmatter 에 `model:` 강제 주입 | Claude Code 호환 | 실측: OpenCode 가 frontmatter `model:` 미사용 — 의미 없음 |

→ **(A) 채택**. 어댑터는 변환만, 모델 선택은 호출자 책임.

---

### 결정 5 — 스킬·프롬프트 보강: **opencode 변형 전용 오버레이** (다른 변형 무영향)

측정 02 가 발견한 모델 절대경로 습관과 결정 2 의 `multiedit → edit` 융합 안내를 **localllm 변형의 코딩 스킬에만** 주입한다. 다른 6 변형은 영향 없음.

**산출**: `src/harness_template/localllm/harness/.claude/skills/coding/SKILL.md` 에 다음 섹션 추가:

```markdown
## OpenCode 호스트 가이드 (이 변형 전용)

- **상대경로 우선**: 절대경로보다 `./` 상대경로를 우선 사용 (측정 02 발견)
- **신규 파일 생성**: `Write` 대신 `edit` 도구 사용 (OpenCode 에 `Write` 없음)
- **다중 편집**: `multiedit` 대신 `edit` 를 여러 번 호출 (OpenCode 에 `multiedit` 없음)
- **에이전트 호출**: `Task` tool 로 subagent spawn (측정 03 PASS — `general` 빌트인 사용 가능)
```

`.opencode/AGENTS.md` (OpenCode 의 CLAUDE.md 상당) 에는 더 짧은 요약을 둔다. 둘 다 두면 모델이 한쪽만 읽어도 가이드를 받는다.

**대안 검토**:

| 옵션 | 장점 | 단점 |
|---|---|---|
| (A) 코딩 스킬 + AGENTS.md 둘 다 (채택) | 모델이 어느 쪽을 읽어도 가이드 받음 | 약간의 중복 |
| (B) AGENTS.md only | 단일 진실 | 모델이 스킬을 먼저 읽으면 가이드 누락 |
| (C) 모든 에이전트 frontmatter description 에 inline | 강제 노출 | 중복 다수, 변환 복잡도↑ |

→ **(A) 채택**.

---

### 결정 6 — localllm 변형 PoC 졸업 여부: **PoC 변형 유지 (정식 졸업은 다음 phase 보류)**

F015 어댑터 완성 후에도 localllm 변형은 **PoC 상태** 로 유지한다. 정식 변형 승격(LINT-MR 등록)은 후속 phase 의 측정 04·05 PASS 가 누적된 후로 미룬다.

**근거**:
- 측정 03b FAIL (멀티스텝 14B 한계) 가 미해결 — 32B+ 모델로 재측정 전엔 orchestrate 안정성 미확인
- LINT-MR 등록은 무회귀 보증의 무게가 큰 작업 — PoC 단계에서 등록하면 MR 가드가 잦은 변경(스킬 보강·도구명 추가) 마다 BLOCK 을 발생
- localllm/ 디렉토리는 이미 격리돼 다른 변형에 영향을 주지 않음 (단순 파일 시스템 격리)

**대신 F015 가 보장하는 것**:
1. `host_adapters/opencode.py` 실구현 (`is_stub=False`)
2. `host.json` agent_type=opencode 지원 (결정 7)
3. localllm 변형이 어댑터를 실사용 (`.opencode/agent/` 자동 생성)
4. 측정 04 (단일 역할 E2E — 결정 8) PASS — 어댑터가 측정 가능한 출력을 만든다는 검증

**LINT-MR 등록 조건** (후속 phase 트리거):
- 측정 04 (단일 역할) + 측정 05 (멀티스텝, 32B 모델) 둘 다 PASS
- 다운스트림 프로젝트가 1개 이상 localllm 변형을 채택
- 위 충족 시 후속 ADR (예: ADR-010) 로 정식 변형 승격 + LINT-MR-9 (opencode 오버레이 격리) 추가

**대안 검토**:

| 옵션 | 장점 | 단점 |
|---|---|---|
| (A) **PoC 유지 (채택)** | 무회귀 안전, MR 가드 noise 회피 | 변형 매트릭스에 안 보임 |
| (B) F015 에서 정식 승격 | 8 변형으로 즉시 일관성 | 측정 03b 미해결 + 잦은 변경으로 MR 가드 마찰 |

→ **(A) 채택**.

---

### 결정 7 — host.json agent_type=opencode 지원

`host.py` 가 `opencode` 어댑터 로드를 인식하도록 `_load_adapter` 분기를 확장한다. 동작:

- `HARNESS_AGENT_TYPE=opencode` 또는 `host.json` 의 `agent_type: "opencode"` 시 `OpenCodeAdapter` 로드
- `/project:host` 명령이 opencode 어댑터의 `adapter_info()` 출력 (도구 매핑·커맨드 예시 표시)
- `/project:host check` 가 opencode 변형에서 회귀 점검 (claude-code 변형에 영향 X)
- `python3 .claude/bin/host.py render-skills` 가 opencode 변형에서:
  - `.claude/skills/<name>/SKILL.md.template` → `.claude/skills/<name>/SKILL.md` 토큰 치환
  - **추가**: `.claude/agents/*.md` → `.opencode/agent/*.md` 7 파일 생성 (결정 1)

**우선순위 (ADR-001 결정 1 그대로)**:
1. 환경변수 `HARNESS_AGENT_TYPE`
2. `.claude/host.json` 의 `agent_type`
3. 기본값 `claude-code`

**중요**: `.claude/settings.json` 은 **절대 수정 안 함** (ADR-001 결정 6 유지). OpenCode 의 hook 메커니즘 (plugin npm) 은 별도 후속 phase 에서 처리. F015 에서는 hook 미러링 미포함.

---

### 결정 8 — 측정 04 범위: **단일 역할 E2E 만** (멀티스텝은 보류)

F015 검증으로 다음 1개 측정을 실행:

**측정 04 — 단일 역할 E2E (developer)**:
- 시나리오: localllm 변형에서 `host.json` agent_type=opencode 설정 → `render-skills` 실행 → `.opencode/agent/developer.md` 생성 확인 → `opencode run --agent developer --model ollama/qwen2.5:14b-instruct-q8_0 "create file X with content Y"` 실행 → 파일 생성 확인
- 합격 기준: 7 agent 변환 모두 생성 + developer 1개로 파일 생성 PASS
- 실패 시: 어댑터 frontmatter 매핑 오류 디버그 후 재시도

**측정 05 (멀티스텝 orchestrate) 는 F015 범위 제외**:
- 32B 모델 서버 부재로 측정 03b FAIL 이 재현될 가능성 높음
- 모델 도입 후 후속 phase 에서 측정 (F016 가칭)
- 측정 04 PASS 만으로 F015 acceptance_criteria 8번 충족 가능 (단일 역할 = "또는" 조건)

**근거**:
- F015 acceptance_criteria 8번이 "측정 04 또는 단일 역할 E2E" 라고 명시 — 후자만 충족해도 합격
- 측정 03b 가 이미 14B 한계를 정량화 — 재측정은 32B 도입 전엔 정보 가치 0

---

### 결정 9 — 세션 분할 (3 세션)

| 세션 | 작업 | 산출물 | 검증 |
|---|---|---|---|
| 1 | opencode.py 어댑터 코어 | `host_adapters/opencode.py` (is_stub=False) + `host.py` _load_adapter 분기 | `python3 .claude/bin/host.py info` 가 opencode info 출력. claude-code info 무회귀 |
| 2 | agent 포맷 변환 렌더링 | `host.py render-skills` 가 `.opencode/agent/*.md` 7개 생성 + 스킬 보강 (결정 5) | 7 파일 생성. opencode CLI 가 인식 (없을 시 `--agent` 인자에 이름 통과 확인) |
| 3 | localllm 적용 + 측정 04 + CLAUDE.md + 미러링 | localllm/host.json agent_type=opencode + 측정 04 결과 (`docs/poc/measurements/04-*.md`) + CLAUDE.md 업데이트 + 메인 미러링 | 측정 04 PASS. 7 변형 LINT-MR 무회귀 (MR-1~8 모두 PASS) |

**세션 간 인계**: claude-progress.txt prefix 형식 (`## [YYYY-MM-DD HH:MM] developer | F015 세션 N — ...`).

---

## 대안 (전체)

| 결정 | 선택 | 거부 안 | 거부 사유 |
|---|---|---|---|
| 1 | 정적 렌더링 | opencode.json 통합 / `agent create` 호출 | 가독성, 결정론, 시간 |
| 2 | write/multiedit → edit 융합 | 미구현 도구는 BLOCK | 측정 02 PASS 가 융합 안전을 증명 |
| 3 | `opencode run --command` 표기 | TUI 슬래시 / placeholder | headless 호환 + 의미 명확 |
| 4 | 어댑터 모델 미관여 | host.json 등급 / frontmatter `model:` | OpenCode 실제 모델 모델과 일치 |
| 5 | 스킬 + AGENTS.md 듀얼 | AGENTS.md only / 에이전트 frontmatter | 노출 보장 |
| 6 | PoC 유지 | F015 정식 승격 | 측정 03b 미해결, MR 마찰 |
| 7 | host.py 분기 확장 | settings.json 확장 | ADR-001 결정 6 (settings 격리) |
| 8 | 측정 04 만 | 측정 05 포함 | 32B 모델 부재 |
| 9 | 3 세션 | 1 세션 / 5 세션 | 산출물 크기 균형 |

---

## 결과

### 긍정적 영향

1. **d-2 어댑터 본질이 실구현됨** — Claude Code → OpenCode 포맷 변환이 자동화. 다운스트림이 OpenCode 로 하네스를 가져갈 수 있는 경로 개통.
2. **무회귀 보장 유지** — claude-code 변형 + 6 다른 변형 모두 한 비트도 안 바뀜. LINT-MR 8개 룰 모두 PASS.
3. **측정 기반 결정** — 9 결정 모두 5회 PoC 측정 또는 opencode 1.16.2 CLI 실측 근거. 추측 0.
4. **모델-무관 / 모델-의존 / 호스트-의존 3분류 확정** — 향후 다른 호스트 어댑터 (cursor/codex 등) 가 같은 분류로 분석 가능.
5. **F006 ADR-001 의 어댑터 패턴이 stub → 실구현 으로 전이된 첫 사례** — codex/openclaw 의 후속 실구현 템플릿이 됨.

### 부정적/잠재 영향

1. **멀티스텝 미해결** — orchestrate 같은 복잡한 흐름은 14B 로 불가, 32B 도입 후속 phase 필요.
2. **`.opencode/` 디렉토리 추가** — localllm 변형에 신규 디렉토리 (gitignore 권장).
3. **커맨드 미러링 미포함** — `command_invocation` 은 표기만 변환, 실제 `.opencode/command/*.md` 생성은 후속.
4. **OpenCode plugin (hook 대체) 미구현** — settings.json 의 훅 5종 (pre-bash-check, pre-write-check, post-write-check, session-end, pre-bash-auto-boundary-check) 의 OpenCode 매핑은 후속 phase.
5. **localllm PoC 변형 유지** — 다른 6 변형과 일관성 매트릭스에 통합되지 않음 (의도된 선택, 결정 6).

### 영향받는 acceptance_criteria (F015)

| AC | 결정 매핑 | 충족도 |
|---|---|---|
| 1. opencode.py 실구현 (is_stub=False) | 결정 7 | ✅ 세션 1 |
| 2. tool_name 매핑 (Bash/Edit/Read → OpenCode) | 결정 2 | ✅ 세션 1 |
| 3. command_invocation (/project:<name> → OpenCode) | 결정 3 | ✅ 세션 1 |
| 4. `.claude/agents/*.md` → `.opencode/agent/*.md` 변환 | 결정 1 | ✅ 세션 2 |
| 5. 모델 등급 분기 (단일=14B / 멀티=32B+) | 결정 4 | ✅ 세션 2 (`docs/poc/MODEL-GRADES.md`) |
| 6. 스킬 보강 (상대경로 우선) | 결정 5 | ✅ 세션 2 |
| 7. localllm 변형 적용 + host.json agent_type=opencode | 결정 7 | ✅ 세션 3 |
| 8. 측정 04 또는 단일 역할 E2E | 결정 8 | ✅ 세션 3 |
| 9. LINT-MR localllm 정식 등록 검토 | 결정 6 (보류) | ⏸️ 세션 3 결론만 |
| 10. ADR-009 | 본 문서 | ✅ (architect, 본 ADR) |

### 후속 작업 (F015 범위 외)

- **F016 가칭**: `.opencode/command/*.md` 미러링 (커맨드 24개 변환)
- **F017 가칭**: OpenCode plugin (npm) 으로 hook 5종 매핑
- **F018 가칭**: 32B 모델 도입 후 측정 05 (멀티스텝 orchestrate E2E)
- **F019 가칭**: 측정 04/05 PASS 후 localllm 정식 변형 승격 + LINT-MR-9 추가

---

## 참고

- ADR-001 멀티 호스트 아키텍처 (F006) — 본 ADR 의 상위 추상화
- ADR-008 이종 에이전트 오케스트레이션 (F013 d-1) — d-2 의 직전 단계
- `src/harness_template/localllm/harness/docs/poc/SUMMARY.md` — 5회 측정 종합
- `src/harness_template/localllm/harness/docs/poc/measurements/03-multi-agent.md` — 어댑터 본질 발견
- `.claude/bin/host_adapters/base.py` — HostAdapter ABC + 토큰 카탈로그
- `.claude/bin/host_adapters/claude_code.py` — 실구현 어댑터 참고 모델
- `.claude/bin/host_adapters/codex.py` — stub 어댑터 패턴 (대조)
- opencode 1.16.2 CLI 실측 (2026-06-07): `opencode agent --help`, `opencode agent create`, `opencode run --help`, `~/.config/opencode/opencode.jsonc`
