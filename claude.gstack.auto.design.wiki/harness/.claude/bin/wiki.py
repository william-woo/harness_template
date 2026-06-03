#!/usr/bin/env python3
"""wiki.py — LLM Wiki 지식 그래프 헬퍼 (F012).

claude.gstack.auto.design.wiki 변형 전용. 프로젝트 산출물 (feature/ADR/learning)
을 Obsidian vault + [[wikilink]] 지식 그래프로 변환·관리한다.

서브커맨드:
  ingest [source]  — 산출물 → vault 노드 (결정론적 매핑 + 옵션 LLM 보강)
  query <검색어>    — (세션 2) vault 검색 (qmd / stdlib grep 자동 분기)
  lint             — (세션 2) vault 정합성 점검 (고아 / stale / 끊긴 wikilink / frontmatter)
  graph            — (세션 2) DOT/mermaid 텍스트 그래프 출력
  self             — 의존성 점검 (Obsidian/qmd/Marp 설치 여부 + graceful degrade 상태)

전역 옵션:
  --vault <path>   — vault 위치 override (테스트용, 기본: <project-root>/wiki/)
  --strict         — BLOCK 1건이라도 있으면 exit 1 (F009 lint.py 일관)
  --format human|json — 출력 형식 (기본: human)

외부 의존성 0 정책 예외 (ADR-007 결정 1):
  - 핵심 기능 (ingest/lint/graph + query stdlib fallback) 은 Python stdlib 만
  - 외부 도구 (Obsidian / qmd / Marp) 는 검색·시각화 향상용 (graceful degrade — 결정 5)
  - 세션 2: query/lint/graph 구현 (이 서브커맨드들은 세션 2에서 추가됨)

설계 원칙:
  - hook-failure-tolerance: 실패해도 exit 0 (--strict 명시 시만 exit 1)
  - 결정론적 매핑: 같은 소스이면 항상 같은 노드 (LLM 보강은 --enrich-llm 옵트인)
  - 멱등성: 재실행해도 같은 결과 (기존 노드 덮어쓰기 — atomic write)
  - F005/F009/F010/F011 단일 파일 헬퍼 패턴 100% 일관
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# ─── 경로 상수 ────────────────────────────────────────────────────────────────

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_VAULT_DIR_DEFAULT = _PROJECT_ROOT / "wiki"
_FEATURE_LIST = _PROJECT_ROOT / "feature_list.json"
_ADR_DIR = _PROJECT_ROOT / "docs" / "adr"
_LEARNINGS = _PROJECT_ROOT / ".claude" / "state" / "learnings.jsonl"

# 라벨 (F009 lint / F011 design_pick 일관)
BLOCK = "BLOCK"
CONCERN = "CONCERN"
INFO = "INFO"
PASS_LABEL = "PASS"

# KST 오프셋 표기 (로컬 TZ 비의존성을 위해 UTC 명시)
_TZ_LABEL = "+00:00"


# ─── 유틸 ──────────────────────────────────────────────────────────────────────

def _now_iso() -> str:
    """현재 시각을 ISO 8601 형식으로 반환 (UTC)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S") + _TZ_LABEL


def _slug_from_text(text: str, max_len: int = 40) -> str:
    """텍스트를 파일명 안전한 slug 로 변환.

    Args:
        text: 원본 텍스트
        max_len: 최대 slug 길이

    Returns:
        소문자, 알파벳/숫자/하이픈만 포함한 slug
    """
    slug = text.lower()
    slug = re.sub(r"[^a-z0-9가-힣\s-]", "", slug)
    slug = re.sub(r"\s+", "-", slug.strip())
    slug = re.sub(r"-+", "-", slug)
    return slug[:max_len].rstrip("-")


