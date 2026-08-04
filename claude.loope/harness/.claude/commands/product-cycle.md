# /project:product-cycle — PM 주도 통합 제품 라이프사이클 (claude.productmgr 전용)

Product Manager 가 supervisor 가 되어 **기획 → 설계 → 개발 → 검증 → 배포** 전 과정을 한 흐름으로
조율하는 통합 커맨드. orchestrate(이종 에이전트 오케스트레이션)를 **제품 관점으로 감싼** 상위 흐름.

**claude.productmgr 변형 전용.** single-host (모든 에이전트가 같은 컨텍스트 풀 — ADR-008 상속).

> 관계: `product-cycle`(제품 사이클 전체) ⊃ `orchestrate`(실행 라우팅) + `plan-full`(설계 체인).
> PM 이 성공지표 기준으로 각 단계 게이트를 점검하는 것이 orchestrate 와의 차이.

---

## 사용법

```
/project:product-cycle "<제품 아이디어 / 요구사항>"          # 전체 (기획부터)
/project:product-cycle "<요청>" --from=design              # 중간 진입 (설계부터)
/project:product-cycle --feature=F0XX --from=develop       # 기존 feature 를 개발부터
/project:product-cycle --feature=F0XX --from=verify        # 구현된 코드를 검증부터
/project:product-cycle "<요청>" --from=design --to=develop # 구간 실행 (설계~개발만)
```

> `--from=<stage>` 미지정 시 `plan`(전체). `--to=<stage>` 미지정 시 `deploy`(끝까지).
> 단계 토큰: `plan | design | develop | verify | deploy`.

---

## 5단계 흐름 (PM supervisor + 조건부 라우팅)

```
① 기획 (PLAN)      product-manager → planner
     PM: 문제·사용자·가치·성공지표·범위 정의 (docs/product/<slug>-brief.md, 사용자와 협력)
     planner: brief → feature_list.json 분해 (검증 가능 기능 + 의존성 + 우선순위)
        │  [PM 게이트] 성공지표·MVP 범위 합의됐나? 문제 정의 명확한가?
        ▼
② 설계 (DESIGN)    architect (+ designer / researcher 조건부)
     architect: DB/외부API/보안/3+파일 변경 시 ADR 작성
     designer: UI 작업 시 디자인 토큰 (design-pick)
     researcher: 모르는 외부 API/도메인 시 선행 조사
        │  [PM 게이트] 설계가 요구사항 충족 + 과설계 아닌가?
        ▼
③ 개발 (DEVELOP)   developer
     feature 1개씩 구현 + 단위 테스트 (한 번에 하나)
        │  [PM 게이트] 테스트 동반? mergeable 상태?
        ▼
④ 검증 (VERIFY)    reviewer → qa (+ design-review / qa-browser 조건부)  ★ Loop 2 정형화
     verify-loop start <F> --rubric code-review   # 검증 루프 개시 (claude.loope)
     reviewer: 코드 품질·보안·성능 (APPROVED → status: qa) → verify_loop record --grader reviewer
     qa: acceptance_criteria E2E 검증 → passes:true (QA 단독) → verify_loop record --grader qa
     design-review/qa-browser: UI 변경 시 → 결정론 grader 로 record (judge 전 게이트)
        │  [PM 게이트] verify_loop status <F> 로 재시도·에스컬레이션 확인 + 성공지표(brief) 충족?
        ▼
⑤ 배포 (DEPLOY)    하네스 게이트 (실제 prod CI/CD 는 다운스트림)
     /project:lint --strict        # 거버넌스 정합성 (BLOCK 0)
     /project:ship                 # 리뷰 준비도 대시보드
     python3 .claude/bin/backup.py sync   # 산출물 동기화 (선택)
        │  [PM 게이트] lint 0 BLOCK + 사이클 회고
```

## 라우팅 판별 (단계 포함/스킵)

| 단계 | 항상 | 조건부 포함 | 스킵 가능 |
|---|---|---|---|
| ① 기획 | ✅ PM + planner | — | brief 이미 있으면 `--from=design` |
| ② 설계 | — | architect(구조/DB/API/보안), designer(UI), researcher(미지 도메인) | 단순 변경 |
| ③ 개발 | ✅ developer | — | — |
| ④ 검증 | ✅ reviewer→qa | design-review/qa-browser(UI) | — |
| ⑤ 배포 | ✅ lint | ship, backup-sync | — |

