# ADR-001: 멀티 호스트 아키텍처 준비 (claude-code / openclaw / codex)

> Feature: F006 — Phase 3 멀티 호스트 아키텍처 준비
> 작성: architect 에이전트 | 날짜: 2026-04-27

## 상태

`Accepted` — 본 ADR은 인터페이스/추상화/기본 어댑터(claude-code) 1개와 stub 안내만 도입한다.
실제 OpenClaw/Codex 어댑터의 완전 구현은 별도 후속 Feature로 분리한다.

---

## 컨텍스트

### 현재 상태 (Phase 1·2·3 완료 시점)

이 하네스는 **Claude Code 전용**으로 설계되어 있다. 모든 결합 지점이 Claude Code의 구체 스키마/규약을 가정한다:

| 결합 지점 | 현재 가정 | Claude Code 고유? |
|---|---|---|
| `.claude/settings.json` | `hooks` 키 + `PreToolUse/PostToolUse/Stop` 이벤트, `matcher`(`Bash`, `Write\|Edit\|MultiEdit`) | ✅ Claude Code 공식 스키마 |
| `.claude/hooks/*.sh` | stdin JSON: `{tool_name, tool_input.command, ...}` | ✅ Claude Code stdin 계약 |
| `.claude/agents/*.md` | YAML frontmatter (`name`, `description`, `model: claude-opus-4-7`, `tools: Read,Write,Edit,...`) | ✅ Claude Code 에이전트 규약 |
| `.claude/commands/*.md` | `/project:<name>` 슬래시 커맨드 | ✅ Claude Code UX |
| `.claude/skills/*/SKILL.md` | YAML frontmatter (`name`, `description`) + 본문 | 부분 (frontmatter 호환 여지 있음) |
| `$CLAUDE_PROJECT_DIR` | 환경변수 | ✅ Claude Code 주입 |
| 도구 이름 | `Bash`, `Read`, `Write`, `Edit`, `MultiEdit`, `Glob`, `Grep` | ✅ Claude Code 도구명 |

### F006의 목표

향후 OpenClaw, Codex 같은 다른 AI 에이전트 호스트에서 **같은 하네스를 그대로 또는 최소 변환으로** 사용할 수 있도록 **기반(scaffolding)** 만 마련한다. 지금 단계의 산출물은 다음과 같다:

1. 호스트를 식별하는 단일 진실 공급원(SSOT, Single Source of Truth)
2. 호스트별로 달라지는 부분을 추출한 **어댑터 인터페이스**
3. `claude-code` 기본 어댑터(현재 동작 그대로 보존)
4. `openclaw` / `codex` stub 어댑터 (안내 메시지만 출력)
5. 호스트별 SKILL.md 렌더링(도구명·커맨드 호출 표기 치환)

### 제약

- **무회귀가 최우선**: 기본값 = `claude-code`이고 이 경로의 동작은 한 비트도 바뀌면 안 된다.
- **외부 의존성 0**: bash + Python 3 stdlib만 사용 (F005 Brain과 동일 원칙).
- **Claude Code settings.json 스키마 호환**: Claude Code가 읽는 `hooks` 키 외 임의 키를 추가했을 때, 향후 스키마 검증이 강화되어도 깨지지 않게 한다.
- **OpenClaw/Codex의 호스트 스펙은 현재 미확정**: stub은 "여기에 매핑이 필요하다"는 자리표시만 한다.

---

## 결정

### 결정 1 — agent_type 의 위치: `.claude/host.json` (별도 파일) + 환경변수 오버라이드

`agent_type`을 `.claude/settings.json`에 넣지 **않는다**. 대신 **`.claude/host.json`** 라는 신규 파일을 SSOT로 둔다.

**파일 형식 (`.claude/host.json`)**:

```json
{
  "agent_type": "claude-code",
  "harness_version": 1,
  "notes": "기본값. openclaw/codex로 변경 시 /project:host 안내 메시지가 안내합니다."
}
```

**해석 우선순위 (높음 → 낮음)**:

1. 환경변수 `HARNESS_AGENT_TYPE` (값: `claude-code` | `openclaw` | `codex`)
2. `.claude/host.json` 의 `agent_type`
3. 기본값 `claude-code` (파일·환경변수 둘 다 없을 때)

