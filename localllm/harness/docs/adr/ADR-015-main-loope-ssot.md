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

### 결정 2 — 로컬 파일은 승격에서 제외 (머신/프로젝트 로컬)

> **개정 (2026-10-20, F021 에스컬레이션)** — 제외 목록의 SSOT 는 **코드**다.
> `lint.py` 의 `_SSOT_EXCLUDE_PREFIXES`(접두) 와 `_SSOT_EXCLUDE_EXACT`(정확 일치) 가
> 정의이고 아래 표는 그 **설명**이다. **개수를 적지 않는다** — 2026-09-22 판의 "5종" 은
> ADR-023 이 2 항목을 더한 날 낡았고 아무도 알아채지 못했다. 세려면 센다:
>
> ```bash
> python3 -c "import sys; sys.path.insert(0,'.claude/bin'); import lint; \
>   print('prefix', len(lint._SSOT_EXCLUDE_PREFIXES), '/ exact', len(lint._SSOT_EXCLUDE_EXACT))"
> ```
>
> | 제외 대상 | 종류 | 이유 | 더한 ADR |
> |---|---|---|---|
> | `state/` | 접두 | 런타임 상태 | 이 ADR |
> | `design/` | 접두 | `design_pick.py apply` 의 프로젝트 로컬 산출물(tokens.json·backup). `references/` 는 `docs/design-references/` 와 중복이라 변형은 후자만 쓴다 | 이 ADR |
> | `settings.json` · `settings.local.json` | 정확 | 머신 로컬 권한·훅 배선 | 이 ADR |
> | `host.json` | 정확 | 프로젝트 로컬 agent_type·백업 설정 | 이 ADR |
> | `bin/live_status.sh` | 정확 | 머신 로컬 관측 도구 (tmux·파일 기반) | 이 ADR |
> | `atlassian-targets.json` | 정확 | 쓰기 허용 대상 — `settings.json` 과 같은 층위의 로컬 값 (3-C 철칙) | **ADR-023** |
> | `hooks/pre-atlassian-write-check.sh` | 정확 | 위 목록을 강제하는 훅. 목록과 한 쌍 | **ADR-023** |
>
> 뒤 2 항목은 이 ADR 이 아니라 **ADR-023**(vela 계보·Atlassian)이 더했다. 역참조가 없어
> 이 ADR 만 읽은 사람은 목록이 5종인 줄 안다.
>
> **규칙 — 가드 없는 제외는 금지한다.** 제외는 곧 *어떤 미러 검사도 보지 않는 파일*을
> 만드는 일이다(F021 이 막은 밀반입 통로가 그 모양이었다). 제외를 더하는 ADR 은 **대체
> 가드를 함께 둔다** — 여기서는 `LINT-ATL` 이 로컬 훅과 배포 사본의 **바이트 동일**을 본다.
>
> **왜 코드로 강제하는가**: 원문은 invariant 를 선언하고 가드를 `LINT-MR` 에 맡겼는데,
> 그 검사기는 **오버레이 파일의 존재만** 본다. 그래서 실제로
> `coding-standards.md` 내용 drift · `CLAUDE.md` 본문 drift · 한쪽에만 있는 파일 3건이
> 전부 **0 BLOCK 으로 통과**했다. F010 의 "미러 회귀 2회" 교훈이 겨냥한 결함 —
> 규칙은 문서에 있고 강제는 존재만 보는 것 — 이 그대로 재발한 것이다.
>
> → **`LINT-SSOT`** 검사기를 신설했다. `.claude/`·`docs/adr/` 를 **내용 해시**로
> 비교하고 `CLAUDE.md` 는 **섹션 단위**로 본다(변형별 헤더 맞춤은 허용). drift 는 BLOCK.
> `handoff` 전 `lint --strict` 가 이 게이트다.
`settings.json`(사용자 권한 구성), `settings.local.json`(로컬 권한 누적), `host.json`(호스트 상태),
`.claude/state/`(프로젝트 로컬 상태)는 loope 템플릿으로 덮지 않는다 — 이들은 SSOT 대상이 아니다.

