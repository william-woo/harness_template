#!/usr/bin/env python3
"""
brain.py — 하네스용 cross-project 영구 지식베이스 헬퍼

Python stdlib sqlite3만 사용. 외부 의존성 없음.
DB 위치: ~/.harness/brain.db  (사용자 홈, git 미포함)

서브커맨드:
  init               DB 스키마 초기화 (idempotent)
  sync               현재 프로젝트의 learnings.jsonl + feature_list.json + ADRs를 brain에 동기화
  search <query>     learnings + adrs + features 에서 검색 (LIKE 기반)
  stats              전체 또는 프로젝트별 통계
  list               등록된 프로젝트 목록
  prune              tombstoned learnings 정리

옵션:
  --project <slug>   특정 프로젝트만 (search/stats)
  --all-projects     모든 프로젝트 (search/stats, 기본값)
  --type <T>         learning type 필터
  --limit N          결과 개수 제한 (기본 20)

설계 원칙:
  - 실패해도 절대 호출자를 차단하지 않음 (exit 0 유지)
  - INSERT OR REPLACE 로 idempotent 동기화
  - tombstone 학습은 sync 시점에 제외
  - 프로젝트 식별: git remote URL 또는 디렉토리 basename
"""

from __future__ import annotations
import argparse
import json
import os
import re
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_DB = Path.home() / ".harness" / "brain.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
  slug        TEXT PRIMARY KEY,
  path        TEXT NOT NULL,
  remote_url  TEXT,
  first_seen  TEXT NOT NULL,
  last_seen   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS learnings (
  project_slug TEXT NOT NULL,
  ts           TEXT NOT NULL,
  type         TEXT NOT NULL,
  key          TEXT NOT NULL,
  insight      TEXT NOT NULL,
  confidence   INTEGER,
  source       TEXT,
  feature_id   TEXT,
  files_json   TEXT,
  PRIMARY KEY (project_slug, ts, key),
  FOREIGN KEY (project_slug) REFERENCES projects(slug) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_learnings_key  ON learnings(key);
CREATE INDEX IF NOT EXISTS idx_learnings_type ON learnings(type);

CREATE TABLE IF NOT EXISTS adrs (
  project_slug TEXT NOT NULL,
  adr_id       TEXT NOT NULL,
  title        TEXT NOT NULL,
  status       TEXT,
  decision     TEXT,
  ts           TEXT NOT NULL,
  PRIMARY KEY (project_slug, adr_id),
  FOREIGN KEY (project_slug) REFERENCES projects(slug) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS features (
  project_slug TEXT NOT NULL,
  feature_id   TEXT NOT NULL,
  title        TEXT NOT NULL,
  status       TEXT NOT NULL,
  passes       INTEGER NOT NULL,
  priority     TEXT,
  category     TEXT,
  ts           TEXT NOT NULL,
  PRIMARY KEY (project_slug, feature_id),
  FOREIGN KEY (project_slug) REFERENCES projects(slug) ON DELETE CASCADE
);
"""


# ────────────────────────────────────────────────────────────
# Utility
# ────────────────────────────────────────────────────────────

def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def get_db(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


def detect_project(project_dir: Path) -> tuple[str, str | None]:
    """
    (slug, remote_url) 반환. slug 우선순위:
      1) git remote origin URL의 repo basename
      2) 디렉토리 basename
    """
    remote = None
    try:
        out = subprocess.run(
            ["git", "-C", str(project_dir), "remote", "get-url", "origin"],
            capture_output=True, text=True, timeout=2,
        )
        if out.returncode == 0:
            remote = out.stdout.strip()
    except Exception:
        pass

    if remote:
        m = re.search(r"[/:]([^/:]+?)(?:\.git)?/?$", remote)
        if m:
            return (m.group(1), remote)

    return (project_dir.name, None)


def upsert_project(conn: sqlite3.Connection, slug: str, path: str, remote: str | None) -> None:
    ts = now_iso()
    conn.execute(
        """
        INSERT INTO projects (slug, path, remote_url, first_seen, last_seen)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(slug) DO UPDATE SET
          path = excluded.path,
          remote_url = excluded.remote_url,
          last_seen = excluded.last_seen
        """,
        (slug, path, remote, ts, ts),
    )


# ────────────────────────────────────────────────────────────
# Subcommand: init
# ────────────────────────────────────────────────────────────

def cmd_init(args) -> int:
    db_path = Path(args.db)
    conn = get_db(db_path)
    init_db(conn)
    conn.close()
    print(f"✅ brain.db 초기화: {db_path}")
    return 0


# ────────────────────────────────────────────────────────────
# Subcommand: sync
# ────────────────────────────────────────────────────────────

def parse_adr(file_path: Path) -> dict | None:
    """ADR 파일에서 메타데이터 추출. 매우 관대한 파서."""
    name_match = re.match(r"(ADR-\d+)-?(.*?)\.md$", file_path.name)
    if not name_match:
        return None
    adr_id = name_match.group(1)

    try:
        text = file_path.read_text(encoding="utf-8")
    except Exception:
        return None

    title = adr_id
    h1 = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
    if h1:
        title = h1.group(1).strip()
    elif name_match.group(2):
        title = name_match.group(2).replace("-", " ")

    status = None
    s_match = re.search(r"(?im)^\*?\*?Status\*?\*?\s*[:：]\s*(.+)$", text)
    if s_match:
        status = s_match.group(1).strip().split()[0].lower()

    decision = None
    d_match = re.search(
        r"(?ims)^##\s*(?:Decision|결정)\s*\n+(.*?)(?=\n##|\Z)", text
    )
    if d_match:
        first_para = d_match.group(1).strip().split("\n\n")[0]
        decision = first_para[:500]

    return {
        "adr_id": adr_id,
        "title": title,
        "status": status,
        "decision": decision,
    }


def cmd_sync(args) -> int:
    project_dir = Path(args.project_dir).resolve()
    if not project_dir.exists():
        print(f"❌ 프로젝트 디렉토리 없음: {project_dir}", file=sys.stderr)
        return 1

    db_path = Path(args.db)
    conn = get_db(db_path)
    init_db(conn)

    slug, remote = detect_project(project_dir)
    upsert_project(conn, slug, str(project_dir), remote)
    print(f"📦 프로젝트: {slug}  ({remote or 'no-remote'})")

    learn_count = 0
    feat_count = 0
    adr_count = 0
    skipped_tombstones = 0

    # ── learnings.jsonl ──────────────────────────────
    learn_file = project_dir / ".claude" / "state" / "learnings.jsonl"
    if learn_file.exists():
        tombstoned: set[str] = set()
        entries: list[dict] = []
        with learn_file.open() as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    e = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if e.get("type") == "tombstone":
                    tombstoned.add(e.get("key", ""))
                    continue
                entries.append(e)

        for e in entries:
            if e.get("key") in tombstoned:
                skipped_tombstones += 1
                continue
            conn.execute(
                """INSERT OR REPLACE INTO learnings
                   (project_slug, ts, type, key, insight, confidence,
                    source, feature_id, files_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    slug,
                    e.get("ts", ""),
                    e.get("type", ""),
                    e.get("key", ""),
                    e.get("insight", ""),
                    e.get("confidence"),
                    e.get("source"),
                    e.get("feature_id"),
                    json.dumps(e.get("files", [])),
                ),
            )
            learn_count += 1

    # ── feature_list.json ────────────────────────────
    feat_file = project_dir / "feature_list.json"
    if feat_file.exists():
        try:
            features = json.loads(feat_file.read_text())
            ts = now_iso()
            for feat in features:
                if not isinstance(feat, dict) or "id" not in feat:
                    continue
                conn.execute(
                    """INSERT OR REPLACE INTO features
                       (project_slug, feature_id, title, status, passes,
                        priority, category, ts)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        slug,
                        feat["id"],
                        feat.get("title", ""),
                        feat.get("status", ""),
                        1 if feat.get("passes") else 0,
                        feat.get("priority"),
                        feat.get("category"),
                        ts,
                    ),
                )
                feat_count += 1
        except Exception as ex:
            print(f"⚠️  feature_list.json 파싱 실패: {ex}", file=sys.stderr)

    # ── docs/adr/*.md ────────────────────────────────
    adr_dir = project_dir / "docs" / "adr"
    if adr_dir.is_dir():
        ts = now_iso()
        for f in sorted(adr_dir.glob("ADR-*.md")):
            adr = parse_adr(f)
            if not adr:
                continue
            conn.execute(
                """INSERT OR REPLACE INTO adrs
                   (project_slug, adr_id, title, status, decision, ts)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (slug, adr["adr_id"], adr["title"], adr["status"], adr["decision"], ts),
            )
            adr_count += 1

    conn.commit()
    conn.close()

    print(f"  • learnings: {learn_count} (tombstone 제외 {skipped_tombstones})")
    print(f"  • features:  {feat_count}")
    print(f"  • ADRs:      {adr_count}")
    return 0


