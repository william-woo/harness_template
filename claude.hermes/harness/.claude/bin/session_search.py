#!/usr/bin/env python3
"""
session_search.py — FTS5 기반 세션 전문(full-text) 검색 (claude.hermes 변형 전용, d-hermes)

Hermes Agent 의 "FTS5 세션 검색 + cross-session recall" 패턴을 하네스에 이식한다.
claude-progress.txt 의 세션 로그 + .claude/state/checkpoints/*.md 를 SQLite FTS5 로
색인하고, 자연어 키워드로 과거 세션을 검색한다.

외부 의존성 0 — Python stdlib(sqlite3 FTS5) 만 사용. FTS5 미지원 빌드면 graceful degrade.

사용법:
  python3 .claude/bin/session_search.py index               # 색인 (재구축)
  python3 .claude/bin/session_search.py search "<질의>"      # FTS5 검색
  python3 .claude/bin/session_search.py search "<질의>" --limit 5
  python3 .claude/bin/session_search.py self                 # 의존성·FTS5 점검

DB 위치: .claude/state/sessions.db (gitignore — 로컬 캐시)
"""
from __future__ import annotations

import argparse
import os
import re
import sqlite3
import sys
from pathlib import Path


def _project_root() -> Path:
    """
    하네스 루트를 반환한다 ($CLAUDE_PROJECT_DIR > 스크립트 위치 기준).

    스크립트는 항상 `<root>/.claude/bin/session_search.py` 에 위치하므로
    parent×3 이 곧 하네스 루트다 (CLAUDE.md·claude-progress.txt 가 있는 곳).
    git toplevel 을 쓰지 않는 이유: 메타 템플릿에서는 변형이 상위 repo 의
    하위 디렉토리라 toplevel 이 변형 루트가 아닌 repo 루트를 가리킨다.
    """
    env = os.environ.get("CLAUDE_PROJECT_DIR")
    if env and Path(env).is_dir():
        return Path(env)
    return Path(__file__).resolve().parent.parent.parent


_ROOT = _project_root()
_DB = _ROOT / ".claude" / "state" / "sessions.db"


def _fts5_available() -> bool:
    """현재 sqlite3 빌드가 FTS5 를 지원하는지 확인한다."""
    try:
        con = sqlite3.connect(":memory:")
        con.execute("CREATE VIRTUAL TABLE _t USING fts5(x)")
        con.close()
        return True
    except sqlite3.OperationalError:
        return False


def _parse_progress(path: Path) -> list[dict]:
    """
    claude-progress.txt 를 세션 블록 단위로 파싱한다.

    신규 prefix 형식 `## [YYYY-MM-DD HH:MM] <agent> | <제목>` 을 헤더로,
    다음 헤더 직전까지를 본문으로 묶는다.

    Returns:
        list[dict]: {"ref", "title", "agent", "ts", "body"} 항목 리스트
    """
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    blocks: list[dict] = []

    # 신규 prefix 형식: `## [YYYY-MM-DD HH:MM] <agent> | <제목>`
    pat_new = re.compile(r"^## \[(.*?)\]\s*(.*?)\s*\|\s*(.*)$", re.MULTILINE)
    matches = list(pat_new.finditer(text))
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        blocks.append({
            "ref": f"progress#{m.group(1)}",
            "ts": m.group(1).strip(),
            "agent": m.group(2).strip(),
            "title": m.group(3).strip(),
            "body": text[start:end].strip(),
        })

    # 레거시 블록 형식: `[YYYY-MM-DD] <agent>: <제목>` ('===' 구분선 사이)
    # CLAUDE.md 가 두 형식 호환을 명시 — 신규 형식에 안 잡힌 헤더만 보강 수집.
    pat_old = re.compile(r"^\[([A-Za-z0-9].*?)\]\s*([^:\s][^:]*?):\s*(.+)$", re.MULTILINE)
    for m in pat_old.finditer(text):
        if any(b["ts"] == m.group(1).strip() and b["title"] == m.group(3).strip()
               for b in blocks):
            continue
        start = m.end()
        nxt = text.find("\n[", start)
        end = nxt if nxt != -1 else len(text)
        body = text[start:end].strip().strip("=").strip()
        blocks.append({
            "ref": f"progress#{m.group(1).strip()}",
            "ts": m.group(1).strip(),
            "agent": m.group(2).strip(),
            "title": m.group(3).strip(),
            "body": body,
        })
    return blocks