### 결정 3 — 미러 정책 재정의
| 방향 | 정책 |
|---|---|
| main → `claude.loope` | **전체 1:1 미러** (새 invariant. 단 결정 2 의 로컬 파일 제외) |
| main → 그 외 변형 | 해당 변형의 오버레이 구성에 맞춰 제외 미러 — `lint.py` 의 `_*_OVERLAY_FILES` / `_VARIANTS_WITH_*` 가 SSOT 다. **범위 번호를 적지 않는다** (`LINT-MR-1~13` 은 MR-14·15 가 생긴 날 낡았다. 세려면 `grep -c "MR-[0-9]*:" .claude/bin/lint.py`). 내용 오버레이는 **결정 5** 참조 |
| `claude.productnw` | nw 오버레이(consortium)는 main 에 없음 — 종전대로 productnw 전용 유지 |
| baseline/openai | 종전대로 동결 (Karpathy 예외만) |

### 결정 5 — 오버레이는 **파일로도, 내용으로도** 존재한다 (2026-10-20 신설)

이 ADR 의 결과절은 "reviewer/qa/retro 의 Loop 2·4 연동판" 유입을 적고 있다. 그것들은
**공유 파일 안의 문단**이지 loope 전용 파일이 아니다. 그런데 결정 3 은 미러를 *파일 목록의
제외*로만 정의했다 — 문서 안의 모순이고, 2026-10-19 에 그 틈으로 사고가 났다. 정책을
**문자대로 따른** 일괄 복사(`reviewer.md` → 전 변형)가 ① loop 서술을 비-loop 변형 5곳에
누수시키고 ② 동결 baseline 을 덮고 ③ aif 2 사본의 의도된 차이를 지웠는데 `lint --strict`
는 **0 BLOCK** 이었다.

| 오버레이 형태 | 예 | 가드 |
|---|---|---|
| **파일** — 그 변형에만 있는 파일 | `verify_loop.py`, `consortium.py` | `LINT-MR` (기존) |
| **내용** — 공유 파일 안에서 변형군별로 갈리는 문단 | `reviewer.md` 의 Loop 2 절, `coding-standards.md` 의 변형별 계약 | **`LINT-CO`** (신설) |
| **동결** — 변경 금지 스냅샷 | `claude/` baseline, `openai/.codex/` | **`LINT-FREEZE`** (신설) |

`LINT-CO` 는 **새 표를 만들지 않는다.** 같은 오버레이 프로필이면 바이트가 같아야 하고,
선언된 축이 만드는 분할과 관측 분할이 일치해야 한다 — 둘 다 기존 `_VARIANTS_WITH_*` 에서
**계산한다**. 파일당 선언은 축 이름 한 줄(값이 아니라 **모양**)이라 정당한 문구 수정에
**불변**이다. 기대 해시 표로 두면 `reviewer.md` 를 한 줄 고칠 때마다 갈래 수만큼 갱신해야
하고, 그 번거로움이 `regenerate` 를 부르며, 그 순간 검사기는 공회전한다.

양방향이라 조용한 실패 모드가 없다 — *같은 프로필인데 바이트가 다르면* 선언 안 된 분기,
*다른 프로필인데 바이트가 같으면* 오버레이 소실. 정당한 편집(모든 비동결 사본에 같은
수정)은 분할을 바꾸지 않으므로 0 BLOCK 이다.

**검사 범위는 트리 전체다** (2026-10-22 개정). 처음엔 `.claude/`·`docs/adr/` 만 봤는데,
그 바깥에 실제 drift(`docs/poc/measurements/06-harness-e2e.md` — F024 리뷰 수정과 딸린
repro·artifact 6건이 3 사본 중 1곳에만)와 미가드 내용 오버레이(`.opencode/` 렌더 산출물
등 9종)가 있었다. **범위를 좁히면 "미분류 0건" 이 범위 축소로 통과한다** — 그래서 좁히지
않고, 줄이는 통로는 `_CO_SKIP_DIRS` 와 아래 (C) 둘뿐이며 둘 다 사유를 적는다.

비교 경계는 **git 추적 파일**이다. 미러는 추적되는 내용에 대한 계약이고, 디스크를 그대로
훑으면 로컬 산출물이 섞인다 — 실측: 메인의 `.opencode/` 는 gitignore 된 render 결과물인데
디스크 스캔에서는 d-2 변형들과 "갈린" 것으로 읽혀 거짓 BLOCK 7건을 냈다.

