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

    args = ap.parse_args()
    return {
        "show": cmd_show, "get": cmd_get, "put": cmd_put,
        "check": cmd_check, "digest": cmd_digest, "pending": cmd_pending,
    }[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
