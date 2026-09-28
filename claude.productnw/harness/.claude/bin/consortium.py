#!/usr/bin/env python3
"""
consortium.py — 분산 멀티팀 에이전트 컨소시엄 (d-3, claude.productnw 전용)

여러 팀이 각자의 멀티 에이전트 하네스를 두고, **팀 간 메시지 계약**으로 통신하며 통합 제품을
만드는 컨소시엄 협업 레이어. ADR-008 의 d-3(이종 호스트 분산) 단계.

설계 (정직):
- **동작하는 핵심(stdlib)**: 메시지 계약(JSON 스키마) + 컨소시엄 로스터 + 로컬 파일 큐(inbox/outbox).
  같은 머신/공유 볼륨에서는 이것만으로 팀 간 메시지·핸드오프가 동작한다.
- **게이트웨이(transport)**: inbox/outbox 를 실제 메신저로 나른다. **Slack 하나만 지원한다.**
  `conversations.history` 는 채널 **로그 읽기**라 다른 봇이 남긴 글이 그대로 들어온다 —
  컨소시엄은 에이전트↔에이전트라 이게 선택 기준의 전부다.

→ 두 수신 경로(slack·openclaw)가 **같은 경계**(`_ingest_record`)를 지난다. 계약 검증·파일명
  위생·유일성이 경로와 무관하게 한 곳에 걸린다 (ADR-013 결정 1 정정).
  `openclaw` 는 메신저 선택지가 아니라 **host=openclaw 일 때의 위임 경로**다 — 채널 연결을
  OpenClaw courier 가 소유하고, consortium 은 핸드오프 디렉토리만 읽고 쓴다.

> **Teams·Telegram 은 제거했다** (2026-09-23, 사용자 결정 "우선 slack 만"). 셋을 함께
> 두는 값보다 **셋을 같은 수준으로 유지하는 비용**이 컸다: 9차 리뷰의 MUST 3건이 전부
> "Slack 에 들어간 수정이 Teams·Telegram 장부 갱신에는 가지 않았다" 였다 (보존 실패 후
> offset ack · quarantine 부재 · `$top=50` nextLink 미추적 — 셋 다 rc=0 조용한 소실).
> 수신 경로를 줄이는 것이 그 결함 클래스를 닫는 가장 싼 방법이다. 필요해지면 되살리되,
> 그때는 장부 갱신까지 parity 테스트로 잠근 뒤 들여온다.

사용법:
  python3 .claude/bin/consortium.py init <team-id> [--agents a,b,c]   # 이 노드를 팀으로 등록
  python3 .claude/bin/consortium.py roster                            # 등록된 팀·에이전트 목록
  python3 .claude/bin/consortium.py send --to <team> --role <agent> --cycle <id> --msg "<텍스트>"
  python3 .claude/bin/consortium.py inbox [--team <team>]             # 수신 메시지 목록/읽기
  python3 .claude/bin/consortium.py gateway slack --send           # outbox → 메신저 (권장)
  python3 .claude/bin/consortium.py gateway slack --receive [--poll N]      # 메신저 → inbox
  python3 .claude/bin/consortium.py self                              # 환경·의존성 점검

상태 위치: .claude/state/consortium/ (roster.json + inbox/ + outbox/ — 런타임 gitignore)
"""
from __future__ import annotations

import argparse
import base64
import json
import math
import os
import re
import sys
import time
import urllib.error
import urllib.parse
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
    data = _load_state(host_json, dict, "host.json")
    if data is not None:
        agent = data.get("agent_type")
        if isinstance(agent, str) and agent.strip():
            return agent.strip()
    return "claude-code"

# 게이트웨이 어댑터 — Slack 단일 (발신+수신 실구현).
_GATEWAYS = {
    "slack": "Slack (chat.postMessage 발신 + conversations.history 폴링 수신)",
}

# 계약 봉투 — 사람용 카드 안에 기계가 무손실 복원할 원본 계약 JSON 을 base64 로 심는다.
# 수신측은 메시지 어디에 박혀 있든 이 마커를 스캔해 원본 메시지를 그대로 복원한다.
_ENVELOPE_PREFIX = "[[consortium-msg]]"
_ENVELOPE_RE = re.compile(re.escape(_ENVELOPE_PREFIX) + r"([A-Za-z0-9+/=]+)")

_TEAM_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
# 오류 문자열에서 봇 토큰을 지우는 패턴 (_safe_err 참조)
_TOKEN_RE = re.compile(r"/bot[^/\s]+/")
# 파일명 한 성분에 허용할 문자 + 그 길이 상한 (_safe_component 참조)
_SAFE_RE = re.compile(r"[^A-Za-z0-9T+]")
_MAX_COMPONENT = 64


def _safe_component(value: str, fallback: str) -> str:
    """원격에서 받은 값을 파일명 **한 성분**으로 쓸 수 있게 화이트리스트로 거른다.

    수신 봉투의 필드는 **신뢰할 수 없는 입력**이다 — 채널에 글을 쓸 수 있는 누구나
    값을 정한다. 이전 구현은 `:` 와 `-` 만 지웠기 때문에 `/` 와 `..` 가 그대로 남았고,
    그 값이 파일명 **선두**에 놓여 경로를 벗어날 수 있었다:

        ts="/etc/ABSOLUTE"    → /etc/ABSOLUTE__from-x.json   (inbox 완전 이탈)
        ts="../../../ESCAPED" → inbox/../../../ESCAPED__...  (상위로 탈출)

    pathlib 은 절대경로 세그먼트를 만나면 앞의 base 를 버리므로 첫 줄이 특히 위험하다.
    제거가 아니라 **허용 문자만 남기는** 방식이라, 새로운 구분자가 생겨도 안전하다.

    길이도 자른다. 화이트리스트만으로는 탈출은 막아도 **길이 공격**이 남는다 —
    ts 300자면 파일명이 255바이트(ext4)를 넘어 `OSError: File name too long` 이 나고,
    그 예외가 수신 루프를 멈추면 경로 탈출과 같은 영구 wedge 가 된다 (재리뷰 실측).
    fallback 도 원격 유래일 수 있으므로(gid) 같은 규칙을 적용한다.
    """
    kept = _SAFE_RE.sub("", str(value or ""))[:_MAX_COMPONENT]
    return kept or _SAFE_RE.sub("", str(fallback or ""))[:_MAX_COMPONENT] or "x"


