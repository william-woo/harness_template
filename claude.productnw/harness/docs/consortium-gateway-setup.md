# 컨소시엄 게이트웨이 설치 가이드 — Slack(권장) · MS Teams · OpenClaw · Telegram

> `consortium.py` 의 **게이트웨이 transport** 를 실제 메신저에 연결하는 설치 절차.
> **처음이라면 §2 Slack 만 읽으면 된다** — 10분. 컨소시엄(에이전트↔에이전트)에
> 실제로 쓸 수 있는 가장 싼 경로다.
> 관련: [consortium.md](../.claude/commands/consortium.md) · [ADR-012](adr/ADR-012-consortium-distribution.md) · [ADR-013](adr/ADR-013-consortium-openclaw-bridge.md)

---

## 0. 무엇을 연결하는가 (정직한 범위)

`consortium.py` 는 메시지 계약 + 로스터 + 로컬 큐(inbox/outbox)를 stdlib 로 **실재 구현**한다.
게이트웨이는 그 큐를 외부 메신저로 나르는 **transport** 다.

### 어느 메신저를 고를까

컨소시엄은 **에이전트↔에이전트** 통신이다. 그래서 첫 질문은 하나다 —
**봇이 다른 봇의 글을 볼 수 있는가.** 이것이 선택을 가른다.

| | **Slack ★권장** | MS Teams | Telegram |
|---|---|---|---|
| **봇↔봇 가시** | ✅ `conversations.history` 는 채널 **로그 읽기** | ✅ Graph 폴링 | ❌ **플랫폼이 금지** |
| 발신 | ✅ `chat.postMessage` | ✅ Incoming Webhook | ✅ `sendMessage` |
| 수신 | ✅ history 폴링 | ✅ Graph 폴링 | ⚠️ **사람이 쓴 것만** |
| 자격증명 | 토큰 1개 + 채널 id | 4개 | 토큰 1개 + chat id |
| 앱 등록 | Slack 앱 생성 | Azure AD 앱 등록 | 없음 |
| 승인 | 워크스페이스 관리자 | **테넌트 관리자 동의** | 없음 |
| 설정 시간 | **~10분** | ~30분 + 승인 대기 | ~5분 |
| 컨소시엄 적합 | ✅ | ✅ | ❌ (§11 — 사람 연동 전용) |
| 절차 | **§2** | §3~§9 | §11 |

**Telegram 은 탈락한다.** Bot FAQ 가 명시한다 — *"bots will not be able to see
messages from other bots **regardless of mode**"*. privacy mode 를 꺼도 안 되고,
봇은 자기가 보낸 것도 되받지 못한다. 팀마다 봇을 두는 토폴로지가 성립하지 않는다.
설정이 가장 쉽지만 **필요한 일을 못 한다**. (발신 + 사람 지시 수신은 되므로 §11 에 남겼다.)

**Slack 이 권장인 이유**: `conversations.history` 는 이벤트 구독이 아니라 채널
로그를 읽는 API 라 다른 앱/봇이 남긴 글이 그대로 들어온다. 평범한 HTTPS 폴링이므로
공개 엔드포인트도 Socket Mode SDK 도 필요 없다 — Teams 의 Graph 폴링과 같은 모양인데
자격증명이 적고 관리자 동의가 가볍다.

> 사내 표준이 Teams 인 조직은 §3~§9 를 그대로 쓰면 된다 — 기능은 동등하고
> 비용만 다르다. **세 경로 모두 같은 수신 경계**(`_ingest_record`)를 지나므로
> 계약 검증·파일명 위생·유일성 보장이 동일하게 걸린다.

| 방향 | 상태 |
|---|---|
| **발신** outbox → 메신저 | ✅ 실구현 (`gateway <slack\|teams\|telegram> --send`) |
| **수신** 메신저 → inbox | ✅ 실구현 (`gateway <slack\|teams> --receive [--poll N]`) |

둘 다 갖추면 **에이전트↔에이전트 완전 자동 왕복**이 된다
(A→메신저→B 수신→B 답변→메신저→A 수신). 자격증명 발급은 사용자/다운스트림 책임 (d-3 경계).

---

## 1. 사전 준비

- 이 하네스 (`consortium.py`, Python 3.8+, **외부 패키지 0** — stdlib `urllib` 만 사용)
- 메신저로의 HTTPS egress
  - Slack: `slack.com`
  - Telegram: `api.telegram.org` (§11 — 사람 연동 전용)
  - Teams: `*.webhook.office.com` 또는 `*.logic.azure.com` + `graph.microsoft.com`
