# localllm — d-2 로컬 LLM PoC 하네스

`claude.gstack.auto.design.wiki.orch` 복사본. 로컬 LLM(Ollama)으로 하네스를
구동 가능한지 **측정**하는 PoC 샌드박스. (학습 #54, ADR-008 d-2 단계)

## 환경
- Ollama 서버: http://172.16.10.217:11434 (RTX 4500)
- 측정 모델: qwen2.5:14b-instruct-q8_0 (주), gemma4:12b (비교)
- 미래 host framework: OpenCode (provider-agnostic, OpenAI 호환)

## PoC 측정 항목
1. 지시 따르기 — 긴 SKILL.md / Karpathy 원칙 / 구조화 출력
2. 도구 호출 — Bash/Edit 형식 (OpenCode 연결 시)
3. 컨텍스트 한계 — CLAUDE.md + SKILL.md 적재
4. 멀티 에이전트 — 서브에이전트 spawn 가능 여부
5. 모델 비교 — qwen2.5:14b vs gemma4:12b

## 측정 결과
docs/poc/measurements/ 에 저장 (NN-제목.md)

## 정식화 조건
PoC 측정 완료 → d-2 어댑터(host_adapters/opencode.py) 방향 결정 →
정식 변형이 되면 LINT-MR 변형 목록에 등록 (현재는 실험 변형 — lint 격리 제외).

## 주의
- 이 변형은 PoC 실험용. LINT-MR 변형 목록 미등록 (격리 검사 제외).
- 측정은 read-only (모델 추론). 모델 pull / 서버 변경은 사용자 승인.
