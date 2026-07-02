# 컨소시엄 게이트웨이 설치 가이드 — MS Teams (claude.productnw, d-3)

> `consortium.py` 의 **게이트웨이 transport** 를 실제 메시징 플랫폼에 연결하는 설치 절차.
> 이 문서는 **MS Teams** 기준. Slack/Telegram 은 아직 stub (부록 참조).
> 관련: [consortium.md](../.claude/commands/consortium.md) · [ADR-012](adr/ADR-012-consortium-distribution.md)

---

## 0. 무엇을 연결하는가 (정직한 범위)

`consortium.py` 는 메시지 계약 + 로스터 + 로컬 큐(inbox/outbox)를 stdlib 로 **실재 구현**한다.
게이트웨이는 그 큐를 외부 플랫폼으로 나르는 **transport** 다.

| 방향 | 상태 | 비고 |
|---|---|---|
| **발신** outbox → Teams 채널 | ✅ **실구현** (`gateway teams --send`) | §2~4 — 웹훅 URL |
| **수신** Teams 채널 → inbox | ✅ **실구현** (`gateway teams --receive`) | §8 — Graph 폴링 + OAuth 토큰 |

→ 발신·수신 모두 stdlib `urllib` 로 동작한다. 발신은 **웹훅 URL**(§2), 수신은 **Graph OAuth 토큰 +
team/channel id**(§8)가 필요하다. 둘 다 갖추면 **에이전트↔에이전트 완전 자동 왕복**이 된다
(A→Teams→B 수신→B답변→Teams→A 수신). 자격증명·앱등록은 사용자/다운스트림 책임 (d-3 경계).

---

## 1. 사전 준비

- MS Teams 팀/채널에 **커넥터 또는 Workflows 를 추가할 권한** (보통 팀 소유자/멤버)
- 이 하네스 (`consortium.py`, Python 3.8+, 외부 패키지 0 — stdlib `urllib` 만 사용)
- 발신 머신에서 `*.webhook.office.com` (또는 Workflows 의 `*.logic.azure.com`) 으로의 HTTPS egress

---

## 2. Teams 웹훅 URL 발급

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
   함께 실으므로 대부분 그대로 렌더된다 (§5 호환성 참조).

### 방법 B — Incoming Webhook 커넥터 (구형 테넌트)

1. 채널 → **⋯ → Connectors** (Connectors 메뉴가 보이는 테넌트만 해당)
2. **Incoming Webhook** → **Configure**
3. 이름(예: `consortium`) 지정 → (선택) 아이콘 업로드 → **Create**
4. 생성된 **URL** 복사 — 형태: `https://<tenant>.webhook.office.com/webhookb2/...`

> Connectors 메뉴가 없으면 테넌트에서 비활성화된 것 — 방법 A 를 쓴다.

---

## 3. 웹훅 URL 안전 보관 (자격증명 — autonomous #3-A)

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

## 4. 발신 테스트

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
  무시하지만 수신측(§8)이 이걸 스캔해 원본 메시지를 무손실 복원한다.

---

## 5. 페이로드 호환성

본 어댑터가 보내는 JSON 은 두 방식을 동시에 만족하도록 설계됐다:

- `@type: MessageCard` + `sections[].facts` → **구형 Connector** 가 제목·필드·본문 카드로 렌더
- top-level `text` → **Workflows** 템플릿이 흔히 참조하는 필드 (본문 텍스트)

Workflows 템플릿을 커스터마이즈해 다른 필드(`@{triggerBody()?['title']}` 등)를 참조한다면,
`consortium.py` 의 `_build_teams_card()` 가 만드는 키와 워크플로 매핑을 맞추면 된다.

---

## 6. 트러블슈팅