**근거**:

| 옵션 | 장점 | 단점 |
|---|---|---|
| (A) `settings.json`에 커스텀 키 추가 | 파일 1개로 끝, 가까이 위치 | Claude Code의 settings 스키마가 향후 strict해질 위험. 실제로 Claude Code는 `hooks` 키만 인식하므로 임의 키가 무시되거나 경고를 띄울 가능성. 다른 호스트가 같은 파일을 자기 형식으로 쓰면 충돌. |
| (B) **별도 `.claude/host.json`** | 호스트별 메타를 한곳에 격리. settings.json은 Claude Code 전용으로 순수 유지. 다른 호스트가 본인의 settings를 가져도 host.json은 공유 가능. | 파일이 1개 늘어남. |
| (C) 환경변수만 사용 | 파일 추가 없음 | 영속성 없음, 새 셸/세션마다 재설정 필요, 팀 공유 불가. |

→ **(B) 채택**, (C)를 **오버라이드 수단**으로 병행.

**왜 `harness_version` 도 함께?**: 추후 스키마가 진화할 때 마이그레이션 경로 확보. 1로 시작.

---

### 결정 2 — 어댑터 인터페이스: 추상화 레이어 4개

호스트마다 달라지는 부분을 다음 4개 카테고리로 분리한다. 각 카테고리는 호스트별 **어댑터 모듈**이 책임진다.

| 카테고리 | 무엇이 다른가 (예시) |
|---|---|
| **A. 도구명 매핑** (Tool Naming) | `Bash` (Claude Code) ↔ `shell`/`exec` (가설적 OpenClaw) ↔ `terminal` (가설적 Codex). `Read`/`Write`/`Edit` 등 7개 도구. |
| **B. 커맨드 호출 표기** (Command Invocation) | `/project:plan-full` (Claude Code 슬래시) ↔ `harness plan-full` (CLI 가설) ↔ `@harness.plan-full` (가설). |
| **C. 훅/이벤트 모델** (Hooks / Lifecycle) | Claude Code: `PreToolUse`/`PostToolUse`/`Stop` + stdin JSON 계약. 다른 호스트는 모델이 다를 수 있음 (e.g. before/after callback, env-var 주입). |
| **D. 환경 컨텍스트** (Env Context) | `$CLAUDE_PROJECT_DIR` (Claude Code) ↔ `$OPENCLAW_WORKSPACE` (가설) ↔ `$CODEX_PROJECT_ROOT` (가설). |

**어댑터 모듈 위치**: `.claude/bin/host_adapters/`

```
.claude/bin/host_adapters/
├── __init__.py          # 빈 파일 (Python 패키지 마커)
├── base.py              # HostAdapter 추상 베이스 + Mapping 데이터 클래스
├── claude_code.py       # 기본 어댑터 (현재 동작과 100% 동일)
├── openclaw.py          # stub — 안내 메시지만 반환
└── codex.py             # stub — 안내 메시지만 반환
```

**핵심 인터페이스 (개념적, 실제 코드는 Developer가 작성)**:

`HostAdapter` 는 다음 4개 메서드/속성을 노출한다:

```
class HostAdapter:
    name: str                            # "claude-code" | "openclaw" | "codex"
    is_stub: bool                        # True면 안내 메시지만 출력하는 미구현 어댑터

    def tool_name(canonical: str) -> str
        # canonical: "bash" | "read" | "write" | "edit" | "multiedit" | "glob" | "grep"
        # 호스트별 실제 도구명으로 변환

    def command_invocation(name: str) -> str
        # "plan-full" → "/project:plan-full" (claude-code) 또는 "harness plan-full" (가설)

    def project_dir_env_var() -> str
        # "CLAUDE_PROJECT_DIR" (claude-code), "OPENCLAW_WORKSPACE" (가설), ...

    def render_skill_md(template_path: str) -> str
        # SKILL.md 템플릿을 읽어 호스트별 토큰을 치환해 반환
```

**호스트 감지 헬퍼**: `.claude/bin/host.py`

- `host.py current` → 현재 `agent_type` 출력 (1줄)
- `host.py info` → 호스트 정보 + 도구 매핑 + 커맨드 표기 예시 출력
- `host.py adapter` → Python에서 임포트 시 활성 어댑터 인스턴스 반환

