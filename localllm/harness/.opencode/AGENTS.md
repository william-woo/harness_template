# AGENTS.md — OpenCode 프로젝트 컨텍스트 (localllm 변형, d-2 · loope 계보)

> 이 파일은 **OpenCode**(오픈소스 agent framework)가 읽는 프로젝트 컨텍스트입니다.
> Claude Code 의 `CLAUDE.md` 에 상당합니다. localllm 변형은 Claude Code 가 아니라
> **OpenCode + 로컬 LLM(Ollama)** 으로 하네스를 구동합니다 (F015 / ADR-009).
> **F023 (ADR-017)**: 구성이 **claude.loope 계보**로 승격 — 검증 루프(verify-loop)·
> 세션 검색(session-search)·PM 사이클(product-cycle)·hill-climb 를 모두 보유합니다.
>
> 하네스의 전체 규칙·에이전트·커맨드는 `CLAUDE.md` 와 `.claude/` 를 그대로 따릅니다.
> 이 파일은 **OpenCode 호스트에서 달라지는 점**만 명시합니다.

## OpenCode 호스트 4대 차이 (Claude Code 대비)

OpenCode 에이전트 정의는 `.opencode/agent/*.md`, 커맨드는 `.opencode/commands/*.md` 에
있습니다 — 각각 `.claude/agents/`, `.claude/commands/` 를 render-agents / render-commands 로
변환한 **산출물**입니다 (수동 편집 금지 — 소스를 고치고 재렌더). 다음 4가지를 반드시 지키세요:

1. **상대경로 우선** — 로컬 모델은 `/home/...` 절대경로를 임의 생성하는 습관이 있습니다
   (PoC 측정 02). 파일 읽기·쓰기는 **프로젝트 루트 기준 상대경로**를 사용하세요.
   OpenCode 는 cwd 기반이므로 현재 작업 디렉토리가 곧 프로젝트 루트입니다.
   (Claude Code 의 `$CLAUDE_PROJECT_DIR` 상당 환경변수 없음 → `$PWD` 사용)

2. **파일 생성 = `edit`** — OpenCode 에는 `write` 도구가 없습니다. 신규 파일 생성도
   `edit` 도구로 합니다 (측정 02 에서 edit 의 신규파일 생성 PASS 확인).

3. **다중 편집 = `edit` 다회 호출** — OpenCode 에는 `multiedit` 도구가 없습니다.
   여러 곳을 고칠 때는 `edit` 를 여러 번 호출하세요 (한 번에 하나씩, 안전).

4. **하위 에이전트 = `task` 도구** — Claude Code 의 `Agent`(구 `Task`) 도구는 OpenCode 에서
   `task` 입니다. `task` 로 `.opencode/agent/<name>.md` 의 subagent 를 spawn 합니다.
   단, **멀티스텝 값 전달(G4)은 32B Q4 에서도 실측 실패**(측정 03b·05) — 단계 간 인계는
   `.claude/state/` **파일 핸드오프**로, 수치 계산은 **결정론 도구**(wc/lint/verify_loop)로.

5. **얕은 경로 — 선행 슬래시 금지** (측정 05) — 프롬프트에 숨김 디렉토리 경로
   (`.claude/state/...`)를 직접 쓰면 로컬 모델이 선행 `/` 를 붙여 external_directory
   권한 프롬프트에 걸리고 headless 실행이 **행**합니다. 에이전트에 넘기는 파일은
   프로젝트 루트 근처 얕은 상대경로로. (bash 명령 인자는 무관 — cwd 기준 실행.)

6. **재작업 = 전체 파일 재작성** (측정 06) — 로컬 모델의 정밀 편집(edit oldString)은
   불일치로 자주 실패합니다. 수정을 지시할 땐 **파일 전체 내용을 제시하고 통째로
   재작성**하게 하세요 (fizzbuzz 통합 테스트: 정밀 편집 실패 → 전체 재작성 성공).

7. **판정 역할의 파일 읽기 = bash `cat`** (측정 06) — read 도구는 로컬 모델이 경로를
   날조(`/workspace/...` 등)해 권한 거부됩니다. reviewer/qa 지시문에 "ONLY the bash
   tool" + `cat <파일>` 을 명시하면 안정적으로 동작합니다.

8. **산출물은 파일시스템·테스트로 검증** (측정 08) — 스크립트에서 opencode 를 호출할 때는
   **`PWD` 환경변수를 작업 디렉토리로 설정**하라. 호스트는 상대경로를 `cwd` 가 아니라 `PWD`
   기준으로 해석하므로, `subprocess(cwd=...)` 만 주면 산출 파일이 **상위 디렉토리에** 떨어진다
   (실측 — 초기엔 이를 환각으로 오진했다). 그 위에서 파일 존재·형식(리터럴 `\n` 여부)·테스트
   기대출력을 검증하라. 파일 작업은 `write` 도구에 절대경로를 날조하지 않는 **`--agent` 모드** 권장.

9. **bash 도구는 `command` + `description` 두 인자 필수** (측정 05·08) — description 을 빼면
   스키마 에러로 호출이 무산된다. bash 사용을 지시할 때 이 점을 함께 알려라.

## 역할 → 모델 매핑 (opencode.json 이 SSOT)

