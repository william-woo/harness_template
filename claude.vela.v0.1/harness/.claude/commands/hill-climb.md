# /project:hill-climb — Loop 4 (Hill-Climbing Loop) (claude.loope 전용)

LangChain "loop engineering" 의 **Loop 4** = *"production 트레이스 → 분석 → harness config 개선"*.
`hill_climb.py` 가 3개 트레이스 소스를 **결정론으로 집계**해 신호 + **개선 후보(candidate)** 를 낸다.

**claude.loope · localllm 변형 전용** (ADR-014/017). Loop 2(verify-loop)와 짝을 이루는 loop engineering 오버레이.

> retro 와 관계: `retro` = 일반 회고(무엇을 했나) / `hill-climb` = **개선 신호**(무엇을 고칠까,
> 특히 verify-loop 트레이스 기반). 둘은 보완적 — retro 가 hill-climb 를 참조한다.

## 사용법

```bash
python3 .claude/bin/hill_climb.py analyze          # 신호 리포트 + 개선 후보
python3 .claude/bin/hill_climb.py analyze --json   # 기계 판독 (분석 에이전트 입력용)
python3 .claude/bin/hill_climb.py self             # 트레이스 소스 감지
```

## 트레이스 소스 (3종)

| 소스 | 내용 | 비고 |
|---|---|---|
| `.claude/state/verify-loop/*.json` | Loop 2 판정·재시도·에스컬레이션 | **F020 신설** — Loop 4 의 금맥 |
| `.claude/state/analytics.jsonl` | handoff/session_end/review 이벤트 | retro 와 공유 |
| `.claude/state/learnings.jsonl` | pitfall/pattern/architecture | 있으면 |

## 개선 후보 heuristic (결정론)

- 에스컬레이션 feature → Architect 선행 검토/분해 후보
- grader revision율 ≥50% → rubric 항목·Developer 가이드 재점검 후보
- handoff 변경파일 ≥30 → Surgical Changes 위반 후보 (리뷰 강화)
- handoff 3회+ 반복 feature → 재작업, learn(pitfall) + 설계 재검토 후보
- 루프는 도는데 learnings 0건 → pitfall 축적 습관 후보

## 루프가 닫히는 지점 (helper vs agent)

**헬퍼 = 결정론 신호·후보** / **에이전트 = 개선안 판단** (하네스 패턴 · Karpathy).
`hill_climb.py` 는 신호와 후보만 낸다. 이를 **구체 harness-config 변경안**으로 바꾸는 것은
분석 에이전트(reviewer/architect)+사람 몫 — 그때 Loop 4 가 닫힌다:

```
python3 .claude/bin/hill_climb.py analyze --json   # 신호 추출
→ architect/reviewer 에게: "위 신호·후보로 harness 개선안을 제시하라"
→ 사람이 채택 → CLAUDE.md/에이전트/rubric 수정 → 다음 사이클 트레이스로 재검증 (hill climb)
```

## 호출 기준

- phase 마일스톤·retro 시점에 함께 (개선 신호 추출)
- verify-loop 에스컬레이션이 반복될 때 (근본 원인 후보 파악)
- handoff 가 여러 번 쌓인 뒤 (반복 재작업 탐지)

해당 없으면 스킵 — **옵셔널**. 신호가 임계 미만이면 "현재 config 유지 가능" 을 출력한다.
