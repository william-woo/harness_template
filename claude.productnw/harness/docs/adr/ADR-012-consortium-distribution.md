# ADR-012: `claude.productnw` 변형 — 분산 멀티팀 에이전트 컨소시엄 (d-3)

> Feature: F019 — Phase 14 `claude.productnw` 변형
> 상태: `Accepted` (구현 — consortium.py 메시지 계약/로스터/로컬 큐 + **Slack★/Teams 게이트웨이 실구현** + /project:consortium)
> 개정: 2026-09-19 — 결정 2 의 "네트워크 전송은 stub" 수정 (ADR-013 결정 5)
> 관련: ADR-008(orch/single-host, d-1·d-2·d-3 단계), ADR-011(productmgr/product-cycle)

## 맥락

ADR-008 은 분산을 3 단계로 구분했다: **d-1**(single-host 오케스트레이션, orch — 완료),
**d-2**(로컬 LLM, localllm — 완료), **d-3**(이종 호스트 분산 — "먼 미래·어쩌면 불필요"로 보류).

사용자는 d-3 을 요청: 여러 팀이 각자 멀티 에이전트 하네스를 두고, **MS Teams/Slack/Telegram** 으로
통신하며 **컨소시엄**을 이루어 통합 제품을 만든다. 이는 productmgr 의 단일 팀 product-cycle 을
**여러 팀으로 확장**한 것이다.

### 정직한 제약 — 전체 구현은 하네스 범위 밖

