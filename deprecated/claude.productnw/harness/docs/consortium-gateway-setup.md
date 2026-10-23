# 컨소시엄 게이트웨이 설치 가이드 — Slack · OpenClaw 브리지

> `consortium.py` 의 **게이트웨이 transport** 를 Slack 에 연결하는 설치 절차.
> **§2 만 읽으면 된다** — 10분. §3 은 host 가 OpenClaw 일 때의 위임 경로다.
> 관련: [consortium.md](../.claude/commands/consortium.md) · [ADR-012](adr/ADR-012-consortium-distribution.md) · [ADR-013](adr/ADR-013-consortium-openclaw-bridge.md)

---

## 0. 무엇을 연결하는가 (정직한 범위)

`consortium.py` 는 메시지 계약 + 로스터 + 로컬 큐(inbox/outbox)를 stdlib 로 **실재 구현**한다.
게이트웨이는 그 큐를 외부 메신저로 나르는 **transport** 다.

### 왜 Slack 하나인가

컨소시엄은 **에이전트↔에이전트** 통신이다. 그래서 첫 질문은 하나다 —
**봇이 다른 봇의 글을 볼 수 있는가.**

Slack 의 `conversations.history` 는 이벤트 구독이 아니라 채널 **로그를 읽는** API 라
다른 앱/봇이 남긴 글이 그대로 들어온다. 평범한 HTTPS 폴링이므로 공개 엔드포인트도
Socket Mode SDK 도 필요 없다 — stdlib `urllib` 로 완결된다. 자격증명은 봇 토큰 1개 +
채널 id 로 끝나고, 설정은 10분이면 된다.

> **Teams·Telegram 은 2026-09-23 에 제거했다.**
>
> Telegram 은 애초에 **필요한 일을 못 했다** — Bot FAQ: *"bots will not be able to
> see messages from other bots **regardless of mode**"*. privacy mode 를 꺼도 안 되고,
> 팀마다 봇을 두는 토폴로지가 성립하지 않는다.
>
> Teams 는 기능은 동등했지만(Graph 폴링) 자격증명 4개 + Azure AD 앱 등록 + 테넌트
> 관리자 동의가 필요했다. 제거한 진짜 이유는 비용이 아니라 **유지 실패**다: 9차 리뷰의
> MUST 3건이 전부 "Slack 에 들어간 수정이 Teams·Telegram 장부 갱신에는 가지 않았다"
> 였다 — 보존 실패 후 offset ack(소실) · quarantine 부재(소실) · `$top=50` nextLink
> 미추적(소실). 셋 다 rc=0 이라 cron 은 성공으로 봤다.
>
> 경로를 셋 유지하는 값보다 **셋을 같은 수준으로 유지하는 비용**이 컸다. 되살릴 때는
> 장부 갱신까지 parity 테스트로 잠근 뒤 들여온다.

| 방향 | 상태 |
|---|---|
| **발신** outbox → Slack | ✅ 실구현 (`gateway slack --send`) |
| **수신** Slack → inbox | ✅ 실구현 (`gateway slack --receive [--poll N]`) |

둘 다 갖추면 **에이전트↔에이전트 완전 자동 왕복**이 된다
(A→메신저→B 수신→B 답변→메신저→A 수신). 자격증명 발급은 사용자/다운스트림 책임 (d-3 경계).

---

## 1. 사전 준비

- 이 하네스 (`consortium.py`, Python 3.8+, **외부 패키지 0** — stdlib `urllib` 만 사용)
- `slack.com` 으로의 HTTPS egress
- Slack 앱 생성 + 워크스페이스 설치 승인 권한

---

## 2. Slack — 설치 (10분)

### 2-1. Slack 앱 만들고 스코프 주기

1. https://api.slack.com/apps → **Create New App** → **From scratch** → 이름·워크스페이스 선택
2. 좌측 **OAuth & Permissions** → *Bot Token Scopes* 에 **두 개**를 추가
   - `chat:write` — 발신
   - `channels:history` — 수신 (비공개 채널이면 `groups:history`)
