# PoC 측정 02 — 도구 호출 (OpenCode + Ollama)

- **측정일**: 2026-06-06
- **환경**: OpenCode 1.16.2 (npm 전역) + Ollama 0.30.5 (172.16.10.217, RTX 4500)
- **모델**: ollama/qwen2.5:14b-instruct-q8_0
- **연결**: OpenCode provider `ollama` → OpenAI 호환 endpoint (`/v1`)

## 측정 항목 + 결과

| # | 측정 | 결과 | 판정 |
|---|---|---|---|
| 1 | OpenCode ↔ Ollama 연결 | `opencode models` 에 ollama/* 인식, `build · qwen2.5:14b` 응답 | ✅ PASS |
| 2 | 모델 도구 호출 (Write) | `← Write result.txt` → "Wrote file successfully" → result.txt="DONE" | ✅ PASS |
| 3 | OpenCode 권한 시스템 | `/tmp/*` (작업 디렉토리 밖) Write → `external_directory; auto-rejecting` | ✅ 작동 (의도) |

## 핵심 발견

1. **로컬 14B 모델이 OpenCode 도구 호출을 한다** — qwen2.5:14b-instruct-q8_0 가 OpenCode 의 tool-use 형식(Write tool)을 따라 실제 파일 생성. d-2 의 두 번째 핵심 불확실성(도구 호출) 해소.

2. **OpenCode 자체 권한 시스템이 우리 autonomous 정책과 동형** — OpenCode 가 작업 디렉토리 밖(`/tmp/*`) 쓰기를 `external_directory` 로 auto-reject. 우리 하네스 규칙 #3-B(작업 디렉토리 밖 차단)와 같은 철학이 OpenCode 에 내장됨 → 어댑터 설계 시 정책 매핑이 자연스러움.

3. **모델의 절대경로 습관** — 모델이 처음엔 `/tmp/` 절대경로로 쓰려다 거부됨. "상대경로 사용" 명시하면 프로젝트 내 쓰기 성공. → 스킬/프롬프트에 "프로젝트 상대경로 우선" 가이드 필요 (d-2 어댑터 보강 포인트).

## 측정 01+02 종합 — d-2 핵심 불확실성 2개 해소

| 불확실성 | 측정 | 결과 |
|---|---|---|
| 로컬 모델이 지시를 따르는가 | 01 | ✅ PASS (Surgical/status/권한/컨텍스트) |
| 로컬 모델이 도구를 호출하는가 | 02 | ✅ PASS (OpenCode Write tool) |
| 멀티 에이전트 spawn 되는가 | 03 (미측정) | ⬜ Task/subagent 측정 필요 |
| 긴 워크플로우 E2E | 04 (미측정) | ⬜ orchestrate 흐름 |

## 환경 재현 (init 통합)

`bash .claude/bin/opencode-setup.sh` 가 위 환경을 자동 구축:
- OpenCode 전역 설치 (npm, autonomous #3-B 승인)
- `~/.config/opencode/opencode.jsonc` 에 ollama provider 설정
- `opencode models` 로 인식 검증

## 다음 단계

1. 측정 03 — 멀티 에이전트 spawn (OpenCode `agent` / Task 상당 기능)
2. 측정 04 — orchestrate 흐름 E2E (researcher→developer 핸드오프)
3. 결과 종합 → d-2 어댑터(`host_adapters/opencode.py`) + 스킬 보강(상대경로 가이드) 설계

## 잠정 결론

**도구 호출 PASS.** 로컬 14B 모델이 OpenCode 를 통해 파일 도구를 호출하고, OpenCode 권한 시스템이 우리 autonomous 경계와 동형으로 작동. d-2 의 1·2번 핵심 불확실성 해소 — 멀티 에이전트·E2E 가 남은 측정.