**왜 Python인가?** F005에서 이미 `.claude/bin/brain.py` 가 stdlib만 사용하는 헬퍼 패턴을 정착시켰다. 동일 원칙으로 일관성 유지.

---

### 결정 3 — SKILL.md 렌더링: 토큰 치환 방식 (정적 템플릿 + 호스트별 렌더)

SKILL.md의 본문에는 도구명, 커맨드 호출, 환경변수 등 호스트마다 다른 표현이 등장한다. 이를 **이중 토큰** `{{HOST.토큰명}}` 으로 표기한 후 호스트 어댑터가 치환한다.

**원본 (저자가 쓰는 것)**: `.claude/skills/<name>/SKILL.md.template`

```markdown
…
도구 호출 시 {{HOST.TOOL.bash}} 도구를 사용하세요.
세션 종료 후 {{HOST.CMD.handoff}} 를 실행합니다.
프로젝트 루트는 {{HOST.ENV.project_dir}} 환경변수에서 읽으세요.
```

**렌더된 결과 (실제로 Claude Code가 읽는 것)**: `.claude/skills/<name>/SKILL.md`

- claude-code 어댑터: `Bash`, `/project:handoff`, `$CLAUDE_PROJECT_DIR`
- openclaw 어댑터(stub): 동일 자리에 `[OpenClaw 매핑 미구현 — F006 후속 Feature 참조]` 안내 + 원본 토큰 보존
- codex 어댑터(stub): 동일 패턴

**렌더 트리거**: `host.py render-skills` 서브커맨드. `agent_type` 변경 시 사용자가 명시적으로 재렌더하거나, `/project:host set <type>` 커맨드가 자동 호출.

**중요한 호환성 결정 — 기본값 무회귀**:

> 현재 존재하는 SKILL.md 파일들은 **그대로 둔다**. F006 시점에는 `.template` 파일이 없으면 기존 SKILL.md를 손대지 않는다. **즉, claude-code 사용자는 어떤 변화도 체감하지 않는다.**

`.template` 도입은 **점진적**으로 — 후속 Feature에서 SKILL.md 본문을 `.template` 로 마이그레이션한다. F006의 책임은 "렌더 엔진을 만들어두는 것"까지.

**토큰 카탈로그 (초안)** — base.py 에 상수로 정의:

| 토큰 | 의미 | claude-code 값 |
|---|---|---|
| `{{HOST.TOOL.bash}}` | 셸 도구명 | `Bash` |
| `{{HOST.TOOL.read}}` | 파일 읽기 | `Read` |
| `{{HOST.TOOL.write}}` | 파일 쓰기 | `Write` |
| `{{HOST.TOOL.edit}}` | 파일 편집 | `Edit` |
| `{{HOST.TOOL.multiedit}}` | 다중 편집 | `MultiEdit` |
| `{{HOST.TOOL.glob}}` | 파일 검색 | `Glob` |
| `{{HOST.TOOL.grep}}` | 텍스트 검색 | `Grep` |
| `{{HOST.CMD.<name>}}` | 슬래시 커맨드 호출 | `/project:<name>` |
| `{{HOST.ENV.project_dir}}` | 프로젝트 루트 환경변수 | `$CLAUDE_PROJECT_DIR` |
| `{{HOST.NAME}}` | 호스트 이름 | `claude-code` |

---

### 결정 4 — Stub 어댑터의 동작: "차단하지 않고 안내만"

`agent_type` 이 `openclaw` 또는 `codex` 로 설정되어도 **하네스가 멈추지 않는다**. 다음과 같이 동작한다:

1. `host.py current` 실행 시 `openclaw (stub — 어댑터 미구현)` 출력
2. `host.py info` 실행 시 다음 안내문 출력:
   ```
   ⚠️  OpenClaw/Codex 어댑터는 현재 stub입니다 (F006 Phase 3).
   - 도구명 매핑, 커맨드 표기, 훅 모델은 후속 Feature에서 구현됩니다.
   - 현재는 claude-code 환경에서만 모든 기능이 정상 동작합니다.
   - claude-code 로 전환: HARNESS_AGENT_TYPE=claude-code 또는
     /project:host set claude-code
   ```
