# /project:host — 멀티 호스트 관리

현재 하네스의 `agent_type`을 조회하거나 변경한다.
기본값은 `claude-code`이며, `.claude/host.json`이 없어도 항상 정상 동작한다.

**HARD GATE: `.claude/settings.json` 은 절대 수정하지 않는다 (Claude Code 공식 스키마 유지).**

## 사용법

```
/project:host                         # 현재 호스트 정보 표시 (info)
/project:host set claude-code         # claude-code 로 설정
/project:host set openclaw            # openclaw 로 설정 (stub 안내 표시)
/project:host set codex               # codex 로 설정 (stub 안내 표시)
/project:host check                   # 무결성 점검 (무회귀 확인)
```

## 실행

```bash
# 현재 agent_type + 전체 정보 표시
python3 .claude/bin/host.py info

# 현재 agent_type만 출력 (1줄)
python3 .claude/bin/host.py current

# agent_type 변경 (host.json 업데이트 + render-skills 자동 호출)
python3 .claude/bin/host.py set claude-code
python3 .claude/bin/host.py set openclaw
python3 .claude/bin/host.py set codex

# 무결성 점검
python3 .claude/bin/host.py check
```

## 동작 원리

### 호스트 감지 우선순위

1. 환경변수 `HARNESS_AGENT_TYPE` (임시 오버라이드)
2. `.claude/host.json` 의 `agent_type` (프로젝트 영구 설정)
3. 기본값 `claude-code` (파일·환경변수 둘 다 없을 때)

```bash
# 환경변수로 임시 오버라이드 (host.json 변경 없음)
HARNESS_AGENT_TYPE=openclaw python3 .claude/bin/host.py current
```

### Stub 어댑터 안내

`openclaw`/`codex`로 설정하면 안내 메시지가 출력되지만 **하네스가 차단되지 않는다**.
기존 훅/커맨드는 어댑터 미참조이므로 그대로 동작한다.

> **[주의] render-skills 부작용**
> 비-claude-code 호스트(codex, openclaw)로 `/project:host set` 또는 `render-skills`를
> 실행할 때 **SKILL.md가 자동 갱신되지 않습니다** (현재 codex/openclaw는 stub).
> `.claude/skills/SKILL.md` 본문은 변경되지 않으며 이것은 **의도된 무회귀 동작**입니다.
> openai/ 변형 자동 재생성은 codex 어댑터가 실구현되는 후속 phase에서 가능합니다.

```
[WARN] OpenClaw 어댑터는 현재 stub입니다 (F006 Phase 3).
  - 도구명 매핑, 커맨드 표기, 훅 모델은 후속 Feature에서 구현됩니다.
  - 현재는 claude-code 환경에서만 모든 기능이 정상 동작합니다.
  - claude-code 로 전환: HARNESS_AGENT_TYPE=claude-code
    또는 /project:host set claude-code
```

### SKILL.md 렌더링 (`render-skills`)

`.claude/skills/**/*.template` 파일을 찾아 토큰을 호스트별 값으로 치환한다.

```bash
python3 .claude/bin/host.py render-skills
```

**토큰 카탈로그**:

| 토큰 | 의미 | claude-code 값 |
|---|---|---|
| `{{HOST.TOOL.bash}}` | 셸 도구명 | `Bash` |
| `{{HOST.TOOL.read}}` | 파일 읽기 | `Read` |
| `{{HOST.TOOL.write}}` | 파일 쓰기 | `Write` |
| `{{HOST.TOOL.edit}}` | 파일 편집 | `Edit` |
| `{{HOST.TOOL.multiedit}}` | 다중 편집 | `MultiEdit` |
| `{{HOST.TOOL.glob}}` | 파일 검색 | `Glob` |
| `{{HOST.TOOL.grep}}` | 텍스트 검색 | `Grep` |
| `{{HOST.CMD.<name>}}` | 커맨드 호출 | `/project:<name>` |
| `{{HOST.ENV.project_dir}}` | 프로젝트 루트 환경변수 | `$CLAUDE_PROJECT_DIR` |
| `{{HOST.NAME}}` | 호스트 이름 | `claude-code` |

**중요**: 현재 존재하는 `SKILL.md` 파일은 수정하지 않는다. `.template` 파일이 있는 항목만 렌더링한다.

## 출력 예시

```
agent_type : claude-code
source     : host.json
is_stub    : False
host.json  : .claude/host.json (존재)

도구 매핑:
  bash         → Bash
  read         → Read
  write        → Write
  edit         → Edit
  multiedit    → MultiEdit
  glob         → Glob
  grep         → Grep

커맨드 표기 예시:
  handoff      → /project:handoff
  plan-full    → /project:plan-full

프로젝트 루트 환경변수: $CLAUDE_PROJECT_DIR
```

## 파일 위치

| 파일 | 역할 |
|---|---|
| `.claude/host.json` | SSOT — agent_type 영구 저장 |
| `.claude/bin/host.py` | CLI 헬퍼 |
| `.claude/bin/host_adapters/base.py` | HostAdapter 추상 베이스 |
| `.claude/bin/host_adapters/claude_code.py` | 기본 어댑터 (실동작) |
| `.claude/bin/host_adapters/openclaw.py` | stub 어댑터 (스펙 미확정) |
| `.claude/bin/host_adapters/codex.py` | stub 어댑터 (스펙 미확정, ADR-001 §결정4) |

## 안전성

- `.claude/settings.json` 절대 수정 안 함 (Claude Code 공식 스키마 격리)
- 기존 `.claude/hooks/*.sh` 변경 없음 (어댑터는 SKILL/커맨드만 추상화)
- 모든 핸들러 `try/except` → 항상 exit 0 (hook-failure-tolerance 원칙)
- host.json 없거나 손상되어도 claude-code fallback
- stub 어댑터는 SKILL.md를 수정하지 않음

## 체크리스트

- [ ] `python3 .claude/bin/host.py current` → `claude-code` 출력
- [ ] `python3 .claude/bin/host.py check` → 무결성 통과
- [ ] `HARNESS_AGENT_TYPE=openclaw python3 .claude/bin/host.py current` → stub 안내 + exit 0
- [ ] host.json 삭제 후 `current` → fallback (에러 없음)
