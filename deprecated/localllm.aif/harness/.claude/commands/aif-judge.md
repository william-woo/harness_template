# /project:aif-judge — 항목형 rubric 판정 (AIF 오버레이, ADR-020)

judge 에게 종합 판단을 묻는 대신 **항목별 이진 판정 + 증거**를 요구하고, 결정론적으로
검증·앙상블한다. RLAIF/CAI 문헌의 판정 설계 규율을 이식한 것이다.

## 사용

```bash
# 1) 판정 프롬프트 생성 → judge(에이전트)에게 준다
python3 .claude/bin/aif_judge.py plan code-review --target src/auth.py,tests/ --repeats 3

# 2) 돌아온 판정을 검증·저장 (N회 반복)
python3 .claude/bin/aif_judge.py record code-review --run F001-r1 --file j1.txt

# 3) 앙상블 집계 → 최종 verdict
python3 .claude/bin/aif_judge.py aggregate F001-r1

# 비교 판정은 순서를 교대해 position bias 를 검출한다
python3 .claude/bin/aif_judge.py compare code-review --a before.py --b after.py

# 로컬 LLM 변형(localllm.aif)은 자동 판정 가능
python3 .claude/bin/aif_judge.py auto code-review --target src/auth.py --run F001-r1 --repeats 3

python3 .claude/bin/aif_judge.py self     # rubric 파싱 점검
```

## 산문형 rubric 과의 차이

| | 산문형 (`code-review.md`) | 항목형 (`code-review.items.md`) |
|---|---|---|
| judge 에게 요구 | "MUST 를 검토하고 pass/revision" | 항목별 met/unmet/na + **증거** |
| 증거 | 자율 | **강제** — `파일:행` 또는 인용 없으면 met 불가 |
| 분산 대응 | 없음 | `--repeats N` 항목별 다수결 |
| 갈린 판정 | 한쪽으로 수렴 | **UNCERTAIN** → 에스컬레이션 |

둘은 공존한다. 산문형은 사람이 읽는 기준이고, 항목형은 기계가 검증하는 채점표다.

## 호출 기준

- judge 판정의 **재현성이 낮을 때** (같은 대상에 다른 판정이 나올 때)
- 판정자가 **약한 모델**일 때 (로컬 LLM — 구조화가 정렬을 개선한다)
- 통과/미통과가 **중요한 게이트**일 때 (배포 직전, feature 완료 판정)

해당 없으면 산문형 rubric + `verify_loop.py record` 로 충분하다. 항목형은 판정 호출이
N배로 늘어나므로 값이 비싸다.

## 하지 않는 것

- 모델 호출 (`auto` 모드 예외) — 호스트가 판정하고 스크립트는 검증·집계만 한다
- 갈린 판정을 pass/revision 중 하나로 강제 기록 — 불확실성을 기록에서 지우지 않는다
- 산문형 rubric 대체 — 항목형은 추가 게이트이지 교체가 아니다