def _now() -> str:
    """UTC ISO 타임스탬프."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _load_state(path: Path, kind: type, what: str):
    """상태 파일을 **안전하게** 읽는다 (없거나 이상하면 None).

    파싱만 감싸면 부족하다 — 타입이 다르면 소비 지점에서 터진다. 실측으로 확인된
    것들: `slack-seen.json` 이 `[1,2]` 면 `sorted(seen)` 이 TypeError 로 죽고 그
    crash 가 영속 **전**이라 매 폴링 재적재된다. (제거된 Teams·Telegram 경로의
    `received-seen.json`·`telegram-offset.json` 은 열거형 except 라 `RecursionError`
    를 놓쳤다 — 같은 클래스였고, 그래서 방어를 여기 한 곳으로 모았다.)

    상태 파일은 **우리가 쓰지만 디스크가 배신할 수 있는** 입력이다. 여섯 지점이
    제각각이던 것을 여기 하나로 모은다 — 주소가 하나여야 클래스를 닫을 수 있다.
    """
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, kind):
            raise TypeError(f"{kind.__name__} 이 아님: {type(data).__name__}")
        return data
    except Exception as exc:  # noqa: BLE001 — 상태 파일도 신뢰 불가 입력이다
        print(f"  ⚠️ {what} 손상 — 빈 상태로 재시작: {type(exc).__name__}: {str(exc)[:60]}")
        return None


def _write_unique(path: Path, text: str) -> Path:
    """이름이 겹치면 `-1`, `-2` … 를 붙여 **절대 덮어쓰지 않고** 쓴다.

    큐의 최소 계약은 "넣은 메시지가 사라지지 않는다" 이다. 파일명은 초 단위 ts +
    팀 id 로 만들어지는데, 둘 다 유일성을 보장하지 않는다 (실측: 같은 초에 send 2회
    → outbox 1건, 첫 메시지가 rc=0 인 채 소멸). 수신 경로도 ts·from_team 을
    원격이 정하므로 같은 일이 난다.

    접미사를 늘려 확률을 낮추는 대신 **파일시스템의 배타 생성**에 유일성을 맡긴다 —
    확률적 회피는 언젠가 실패하고, 실패가 조용하다.
    """
    path.parent.mkdir(parents=True, exist_ok=True)  # 호출자에게 맡기면 반드시 빠뜨린다
    for n in range(1000):
        candidate = path if n == 0 else path.with_name(f"{path.stem}-{n}{path.suffix}")
        try:
            with open(candidate, "x", encoding="utf-8") as fh:
                fh.write(text)
            return candidate
        except FileExistsError:
            continue
    raise OSError(f"파일명 충돌 1000회 초과: {path.name}")


def _move_unique(src: Path, dest_dir: Path) -> Path:
    """파일을 옮기되 같은 이름이 있으면 `-1`, `-2` … 를 붙인다 — **덮어쓰지 않는다**.

    `Path.rename` 은 POSIX 에서 기존 파일을 **조용히 교체**한다. 큐 파일 이름은 초 단위
    ts + 팀 id 라 유일하지 않으므로, 같은 초의 두 메시지가 큐에서 사라진다 (실측: openclaw
    `--send` 3회 → outbound 1건·sent 1건, 2건이 rc=0 인 채 소멸).

    `_write_unique` 와 짝이다. 그쪽이 "새로 쓰는" 경로를, 이쪽이 "옮기는" 경로를 맡는다 —
    큐의 최소 계약("넣은 메시지가 사라지지 않는다")은 두 경로 모두에서 지켜져야 한다.

    **`os.link` 만 쓰면 안 된다** (QA 실측). 배타 생성은 경쟁까지 막아 주지만 `rename`
    이 되던 것을 못 한다:
      · 디렉토리 — `link` 는 디렉토리에 걸리지 않는다 (courier 가 잘못 만든 드롭)
      · `fs.protected_hardlinks=1` (Ubuntu 기본) 에서 **타 계정 소유 파일은 EPERM** —
        courier 가 별도 계정이면 모든 드롭이 이 경로를 탄다
      · 크로스 디바이스(EXDEV)
    그래서 `link` 가 EEXIST **외의** 이유로 실패하면 `rename` 으로 내려간다. 이름이 비어
    있음은 위에서 확인했으므로 잃는 것은 "경쟁까지 막는 보장" 하나뿐이고, 얻는 것은
    **wedge 가 나지 않는다**는 성질이다. 그 교환이 옳다 — 메시지 소멸과 큐 정지 중
    어느 것도 이름 충돌 확률보다 싸지 않다.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    for n in range(1000):
        candidate = dest_dir / (src.name if n == 0 else f"{src.stem}-{n}{src.suffix}")
        if candidate.exists():
            continue                  # 이름 충돌 — 다음 후보
        try:
            os.link(src, candidate)   # 배타 — 경쟁까지 막는다
        except FileExistsError:
            continue                  # 경쟁에서 짐 — 다음 후보
        except OSError:
            try:
                os.rename(src, candidate)  # 디렉토리·EPERM·EXDEV 폴백
                return candidate
            except OSError:
                continue              # 이 후보가 안 되면 다음 이름으로
        else:
            src.unlink()              # 하드링크 하나를 떼는 것 — 내용은 candidate 에 남는다
            return candidate
    raise OSError(f"이동 실패(후보 1000개 소진): {src.name}")


class RejectedRecord(Exception):
    """수신 경계가 레코드를 거부했다 (거부 사유를 메시지로 싣는다)."""


def _ingest_record(raw: object, me: str, unique_hint: str, extra: dict | None = None) -> dict | None:
    """**수신 신뢰 경계** — 원격이 만든 레코드 1건을 검증·위생 처리해 inbox 에 적재한다.

    transport(Slack history / OpenClaw 드롭)는 "바이트를 어디서 가져오는가" 만 다르고
    그 뒤는 전부 같다. 그래서 이 경계는 **하나뿐이어야 한다** — ADR-013 결정 1 범위 정정.

    경계가 2벌로 복제돼 있던 동안 "결함의 클래스를 닫는다" 가 주소를 갖지 못했다.
    리뷰어는 자기가 찔러본 사본만 보고하고, 수정은 그 사본에만 갔다. 실측 증거:
    `except Exception` 수정이 openclaw 쪽에만 적용되고 (당시의) teams 쪽은 열거형으로
    남아 같은 `RecursionError` 로 뚫렸다 — 클래스를 닫으려던 수정조차 인스턴스만 닫았다.

    Args:
        raw: 원격이 만든 레코드 (Graph 메시지 dict 또는 드롭 파일의 파싱 결과)
        me: 내 팀 id — 지목 필터 기준
        unique_hint: 파일명 유일성 보조 성분 (graph id 꼬리 / 드롭 파일명 꼬리)
        extra: 계약에 덧붙일 로컬 메타 (graph_msg_id 등)

    Returns:
        적재한 계약 dict. consortium 메시지가 아니거나 내 앞으로가 아니면 None.

    Raises:
        RejectedRecord: 계약 위반 — 호출자가 격리·집계한다.
        그 외 모든 예외는 호출자의 경계 핸들러가 잡는다 (예외를 열거하지 않는다).
    """
    if not isinstance(raw, dict):
        raise RejectedRecord(f"최상위가 객체가 아님: {type(raw).__name__}")
    # 계약 복원: 명시 consortium_msg(openclaw 드롭) 우선, 없으면 텍스트의 base64 봉투 스캔(Slack)
    contract = raw.get("consortium_msg") or _extract_envelope(raw)
    if not contract:
        return None  # consortium 메시지 아님
    if not isinstance(contract, dict):
        raise RejectedRecord(f"계약이 객체가 아님: {type(contract).__name__}")
    # 지목 필터 — 채널은 공유되므로 내 앞으로가 아니면 무시
    if contract.get("to_team") != me or contract.get("from_team") == me:
        return None

    # 계약 검증을 **수신에도** 건다 (ADR-012 결정 3 수정). 발신만 검증하면
    # 위협이 있는 쪽엔 검증이 없다 — 값을 정하는 것은 원격이다.
    # `_safe_component` 는 파일명만 지킨다. role·cycle_id 는 product-cycle
    # 라우팅 키로 흘러가므로 계약 검증이 아니면 아무도 지키지 않는다.
    errs = _validate_message(contract)
    if errs:
        raise RejectedRecord("; ".join(errs))

    contract["status"] = "received"
    if extra:
        contract.update(extra)
    safe_ts = _safe_component(contract.get("ts", ""), unique_hint)
    safe_from = _safe_component(contract.get("from_team", ""), "unknown")
    _write_unique(_INBOX / f"{safe_ts}__from-{safe_from}__{_safe_component(unique_hint[-6:], 'x')}.json",
                  json.dumps(contract, ensure_ascii=False, indent=2))
    print(f"  ⬇ {contract.get('from_team','?')} → {me} [{contract.get('role','?')}] "
          f"cycle={contract.get('cycle_id','?')}: {str(contract.get('msg') or '')[:50]}")
    return contract