| 증상 | 원인 / 해결 |
|---|---|
| `CONSORTIUM_TEAMS_WEBHOOK 미설정` | §3 환경변수 주입 누락 — `cat` 으로 파일을 읽어 prefix 로 전달했는지 확인 |
| `HTTP 400` | 페이로드 형식 불일치 — Workflows 라면 §5 매핑 확인. URL 끝의 `&sig=...` 까지 정확히 복사했는지 |
| `HTTP 401/403` | 웹훅 만료·비활성화·서명(sig) 누락 — Teams 에서 URL 재발급 |
| `HTTP 404` | 워크플로/커넥터가 삭제됨 — 재생성 |
| `전송 실패: <URLError>` | 네트워크 egress 차단 (프록시/방화벽) — 사내망이면 프록시 설정 필요 |
| 메시지는 가는데 렌더가 깨짐 | §5 — Workflows 플로의 게시 카드가 다른 필드 참조 중. 플로 편집에서 `text` 참조로 변경 |

---

## 7. 보안·운영 메모

- 웹훅 URL 유출 시 누구나 채널에 글쓰기 가능 → **즉시 Teams 에서 URL 재발급(rotate)**.
- 발신/수신 자격증명(웹훅·토큰)은 **환경변수로만** 주입 — 코드·설정·로그·채팅 노출 금지.
- 발송량이 많으면 Teams 측 rate limit 가능 — 배치 발신 시 간격을 둔다 (현재 어댑터는 순차 발신).

---

## 8. 수신 — Graph API 폴링 (채널 → inbox)

발신의 역방향. Teams 채널 메시지를 **Microsoft Graph** 로 폴링해, consortium 계약 봉투(§4)를
가진 메시지만 골라 **나(이 팀)에게 온 것**을 `inbox/` 에 적재한다. 이게 채워지면 **완전 자동 왕복**
(A→Teams→B 수신→B답변→Teams→A 수신)이 된다. stdlib `urllib` 만 사용.

### 8-1. Azure 앱 등록 (1회)

