#!/usr/bin/env python3
"""atlassian_map.py — 하네스 산출물 ↔ Atlassian 객체 매핑을 결정론으로 관리한다.

왜 코드가 필요한가:
  Atlassian MCP(공식 커넥터)가 도구를 이미 제공하므로 **API 호출 래퍼는 만들지 않는다**.
  에이전트가 MCP 도구를 직접 부른다. 코드가 필요한 곳은 딱 하나 —
  **"이걸 이미 발행했는가"** 다.

  모델에게 그 기억을 맡기면 중복 페이지·중복 이슈가 생긴다. 되돌리기 어렵고 팀에 알림까지
  간다. 우리 하네스의 grader(결정론) / judge(모델) 분리를 그대로 적용하는 자리다 —
  **판단은 모델이, 멱등성은 코드가.**

SSOT 방향 (ADR-023 결정 2):
  우리 리포가 SSOT 이고 Atlassian 은 **발행 대상(publish target)** 이다.
  이 스크립트는 역방향 편집을 반영하지 않는다 — 두 SSOT 를 만들면 반드시 어긋난다.

사용:
  atlassian_map.py show                                  # 전체 매핑
  atlassian_map.py get adr ADR-014                       # 단건 조회 (없으면 exit 1)
  atlassian_map.py put adr ADR-014 --url <URL> --id 123  # 발행 후 기록
  atlassian_map.py check adr ADR-014 --digest <sha>      # 재발행 필요 여부 판정
  atlassian_map.py digest docs/adr/ADR-014-*.md          # 파일 내용 digest 계산
  atlassian_map.py pending --kind adr                    # 미발행·변경분 목록

종류(kind): adr | feature | checkpoint | judgement
"""
import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

_KINDS = ("adr", "feature", "checkpoint", "judgement")


def _root() -> Path:
    """하네스 루트를 반환한다 (다른 헬퍼와 동일 규약)."""
    env = os.environ.get("CLAUDE_PROJECT_DIR")
    if env and Path(env).is_dir():
        return Path(env)
    return Path(__file__).resolve().parent.parent.parent


_ROOT = _root()
_MAP = _ROOT / ".claude" / "state" / "atlassian" / "map.json"
_HOST = _ROOT / ".claude" / "host.json"


def _load_host() -> dict:
    """host.json 을 읽는다 (backup.py 와 같은 설정 자리 — 머신 로컬, 미러 제외)."""
    if not _HOST.is_file():
        return {}
    return json.loads(_HOST.read_text(encoding="utf-8"))


def _save_host(data: dict) -> None:
    """host.json 을 쓴다."""
    _HOST.parent.mkdir(parents=True, exist_ok=True)
    _HOST.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def resolve_space(kind: str) -> str | None:
    """이 종류의 산출물이 갈 스페이스를 반환한다.

    **작업 시작 시 한 번 정하고, 발행할 때마다 다시 판단하지 않는다.**
    스페이스가 40개가 넘는 사이트에서 매번 고르면 언젠가 틀린 곳에 공개된다 —
    틀린 스페이스는 페이지를 지워도 알림이 이미 간 뒤다 (ADR-023 결정 5).

    우선순위: kind 별 지정 → default → 없음(None → 호출부가 사용자에게 묻는다).
    """
    spaces = (_load_host().get("atlassian") or {}).get("spaces") or {}
    return spaces.get(kind) or spaces.get("default")


def _load() -> dict:
    """매핑 파일을 읽는다. 없으면 빈 구조."""
    if not _MAP.is_file():
        return {"version": 1, "entries": {}}
    return json.loads(_MAP.read_text(encoding="utf-8"))


def _save(data: dict) -> None:
    """매핑 파일을 쓴다."""
    _MAP.parent.mkdir(parents=True, exist_ok=True)
    _MAP.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _key(kind: str, local_id: str) -> str:
    """매핑 키를 만든다."""
    if kind not in _KINDS:
        raise SystemExit(f"[atlassian-map] ❌ 알 수 없는 kind: {kind} (허용: {', '.join(_KINDS)})")
    return f"{kind}:{local_id}"


def file_digest(path: Path) -> str:
    """파일 내용의 digest 를 계산한다 (재발행 필요 판정용)."""
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def cmd_digest(args) -> int:
    """파일 digest 를 출력한다."""
    p = Path(args.path)
    if not p.is_file():
        print(f"[atlassian-map] ❌ 파일 없음: {p}")
        return 1
    print(file_digest(p))
    return 0


def cmd_show(args) -> int:
    """전체 매핑을 표로 출력한다."""
    data = _load()
    entries = data.get("entries") or {}
    if not entries:
        print(f"[atlassian-map] 매핑 없음 ({_MAP})")
        return 0
    print(f"[atlassian-map] {len(entries)}건 — {_MAP}")
    for k, v in sorted(entries.items()):
        kind, local = k.split(":", 1)
        print(f"  {kind:10} {local:28} → {v.get('url', '?')}")
        print(f"  {'':10} {'':28}   digest={v.get('digest', '-')} published={v.get('published_at', '-')}")
    return 0