## 진입점 선택 — 중간 단계부터 시작 (`--from` / `--to`)

라이프사이클은 항상 기획부터 시작할 필요가 없다. 이미 brief·설계·코드가 있으면 해당 지점부터 진입한다.

### 단계 순서 + 진입 전제조건
PM 은 `--from=<stage>` 진입 시, 그 단계가 필요로 하는 **상위 산출물이 실제로 존재하는지 먼저 점검**한다.

| `--from` | 진입 전제조건 (없으면 경고 + 더 앞 단계 권고) | 진입 시 PM 이 하는 일 |
|---|---|---|
| `plan` (기본) | 없음 | 전체 — 문제 발견부터 |
| `design` | 제품 brief 또는 feature_list 항목 존재 | brief/feature 를 컨텍스트로 로드 → 설계로 |
| `develop` | 대상 feature(`--feature=F0XX`) + (설계 필요시) ADR | feature 의 acceptance_criteria 를 성공지표로 채택 → 개발로 |
| `verify` | 구현된 코드(diff/feature status≥review) | 성공지표 기준 검증만 (reviewer→qa) |
| `deploy` | 검증 통과(passes:true 또는 리뷰 완료) | 하네스 게이트만 (lint→ship→backup) |

### 경량 intake (brief 없이 중간 진입 시)
`--from=develop|verify` 인데 제품 brief 가 없으면, PM 은 **풀 제품 발견을 건너뛰고** 다음만 한다:
- 대상 feature 의 `acceptance_criteria` 를 **성공지표로 채택** (이미 측정 가능 기준이므로)
- 누락된 성공지표가 있으면 1~2개만 사용자에게 확인 (전체 brief 요구 X)
- `00-brief.md` 에 "경량 intake (from=<stage>)" 로 최소 기록

### 전제조건 미충족 시
PM 은 진입을 막지 않되 **명시적으로 경고**하고 더 앞 단계를 권고한다:
> "⚠️ `--from=verify` 인데 구현 흔적이 없음 (feature status=todo). `--from=develop` 또는 `plan` 권장."
사용자가 그대로 진행을 원하면 진행 (autonomous — 사용자 판단 존중).

### `--to=<stage>` (조기 종료)
지정 단계까지만 실행하고 멈춘다. 예: `--from=design --to=develop` = 설계+개발만 (검증·배포 스킵).
핸드오프 디렉토리엔 실행한 단계 파일만 생성된다.

## PM supervisor 의 역할 (핵심 차별점)

각 단계 산출물이 **제품 brief 의 성공지표에 부합하는지** PM 이 게이트한다:
- 부합 → 다음 단계로 핸드오프
- 어긋남 → 해당 단계 에이전트에 **재작업 요청** (예: "성공지표 p95<200ms 미충족 → developer 재구현")
- PM 은 조율만 — 코드/문서 직접 수정 X, `passes` 마킹 X (QA 단독)

## 핸드오프 디렉토리 규약

```
.claude/state/product-cycle/<cycle-id>/
  ├── 00-brief.md         # PM 제품 brief
  ├── 01-plan.md          # planner feature 분해
  ├── 02-design.md        # architect/designer 산출
  ├── 03-dev.md           # developer 구현 요약
  ├── 04-verify.md        # reviewer/qa 결과
  └── 05-deploy.md        # lint/ship/backup 결과 + 회고
```
(orch 의 `.claude/state/orch/` 규약과 동일 패턴 — ADR-008 결정 3 상속)

## 호출 기준

다음일 때 `/project:product-cycle` 권장:
- **아이디어 → 출시**를 한 흐름으로 (제품 발견부터 배포 게이트까지)
- 제품 관점(사용자·가치·성공지표)이 중요한 신규 기능
- 여러 역할(기획·설계·개발·검증)이 모두 필요한 복합 제품 작업

해당 없으면:
- 단일 역할(버그 수정 등) → 해당 에이전트 직접 호출
- 실행 라우팅만(제품 brief 불필요) → `/project:orchestrate`
- 설계 체인만 → `/project:plan-full`

## single-host / d-1 경계
모든 에이전트는 Claude Code Agent 도구(구 Task)로 spawn (같은 컨텍스트 풀). 이종 호스트 분산(d-3) 아님.
(ADR-008 결정 5 상속 — claude.productmgr 는 orch/hermes 계보)