3. `host.py render-skills` 호출 시 stub 어댑터는 SKILL.md 를 **수정하지 않고** 안내 메시지만 출력 후 exit 0
4. 모든 hook 스크립트는 현재처럼 동작 (어댑터 미참조 — Phase 3 단계에서는 hook 자체는 추상화하지 않음)

**왜 차단하지 않는가?**: F005 Brain의 hook-failure-tolerance 원칙과 동일. 하네스 보조 도구는 어떤 경우에도 사용자의 작업을 막지 않는다.

---

### 결정 5 — `/project:host` 커맨드 신설

호스트 전환·조회를 위한 단일 커맨드.

| 호출 | 동작 |
|---|---|
| `/project:host` | 현재 `agent_type` + 어댑터 정보 표시 (host.py info 호출) |
| `/project:host set <claude-code\|openclaw\|codex>` | `.claude/host.json` 에 기록 → `render-skills` 자동 호출 → 변경 안내 메시지 |
| `/project:host check` | 현재 어댑터로 SKILL.md/커맨드 무결성 점검 (stub이면 안내만) |

---

## 대안 검토

| 대안 | 장점 | 단점 | 제외 이유 |
|---|---|---|---|
| **A. settings.json 에 `agent_type` 직접 추가** | 파일 1개로 단순 | Claude Code 공식 스키마 외 키. 향후 Claude Code 측에서 strict 검증/경고 도입 시 깨질 위험. 다른 호스트(예: OpenClaw)도 자체 settings를 가질 수 있어 충돌 위험. | 호환성 위험 > 단순성 이득 |
| **B. `.claude/host.json` 별도 파일 (채택)** | settings.json 순수 유지. 호스트별 메타 격리. | 파일 1개 추가. | — |
| **C. 환경변수만 사용 (`HARNESS_AGENT_TYPE`)** | 파일 추가 없음 | 영속성·팀 공유 불가. CI/공동작업에서 불일치 | 단독 사용 X, 오버라이드용으로 병행 |
| **D. 어댑터를 bash 스크립트로** | 기존 hook과 일관됨 | 토큰 치환·테이블 매핑·테스트가 bash로는 비효율, 단위 테스트 어려움 | F005에서 Python 헬퍼 패턴 정립됨 |
| **E. 어댑터를 정식 플러그인 시스템(엔트리포인트)으로** | 확장성 최고 | 복잡도 폭증, 외부 패키지 필요 가능성 | "점진적 복잡도" 원칙 위배. F006는 기반만 |
| **F. SKILL.md 를 호스트별 디렉토리로 분기 (`skills/claude-code/coding/`)** | 단순 파일 복사 | 본문이 99% 동일한데 N배로 복제됨, 유지보수 폭발 | 토큰 치환이 더 경제적 |
| **G. 지금 OpenClaw/Codex 완전 구현** | F006 한 번에 끝 | 두 호스트의 실제 스펙·SDK가 미확정. 잘못된 가정 위에 구현하면 재작업 비용 큼 | F006의 estimated_sessions=2 와 맞지 않음 |

---

## 결과

### 긍정적 영향

- **무회귀**: claude-code 사용자는 `.claude/host.json` 1개 파일이 추가될 뿐 어떤 동작 변화도 없음
- **확장성**: OpenClaw/Codex의 실제 스펙이 확정되면 `claude_code.py` 를 본보기로 `openclaw.py` / `codex.py` 만 채워 넣으면 됨
- **명확한 결합 지점 카탈로그**: 토큰 카탈로그·도구 매핑 테이블이 "어디가 호스트에 묶여있나" 를 문서화 — 후속 마이그레이션의 체크리스트가 됨
- **외부 의존성 0**: F005 정책 유지
- **Claude Code 스키마 호환성**: settings.json 을 건드리지 않으므로 향후 Claude Code 측 변경에 강건

### 부정적 영향 / 트레이드오프

- 파일 1개 (`.claude/host.json`) 추가
- Python 모듈 5개(`base.py`, 3개 어댑터, `host.py`) 신규
- 슬래시 커맨드 1개 (`/project:host`) 신규
- SKILL.md 토큰 치환은 **렌더 엔진만 도입**하고 실제 본문은 그대로 둔다 → 후속 Feature에서 점진적 적용 필요 (덜 끝난 느낌이 있음)
- 호스트별 hook 추상화는 이번에 도입하지 않음 — 추후 OpenClaw가 `PreToolUse` 와 다른 라이프사이클을 가질 경우 hook 레이어 재설계 필요