- Slack 은 앱 생성 + 워크스페이스 설치 승인이 필요하다. Teams 는 채널에 커넥터/Workflows 를 추가할 권한 +
  Azure AD 앱 등록 권한(수신용)이 필요하다.

---

## 2. Slack — 권장 경로 (10분)

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
  python3 .claude/bin/consortium.py gateway slack --receive --poll 20
```

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
- **rate limit**: 앱을 Slack Marketplace 에 배포하지 말고 **워크스페이스 내부 앱**으로
  두십시오. 비-Marketplace 앱은 `conversations.history` 가 **분당 1회·15건**으로
  제한되어(2025-05 변경) 백로그를 따라잡는 데 오래 걸립니다.

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

## 3. Teams 웹훅 URL 발급

Microsoft 가 구형 Office 365 Connectors 를 단계적으로 폐기 중이라 **방법 A(Workflows)** 가 현재 표준이다.
테넌트에 따라 둘 중 가능한 쪽을 쓰면 된다.

### 방법 A — Workflows (현재 권장)

1. Teams 에서 대상 **채널** → 채널명 옆 **⋯ (More options)** → **Workflows**
   (또는 좌측 **Apps** 에서 **Workflows** 앱 추가)
2. 템플릿 검색: **"Post to a channel when a webhook request is received"** 선택
3. 워크플로 이름 지정 → 게시할 **팀/채널** 선택 → **Create / Add**
4. 생성 완료 화면에 표시되는 **HTTP POST URL** 을 복사 (이게 웹훅 URL)
   - 형태: `https://prod-XX.<region>.logic.azure.com:443/workflows/.../triggers/manual/paths/invoke?...&sig=...`
5. (선택) 워크플로 편집에서 게시 메시지가 수신 JSON 의 어떤 필드를 참조하는지 확인.
   기본 템플릿은 보통 본문 텍스트를 그대로 게시한다 — 본 어댑터는 페이로드에 top-level `text` 를
   함께 실으므로 대부분 그대로 렌더된다 (§6 호환성 참조).

### 방법 B — Incoming Webhook 커넥터 (구형 테넌트)

1. 채널 → **⋯ → Connectors** (Connectors 메뉴가 보이는 테넌트만 해당)
2. **Incoming Webhook** → **Configure**
3. 이름(예: `consortium`) 지정 → (선택) 아이콘 업로드 → **Create**
4. 생성된 **URL** 복사 — 형태: `https://<tenant>.webhook.office.com/webhookb2/...`

> Connectors 메뉴가 없으면 테넌트에서 비활성화된 것 — 방법 A 를 쓴다.

---

## 4. 웹훅 URL 안전 보관 (자격증명 — autonomous #3-A)

웹훅 URL 은 **그 자체가 비밀**이다 (URL 을 아는 누구나 그 채널에 글을 쓸 수 있음).
따라서:

- ❌ 채팅·이슈·커밋·로그·셸 히스토리에 붙여넣지 않는다
- ✅ git 에 안 들어가는 **파일**에 저장하고, 환경변수로 주입한다

```bash
mkdir -p ~/.config/consortium && chmod 700 ~/.config/consortium
# 에디터로 붙여넣거나 (히스토리에 안 남게):
printf '%s\n' 'PASTE_WEBHOOK_URL_HERE' > ~/.config/consortium/teams_webhook.txt
chmod 600 ~/.config/consortium/teams_webhook.txt
```

> 이 하네스의 `consortium.py` 는 `CONSORTIUM_TEAMS_WEBHOOK` **환경변수**에서만 웹훅을 읽는다.
> 코드·설정파일에 URL 을 하드코딩하지 않는다.

---

## 5. 발신 테스트

```bash
cd <하네스 루트>

# (1) 이 노드를 팀으로 등록 (gateway=teams)
python3 .claude/bin/consortium.py init team-alpha --gateway teams

# (2) 팀 간 메시지를 outbox 에 만든다 (계약 검증)
python3 .claude/bin/consortium.py send --from team-alpha --to team-beta \
  --role designer --cycle PCYC-01 --stage design \
  --msg "컨소시엄 Teams 연동 테스트"

# (3) 게이트웨이로 실제 발신 — 웹훅은 파일에서 읽어 환경변수로만 주입
CONSORTIUM_TEAMS_WEBHOOK="$(cat ~/.config/consortium/teams_webhook.txt)" \
  python3 .claude/bin/consortium.py gateway teams --send
```