진짜 원격 멀티팀 메시징은 (1) Teams/Slack/Telegram 봇 등록·자격증명(autonomous #3-A 경계),
(2) 외부 SDK·웹훅·항상 켜진 서버, (3) 분산 상태 동기화를 요구한다 — 대형 인프라 프로젝트이며
하네스(stdlib + 문서 + 에이전트 정의) 의 범위를 벗어난다.

## 결정

### 결정 1 — 새 변형 `claude.productnw` = productmgr 복사 + nw(컨소시엄) 오버레이
가장 기능이 완전한 `claude.productmgr` 를 복사(auto+design+wiki+orch+hermes+pm 전부 상속) +
nw 오버레이. → 컨소시엄의 각 팀이 PM·세션검색·wiki·orchestrate 까지 모두 활용.

### 결정 2 — "프로토콜은 stdlib 로 실재, 네트워크 전송은 stub"

> **수정 (2026-09-19, ADR-013 결정 5)** — "네트워크 전송은 stub" 은 **더 이상 사실이 아니다**.
>
> 원문은 봇 transport 전체를 다운스트림에 위임한다고 적었다. 그런데 실제로 필요한 것은
> **폴링 수신**뿐이었고, 그건 stdlib `urllib` 로 된다:
> - Slack `conversations.history` — 채널 **로그 읽기**라 다른 봇의 글도 들어온다
> - Teams Microsoft Graph — 같은 모양 (자격증명 4개 + 관리자 동의)
>
> "외부 SDK 가 필요하다" 는 판단은 **푸시**(Slack Events API / Socket Mode)만 보고 내린
> 것이었다. 푸시는 공개 HTTPS 엔드포인트나 웹소켓 SDK 를 요구하지만, 폴링은 요구하지 않는다.
>
> 남는 #3-A 경계는 **자격증명 발급**(앱 생성·토큰·관리자 승인)뿐이고 그건 여전히
> 사용자·다운스트림 몫이다. 코드는 자격증명이 없으면 안내만 하고 graceful degrade 한다.
>
> Telegram 은 예외다 — 발신과 사람 메시지 수신은 되지만 **봇은 다른 봇의 글을 보지 못해**
> (Bot FAQ, privacy mode 무관) 에이전트↔에이전트에는 쓸 수 없다. 그 범위로 좁혀 남겼다.

(원문) codex/openclaw 호스트 stub 와 같은 정직한 패턴으로 출발했다:

| 구성요소 | 상태 | 근거 |
|---|---|---|
| 메시지 계약(JSON 스키마) | ✅ stdlib 실재 | 팀 간 상호운용 표준 — 플랫폼 무관 |
| 컨소시엄 로스터(팀·에이전트 등록) | ✅ stdlib 실재 | 누가 무엇을 담당하는지 SSOT |
| 로컬 큐(inbox/outbox 파일) | ✅ stdlib 실재 | 같은 머신/공유 볼륨이면 협업 흐름 검증 가능 |
| Slack★ / Teams 게이트웨이 | ✅ **실구현** | 발신 + **폴링 수신**. 자격증명 발급만 #3-A (아래 수정 참조) |
| Telegram 게이트웨이 | ⚠️ 부분 | 발신 + **사람이 쓴 메시지** 수신. 봇↔봇은 플랫폼이 금지 |

→ graceful degrade: 봇 미연동이어도 로컬 큐로 컨소시엄 흐름(등록→메시지→핸드오프)을 검증할 수 있다.

### 결정 3 — 메시지 계약: 팀 간 상호운용 표준
필수 필드 `from_team / to_team / role / cycle_id / msg`, 선택 `stage`(plan|design|develop|verify|deploy).
`consortium.py send` 가 발신 전 계약을 검증(위반 시 거부)하고 outbox 에 JSON 으로 기록.
게이트웨이는 이 JSON 을 그대로 실어 보내고, 수신도 같은 스키마로 inbox 에 적재 → 플랫폼 독립.
`cycle_id` 가 분산된 작업을 하나의 제품 사이클로 묶는 키 (productmgr 의 product-cycle id 와 연결).

> **수정 (2026-09-17, F019 에스컬레이션)** — 계약 검증은 **양방향**이다.
>
> 원문은 `send` 검증만 명시하고 수신 검증은 어느 문장도 요구하지 않았다. 그런데 값을
> **공격자가 정하는 쪽은 수신**이다. 그 결과 구현은 egress 만 지켰고, 리뷰 3라운드의
> MUST 가 전부 수신 경계에서 나왔다 (경로 탈출 · 큐 영구 wedge · 메시지 소멸).
>
> 필드별로 **누가 이 값을 정하는가**를 명시한다:
>
> | 필드 | 발신 시 | 수신 시 | 비고 |
> |---|---|---|---|
> | `from_team` / `to_team` | 운영자 | **원격** | 파일명 성분 + 지목 필터 키 |
> | `role` / `cycle_id` | 운영자 | **원격** | product-cycle 라우팅 키 |
> | `msg` / `stage` | 운영자 | **원격** | 본문 |
> | `ts` | 로컬 시계 | **원격** | 파일명 선두 — 탈출 위험이 가장 컸던 자리 |
>
> **원격이 정하는 값이 파일명·경로·라우팅 키가 되는 지점**이 신뢰 경계다.
> 수신은 복원한 계약에 `_validate_message` 를 걸고, 파일명 성분은 화이트리스트로
> 거르며(`_safe_component`), 파일 생성은 배타 생성으로 유일성을 보장한다(`_write_unique`).
> `_safe_component` 는 파일명만 지킨다 — 라우팅 키는 계약 검증이 지킨다.

### 결정 4 — 팀 내부는 single-host, 팀 사이만 메시지 계약
각 팀 노드 내부는 자기 하네스의 Task 오케스트레이션(d-1, 같은 컨텍스트 풀). 팀 **사이**만
계약 메시지로 느슨하게 연결. → d-3 의 분산은 "팀 경계"에서만 발생, 팀 내부는 검증된 d-1 패턴 재사용.

### 결정 5 — `/project:consortium`: 멀티팀 product-cycle
PM(주관 팀)이 product-cycle 로 brief·성공지표 정의 → 단계를 팀에 분배 → `consortium send`(cycle_id
로 묶음) → 각 팀이 자기 단계 수행(로컬 `product-cycle --from=<stage>`) → 결과 회신 → PM 통합 게이트.

### 결정 6 — 격리: LINT-MR-12
nw 오버레이(`consortium.py`, `consortium.md`, `state/consortium/`)는 **claude.productnw 에만** 존재.
다른 10 변형에 누수 시 BLOCK. `lint.py check --only=LINT-MR` (MR-12) 가드.

### 결정 7 — 외부 의존성: productmgr/hermes 상속 (nw 오버레이는 stdlib/문서만)
consortium.py 는 stdlib only(json/argparse/urllib/pathlib). 게이트웨이도 **stdlib 폴링으로 실구현**
했으므로 변형 자체엔 신규 의존성 0 이다 (2026-09-19 개정 — 원문은 외부 SDK 가 필요하다고
보았으나 그건 푸시 수신에만 해당했다). wiki/hermes 상속분(Obsidian/qmd/Marp)만 허용.

## d-3 제약 (정직한 명시)

- **컨텍스트 전달 손실**: 팀 간엔 같은 컨텍스트 풀이 없다 → 메시지에 brief·성공지표를 충분히 실어야 함
  (single-host 의 암묵 공유 불가). 명시 전달만이 표준.
- **인증 경계**: 게이트웨이 = 외부 메시징 = #3-A. 토큰·봇 등록은 사용자 승인·다운스트림 책임.
- **결과적 일관성**: 비동기 큐 — 즉시성·순서 보장 없음. cycle_id 로 추적.
- **검증 범위**: 로컬 큐 + Slack★/Teams/OpenClaw **mock 왕복** E2E 검증 완료(42건).
  **실제 워크스페이스 연동은 미검증** — 자격증명이 사용자 소유라 우리가 돌려 볼 수 없다
  (d-2 의 localllm 이 32B 환경을 다운스트림에 위임한 것과 같은 정직한 경계).

## 대안 검토

| 옵션 | 장점 | 단점 |
|---|---|---|
| (A) **새 변형 + 계약/로스터/큐 + 게이트웨이 (채택)** | 정직, 즉시 검증 가능, 격리 | 자격증명 발급은 다운스트림 |
| (B) Teams/Slack/Telegram 봇 풀스택 구현 | "완전" 동작 | 자격증명#3-A·외부SDK·서버 — 하네스 범위 밖, 유지보수 부담 |
| (C) d-3 보류 유지 (ADR-008 그대로) | 단순 | 사용자의 멀티팀 컨소시엄 요구 미충족 |

→ **(A) 채택**. codex/openclaw stub·localllm d-2 위임과 일관된 정직한 경계 설정.

## 결과
- 신규: `consortium.py`, `consortium.md`, `state/consortium/`, 이 ADR, LINT-MR-12.
- 상속 재사용: productmgr 의 product-cycle + 8 에이전트 + orchestrate/plan-full.
- 2026-09-19 개정: Slack★/Teams 폴링 transport 를 **실구현**했다 (ADR-013 결정 5).
  미이식으로 남는 것은 **자격증명 발급**과 Slack 푸시(Events API/Socket Mode)뿐이다.
