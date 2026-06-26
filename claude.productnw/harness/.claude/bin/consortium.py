#!/usr/bin/env python3
"""
consortium.py — 분산 멀티팀 에이전트 컨소시엄 (d-3, claude.productnw 전용)

여러 팀이 각자의 멀티 에이전트 하네스를 두고, **팀 간 메시지 계약**으로 통신하며 통합 제품을
만드는 컨소시엄 협업 레이어. ADR-008 의 d-3(이종 호스트 분산) 단계.

설계 (정직):
- **동작하는 핵심(stdlib)**: 메시지 계약(JSON 스키마) + 컨소시엄 로스터 + 로컬 파일 큐(inbox/outbox).
  같은 머신/공유 볼륨에서는 이것만으로 팀 간 메시지·핸드오프가 동작한다.
- **stub(미구현)**: Teams/Slack/Telegram 게이트웨이 = inbox/outbox 를 실제 메시징 플랫폼으로
  나르는 transport. 자격증명(#3-A)·외부 SDK·웹훅이 필요하므로 **다운스트림이 봇을 붙인다**.
  여기선 codex/openclaw 어댑터처럼 안내만 출력하고 graceful degrade.

→ 즉 "프로토콜은 stdlib 로 실재, 네트워크 전송은 stub". 분산 멀티에이전트 메시징 시스템 전체를
  여기서 구현하지 않는다 (대형 인프라 — 하네스 범위 밖).

사용법:
  python3 .claude/bin/consortium.py init <team-id> [--agents a,b,c]   # 이 노드를 팀으로 등록
  python3 .claude/bin/consortium.py roster                            # 등록된 팀·에이전트 목록
  python3 .claude/bin/consortium.py send --to <team> --role <agent> --cycle <id> --msg "<텍스트>"
  python3 .claude/bin/consortium.py inbox [--team <team>]             # 수신 메시지 목록/읽기
  python3 .claude/bin/consortium.py gateway <slack|teams|telegram> [status|setup]   # 전송 어댑터 (stub)
  python3 .claude/bin/consortium.py self                              # 환경·의존성 점검

상태 위치: .claude/state/consortium/ (roster.json + inbox/ + outbox/ — 런타임 gitignore)
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


def _project_root() -> Path:
    """하네스 루트 ($CLAUDE_PROJECT_DIR > 스크립트 위치 기준 parent×3)."""
    env = os.environ.get("CLAUDE_PROJECT_DIR")
    if env and Path(env).is_dir():
        return Path(env)
    return Path(__file__).resolve().parent.parent.parent


_ROOT = _project_root()
_STATE = _ROOT / ".claude" / "state" / "consortium"
_ROSTER = _STATE / "roster.json"
_INBOX = _STATE / "inbox"
_OUTBOX = _STATE / "outbox"

# OpenClaw 채널 브리지 핸드오프 디렉토리 (ADR-013) — host=openclaw 일 때만 사용.
# consortium ↔ OpenClaw 에이전트(courier) 사이의 interop 경계.
_OC_OUTBOUND = _STATE / "openclaw-outbound"  # consortium → OpenClaw(채널로 발신)
_OC_INBOUND = _STATE / "openclaw-inbound"    # OpenClaw(채널 수신) → consortium


def _detect_host() -> str:
    """현재 host 를 감지한다 (HARNESS_AGENT_TYPE > host.json agent_type > 기본 claude-code).
    consortium 게이트웨이 transport 선택에 쓰인다 (ADR-013)."""
    env = os.environ.get("HARNESS_AGENT_TYPE", "").strip()
    if env:
        return env
    host_json = _ROOT / ".claude" / "host.json"
    if host_json.exists():
        try:
            return json.loads(host_json.read_text(encoding="utf-8")).get("agent_type", "claude-code")
        except (json.JSONDecodeError, OSError):
            pass
    return "claude-code"

# 게이트웨이 어댑터 — teams 는 발신(단방향) 실구현, slack/telegram 은 stub.
_GATEWAYS = {
    "slack": "Slack (Incoming Webhook 또는 Bolt 봇 + bot token)",
    "teams": "MS Teams (Incoming Webhook — 채널 커넥터/Workflows)",
    "telegram": "Telegram (Bot API + BotFather 토큰)",
}

# Teams 발신 어댑터: 웹훅 URL 은 자격증명(autonomous #3-A) — 셸 노출 금지, 환경변수로만 주입.
_TEAMS_WEBHOOK_ENV = "CONSORTIUM_TEAMS_WEBHOOK"

# Teams 수신(Graph 폴링) 자격증명 — 모두 환경변수로만 주입 (#3-A).
_TEAMS_TOKEN_ENV = "CONSORTIUM_TEAMS_TOKEN"      # OAuth Bearer 토큰 (앱 등록 + ChannelMessage.Read.All)
_TEAMS_TEAM_ENV = "CONSORTIUM_TEAMS_TEAM_ID"     # Graph team(group) id
_TEAMS_CHANNEL_ENV = "CONSORTIUM_TEAMS_CHANNEL_ID"  # Graph channel id
_GRAPH_BASE = "https://graph.microsoft.com/v1.0"

# 계약 봉투 — 사람용 카드 안에 기계가 무손실 복원할 원본 계약 JSON 을 base64 로 심는다.
# 수신측은 메시지 어디에 박혀 있든 이 마커를 스캔해 원본 메시지를 그대로 복원한다.
_ENVELOPE_PREFIX = "[[consortium-msg]]"
_ENVELOPE_RE = re.compile(re.escape(_ENVELOPE_PREFIX) + r"([A-Za-z0-9+/=]+)")

_TEAM_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


def _now() -> str:
    """UTC ISO 타임스탬프."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _load_roster() -> dict:
    """roster.json 을 읽는다 (없으면 빈 구조)."""
    if _ROSTER.exists():
        try:
            return json.loads(_ROSTER.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {"teams": {}}


# ---------------------------------------------------------------------------
# 메시지 계약 (inter-team message schema) — 팀 간 상호운용 표준
# ---------------------------------------------------------------------------
# 필수: from_team, to_team, role, cycle_id, msg. 선택: stage, payload, status.
_REQUIRED_MSG_FIELDS = ("from_team", "to_team", "role", "cycle_id", "msg")


def _validate_message(m: dict) -> list[str]:
    """메시지가 계약을 만족하는지 검증하고 위반 목록을 반환한다 (빈 = 통과)."""
    errs = [f"필수 필드 누락: {f}" for f in _REQUIRED_MSG_FIELDS
            if not str(m.get(f, "")).strip()]
    stage = m.get("stage", "")
    if stage and stage not in ("plan", "design", "develop", "verify", "deploy"):
        errs.append(f"stage 값 오류: {stage} (plan|design|develop|verify|deploy)")
    return errs


def cmd_init(args) -> int:
    """이 노드를 컨소시엄 팀으로 로스터에 등록한다."""
    team = args.team.strip()
    if not _TEAM_RE.match(team):
        print(f"[consortium] ❌ 잘못된 team-id '{team}' — 소문자·숫자·하이픈, 소문자/숫자로 시작")
        return 1
    _STATE.mkdir(parents=True, exist_ok=True)
    _INBOX.mkdir(exist_ok=True)
    _OUTBOX.mkdir(exist_ok=True)
    roster = _load_roster()
    agents = [a.strip() for a in (args.agents or "").split(",") if a.strip()]
    roster["teams"][team] = {
        "team_id": team,
        "agents": agents or ["product-manager", "developer", "reviewer", "qa"],
        "registered": _now(),
        "gateway": args.gateway or "(미설정 — gateway setup 참조)",
    }
    _ROSTER.write_text(json.dumps(roster, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[consortium] 팀 등록: {team} (agents: {', '.join(roster['teams'][team]['agents'])})")
    print(f"  로스터: {_ROSTER.relative_to(_ROOT)}")
    return 0


def cmd_roster(args) -> int:
    """등록된 팀·에이전트 목록을 표시한다."""
    roster = _load_roster()
    teams = roster.get("teams", {})
    if not teams:
        print("[consortium] 등록된 팀 없음 — `consortium.py init <team-id>` 로 등록")
        return 0
    print(f"[consortium] 컨소시엄 로스터 — {len(teams)}개 팀\n")
    for tid, t in sorted(teams.items()):
        print(f"  ● {tid}  (gateway: {t.get('gateway', '?')})")
        print(f"      agents: {', '.join(t.get('agents', []))}")
        print(f"      등록: {t.get('registered', '?')}")
    return 0


def cmd_send(args) -> int:
    """팀 간 메시지를 계약 검증 후 outbox 에 기록한다 (게이트웨이가 transport)."""
    _OUTBOX.mkdir(parents=True, exist_ok=True)
    msg = {
        "from_team": args.from_team or _load_roster().get("self", ""),
        "to_team": args.to,
        "role": args.role,
        "cycle_id": args.cycle,
        "stage": args.stage or "",
        "msg": args.msg,
        "status": "queued",
        "ts": _now(),
    }
    # from_team 미지정 시 로스터의 첫 팀을 self 로 추정 (단일 팀 노드 편의)
    if not msg["from_team"]:
        teams = list(_load_roster().get("teams", {}))
        msg["from_team"] = teams[0] if teams else "unknown"
    errs = _validate_message(msg)
    if errs:
        print("[consortium] ❌ 메시지 계약 위반:")
        for e in errs:
            print(f"      - {e}")
        return 1
    # 파일명: ts + to_team (정렬 가능)
    safe_ts = msg["ts"].replace(":", "").replace("-", "")
    out_file = _OUTBOX / f"{safe_ts}__to-{args.to}.json"
    out_file.write_text(json.dumps(msg, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[consortium] outbox 기록: {out_file.relative_to(_ROOT)}")
    print(f"  {msg['from_team']} → {args.to} [{args.role}] cycle={args.cycle}")
    print("  → 실제 전송은 `gateway <platform>` (현재 stub — 다운스트림 봇 연동 필요)")
    return 0


def cmd_inbox(args) -> int:
    """수신 메시지(inbox)를 목록·표시한다. 게이트웨이가 외부→inbox 로 가져온다."""
    if not _INBOX.exists():
        print("[consortium] inbox 없음 — `init` 먼저 실행")
        return 0
    msgs = sorted(_INBOX.glob("*.json"))
    if args.team:
        msgs = [m for m in msgs
                if json.loads(m.read_text(encoding="utf-8")).get("to_team") == args.team]
    if not msgs:
        print("[consortium] inbox 비어있음")
        return 0
    print(f"[consortium] inbox — {len(msgs)}건\n")
    for mf in msgs:
        m = json.loads(mf.read_text(encoding="utf-8"))
        print(f"  ● [{m.get('ts','?')}] {m.get('from_team','?')} → {m.get('to_team','?')} "
              f"[{m.get('role','?')}] cycle={m.get('cycle_id','?')} stage={m.get('stage','-')}")
        print(f"      {m.get('msg','')}")
    return 0


def _build_teams_card(m: dict) -> dict:
    """컨소시엄 메시지를 Teams 웹훅 페이로드로 변환한다.
    MessageCard 키(구형 Connector 렌더) + top-level text(Workflows 템플릿이 흔히 참조) 동시 포함."""
    title = f"[consortium] {m.get('from_team','?')} → {m.get('to_team','?')} (cycle {m.get('cycle_id','?')})"
    # 원본 계약을 base64 봉투로 심어 수신측이 무손실 복원 (사람은 무시, 기계는 파싱).
    envelope = _ENVELOPE_PREFIX + base64.b64encode(
        json.dumps(m, ensure_ascii=False).encode("utf-8")).decode("ascii")
    flat = (f"{title}\n역할: {m.get('role','-')} · 단계: {m.get('stage') or '-'} · "
            f"{m.get('ts','-')}\n{m.get('msg','')}\n{envelope}")
    return {
        "@type": "MessageCard",
        "@context": "http://schema.org/extensions",
        "themeColor": "0076D7",
        "summary": f"consortium {m.get('from_team','?')}→{m.get('to_team','?')}",
        "title": title,
        "text": flat,  # Workflows 템플릿 호환 (triggerBody()?['text'])
        "sections": [{
            "facts": [
                {"name": "role", "value": str(m.get("role", "-"))},
                {"name": "stage", "value": str(m.get("stage") or "-")},
                {"name": "ts", "value": str(m.get("ts", "-"))},
            ],
            "text": str(m.get("msg", "")),
        }],
    }


def _post_teams(webhook: str, payload: dict) -> tuple[bool, str]:
    """Teams 웹훅으로 페이로드를 POST 한다. (성공여부, 응답/오류) 반환. 네트워크=경계 방어."""
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        webhook, data=data, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = resp.read().decode("utf-8", "replace").strip()
            return (200 <= resp.status < 300, f"HTTP {resp.status} {body[:200]}")
    except urllib.error.HTTPError as exc:
        return (False, f"HTTP {exc.code} {exc.read().decode('utf-8', 'replace')[:200]}")
    except (urllib.error.URLError, OSError) as exc:
        return (False, f"전송 실패: {exc}")


def _send_teams() -> int:
    """outbox 의 미발신 메시지를 Teams 채널로 발신하고, 성공분을 outbox/sent/ 로 이동한다."""
    webhook = os.environ.get(_TEAMS_WEBHOOK_ENV, "").strip()
    if not webhook:
        print(f"[consortium] ❌ 환경변수 {_TEAMS_WEBHOOK_ENV} 미설정 — 웹훅 URL 을 셸에 노출하지 말고")
        print(f"  `export {_TEAMS_WEBHOOK_ENV}='https://...webhook.office.com/...'` 로 주입 후 재실행.")
        print("  (Teams 채널 → 커넥터/Workflows 에서 'Incoming Webhook' URL 발급)")
        return 1
    if not _OUTBOX.exists():
        print("[consortium] outbox 없음 — `init`/`send` 먼저 실행")
        return 0
    pending = sorted(p for p in _OUTBOX.glob("*.json"))
    if not pending:
        print("[consortium] 발신할 outbox 메시지 없음")
        return 0
    sent_dir = _OUTBOX / "sent"
    sent_dir.mkdir(exist_ok=True)
    ok_count = 0
    for mf in pending:
        m = json.loads(mf.read_text(encoding="utf-8"))
        ok, detail = _post_teams(webhook, _build_teams_card(m))
        tag = "✅" if ok else "❌"
        print(f"  {tag} {m.get('from_team','?')}→{m.get('to_team','?')} cycle={m.get('cycle_id','?')} — {detail}")
        if ok:
            mf.rename(sent_dir / mf.name)
            ok_count += 1
    print(f"[consortium] Teams 발신 완료: {ok_count}/{len(pending)} (성공분 → outbox/sent/)")
    return 0 if ok_count == len(pending) else 1


def _self_team() -> str:
    """이 노드의 팀 id (로스터의 첫 등록 팀). 수신 시 '나에게 온 메시지'만 거른다."""
    teams = list(_load_roster().get("teams", {}))
    return teams[0] if teams else ""


def _graph_get(url: str, token: str) -> tuple[bool, dict | str]:
    """Graph API GET (Bearer). (성공여부, JSON|오류문자열). 네트워크=경계 방어."""
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return True, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return False, f"HTTP {exc.code} {exc.read().decode('utf-8', 'replace')[:300]}"
    except (urllib.error.URLError, OSError, json.JSONDecodeError) as exc:
        return False, f"요청 실패: {exc}"


def _extract_envelope(msg: dict) -> dict | None:
    """Graph 메시지 어디에 박혀 있든 계약 봉투(base64)를 스캔·복원한다. 없으면 None."""
    blob = json.dumps(msg, ensure_ascii=False)  # body·attachments 어디든 마커가 있으면 잡힘
    hit = _ENVELOPE_RE.search(blob)
    if not hit:
        return None
    try:
        return json.loads(base64.b64decode(hit.group(1)).decode("utf-8"))
    except (ValueError, json.JSONDecodeError):
        return None


def _receive_teams() -> int:
    """Graph API 로 채널 메시지를 폴링 → consortium 계약 봉투를 가진 것만 inbox 에 적재.
    토큰/team/channel id 는 환경변수로만 주입. seen 집합으로 멱등(중복 적재 방지)."""
    token = os.environ.get(_TEAMS_TOKEN_ENV, "").strip()
    team_id = os.environ.get(_TEAMS_TEAM_ENV, "").strip()
    channel_id = os.environ.get(_TEAMS_CHANNEL_ENV, "").strip()
    if not (token and team_id and channel_id):
        print("[consortium] ❌ Graph 수신 자격증명 미설정 — 환경변수로 주입 (셸 노출 금지):")
        print(f"  {_TEAMS_TOKEN_ENV} (Bearer 토큰, ChannelMessage.Read.All)")
        print(f"  {_TEAMS_TEAM_ENV} / {_TEAMS_CHANNEL_ENV} (Graph team·channel id)")
        print("  발급 절차: docs/consortium-gateway-setup.md §8 (Graph 폴링 수신)")
        return 1
    me = _self_team()
    if not me:
        print("[consortium] ❌ 로스터에 팀 없음 — `init <team>` 먼저 실행")
        return 1

    _INBOX.mkdir(parents=True, exist_ok=True)
    seen_file = _STATE / "received-seen.json"
    seen = set(json.loads(seen_file.read_text(encoding="utf-8"))) if seen_file.exists() else set()

    url = f"{_GRAPH_BASE}/teams/{team_id}/channels/{channel_id}/messages?$top=50"
    ok, data = _graph_get(url, token)
    if not ok:
        print(f"[consortium] ❌ Graph 폴링 실패 — {data}")
        return 1

    ingested = skipped = 0
    for msg in data.get("value", []):
        gid = msg.get("id", "")
        if gid in seen:
            continue
        seen.add(gid)  # 봉투 유무와 무관하게 본 메시지는 기록 (재스캔 방지)
        contract = _extract_envelope(msg)
        if not contract:
            continue  # consortium 메시지 아님
        # 나에게 온 것만, 내가 보낸 건 제외
        if contract.get("to_team") != me or contract.get("from_team") == me:
            skipped += 1
            continue
        contract["status"] = "received"
        contract["graph_msg_id"] = gid
        safe_ts = str(contract.get("ts", "")).replace(":", "").replace("-", "") or gid
        out = _INBOX / f"{safe_ts}__from-{contract.get('from_team','?')}__{gid[-6:]}.json"
        out.write_text(json.dumps(contract, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  ⬇ {contract.get('from_team','?')} → {me} [{contract.get('role','?')}] "
              f"cycle={contract.get('cycle_id','?')}: {contract.get('msg','')[:50]}")
        ingested += 1

    seen_file.write_text(json.dumps(sorted(seen), ensure_ascii=False), encoding="utf-8")
    print(f"[consortium] Teams 수신 완료: {ingested}건 inbox 적재 "
          f"(타팀행 {skipped}건 제외, 누적 seen {len(seen)})")
    return 0


# ---------------------------------------------------------------------------
# OpenClaw 채널 브리지 (ADR-013) — host=openclaw 일 때 transport.
# webhook/Graph 를 직접 안 쓰고, OpenClaw Gateway(에이전트=courier)에 위임한다.
# consortium 은 핸드오프 디렉토리에 계약을 싣고/내릴 뿐 — 실제 채널 I/O 는 courier 몫.
# ---------------------------------------------------------------------------
def _send_openclaw(platform: str) -> int:
    """outbox 메시지를 OpenClaw outbound 핸드오프로 적재한다.
    OpenClaw 에이전트(courier)가 이를 읽어 자기 채널 reply 도구로 platform 채널에 전송한다."""
    if not _OUTBOX.exists():
        print("[consortium] outbox 없음 — `init`/`send` 먼저 실행")
        return 0
    pending = sorted(_OUTBOX.glob("*.json"))
    if not pending:
        print("[consortium] 발신할 outbox 메시지 없음")
        return 0
    _OC_OUTBOUND.mkdir(parents=True, exist_ok=True)
    sent_dir = _OUTBOX / "sent"
    sent_dir.mkdir(exist_ok=True)
    for mf in pending:
        m = json.loads(mf.read_text(encoding="utf-8"))
        card = _build_teams_card(m)  # 사람용 text + base64 계약 봉투 재사용 (무손실)
        record = {
            "channel": platform,                         # msteams/slack/telegram …
            "conversation_ref": m.get("conversation_ref", ""),  # 원 스레드 복귀용 (있으면)
            "text": card["text"],                        # 봉투 포함 본문
            "consortium_msg": m,                         # 원본 계약 (courier 편의)
        }
        out = _OC_OUTBOUND / mf.name
        out.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        mf.rename(sent_dir / mf.name)
        print(f"  ↪ {m.get('from_team','?')}→{m.get('to_team','?')} [{m.get('role','?')}] "
              f"cycle={m.get('cycle_id','?')} → openclaw-outbound/ ({platform})")
    print(f"[consortium] OpenClaw outbound 적재: {len(pending)}건 "
          f"→ OpenClaw 에이전트(courier)가 채널로 전송")
    return 0


def _receive_openclaw() -> int:
    """OpenClaw inbound 핸드오프(채널에서 받은 메시지)를 읽어 계약을 복원·inbox 적재한다.
    OpenClaw courier 가 채널 수신분을 openclaw-inbound/ 에 드롭한다. 지목 필터 + 멱등."""
    me = _self_team()
    if not me:
        print("[consortium] ❌ 로스터에 팀 없음 — `init <team>` 먼저 실행")
        return 1
    if not _OC_INBOUND.exists() or not any(_OC_INBOUND.glob("*.json")):
        print("[consortium] openclaw-inbound 비어있음 — OpenClaw courier 가 채널 수신분을 여기 드롭")
        return 0
    _INBOX.mkdir(parents=True, exist_ok=True)
    processed_dir = _OC_INBOUND / "processed"
    processed_dir.mkdir(exist_ok=True)
    ingested = skipped = 0
    for rf in sorted(_OC_INBOUND.glob("*.json")):
        record = json.loads(rf.read_text(encoding="utf-8"))
        # 계약 복원: 명시 consortium_msg 우선, 없으면 text 의 base64 봉투 스캔
        contract = record.get("consortium_msg") or _extract_envelope(record)
        if not contract:
            rf.rename(processed_dir / rf.name)
            continue  # consortium 메시지 아님
        if contract.get("to_team") != me or contract.get("from_team") == me:
            rf.rename(processed_dir / rf.name)
            skipped += 1
            continue
        contract["status"] = "received"
        if record.get("conversation_ref"):
            contract["conversation_ref"] = record["conversation_ref"]  # 답장 스레드 복귀용
        safe_ts = str(contract.get("ts", "")).replace(":", "").replace("-", "") or rf.stem
        out = _INBOX / f"{safe_ts}__from-{contract.get('from_team','?')}.json"
        out.write_text(json.dumps(contract, ensure_ascii=False, indent=2), encoding="utf-8")
        rf.rename(processed_dir / rf.name)
        print(f"  ⬇ {contract.get('from_team','?')} → {me} [{contract.get('role','?')}] "
              f"cycle={contract.get('cycle_id','?')}: {contract.get('msg','')[:50]}")
        ingested += 1
    print(f"[consortium] OpenClaw 수신 완료: {ingested}건 inbox 적재 "
          f"(타팀행 {skipped}건 제외, openclaw-inbound/processed/ 로 이동)")
    return 0


def cmd_gateway(args) -> int:
    """메시징 게이트웨이 어댑터 (teams=발신 실구현 / slack·telegram=stub)."""
    platform = args.platform
    host = _detect_host()
    do_send = getattr(args, "send", False)
    do_recv = getattr(args, "receive", False)

    # host=openclaw → OpenClaw Gateway 위임 (ADR-013): webhook/Graph 대신 핸드오프 브리지.
    if host == "openclaw" and (do_send or do_recv):
        if do_send:
            return _send_openclaw(platform)
        interval = getattr(args, "poll", 0) or 0
        if interval <= 0:
            return _receive_openclaw()
        print(f"[consortium] OpenClaw 수신 폴링 — {interval}s 간격 (Ctrl-C 종료)")
        try:
            while True:
                _receive_openclaw()
                time.sleep(interval)
        except KeyboardInterrupt:
            print("\n[consortium] 폴링 종료")
            return 0

    # claude-code/codex host → Teams webhook(발신) + Graph(수신) 직접 transport.
    if platform == "teams" and do_send:
        return _send_teams()
    if platform == "teams" and do_recv:
        interval = getattr(args, "poll", 0) or 0
        if interval <= 0:
            return _receive_teams()
        print(f"[consortium] Teams 수신 폴링 — {interval}s 간격 (Ctrl-C 종료)")
        try:
            while True:
                _receive_teams()
                time.sleep(interval)
        except KeyboardInterrupt:
            print("\n[consortium] 폴링 종료")
            return 0
    desc = _GATEWAYS.get(platform, "?")
    print(f"[consortium] gateway: {platform} — {desc}  (host={host})")
    if host == "openclaw":
        print("  ✅ host=openclaw → OpenClaw Gateway 위임 (ADR-013): `--send`/`--receive` 로")
        print("     openclaw-outbound/·openclaw-inbound/ 핸드오프 브리지 사용 (webhook/Graph 불요).")
        print("     OpenClaw 에이전트(courier)가 네이티브 채널과 핸드오프 사이를 잇는다.")
        print("     설치: docs/consortium-gateway-setup.md §9 (OpenClaw host)")
        return 0
    print("  ⚠️ STUB: 이 하네스는 메시지 계약·로스터·로컬 큐(inbox/outbox)만 stdlib 로 제공합니다.")
    print("  실제 전송(outbox→플랫폼, 플랫폼→inbox)은 자격증명(#3-A)·외부 SDK·웹훅이 필요해")
    print("  **다운스트림이 봇을 붙입니다**. 권장 연동:")
    if platform == "slack":
        print("    - Incoming Webhook 으로 outbox 메시지 POST, Events API 로 수신→inbox")
        print("    - 또는 slack_bolt 봇 (SLACK_BOT_TOKEN, 채널별 cycle_id 매핑)")
    elif platform == "teams":
        print("    - ✅ 발신: `gateway teams --send` (outbox→채널 POST)")
        print(f"      웹훅 URL → `export {_TEAMS_WEBHOOK_ENV}=...` (셸 노출 금지)")
        print("    - ✅ 수신: `gateway teams --receive [--poll N]` (Graph 폴링 채널→inbox)")
        print(f"      토큰/ID → {_TEAMS_TOKEN_ENV}/{_TEAMS_TEAM_ENV}/{_TEAMS_CHANNEL_ENV}")
        print("      (앱 등록 + ChannelMessage.Read.All — docs/consortium-gateway-setup.md §8)")
    elif platform == "telegram":
        print("    - Bot API sendMessage(outbox), getUpdates/webhook(수신→inbox). BotFather 토큰")
    else:
        print(f"    - 지원 플랫폼: {', '.join(_GATEWAYS)}")
        return 1
    print("  계약: outbox/*.json 을 그대로 실어 보내고, 수신은 같은 스키마로 inbox/ 에 적재하면 됨.")
    print("  → graceful degrade: 봇 미연동이어도 로컬 큐로 협업 흐름은 검증 가능.")
    return 0


def cmd_self(args) -> int:
    """환경·의존성·상태 점검."""
    print("[consortium] ── self check ──")
    print(f"  Python: {sys.version.split()[0]} (stdlib only — 외부 의존성 0)")
    print(f"  프로젝트 루트: {_ROOT}")
    print(f"  consortium state: {'존재' if _STATE.exists() else '없음 (init 필요)'}")
    roster = _load_roster()
    print(f"  등록 팀: {len(roster.get('teams', {}))}개")
    print(f"  outbox: {len(list(_OUTBOX.glob('*.json'))) if _OUTBOX.exists() else 0}건 / "
          f"inbox: {len(list(_INBOX.glob('*.json'))) if _INBOX.exists() else 0}건")
    host = _detect_host()
    if host == "openclaw":
        oc_out = len(list(_OC_OUTBOUND.glob("*.json"))) if _OC_OUTBOUND.exists() else 0
        oc_in = len(list(_OC_INBOUND.glob("*.json"))) if _OC_INBOUND.exists() else 0
        print(f"  host: openclaw → transport=OpenClaw 채널 브리지 (ADR-013)")
        print(f"    핸드오프: outbound {oc_out}건 / inbound {oc_in}건 "
              f"(OpenClaw courier 가 네이티브 채널과 연결)")
    else:
        send_ok = "✓" if os.environ.get(_TEAMS_WEBHOOK_ENV, "").strip() else "✗"
        recv_ok = "✓" if all(os.environ.get(e, "").strip()
                             for e in (_TEAMS_TOKEN_ENV, _TEAMS_TEAM_ENV, _TEAMS_CHANNEL_ENV)) else "✗"
        print(f"  host: {host} → transport=Teams webhook+Graph")
        print(f"    게이트웨이: teams=발신[{send_ok}]+수신[{recv_ok}] / slack·telegram=stub")
        print("    (✓=자격증명 준비됨 / ✗=환경변수 미설정 — 기능은 구현됨)")
    return 0


def main() -> None:
    """CLI 진입점."""
    parser = argparse.ArgumentParser(description="분산 멀티팀 에이전트 컨소시엄 (d-3, productnw 전용)")
    sub = parser.add_subparsers(dest="command")

    p_init = sub.add_parser("init", help="이 노드를 컨소시엄 팀으로 등록")
    p_init.add_argument("team", help="team-id (소문자·숫자·하이픈)")
    p_init.add_argument("--agents", help="팀 에이전트 목록 (쉼표구분)")
    p_init.add_argument("--gateway", help="이 팀의 게이트웨이 (slack|teams|telegram)")

    sub.add_parser("roster", help="등록된 팀·에이전트 목록")

    p_send = sub.add_parser("send", help="팀 간 메시지를 outbox 에 기록 (계약 검증)")
    p_send.add_argument("--to", required=True, dest="to", help="수신 팀 id")
    p_send.add_argument("--role", required=True, help="대상 에이전트 역할")
    p_send.add_argument("--cycle", required=True, help="product-cycle id")
    p_send.add_argument("--msg", required=True, help="메시지 본문")
    p_send.add_argument("--stage", help="라이프사이클 단계 (plan|design|develop|verify|deploy)")
    p_send.add_argument("--from", dest="from_team", help="송신 팀 id (생략 시 로스터 추정)")

    p_inbox = sub.add_parser("inbox", help="수신 메시지 목록/표시")
    p_inbox.add_argument("--team", help="특정 수신 팀만 필터")

    p_gw = sub.add_parser("gateway", help="메시징 게이트웨이 (teams=발신 실구현 / 그외 stub)")
    p_gw.add_argument("platform", choices=list(_GATEWAYS), help="slack|teams|telegram")
    p_gw.add_argument("action", nargs="?", default="status", choices=["status", "setup"])
    p_gw.add_argument("--send", action="store_true",
                      help=f"(teams) outbox 메시지를 실제 발신 — 웹훅은 {_TEAMS_WEBHOOK_ENV} 환경변수")
    p_gw.add_argument("--receive", action="store_true",
                      help=f"(teams) Graph 폴링으로 채널→inbox 수신 — {_TEAMS_TOKEN_ENV}/TEAM_ID/CHANNEL_ID 환경변수")
    p_gw.add_argument("--poll", type=int, default=0, metavar="SEC",
                      help="(teams --receive) 주기 폴링 간격(초). 0=1회만")

    sub.add_parser("self", help="환경·의존성 점검")

    args = parser.parse_args()
    handlers = {
        "init": cmd_init, "roster": cmd_roster, "send": cmd_send,
        "inbox": cmd_inbox, "gateway": cmd_gateway, "self": cmd_self,
    }
    if args.command is None:
        parser.print_help()
        sys.exit(0)
    sys.exit(handlers[args.command](args))


if __name__ == "__main__":
    main()