def _load_roster() -> dict:
    """roster.json 을 읽는다 (없으면 빈 구조)."""
    data = _load_state(_ROSTER, dict, "로스터")
    if data is not None and isinstance(data.get("teams"), dict):
        return data
    return {"teams": {}}


# ---------------------------------------------------------------------------
# 메시지 계약 (inter-team message schema) — 팀 간 상호운용 표준
# ---------------------------------------------------------------------------
# 필수: from_team, to_team, role, cycle_id, msg. 선택: stage, payload, status.
_REQUIRED_MSG_FIELDS = ("from_team", "to_team", "role", "cycle_id", "msg")


def _validate_message(m: dict) -> list[str]:
    """메시지가 계약을 만족하는지 검증하고 위반 목록을 반환한다 (빈 = 통과)."""
    # `str(m.get(f, ""))` 로 비교하면 비문자열이 전부 "존재" 로 통과한다 —
    # str(None)="None", str([])="[]", str(False)="False". send 는 argparse 가 문자열만
    # 주므로 도달하지 않지만 **수신은 원격이 타입까지 정한다**: `role: null` 이 그대로
    # 적재됐다(실측). ADR-012 정정문이 "role·cycle_id 는 라우팅 키, 계약 검증이 지킨다"
    # 고 적은 바로 그 필드라, 타입을 안 보면 그 약속이 성립하지 않는다.
    errs = [f"필수 필드 누락·형식 오류: {f}={m.get(f)!r}" for f in _REQUIRED_MSG_FIELDS
            if not (isinstance(m.get(f), str) and m[f].strip())]
    # 팀 id 는 outbox 파일명에 들어간다 — init 은 _TEAM_RE 로 걸렀는데 send 는
    # 안 걸렀다. 운영자 오타가 파일명으로 새는 것을 여기서 막는다.
    errs += [f"team-id 형식 오류: {f}={m.get(f)!r} (소문자·숫자·하이픈)"
             for f in ("from_team", "to_team")
             if str(m.get(f, "")).strip() and not _TEAM_RE.match(str(m[f]).strip())]
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
        # strip 은 저장 시점에 한다 — 검증만 strip 후 매칭하면 `" team-b"` 가 통과해
        # 파일명과 계약에 공백째 남고, 수신측이 `!= me` 로 조용히 버린다.
        "from_team": (args.from_team or _load_roster().get("self", "")).strip(),
        "to_team": args.to.strip(),
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
    # 파일명: ts + to_team (정렬 가능). ts 는 초 단위라 유일하지 않다 — _write_unique 가 보장.
    safe_ts = msg["ts"].replace(":", "").replace("-", "")
    out_file = _write_unique(_OUTBOX / f"{safe_ts}__to-{msg['to_team']}.json",
                             json.dumps(msg, ensure_ascii=False, indent=2))
    print(f"[consortium] outbox 기록: {out_file.relative_to(_ROOT)}")
    print(f"  {msg['from_team']} → {msg['to_team']} [{args.role}] cycle={args.cycle}")
    print("  → 실제 전송은 `gateway slack --send` (outbox → 채널)")
    return 0


def cmd_inbox(args) -> int:
    """수신 메시지(inbox)를 목록·표시한다. 게이트웨이가 외부→inbox 로 가져온다."""
    if not _INBOX.exists():
        print("[consortium] inbox 없음 — `init` 먼저 실행")
        return 0
    # 파일 하나가 찢어져도 목록 전체가 죽지 않게 한 번만 읽고 거른다 (QA 실측:
    # torn inbox 파일 1건에 `inbox`·`inbox --team` 둘 다 traceback).
    loaded, broken = [], 0
    for mf in sorted(_INBOX.glob("*.json")):
        try:
            loaded.append((mf, json.loads(mf.read_text(encoding="utf-8"))))
        except Exception:  # noqa: BLE001 — 목록 조회는 최대한 보여 주는 쪽이 낫다
            broken += 1
    if args.team:
        loaded = [(mf, m) for mf, m in loaded
                  if isinstance(m, dict) and m.get("to_team") == args.team]
    if broken:
        print(f"[consortium] ⚠️ 읽을 수 없는 inbox 파일 {broken}건 건너뜀")
    if not loaded:
        print("[consortium] inbox 비어있음")
        return 0
    print(f"[consortium] inbox — {len(loaded)}건\n")
    for mf, m in loaded:
        if not isinstance(m, dict):
            print(f"  ⚠️ {mf.name} — 계약이 객체가 아님(건너뜀)")
            continue
        print(f"  ● [{m.get('ts','?')}] {m.get('from_team','?')} → {m.get('to_team','?')} "
              f"[{m.get('role','?')}] cycle={m.get('cycle_id','?')} stage={m.get('stage','-')}")
        print(f"      {m.get('msg','')}")
    return 0


