# ADR-018: 결정론 supervisor 드라이버 — supervisor 의 로컬화 (cycle_driver.py)

> Feature: F025 — supervisor 도 로컬에서 담당하는 방안
> 상태: `Accepted` (구현 — localllm d-2 오버레이, 측정 07 무인 검증)
> 관련: ADR-014(loop engineering — host 가 루프 소유), ADR-017(loope 계보 승격 + 측정 05/06)

## 맥락

측정 06(하네스 통합 테스트 01)은 **하이브리드 구조**로 SDLC 풀사이클을 완주했다 — 로컬
에이전트가 역할을 수행하고, **상위 호스트(Claude Code)가 supervisor** 로 핸드오프·grader
실행·북키핑을 담당했다. 사용자 질문: "supervisor 도 로컬 LLM 에서 담당할 수 없는가?"

측정 05 의 실측이 답의 방향을 결정한다:
- **LLM 이 문맥으로 흐름을 조율**(G4/G5 — 값 전달·다단계 핸드오프)은 **32B 로도 실패** (3회 0클린)
- 반면 **단일 역할 호출**(생성 14B / 판정 32B)과 **결정론 도구**는 안정적으로 동작

## 결정

### 결정 1 — supervisor 를 "로컬 LLM" 이 아니라 "로컬 결정론 코드"로
supervisor 가 하는 일(단계 순서·grader 실행·재시도·에스컬레이션·북키핑)은 **판단이 아니라
상태 기계**다. 이를 stdlib 드라이버 `cycle_driver.py` 로 코드화한다:

```
develop(14B) → grade(결정론: exit 0 + 기대 출력) ─ pass → review(32B) → qa(32B) → bookkeep
                     └ revision → 전체 파일 재작성 재작업 (유계 — verify-loop 임계 3)
                                   └ 초과 → 🚨 상위 호스트 인계 (exit 2)
```

LLM supervisor 재시도(G5)는 측정으로 반증된 경로이므로 채택하지 않는다 — LangGraph 를
기각했던 ADR-014 의 "host 가 루프를 소유" 원칙의 d-2 완성형이다. 이로써 사이클 전체가
**로컬 머신에서 무인 실행**되고, 클라우드 LLM 은 개입하지 않는다.

### 결정 2 — 측정 05/06 규율의 코드화
- **값 주입**: 재작업 프롬프트에 실패 출력 + 현재 파일 내용을 드라이버가 직접 주입 (LLM 문맥 전달 배제)
- **전체 파일 재작성** 지시 (AGENTS.md 규칙 6), **judge bash-only** 템플릿 (규칙 7)
- **공허 통과 차단**: grader 는 exit 0 + `--expect` 문자열 동시 확인
- **부트스트랩 간헐 행 대응**: opencode 호출 timeout + 1회 재시도 (측정 06 운영 참고의 코드화)

### 결정 3 — judge 의 판정은 LLM, 판정의 "기록 검증"은 드라이버
reviewer/qa(32B) 가 verify_loop record 를 스스로 실행하되, **기록이 실제로 남았는지는
드라이버가 상태 JSON 으로 결정론 검증**한다. 미기록 시 1회 재시도 후 상위 호스트 인계 —
드라이버가 판정을 대신 기록하지 않는다 (judge 무결성).

### 결정 4 — 에스컬레이션 경계 유지
revision 임계(기본 3) 도달·judge 미기록·NEEDS REVISION 판정 시 드라이버는 **정직하게 멈추고**
exit 2/3 으로 상위 호스트(사람/Claude Code)에 인계한다. passes 반영은 qa pass 기록이 있을 때만.

## 대안 검토

- **32B 를 orchestrate supervisor 로**: 측정 05 G5 실측 실패 — 기각.
- **32B "다음 단계 선택" judge + 코드 실행**: 고정 파이프라인에서 선택 판단이 불필요 —
  취약성만 추가. 기각 (단계 분기가 생기는 후속 phase 에서 재검토).
- **OpenCode plugin 으로 루프 내장**: 외부 plugin API 의존 — ADR-017 보류 항목 유지.

## 결과

- `cycle_driver.py` (stdlib, d-2 오버레이 — LINT-MR-9 등재). run/self 서브커맨드.
- 측정 07 (3 run): run1 부트스트랩 행→`--pure` 코드화 / run2 dev 실패 3회→정직 에스컬레이션
  (상위 호스트 1분 개입) / 재개 버그→**grade-before-generate** 불변식 / run3 **무인 완주 exit 0**
  — reviewer·qa(32B)가 구체 소견으로 스스로 기록, 드라이버가 passes·커밋까지 수행.
  → docs/poc/measurements/07-unattended-cycle.md
- supervisor 역할 재정의: 평시 = 로컬 결정론 드라이버 / 예외(에스컬레이션) = 상위 호스트.
