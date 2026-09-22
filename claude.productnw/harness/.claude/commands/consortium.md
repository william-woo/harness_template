# /project:consortium — 분산 멀티팀 에이전트 컨소시엄 (claude.productnw 전용, d-3)

여러 팀이 각자의 멀티 에이전트 하네스를 두고, **팀 간 메시지 계약**으로 통신하며 통합 제품을
만드는 컨소시엄 협업. `product-cycle`(단일 팀 통합 SDLC)을 **여러 팀으로 확장**한 것.

**claude.productnw 변형 전용.** ADR-008 의 **d-3(이종 호스트 분산)** 단계 — 정직한 범위는 아래 참조.

> 관계: product-cycle(한 팀이 기획→배포) → **consortium(여러 팀이 각 단계를 분담·핸드오프)**.

---

## 정직한 범위 (꼭 읽기)

| 구성요소 | 상태 |
|---|---|
| 메시지 계약(JSON 스키마) + 로스터 + 로컬 큐(inbox/outbox) | ✅ **stdlib 로 실재 동작** |
| **Slack** 발신+수신 ★권장 | ✅ **실구현** — 봇 토큰 1개 + 채널 id. `conversations.history` 는 채널 **로그 읽기**라 다른 봇의 글도 들어온다 |
| **Teams** 발신+수신 | ✅ **실구현** — 자격증명 4개 + Azure AD 앱 등록 + 관리자 동의 필요 |
| Telegram | ⚠️ 발신 + **사람이 쓴 메시지** 수신만 — 봇은 다른 봇의 글을 못 본다(플랫폼 정책) |

→ 로컬 큐만으로도 **협업 흐름·핸드오프를 검증**할 수 있고, 실제 원격 멀티팀 메시징은
**Slack 이면 10분**이면 붙는다 (가이드 §2). 컨소시엄은 에이전트↔에이전트라
**봇이 다른 봇의 글을 보는가**가 선택을 가른다 — Telegram 은 그걸 못 해서 탈락했다(§11).
세 transport 는 **같은 수신 경계**를 지나므로 계약 검증·파일명 위생·유일성이
플랫폼과 무관하게 동일하게 걸린다.

---

## 사용법

```bash
# 각 팀 노드에서 자기 팀 등록
python3 .claude/bin/consortium.py init team-alpha --agents "product-manager,developer,qa" --gateway slack
python3 .claude/bin/consortium.py roster                      # 컨소시엄 팀·에이전트 목록

# 팀 간 메시지 (계약 검증 후 outbox)
python3 .claude/bin/consortium.py send --to team-beta --role designer --cycle PCYC-01 --stage design --msg "결제 화면 토큰 요청"
python3 .claude/bin/consortium.py inbox                        # 수신 메시지 (게이트웨이가 외부→inbox)

# 게이트웨이 — host-aware transport (ADR-013)
python3 .claude/bin/consortium.py gateway slack                # 연동 안내 (host 표시)
# ★권장: Slack — 봇 토큰 1개 + 채널 id 로 발신·수신
CONSORTIUM_SLACK_TOKEN="$(< ~/.config/consortium/slack_token.txt)" \
CONSORTIUM_SLACK_CHANNEL="$(< ~/.config/consortium/slack_channel.txt)" \
  python3 .claude/bin/consortium.py gateway slack --send       # outbox→채널 발신
CONSORTIUM_SLACK_TOKEN="$(< ~/.config/consortium/slack_token.txt)" \
CONSORTIUM_SLACK_CHANNEL="$(< ~/.config/consortium/slack_channel.txt)" \
  python3 .claude/bin/consortium.py gateway slack --receive --poll 60   # 채널→inbox
# 대안: Teams (사내 표준이 Teams 인 조직)
CONSORTIUM_TEAMS_WEBHOOK="$(< ~/.config/consortium/teams_webhook.txt)" \
  python3 .claude/bin/consortium.py gateway teams --send
# openclaw host: OpenClaw Gateway 위임 (핸드오프 브리지, webhook/Graph 불요)
HARNESS_AGENT_TYPE=openclaw python3 .claude/bin/consortium.py gateway teams --send
python3 .claude/bin/consortium.py self                         # host/transport 점검
```