3. 상단 **Install to Workspace** → 승인 → **Bot User OAuth Token** 복사 (`xoxb-` 로 시작)

> 워크스페이스 관리자가 아니면 설치 승인 요청이 간다. Teams 의 테넌트 관리자 동의보다
> 가볍지만 **무승인은 아니다** — 조직 정책에 따라 대기가 생길 수 있다.

### 2-2. 채널 만들고 봇 초대 + 채널 id 확보

컨소시엄은 팀들이 **한 채널**을 공유한다.

1. 채널 생성 (예: `#consortium`) → 채널에서 `/invite @<봇이름>`
2. 채널 id 확인 — 채널명 클릭 → 맨 아래 **Channel ID** (`C` 로 시작).
   또는 브라우저 URL `.../archives/C0123ABCD` 의 마지막 토큰.

> **이름이 아니라 id** 를 쓴다. 이름은 바뀌지만 id 는 안 바뀐다.

### 2-3. 자격증명 안전 보관 (autonomous #3-A)

**리포 안에 두지 않는다.** 홈 디렉토리에 600 권한으로 둔다:

```bash
mkdir -p ~/.config/consortium && chmod 700 ~/.config/consortium
printf '%s\n' 'xoxb-PASTE-TOKEN-HERE' > ~/.config/consortium/slack_token.txt
printf '%s\n' 'C0123ABCD'             > ~/.config/consortium/slack_channel.txt
chmod 600 ~/.config/consortium/slack_*.txt
```

> 토큰을 **명령줄 인자로 주지 않는다** — 셸 히스토리와 `ps` 출력에 남는다.

### 2-4. 왕복 테스트

```bash
# (1) 이 노드를 팀으로 등록
python3 .claude/bin/consortium.py init team-alpha --agents developer,reviewer --gateway slack

# (2) 팀 간 메시지를 outbox 에 만든다 (계약 검증이 여기서 걸린다)
python3 .claude/bin/consortium.py send --to team-beta --role developer \
  --cycle PCYC-01 --stage develop --msg "설계 완료, 구현 요청"

# (3) 발신 — 자격증명은 파일에서 읽어 환경변수로만
CONSORTIUM_SLACK_TOKEN="$(< ~/.config/consortium/slack_token.txt)" \
CONSORTIUM_SLACK_CHANNEL="$(< ~/.config/consortium/slack_channel.txt)" \
  python3 .claude/bin/consortium.py gateway slack --send

# (4) 수신 — 상대 팀 노드에서 (같은 채널, 다른 team-id 로 init 된 상태)
CONSORTIUM_SLACK_TOKEN="$(< ~/.config/consortium/slack_token.txt)" \
CONSORTIUM_SLACK_CHANNEL="$(< ~/.config/consortium/slack_channel.txt)" \
  python3 .claude/bin/consortium.py gateway slack --receive

# (5) 상시 폴링 (에이전트 자동 왕복)
CONSORTIUM_SLACK_TOKEN="$(< ~/.config/consortium/slack_token.txt)" \
CONSORTIUM_SLACK_CHANNEL="$(< ~/.config/consortium/slack_channel.txt)" \
  python3 .claude/bin/consortium.py gateway slack --receive --poll 60
```

> `--poll` 은 **60초 이상**을 권한다 — Marketplace 미등재 앱의 history 제한이 분당 1회다.

### 기대 출력

```
[consortium] outbox 기록: .claude/state/consortium/outbox/2026...__to-team-beta.json
  ✅ team-alpha→team-beta cycle=PCYC-01 — ts=1758240000.000100
[consortium] Slack 발신 완료: 1/1 (성공분 → outbox/sent/)

  ⬇ team-alpha → team-beta [developer] cycle=PCYC-01: 설계 완료, 구현 요청
[consortium] Slack 수신 완료: 1건 inbox 적재 (미적재 0건 …, cursor=1758240000.000100)
```

### 2-5. 동작 규칙

- **봇이 쓴 글을 다른 봇이 본다** — `conversations.history` 는 이벤트 구독이 아니라
  **채널 로그 읽기**라 `bot_id` 가 붙은 메시지가 그대로 들어온다. 이것이 Telegram 이
  탈락하고 Slack 이 권장인 이유다 (§11 참조).
