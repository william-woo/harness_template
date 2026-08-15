# 측정 07 — 무인 사이클: 결정론 supervisor 드라이버 (cycle_driver, F025)

- **일시**: 2026-08-05
- **환경**: OpenCode 1.16.2 + Ollama (172.16.10.217, RTX 4500) — qwen2.5 14B(생성)/32B(판정)
- **목적**: supervisor(핸드오프·grader·재시도·북키핑)를 상위 호스트가 아니라 **로컬 결정론
  코드**가 담당할 수 있는지 검증 (ADR-018) — 과제: F001 palindrome checker
- **방법**: 새 샌드박스에 템플릿 배포 → `cycle_driver.py run F001` 1회 실행 후 무개입 관찰
  (실패 시 원인 수정 → 재실행 반복)

## 실행 이력 (3 run — 각 실패가 드라이버를 강화)

| Run | 결과 | 원인·조치 |
|---|---|---|
| 1 | exit 1 (정직 중단) | OpenCode 부트스트랩 행 ×2 (외부 플러그인 해석 — 네트워크 구간). → **`--pure` 기본값** + 재시도 백오프 10초 |
| 2 | exit 2 (정직 에스컬레이션) | dev(14B)가 module-level assert + 미정의 함수 호출 혼합 패턴 생성, 전체 재작성 3회도 동일 패턴 반복 → 임계 도달. 상위 호스트가 1분 진단·수정 (하이브리드 인계 규약 작동) |
| 2-재개 | exit 2 (버그 발견) | **드라이버 설계 버그**: 재개 시 무조건 ①구현 호출 → 14B 가 수정된 파일을 다시 훼손. → **grade-before-generate** (grader 선통과 시 생성 생략 — 멱등 재개) |
| 3 | **exit 0 ✅ 완주** | grader 선통과 → reviewer(32B) pass → qa(32B) pass → passes:true + git 커밋 — 전 과정 드라이버 무인 수행 |

## verify-loop 최종 트레이스 (7 기록)

```
#1~#4 test → revision ×3 + 에스컬레이션 (run 2)
#5 test(deterministic) → pass
#6 reviewer(judge) → pass — "is_palindrome … ignoring case and spaces, accurate asserts, exit 0"
#7 qa(judge) → pass — "ran successfully … printed PASS"
```

주목: run 3 의 reviewer/qa(32B)는 **구체 소견을 담아** 스스로 기록했다 (placeholder 아님) —
드라이버의 judge 템플릿(bash-only + 검증 절차 명시)이 판정 품질을 끌어올렸다.

## 결론

1. **supervisor 로컬화 성립** — 단, "로컬 LLM supervisor"가 아니라 **로컬 결정론 드라이버**로.
   LLM 흐름 조율(G5)은 측정 05 에서 반증된 경로다. 상태 기계는 코드가, 생성·판정만 LLM 이.
2. **에스컬레이션 경계가 실제로 가치를 냈다** — dev(14B)의 패턴 혼합 실패를 3회 만에 유계
   차단하고 상위 호스트에 넘겼다. 상위 호스트 개입은 1분 (진단+1파일 수정).
3. **grade-before-generate** 는 무인 루프의 필수 불변식 — 결정론 게이트가 통과하는 산출물에
   생성 모델을 다시 대면 회귀를 만든다 (재개 멱등성).
4. 신뢰 경계 요약: 로컬 무인 구간 = 흐름·채점·북키핑(코드) + 생성(14B) + 판정(32B).
   상위 호스트 구간 = 에스컬레이션 처리만.

## 드라이버 강화분 (이번 측정 반영)

- `--pure` 기본값 (CYCLE_OC_PURE=0 으로 해제) — 부트스트랩 네트워크 구간 제거
- timeout 재시도 사이 10초 백오프
- grade-before-generate (멱등 재개)

## 재현

```bash
# 템플릿 배포 후
python3 .claude/bin/cycle_driver.py run F001 \
    --test-cmd "python3 test_palindrome.py" --expect PASS \
    --files palindrome.py,test_palindrome.py
# exit 0=완주 / 1=인프라 실패 / 2=에스컬레이션(상위 호스트 인계) / 3=judge NEEDS REVISION
```
