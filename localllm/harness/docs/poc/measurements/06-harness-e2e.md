# 측정 06 — 하네스 통합 테스트 01: 로컬 LLM SDLC 풀사이클 (F001 fizzbuzz)

- **일시**: 2026-08-05
- **환경**: OpenCode 1.16.2 + Ollama (172.16.10.217, RTX 4500 24GB) — qwen2.5 14B(생성)/32B(판정)
- **구조**: **하이브리드** (측정 05 결론 적용) — 로컬 에이전트가 역할 수행, 상위 호스트
  (Claude Code)가 supervisor 로 핸드오프·grader 실행·북키핑 담당
- **시나리오**: localllm 템플릿을 다운스트림 샌드박스에 배포 → F001(fizzbuzz CLI) 시드 →
  하네스 SDLC 사이클 전체 (구현→검증루프→리뷰→QA→passes)

## 결과: ✅ 풀사이클 완주 — verify-loop 6 기록 / revision 2 / 에스컬레이션 0

| 단계 | 티어 | 결과 |
|---|---|---|
| developer 구현 | 14B (opencode.json 자동) | 파일 2개 생성 — 로직 정확, 단 **테스트 함수 미호출** |
| grader #1 (허술: exit code 만) | 결정론 | ⚠️ **공허 통과(vacuous pass)** — assert 미실행인데 exit 0 |
| grader 엄격화 (exit 0 + `PASS` 출력) | 결정론 | revision 기록 → 재작업 지시 |
| developer 재작업 1 (정밀 편집) | 14B | ❌ edit oldString 불일치 → 질문 이탈 (revision 2/3) |
| developer 재작업 2 (**전체 파일 재작성**) | 14B | ✅ 통과 — 엄격 grader PASS |
| reviewer 판정 1 (read 도구) | 32B | ❌ `/workspace/...` 경로 날조 → 권한 거부 |
| reviewer 판정 2 (**bash-only** 지시) | 32B | ✅ cat 으로 읽고 판정 → `record reviewer pass` |
| qa 인수 검증 (bash-only) | 32B | ✅ 테스트 실행 + 기준 확인 → `record qa pass` |
| supervisor 북키핑 | 상위 호스트 | passes:true / status:done / git 커밋 / 핸드오프 로그 |

## 신규 규율 3건 (AGENTS.md 반영)

1. **공허 통과 주의**: 결정론 grader 는 exit code 만이 아니라 **기대 출력**(`PASS` 등)까지
   확인한다 — 로컬 모델이 테스트를 정의만 하고 호출하지 않는 실패 모드가 실재.
2. **재작업 = 전체 파일 재작성** (AGENTS.md 규칙 6): 정밀 편집(edit oldString)은 불일치로
   실패·이탈. 파일 전체 내용을 제시하고 통째로 재작성시키는 편이 안정적.
3. **판정 역할 파일 접근 = bash `cat`** (AGENTS.md 규칙 7): read 도구는 경로 날조
   (`/workspace/` 등)로 거부됨. reviewer/qa 프롬프트에 "ONLY the bash tool" 명시.

## 운영 참고

- OpenCode 부트스트랩 간헐 행 (vcs init 직후 세션 미생성) 3회째 관찰 — **재시도로 항상 해소**.
  headless 파이프라인에선 timeout + 1회 재시도를 기본 패턴으로.
- 판정 프롬프트의 `--notes '<one short finding>'` 는 32B 가 placeholder 그대로 기록 —
  notes 는 supervisor 가 채우거나 구체 값 예시를 지시문에 넣을 것.

## 종합 판단

localllm 하네스는 **하이브리드 supervisor 패턴으로 실전 SDLC 사이클을 완주할 수 있다**.
로컬 티어의 역할: 생성(14B 초안) + 판정(32B judge, bash-only 규율 하). 결정론 grader 와
verify-loop 상태가 품질을 지탱하고, supervisor 는 핸드오프·북키핑·grader 정의만 담당한다.

---

## 재현 (2026-09-23 — F024 리뷰 MUST)

> **위 2026-08-05 세션의 산출물은 하나도 보존되지 않았다.** 샌드박스·프롬프트·verify-loop
> 상태가 전부 사라지고 이 문서만 남아 "완주"를 주장했다. 리뷰가 그 점을 MUST 로 지적했고
> (재현 artifact 0건), 그래서 같은 시나리오를 **다시 돌려 산출물을 리포에 남겼다**.

```bash
python3 docs/poc/repro/06-harness-e2e.py     # 샌드박스 생성 → 무인 실행 → artifact 보존
```

| 항목 | 원본 (2026-08-05) | 재현 (2026-09-23) |
|---|---|---|
| supervisor | **사람** — 핸드오프·grader 정의·북키핑 수동 | **`cycle_driver`** (F025) 가 결정론으로 수행 |
| 판정 티어 | 32B (qwen2.5:32b-instruct-q4_K_M) | 좌동 |
| 결과 | 완주 — verify-loop 6기록 / revision 2 | **완주 — 5기록 / revision 2 / judge `revision→pass→pass`** |
| 소요 | 미기록 | 240초 |
| 독립 검증 | 없음 | ground truth 재실행 `PASS`, 거짓 결과 0 |
| 산출물 | **없음** | `docs/poc/artifacts/06/` (verify-loop JSON · 드라이버 로그 · 생성 파일 · 요약) |

**재현은 원본을 복제하지 않는다.** supervisor 가 사람에서 드라이버로 바뀌었으므로, 확인된
것은 원본이 주장한 **결론**(로컬 티어가 SDLC 사이클을 완주한다)이 재현 가능하다는 것뿐이다.
원본이 관찰한 실패 양상(공허 통과·edit oldString 이탈·경로 날조)은 그 뒤 규율 3건과
grader 엄격화로 닫혔으므로 재현에서 같은 형태로 다시 나오지 않는다 — 나오지 않은 것이
곧 수정이 들었다는 증거는 아니고, 그 증거는 `tests/test_cycle_driver_gates.py` 가 진다.

### 재현이 잡은 결함 (F024 의 실제 소득)

첫 재현 시도는 **0초 만에 죽었다**:

```
NameError: name '_detect_host' is not defined   (cycle_driver.py:1024)
```

`cycle_driver.py run` 이 **3 사본 전부에서 즉시 크래시**하고 있었다 — 무인 드라이버가
아예 동작하지 않는 상태였다. 전제 확인 줄(`fix(F025·F026)`)이 부르는 이름이 실제 함수명
(`_driver_host`)과 달랐고, `localllm.aif` 에는 그 함수가 아예 없다. 같은 커밋이 추가한
게이트 테스트 12건은 순수 함수만 직접 불러서 **전부 통과했다**.

→ 호출 한 줄을 고치는 대신 `HelperResolutionTest` 를 넣었다. 모듈이 부르는 `_헬퍼()` 이름이
전부 정의돼 있는지 훑으므로 같은 실수를 어느 줄에서 하든 잡힌다.
**측정을 재현하려 한 행위 자체가 결함을 찾아냈다** — 문서만 남은 측정이 왜 위험한지의 실례다.
