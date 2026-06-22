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
import json
import os
import re
import sys
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

# 게이트웨이 어댑터 — teams 는 발신(단방향) 실구현, slack/telegram 은 stub.
_GATEWAYS = {
    "slack": "Slack (Incoming Webhook 또는 Bolt 봇 + bot token)",
    "teams": "MS Teams (Incoming Webhook — 채널 커넥터/Workflows)",
    "telegram": "Telegram (Bot API + BotFather 토큰)",
}

# Teams 발신 어댑터: 웹훅 URL 은 자격증명(autonomous #3-A) — 셸 노출 금지, 환경변수로만 주입.
_TEAMS_WEBHOOK_ENV = "CONSORTIUM_TEAMS_WEBHOOK"

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
    flat = (f"{title}\n역할: {m.get('role','-')} · 단계: {m.get('stage') or '-'} · "
            f"{m.get('ts','-')}\n{m.get('msg','')}")
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


def cmd_gateway(args) -> int:
    """메시징 게이트웨이 어댑터 (teams=발신 실구현 / slack·telegram=stub)."""
    platform = args.platform
    if platform == "teams" and getattr(args, "send", False):
        return _send_teams()
    desc = _GATEWAYS.get(platform, "?")
    print(f"[consortium] gateway: {platform} — {desc}")
    print("  ⚠️ STUB: 이 하네스는 메시지 계약·로스터·로컬 큐(inbox/outbox)만 stdlib 로 제공합니다.")
    print("  실제 전송(outbox→플랫폼, 플랫폼→inbox)은 자격증명(#3-A)·외부 SDK·웹훅이 필요해")
    print("  **다운스트림이 봇을 붙입니다**. 권장 연동:")
    if platform == "slack":
        print("    - Incoming Webhook 으로 outbox 메시지 POST, Events API 로 수신→inbox")
        print("    - 또는 slack_bolt 봇 (SLACK_BOT_TOKEN, 채널별 cycle_id 매핑)")
    elif platform == "teams":
        print("    - ✅ 발신 실구현됨: `gateway teams --send` (outbox→채널 POST)")
        print(f"      웹훅 URL 은 `export {_TEAMS_WEBHOOK_ENV}=...` 환경변수로 주입 (셸 노출 금지)")
        print("    - 수신(채널→inbox)은 Bot Framework + Azure 앱 등록 필요 (다운스트림)")
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
    teams_ready = "ready" if os.environ.get(_TEAMS_WEBHOOK_ENV, "").strip() else f"{_TEAMS_WEBHOOK_ENV} 미설정"
    print(f"  게이트웨이: teams=발신 실구현({teams_ready}) / slack·telegram=stub (다운스트림 봇 연동)")
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