**현재 설정** (측정 08 라운드 14 이후 — 생성형도 32B 로 승급):

| 역할 | 모델 |
|---|---|
| architect · designer · developer · planner · product-manager · qa · researcher · reviewer | `qwen2.5:32b-instruct-q4_K_M` |
| gatekeeper | `qwen2.5:14b-instruct-q8_0` |
| (기본값) | `qwen2.5:14b-instruct-q8_0` |

| 모델 | 크기 | 근거 |
|---|---|---|
| `qwen2.5:32b-instruct-q4_K_M` | 19.9GB | 측정 08 — 14B 는 다중파일·AC 준수 과제에서 3라운드 연속 수렴 실패, 32B 전환 즉시 exit 0 완주 |
| `qwen2.5:14b-instruct-q8_0` | 15.7GB | 측정 02·04 — 단일파일·단순 과제에는 충분 (현재 gatekeeper 만 사용) |

> **비교 실험용**: `gemma4:12b` 는 측정 05(G4 오케스트레이션)에서만 사용했고 무동작이었다.

### ⚠️ 모델은 **전역 설정**에 등재돼야 해석된다 (측정 08 발견 2)

OpenCode 1.16.2 는 프로젝트 `opencode.json` 의 `provider.*.models` 를 **모델 해석에 반영하지
않는다**. 역할 모델이 `~/.config/opencode/opencode.json*` 에 없으면 **`--agent` 실행 전체가**
`UnknownError` 로 실패한다 (레지스트리 로드 시 전 역할 모델을 해석하므로).

```bash
bash .claude/bin/opencode-setup.sh            # 누락 모델을 전역 설정에 자동 병합
python3 .claude/bin/cycle_driver.py self      # 역할 모델 해석 가능 여부 프리플라이트
```

> Ollama 서버: 전역 설정의 provider `baseURL` 로 지정 (원격 서버 사용 가능).
## Loop 2 × 로컬 LLM — 결정론 grader 우선 (F023 핵심 규율)

verify-loop 의 **결정론 grader 우선** 원칙이 로컬 LLM 의 검증 약점을 구조적으로 보완합니다:

```bash
# 1) 값싼 결정론 게이트 먼저 (stdlib 스크립트 — 모델 무관 100% 신뢰)
python3 .claude/bin/lint.py check --strict
python3 .claude/bin/verify_loop.py record <F> --grader lint --verdict pass
# 2) judge 판정은 32B 로 (reviewer/qa — opencode.json 이 자동 매핑)
opencode run --agent reviewer "F0XX 구현을 리뷰하고 verify_loop record 로 판정을 남겨줘"
# 3) 재시도 3회 초과 시 자동 에스컬레이션 (verify_loop.py status <F> 로 확인)
```

> **공허 통과(vacuous pass) 주의** (측정 06): 결정론 grader 는 exit code 만 보지 말고
> **기대 출력**(예: `PASS` 문자열)까지 확인하라 — 로컬 모델이 테스트 함수를 정의만 하고
> 호출하지 않으면 exit 0 으로 공허 통과한다.

## 환경 설정 · 렌더링

```bash
bash .claude/bin/opencode-setup.sh           # OpenCode 설치 + Ollama provider 설정 (#3-B 승인)
python3 .claude/bin/host.py render-agents    # .claude/agents/  → .opencode/agent/
python3 .claude/bin/host.py render-commands  # .claude/commands/ → .opencode/commands/ (F023)
opencode agent list                          # 인식 확인
```

## 무인 사이클 — cycle_driver (F025, supervisor 로컬화)

supervisor(단계 순서·grader·재시도·북키핑)는 LLM 이 아니라 **결정론 드라이버**가 담당한다
(측정 05: LLM 흐름 조율은 32B 도 실패 → ADR-018). 사이클 전체가 로컬에서 무인 실행:

```bash
python3 .claude/bin/cycle_driver.py run F001 \
    --test-cmd "python3 test_x.py" --expect PASS --files x.py,test_x.py
# exit 0=완주(passes:true)  exit 2=에스컬레이션(상위 호스트 인계)  exit 3=judge NEEDS REVISION
python3 .claude/bin/cycle_driver.py self    # 의존성 점검
```

드라이버가 develop(14B)→grade(결정론)→재작업(전체 재작성, 유계)→review/qa(32B, 기록 검증)
→bookkeep(passes·커밋) 을 순서대로 실행한다. 에스컬레이션 시 정직하게 멈춘다.

## 대표 사용 패턴

```bash
# 단일 역할 직접 호출 (생성형 — 14B 자동)
opencode run --agent developer "F001 로그인 API 를 feature_list 기준으로 구현해줘"
# 판정 역할 (32B 자동)
opencode run --agent reviewer "방금 구현된 F001 을 리뷰하고 verify-loop 에 기록해줘"
# 커스텀 커맨드 (render-commands 산출물)
opencode run --command status
opencode run --command verify-loop "F001"
```

## 모델 등급 (요약)

- **생성형 단일 역할** (developer/architect/designer/planner): 14B 로 **즉시 가능**
- **검증형·판정** (reviewer/qa) 및 **멀티스텝 오케스트레이션**: **32B+** — 14B 는 측정 03b·04 에서 한계

→ 상세: docs/poc/MODEL-GRADES.md, docs/poc/SUMMARY.md
