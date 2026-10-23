# PoC 측정 03 — 멀티 에이전트 / 에이전트 포맷

- **측정일**: 2026-06-07
- **환경**: OpenCode 1.16.2 + Ollama (qwen2.5:14b-instruct-q8_0)

## 측정 항목 + 결과

| # | 측정 | 결과 | 판정 |
|---|---|---|---|
| 1 | OpenCode 빌트인 agent | build/plan/compaction/summary/title (primary), explore/general (subagent) | — |
| 2 | 우리 `.claude/agents/*.md` 인식 | researcher/designer/gatekeeper/planner/architect/reviewer/developer **전부 미인식** | ❌ FAIL (예상됨) |
| 3 | 로컬 모델 subagent spawn (general) | `• Count Lines General Agent → ✓` spawn 성공 | ✅ PASS (메커니즘) |
| 3b | subagent 멀티스텝 값 전달 | lines.txt = `{{line_count}}` (플레이스홀더 literal — 실제 값 3 미치환) | ❌ **FAIL (14B 한계)** |

## 핵심 발견 — d-2 어댑터의 주 작업이 드러남

**OpenCode 는 우리 `.claude/agents/*.md` (Claude Code 포맷) 를 인식하지 못한다.**

- OpenCode 의 agent 정의는 별도 포맷 (`.opencode/agent/*.md` 또는 `opencode.json` 의 `agent` 키)
- 우리 7 에이전트(planner/architect/developer/reviewer/qa/designer/researcher/gatekeeper)는 OpenCode 에 그대로는 안 보임
- 즉 **d-2 어댑터(`host_adapters/opencode.py`)의 핵심 작업 = 에이전트 정의 포맷 변환**:
  - `.claude/agents/<name>.md` (frontmatter: name/description/model/tools)
  - → OpenCode agent 포맷 (`.opencode/agent/<name>.md` 또는 opencode.json)
  - 도구명 매핑은 이미 F006 `host_adapters/base.py` 의 토큰 카탈로그 패턴으로 처리 가능

## 모델-무관 vs 모델-의존 vs 호스트-의존 (3분류로 정밀화)

PoC 측정으로 기존 2분류(모델무관/모델의존)가 3분류로 정밀화됨:

| 분류 | 항목 | 로컬 LLM(OpenCode) |
|---|---|---|
| **모델 무관** | Python 헬퍼 7종, 훅, git, 거버넌스 파일 | ✅ 그대로 작동 (측정 01 컨텍스트로 확인) |
| **모델 의존** | 지시 따르기, 도구 호출 | ✅ qwen2.5:14b PASS (측정 01, 02) |
| **호스트 의존** | 에이전트 정의, 커맨드, 스킬 로딩, subagent spawn | ⚠️ **포맷 변환 필요** (측정 03 — Claude Code ≠ OpenCode 포맷) |

→ d-2 어댑터의 본질 = **"호스트 의존" 층의 Claude Code → OpenCode 포맷 변환**. 모델 무관·모델 의존 층은 이미 통과.

## d-2 어댑터 설계 방향 (측정 기반)

`host_adapters/opencode.py` 가 해야 할 일:
1. `.claude/agents/*.md` → `.opencode/agent/*.md` 변환 (frontmatter 포맷 매핑)
2. `.claude/commands/*.md` (슬래시 커맨드) → OpenCode 커맨드 메커니즘 (또는 opencode run 프롬프트)
3. `.claude/skills/SKILL.md` → OpenCode 스킬 로딩 방식
4. 도구명 매핑 (Bash/Edit/Read → OpenCode tool 이름) — base.py 토큰 카탈로그 재사용
5. settings.json hooks → OpenCode plugin/hook 메커니즘
6. 모델 의존 보강: "상대경로 우선" 가이드 (측정 02 발견)

모델-무관 코어(헬퍼/훅/git)는 변환 불필요 — 그대로 복사.

## 측정 03b 발견 — 14B 의 멀티스텝 한계 (가장 값진 발견)

subagent spawn 자체는 작동했으나(`✓ Count Lines General Agent`), 결과 파일에
`{{line_count}}` 플레이스홀더가 **literal 로** 기록됨. 즉 14B 모델이:
- subagent 를 spawn 함 ✅
- 도구를 호출함 ✅
- 그러나 **subagent 결과를 받아 변수를 치환하는 멀티스텝 추론에서 실패** ❌

이는 모델 크기 한계다. 클라우드 모델(또는 32B+)은 이 멀티스텝 값 전달을 안정적으로
하지만, 14B Q8 은 단일 스텝은 되어도 "subagent 결과 → 최종 산출물 치환" 같은
2-홉 추론에서 신뢰도가 급락한다.

### d-2 모델 등급별 적합도 (측정 기반 추정)

| 작업 | 14B (qwen2.5) | 32B+ 권장 |
|---|---|---|
| 지시 따르기 (단일) | ✅ | ✅ |
| 도구 호출 (단일) | ✅ | ✅ |
| subagent spawn (메커니즘) | ✅ | ✅ |
| **멀티스텝 오케스트레이션 (값 전달)** | ❌ | ✅ (Devstral/Qwen3.6 등) |

→ d-2 에서 **orchestrate 같은 복잡한 이종 에이전트 핸드오프는 14B 엔 무리**.
24GB GPU 라면 Devstral Small 2 / Qwen3.6 27B (검색 추천 라인업) 가 멀티스텝에 적합.
또는 오케스트레이션을 단순화(단일 스텝 분해)해서 14B 로도 가능하게.

## 잠정 결론

지시 따르기·도구 호출·subagent spawn 메커니즘은 14B 로컬 모델로 통과(측정 01·02·03).
**그러나 멀티스텝 오케스트레이션(subagent 결과 값 전달)은 14B 한계**(측정 03b) — 더 큰
모델 또는 흐름 단순화 필요. 남은 d-2 작업은 (a) 호스트 포맷 변환(에이전트/커맨드/스킬
어댑터) + (b) 모델 등급 선택(멀티스텝 필요 시 32B+). 측정 04(orchestrate E2E)는 우리
orchestrate.md 가 OpenCode 미인식(측정 03)이라 어댑터 전엔 직접 불가 — 멀티스텝 능력은
03b 가 대표 측정.