def _atomic_write(path: Path, content: str) -> None:
    """원자적으로 파일을 쓴다 (임시 파일 → rename).

    Args:
        path: 대상 파일 경로
        content: 쓸 내용
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_path = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _detect_external_tools() -> dict[str, bool]:
    """외부 도구 설치 여부 자동 감지 (ADR-007 결정 5).

    Returns:
        dict: {tool: bool} — True 면 사용 가능, False 면 fallback
    """
    return {
        "qmd": shutil.which("qmd") is not None,
        "obsidian": _detect_obsidian_vault(),
        "marp": shutil.which("marp") is not None,
    }


def _detect_obsidian_vault() -> bool:
    """vault 에 .obsidian/ 폴더가 있으면 Obsidian 설정 존재로 간주.

    Returns:
        bool: .obsidian/ 존재 여부
    """
    vault = _VAULT_DIR_DEFAULT
    return (vault / ".obsidian").is_dir()


def _load_feature_list(feature_list_path: Path) -> list[dict]:
    """feature_list.json 을 읽어 feature 목록을 반환.

    Args:
        feature_list_path: feature_list.json 경로

    Returns:
        list: feature dict 목록. 파일 없으면 빈 리스트.
    """
    if not feature_list_path.exists():
        return []
    try:
        data = json.loads(feature_list_path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data
        return []
    except (json.JSONDecodeError, OSError):
        return []


def _build_index_content(vault_dir: Path) -> str:
    """wiki/index.md 콘텐츠를 생성한다.

    vault 내 nodes 하위 디렉토리를 스캔하여 카탈로그를 구성한다.

    Args:
        vault_dir: vault 루트 경로

    Returns:
        str: index.md 전체 내용
    """
    now = _now_iso()
    sections: dict[str, list[str]] = {
        "features": [],
        "adrs": [],
        "learnings": [],
        "pages": [],
        "sources": [],
    }

    for node_type in sections:
        node_dir = vault_dir / node_type
        if not node_dir.exists():
            continue
        for md_file in sorted(node_dir.glob("*.md")):
            node_id = md_file.stem
            sections[node_type].append(f"- [[{node_id}]]")

    total = sum(len(v) for v in sections.values())

    lines = [
        "# Wiki Vault 카탈로그",
        "",
        "> 이 파일은 `python3 .claude/bin/wiki.py ingest` 가 자동으로 갱신합니다.",
        "> 직접 편집하지 마세요 — 다음 ingest 시 덮어씌워집니다.",
        "",
        f"**마지막 갱신**: {now}",
        f"**노드 수**: {total}",
        "",
        "---",
        "",
    ]

    labels = {
        "features": "Features",
        "adrs": "ADRs",
        "learnings": "Learnings",
        "pages": "Pages",
        "sources": "Sources",
    }

    for node_type, entries in sections.items():
        label = labels[node_type]
        lines.append(f"## {label} ({len(entries)})")
        lines.append("")
        if entries:
            lines.extend(entries)
        else:
            lines.append("_(없음)_")
        lines.append("")

    return "\n".join(lines)


def _append_log(vault_dir: Path, action: str, summary: str) -> None:
    """wiki/log.md 에 항목을 prepend (F009 prefix 컨벤션).

    Args:
        vault_dir: vault 루트 경로
        action: 동작 이름 (ingest / query / lint 등)
        summary: 한 줄 요약
    """
    log_path = vault_dir / "log.md"
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
    new_entry = f"\n## [{ts}] {action} | {summary}\n"

    if log_path.exists():
        existing = log_path.read_text(encoding="utf-8")
        # 헤더 라인 유지 + 새 항목 삽입
        header_end = existing.find("\n---\n")
        if header_end != -1:
            header = existing[: header_end + 5]
            body = existing[header_end + 5:]
            content = header + new_entry + body
        else:
            content = existing + new_entry
    else:
        content = (
            "# Wiki 변경 로그\n\n"
            "> F009 prefix 컨벤션: `## [YYYY-MM-DD HH:MM] <action> | <요약>`\n\n"
            "---\n"
            + new_entry
        )

    log_path.write_text(content, encoding="utf-8")


# ─── ingest: feature_list.json → nodes/features/ ─────────────────────────────

def _ingest_features(vault_dir: Path, enrich_llm: bool = False) -> tuple[int, int]:
    """feature_list.json 각 항목을 wiki/features/<id>.md 노드로 변환.

    ADR-007 결정 3: 결정론적 매핑.
    - dependencies → related: [...] wikilink 엣지
    - 역방향 엣지 (dependents) 도 자동 계산

    Args:
        vault_dir: vault 루트 경로
        enrich_llm: LLM 보강 모드 (세션 1 은 안내만 출력)

    Returns:
        tuple: (생성된 노드 수, 건너뛴 수)
    """
    features_dir = vault_dir / "features"
    features_dir.mkdir(parents=True, exist_ok=True)

    features = _load_feature_list(_FEATURE_LIST)
    if not features:
        print(f"  CONCERN: feature_list.json 없음 또는 비어있음 ({_FEATURE_LIST})")
        print("           graceful — features 노드 생성 스킵")
        return 0, 0

    # 역방향 엣지 계산: id → dependents
    dependents: dict[str, list[str]] = {}
    for f in features:
        for dep in f.get("dependencies", []):
            dependents.setdefault(dep, []).append(f["id"])

    created = 0
    for feature in features:
        fid = feature.get("id", "")
        if not fid:
            continue

        title = feature.get("title", fid)
        description = feature.get("description", "")
        ac_list = feature.get("acceptance_criteria", [])
        deps = feature.get("dependencies", [])
        status = feature.get("status", "todo")
        passes = feature.get("passes", False)
        tags = [feature.get("category", ""), f"phase-{_guess_phase(fid)}"]
        tags = [t for t in tags if t]

        # related: dependencies
        related_refs = deps[:]

        # 본문 wikilink (dependencies)
        dep_body = ""
        if deps:
            dep_body = "## Dependencies\n\n"
            for dep in deps:
                dep_body += f"- [[{dep}]]\n"
        else:
            dep_body = "## Dependencies\n\n_(없음)_\n"

        # dependents (역방향)
        dep_back = dependents.get(fid, [])
        dep_back_body = "## Dependents\n\n"
        if dep_back:
            for d in dep_back:
                dep_back_body += f"- [[{d}]]\n"
        else:
            dep_back_body += "_(없음)_\n"

        # AC 목록
        ac_body = "## Acceptance Criteria\n\n"
        if ac_list:
            for ac in ac_list:
                ac_body += f"- {ac}\n"
        else:
            ac_body += "_(없음)_\n"

        # frontmatter
        related_yaml = json.dumps(related_refs) if related_refs else "[]"
        tags_yaml = json.dumps(tags)
        node_status = "active" if passes else "draft"
        frontmatter = (
            "---\n"
            f"type: feature\n"
            f"id: {fid}\n"
            f"created: {_now_iso()}\n"
            f"source_ref: feature_list.json#{fid}\n"
            f"tags: {tags_yaml}\n"
            f"related: {related_yaml}\n"
            f"status: {node_status}\n"
            "---\n"
        )

        body = (
            f"# {fid} — {title}\n\n"
            f"{description}\n\n"
            f"{ac_body}\n"
            f"{dep_body}\n"
            f"{dep_back_body}\n"
            f"**Status**: `{status}` | **Passes**: `{passes}`\n"
        )

        content = frontmatter + "\n" + body
        _atomic_write(features_dir / f"{fid}.md", content)
        created += 1

    if enrich_llm:
        print("  INFO: --enrich-llm 옵트인 감지.")
        print("        LLM 보강은 designer 에이전트 (opus-4-7) 위임 패턴을 사용합니다.")
        print("        이 기능은 세션 2 이후 구현 예정 — 현재는 결정론적 매핑만 실행됨.")

    return created, 0


def _guess_phase(fid: str) -> str:
    """feature ID 로부터 phase 를 추정 (F001~F003→1, F004→2, ...).

    Args:
        fid: Feature ID (예: F001)

    Returns:
        str: 추정 phase 번호
    """
    try:
        num = int(fid[1:])
        if num <= 3:
            return "1"
        elif num <= 6:
            return "2"
        elif num <= 9:
            return "3"
        elif num <= 12:
            return "4"
        return str((num - 1) // 3)
    except (ValueError, IndexError):
        return "unknown"


# ─── ingest: docs/adr/*.md → nodes/adrs/ ─────────────────────────────────────

def _ingest_adrs(vault_dir: Path, enrich_llm: bool = False) -> tuple[int, int]:
    """docs/adr/*.md 를 wiki/adrs/<ADR-NNN>.md 노드로 변환.

    ADR-007 결정 3: 본문의 FXXX 참조 추출 → related wikilink 엣지.

    Args:
        vault_dir: vault 루트 경로
        enrich_llm: LLM 보강 모드 플래그

    Returns:
        tuple: (생성된 노드 수, 건너뛴 수)
    """
    adrs_dir = vault_dir / "adrs"
    adrs_dir.mkdir(parents=True, exist_ok=True)

    if not _ADR_DIR.exists():
        print(f"  CONCERN: docs/adr/ 디렉토리 없음 ({_ADR_DIR})")
        print("           graceful — adrs 노드 생성 스킵")
        return 0, 0

    adr_files = sorted(_ADR_DIR.glob("ADR-*.md"))
    if not adr_files:
        print("  INFO: docs/adr/ 에 ADR-*.md 파일 없음 — 스킵")
        return 0, 0

    created = 0
    for adr_path in adr_files:
        # ADR-000-template.md 같은 템플릿은 스킵
        if "template" in adr_path.name.lower():
            continue

        raw = adr_path.read_text(encoding="utf-8")

        # ADR-NNN 추출
        m = re.match(r"ADR-(\d+)", adr_path.stem)
        if not m:
            continue
        adr_num = m.group(1)
        node_id = f"ADR-{adr_num}"

        # Feature 참조 추출 (헤더의 "Feature:" 라인 + 본문 FXXX 패턴)
        feature_refs: list[str] = []
        header_feat = re.search(r"Feature:\s*(F\d+)", raw)
        if header_feat:
            feature_refs.append(header_feat.group(1))
        body_feats = re.findall(r"\b(F\d{3,})\b", raw)
        for bf in body_feats:
            if bf not in feature_refs:
                feature_refs.append(bf)
        # 중복 제거 + 정렬
        feature_refs = sorted(set(feature_refs))

        # 제목 추출 (첫 번째 # 헤딩)
        title_m = re.search(r"^#\s+(.+)$", raw, re.MULTILINE)
        title = title_m.group(1).strip() if title_m else node_id

        # 상태 추출
        status_m = re.search(r"`(Proposed|Accepted|Deprecated|Superseded)`", raw)
        adr_status = status_m.group(1).lower() if status_m else "draft"

        # 본문 발췌: "결정" 섹션 + "결과" 섹션 (첫 500자)
        excerpt = _extract_adr_excerpt(raw)

        # frontmatter
        related_yaml = json.dumps(feature_refs)
        tags_yaml = json.dumps(["adr", f"adr-{adr_num}"])
        node_wiki_status = "active" if adr_status == "accepted" else "draft"
        frontmatter = (
            "---\n"
            f"type: adr\n"
            f"id: {node_id}\n"
            f"created: {_now_iso()}\n"
            f"source_ref: docs/adr/{adr_path.name}\n"
            f"tags: {tags_yaml}\n"
            f"related: {related_yaml}\n"
            f"status: {node_wiki_status}\n"
            "---\n"
        )

        # 역방향 wikilink (feature 참조)
        feat_links = ""
        if feature_refs:
            feat_links = "## 관련 Features\n\n"
            for ref in feature_refs:
                feat_links += f"- [[{ref}]]\n"
            feat_links += "\n"

        body = (
            f"# {node_id} — {title}\n\n"
            f"**원본**: `docs/adr/{adr_path.name}`\n\n"
            f"{feat_links}"
            f"## 발췌\n\n"
            f"{excerpt}\n"
        )

        content = frontmatter + "\n" + body
        _atomic_write(adrs_dir / f"{node_id}.md", content)
        created += 1

    if enrich_llm:
        print("  INFO: --enrich-llm 옵트인 감지 (ADRs). 세션 2 이후 구현 예정.")

    return created, 0


def _extract_adr_excerpt(raw: str) -> str:
    """ADR 본문에서 '결정' 또는 '## 결정' 섹션을 발췌 (최대 500자).

    Args:
        raw: ADR 원본 텍스트

    Returns:
        str: 발췌 텍스트
    """
    # 한국어 '결정' 또는 영어 'Decision' 섹션 찾기
    m = re.search(r"^##\s+(결정|Decision)\s*$", raw, re.MULTILINE)
    if m:
        excerpt = raw[m.start():][:500]
        return excerpt.strip()

    # 없으면 전체 본문 앞 500자
    return raw[:500].strip()


# ─── ingest: learnings.jsonl → nodes/learnings/ ───────────────────────────────

def _ingest_learnings(vault_dir: Path, enrich_llm: bool = False) -> tuple[int, int]:
    """learnings.jsonl 각 엔트리를 wiki/learnings/ 노드로 변환.

    ADR-007 결정 3: feature_id → related wikilink 엣지.

    Args:
        vault_dir: vault 루트 경로
        enrich_llm: LLM 보강 모드 플래그

    Returns:
        tuple: (생성된 노드 수, 건너뛴 수)
    """
    learnings_dir = vault_dir / "learnings"
    learnings_dir.mkdir(parents=True, exist_ok=True)

    if not _LEARNINGS.exists():
        print(f"  CONCERN: learnings.jsonl 없음 ({_LEARNINGS})")
        print("           graceful — learnings 노드 생성 스킵")
        return 0, 0

    lines = _LEARNINGS.read_text(encoding="utf-8").splitlines()
    entries = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue

    if not entries:
        print("  INFO: learnings.jsonl 비어있음 — 스킵")
        return 0, 0

    created = 0
    for entry in entries:
        ts = entry.get("ts", "unknown")
        category = entry.get("category", "general")
        note = entry.get("note", entry.get("text", ""))
        feature_id = entry.get("feature_id", "")
        tags_raw = entry.get("tags", [])

        # 슬러그: ts + category + note 앞 30자
        note_slug = _slug_from_text(note, 30) if note else "note"
        # ts 에서 날짜 부분만 추출 (YYYY-MM-DD)
        date_part = ts[:10] if len(ts) >= 10 else ts
        node_id = f"{date_part}-{category}-{note_slug}"

        # related: feature_id + note 에서 FXXX 추출
        related: list[str] = []
        if feature_id:
            related.append(feature_id)
        note_feats = re.findall(r"\b(F\d{3,})\b", note)
        for nf in note_feats:
            if nf not in related:
                related.append(nf)

        tags = [category] + (tags_raw if isinstance(tags_raw, list) else [])

        # frontmatter
        related_yaml = json.dumps(related)
        tags_yaml = json.dumps(tags)
        frontmatter = (
            "---\n"
            f"type: learning\n"
            f"id: {node_id}\n"
            f"created: {_now_iso()}\n"
            f"source_ref: .claude/state/learnings.jsonl\n"
            f"tags: {tags_yaml}\n"
            f"related: {related_yaml}\n"
            f"status: active\n"
            "---\n"
        )

        # 본문
        feat_links = ""
        if related:
            feat_links = "## 관련 Features\n\n"
            for ref in related:
                feat_links += f"- [[{ref}]]\n"
            feat_links += "\n"

        body = (
            f"# Learning: {category}\n\n"
            f"**기록 시각**: {ts}\n\n"
            f"{feat_links}"
            f"## 내용\n\n"
            f"{note}\n"
        )

        content = frontmatter + "\n" + body
        _atomic_write(learnings_dir / f"{node_id}.md", content)
        created += 1

    if enrich_llm:
        print("  INFO: --enrich-llm 옵트인 감지 (learnings). 세션 2 이후 구현 예정.")

    return created, 0


# ─── 서브커맨드 핸들러 ─────────────────────────────────────────────────────────

def cmd_ingest(args: argparse.Namespace) -> int:
    """ingest 서브커맨드 — 산출물을 vault 노드로 결정론적 변환.

    Args:
        args: argparse 파싱 결과

    Returns:
        int: exit code (0: 성공, 1: --strict + BLOCK)
    """
    vault_dir = Path(args.vault) if args.vault else _VAULT_DIR_DEFAULT
    source = getattr(args, "source", "all") or "all"
    enrich_llm = getattr(args, "enrich_llm", False)

    print(f"[wiki.py ingest] vault: {vault_dir}")
    print(f"  source: {source}")

    total_created = 0
    has_concern = False

    if source in ("features", "all"):
        print("\n[1/3] feature_list.json → features/")
        created, _ = _ingest_features(vault_dir, enrich_llm)
        total_created += created
        print(f"  {PASS_LABEL}: features 노드 {created}개 생성")

    if source in ("adrs", "all"):
        print("\n[2/3] docs/adr/*.md → adrs/")
        created, _ = _ingest_adrs(vault_dir, enrich_llm)
        total_created += created
        print(f"  {PASS_LABEL}: adrs 노드 {created}개 생성")

    if source in ("learnings", "all"):
        print("\n[3/3] learnings.jsonl → learnings/")
        created, _ = _ingest_learnings(vault_dir, enrich_llm)
        total_created += created
        print(f"  {PASS_LABEL}: learnings 노드 {created}개 생성")

    # index.md 갱신
    print("\n[index] wiki/index.md 갱신 중...")
    index_content = _build_index_content(vault_dir)
    _atomic_write(vault_dir / "index.md", index_content)
    print(f"  {PASS_LABEL}: index.md 갱신 완료")

    # log.md append
    _append_log(vault_dir, "ingest", f"{source} — {total_created}개 노드 생성")

    print(f"\n[완료] 총 {total_created}개 노드 생성/갱신 | vault: {vault_dir}")

    return 0


def cmd_query(args: argparse.Namespace) -> int:
    """query 서브커맨드 스텁 — 세션 2 에서 구현.

    Args:
        args: argparse 파싱 결과

    Returns:
        int: 0 (항상 graceful)
    """
    print("[wiki.py query] 세션 2 구현 예정.")
    print("  현재: stdlib grep fallback 스텁")
    query_text = getattr(args, "query_text", "")
    if query_text:
        print(f"  검색어: '{query_text}'")
        print("  vault 검색은 세션 2 (query + graceful degrade) 완성 후 사용 가능합니다.")
    return 0


def cmd_lint(args: argparse.Namespace) -> int:
    """lint 서브커맨드 스텁 — 세션 2 에서 구현.

    Args:
        args: argparse 파싱 결과

    Returns:
        int: 0 (항상 graceful)
    """
    print("[wiki.py lint] 세션 2 구현 예정.")
    print("  구현 예정 항목: WIKI-ORPHAN / WIKI-DEAD-LINK / WIKI-STALE / WIKI-FRONTMATTER")
    return 0


def cmd_graph(args: argparse.Namespace) -> int:
    """graph 서브커맨드 스텁 — 세션 2 에서 구현.

    Args:
        args: argparse 파싱 결과

    Returns:
        int: 0 (항상 graceful)
    """
    print("[wiki.py graph] 세션 2 구현 예정.")
    print("  구현 예정: mermaid / DOT 텍스트 그래프 출력")
    return 0


def cmd_self(args: argparse.Namespace) -> int:
    """self 서브커맨드 — 의존성·vault 정합 점검 (ADR-007 결정 5).

    외부 도구 설치 여부 + graceful degrade 상태를 점검한다.
    F009/F010/F011 self 마크다운 표 형식 일관.

    Args:
        args: argparse 파싱 결과

    Returns:
        int: 0 (hook-failure-tolerance — 항상 exit 0)
    """
    vault_dir = Path(args.vault) if args.vault else _VAULT_DIR_DEFAULT
    strict = getattr(args, "strict", False)

    print("[wiki.py self] wiki 변형 환경 점검")
    print("")

    results: list[tuple[str, str, str]] = []  # (항목, 상태, 메모)

    # --- Python stdlib ---
    results.append(("Python stdlib", PASS_LABEL, f"Python {sys.version.split()[0]}"))

    # --- vault 디렉토리 ---
    if vault_dir.exists():
        results.append(("vault 디렉토리", PASS_LABEL, str(vault_dir)))
    else:
        results.append(
            ("vault 디렉토리", CONCERN, f"없음 ({vault_dir}) — ingest 실행 시 자동 생성")
        )

    # --- vault 하위 디렉토리 ---
    node_dirs = ["features", "adrs", "learnings", "pages", "sources"]
    for nd in node_dirs:
        nd_path = vault_dir / nd
        if nd_path.exists():
            count = len(list(nd_path.glob("*.md")))
            results.append((f"vault/{nd}/", PASS_LABEL, f"{count}개 노드"))
        else:
            results.append((f"vault/{nd}/", CONCERN, "없음 — ingest 후 생성"))

    # --- 외부 도구 ---
    tools = _detect_external_tools()
    tool_notes = {
        "qmd": "BM25/vector 검색 — 미설치 시 stdlib grep fallback",
        "obsidian": ".obsidian/ 존재 (GUI는 수동 설치)",
        "marp": "슬라이드 변환 — 미설치 시 .md 직접 제공",
    }
    for tool, present in tools.items():
        note = tool_notes.get(tool, "")
        if present:
            results.append((f"외부 도구: {tool}", PASS_LABEL, f"설치됨 | {note}"))
        else:
            results.append(
                (f"외부 도구: {tool}", CONCERN, f"미설치 — stdlib fallback 활성 | {note}")
            )

    # --- source 파일 존재 ---
    sources_check = [
        (_FEATURE_LIST, "feature_list.json (ingest features 소스)"),
        (_ADR_DIR, "docs/adr/ (ingest adrs 소스)"),
        (_LEARNINGS, ".claude/state/learnings.jsonl (ingest learnings 소스)"),
    ]
    for src_path, label in sources_check:
        if src_path.exists():
            results.append((label, PASS_LABEL, "존재"))
        else:
            results.append(
                (label, CONCERN, f"없음 ({src_path}) — ingest 시 graceful 스킵")
            )

    # --- 출력 ---
    blocks = [r for r in results if r[1] == BLOCK]
    concerns = [r for r in results if r[1] == CONCERN]
    passes = [r for r in results if r[1] == PASS_LABEL]

    col_w = 40
    print(f"{'항목':<{col_w}} {'상태':<10} {'메모'}")
    print("-" * 90)
    for item, status, memo in results:
        print(f"{item:<{col_w}} {status:<10} {memo}")

    print("")
    print(f"요약: PASS {len(passes)} / CONCERN {len(concerns)} / BLOCK {len(blocks)}")

    if concerns:
        print("")
        print("외부 도구 설치 (선택): bash .claude/bin/wiki-setup.sh")
        print("  - 설치 안 해도 핵심 기능 (ingest/lint/graph + grep query) 은 동작.")

    if blocks:
        print("")
        print(f"BLOCK {len(blocks)}건 발견:")
        for item, _, memo in blocks:
            print(f"  [{BLOCK}] {item}: {memo}")
        if strict:
            return 1

    return 0


# ─── CLI 진입점 ────────────────────────────────────────────────────────────────

def _build_parser() -> argparse.ArgumentParser:
    """CLI 파서를 구성한다.

    Returns:
        argparse.ArgumentParser: 구성된 파서
    """
    parser = argparse.ArgumentParser(
        prog="wiki.py",
        description="LLM Wiki 지식 그래프 헬퍼 (F012 — claude.gstack.auto.design.wiki 변형 전용)",
    )
    parser.add_argument(
        "--vault",
        default=None,
        help="vault 위치 override (기본: <project-root>/wiki/)",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        default=False,
        help="BLOCK 1건이라도 있으면 exit 1",
    )
    parser.add_argument(
        "--format",
        choices=["human", "json"],
        default="human",
        help="출력 형식 (기본: human)",
    )

    sub = parser.add_subparsers(dest="command", help="서브커맨드")

    # ingest
    ingest_p = sub.add_parser("ingest", help="산출물 → vault 노드 변환")
    ingest_p.add_argument(
        "source",
        nargs="?",
        choices=["features", "adrs", "learnings", "all"],
        default="all",
        help="ingest 대상 (기본: all)",
    )
    ingest_p.add_argument(
        "--enrich-llm",
        dest="enrich_llm",
        action="store_true",
        default=False,
        help="LLM 보강 모드 옵트인 (세션 2 이후 실구현)",
    )

    # query (세션 2 구현 예정)
    query_p = sub.add_parser("query", help="vault 검색 (세션 2 구현 예정)")
    query_p.add_argument("query_text", nargs="?", help="검색어")
    query_p.add_argument("--limit", type=int, default=10, help="결과 수 제한")
    query_p.add_argument("--type", dest="node_type", help="노드 타입 필터")

    # lint (세션 2 구현 예정)
    lint_p = sub.add_parser("lint", help="vault 정합성 점검 (세션 2 구현 예정)")

    # graph (세션 2 구현 예정)
    graph_p = sub.add_parser("graph", help="vault 그래프 출력 (세션 2 구현 예정)")
    graph_p.add_argument(
        "--format",
        dest="graph_format",
        choices=["mermaid", "dot", "json"],
        default="mermaid",
        help="그래프 출력 형식",
    )
    graph_p.add_argument("--node-type", dest="node_type_filter", help="노드 타입 필터")

    # self
    self_p = sub.add_parser("self", help="의존성·환경 점검 (graceful degrade 상태)")

    return parser


def main() -> int:
    """CLI 메인 진입점.

    Returns:
        int: exit code
    """
    parser = _build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 0

    try:
        if args.command == "ingest":
            return cmd_ingest(args)
        elif args.command == "query":
            return cmd_query(args)
        elif args.command == "lint":
            return cmd_lint(args)
        elif args.command == "graph":
            return cmd_graph(args)
        elif args.command == "self":
            return cmd_self(args)
        else:
            parser.print_help()
            return 0
    except Exception as e:
        # hook-failure-tolerance: 예상치 못한 예외도 graceful
        print(f"[wiki.py] 예외 발생 — graceful degrade: {e}", file=sys.stderr)
        if getattr(args, "strict", False):
            return 1
        return 0


if __name__ == "__main__":
    sys.exit(main())