def cmd_get(args) -> int:
    """단건 매핑을 조회한다. 없으면 exit 1 (셸에서 분기 가능)."""
    entry = (_load().get("entries") or {}).get(_key(args.kind, args.local_id))
    if not entry:
        print(f"[atlassian-map] 미발행: {args.kind}:{args.local_id}")
        return 1
    print(json.dumps(entry, ensure_ascii=False, indent=2))
    return 0


def cmd_put(args) -> int:
    """발행 결과를 기록한다. 같은 키에 다시 쓰면 갱신(재발행)으로 본다."""
    data = _load()
    entries = data.setdefault("entries", {})
    k = _key(args.kind, args.local_id)
    prev = entries.get(k)
    entries[k] = {
        "url": args.url,
        "remote_id": args.id,
        "digest": args.digest,
        "published_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "revision": (prev or {}).get("revision", 0) + 1,
    }
    _save(data)
    verb = "갱신" if prev else "신규"
    print(f"[atlassian-map] ✅ {verb} 기록: {k} → {args.url} (revision {entries[k]['revision']})")
    return 0


def cmd_init(args) -> int:
    """스페이스·사이트를 **작업 시작 시 한 번** 정한다 (backup.py init 과 같은 규약).

    발행 때마다 스페이스를 고르면 판단이 반복되고, 40개가 넘는 스페이스 중 하나를
    언젠가 틀리게 고른다. 틀린 스페이스는 되돌리기 어렵다 — 페이지를 지워도 알림은 이미 갔다.

    설정은 `host.json` 의 `atlassian` 필드에 둔다 (머신 로컬 — 미러 제외, ADR-015 결정 2).
    이미 설정돼 있으면 현재 값을 보여주고 `--force` 없이는 덮어쓰지 않는다.
    """
    host = _load_host()
    cur = host.get("atlassian") or {}
    if cur and not (args.force or args.space or args.site or args.space_for):
        print("[atlassian-map] 현재 설정:")
        print(f"  사이트   : {cur.get('site', '-')}")
        print(f"  cloudId  : {cur.get('cloudId', '-')}")
        for k, v in sorted((cur.get("spaces") or {}).items()):
            print(f"  스페이스 : {k:12} → {v}")
        print("  변경하려면 --space/--site/--space-for 를 주거나 --force 를 붙이십시오.")
        return 0

    spaces = dict(cur.get("spaces") or {})
    if args.space:
        spaces["default"] = args.space
    for pair in args.space_for or []:
        if "=" not in pair:
            raise SystemExit(f"[atlassian-map] ❌ --space-for 형식은 kind=KEY 입니다: {pair}")
        kind, key = pair.split("=", 1)
        if kind not in _KINDS:
            raise SystemExit(f"[atlassian-map] ❌ 알 수 없는 kind: {kind} (허용: {', '.join(_KINDS)})")
        spaces[kind] = key
    if not spaces:
        raise SystemExit("[atlassian-map] ❌ 최소한 --space <KEY> 로 기본 스페이스를 정하십시오.")

    host["atlassian"] = {
        "site": args.site or cur.get("site", ""),
        "cloudId": args.cloud_id or cur.get("cloudId", ""),
        "spaces": spaces,
    }
    _save_host(host)
    print("[atlassian-map] ✅ 설정 저장 (host.json · 머신 로컬)")
    print(f"  사이트   : {host['atlassian']['site'] or '(미지정)'}")
    print(f"  cloudId  : {host['atlassian']['cloudId'] or '(미지정 — getAccessibleAtlassianResources 로 확인)'}")
    for k, v in sorted(spaces.items()):
        print(f"  스페이스 : {k:12} → {v}")
    return 0


def cmd_space(args) -> int:
    """이 종류가 갈 스페이스를 출력한다. 미설정이면 exit 1 (호출부가 사용자에게 묻는다)."""
    key = resolve_space(args.kind)
    if not key:
        print(f"[atlassian-map] 스페이스 미설정 ({args.kind}) — "
              "`atlassian_map.py init --space <KEY>` 로 먼저 정하십시오.\n"
              "  추측해서 발행하지 않습니다. 틀린 스페이스는 되돌리기 어렵습니다.")
        return 1
    print(key)
    return 0


def cmd_forget(args) -> int:
    """매핑을 지운다. **원격 페이지는 지우지 않는다** — 기록만 끊는다.

    필요한 경우: 원격에서 페이지가 삭제됐거나, 시험용으로 남은 기록을 정리할 때.
    이 명령 뒤에는 다음 `check` 가 '신규'로 판정하므로 새 페이지가 생긴다 — 원격에
    페이지가 남아 있는 상태에서 부르면 중복이 만들어진다. 그래서 확인을 요구한다.
    """
    data = _load()
    k = _key(args.kind, args.local_id)
    entry = (data.get("entries") or {}).get(k)
    if not entry:
        print(f"[atlassian-map] 기록 없음: {k}")
        return 1
    if not args.yes:
        print(f"[atlassian-map] 지울 기록: {k} → {entry.get('url')}\n"
              "  원격 페이지는 지워지지 않습니다. 이후 발행하면 **새 페이지가 생깁니다**.\n"
              "  진행하려면 --yes 를 붙이십시오.")
        return 2
    del data["entries"][k]
    _save(data)
    print(f"[atlassian-map] ✅ 기록 삭제: {k} (원격 페이지는 그대로)")
    return 0