def _safe_err(exc: BaseException, secret: str = "") -> str:
    """예외를 사람이 읽을 문자열로 바꾸되 **자격증명을 흘리지 않는다**.

    Bot API URL 은 경로에 토큰이 박힌다(`/bot<TOKEN>/method`). `urllib` 은 잘못된
    URL 을 통째로 예외 메시지에 실으므로, 그대로 출력하면 토큰이 로그에 남는다.
    """
    text = str(exc)
    if isinstance(exc, urllib.error.HTTPError):
        try:
            text = exc.read().decode("utf-8", "replace")
        except Exception:  # noqa: BLE001 — 오류 보고 중의 오류는 삼킨다
            text = f"HTTP {exc.code}"
    text = _TOKEN_RE.sub("/bot<REDACTED>/", text)
    if secret:
        # 전체 URL 비교만으로는 샌다 — `InvalidURL` 은 **경로만** 싣는다 (실측).
        parts = urllib.parse.urlsplit(secret)
        for chunk in (secret, parts.path, parts.query, f"{parts.path}?{parts.query}"):
            if chunk and len(chunk) > 8 and chunk in text:
                text = text.replace(chunk, "<REDACTED>")
    return text


def _net_boundary_note() -> None:
    """네트워크 응답은 **신뢰 불가 입력**이다 — 예외를 열거하지 않는다.

    실측으로 열거형 except 를 뚫은 것들: `http.client.IncompleteRead`(Content-Length
    불일치 — OSError 아님), 프록시가 돌려준 Latin-1 본문의 `UnicodeDecodeError`,
    최상위가 배열인 JSON 의 `AttributeError`. 셋 다 `--poll` 데몬을 traceback 으로
    죽였다. 이 파일이 레코드 경계에서 세 라운드에 걸쳐 배운 것이 네트워크 경계에도
    그대로 적용된다 — `_slack_api` 가 그 규율을 따른다.
    """


def _self_team() -> str:
    """이 노드의 팀 id (로스터의 첫 등록 팀). 수신 시 '나에게 온 메시지'만 거른다."""
    teams = list(_load_roster().get("teams", {}))
    return teams[0] if teams else ""


# ---------------------------------------------------------------------------
# Slack 게이트웨이 — 유일한 transport (발신·수신 모두 실구현, stdlib only)
# ---------------------------------------------------------------------------
# 왜 Slack 인가 (ADR-013 결정 5, 2026-09-19 정정):
#   컨소시엄은 **에이전트↔에이전트** 통신이다. 그래서 "봇이 다른 봇의 글을 볼 수
#   있는가" 가 플랫폼 선택의 첫 질문이고, 이게 Telegram 을 탈락시킨다 —
#   Bot FAQ: "bots will not be able to see messages from other bots **regardless
#   of mode**". privacy mode 를 꺼도 안 된다 (봇 루프 방지 정책).
#
#   Slack 은 `conversations.history` 가 채널의 **메시지 로그를 읽는** API 라
#   다른 앱/봇이 남긴 글(`bot_id`·`subtype: bot_message`)이 그대로 들어온다.
#   Events API(공개 엔드포인트)나 Socket Mode(SDK)가 필요하다는 것은 **푸시**
#   수신 얘기였고, 폴링 경로는 평범한 HTTPS 라 stdlib 로 완결된다.
#   자격증명도 토큰 1개 + 채널 id 로 끝난다 (Teams 는 4개 + Azure AD 앱 등록 +
#   관리자 동의가 필요했다 — 2026-09-23 에 Teams·Telegram 을 제거한 이유의 일부다).
_SLACK_TOKEN_ENV = "CONSORTIUM_SLACK_TOKEN"      # xoxb- 봇 토큰 (chat:write, channels:history)
_SLACK_CHANNEL_ENV = "CONSORTIUM_SLACK_CHANNEL"  # 채널 id (C...) — 이름 아님
# 테스트 주입 전용 (mock 서버). 운영에서는 건드리지 않는다.
_SLACK_BASE = os.environ.get("CONSORTIUM_SLACK_BASE", "https://slack.com/api")
# `chat.postMessage` 의 text 상한. 넘으면 Slack 이 `msg_too_long` 으로 거부하거나 잘라
# 저장하는데, 잘리면 base64 봉투가 깨져 수신측이 계약을 복원하지 못한다.
_SLACK_TEXT_LIMIT = 40000


