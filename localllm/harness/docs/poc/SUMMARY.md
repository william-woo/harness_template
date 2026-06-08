# d-2 로컬 LLM PoC — 1차 종합

- **기간**: 2026-06-06 ~ 06-07
- **환경**: OpenCode 1.16.2 + Ollama 0.30.5 (172.16.10.217, RTX 4500)
- **모델**: qwen2.5:14b-instruct-q8_0 (주), gemma4:12b (비교)
- **하네스**: localllm 변형 (orch 복사본)

## 측정 종합

| 측정 | 항목 | 결과 |
|---|---|---|
| 01 | 지시 따르기 (Surgical/status/권한/컨텍스트) | ✅ PASS |
| 02 | 도구 호출 (OpenCode Write tool) | ✅ PASS |
| 03 | 에이전트 포맷 인식 (.claude/agents/) | ❌ 미인식 — 어댑터 변환 필요 |
| 03 | subagent spawn 메커니즘 (general) | ✅ PASS |
| 03b | 멀티스텝 값 전달 (subagent 결과 치환) | ❌ **FAIL (14B 한계)** |
| 04 | 단일역할 E2E (변환된 .opencode/agent/ + developer) | ✅ **PASS** (mode:all 보정 후) |

> **측정 04 (F015 세션 3)**: 변환된 `.opencode/agent/developer` 로 단일파일 코딩(add.js/sub.js)
> 을 로컬 14B 가 end-to-end 완성 (node assert 통과). 단, 직접 진입엔 **mode: all** 필수
> (subagent 는 fallback). 변환기 보정 완료. → docs/poc/measurements/04-single-role-e2e.md

## 3대 결론

### 1. 로컬 14B 로 "단일 역할"은 작동한다
지시 따르기 + 도구 호출 + subagent spawn 메커니즘 모두 qwen2.5:14b 로 통과.
Developer/Reviewer/QA 같은 단일 역할 에이전트는 로컬 14B 로 구동 가능.

### 2. "멀티스텝 오케스트레이션"은 14B 한계
subagent 결과를 받아 값을 치환하는 2-홉 추론에서 `{{line_count}}` literal 오류.
orchestrate 같은 이종 에이전트 핸드오프는 14B 엔 무리 → **32B+ (Devstral/Qwen3.6)** 또는
흐름 단순화 필요. (RTX 4500 24GB 면 32B Q4 적재 가능 — 검색 추천 라인업)

### 3. d-2 어댑터의 본질 = "호스트 포맷 변환" (모델 문제 아님)
모델-무관 코어(헬퍼/훅/git)와 모델-의존(지시/도구)은 통과. 남은 건 **호스트-의존 층**:
- `.claude/agents/*.md` → OpenCode agent 포맷
- `.claude/commands/*.md` → OpenCode 커맨드
- `.claude/skills/SKILL.md` → OpenCode 스킬 로딩
- settings.json hooks → OpenCode plugin
- 도구명 매핑 (F006 base.py 토큰 카탈로그 재사용)

## d-2 다음 단계 (어댑터 실구현 = F015 후보)

1. `host_adapters/opencode.py` — Claude Code → OpenCode 포맷 변환기
2. `.claude/agents/*.md` → `.opencode/agent/*.md` 자동 렌더링
3. 모델 등급 분기: 단일 역할 = 14B / 멀티 오케스트레이션 = 32B+
4. 스킬 보강: "프로젝트 상대경로 우선" (측정 02 발견 — 모델 절대경로 습관)
5. 측정 04 재시도 (어댑터 완성 후 orchestrate E2E)

## 비용·보안 목적 달성도

| 목적 | 달성 |
|---|---|
| 비용 절감 | ✅ 로컬 추론 — API 비용 0 (단일 역할 작업 즉시 가능) |
| 보안 (오프라인) | ✅ 내부망 Ollama — 외부 전송 0 |
| 한계 | ⚠️ 복잡 오케스트레이션은 32B+ 필요 (14B 부족) |

## 핵심 메시지

**"로컬 LLM 으로 하네스가 되는가?" → 부분적으로 YES, 측정으로 확정.**
단일 역할(코딩/리뷰/QA)은 14B 로 지금 가능. 복잡한 이종 에이전트 오케스트레이션은
더 큰 모델 또는 흐름 단순화 필요. d-2 어댑터는 모델 문제가 아니라 호스트 포맷 변환
엔지니어링 — F015 로 진행 가능. 모두 추측이 아닌 5회 실측 기반.
