# ADR-013: consortium 게이트웨이 transport 추상화 + OpenClaw 채널 브리지

> Feature: F019 (확장) — claude.productnw 컨소시엄 게이트웨이 host-aware 화
> 상태: `Accepted` (구현 — host 별 transport 분기 + OpenClaw 핸드오프 브리지)
> 관련: ADR-012(consortium d-3), ADR-001(host 어댑터), ADR-009(opencode 어댑터)

## 맥락

ADR-012 의 consortium 게이트웨이는 Teams 를 **Incoming Webhook(발신) + Graph 폴링(수신)** 으로
직접 구현했다. 이는 **claude-code host 에 채널 개념이 없어서** 우리가 직접 plumbing 한 것이다.

그런데 host 가 **OpenClaw** 면 그림이 달라진다 (웹 조사 / docs.openclaw.ai):
- OpenClaw 는 Teams/Slack/Telegram 등 **20+ 채널을 네이티브 지원** (로컬 Gateway 데몬이 지속 연결).
- inbound 채널 → 격리 에이전트 워크스페이스 라우팅, 답장은 conversation reference 로 원 스레드 복귀.
- 즉 OpenClaw 의 *"채널↔에이전트 라우팅"* 이 우리 컨소시엄의 *"팀 간 메시지↔에이전트"* 와 같은 일을 한다.

→ OpenClaw host 에서 우리 webhook/Graph 코드를 **다시 짜는 건 낭비이자 중복**이다. OpenClaw Gateway 에
**위임**하고, consortium 은 그 위에 **계약·cycle 의미론**만 얹어야 한다.

## 결정

### 결정 1 — 게이트웨이를 host-aware 로: transport 를 host 가 고른다
consortium 의 송수신은 **transport** 로 분리하고, host(`HARNESS_AGENT_TYPE` > `.claude/host.json`
agent_type > 기본 claude-code)에 따라 선택한다:

| host | transport | 비고 |
|---|---|---|
| `claude-code` / `codex` | **webhook+Graph** (ADR-012) | 채널 없는 host → 직접 plumbing |
| `openclaw` | **채널 핸드오프 브리지** (이 ADR) | OpenClaw Gateway 에 위임 |

> 과잉 추상화 금지(Karpathy): 클래스 계층 대신 host 분기 + 함수(`_send_teams`/`_send_openclaw`)로 단순 유지.

> **범위 정정 (2026-09-17, F019 에스컬레이션)** — 이 결정은 **발신에만** 적용된다.
> 결정을 번복하는 것이 아니라 적용 범위를 좁히는 것이므로 Superseded 로 올리지 않는다.
>
> 발신은 host 별로 **진짜 다르다** (HTTP POST vs 파일 드롭). 수신은 바이트를 어디서
> 가져오는가만 다르고, 그 뒤 6단계(봉투 복원 → 형식 확인 → 지목 필터 → status 각인 →
> 안전 파일명 → 기록)가 동일하다. 그런데 이 결정을 수신에도 대칭 적용해
> `_receive_teams` / `_receive_openclaw` 두 벌로 복제했다.
>
> **대가**: 신뢰 불가 입력을 다루는 경계가 2개가 되면서 "결함의 클래스를 닫는다"가
> **주소를 갖지 못했다**. 리뷰어는 자기가 찔러본 사본만 보고하고, 수정은 그 사본에만
> 갔다. 실측 증거 — 3차 MUST 의 `except Exception` 수정이 `_receive_openclaw` 에만
> 적용되고 `_receive_teams` 는 열거형으로 남아 같은 `RecursionError` 로 뚫렸다.
> 클래스를 닫으려던 수정조차 인스턴스만 닫은 것이다.
>
> **따라서 수신은 단일 경계 + host 별 fetch 로 한다**: `_ingest_record()` 하나가
> 계약 검증·파일명 위생·유일성을 소유하고, `_receive_*` 는 "후보 레코드를 가져온다" +
> 성공 후 장부(seen 기록 vs 파일 이동)만 남긴다.
>
> **예외 격리는 호출자에 둔다** — `_ingest_record` 가 아니라 두 `_receive_*` 의
> per-item `except Exception` 이다. 격리 **동작**(quarantine 이동 vs seen 기록 후 건너뜀)이
> transport 마다 다르기 때문이다. 경계 함수는 `RejectedRecord` 를 올리고, 무엇을 할지는
> 장부를 소유한 쪽이 정한다. 두 호출자가 **같은 형태**(`except Exception`)를 쓰는지는
> `ReceiveBoundaryParityTest` 가 같은 악성 입력을 양쪽에 태워 잠근다.
> 같은 연산의 사본이 2개가 되는 순간이 Simplicity First 의 "2곳 이상이면 추출"
> 발동 시점이다 — 추측 추상화가 아니라 **사후 추출**이라 원칙에 어긋나지 않는다.

