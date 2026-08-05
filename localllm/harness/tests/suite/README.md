# 무인 테스트 스위트 (localllm — F026 / 측정 08)

`cycle_driver` 로 SDLC 사이클을 무인 실행하고 **독립 oracle** 로 결과를 재검증한다.
목적은 성공 확인이 아니라 **에러·정확도·hallucination·거짓 결과** 탐지다.

```bash
python3 tests/suite/run_suite.py                 # 10 시나리오 전체
python3 tests/suite/run_suite.py S01 S07         # 선택 실행
python3 tests/suite/run_suite.py --round 3       # 라운드 태깅
SUITE_SANDBOX=/tmp/sb SUITE_RESULTS=/tmp/res python3 tests/suite/run_suite.py
```

## oracle (드라이버 주장을 신뢰하지 않는다)

| oracle | 검사 | 탐지 |
|---|---|---|
| O1 | exit code ↔ 시나리오 기대 | 흐름 오류 |
| O2 | 테스트 독립 실행 | ground truth |
| O3 | judge pass ↔ O2 실패 | **거짓 결과(FALSE_PASS)** |
| O4 | judge notes 의 없는 파일 언급·placeholder | **hallucination** |
| O5 | passes ↔ qa 판정 ↔ ground truth | 북키핑 |
| O6 | 시나리오 불변식 (테스트 약화·파일 보존·AC 준수·리팩토링) | cheat·정확도 |

판정: `PASS` / `ACCURACY`(정확도 결함) / `BUG`(하네스 결함) / `INFRA`(호스트 일시 결함 — 하네스 무죄).

결과는 `results/round<N>.jsonl` 에 시나리오별 JSON 으로 누적된다 (findings·judge notes·driver 로그 포함).