- **멱등**: 마지막 처리 `ts` 를 `.claude/state/consortium/slack-cursor.json` 에 기록하고
  다음 폴링에 `oldest` 로 넘긴다. cursor 는 **보존 또는 처리된 접두**까지만 전진한다 —
  처리에 실패한 메시지의 원본을 `slack-quarantine/` 에 남기지 못하면 그 지점부터
  cursor 를 **동결**해 다음 폴링이 다시 받게 한다 (소실 금지).
- **수신 범위**: 채널 id 를 `--receive` 에도 요구한다. API 가 그 채널만 읽으므로
  다른 채널·DM 이 주입구가 되지 않는다.
- **지목 필터**: 채널은 공유되므로 `to_team` 이 내가 아니거나 `from_team` 이 나면 무시한다.
- **계약 검증은 양방향**: 수신분도 `_validate_message` 를 통과해야 적재된다 (ADR-012 결정 3).
- **페이지네이션**: 한 폴링이 `next_cursor` 로 페이지를 **전부 모은 뒤** 처리한다.
  다 받지 못하면(네트워크 실패·페이지 50개 상한) 받은 것은 **처리하되**
  cursor 를 **동결**하고 `rc=2` 로 끝낸다 — 오래된 미수집 구간을 건너뛰지 않기 위해서다.
  재적재는 `slack-seen.json` 이 막는다. 최신 창은 매 폴링 흐르므로 백로그가 길어도
  **신규 메시지는 막히지 않는다**.
- **첫 폴링은 채널 전체 이력**을 훑는다(`oldest=0`). 이미 길게 쓰던 채널에 합류하면
  여러 회차에 걸쳐 따라잡는다. 건너뛰려면 시작점을 지정한다:
  `CONSORTIUM_SLACK_OLDEST="$(date +%s).000000"`
- **rate limit**: Slack 은 2025-05 부터 **Marketplace 미등재 앱**의
  `conversations.history` 를 **분당 1회·15건**으로 제한한다. §2-1 의 "From scratch" 로
  만든 내부 앱이 여기 해당하므로, 백로그를 따라잡는 데 시간이 걸린다.
  → `--poll` 간격을 **60초 이상**으로 두고, 긴 이력은 `CONSORTIUM_SLACK_OLDEST` 로 건너뛴다.
  (이 제한은 문서 기준이며 **실제 워크스페이스에서 미검증**이다 — d-3 경계.)

### 2-6. 트러블슈팅

| 증상 | 확인 |
|---|---|
| `자격증명 미설정` | `CONSORTIUM_SLACK_TOKEN` / `CONSORTIUM_SLACK_CHANNEL` 둘 다 주입했는지 |
| `API 거부: invalid_auth` | 토큰 오타 또는 앱 재설치 필요 — OAuth & Permissions 에서 재복사 |
| `API 거부: not_in_channel` | 봇을 채널에 초대하지 않았다 — `/invite @<봇>` |
| `API 거부: missing_scope` | `channels:history`(또는 `groups:history`) 누락 → 추가 후 **재설치** |
| `API 거부: channel_not_found` | 채널 **이름**을 넣었다. `C` 로 시작하는 id 를 쓴다 |
| 발신은 되는데 수신 0건 | 상대 팀 노드가 **다른 `team-id`** 로 init 됐는지. `to_team` 이 내 팀이어야 적재된다 |
| 같은 메시지가 반복 적재 | `slack-cursor.json`·`slack-seen.json` 손상/삭제 — 경고가 뜨고 처음부터 재시작한다 |
| `rc=2` / `⚠️ 페이지 미완` | 정상 동작이다 — 받은 것은 처리했고 오래된 구간이 남았다. 다음 폴링이 이어받는다 |
| `rc=2` 가 계속 반복 | ① 채널 이력이 길다 → `CONSORTIUM_SLACK_OLDEST` 로 시작점 이동 ② rate limit(비-Marketplace 앱은 분당 1회·15건) → `--poll` 간격을 60초 이상으로 ③ 네트워크 불안정 |
| 수신이 0건에서 안 늘어남 | 백로그가 상한(50페이지)을 넘었는지 확인. 신규 메시지는 그래도 도착해야 한다 — 안 오면 `to_team`·채널 id 를 먼저 본다 |