# ────────────────────────────────────────────────────────────
# Subcommand: search
# ────────────────────────────────────────────────────────────

def cmd_search(args) -> int:
    # 검색어 비어있어도 --type 또는 --project 필터가 있으면 허용
    if not args.query and not args.type and not args.project:
        print("❌ 검색어 또는 --type / --project 중 하나는 필요", file=sys.stderr)
        return 1

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"ℹ️  brain.db 없음. 먼저 sync 하세요: {db_path}", file=sys.stderr)
        return 0

    conn = get_db(db_path)
    q = f"%{args.query}%" if args.query else None
    limit = args.limit

    sql_filters: list[str] = []
    params: list = []
    if q is not None:
        sql_filters.append("(key LIKE ? OR insight LIKE ?)")
        params.extend([q, q])
    if args.project:
        sql_filters.append("project_slug = ?")
        params.append(args.project)
    if args.type:
        sql_filters.append("type = ?")
        params.append(args.type)

    where = " AND ".join(sql_filters)

    print(f"\n🧠 BRAIN SEARCH '{args.query}'")
    print("=" * 60)

    # Learnings
    rows = conn.execute(
        f"""SELECT project_slug, type, key, insight, confidence, feature_id, ts
            FROM learnings
            WHERE {where}
            ORDER BY confidence DESC NULLS LAST, ts DESC
            LIMIT ?""",
        (*params, limit),
    ).fetchall()
    if rows:
        print(f"\n[LEARNINGS] {len(rows)} matches")
        for proj, t, k, ins, conf, fid, ts in rows:
            fid_s = f" [{fid}]" if fid else ""
            print(f"  • {proj}::{k}{fid_s}  ({t}, conf {conf or '?'}/10)")
            print(f"    └─ {ins[:140]}")

    # ADRs (type 필터 시 ADR 검색 생략 — type 은 learning 전용)
    if not args.type and q is not None:
        adr_filters = ["(title LIKE ? OR decision LIKE ?)"]
        adr_params: list = [q, q]
        if args.project:
            adr_filters.append("project_slug = ?")
            adr_params.append(args.project)
        adr_where = " AND ".join(adr_filters)
        rows = conn.execute(
            f"""SELECT project_slug, adr_id, title, status, decision
                FROM adrs WHERE {adr_where} ORDER BY adr_id LIMIT ?""",
            (*adr_params, limit),
        ).fetchall()
        if rows:
            print(f"\n[ADRs] {len(rows)} matches")
            for proj, aid, title, status, dec in rows:
                print(f"  • {proj}::{aid} {title}  ({status or 'no-status'})")
                if dec:
                    print(f"    └─ {dec[:140]}")

    # Features (제목 검색, type 필터 시 생략)
    if not args.type and q is not None:
        feat_filters = ["title LIKE ?"]
        feat_params: list = [q]
        if args.project:
            feat_filters.append("project_slug = ?")
            feat_params.append(args.project)
        feat_where = " AND ".join(feat_filters)
        rows = conn.execute(
            f"""SELECT project_slug, feature_id, title, status, passes, priority
                FROM features WHERE {feat_where}
                ORDER BY project_slug, feature_id LIMIT ?""",
            (*feat_params, limit),
        ).fetchall()
        if rows:
            print(f"\n[FEATURES] {len(rows)} matches")
            for proj, fid, title, status, passes, pri in rows:
                mark = "✅" if passes else "⬜"
                print(f"  {mark} {proj}::{fid} [{pri or '-'}] ({status}) {title[:80]}")

    conn.close()
    print()
    return 0