def cmd_check(args) -> int:
    """재발행이 필요한지 판정한다.

    exit 0 = 발행 필요 없음(동일 digest) / exit 2 = 신규 발행 / exit 3 = 갱신 발행
    셸에서 `case $?` 로 분기한다. 판단을 모델에게 맡기지 않는 것이 요점이다.
    """
    entry = (_load().get("entries") or {}).get(_key(args.kind, args.local_id))
    if not entry:
        print(f"[atlassian-map] 신규 — 발행 대상 ({args.kind}:{args.local_id})")
        return 2
    if entry.get("digest") != args.digest:
        print(f"[atlassian-map] 변경 감지 — 갱신 대상 "
              f"(기록 {entry.get('digest')} ≠ 현재 {args.digest})\n  대상: {entry.get('url')}")
        return 3
    print(f"[atlassian-map] 최신 — 발행 불필요 ({entry.get('url')})")
    return 0


def cmd_pending(args) -> int:
    """발행 대상 후보를 나열한다 (ADR 은 파일 스캔으로 자동 수집)."""
    if args.kind != "adr":
        print(f"[atlassian-map] pending 은 현재 adr 만 지원합니다 (요청: {args.kind})")
        return 1
    entries = _load().get("entries") or {}
    adr_dir = _ROOT / "docs" / "adr"
    if not adr_dir.is_dir():
        print(f"[atlassian-map] docs/adr 없음: {adr_dir}")
        return 1
    rows = []
    for f in sorted(adr_dir.glob("ADR-*.md")):
        if f.name == "ADR-000-template.md":
            continue      # 템플릿은 발행 대상이 아니다
        adr_id = f.name.split("-")[0] + "-" + f.name.split("-")[1]
        cur = file_digest(f)
        rec = entries.get(_key("adr", adr_id))
        if not rec:
            rows.append(("신규", adr_id, f.name, "-"))
        elif rec.get("digest") != cur:
            rows.append(("변경", adr_id, f.name, rec.get("url", "?")))
    if not rows:
        print("[atlassian-map] ✅ 발행 대상 없음 — 모든 ADR 이 최신입니다")
        return 0
    print(f"[atlassian-map] 발행 대상 {len(rows)}건")
    for state, adr_id, name, url in rows:
        print(f"  [{state}] {adr_id:10} {name:52} {url}")
    return 0


def main() -> int:
    """CLI 진입점."""
    ap = argparse.ArgumentParser(description="하네스 산출물 ↔ Atlassian 매핑 (결정론 층위)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("show", help="전체 매핑 출력")

    for name, help_text in (("get", "단건 조회"), ("check", "재발행 필요 여부")):
        s = sub.add_parser(name, help=help_text)
        s.add_argument("kind", choices=_KINDS)
        s.add_argument("local_id")
        if name == "check":
            s.add_argument("--digest", required=True)

    s = sub.add_parser("put", help="발행 결과 기록")
    s.add_argument("kind", choices=_KINDS)
    s.add_argument("local_id")
    s.add_argument("--url", required=True)
    s.add_argument("--id", default="")
    s.add_argument("--digest", default="")

    s = sub.add_parser("digest", help="파일 digest 계산")
    s.add_argument("path")

    s = sub.add_parser("pending", help="발행 대상 나열")
    s.add_argument("--kind", default="adr", choices=_KINDS)

    s = sub.add_parser("forget", help="매핑 기록 삭제 (원격 페이지는 유지)")
    s.add_argument("kind", choices=_KINDS)
    s.add_argument("local_id")
    s.add_argument("--yes", action="store_true", help="확인 없이 삭제")

    s = sub.add_parser("init", help="스페이스·사이트 초기 설정 (작업 시작 시 1회)")
    s.add_argument("--space", help="기본 스페이스 키 (예: SD)")
    s.add_argument("--space-for", action="append", metavar="kind=KEY",
                   help="종류별 스페이스 (예: adr=SD). 여러 번 지정 가능")
    s.add_argument("--site", help="사이트 호스트명 (예: obigoinc.atlassian.net)")
    s.add_argument("--cloud-id", help="cloudId (UUID)")
    s.add_argument("--force", action="store_true", help="기존 설정 덮어쓰기")

    s = sub.add_parser("space", help="이 종류가 갈 스페이스 출력 (미설정이면 exit 1)")
    s.add_argument("kind", choices=_KINDS)

    args = ap.parse_args()
    return {
        "show": cmd_show, "get": cmd_get, "put": cmd_put, "check": cmd_check,
        "digest": cmd_digest, "pending": cmd_pending, "forget": cmd_forget,
        "init": cmd_init, "space": cmd_space,
    }[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
