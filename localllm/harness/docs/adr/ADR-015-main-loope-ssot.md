# ADR-015: 메인 하네스 SSOT 전환 — main ≡ claude.loope (loope 승격)

> Feature: F021 — 메인 하네스 loope 승격 (dogfooding 전면화)
> 상태: `Accepted` (구현 — main .claude/ ≡ claude.loope 1:1)
> 관련: ADR-014(loope/loop engineering), CLAUDE.md 미러 정책, F020 "선택 채택" 결정

## 맥락

F020 까지 메인 하네스(우리 자체 `.claude/`)의 SSOT invariant 는 **main ≡ claude.gstack.auto** 였고,
우리가 만든 상위 기능(design/wiki/orch/hermes/pm/loop)은 변형에만 있어 **우리 개발엔 못 썼다**.
F020 에서 "선택 채택"(meta-dev 오버레이: verify_loop+session_search 만) 으로 부분 dogfood 를 시작했고,
전면 승격은 "SSOT invariant 를 바꾸므로 별도 ADR 없이는 하지 않는다"로 보류했다.

사용자가 전면 승격을 결정: **"우리 하네스를 claude.loope 로 업그레이드해서 진행하고 싶어"** (2026-08-02).
loope 는 가장 완전한 스택(auto+design+wiki+orch+hermes+pm+loop)이며 PR #2 로 main 브랜치에 병합됨.

## 결정

### 결정 1 — SSOT 전환: main ≡ claude.loope (1:1)
메인 `.claude/` + `wiki/` + `docs/{adr,design-references,orch-examples}` 를 claude.loope 와 정합.
이제 우리 자체 개발이 product-cycle·orchestrate·wiki·session-search·verify-loop·hill-climb 를 모두 사용
(완전한 dogfooding). F020 의 "meta-dev 오버레이" 개념은 이 결정으로 **흡수·폐기**된다.

### 결정 2 — 로컬 파일 3종은 승격에서 제외 (머신/프로젝트 로컬)
`settings.json`(사용자 권한 구성), `settings.local.json`(로컬 권한 누적), `host.json`(호스트 상태),
`.claude/state/`(프로젝트 로컬 상태)는 loope 템플릿으로 덮지 않는다 — 이들은 SSOT 대상이 아니다.

### 결정 3 — 미러 정책 재정의
| 방향 | 정책 |
|---|---|
| main → `claude.loope` | **전체 1:1 미러** (새 invariant. 단 결정 2 의 로컬 파일 제외) |
| main → 그 외 변형 | 해당 변형의 오버레이 구성에 맞춰 제외 미러 — **LINT-MR-1~13 목록이 SSOT** (예: gstack.auto = main − design/wiki/orch/hermes/pm/loop 오버레이) |
| `claude.productnw` | nw 오버레이(consortium)는 main 에 없음 — 종전대로 productnw 전용 유지 |
| baseline/openai | 종전대로 동결 (Karpathy 예외만) |

### 결정 4 — 격리 가드 불변
LINT-MR 은 `src/harness_template/` 변형만 검사하므로 main 승격은 가드에 영향 없음 (0 BLOCK 유지).
변형별 오버레이 격리(_VARIANTS_WITH/NO_*) 는 그대로 유효하다.

## 대안 검토

| 옵션 | 장점 | 단점 |
|---|---|---|
| (A) **main ≡ loope 전면 승격 (채택)** | 완전 dogfood — 만든 걸 우리가 씀 | 미러 정책 재정의 필요(이 ADR) |
| (B) 선택 채택 유지 (F020) | 변경 최소 | 상위 기능(pm/wiki/orch) 미활용 지속 |
| (C) main ≡ productnw | consortium 까지 | 우리 개발은 단일 팀 — nw 불필요 노이즈 |

→ **(A)**. loope 가 단일 팀 개발에 필요한 전 스택 + loop engineering 을 갖춘 최신 계보라 적합.
(consortium 이 필요해지면 그때 productnw 재검토.)

## 결과
- main `.claude/` 에 유입: designer/researcher/product-manager 에이전트, wiki.py/design_pick.py/
  skill_forge.py/hill_climb.py, 커맨드 8종+, rubrics, reviewer/qa/retro 의 Loop 2·4 연동판,
  backup.py 보안스캔 fix(6a10c0f). + `wiki/` vault, docs 3종, ADR-007~014.
- CLAUDE.md 미러 정책 섹션 재작성 (이 ADR 반영). meta-dev 섹션 폐기.
- 이후 신규 기능 개발: **main 에서 개발 → loope 로 1:1 미러 → 하위 변형은 오버레이 규칙대로 제외 미러**.