### 후속 조치

- [ ] (F006-A 후속) OpenClaw 실제 스펙 확정 시 `openclaw.py` 채우기
- [ ] (F006-B 후속) Codex 실제 스펙 확정 시 `codex.py` 채우기
- [ ] (F006-C 후속) SKILL.md 본문을 `.template` 로 점진 마이그레이션
- [ ] (F006-D 후속) 훅 라이프사이클 추상화 (`HostAdapter.hook_events()`, `parse_tool_input()`)
- [ ] (F006-E 후속) `agents/*.md` frontmatter 의 `model:` 필드 호스트별 매핑 추가

---

## 구현 가이드 (Developer 인계용)

### 변경/신규 파일 목록

**신규 생성**:

```
.claude/host.json                              # SSOT — agent_type 저장
.claude/bin/host.py                            # CLI 헬퍼 (current/info/set/render-skills/check)
.claude/bin/host_adapters/__init__.py          # 빈 패키지 마커
.claude/bin/host_adapters/base.py              # HostAdapter 베이스 + 토큰 카탈로그
.claude/bin/host_adapters/claude_code.py       # 기본 어댑터 (실동작)
.claude/bin/host_adapters/openclaw.py          # stub 어댑터
.claude/bin/host_adapters/codex.py             # stub 어댑터
.claude/commands/host.md                       # /project:host 슬래시 커맨드 정의
docs/design/F006-multi-host-design.md          # (선택) 본 ADR을 보완하는 상세 설계 — 토큰 표·예시
```

**수정**:

```
CLAUDE.md                                      # "멀티 호스트" 섹션 추가, host.json 행 추가
.gitignore                                     # (검토) host.json 은 커밋, 환경변수는 자연 미추적
feature_list.json                              # F006 진행/완료 마킹 (Developer 작업 끝에)
.claude/state/learnings.jsonl                  # 새 학습 append (해당 시)
```

**의도적 미수정 (무회귀 보장)**:

```
.claude/settings.json                          # 손대지 않는다 — Claude Code 공식 스키마 유지
.claude/hooks/*.sh                             # 손대지 않는다 — 어댑터는 hook이 아닌 SKILL/커맨드만 추상화
.claude/agents/*.md                            # 손대지 않는다 — model 필드 호스트별 매핑은 후속
.claude/skills/*/SKILL.md                      # 손대지 않는다 — .template 마이그레이션은 후속
.claude/bin/brain.py                           # 손대지 않는다
```

### 단계별 작업 순서

**Step 1 — `.claude/host.json` 생성**
- 내용: `{"agent_type": "claude-code", "harness_version": 1, "notes": "..."}`
- 파일 존재 자체가 SSOT. 기본값 = claude-code → 무회귀 보장.
- 인수 기준 충족: **AC1 (settings.json/host에 agent_type 필드 추가)** — settings.json 대신 host.json 으로 결정.

**Step 2 — `host_adapters/base.py` 작성 (인터페이스 + 토큰 카탈로그)**
- `HostAdapter` 추상 클래스 (4개 속성/메서드: `name`, `is_stub`, `tool_name()`, `command_invocation()`, `project_dir_env_var()`, `render_skill_md()`)
- 토큰 카탈로그 상수 `CANONICAL_TOOLS = ["bash","read","write","edit","multiedit","glob","grep"]`
- 토큰 정규식: `r"\{\{HOST\.(TOOL|CMD|ENV|NAME)\.?([a-zA-Z_]*)\}\}"`
- 외부 의존성 0. typing.Protocol 또는 abc.ABC 사용.

**Step 3 — `host_adapters/claude_code.py` 작성 (기본 어댑터, 무회귀)**
- 토큰 매핑 테이블:
  - `TOOL.bash → "Bash"`, `TOOL.read → "Read"`, ... (7개)
  - `CMD.<name> → "/project:<name>"`
  - `ENV.project_dir → "$CLAUDE_PROJECT_DIR"`
  - `NAME → "claude-code"`
