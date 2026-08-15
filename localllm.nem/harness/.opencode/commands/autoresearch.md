---
description: "하네스 자가 실험 루프 (localllm 전용, F027)"
---

# /autoresearch — 하네스 자가 실험 루프 (localllm 전용, F027)

무인 스위트를 **적합도 함수**로 써서 역할 지시(정책)를 실험적으로 개선한다.
karpathy/autoresearch 의 구조를 이식했다 — 자동 채택은 **실험 결과까지**, 하네스 본체 반영은
**사람 승인**으로만 (ADR-019).

## 사용

```bash
python3 .claude/bin/autoresearch.py self                     # 의존성·불변 매니페스트 점검
python3 .claude/bin/autoresearch.py init                     # program.md + 실험 공간 scaffold
python3 .claude/bin/autoresearch.py run --experiments 3 --scenarios S06,S09 --repeats 2
python3 .claude/bin/autoresearch.py status                   # 원장(ledger) + 챔피언 정책
python3 .claude/bin/autoresearch.py promote exp-003          # 변경 내용만 표시 (미반영)
python3 .claude/bin/autoresearch.py promote exp-003 --yes     # 하네스 본체 반영 (사람 승인)
```

옵션: `--timeout <초>` (구간당 제한), `--budget-min <분>` (전체 예산),
`AUTORESEARCH_DIR=<경로>` (실험 공간을 리포 밖에 두기 — 결과·샌드박스가 수 GB 로 늘 수 있다).

## 한 실험이 하는 일

1. **베이스라인 측정** — 현재 챔피언 정책으로 지정 시나리오를 돌린다.
2. **후보 제안** — 로컬 LLM(researcher)이 `program.md` + 실패 증거를 읽고 정책 1건을 제안한다.
3. **후보 측정** — 같은 시나리오·같은 반복 수로 다시 돌린다 (paired).
4. **무결성 검사** — 게이트·oracle·드라이버 해시가 바뀌었으면 실험 무효.
5. **판정** — 후보가 더 많이 통과하면 KEEP(챔피언 갱신), 아니면 DISCARD.
   후보 구간에 **거짓 결과(ACCURACY)가 1건이라도** 있으면 점수와 무관하게 실격.

## 호출 기준

- 스위트 재현율이 낮은 시나리오가 있고, 그 원인이 **모델의 작업 방식**으로 보일 때
- 역할 지시문을 손으로 튜닝하기 전에 근거를 얻고 싶을 때
- 유휴 시간(밤새)에 로컬 GPU 를 개선 실험에 쓰고 싶을 때

해당 없으면 호출하지 않는다. 실험 1건은 스위트를 2회(2구간) 돌리므로 **비싸다** — 시나리오 2개 ×
2반복이면 8 사이클이다.

## 하지 않는 것

- 게이트·oracle·시나리오 수정 (불변 — 실험이 건드리면 무효 처리)
- 하네스 본체(`.claude/policy/`) 자동 수정 — `promote --yes` 없이는 절대
- 통계적 유의성 판정 — 표본이 작으면 원장의 delta 는 **가설**이다. 재현 실험을 더 돌린 뒤 승격한다.

## 사람이 할 일

`program.md` 의 "관찰된 약점" 을 갱신하는 것이 실험 방향을 조종하는 주된 수단이다
(원본 autoresearch 에서 연구자가 `program.md` 를 손보는 것과 같다). 코드를 직접 고치는 대신
지침을 고친다.

---

사용자 인자 (없으면 무시): $ARGUMENTS

---

> **로컬 LLM 실행 힌트**: 이 커맨드의 동작은 위 문서의 bash 명령을 **그대로 실행**하는 것이다. 문서에 `python3 .claude/bin/...` 또는 bash 블록이 있으면 추측·재해석하지 말고 그 명령을 bash 도구로 즉시 실행하고, 그 출력을 요약해 보고하라. bash 도구 호출 시 `command` 와 `description` **두 인자를 모두** 채워라 (description 누락 = 스키마 에러). 파일이 없거나 실패하면 문서의 안내 문구를 따르고 사용자에게 질문하지 마라.
