# d-2 로컬 LLM 모델 등급 — 작업별 적합 모델 (F015 실측 기반)

> OpenCode + Ollama 환경에서 하네스 역할별로 어느 크기의 로컬 모델이 필요한가.
> **추측이 아니라 PoC 5회 실측**(docs/poc/measurements/) 기반. 측정 환경:
> OpenCode 1.16.2 + Ollama (172.16.10.217, RTX 4500 24GB).

## 핵심 결론 (한 줄)

**단일 역할은 14B 로 지금 작동한다. 멀티스텝 오케스트레이션은 32B+ 필요.**

d-2 에서 "로컬 LLM 으로 하네스가 되는가?"의 답은 **모델 크기에 좌우되는 작업 등급**에 달려 있다.

---

## 작업 등급 매트릭스

| 작업 등급 | 대표 작업 | 14B (qwen2.5:14b-q8) | 32B+ 권장 | 측정 근거 |
|---|---|:-:|:-:|---|
| **G1 — 지시 따르기** | Surgical 편집, status 갱신, 권한 경계 준수, 컨텍스트 유지 | ✅ PASS | ✅ | 측정 01 |
| **G2 — 단일 도구 호출** | read/edit/bash 1회 호출로 파일 생성·수정 | ✅ PASS | ✅ | 측정 02 |
| **G3 — subagent spawn (메커니즘)** | Task 로 하위 에이전트 1개 띄우기 | ✅ PASS | ✅ | 측정 03 |
| **G4 — 멀티스텝 값 전달** | subagent 결과를 받아 다음 단계에 치환·전달 (2-홉 추론) | ❌ **FAIL** | ✅ | 측정 03b |
| **G5 — 이종 에이전트 오케스트레이션** | researcher→designer→developer→reviewer 핸드오프 (orchestrate) | ❌ (G4 의존) | ✅ | G4 에서 파생 추정 |

> G4 의 대표 실패: subagent 가 라인 수를 세어 반환했으나, 14B 가 결과를 받아
> 최종 파일에 `{{line_count}}` **플레이스홀더를 literal 로 기록**(실제 값 미치환).
> spawn·도구호출은 됐으나 "결과 → 변수 치환" 2-홉 추론에서 신뢰도 급락. → docs/poc/measurements/03-multi-agent.md

---

## 하네스 역할 → 최소 모델 등급

우리 7 에이전트를 작업 등급으로 분류하면:

| 에이전트 | 주 작업 등급 | 14B 로 충분? | 비고 |
|---|---|:-:|---|
| developer | G1·G2 (구현+편집) | ✅ | 단일 feature 구현은 14B 로 가능 |
| reviewer | G1 (읽고 판정) | ✅ | 코드 읽기+판정은 단일 추론 |
| qa | G1·G2 (검증+마킹) | ✅ | acceptance 체크는 단일 역할 |
| architect | G1 (설계 문서 작성) | ✅ | ADR 작성은 생성 작업 |
| planner | G1 (feature 분해) | ✅ | 단, 복잡 분해는 품질 편차 |
| designer | G1 (토큰 추천) | ✅ | 단일 생성 |
| **orchestrate (커맨드)** | **G5** | ❌ | **32B+ 또는 흐름 단순화 필요** |

→ **단일 역할 에이전트(developer/reviewer/qa/...)는 14B 로 d-2 즉시 가능.**
→ **orchestrate 같은 이종 핸드오프는 14B 한계** — 32B+ 또는 단일 스텝 분해.

---

## 24GB GPU (RTX 4500) 권장 라인업

| 용도 | 모델 | 적재 | 비고 |
|---|---|---|---|
| 단일 역할 (G1~G3) | qwen2.5:14b-instruct-q8_0 | ~16GB | **실측 PASS** — 현재 기본 모델 |
| 멀티스텝 (G4~G5) | Devstral Small 2 / Qwen3 32B 계열 Q4 | ~18-20GB | 24GB 에 Q4 적재 가능 (검색 추천 라인업, 미실측) |
| 경량 비교 | gemma:12b 계열 | ~10GB | 측정 비교군 |

> 32B Q4 는 RTX 4500 24GB 에 적재 가능하나 **본 PoC 에서 직접 측정하지 않음** — 추정.
> 멀티스텝이 꼭 필요하면 (a) 32B+ 도입 또는 (b) orchestrate 흐름을 단일 스텝으로 분해.

---

## 운영 가이드 (모델 등급 분기)

```bash
# 단일 역할 — 14B 로 충분 (비용·속도 최적)
opencode run --model ollama/qwen2.5:14b-instruct-q8_0 "developer: F003 구현"

# 멀티스텝 오케스트레이션 — 32B+ 권장 (14B 는 G4 실패)
opencode run --model ollama/<32b-model> "orchestrate: 신규 API 조사부터 QA까지"
```

**판단 규칙**: 요청이 단일 역할이면 14B, 여러 역할 핸드오프(G4/G5)면 32B+ 또는 단순화.

---

## 비용·보안 목적 달성도 (재확인)

| 목적 | 달성 | 단서 |
|---|---|---|
| 비용 절감 | ✅ | 로컬 추론 — API 비용 0 (단일 역할 즉시 가능) |
| 보안 (오프라인) | ✅ | 내부망 Ollama — 외부 전송 0 |
| 한계 | ⚠️ | 복잡 오케스트레이션(G4/G5)은 32B+ 필요 |

→ 자세한 측정: docs/poc/SUMMARY.md, docs/poc/measurements/03-multi-agent.md