### 기대 출력 / 확인

```
  ✅ team-alpha→team-beta cycle=PCYC-01 — HTTP 200 ...
[consortium] Teams 발신 완료: 1/1 (성공분 → outbox/sent/)
```

- ✅ 지정한 **Teams 채널에 카드/메시지가 게시**되면 성공.
- 발신 성공한 메시지는 `outbox/sent/` 로 이동 → 재실행해도 중복 발송 안 됨.
- 발신 페이로드의 본문에는 **base64 계약 봉투**(`[[consortium-msg]]...`)가 함께 실린다 — 사람은
  무시하지만 수신측(§9)이 이걸 스캔해 원본 메시지를 무손실 복원한다.

---

## 6. 페이로드 호환성

본 어댑터가 보내는 JSON 은 두 방식을 동시에 만족하도록 설계됐다:

- `@type: MessageCard` + `sections[].facts` → **구형 Connector** 가 제목·필드·본문 카드로 렌더
- top-level `text` → **Workflows** 템플릿이 흔히 참조하는 필드 (본문 텍스트)

Workflows 템플릿을 커스터마이즈해 다른 필드(`@{triggerBody()?['title']}` 등)를 참조한다면,
`consortium.py` 의 `_build_teams_card()` 가 만드는 키와 워크플로 매핑을 맞추면 된다.

---

## 7. 트러블슈팅

| 증상 | 원인 / 해결 |
|---|---|
| `CONSORTIUM_TEAMS_WEBHOOK 미설정` | §4 환경변수 주입 누락 — `cat` 으로 파일을 읽어 prefix 로 전달했는지 확인 |
| `HTTP 400` | 페이로드 형식 불일치 — Workflows 라면 §6 매핑 확인. URL 끝의 `&sig=...` 까지 정확히 복사했는지 |
| `HTTP 401/403` | 웹훅 만료·비활성화·서명(sig) 누락 — Teams 에서 URL 재발급 |
| `HTTP 404` | 워크플로/커넥터가 삭제됨 — 재생성 |
| `전송 실패: <URLError>` | 네트워크 egress 차단 (프록시/방화벽) — 사내망이면 프록시 설정 필요 |
| 메시지는 가는데 렌더가 깨짐 | §6 — Workflows 플로의 게시 카드가 다른 필드 참조 중. 플로 편집에서 `text` 참조로 변경 |

---

## 8. 보안·운영 메모

- 웹훅 URL 유출 시 누구나 채널에 글쓰기 가능 → **즉시 Teams 에서 URL 재발급(rotate)**.
- 발신/수신 자격증명(웹훅·토큰)은 **환경변수로만** 주입 — 코드·설정·로그·채팅 노출 금지.
- 발송량이 많으면 Teams 측 rate limit 가능 — 배치 발신 시 간격을 둔다 (현재 어댑터는 순차 발신).

---

## 9. 수신 — Graph API 폴링 (채널 → inbox)

발신의 역방향. Teams 채널 메시지를 **Microsoft Graph** 로 폴링해, consortium 계약 봉투(§5)를
가진 메시지만 골라 **나(이 팀)에게 온 것**을 `inbox/` 에 적재한다. 이게 채워지면 **완전 자동 왕복**
(A→Teams→B 수신→B답변→Teams→A 수신)이 된다. stdlib `urllib` 만 사용.

### 9-1. Azure 앱 등록 (1회)

