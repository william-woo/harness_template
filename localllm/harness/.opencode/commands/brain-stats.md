---
description: "영구 지식베이스 통계"
---

# /brain-stats — 영구 지식베이스 통계

`~/.harness/brain.db` 의 전체 또는 프로젝트별 통계 표시.

**HARD GATE: 읽기 전용.**

## 사용

```
/brain-stats                       # 전체 통계 + 프로젝트별 요약
/brain-stats --project <slug>     # 특정 프로젝트만
```

## 실행

```bash
python3 .claude/bin/brain.py stats
python3 .claude/bin/brain.py stats --project harness_update_agent
```

## 출력 예시

```
📊 BRAIN STATS
═══════════════════════════════════════

범위: ALL projects
  projects:  3
  learnings: 47
  features:  18  (done: 11)
  ADRs:      5

프로젝트별:
  • harness_update_agent       learnings= 18  features=4/8  adrs=0  last=2026-04-25
  • web-frontend               learnings= 22  features=7/10 adrs=4  last=2026-04-24
  • payment-service            learnings=  7  features=0/0  adrs=1  last=2026-04-20

Learnings — type 분포:
  pattern       : 14
  pitfall       : 12
  architecture  : 11
  preference    :  7
  tool          :  3
```

## 출력 컬럼 설명

- **projects**: 등록된 프로젝트 수
- **learnings**: 누적 학습 (tombstone 제외)
- **features**: 전체 / 완료 (passes:true) 비율
- **ADRs**: 등록된 아키텍처 결정 문서
- **last**: 마지막 sync 일자

## 활용

- 어느 프로젝트가 학습을 잘 누적하는지 파악
- 함정 비율 (pitfall %) 이 높으면 그 프로젝트 회고 권장
- 다른 프로젝트보다 ADR 부족 → 설계 문서화 부족 신호

## 빈 DB 처리

`~/.harness/brain.db` 가 없으면:
```
ℹ️  brain.db 없음: /home/<user>/.harness/brain.db
```
→ 먼저 `/brain-sync` 한 번 호출.

---

사용자 인자 (없으면 무시): $ARGUMENTS

---

> **로컬 LLM 실행 힌트**: 이 커맨드의 동작은 위 문서의 bash 명령을 **그대로 실행**하는 것이다. 문서에 `python3 .claude/bin/...` 또는 bash 블록이 있으면 추측·재해석하지 말고 그 명령을 bash 도구로 즉시 실행하고, 그 출력을 요약해 보고하라. bash 도구 호출 시 `command` 와 `description` **두 인자를 모두** 채워라 (description 누락 = 스키마 에러). 파일이 없거나 실패하면 문서의 안내 문구를 따르고 사용자에게 질문하지 마라.