- `is_stub = False`
- `render_skill_md(template_path)`: 템플릿 파일이 있으면 토큰 치환 후 반환, 없으면 None (호출자가 무시)

**Step 4 — `host_adapters/openclaw.py` + `codex.py` (stub)**
- `is_stub = True`
- 모든 메서드는 호출 시 `[<host>: 어댑터 미구현 — F006 후속]` 형태의 placeholder 반환
- `render_skill_md()` 는 None 반환 (= 변경 없음)

**Step 5 — `host.py` CLI 작성**
- `argparse` 서브커맨드: `current`, `info`, `set`, `render-skills`, `check`
- 호스트 감지 우선순위:
  1. `os.environ.get("HARNESS_AGENT_TYPE")`
  2. `.claude/host.json` 의 `agent_type`
  3. `"claude-code"`
- 각 핸들러는 `try/except` 로 감싸 **항상 exit 0** (Brain 패턴과 동일)
- `set` 은 인자 검증 후 host.json 업데이트 + render-skills 자동 호출
- 인수 기준 충족: **AC2 (호스트별 커맨드 호출 어댑터)**, **AC4 (기본값 claude-code 유지, 다른 값 선택 시 안내)**

**Step 6 — `commands/host.md` 작성**
- 다른 `commands/*.md` 와 동일한 구조 (제목 + 실행 순서 + 출력 예시)
- 본문에서 `python3 .claude/bin/host.py <subcmd>` 호출

**Step 7 — SKILL.md 렌더링 동작 검증 (실제 .template 마이그레이션은 안 함)**
- 테스트용 임시 `.claude/skills/_test/SKILL.md.template` 1개 만들어 `host.py render-skills` 실행
- 결과로 `_test/SKILL.md` 가 토큰 치환되어 생성되는지 확인
- 테스트 후 임시 파일 제거 (또는 examples/ 디렉토리에 영구 보존)
- 인수 기준 충족: **AC3 (호스트별 SKILL.md 생성 로직)**

**Step 8 — CLAUDE.md 업데이트**
- 디렉토리 구조 트리에 `.claude/host.json`, `.claude/bin/host_adapters/` 추가
- 새 섹션 "## 멀티 호스트 (F006)" — host.json 위치, 환경변수 오버라이드, `/project:host` 커맨드 사용법
- "상태 파일 (.claude/state/)" 표 아래에 `.claude/host.json` 행 추가 (단, state가 아니라 config이므로 별도 표 권장)

**Step 9 — 무회귀 검증**
- `agent_type` 미설정 또는 `claude-code` 인 상태에서:
  - 모든 hook 정상 동작 (간단 Bash 명령으로 확인)
  - 모든 기존 슬래시 커맨드 정상 호출
  - `/project:start-session` → `/project:handoff` 라운드트립 정상
- `HARNESS_AGENT_TYPE=openclaw` 또는 `codex` 일 때:
  - `host.py current` 가 stub 안내 출력 + exit 0
  - 기존 hook은 어댑터 미참조이므로 영향 없음 → 정상 동작
  - SKILL.md 변경 없음 (render-skills가 stub은 no-op)

**Step 10 — 핸드오프**
- `feature_list.json` F006: `status: "in-progress" → "review"`
- `/project:context-save "F006 multi-host scaffolding"` 로 체크포인트
- `/project:learn add` 로 다음 학습 후보 기록:
  - `architecture`: "agent_type 은 settings.json 이 아닌 host.json — Claude Code 스키마 격리"
  - `pattern`: "stub 어댑터는 차단 X, 안내 메시지 + exit 0 (Brain hook-failure-tolerance 일관성)"
  - `pitfall`: "SKILL.md 본문 직접 수정 금지 — .template 도입 전까지 기존 파일 보존"

### 인수 기준 매핑