### 결정 2 — OpenClaw 브리지 = 핸드오프 디렉토리 계약 (consortium ↔ OpenClaw 에이전트)
OpenClaw 에이전트(= Claude Code 등 백엔드, bash/python 실행 가능)가 **courier** 역할을 한다.
consortium 과 OpenClaw 에이전트 사이의 interop 경계는 **두 핸드오프 디렉토리**다:

- **outbound** `state/consortium/openclaw-outbound/` — consortium 이 보낼 메시지를 채널 핸드오프
  레코드로 적재 → OpenClaw 에이전트가 읽어 자기 **채널 reply 도구**로 전송.
- **inbound** `state/consortium/openclaw-inbound/` — OpenClaw 가 채널에서 받은 메시지를 여기 드롭
  → consortium 이 계약 봉투를 복원해 `inbox/` 로 적재 (지목 필터 + 멱등).

핸드오프 레코드는 ADR-012 의 **base64 계약 봉투**(`[[consortium-msg]]`)를 그대로 운반하므로
무손실이다. `conversation_ref` 를 함께 실어 OpenClaw 가 **원 스레드로 답장 복귀**하게 한다.

### 결정 3 — 정직한 경계: 매핑은 실재, OpenClaw I/O 바인딩은 courier 몫
- consortium 쪽 **계약↔핸드오프 매핑 + 라우팅(지목/멱등)** 은 **stdlib 로 실재 구현·테스트**된다.
- 핸드오프 레코드를 **실제 OpenClaw 채널로 싣고 내리는 courier**(OpenClaw 에이전트의 채널 도구 호출,
  또는 Gateway 플로/ACP)는 **OpenClaw 런타임에 바인딩**된다 — Teams stub→real 진행과 같은 seam.
- 같은 머신/공유 볼륨에서 courier 를 모킹하면 **완전 왕복을 검증**할 수 있다 (실 OpenClaw 는 다운스트림).

### 결정 4 — 격리: consortium 이 host 를 알되, host 어댑터는 consortium 을 모른다
host 감지는 consortium.py 가 `.claude/host.json` 을 **읽기만** 한다. base 의 openclaw 어댑터
(`host_adapters/openclaw.py`)에 consortium 개념을 넣지 않는다 → LINT-MR 격리 유지.
nw 오버레이(consortium.py/관련 문서)는 여전히 claude.productnw 전용.

## 대안 검토

| 옵션 | 장점 | 단점 |
|---|---|---|
| (A) **host 분기 + OpenClaw 핸드오프 브리지 (채택)** | 중복 제거, OpenClaw 네이티브 활용, 격리 유지 | courier 바인딩은 다운스트림 |
| (B) OpenClaw 에서도 webhook/Graph 재사용 | 코드 1벌 | OpenClaw Gateway 와 중복·충돌, 봇 2개 등록 |
| (C) consortium 을 OpenClaw 플러그인으로 재작성 | 완전 네이티브 | productnw 변형/계약 레이어 폐기 — 과대 |

→ **(A) 채택**. codex/opencode 어댑터·Teams stub→real 과 일관된 정직한 seam.

## 결과
- 신규: `_detect_host()` + `_send_openclaw()`/`_receive_openclaw()` (consortium.py),
  핸드오프 디렉토리 2종, 이 ADR, 설치 가이드 §10.
- 변경: `gateway teams --send/--receive` 가 host 에 따라 transport 분기. self-check 에 host/transport 표시.
- 미구현(다운스트림): OpenClaw courier 의 실제 채널 I/O 바인딩 (ACP/Gateway 도구).
  브리지 왕복(outbox → openclaw-outbound → courier → openclaw-inbound → inbox)은
  `tests/test_consortium_gateway.py::OpenClawBridgeRoundTripTest` 가 실제로 태운다 —
  courier 자리만 파일 이동으로 대체하고 나머지는 실제 코드다.

---

## 결정 5 — 권장 transport 를 Slack 으로 (2026-09-19)

> **정정 이력**: 이 결정은 처음 Telegram 을 권장으로 적었다가 **같은 날 뒤집었다**.
> 무엇을 틀렸는지 남긴다 — 틀린 이유가 다음 사람에게 더 쓸모 있다.

**맥락**: F019 는 Teams 를 먼저 구현했다(사내 표준). 그런데 "컨소시엄을 실제 메신저로
한번 돌려 보자" 는 사람에게 Teams 는 비싼 첫 관문이다 — Azure AD 앱 등록,
`ChannelMessage.Read.All` **관리자 동의**, 자격증명 4개.

**첫 판단(틀림)**: 설정이 가장 싼 Telegram 을 골랐다. 근거는 "토큰 하나로 발신·수신이
모두 된다" 였다. **두 가지를 확인하지 않았다.**