def _parse_checkpoints(ckpt_dir: Path) -> list[dict]:
    """.claude/state/checkpoints/*.md 를 항목으로 파싱한다 (파일 1개 = 1 항목)."""
    if not ckpt_dir.is_dir():
        return []
    items: list[dict] = []
    for f in sorted(ckpt_dir.glob("*.md")):
        body = f.read_text(encoding="utf-8")
        first = next((ln for ln in body.splitlines() if ln.strip()), f.stem)
        items.append({
            "ref": f"checkpoint:{f.name}",
            "ts": f.stem[:13],
            "agent": "checkpoint",
            "title": first.lstrip("# ").strip()[:120],
            "body": body,
        })
    return items


def cmd_index(args) -> int:
    """세션 로그 + 체크포인트를 FTS5 테이블로 (재)색인한다."""
    if not _fts5_available():
        print("[session-search] ⚠️ 이 sqlite3 빌드는 FTS5 미지원 — 색인 건너뜀 (graceful degrade)")
        return 0
    _DB.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(_DB)
    con.execute("DROP TABLE IF EXISTS sessions")
    con.execute(
        "CREATE VIRTUAL TABLE sessions USING fts5(ref, ts, agent, title, body)"
    )
    rows = _parse_progress(_ROOT / "claude-progress.txt") + \
        _parse_checkpoints(_ROOT / ".claude" / "state" / "checkpoints")
    con.executemany(
        "INSERT INTO sessions(ref, ts, agent, title, body) VALUES(?,?,?,?,?)",
        [(r["ref"], r["ts"], r["agent"], r["title"], r["body"]) for r in rows],
    )
    con.commit()
    con.close()
    print(f"[session-search] 색인 완료: {len(rows)}개 항목 → {_DB.relative_to(_ROOT)}")
    return 0


def cmd_search(args) -> int:
    """FTS5 MATCH 로 세션을 검색하고 스니펫을 출력한다."""
    if not _fts5_available():
        print("[session-search] ⚠️ FTS5 미지원 — grep 대체를 권장: "
              f"grep -ri '{args.query}' claude-progress.txt")
        return 0
    if not _DB.exists():
        print("[session-search] 색인 없음 — 먼저 `session_search.py index` 실행")
        return 1
    con = sqlite3.connect(_DB)
    con.row_factory = sqlite3.Row
    try:
        cur = con.execute(
            "SELECT ref, ts, agent, title, "
            "snippet(sessions, 4, '[', ']', ' … ', 12) AS snip "
            "FROM sessions WHERE sessions MATCH ? ORDER BY rank LIMIT ?",
            (args.query, args.limit),
        )
        rows = cur.fetchall()
    except sqlite3.OperationalError as exc:
        print(f"[session-search] 질의 오류: {exc} (FTS5 구문 확인)")
        con.close()
        return 1
    con.close()
    if not rows:
        print(f"[session-search] '{args.query}' 결과 없음")
        return 0
    print(f"[session-search] '{args.query}' — {len(rows)}건\n")
    for r in rows:
        print(f"● [{r['ts']}] {r['agent']} | {r['title']}")
        print(f"  ref: {r['ref']}")
        print(f"  … {r['snip']}\n")
    return 0


def cmd_self(args) -> int:
    """의존성·FTS5·색인 상태를 점검한다."""
    print("[session-search] ── self check ──")
    print(f"  sqlite3: {sqlite3.sqlite_version}")
    print(f"  FTS5 지원: {'PASS' if _fts5_available() else 'FAIL (grep 대체)'}")
    print(f"  프로젝트 루트: {_ROOT}")
    print(f"  색인 DB: {'존재' if _DB.exists() else '없음 (index 필요)'}")
    prog = _ROOT / "claude-progress.txt"
    print(f"  claude-progress.txt: {'존재' if prog.exists() else '없음'}")
    return 0


def main() -> None:
    """CLI 진입점."""
    parser = argparse.ArgumentParser(description="FTS5 세션 검색 (claude.hermes 전용)")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("index", help="세션 로그·체크포인트 FTS5 색인 (재구축)")
    p_search = sub.add_parser("search", help="FTS5 검색")
    p_search.add_argument("query", help="검색 질의 (FTS5 구문 지원)")
    p_search.add_argument("--limit", type=int, default=10, help="최대 결과 수 (기본 10)")
    sub.add_parser("self", help="의존성·FTS5 점검")

    args = parser.parse_args()
    handlers = {"index": cmd_index, "search": cmd_search, "self": cmd_self}
    if args.command is None:
        parser.print_help()
        sys.exit(0)
    sys.exit(handlers[args.command](args))


if __name__ == "__main__":
    main()