공유 파일은 **셋 중 하나**로 빠짐없이 분류된다 — 미분류가 0건이어야 한다:

| 부류 | 뜻 | 선언 위치 |
|---|---|---|
| **(A)** | 어디서나 바이트 동일 | 기본값 (선언 불필요) |
| **(B)** | 계보 그룹별 사본 = 내용 오버레이 | `_CONTENT_OVERLAY_AXES` |
| **(C)** | 미러 대상 아님 (변형 로컬·생성물) | `_CO_VARIANT_LOCAL` — **사유 필수** |

`check_ssot()` 은 `docs/adr/` 를 **loope 하고만** 비교해 나머지 변형이 무가드였고, 실제로
이 ADR 과 ADR-017 이 2:4 로 갈린 채 0 BLOCK 이었다. 이제 `LINT-CO` 가 전 트리를 본다.
`wiki/` 는 (C) 다 — 변형별 노드 집합이 다르다고 적었던 것은 **틀렸고**, 실측상 같은 노드가
여러 트리에서 **재생성 시각(`updated:`)만** 다르다. 생성 산출물이라 제외한다.

또한 모델 축(`localllm.nem`, F030/ADR-021)은 **자기 파일이 하나도 없는 최초의 순수 내용
오버레이**다. 그래서 파일 기반 정책이 구조적으로 볼 수 없었다 — 실측상 4 파일에서 부모와
갈려 있다. `_VARIANTS_WITH_MODEL_NEM` 으로 등재한다.

### 결정 6 — 동결은 **해시 매니페스트**로 강제한다. `regenerate` 를 만들지 않는다

`claude/` baseline 과 `openai/.codex/` 는 "변경 금지, Karpathy 4원칙만 예외" 인데 강제가
**0이었다**. `LINT-CO` 로는 못 잡는다(실측 — baseline 덮어쓰기에서 0 BLOCK). 동결을 축으로
모델링하면 "baseline 은 늘 달라야 한다" 가 되어 Karpathy 동기화를 영구 금지하게 된다.

여기서는 **해시가 정답**이다 — 해시 표의 결함("자주 바뀌는 파일에 쓰면 regenerate 를 부른다")
은 자주 바뀌는 대상에서만 생기는데, 동결 대상은 정의상 안 바뀐다.
`.claude/freeze-manifest.json` 이 경로마다 `sha256` 과 `reason`(`phase0` | `karpathy` **둘뿐**)
을 둔다. **`regenerate` 서브커맨드를 만들지 않는다** — 만드는 순간 이 검사기는 공회전한다.

Karpathy 예외는 검사기가 "이해" 하지 않는다. 예외는 **매니페스트를 거쳐 간다** — 동기화
커밋이 해당 엔트리의 해시와 `reason` 을 **같은 커밋에서** 갱신하고, 그 한 줄이 diff 에 남아
리뷰에서 보인다. 일괄 `cp` 는 매니페스트를 갱신하지 않으므로 잡힌다. 보강으로
`reason: "karpathy"` 인 파일은 4원칙 제목을 **하나 이상 포함**해야 한다(없으면 사유가
거짓이므로 BLOCK) — 앵커의 안전한 쪽(`must_contain`)이라 리워딩되면 **시끄럽게** 실패한다.

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
- **미러 범위 정정 (2026-10-20)**: 이 ADR 은 main·loope 2곳이 아니라 `docs/adr/` **7 사본**
  (main·loope·vela·claude.aif·localllm·localllm.aif·localllm.nem)에 존재하며,
  `wiki/adrs/ADR-015.md` 요약 노드가 4곳 더 있다. 2026-09-22 보강은 앞 3곳에만 도달했고
  뒤 4곳은 21줄이 빠진 채였다(ADR-017 도 동일 분할). 원인은 `check_ssot()` 이 `docs/adr/`
  를 loope 하고만 비교하는 것이고, **결정 5** 의 `LINT-CO` 가 `docs/adr/`(축 ∅)를 범위에
  넣어 닫는다.