def _slack_api(token: str, method: str, payload: dict, get: bool = False) -> tuple[bool, dict | str]:
    """Slack Web API 호출. (성공여부, 응답|오류문자열). 네트워크=경계 방어."""
    url = f"{_SLACK_BASE}/{method}"
    headers = {"Authorization": f"Bearer {token}"}
    try:
        if get:
            url = f"{url}?{urllib.parse.urlencode(payload)}"
            req = urllib.request.Request(url, headers=headers)
        else:
            headers["Content-Type"] = "application/json; charset=utf-8"
            req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"),
                                         headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = json.loads(resp.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as exc:
        if exc.code == 429:
            # rate limit 은 **회복 가능한** 실패다. 다른 오류와 구분해야 호출자가
            # 기다렸다 이어서 완주할 수 있다 — 구분이 없으면 Marketplace 미등재 앱
            # (분당 1회) 체제에서 cursor 가 영구 동결되고 tail 이 영원히 안 온다.
            try:
                wait = int((exc.headers or {}).get("Retry-After", "") or 0)
            except (TypeError, ValueError):
                wait = 0
            return False, {"rate_limited": True, "retry_after": max(0, min(wait, 60))}
        return False, f"HTTP {exc.code} {_safe_err(exc, url)[:300]}"
    except Exception as exc:  # noqa: BLE001 — 네트워크 경계
        return False, f"요청 실패: {_safe_err(exc, url)}"
    if not isinstance(body, dict):
        return False, f"응답이 객체가 아님: {type(body).__name__}"
    if not body.get("ok"):
        # Slack 은 실패도 HTTP 200 으로 준다 — ok 플래그를 봐야 한다.
        if body.get("error") == "ratelimited":
            return False, {"rate_limited": True, "retry_after": 0}
        return False, f"API 거부: {str(body.get('error'))[:200]}"
    return True, body


def _send_slack() -> int:
    """outbox 의 미발신 메시지를 Slack 채널로 발신하고 성공분을 outbox/sent/ 로 옮긴다."""
    token = os.environ.get(_SLACK_TOKEN_ENV, "").strip()
    channel = os.environ.get(_SLACK_CHANNEL_ENV, "").strip()
    if not token or not channel:
        print("[consortium] ❌ Slack 자격증명 미설정 — 환경변수로만 주입 (셸 노출 금지):")
        print(f"  {_SLACK_TOKEN_ENV} (xoxb- 봇 토큰 — chat:write, channels:history)")
        print(f"  {_SLACK_CHANNEL_ENV} (채널 id, C 로 시작 — 채널 '이름' 이 아니다)")
        print("  발급 절차: docs/consortium-gateway-setup.md §2 (Slack — 권장)")
        return 1
    if not _OUTBOX.exists():
        print("[consortium] outbox 없음 — `init`/`send` 먼저 실행")
        return 0
    pending = sorted(_OUTBOX.glob("*.json"))
    if not pending:
        print("[consortium] 발신할 outbox 메시지 없음")
        return 0
    sent_dir = _OUTBOX / "sent"
    sent_dir.mkdir(exist_ok=True)
    ok_count = 0
    for mf in pending:
        try:
            m = json.loads(mf.read_text(encoding="utf-8"))
            if not isinstance(m, dict):
                # 파싱은 성공해도 타입이 다르면 바로 뒤의 `.get()` 이 try **밖**에서
                # 터진다 — 유효한 JSON `[1,2]` 하나로 발신 큐가 영구 정지했다(실측).
                raise TypeError(f"계약이 객체가 아님: {type(m).__name__}")
        except Exception as exc:  # noqa: BLE001 — 찢어진 outbox 파일 하나가 발신 전체를 막지 않는다
            print(f"  ❌ {mf.name} — 읽기 실패: {type(exc).__name__}: {str(exc)[:80]}")
            continue
        text = _build_slack_text(m)
        if len(text) > _SLACK_TEXT_LIMIT:
            # 잘라 보내면 base64 봉투가 깨져 수신측이 계약을 복원하지 못하고, 그러면
            # consortium 메시지가 아닌 것으로 **조용히 무시**된다. 시끄러운 거부를 택한다.
            # (제거된 Telegram 경로에 있던 규율이다 — 경로를 지우면서 같이 버리면
            #  "수정이 갈 곳에 안 간다" 의 반대 방향이 된다.)
            print(f"  ❌ {mf.name} — 본문 {len(text)}자 > 상한 {_SLACK_TEXT_LIMIT}자: "
                  f"outbox 에 남긴다 (msg 를 줄이거나 나눠 보낼 것)")
            continue
        ok, detail = _slack_api(token, "chat.postMessage",
                                {"channel": channel, "text": text,
                                 "unfurl_links": False})
        tag = "✅" if ok else "❌"
        info = f"ts={detail.get('ts')}" if ok and isinstance(detail, dict) else detail
        print(f"  {tag} {m.get('from_team','?')}→{m.get('to_team','?')} "
              f"cycle={m.get('cycle_id','?')} — {info}")
        if ok:
            _move_unique(mf, sent_dir)
            ok_count += 1
    print(f"[consortium] Slack 발신 완료: {ok_count}/{len(pending)} (성공분 → outbox/sent/)")
    return 0 if ok_count == len(pending) else 1


def _build_slack_text(m: dict) -> str:
    """사람이 읽는 줄 + 기계가 무손실 복원할 봉투를 한 메시지에 담는다."""
    envelope = _ENVELOPE_PREFIX + base64.b64encode(
        json.dumps(m, ensure_ascii=False).encode("utf-8")).decode("ascii")
    head = (f"[consortium] {m.get('from_team','?')} → {m.get('to_team','?')} "
            f"[{m.get('role','?')}] cycle={m.get('cycle_id','?')}")
    stage = f"\nstage: {m['stage']}" if m.get("stage") else ""
    return f"{head}{stage}\n{m.get('msg','')}\n\n{envelope}"


def _receive_slack() -> int:
    """conversations.history 로 채널 로그를 읽어 **단일 수신 경계**에 넘긴다."""
    token = os.environ.get(_SLACK_TOKEN_ENV, "").strip()
    channel = os.environ.get(_SLACK_CHANNEL_ENV, "").strip()
    if not token or not channel:
        print("[consortium] ❌ Slack 자격증명 미설정 — 토큰과 채널 id 를 모두 주입한다.")
        print("  채널 id 를 요구하는 이유: 수신 범위를 그 채널로 **못 박기** 위해서다.")
        print("  발급 절차: docs/consortium-gateway-setup.md §2 (Slack — 권장)")
        return 1
    me = _self_team()
    if not me:
        print("[consortium] ❌ 로스터에 팀 없음 — `init <team>` 먼저 실행")
        return 1

    _INBOX.mkdir(parents=True, exist_ok=True)
    cursor_file = _STATE / "slack-cursor.json"
    # 첫 폴링은 기본적으로 **채널 전체 이력**을 훑는다. 긴 채널에 합류하는 노드는
    # 이 값을 주어 시작점을 옮긴다 (`date +%s` 또는 메시지 ts).
    oldest = "0"
    if cursor_file.exists():
        raw_cursor = _load_state(cursor_file, dict, "slack-cursor 기록")
        try:
            oldest = str((raw_cursor or {})["oldest"])
            if not math.isfinite(float(oldest)):   # inf/nan 은 API 가 매번 거부한다
                raise ValueError(f"유한수가 아님: {oldest}")
        except Exception:  # noqa: BLE001
            oldest = "0"
    # 환경변수는 **cursor 가 있어도** 우선한다. 파일 부재 시에만 적용되면, 백로그에
    # 막힌 운영 중 노드에서 문서가 처방한 탈출구가 동작하지 않는다 (QA 실측).
    forced = os.environ.get("CONSORTIUM_SLACK_OLDEST", "").strip()
    if forced:
        try:
            if float(forced) > float(oldest or 0):
                print(f"  ℹ️ CONSORTIUM_SLACK_OLDEST={forced} — 시작점을 앞당긴다 "
                      f"(이전 cursor={oldest}, 그 사이 미수신분은 건너뛴다)")
                oldest = forced
        except (TypeError, ValueError):
            print(f"  ⚠️ CONSORTIUM_SLACK_OLDEST 형식 오류(무시): {forced[:40]!r}")

    # `conversations.history` 는 `oldest` 이후 구간에서 **최신 쪽 limit 건의 창**만 주고
    # 나머지는 `has_more` + `next_cursor` 로 넘긴다. 창만 처리하고 cursor 를 그 창의
    # 최신 ts 로 올리면 **창보다 오래된 미처리분이 영원히 조회되지 않는다** (실측:
    # 250건/limit 200 → 50건 소실). 커서 전진의 불변식이 "처리된 **접두**" 인데,
    # 한 창만 처리하면 처리 집합이 접두가 아니라 접미가 되기 때문이다.
    # → 페이지를 **전부 모은 뒤** ts 오름차순으로 정렬해 처리한다.
    pages, next_cursor, truncated = [], "", False
    for _ in range(50):          # 안전 상한 — 무한 페이지네이션 방지
        payload = {"channel": channel, "oldest": oldest, "limit": 200}
        if next_cursor:
            payload["cursor"] = next_cursor
        ok, body = _slack_api(token, "conversations.history", payload, get=True)
        if not ok and isinstance(body, dict) and body.get("rate_limited"):
            # 유계 재시도 — 같은 페이지를 최대 2회까지 기다렸다 다시 받는다.
            # 무한 대기는 `--poll` 데몬을 멈추고, 재시도가 없으면 이 체제에서
            # 페이지네이션이 영원히 완주하지 못한다 (실측: tail 6건 영구 미도달).
            for attempt in (1, 2):
                wait = body.get("retry_after") or (attempt * 20)
                print(f"  ⏳ rate limit — {wait}s 대기 후 재시도 ({attempt}/2)")
                time.sleep(min(wait, 60))
                ok, body = _slack_api(token, "conversations.history", payload, get=True)
                if ok or not (isinstance(body, dict) and body.get("rate_limited")):
                    break
        if not ok:
            if isinstance(body, dict):
                body = "rate limit (재시도 소진)"
            if pages:
                # 일부만 받았다면 그 구간만 처리하고, 못 받은 더 오래된 구간을
                # 건너뛰지 않도록 cursor 를 **전진시키지 않는다**.
                print(f"  ⚠️ 페이지 수집 중단 — cursor 를 전진시키지 않는다: {body}")
                truncated = True
                break
            print(f"[consortium] ❌ Slack 폴링 실패 — {body}")
            return 1
        chunk = body.get("messages") if isinstance(body, dict) else None
        if not isinstance(chunk, list):
            print("[consortium] ❌ Slack 응답에 messages 배열이 없다")
            return 1
        pages.extend(chunk)
        prev_cursor = next_cursor
        meta = body.get("response_metadata")
        next_cursor = (meta.get("next_cursor") or "") if isinstance(meta, dict) else ""
        if not body.get("has_more") or not next_cursor or next_cursor == prev_cursor:
            break   # 같은 커서를 반복 주는 비정상 서버에서 무한 루프를 막는다
    else:
        truncated = True
        print("  ⚠️ 페이지 상한(50) 도달 — cursor 를 전진시키지 않는다")

    # 수집이 불완전해도 **받은 것은 처리한다**. 두 번의 오답을 거쳐 여기 왔다:
    #   ① 창 하나만 처리하고 cursor 를 올림 → 더 오래된 미처리분 **소실**
    #   ② 전부 못 받으면 아무것도 처리 안 함(all-or-nothing) → **기아**.
    #      실측: 51페이지 백로그(상한 50)에서 폴링 3회 모두 0건, 그 사이 발신한
    #      **신규 메시지조차 영원히 도착하지 않는다**. rc=0 이라 cron 은 성공으로 본다.
    #
    # ①의 진짜 원인은 부분 처리가 아니라 **dedup 부재**였다. `slack-seen.json` 을 두면
    # 부분 처리해도 재적재되지 않는다.
    # → 최신 창은 매 폴링 흐르고(기아 없음), 오래된 구간은 한산할 때 따라잡는다.
    #   cursor 는 여전히 **완전 수집한 회차에만** 전진한다(소실 없음).

    # 정렬 순서를 API 에 의존하지 않는다 — 문서가 순서를 명시하지 않으므로
    # 관측에 기대면 조용히 어긋난다. ts 로 직접 오름차순 정렬한다.
    def _ts_key(m: object) -> float:
        try:
            return float(m.get("ts", 0)) if isinstance(m, dict) else 0.0
        except (TypeError, ValueError):
            return 0.0
    # 페이지가 겹쳐 들어와도 같은 ts 는 한 번만 처리한다.
    seen_ts: set[str] = set()
    messages = []
    for msg in sorted(pages, key=_ts_key):
        key = str(msg.get("ts", "")) if isinstance(msg, dict) else ""
        if key and key in seen_ts:
            continue
        seen_ts.add(key)
        messages.append(msg)

    ingested = skipped = rejected = failed = 0
    quarantine_dir = _STATE / "slack-quarantine"
    # cursor 는 **보존 또는 처리된 접두**까지만 전진시킨다. 한 건이라도 보존에
    # 실패하면 거기서 멈춘다 — 전진시켜 버리면 다음 폴링이 그 메시지를 건너뛰고
    # 원본은 어디에도 남지 않는다 (큐의 최소 계약 위반).
    # `seen` 은 부분 처리의 멱등 장치다 — cursor 가 동결돼도 재적재를 막는다.
    seen_file = _STATE / "slack-seen.json"
    raw_seen = _load_state(seen_file, list, "slack-seen 기록")
    seen: set[str] = {t for t in (raw_seen or []) if isinstance(t, str)}

    advanced = oldest
    frozen = truncated   # 다 못 받았으면 cursor 는 멈춘다 (더 오래된 쪽이 미수집)
    for msg in messages:
        ts = str(msg.get("ts", "")) if isinstance(msg, dict) else ""
        if ts and ts in seen:
            continue                      # 이미 처리한 것 (부분 처리 회차의 잔상)
        # seen 등재는 **처리가 확정된 뒤**다. try 앞에서 등재하면 보존까지 실패한
        # 메시지도 "처리됨" 으로 남아, 동결이 약속한 재시도가 무효가 되고 원본이
        # 어디에도 없이 사라진다 (실측: MSG-2 가 inbox·quarantine 둘 다 없음).
        handled = True
        try:
            if _ingest_record(msg, me, _safe_component(ts, "x"),
                              extra={"slack_ts": ts, "slack_channel": channel}) is None:
                skipped += 1
            else:
                ingested += 1
        except RejectedRecord as exc:
            print(f"  ⚠️ 계약 위반(거부): ts={ts} — {str(exc)[:80]}")
            rejected += 1
        except Exception as exc:  # noqa: BLE001 — 신뢰 불가 원격 입력의 경계
            print(f"  ⚠️ 메시지 처리 실패: ts={ts} — {type(exc).__name__}: {str(exc)[:80]}")
            failed += 1
            try:
                _write_unique(quarantine_dir / f"{_safe_component(ts, 'x')}.json",
                              json.dumps(msg, ensure_ascii=False, indent=2))
            except Exception as keep_exc:  # noqa: BLE001
                # cursor 만 동결한다. 여기서 루프를 끊으면 **뒤의 정상 메시지가 막혀**
                # 이 파일이 다섯 번 고친 wedge 가 그대로 재발한다 (parity 테스트가 잡음).
                print(f"     ↳ 원본 보존 실패 — cursor 를 여기서 동결한다: "
                      f"{type(keep_exc).__name__}: {str(keep_exc)[:60]}")
                frozen = True
                handled = False   # 원본이 어디에도 없다 — 다음 폴링이 다시 받아야 한다
        if ts and handled:
            seen.add(ts)
        if ts and not frozen:
            try:
                float(ts)          # 파싱 불가 ts 를 cursor 에 넣으면 이후 폴링이 전부 실패한다
                advanced = ts
            except (TypeError, ValueError):
                print(f"  ⚠️ ts 형식 이상 — cursor 를 올리지 않는다: {ts[:40]!r}")

    if advanced != oldest:
        tmp = cursor_file.with_suffix(".json.tmp")
        tmp.write_text(json.dumps({"oldest": advanced}), encoding="utf-8")
        os.replace(tmp, cursor_file)
        # cursor 이하는 다시 조회되지 않으므로 seen 에서 덜어낸다 (무한 증가 방지).
        try:
            bound = float(advanced)
        except (TypeError, ValueError):
            bound = None
        if bound is not None:
            # 원소별로 거른다 — 하나가 파싱 불가라고 prune 전체를 포기하면
            # seen 이 영영 줄지 않는다 (실측: `["abc"]` 하나로 전체 중단).
            kept = set()
            for t in seen:
                try:
                    if float(t) > bound:
                        kept.add(t)
                except (TypeError, ValueError):
                    continue      # 파싱 불가 항목은 버린다
            seen = kept
    tmp_seen = seen_file.with_suffix(".json.tmp")
    tmp_seen.write_text(json.dumps(sorted(seen)), encoding="utf-8")
    os.replace(tmp_seen, seen_file)

    tail = ((f", 거부 {rejected}건" if rejected else "")
            + (f", 실패 {failed}건 slack-quarantine/ 보존" if failed else "")
            )
    if truncated:
        tail += ", ⚠️ 페이지 미완 — cursor 동결(오래된 구간은 다음 폴링)"
    print(f"[consortium] Slack 수신 완료: {ingested}건 inbox 적재 "
          f"(미적재 {skipped}건 — 타팀행·비consortium, cursor={advanced}{tail})")
    if truncated:
        # rc 를 구분한다 — `--poll` 루프는 rc 를 안 보므로 데몬은 영향 없고,
        # 1회 실행·cron 은 "받긴 받았지만 뒤가 남았다" 를 알아챈다.
        print("     계속 반복되면 채널 이력이 너무 길거나 rate limit 이다 — "
              "docs/consortium-gateway-setup.md §2-6 참조.")
        return 2
    return 0



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
        try:
            m = json.loads(mf.read_text(encoding="utf-8"))
            if not isinstance(m, dict):
                # 파싱은 성공해도 타입이 다르면 바로 뒤의 `.get()` 이 try **밖**에서
                # 터진다 — 유효한 JSON `[1,2]` 하나로 발신 큐가 영구 정지했다(실측).
                raise TypeError(f"계약이 객체가 아님: {type(m).__name__}")
        except Exception as exc:  # noqa: BLE001 — 찢어진 파일 하나가 발신 전체를 막지 않는다
            print(f"  ❌ {mf.name} — 읽기 실패: {type(exc).__name__}: {str(exc)[:80]}")
            continue
        text = _build_slack_text(m)  # 사람용 줄 + base64 계약 봉투 (무손실 복원용)
        record = {
            "channel": platform,                         # 현재는 항상 "slack"
            "conversation_ref": m.get("conversation_ref", ""),  # 원 스레드 복귀용 (있으면)
            "text": text,                                # 봉투 포함 본문
            "consortium_msg": m,                         # 원본 계약 (courier 편의)
        }
        # courier 가 비동기로 가져가는 **큐**다 — outbox·inbox 와 같은 계약이 걸린다.
        _write_unique(_OC_OUTBOUND / mf.name,
                      json.dumps(record, ensure_ascii=False, indent=2))
        _move_unique(mf, sent_dir)
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
    ingested = skipped = rejected = 0
    quarantine_dir = _OC_INBOUND / "quarantine"
    damaged = stuck = 0
    for rf in sorted(_OC_INBOUND.glob("*.json")):
        # courier 가 드롭하는 파일은 **신뢰할 수 없는 입력**이다 — 전송 중 잘리거나
        # 다른 도구가 쓰다 만 것이 섞인다. 항목 하나의 실패가 큐 전체를 멈추면
        # 그 파일이 processed/ 로 가지 못해 **매 실행 같은 지점에서 영구히 죽는다**.
        # 검증·위생·적재는 전부 `_ingest_record`(단일 수신 경계)가 한다 — 여기 남는
        # 것은 "바이트를 가져온다" 와 성공 후 장부(파일 이동)뿐이다.
        try:
            record = json.loads(rf.read_text(encoding="utf-8"))
            contract = _ingest_record(
                record, me, rf.stem,
                # 답장 스레드 복귀용 — 드롭 레코드에만 있는 로컬 메타
                extra={"conversation_ref": record["conversation_ref"]}
                if isinstance(record, dict) and record.get("conversation_ref") else None)
            _move_unique(rf, processed_dir)
            if contract is None:
                skipped += 1
            else:
                ingested += 1
        except RejectedRecord as exc:
            # 계약 위반(원격이 보낸 것)은 "손상" 이 아니다 — 분리해 집계한다.
            print(f"  ⚠️ 계약 위반(거부): {rf.name} — {str(exc)[:80]}")
            rejected += 1
            try:
                quarantine_dir.mkdir(exist_ok=True)
                if rf.exists():
                    _move_unique(rf, quarantine_dir)
            except Exception as move_exc:  # noqa: BLE001
                print(f"     ↳ 격리 이동 실패 — 큐에 남긴다: {type(move_exc).__name__}")
                stuck += 1
            continue
        except Exception as exc:  # noqa: BLE001 — 신뢰 불가 파일 입력의 경계
            # 예외를 열거하면 반드시 빠뜨린다. 실제로 `RecursionError`("["*100000)가
            # 열거형 튜플을 뚫고 큐를 영구 정지시켰다 — "어떤 필드가 무슨 예외를 낼지
            # 미리 셀 수 없다" 와 열거형 except 는 모순이었다.
            # coding-standards "에러 처리는 경계에서만" 의 바로 그 경계가 여기다.
            # 격리는 **최후 수단**이다. 여기서 던지면 잡는 곳이 없어 루프가 죽고,
            # 그게 바로 이 핸들러가 막으려던 wedge 다 (QA 실측: 디렉토리 드롭 →
            # 격리 이동이 PermissionError → rc=1, 뒤의 정상분 영구 미처리).
            # 이동에 실패하면 그 항목만 큐에 남기고 **다음 항목으로 넘어간다** —
            # 재시도는 되지만 다른 메시지를 막지는 않는다.
            print(f"  ⚠️ 처리 불가 드롭: {rf.name} — {type(exc).__name__}: {str(exc)[:80]}")
            try:
                quarantine_dir.mkdir(exist_ok=True)
                if rf.exists():  # 이동 이후 실패면 이미 processed/ 로 옮겨진 상태
                    _move_unique(rf, quarantine_dir)
                    damaged += 1
            except Exception as move_exc:  # noqa: BLE001 — 최후 수단도 실패할 수 있다
                print(f"     ↳ 격리 이동 실패 — 큐에 남긴다(다음 실행 재시도): "
                      f"{type(move_exc).__name__}: {str(move_exc)[:60]}")
                stuck += 1
            continue
    tail = ((f", 거부 {rejected}건" if rejected else "")
            + (f", 손상 {damaged}건 quarantine/ 격리" if damaged else "")
            + (f", ⚠️ 이동 불가 {stuck}건 큐 잔존" if stuck else ""))
    print(f"[consortium] OpenClaw 수신 완료: {ingested}건 inbox 적재 "
          f"(미적재 {skipped}건 — 타팀행·비consortium, openclaw-inbound/processed/ 로 이동{tail})")
    return 0


def _poll_forever(recv_fn, label: str, interval: int) -> int:
    """수신 함수를 주기 실행한다. **한 회차의 실패가 데몬을 죽이지 않는다.**

    예전엔 `while True: recv_fn(); sleep()` 이 `KeyboardInterrupt` 만 감쌌다. 상태
    파일 교체 중의 `FileNotFoundError`(동시 폴러가 `.tmp` 를 가로챈 경우) 한 번에
    데몬이 traceback 으로 끝났고, cron 재기동이 없으면 그대로 멎었다.

    이 파일은 레코드·네트워크 경계에서 "한 건의 실패가 전체를 막지 않는다" 를 여러
    라운드에 걸쳐 배웠다. 그 규율의 마지막 바깥 테두리가 이 루프다.
    """
    print(f"[consortium] {label} 수신 폴링 — {interval}s 간격 (Ctrl-C 종료)")
    try:
        while True:
            try:
                recv_fn()
            except Exception as exc:  # noqa: BLE001 — 한 회차 실패로 데몬을 끝내지 않는다
                print(f"  ⚠️ 폴링 1회 실패 — 다음 주기에 재시도: "
                      f"{type(exc).__name__}: {str(exc)[:100]}")
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\n[consortium] 폴링 종료")
        return 0


def cmd_gateway(args) -> int:
    """메시징 게이트웨이 어댑터 — Slack 단일 (발신·수신 실구현).

    host=openclaw 면 채널 I/O 를 OpenClaw courier 에 위임한다 (ADR-013). 그건 메신저
    선택지가 아니라 **호스트가 바뀌었을 때의 같은 Slack 채널로 가는 다른 길**이다.
    """
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
        return _poll_forever(_receive_openclaw, "OpenClaw", interval)

    # claude-code/codex host → Slack 직접 transport.
    if platform == "slack" and (do_send or do_recv):
        send_fn, recv_fn = _send_slack, _receive_slack
        if do_send:
            return send_fn()
        interval = getattr(args, "poll", 0) or 0
        if interval <= 0:
            return recv_fn()
        return _poll_forever(recv_fn, platform, interval)
    desc = _GATEWAYS.get(platform, "?")
    print(f"[consortium] gateway: {platform} — {desc}  (host={host})")
    if host == "openclaw":
        print("  ✅ host=openclaw → OpenClaw Gateway 위임 (ADR-013): `--send`/`--receive` 로")
        print("     openclaw-outbound/·openclaw-inbound/ 핸드오프 브리지 사용 (webhook/Graph 불요).")
        print("     OpenClaw 에이전트(courier)가 네이티브 채널과 핸드오프 사이를 잇는다.")
        print("     설치: docs/consortium-gateway-setup.md §10 (OpenClaw host)")
        return 0
    print("  ✅ 실구현 — 봇 토큰 1개 + 채널 id 로 발신·수신이 모두 됩니다.")
    print("    - 발신: `gateway slack --send`        (outbox → chat.postMessage)")
    print("    - 수신: `gateway slack --receive [--poll N]` (conversations.history → inbox)")
    print(f"      자격증명 → {_SLACK_TOKEN_ENV} / {_SLACK_CHANNEL_ENV} (셸 노출 금지)")
    print("      발급 절차: docs/consortium-gateway-setup.md §2")
    # 예전 문구는 "수신은 같은 스키마로 inbox/ 에 적재하면 됨" 이었다. 그건 다운스트림에게
    # **수신 경계를 우회하라고 초대**하는 말이었다 — 검증·위생·유일성이 전부 그 경계에 있다.
    # 경계 바깥에서 inbox 에 직접 쓰면 이 변형이 3라운드에 걸쳐 고친 결함이 그대로 재생산된다.
    print("  수신은 `gateway slack --receive` 가 **단일 수신 경계**에서 계약 검증·위생·")
    print("  유일성을 처리한다. ⚠️ inbox/ 에 직접 쓰지 말 것 — 경계를 건너뛰면 원격이 정한")
    print("  값이 그대로 파일명·경로·라우팅 키가 된다.")
    print("  → graceful degrade: 자격증명 미설정이어도 로컬 큐로 협업 흐름은 검증 가능.")
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
        print("  host: openclaw → transport=OpenClaw 채널 브리지 (ADR-013)")
        print(f"    핸드오프: outbound {oc_out}건 / inbound {oc_in}건 "
              f"(OpenClaw courier 가 네이티브 채널과 연결)")
    else:
        def _flag(env: str) -> str:
            return "✓" if os.environ.get(env, "").strip() else "✗"
        print(f"  host: {host} → transport=Slack (chat.postMessage / conversations.history 폴링)")
        print(f"    게이트웨이: slack=토큰[{_flag(_SLACK_TOKEN_ENV)}]+채널[{_flag(_SLACK_CHANNEL_ENV)}]")
        print("    (✓=자격증명 준비됨 / ✗=환경변수 미설정 — 기능은 구현됨)")
    return 0


def main() -> None:
    """CLI 진입점."""
    parser = argparse.ArgumentParser(description="분산 멀티팀 에이전트 컨소시엄 (d-3, productnw 전용)")
    sub = parser.add_subparsers(dest="command")

    p_init = sub.add_parser("init", help="이 노드를 컨소시엄 팀으로 등록")
    p_init.add_argument("team", help="team-id (소문자·숫자·하이픈)")
    p_init.add_argument("--agents", help="팀 에이전트 목록 (쉼표구분)")
    p_init.add_argument("--gateway", default="slack", choices=list(_GATEWAYS),
                        help="이 팀의 게이트웨이 (현재 slack 만)")

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

    p_gw = sub.add_parser("gateway", help="메시징 게이트웨이 — Slack 단일 (발신·수신 실구현)")
    p_gw.add_argument("platform", nargs="?", default="slack", choices=list(_GATEWAYS),
                      help="slack (기본값이자 유일한 선택지)")
    p_gw.add_argument("action", nargs="?", default="status", choices=["status", "setup"])
    p_gw.add_argument("--send", action="store_true",
                      help="outbox 메시지를 실제 발신 (자격증명은 플랫폼별 환경변수)")
    p_gw.add_argument("--receive", action="store_true",
                      help="채널→inbox 폴링 수신 (자격증명은 플랫폼별 환경변수)")
    p_gw.add_argument("--poll", type=int, default=0, metavar="SEC",
                      help="주기 폴링 간격(초) — --receive 와 함께. 0=1회만")

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