1. [Azure Portal](https://portal.azure.com) → **Microsoft Entra ID → App registrations → New registration**
2. 이름 지정 → 등록. **Application (client) ID** + **Directory (tenant) ID** 기록
3. **API permissions → Add → Microsoft Graph**:
   - 봇처럼 무인 폴링 → **Application permission** `ChannelMessage.Read.All`
   - **Grant admin consent** 클릭 (관리자 동의 필수)
4. **Certificates & secrets → New client secret** → 값 복사 (한 번만 보임)

### 9-2. team / channel id 확보

- Teams 채널 → ⋯ → **Get link to channel** → URL 의 `groupId`(=team id) 와 `channelId` 추출, 또는
- Graph 탐색: `GET /me/joinedTeams` → team id, `GET /teams/{team-id}/channels` → channel id

### 9-3. 액세스 토큰 발급 (client credentials)

```bash
curl -s -X POST "https://login.microsoftonline.com/<TENANT_ID>/oauth2/v2.0/token" \
  -d "client_id=<CLIENT_ID>" \
  -d "client_secret=<CLIENT_SECRET>" \
  -d "scope=https://graph.microsoft.com/.default" \
  -d "grant_type=client_credentials" | python3 -c "import sys,json;print(json.load(sys.stdin)['access_token'])"
```
> 토큰은 보통 1시간 만료 → 폴링 루프를 길게 돌릴 땐 토큰 갱신 래퍼가 필요(다운스트림). 단발/단시간은 그대로.

### 9-4. 자격증명 주입 + 수신 실행

```bash
export CONSORTIUM_TEAMS_TOKEN="$(< ~/.config/consortium/teams_token.txt)"   # 위에서 받은 토큰
export CONSORTIUM_TEAMS_TEAM_ID='<team(group) id>'
export CONSORTIUM_TEAMS_CHANNEL_ID='<channel id>'

python3 .claude/bin/consortium.py gateway teams --receive          # 1회 폴링
python3 .claude/bin/consortium.py gateway teams --receive --poll 30  # 30초 간격 연속 폴링
python3 .claude/bin/consortium.py inbox                            # 적재된 수신 메시지 확인
```

기대 출력:
```
  ⬇ team-alpha → team-beta [designer] cycle=PCYC-01: 디자인 토큰 요청
[consortium] Teams 수신 완료: 1건 inbox 적재 (타팀행 0건 제외, 누적 seen 1)
```

### 9-5. 동작 규칙

- **봉투 복원**: 메시지 body·attachment 어디에 박혀 있든 `[[consortium-msg]]<base64>` 마커를
  스캔해 원본 계약 JSON 을 무손실 복원 (사람용 카드 렌더와 무관).
- **지목 필터**: 계약의 `to_team` 이 **내 팀**이고 `from_team` 이 내가 아닌 것만 적재 (내가 보낸 건 제외).
- **멱등성**: 처리한 Graph 메시지 id 를 `state/consortium/received-seen.json` 에 기록 → 재폴링해도 중복 적재 없음.

### 9-6. 수신 트러블슈팅

| 증상 | 원인 / 해결 |
|---|---|
| `자격증명 미설정` | §9-4 환경변수 3종(`TOKEN`/`TEAM_ID`/`CHANNEL_ID`) 주입 확인 |
| `HTTP 401` | 토큰 만료/오류 — §9-3 재발급 |
| `HTTP 403` | 권한 부족 — `ChannelMessage.Read.All` + **관리자 동의** 확인 |
| `HTTP 404` | team/channel id 오류 — §9-2 재확인 |
| 0건 적재(메시지는 있는데) | 발신측이 봉투 포함 버전(`--send`)으로 보냈는지, `to_team` 이 내 팀인지 확인 |

---

## 10. OpenClaw host — 네이티브 채널 브리지 (ADR-013)

§3~9 은 **claude-code/codex host** 기준(우리가 webhook+Graph 를 직접 plumbing). 그런데 host 가
**OpenClaw** 면 OpenClaw 가 Teams/Slack/Telegram 등 **20+ 채널을 네이티브 지원**(로컬 Gateway 데몬,
채널↔에이전트 라우팅)하므로, 우리 webhook/Graph 를 다시 짜지 않고 **OpenClaw 에 위임**한다.

consortium 게이트웨이는 **host-aware** 다 (`HARNESS_AGENT_TYPE` > `host.json` agent_type):

| host | transport |
|---|---|
| `claude-code` / `codex` | Teams webhook(발신) + Graph 폴링(수신) — §3~9 |
| `openclaw` | **핸드오프 브리지** — OpenClaw Gateway(에이전트=courier)에 위임 |

### 10-1. 동작 구조

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

### 10-2. 사용

```bash
export HARNESS_AGENT_TYPE=openclaw   # 또는 .claude/host.json 의 agent_type=openclaw
python3 .claude/bin/consortium.py gateway teams --send       # → openclaw-outbound/
python3 .claude/bin/consortium.py gateway teams --receive    # openclaw-inbound/ → inbox
python3 .claude/bin/consortium.py self                       # host=openclaw transport 확인
```

OpenClaw 채널 설정(Azure Bot·`~/.openclaw/openclaw.json`·터널)은 OpenClaw 문서를 따른다:
- 공식: https://docs.openclaw.ai/channels/msteams (Azure Bot + RSC 권한 + `/api/messages` + 터널)

### 10-3. courier 바인딩 (정직한 경계)

- consortium 쪽 **계약↔핸드오프 매핑 + 지목/멱등 라우팅** 은 stdlib 로 **실재·테스트**됨.
- 핸드오프 레코드를 **실제 OpenClaw 채널로 싣고 내리는 courier**(OpenClaw 에이전트의 채널 도구
  호출, 또는 Gateway 플로/ACP)는 OpenClaw 런타임에 바인딩 — §3~9 Teams stub→real 과 같은 seam.
- courier 를 모킹한 **완전 왕복이 테스트로 실재**한다 —
  `tests/test_consortium_gateway.py` (Slack·Teams·OpenClaw 왕복 + 경계 parity 30건, openclaw 브리지 포함).
  실 OpenClaw·실 Teams 채널 연결은 다운스트림 몫.

---

## 11. Telegram — 사람이 끼는 흐름 전용 (봇↔봇 불가)

> ⚠️ **컨소시엄 팀 노드끼리의 자동 왕복에는 쓸 수 없다.**
> Telegram Bot FAQ: *"Bots talking to each other could potentially get stuck in
> unwelcome loops. To avoid this, we decided that bots will not be able to see
> messages from other bots **regardless of mode**."*
> `/setprivacy` 를 꺼도 **봇은 다른 봇의 글을 보지 못한다**. 봇은 자기가 보낸 것도
> `getUpdates` 로 되받지 못한다. 따라서 "팀마다 봇을 만들어 같은 그룹에 넣는"
> 토폴로지는 성립하지 않는다 — 에이전트↔에이전트가 필요하면 **§2 Slack** 을 쓴다.
>
> 남는 용도는 **사람이 끼는 흐름**이다: 에이전트가 컨소시엄 메시지를 사람에게 알리고,
> 사람이 그룹에 쓴 지시를 에이전트가 받는다. 아래 절차는 그 범위다.
> `--receive` 는 chat id 를 **필수**로 요구한다 — 봇은 누구에게나 DM 을 받을 수 있고,
> 필터가 없으면 낯선 사용자의 DM 이 그대로 inbox·라우팅 키로 흘러간다 (실측).

### 11-1. 봇 만들기 (BotFather)

1. Telegram 에서 **@BotFather** 와 대화 시작
2. `/newbot` → 봇 이름 → 사용자명(`_bot` 으로 끝나야 함)
3. 받은 **토큰** 복사 — 형태: `123456789:AAH...`

### 11-2. 그룹 만들고 봇 초대 + chat id

에이전트가 알림을 보낼 **사람들의 그룹**을 만든다 (팀 노드끼리의 채널이 아니다).

1. 그룹 생성 → 봇을 멤버로 추가
2. BotFather `/setprivacy` → 봇 선택 → **Disable**
   (privacy mode 가 켜져 있으면 봇이 **사람이 쓴** 일반 메시지를 못 본다.
   변경 후 봇을 그룹에서 뺐다가 다시 넣어야 적용된다. 이걸 꺼도 **다른 봇의**
   글은 여전히 못 본다 — 그건 privacy mode 와 무관한 플랫폼 정책이다)
3. BotFather `/setjoingroups` → 필요 없으면 **Disable** (봇이 임의 그룹에 끌려가는 표면 축소)
4. 그룹에 사람이 아무 메시지나 한 줄 쓴다 (그래야 `getUpdates` 에 잡힌다)
5. chat id 확인 — **음수**로 나오는 것이 그룹 id 다:

```bash
TOKEN="$(< ~/.config/consortium/telegram_token.txt)"
curl -s "https://api.telegram.org/bot${TOKEN}/getUpdates" | python3 -m json.tool | grep -A3 '"chat"'
```

> 일반 그룹은 `-123456789`, 슈퍼그룹은 `-100...` 형태다. 그룹이 슈퍼그룹으로
> 승격되면 **id 가 바뀌어** 발신이 깨진다 — 그때 다시 확인한다.

### 11-3. 자격증명 안전 보관 (autonomous #3-A)

```bash
mkdir -p ~/.config/consortium && chmod 700 ~/.config/consortium
printf '%s\n' 'PASTE_BOT_TOKEN_HERE' > ~/.config/consortium/telegram_token.txt
printf '%s\n' '-1001234567890'       > ~/.config/consortium/telegram_chat_id.txt
chmod 600 ~/.config/consortium/telegram_*.txt
```

### 11-4. 발신 — 에이전트 → 사람

```bash
python3 .claude/bin/consortium.py init team-alpha --gateway telegram
python3 .claude/bin/consortium.py send --to team-beta --role developer \
  --cycle PCYC-01 --stage develop --msg "설계 완료, 구현 요청"

CONSORTIUM_TELEGRAM_TOKEN="$(< ~/.config/consortium/telegram_token.txt)" \
CONSORTIUM_TELEGRAM_CHAT_ID="$(< ~/.config/consortium/telegram_chat_id.txt)" \
  python3 .claude/bin/consortium.py gateway telegram --send
```

그룹에 사람이 읽을 카드 + 기계가 복원할 봉투가 함께 올라간다.

### 11-5. 수신 — 사람 → 에이전트

**토큰과 chat id 를 둘 다** 넘긴다. chat id 는 수신 범위를 그 그룹으로 못 박는 장치다 —
봇은 **누구에게나 DM 을 받을 수 있고** `getUpdates` 는 봇이 속한 모든 채팅을 주므로,
필터가 없으면 낯선 사용자의 DM 이 계약 검증을 통과해 라우팅 키로 흘러간다(실측).

```bash
CONSORTIUM_TELEGRAM_TOKEN="$(< ~/.config/consortium/telegram_token.txt)" \
CONSORTIUM_TELEGRAM_CHAT_ID="$(< ~/.config/consortium/telegram_chat_id.txt)" \
  python3 .claude/bin/consortium.py gateway telegram --receive --poll 20
```

**사람이 무엇을 써야 하는가**: 에이전트가 읽으려면 계약 봉투가 필요하다.
발신 노드의 `outbox/*.json`(또는 같은 스키마의 JSON)을 base64 로 인코딩해
`[[consortium-msg]]<base64>` 한 줄을 그룹에 붙여 넣는다:

```bash
python3 - <<'EOF'
import base64, json
msg = {"from_team": "team-human", "to_team": "team-alpha", "role": "developer",
       "cycle_id": "PCYC-01", "msg": "승인합니다. 배포 진행하세요."}
print("[[consortium-msg]]" + base64.b64encode(
    json.dumps(msg, ensure_ascii=False).encode()).decode())
EOF
```

> 봉투 없이 쓴 글은 consortium 메시지가 아니므로 조용히 무시된다(정상 동작).

### 11-6. 동작 규칙

- **멱등**: `offset` 을 `telegram-offset.json` 에 기록하고 **처리 후에만** 전진한다.
  Telegram 은 offset 을 확인(ack)으로 받아 그 이전 update 를 **서버에서 지우므로**,
  먼저 올리면 처리 못 한 메시지가 사라진다. 실패분은 `telegram-quarantine/` 에
  원본을 보존하고, 보존까지 실패하면 그 지점부터 offset 을 **동결**한다.
- **중복 허용**: 중단 시 같은 update 를 다시 받는다(at-least-once). 중복은 파일명에
  `-1` 이 붙어 흡수되므로 소비측은 `telegram_update_id` 로 dedupe 한다.
- **본문 상한 4096자**: 넘으면 **거부**하고 outbox 에 남긴다. 잘라 보내면 봉투가
  깨져 복원이 불가능하다 — 조용한 손상보다 시끄러운 거부.

### 11-7. 트러블슈팅

| 증상 | 확인 |
|---|---|
| `자격증명 미설정` | `--receive` 도 **chat id 가 필수**다 (주입 누락) |
| `API 거부: Unauthorized` | 토큰 오타 — BotFather `/mybots` → API Token |
| `API 거부: chat not found` | chat id 오류. 그룹은 **음수**. 봇이 멤버인지 확인 |
| `API 거부: Conflict` | 봇에 webhook 이 걸려 있다 — `deleteWebhook` 후 재시도 |
| 사람이 썼는데 수신 0건 | ① `/setprivacy` Disable 후 **재초대** 했는지 ② 봉투(`[[consortium-msg]]…`)를 붙였는지 ③ chat id 가 그 그룹인지 |
| 봇이 보낸 건 왜 안 오나 | **정상이다.** 봇은 자기 글도, 다른 봇의 글도 받지 못한다 (§11 머리말) |