# ────────────────────────────────────────────────────────────
# Subcommand: stats
# ────────────────────────────────────────────────────────────

def cmd_stats(args) -> int:
    db_path = Path(args.db)
    if not db_path.exists():
        print(f"ℹ️  brain.db 없음: {db_path}")
        return 0
    conn = get_db(db_path)

    print(f"\n📊 BRAIN STATS")
    print("=" * 60)

    where = "WHERE project_slug = ?" if args.project else ""
    params = (args.project,) if args.project else ()

    proj_count = conn.execute("SELECT COUNT(*) FROM projects").fetchone()[0]
    learn_count = conn.execute(
        f"SELECT COUNT(*) FROM learnings {where}", params
    ).fetchone()[0]
    feat_count = conn.execute(
        f"SELECT COUNT(*) FROM features {where}", params
    ).fetchone()[0]
    feat_done = conn.execute(
        f"SELECT COUNT(*) FROM features {where + (' AND ' if where else 'WHERE ')}passes = 1",
        params,
    ).fetchone()[0]
    adr_count = conn.execute(
        f"SELECT COUNT(*) FROM adrs {where}", params
    ).fetchone()[0]

    scope = f"project={args.project}" if args.project else "ALL projects"
    print(f"\n범위: {scope}")
    print(f"  projects:  {proj_count}")
    print(f"  learnings: {learn_count}")
    print(f"  features:  {feat_count}  (done: {feat_done})")
    print(f"  ADRs:      {adr_count}")

    if not args.project and proj_count > 0:
        print("\n프로젝트별:")
        rows = conn.execute(
            """SELECT p.slug,
                  (SELECT COUNT(*) FROM learnings WHERE project_slug=p.slug),
                  (SELECT COUNT(*) FROM features WHERE project_slug=p.slug),
                  (SELECT COUNT(*) FROM features WHERE project_slug=p.slug AND passes=1),
                  (SELECT COUNT(*) FROM adrs WHERE project_slug=p.slug),
                  p.last_seen
               FROM projects p ORDER BY p.last_seen DESC"""
        ).fetchall()
        for slug, l, f, fd, a, seen in rows:
            print(f"  • {slug:30s} learnings={l:3d}  features={fd}/{f}  adrs={a}  last={seen[:10]}")

    if learn_count > 0:
        print("\nLearnings — type 분포:")
        rows = conn.execute(
            f"""SELECT type, COUNT(*) FROM learnings {where}
                GROUP BY type ORDER BY 2 DESC""",
            params,
        ).fetchall()
        for t, n in rows:
            print(f"  {t:14s}: {n}")

    conn.close()
    print()
    return 0


