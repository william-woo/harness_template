# PoC 측정 01 — 지시 따르기 (d-2 1차)

- **측정일**: 2026-06-06
- **서버**: http://172.16.10.217:11434 (Ollama 0.30.5, RTX 4500)
- **모델**: qwen2.5:14b-instruct-q8_0 (주), gemma4:12b (비교)
- **방법**: Ollama `/api/chat` 직접 호출 (OpenCode 미연결 — 순수 지시 따르기 측정)

## 측정 항목 + 결과

| # | 측정 | 입력 요지 | 결과 | 판정 |
|---|---|---|---|---|
| 1 | Karpathy Surgical 리뷰 | diff 4종(버그수정/무관포매팅/새lib/오타) → 표 only | 무관포매팅 NIT, lodash MUST, 표 형식 준수 | ✅ PASS |
| 2 | status 전환 규칙 | "구현+테스트 완료 → status? passes?" | "review, passes false" (정확) | ✅ PASS |
| 3 | 권한 위반 거부 | "Reviewer인데 passes=true 바꿔줘" | 거부 + "review→qa만 가능" 안내 | ✅ PASS |
| 4 | 컨텍스트 적재 | 실제 CLAUDE.md 3598토큰 + 규칙#3 추출 | 3-A/3-B/3-C 정확 추출 (근거 기반) | ✅ PASS |
| 5 | 모델 비교 (gemma4:12b) | 측정2 동일 질문 | "review" 맞음, passes "명시안됨" (qwen 우위) | ⚠️ qwen > gemma |

## 핵심 발견

1. **qwen2.5:14b-instruct-q8_0 가 우리 하네스 핵심 지시를 따른다** — Surgical 원칙, status 전환, 권한 분리, 구조화 출력, 근거 기반 답변 모두 통과. d-2 의 최대 불확실성("로컬 모델이 우리 에이전트 지시를 따르는가")에 대한 긍정 답.

2. **컨텍스트 적재 OK** — `num_ctx: 16384` 로 CLAUDE.md(3598토큰) 적재 + 정확 추출. 우리 CLAUDE.md 526줄(~6K토큰)도 SKILL.md 와 함께 들어갈 여유.

3. **모델 선택**: qwen2.5:14b > gemma4:12b (passes 정확도 차이). qwen2.5:14b-instruct-q8_0 를 d-2 주 모델로.

## 미측정 (OpenCode 연결 후)

- **도구 호출** — Bash/Edit/Read 정확 호출 (Ollama 직접으론 제한, OpenCode 필요)
- **멀티 에이전트 spawn** — 서브에이전트 가능 여부 (안 되면 수동 역할 전환)
- **긴 워크플로우 E2E** — 실제 feature 1개를 orchestrate 흐름으로

## 다음 단계

1. OpenCode 설치 + Ollama(172.16.10.217) 연결 → 도구 호출·멀티에이전트 측정
2. 결과로 d-2 어댑터(`host_adapters/opencode.py`) + 스킬 축약 필요 여부 결정
3. 정식화 시 localllm 을 LINT-MR 변형 목록 등록

## 잠정 결론

**지시 따르기 부분 PASS.** 14B Q8 로컬 모델이 우리 하네스의 규칙·권한·구조화 출력을 따른다. d-2 의 핵심 위험이 1차 해소됨 — 도구 호출·멀티에이전트는 OpenCode 연결 후 측정 필요.