| AC | 충족 단계 | 비고 |
|---|---|---|
| **AC1** settings.json에 agent_type 필드 추가 | Step 1 | **결정 사항: settings.json 대신 `.claude/host.json` 으로 변경** (ADR 결정 1 참조). feature_list.json 의 AC 표기는 "settings에 agent_type" 의 정신을 host.json 에서 충족. |
| **AC2** 호스트별 커맨드 호출 어댑터 (OpenClaw tool mapping) | Step 2~5 | base.py 의 `tool_name()` + `command_invocation()` + claude-code 어댑터 + stub 2개 |
| **AC3** 호스트별 SKILL.md 생성 로직 | Step 5, 7 | host.py `render-skills` 서브커맨드 + 토큰 카탈로그 |
| **AC4** 기본값 claude-code 유지, 다른 값 선택 시 안내 | Step 1, 4, 5 | host.json 기본값 + stub 안내 메시지 + 우선순위 fallback |

### 테스트 방법

**무회귀 (claude-code 기본값) 테스트**:

```
# (1) host.json 없이 시작
[ -f .claude/host.json ] || echo "host.json absent → fallback to claude-code"
python3 .claude/bin/host.py current
# 기대: "claude-code"

# (2) 기존 hook 동작 확인 — 안전한 명령
echo "test" > /tmp/_t.txt && rm /tmp/_t.txt
# 기대: 차단 없음

# (3) 기존 명령 동작 확인
ls .claude/commands/handoff.md
# 기대: 정상 출력
```

**호스트 전환 안내 테스트**:

```
# (4) 환경변수로 openclaw 전환
HARNESS_AGENT_TYPE=openclaw python3 .claude/bin/host.py info
# 기대: "⚠️  OpenClaw 어댑터는 현재 stub..." 안내 메시지 + exit 0

# (5) host.json 으로 codex 전환
python3 .claude/bin/host.py set codex
python3 .claude/bin/host.py current
# 기대: "codex (stub)"

# (6) 환경변수가 host.json 보다 우선
HARNESS_AGENT_TYPE=claude-code python3 .claude/bin/host.py current
# 기대: "claude-code"

# (7) 복원
python3 .claude/bin/host.py set claude-code
```

**SKILL 렌더 테스트**:

```
# (8) 임시 템플릿 1개 생성
mkdir -p .claude/skills/_render_test
cat > .claude/skills/_render_test/SKILL.md.template <<'EOF'
도구: {{HOST.TOOL.bash}}
커맨드: {{HOST.CMD.handoff}}
환경변수: {{HOST.ENV.project_dir}}
호스트: {{HOST.NAME}}
EOF

# (9) 렌더
python3 .claude/bin/host.py render-skills
cat .claude/skills/_render_test/SKILL.md
# 기대 (claude-code):
#   도구: Bash
#   커맨드: /project:handoff
#   환경변수: $CLAUDE_PROJECT_DIR
#   호스트: claude-code

# (10) stub 호스트로 전환 후 재렌더 → 변경 없음
python3 .claude/bin/host.py set openclaw
python3 .claude/bin/host.py render-skills
diff <(cat .claude/skills/_render_test/SKILL.md) <(echo -e "도구: Bash\n커맨드: /project:handoff\n환경변수: \$CLAUDE_PROJECT_DIR\n호스트: claude-code")
# 기대: 차이 없음 (stub은 SKILL.md 수정 안 함)

# (11) 정리
python3 .claude/bin/host.py set claude-code
rm -rf .claude/skills/_render_test
```

**모든 단계가 exit 0 으로 종료되는지** 확인 (호출자 차단 방지 원칙).

### 피해야 할 패턴

- ❌ `.claude/settings.json` 에 `agent_type` 키 추가 (Claude Code 스키마 오염)
- ❌ 기존 `.claude/skills/*/SKILL.md` 본문에 `{{HOST.…}}` 토큰 직접 삽입 (마이그레이션은 후속 Feature)
- ❌ 어댑터 stub 이 어떤 형태로든 exit code 0이 아닌 값으로 종료 (Brain hook-failure-tolerance 위배)
- ❌ Python 패키지 추가 (Pydantic·click·toml 등 모두 금지 — argparse + json + pathlib + re 만)
- ❌ 호스트 전환 시 사용자 확인 없이 SKILL.md 를 무차별 덮어쓰기 (`.template` 가 있는 항목만 렌더)
- ❌ hook 스크립트 안에서 어댑터 임포트 (Phase 3 단계에서는 hook 추상화 X — 후속에서)

---

*작성: architect 에이전트 | 날짜: 2026-04-27 | 상태: Accepted*
