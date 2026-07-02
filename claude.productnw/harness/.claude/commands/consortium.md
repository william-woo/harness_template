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
| Teams/Slack/Telegram 실제 전송 | 🔸 **stub** — 자격증명(#3-A)·외부 SDK·웹훅 필요 → **다운스트림이 봇 연동** |

→ 같은 머신/공유 볼륨이면 로컬 큐만으로 **협업 흐름·핸드오프를 검증**할 수 있고, 진짜 원격
멀티팀 메시징은 다운스트림이 게이트웨이 봇을 붙여 완성한다. (분산 메시징 시스템 전체는 하네스 범위 밖.)

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
python3 .claude/bin/consortium.py gateway teams                # 연동 안내 (host 표시)
# claude-code/codex host: Teams webhook(발신) + Graph 폴링(수신)
CONSORTIUM_TEAMS_WEBHOOK="$(cat ~/.config/consortium/teams_webhook.txt)" \
  python3 .claude/bin/consortium.py gateway teams --send       # outbox→Teams 채널 발신
python3 .claude/bin/consortium.py gateway teams --receive      # Graph 폴링 채널→inbox
# openclaw host: OpenClaw Gateway 위임 (핸드오프 브리지, webhook/Graph 불요)
HARNESS_AGENT_TYPE=openclaw python3 .claude/bin/consortium.py gateway teams --send
python3 .claude/bin/consortium.py self                         # host/transport 점검
```

> **게이트웨이 설치**: [docs/consortium-gateway-setup.md](../../docs/consortium-gateway-setup.md) 참조.
> - claude-code/codex host: §2~8 (Teams 웹훅 발신 + Graph 폴링 수신, 완전 왕복)
> - **openclaw host**: §9 (OpenClaw 네이티브 채널에 위임 — 핸드오프 브리지, ADR-013)
> consortium 게이트웨이는 host(`HARNESS_AGENT_TYPE`/host.json)에 따라 transport 를 자동 선택한다.

## 메시지 계약 (팀 간 상호운용 표준)

```json
{
  "from_team": "team-alpha", "to_team": "team-beta",
  "role": "designer", "cycle_id": "PCYC-01",
  "stage": "design", "msg": "...", "status": "queued", "ts": "..."
}
```
필수: `from_team / to_team / role / cycle_id / msg`. `stage` ∈ {plan,design,develop,verify,deploy}.
→ 게이트웨이는 이 JSON 을 그대로 실어 보내고, 수신도 같은 스키마로 inbox 에 적재하면 된다 (플랫폼 무관).

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