1. **Telegram 봇은 다른 봇의 글을 보지 못한다.** Bot FAQ: *"Bots talking to each
   other could potentially get stuck in unwelcome loops. To avoid this, we decided
   that bots will not be able to see messages from other bots **regardless of
   mode**."* `/setprivacy` 를 꺼도 안 된다. 봇은 자기가 보낸 것도 되받지 못한다.
   → "팀마다 봇을 만들어 같은 그룹에 넣는" 토폴로지가 **성립하지 않는다**.
   컨소시엄은 에이전트↔에이전트인데, Telegram 은 그 한 가지를 못 한다.
2. **Slack 을 잘못 배제했다.** "수신에 공개 엔드포인트나 Socket Mode SDK 가 필요"
   하다고 적었는데 그건 **푸시**(Events API) 얘기다. `conversations.history` **폴링**은
   평범한 HTTPS GET 이고, 채널 **로그를 읽는** API 라 `bot_id` 가 붙은 다른 봇의
   메시지가 그대로 들어온다. Teams 의 Graph 폴링과 같은 모양이다.

**어떻게 놓쳤나**: mock 이 가렸다. `_MockTelegram.getUpdates` 가 **작성자와 무관하게**
모든 update 를 돌려줘, 실제 Telegram 이 금지하는 동작을 흉내 냈다. 왕복 테스트 5건이
전부 통과했고 그래서 "권장" 주장의 근거처럼 보였다. 이 파일이 이미 배운 교훈
("통과하는 테스트가 결함 부재의 증거는 아니다")의 **플랫폼 버전**이다.
지금 mock 은 규칙을 강제하고, `test_봇이_보낸_메시지는_다른_봇이_받지_못한다` 가 그 전제를 잠근다.

**결정**: `slack` 을 **권장 transport** 로 삼고 발신(`chat.postMessage`) + 수신
(`conversations.history` 폴링)을 실구현한다.

| | Slack ★ | Teams | Telegram |
|---|---|---|---|
| **봇↔봇 가시** | ✅ | ✅ | ❌ 플랫폼 금지 |
| 자격증명 | 토큰 1개 + 채널 id | 4개 | 토큰 1개 + chat id |
| 승인 | 워크스페이스 관리자 | 테넌트 관리자 동의 | 없음 |
| stdlib only | ✅ | ✅ | ✅ |
| 컨소시엄 적합 | ✅ | ✅ | ❌ |

**Telegram·Teams 를 제거하지 않는다**: Teams 는 사내 표준인 조직에 필요하고 5라운드
리뷰로 굳혔다. Telegram 은 **사람이 끼는 흐름**(에이전트가 사람에게 알리고, 사람이
지시를 준다)에는 여전히 유효하므로 그 범위로 좁혀 남겼다 — 할 수 없는 것을 할 수
있다고 적지 않는 것이 이 파일의 규율이다.

**세 transport 는 같은 수신 경계를 쓴다** — `_ingest_record` (결정 1 정정).
`ReceiveBoundaryParityTest` 가 **같은 악성 입력 5종을 세 transport 에** 태워 잠근다.
transport 별 사본 테스트를 만들면 테스트가 같은 병에 걸린다 — 실제로 Slack 을 이
parity 에 등재하자마자 사본 테스트가 놓쳤을 결함(보존 실패 시 `break` 로 뒤의 정상분이
막힘)이 즉시 잡혔다.

**수신 범위를 자격증명으로 못 박는다**: Slack 은 `conversations.history` 가 채널 id 를
요구하므로 구조적으로 그 채널만 읽는다. Telegram 은 `getUpdates` 가 봇이 속한 **모든**
채팅을 주므로 `--receive` 에도 chat id 를 **필수**로 요구해 필터한다 — 없으면 낯선
사용자의 DM 이 계약 검증을 통과해 라우팅 키로 흘러간다(실측).

**cursor/offset 은 "보존 또는 처리된 접두" 까지만 전진한다**: Telegram 의 offset 전진은
서버에 **확인(ack)** 이라 그 update 가 지워진다. 처리에 실패한 것을 그냥 전진시키면
원본이 어디에도 남지 않는다(실측 소실). 실패분 원본을 `*-quarantine/` 에 보존하고,
보존까지 실패하면 그 지점부터 cursor 를 **동결**한다 — 루프는 계속 돌려 뒤의 정상분을
막지 않는다.

**검증 범위**: mock Web API 로 Slack 왕복 4건 + parity 5종 실측. **실제 Slack 앱 연동은
미검증** (자격증명은 사용자 소유 — d-3 경계). 설치 절차는 `docs/consortium-gateway-setup.md §2`.

**본문 상한**: Telegram 은 4096자를 넘으면 **거부**하고 outbox 에 남긴다. 봉투가 잘리면
수신측이 복원하지 못한다 — 조용한 손상보다 시끄러운 거부를 택한다.
