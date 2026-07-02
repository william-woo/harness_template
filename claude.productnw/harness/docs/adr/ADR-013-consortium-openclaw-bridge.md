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
  핸드오프 디렉토리 2종, 이 ADR, 설치 가이드 §9.
- 변경: `gateway teams --send/--receive` 가 host 에 따라 transport 분기. self-check 에 host/transport 표시.
- 미구현(다운스트림): OpenClaw courier 의 실제 채널 I/O 바인딩 (ACP/Gateway 도구) — 모킹으로 왕복 검증함.
