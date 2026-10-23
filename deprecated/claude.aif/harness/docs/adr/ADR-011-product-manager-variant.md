# ADR-011: `claude.productmgr` 변형 — Product Manager 주도 통합 SDLC

> Feature: F018 — Phase 13 `claude.productmgr` 변형
> 상태: `Accepted` (구현 — product-manager 에이전트 + /project:product-cycle 커맨드)
> 관련: ADR-008(orch/single-host), ADR-010(hermes), plan-full(설계 체인)

## 맥락

기존 orch 변형은 이종 에이전트(research/design/dev/review/qa)를 실행 라우팅(`orchestrate`)한다.
그러나 **제품 관점**(누구를 위해·왜·성공지표)을 책임지는 역할이 없었다. 사용자는 PM 이 사용자와
협력하여 **기획→설계→개발→검증→배포** 전 과정을 조율하는 통합 에이전트를 요청.

## 결정

### 결정 1 — 새 변형 `claude.productmgr` = hermes 복사 + pm 오버레이
가장 기능이 완전한 `claude.hermes` 를 복사(auto+design+wiki+orch+hermes 전부 상속) + pm 오버레이.
→ PM 사이클이 세션검색(과거 회상)·wiki(지식)·skill_forge 까지 활용 가능.

### 결정 2 — `product-manager` 에이전트: planner 의 앞단 (대체 아님)
- **PM = why·what·who·성공지표·로드맵** (제품 brief). **Planner = feature 분해·의존성·우선순위**.
- PM 은 `feature_list.json` 의 `passes` 를 만지지 않음 (QA 단독). 코드 직접 수정 X (조율자).
- 산출물: `docs/product/<slug>-brief.md` (문제·사용자·가치·성공지표·범위·로드맵).

### 결정 3 — `/project:product-cycle`: PM supervisor 통합 5단계
기획(PM→planner) → 설계(architect/designer/researcher 조건부) → 개발(developer) →
검증(reviewer→qa) → 배포(lint→ship→backup-sync). orchestrate 를 **제품 관점으로 감싼** 상위 흐름.
- 차별점: PM 이 각 단계 산출물을 **제품 brief 의 성공지표 기준으로 게이트**, 어긋나면 재작업 요청.
- single-host (Task spawn, 같은 컨텍스트 풀 — ADR-008 결정 5 상속). d-3 분산 아님.
- 핸드오프: `.claude/state/product-cycle/<cycle-id>/` (00-brief~05-deploy), 런타임 gitignore.
- **중간 진입 `--from=<stage>` / 조기 종료 `--to=<stage>`** (stage: plan|design|develop|verify|deploy):
  이미 brief·설계·코드가 있으면 해당 단계부터 진입. PM 이 진입 전제조건(상위 산출물 존재)을 점검하고,
  brief 없으면 feature 의 acceptance_criteria 를 성공지표로 채택하는 **경량 intake** 수행. 전제조건
  미충족 시 막지 않고 경고+더 앞 단계 권고 (autonomous — 사용자 판단 존중).

### 결정 4 — "배포(deploy)" 정의: 하네스 게이트 (prod CI/CD 는 다운스트림)
하네스엔 실제 프로덕션 배포가 없으므로, 배포 단계 = `lint --strict`(0 BLOCK) + `/project:ship`
(리뷰 준비도) + `backup.py sync`(산출물 동기화). 실제 CI/CD 는 다운스트림 프로젝트가 담당.

### 결정 5 — 격리: LINT-MR-11
pm 오버레이(`product-manager.md`, `product-cycle.md`)는 **claude.productmgr 에만** 존재.
다른 9 변형에 누수 시 BLOCK. `lint.py check --only=LINT-MR` (MR-11) 가드.

### 결정 6 — 외부 의존성: hermes 상속 (pm 오버레이는 stdlib/문서만)
pm 오버레이는 에이전트 정의 + 커맨드 문서뿐 — 신규 외부 의존성 0. wiki/hermes 상속분만 허용.

## 대안 검토

| 옵션 | 장점 | 단점 |
|---|---|---|
| (A) **새 변형 + PM 에이전트 + product-cycle (채택)** | 기존 무회귀, 제품 관점 격리 | 10번째 변형 |
| (B) orch 의 orchestrate 에 PM 단계만 추가 | 변형 수 유지 | orch 사용자에 PM 강제, 제품 brief 개념 혼입 |
| (C) planner 를 PM 으로 확장 | 에이전트 수 유지 | 제품(why)과 분해(how-much) 책임 혼재 → 단일책임 위반 |

→ **(A) 채택**. wiki/orch/hermes 변형 격리 패턴과 일관.

## 결과
- 신규: `product-manager.md`, `product-cycle.md`, `state/product-cycle/`, 이 ADR, LINT-MR-11.
- 기존 8 에이전트 + orchestrate/plan-full 재사용 (PM 이 상위 조율).
- 미이식: 실제 prod 배포 자동화 (다운스트림 위임, 결정 4).