---

## 3. OpenClaw host — 네이티브 채널 브리지 (ADR-013)

§2 는 **claude-code/codex host** 기준(우리가 Slack API 를 직접 호출). 그런데 host 가
**OpenClaw** 면 OpenClaw 가 Slack 을 포함한 **20+ 채널을 네이티브 지원**(로컬 Gateway
데몬, 채널↔에이전트 라우팅)하므로, 우리 HTTP 호출을 다시 짜지 않고 **OpenClaw 에 위임**한다.

이것은 **메신저 선택지가 아니다** — 같은 Slack 채널로 가는 다른 길이다.
consortium 게이트웨이는 **host-aware** 다 (`HARNESS_AGENT_TYPE` > `host.json` agent_type):

| host | transport |
|---|---|
| `claude-code` / `codex` | Slack `chat.postMessage`(발신) + `conversations.history` 폴링(수신) — §2 |
| `openclaw` | **핸드오프 브리지** — OpenClaw Gateway(에이전트=courier)에 위임 |

**두 경로는 같은 수신 경계**(`_ingest_record`)를 지난다 — 계약 검증·파일명 위생·유일성
보장이 경로와 무관하게 동일하게 걸리고, `ReceiveBoundaryParityTest` 가 같은 악성 목록을
둘 다에 태운다.

### 3-1. 동작 구조

consortium 과 OpenClaw 에이전트(courier) 사이의 경계는 **두 핸드오프 디렉토리**다:

```
state/consortium/openclaw-outbound/   consortium → OpenClaw (채널로 발신할 메시지)
state/consortium/openclaw-inbound/    OpenClaw → consortium (채널에서 받은 메시지)
```

- `gateway <channel> --send` (host=openclaw) → outbox 메시지를 **openclaw-outbound/** 에 핸드오프
  레코드(채널·conversation_ref·본문+base64 계약 봉투)로 적재.
- OpenClaw 에이전트(courier)가 이를 읽어 **자기 채널 reply 도구**로 실제 채널에 전송
  (답장은 OpenClaw 가 conversation_ref 로 원 스레드에 복귀).
- 반대로 OpenClaw 가 채널에서 받은 메시지를 **openclaw-inbound/** 에 드롭하면,
  `gateway <channel> --receive` 가 계약을 복원해 `inbox/` 로 적재 (지목 필터 + processed/ 멱등).

### 3-2. 사용

```bash
export HARNESS_AGENT_TYPE=openclaw   # 또는 .claude/host.json 의 agent_type=openclaw
python3 .claude/bin/consortium.py gateway slack --send       # → openclaw-outbound/
python3 .claude/bin/consortium.py gateway slack --receive    # openclaw-inbound/ → inbox
python3 .claude/bin/consortium.py self                       # host=openclaw transport 확인
```

OpenClaw 채널 설정(`~/.openclaw/openclaw.json`·토큰·터널)은 OpenClaw 문서를 따른다:
- 공식: https://docs.openclaw.ai/channels

### 3-3. courier 바인딩 (정직한 경계)

- consortium 쪽 **계약↔핸드오프 매핑 + 지목/멱등 라우팅** 은 stdlib 로 **실재·테스트**됨.
- 핸드오프 레코드를 **실제 OpenClaw 채널로 싣고 내리는 courier**(OpenClaw 에이전트의 채널 도구
  호출, 또는 Gateway 플로/ACP)는 OpenClaw 런타임에 바인딩 — §2 의 Slack 자격증명과 같은 seam.
- courier 를 모킹한 **완전 왕복이 테스트로 실재**한다 —
  `tests/test_consortium_gateway.py` (Slack 왕복 + OpenClaw 브리지 + 수신 경계 parity, 26건).
  실 OpenClaw·실 Slack 워크스페이스 연결은 다운스트림 몫.

---