> **게이트웨이 설치**: [docs/consortium-gateway-setup.md](../../docs/consortium-gateway-setup.md) 참조.
> - **처음이라면 §2 (Slack — 10분)** 만 읽으면 된다
> - Telegram 은 §11 (봇↔봇 불가 — 사람이 끼는 흐름 전용)
> - claude-code/codex host + Teams: §3~§9 (웹훅 발신 + Graph 폴링 수신)
> - **openclaw host**: §10 (OpenClaw 네이티브 채널에 위임 — 핸드오프 브리지, ADR-013)
> consortium 게이트웨이는 host(`HARNESS_AGENT_TYPE`/host.json)에 따라 transport 를 자동 선택한다.

## 메시지 계약 (팀 간 상호운용 표준)

```json
{
  "from_team": "team-alpha", "to_team": "team-beta",
  "role": "designer", "cycle_id": "PCYC-01",
  "stage": "design", "msg": "...", "status": "queued", "ts": "..."
}
```
필수: `from_team / to_team / role / cycle_id / msg` (전부 **비어 있지 않은 문자열**).
`stage` ∈ {plan,design,develop,verify,deploy}. 계약 검증은 **발신·수신 양쪽**에 걸린다
(ADR-012 결정 3) — 값을 정하는 쪽은 수신에선 원격이기 때문이다.

→ 게이트웨이는 이 JSON 을 그대로 실어 보내고, **수신분은 `openclaw-inbound/` 에 드롭**한다.
`gateway <platform> --receive` 가 **단일 수신 경계**에서 계약 검증·파일명 위생·유일성을 처리한다.

> ⚠️ **`inbox/` 에 직접 쓰지 말 것.** 경계를 건너뛰면 원격이 정한 값이 그대로 파일명·경로·
> 라우팅 키가 된다. 이 변형이 리뷰 3라운드에 걸쳐 닫은 결함(경로 탈출·큐 영구 정지·메시지
> 소멸)이 전부 그 지점에서 나왔다.

## 컨소시엄 흐름 (멀티팀 product-cycle)

```
PM(주관 팀)이 product-cycle 로 제품 brief·성공지표 정의
   → 단계를 팀에 분배: 설계=team-beta, 개발=team-gamma ...
   → consortium send (cycle_id 로 묶음) → 각 팀이 자기 단계 수행(로컬 product-cycle --from=<stage>)
   → 결과를 consortium send 로 회신 → PM 이 성공지표 기준 통합 게이트
```
- 각 팀 내부는 **single-host**(자기 하네스의 Task 오케스트레이션). 팀 **사이**만 메시지 계약으로 연결.
- `cycle_id` 가 분산된 작업을 하나의 제품 사이클로 묶는 키.

## 호출 기준

- 여러 팀/조직이 **한 제품을 분담**해 만들 때 (팀별 전문성 분리)
- 단계별로 다른 팀이 담당 (예: A팀 기획·PM, B팀 디자인, C팀 개발)

해당 없으면:
- 한 팀 내 통합 흐름 → `/project:product-cycle`
- 한 팀 내 실행 라우팅 → `/project:orchestrate`

## d-3 제약 (ADR-008 결정 5 / ADR-012)

- **컨텍스트 전달 손실**: 팀 간엔 같은 컨텍스트 풀이 없다 → 메시지 계약으로 명시 전달만. brief·성공지표를
  메시지에 충분히 실어야 함 (single-host 의 암묵 공유 불가).
- **인증 경계**: 게이트웨이 = 외부 메시징 = #3-A. 토큰·봇 등록은 사용자 승인·다운스트림 책임.
- **결과적 일관성**: 비동기 메시지 큐 — 즉시성 보장 없음. cycle_id 로 추적.