1. [Azure Portal](https://portal.azure.com) → **Microsoft Entra ID → App registrations → New registration**
2. 이름 지정 → 등록. **Application (client) ID** + **Directory (tenant) ID** 기록
3. **API permissions → Add → Microsoft Graph**:
   - 봇처럼 무인 폴링 → **Application permission** `ChannelMessage.Read.All`
   - **Grant admin consent** 클릭 (관리자 동의 필수)
4. **Certificates & secrets → New client secret** → 값 복사 (한 번만 보임)

### 8-2. team / channel id 확보

- Teams 채널 → ⋯ → **Get link to channel** → URL 의 `groupId`(=team id) 와 `channelId` 추출, 또는
- Graph 탐색: `GET /me/joinedTeams` → team id, `GET /teams/{team-id}/channels` → channel id

### 8-3. 액세스 토큰 발급 (client credentials)

```bash
curl -s -X POST "https://login.microsoftonline.com/<TENANT_ID>/oauth2/v2.0/token" \
  -d "client_id=<CLIENT_ID>" \
  -d "client_secret=<CLIENT_SECRET>" \
  -d "scope=https://graph.microsoft.com/.default" \
  -d "grant_type=client_credentials" | python3 -c "import sys,json;print(json.load(sys.stdin)['access_token'])"
```
> 토큰은 보통 1시간 만료 → 폴링 루프를 길게 돌릴 땐 토큰 갱신 래퍼가 필요(다운스트림). 단발/단시간은 그대로.

### 8-4. 자격증명 주입 + 수신 실행

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

### 8-5. 동작 규칙

- **봉투 복원**: 메시지 body·attachment 어디에 박혀 있든 `[[consortium-msg]]<base64>` 마커를
  스캔해 원본 계약 JSON 을 무손실 복원 (사람용 카드 렌더와 무관).
- **지목 필터**: 계약의 `to_team` 이 **내 팀**이고 `from_team` 이 내가 아닌 것만 적재 (내가 보낸 건 제외).
- **멱등성**: 처리한 Graph 메시지 id 를 `state/consortium/received-seen.json` 에 기록 → 재폴링해도 중복 적재 없음.

### 8-6. 수신 트러블슈팅

| 증상 | 원인 / 해결 |
|---|---|
| `자격증명 미설정` | §8-4 환경변수 3종(`TOKEN`/`TEAM_ID`/`CHANNEL_ID`) 주입 확인 |
| `HTTP 401` | 토큰 만료/오류 — §8-3 재발급 |
| `HTTP 403` | 권한 부족 — `ChannelMessage.Read.All` + **관리자 동의** 확인 |
| `HTTP 404` | team/channel id 오류 — §8-2 재확인 |
| 0건 적재(메시지는 있는데) | 발신측이 봉투 포함 버전(`--send`)으로 보냈는지, `to_team` 이 내 팀인지 확인 |

---

## 9. OpenClaw host — 네이티브 채널 브리지 (ADR-013)

§2~8 은 **claude-code/codex host** 기준(우리가 webhook+Graph 를 직접 plumbing). 그런데 host 가
**OpenClaw** 면 OpenClaw 가 Teams/Slack/Telegram 등 **20+ 채널을 네이티브 지원**(로컬 Gateway 데몬,
채널↔에이전트 라우팅)하므로, 우리 webhook/Graph 를 다시 짜지 않고 **OpenClaw 에 위임**한다.

consortium 게이트웨이는 **host-aware** 다 (`HARNESS_AGENT_TYPE` > `host.json` agent_type):

| host | transport |
|---|---|
| `claude-code` / `codex` | Teams webhook(발신) + Graph 폴링(수신) — §2~8 |
| `openclaw` | **핸드오프 브리지** — OpenClaw Gateway(에이전트=courier)에 위임 |

### 9-1. 동작 구조

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

### 9-2. 사용

```bash
export HARNESS_AGENT_TYPE=openclaw   # 또는 .claude/host.json 의 agent_type=openclaw
python3 .claude/bin/consortium.py gateway teams --send       # → openclaw-outbound/
python3 .claude/bin/consortium.py gateway teams --receive    # openclaw-inbound/ → inbox
python3 .claude/bin/consortium.py self                       # host=openclaw transport 확인
```

OpenClaw 채널 설정(Azure Bot·`~/.openclaw/openclaw.json`·터널)은 OpenClaw 문서를 따른다:
- 공식: https://docs.openclaw.ai/channels/msteams (Azure Bot + RSC 권한 + `/api/messages` + 터널)

### 9-3. courier 바인딩 (정직한 경계)

- consortium 쪽 **계약↔핸드오프 매핑 + 지목/멱등 라우팅** 은 stdlib 로 **실재·테스트**됨.
- 핸드오프 레코드를 **실제 OpenClaw 채널로 싣고 내리는 courier**(OpenClaw 에이전트의 채널 도구
  호출, 또는 Gateway 플로/ACP)는 OpenClaw 런타임에 바인딩 — §2~8 Teams stub→real 과 같은 seam.
- 같은 머신에서 courier 를 모킹하면 **완전 왕복 검증 가능** (실 OpenClaw 연결은 다운스트림 몫).

---

## 부록 — Slack / Telegram (아직 stub)

같은 outbox→플랫폼 패턴이며 transport 만 다르다. 현재 `consortium.py` 는 안내만 출력한다.

- **Slack**: 채널 Incoming Webhook URL 발급 → outbox JSON 을 `{"text": ...}` 로 POST.
  수신은 Events API (별도 서버) 필요.
- **Telegram**: BotFather 로 봇 생성 → 토큰 + `chat_id` → `sendMessage`. 수신은 `getUpdates` 폴링/webhook.

이들을 켜려면 `consortium.py` 에 Teams 발신부와 동일한 패턴으로 어댑터를 추가하면 된다
(다운스트림이 필요 시 확장 — d-3 의 정직한 경계).