# ────────────────────────────────────────────────────────────
# Subcommand: list
# ────────────────────────────────────────────────────────────

def cmd_list(args) -> int:
    db_path = Path(args.db)
    if not db_path.exists():
        print(f"ℹ️  brain.db 없음: {db_path}")
        return 0
    conn = get_db(db_path)

    rows = conn.execute(
        """SELECT slug, path, remote_url, first_seen, last_seen
           FROM projects ORDER BY last_seen DESC"""
    ).fetchall()

    if not rows:
        print("등록된 프로젝트 없음. 먼저 sync 하세요.")
        return 0

    print(f"\n🧠 BRAIN PROJECTS ({len(rows)})")
    print("=" * 60)
    for slug, path, remote, first, last in rows:
        print(f"\n• {slug}")
        print(f"    path:   {path}")
        if remote:
            print(f"    remote: {remote}")
        print(f"    first:  {first[:19]}")
        print(f"    last:   {last[:19]}")
    conn.close()
    print()
    return 0


# ────────────────────────────────────────────────────────────
# Main
# ────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="brain.py")
    parser.add_argument("--db", default=str(DEFAULT_DB),
                        help=f"DB 경로 (기본: {DEFAULT_DB})")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init", help="DB 스키마 초기화")

    p_sync = sub.add_parser("sync", help="현재 프로젝트를 brain에 동기화")
    p_sync.add_argument("--project-dir", default=".", help="프로젝트 루트 (기본: 현재 디렉토리)")

    p_search = sub.add_parser("search", help="learnings + adrs + features 검색")
    p_search.add_argument("query", nargs="?", default="", help="검색어")
    p_search.add_argument("--project", help="특정 프로젝트만")
    p_search.add_argument("--type", help="learning type 필터 (pattern/pitfall/...)")
    p_search.add_argument("--limit", type=int, default=20)

    p_stats = sub.add_parser("stats", help="통계")
    p_stats.add_argument("--project", help="특정 프로젝트만")

    sub.add_parser("list", help="등록된 프로젝트 목록")

    args = parser.parse_args(argv)

    handlers = {
        "init": cmd_init,
        "sync": cmd_sync,
        "search": cmd_search,
        "stats": cmd_stats,
        "list": cmd_list,
    }
    try:
        return handlers[args.cmd](args)
    except Exception as ex:
        # hook-failure-tolerance: 호출자를 절대 차단하지 않음
        print(f"⚠️  brain.py {args.cmd} 실패: {ex}", file=sys.stderr)
        return 0


if __name__ == "__main__":
    sys.exit(main())
