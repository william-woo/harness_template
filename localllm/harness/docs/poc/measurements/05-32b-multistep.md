# 측정 05 — 32B 멀티스텝(G4) + loope 계보 E2E (F023)

- **일시**: 2026-08-05
- **환경**: OpenCode 1.16.2 + Ollama (172.16.10.217, RTX 4500 24GB)
- **모델**: qwen2.5:32b-instruct-q4_K_M (주), gemma4:12b (비교), qwen2.5:14b-instruct-q8_0 (sanity)
- **하네스**: localllm 변형 — **F023 loope 계보 승격 직후** (verify-loop/opencode.json/render-commands 포함)
- **배경**: 측정 03b 에서 14B 가 G4(서브에이전트 반환값 치환)에 실패. F015 는 "32B 확보 시
  측정 05 로 검증"을 보류 항목으로 남겼다. 32B 확보로 실측 실행.

## 결과 요약

| # | 시나리오 | 모델 | 결과 |
|---|---|---|---|
| 05-0 | sanity 왕복 (단답) | 14B | ✅ PASS (8초) |
| 05-1 | G4: 서브에이전트 라인수 → 치환 (`.claude/state/...` 경로) | 32B | ❌ **행(hang)** — 경로 훼손→권한 프롬프트 |
| 05-2 | G4: 동일 (프로젝트 루트 얕은 경로) | 32B | ❌ **값 오염** — LINES=3 (정답 17) |
| 05-3 | G4: 엄격 프로토콜 (`wc -l` + COUNT=N 형식 강제) | 32B | ❌ **미생성** — 서브에이전트 완료 후 오케스트레이터 혼란 |
| 05-4 | 렌더된 커맨드 파이프라인 (`--command lint report`) | 14B | ✅ 인식·도구구동 PASS (품질 한계 별도) |
| 05-5 | **reviewer 에이전트 × verify-loop 기록** (loope E2E) | 32B (opencode.json 자동 매핑) | ✅ **PASS** (21초) |
| 05-6 | G4 비교: thinking 모델 오케스트레이터 | gemma4:12b | ❌ **무동작** — task 도구 미개입, 출력 없음 |

## 발견 1 — G4 는 32B Q4 에서도 신뢰 불가 (3회 중 0회 클린 통과)

실패 모드가 14B 와 **다르다**:
- **14B (측정 03b)**: `{{line_count}}` placeholder literal 기록 — 치환 시도 자체가 없음
- **32B (이번)**: 치환 메커니즘은 개입하나 —
  1. **경로 훼손 → 권한 행**: 서브에이전트가 상대경로에 선행 `/` 를 붙여
     (`/.claude/state/m05/*`) OpenCode `external_directory` 권한 프롬프트 발생.
     headless `opencode run` 은 응답 수단이 없어 **무한 대기** (timeout 까지).
  2. **값 오염**: 파일은 생성됐으나 `LINES=3` (정답 17) — 실수(實數)를 썼지만 틀린 값.
  3. **인계 후 혼란**: 서브에이전트 정상 완료 후 오케스트레이터가 "이전 bash 시도에
     문제가 있었다"며 사용자에게 질문 — 파일 미생성.

**결론**: 로컬 모델의 "값을 문맥으로 전달"은 32B Q4 에서도 성립하지 않는다.
값 전달이 필요한 흐름은 **파일 핸드오프 + 결정론 도구**로 우회한다 (아래 규율).

## 발견 2 — loope 계보 E2E 는 성립한다 (05-5 ✅)

`opencode run --agent reviewer "...verify_loop.py record 로 판정 기록..."` 실행 시:
- opencode.json 의 역할별 모델 매핑이 자동 적용 (reviewer → 32B — 로그로 확인)
- render-agents 산출물의 **permission deny-list 가 실제로 차단** (허용 외 도구 1건 거부
  → 에이전트가 bash 로 적응) — 권한 경계 실동작
- `python3 .claude/bin/verify_loop.py record F901 --grader reviewer --verdict pass --notes ...`
  를 스스로 실행 → 상태 파일에 판정·노트 기록 확인

**단일 역할 에이전트가 loope 하네스 도구를 조작하는 흐름은 로컬 LLM 으로 실용 가능.**

## 발견 3 — 렌더된 커맨드 파이프라인 동작 (05-4 ✅, 품질 한계 병기)

- 미존재 커맨드 → 즉시 서버 에러 / 렌더된 30개 커맨드 → 정상 세션 시작 (인식 확인)
- `--command lint report`(14B): 커맨드 문서를 따라 `.claude/state/lint-last.json` 읽기
  시도 (실제 도구 구동) — 파이프라인 성립
- 14B 품질 한계: 언어 드리프트(일본어 혼입), 파일 부재 시 문서의 graceful 안내 대신
  사용자 질문으로 이탈 → **커맨드 실행도 판정·복합 커맨드는 32B 권장**

## 규율 갱신 (이번 측정이 낳은 하네스 규칙)

1. **얕은 경로 + 선행 슬래시 금지** (AGENTS.md 5번 규칙 신설):
   로컬 LLM 에이전트에 넘기는 파일 경로는 프로젝트 루트 근처 얕은 상대경로로.
   숨김 디렉토리(`.claude/...`)를 프롬프트에 직접 쓰면 선행 `/` 훼손 위험
   (스크립트 인자로 넘기는 bash 명령은 무관 — cwd 기준 실행).
2. **값 전달 금지, 파일 핸드오프**: orchestrate/product-cycle 의 단계 간 인계는
   `.claude/state/orch/`·`.claude/state/product-cycle/` **파일 규약**을 사용하고,
   수치·식별자 계산은 **결정론 도구**(wc/lint/verify_loop)로 — LLM 문맥 전달 배제.
3. **결정론 grader 우선** (ADR-017 결정 2 재확인): lint→verify_loop record 를 먼저,
   judge(32B) 판정은 그 다음.

## MODEL-GRADES 반영

- G4 행: "32B+ 권장" → **"32B Q4 실측 ❌ (3회 0클린) — 파일 핸드오프로 우회"**
- G5 행: 32B 추정 상향 불가 — **로컬 단독 오케스트레이션 비권장**, 상위 호스트(Claude Code)
  supervisor + 로컬 단일역할 하이브리드가 실용 경로
- 신규 행: **G-Loop (loope 도구 조작)**: 32B ✅ 실측 PASS (05-5)

## 재현 방법

```bash
cd src/harness_template/localllm/harness
# G4 (05-2/05-3 상당)
opencode run -m ollama/qwen2.5:32b-instruct-q4_K_M "Use the task tool to spawn ONE subagent ... LINES=<N>"
# loope E2E (05-5)
python3 .claude/bin/verify_loop.py start F901 --rubric code-review
opencode run --agent reviewer "... python3 .claude/bin/verify_loop.py record F901 --grader reviewer --verdict pass ..."
python3 .claude/bin/verify_loop.py status F901
```
