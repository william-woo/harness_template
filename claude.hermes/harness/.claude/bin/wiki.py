#!/usr/bin/env python3
"""wiki.py — LLM Wiki 지식 그래프 헬퍼 (F012).

claude.gstack.auto.design.wiki 변형 전용. 프로젝트 산출물 (feature/ADR/learning)
을 Obsidian vault + [[wikilink]] 지식 그래프로 변환·관리한다.

서브커맨드:
  ingest [source]  — 산출물 → vault 노드 (결정론적 매핑 + 옵션 LLM 보강)
  query <검색어>    — vault 검색 (qmd BM25/vector / stdlib grep 자동 분기 — graceful degrade)
  lint             — vault 정합성 점검 (WIKI-ORPHAN / WIKI-DEAD-LINK / WIKI-STALE / WIKI-FRONTMATTER)
  graph            — DOT/mermaid/JSON 텍스트 그래프 출력 (외부 도구 0 — stdlib only)
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

    개행 문자를 먼저 제거하고 첫 줄만 사용하여 slug 에 \\n 이 들어가는 버그 방지.

    Args:
        text: 원본 텍스트
        max_len: 최대 slug 길이

    Returns:
        소문자, 알파벳/숫자/하이픈만 포함한 slug
    """
    # 개행 제거: 첫 줄만 사용 (slug 에 \n 문자 포함 방지 — F014 수정)
    text = text.split("\n")[0].replace("\r", " ").strip()
    slug = text.lower()
    slug = re.sub(r"[^a-z0-9가-힣\s-]", "", slug)
    slug = re.sub(r"\s+", "-", slug.strip())
    slug = re.sub(r"-+", "-", slug)
    return slug[:max_len].rstrip("-")


def _extract_created(content: str) -> Optional[str]:
    """기존 노드 파일에서 created 타임스탬프를 추출한다.

    frontmatter 의 'created: <값>' 라인을 파싱.
    없으면 None 반환 (호출자가 _now_iso() 로 fallback).

    Args:
        content: 노드 파일 전체 텍스트

    Returns:
        ISO 8601 타임스탬프 문자열 또는 None
    """
    m = re.search(r"^created:\s*(.+)$", content, re.MULTILINE)
    return m.group(1).strip() if m else None


def _content_equal_ignoring_timestamps(old: str, new: str) -> bool:
    """created/updated 줄을 제외한 본문이 동일한지 비교한다.

    완전 멱등성 구현: 같은 소스를 2회 ingest 해도 파일을 쓰지 않아 diff 0.

    Args:
        old: 기존 파일 내용
        new: 새로 생성된 내용

    Returns:
        True 면 내용이 동일 (파일 skip 가능), False 면 변경됨
    """
    _ts_pattern = re.compile(r"^(created|updated):\s*.+$", re.MULTILINE)
    return _ts_pattern.sub("", old) == _ts_pattern.sub("", new)


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


def _node_exists(node_id: str, vault_dir: Path) -> bool:
    """vault 에 해당 node_id 의 .md 파일이 존재하는지 확인한다.

    Args:
        node_id: 확인할 노드 ID (파일명 stem)
        vault_dir: vault 루트 경로

    Returns:
        bool: 노드가 vault 의 하위 디렉토리 어딘가에 존재하면 True
    """
    for sub in ("features", "adrs", "learnings", "pages", "sources"):
        if (vault_dir / sub / f"{node_id}.md").exists():
            return True
    return False


def _collect_known_node_ids(vault_dir: Path) -> set[str]:
    """vault 에 현재 존재하는 모든 노드 ID 집합을 반환한다.

    Args:
        vault_dir: vault 루트 경로

    Returns:
        set[str]: 노드 ID (파일명 stem) 집합
    """
    ids: set[str] = set()
    for sub in ("features", "adrs", "learnings", "pages", "sources"):
        node_dir = vault_dir / sub
        if node_dir.exists():
            for md_file in node_dir.glob("*.md"):
                ids.add(md_file.stem)
    return ids


def _detect_external_tools(vault_dir: Optional[Path] = None) -> dict[str, bool]:
    """외부 도구 설치 여부 자동 감지 (ADR-007 결정 5).

    Args:
        vault_dir: vault 경로 (Obsidian 감지용). None 이면 기본 경로 사용.

    Returns:
        dict: {tool: bool} — True 면 사용 가능, False 면 fallback
    """
    return {
        "qmd": shutil.which("qmd") is not None,
        "obsidian": _detect_obsidian_vault(vault_dir),
        "marp": shutil.which("marp") is not None,
    }


def _detect_obsidian_vault(vault_dir: Optional[Path] = None) -> bool:
    """vault 에 .obsidian/ 폴더가 있으면 Obsidian 설정 존재로 간주.

    Args:
        vault_dir: 확인할 vault 경로. None 이면 기본 경로 사용.

    Returns:
        bool: .obsidian/ 존재 여부
    """
    vault = vault_dir if vault_dir is not None else _VAULT_DIR_DEFAULT
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
    - deps/dependents 는 feature_list.json 내부 참조이므로 vault 존재 확인 불필요

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

    # feature_list.json 에 정의된 유효 ID 집합 (deps/dependents wikilink 안전 집합)
    valid_feature_ids: set[str] = {f.get("id", "") for f in features if f.get("id")}

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

        # related: dependencies (frontmatter — 메타데이터만, 끊겨도 OK)
        related_refs = deps[:]

        # 본문 wikilink (dependencies) — feature_list.json 내부 참조만
        dep_body = ""
        if deps:
            dep_body = "## Dependencies\n\n"
            for dep in deps:
                if dep in valid_feature_ids:
                    dep_body += f"- [[{dep}]]\n"
                else:
                    dep_body += f"- {dep}\n"
        else:
            dep_body = "## Dependencies\n\n_(없음)_\n"

        # dependents (역방향) — feature_list.json 내부 참조만
        dep_back = dependents.get(fid, [])
        dep_back_body = "## Dependents\n\n"
        if dep_back:
            for d in dep_back:
                if d in valid_feature_ids:
                    dep_back_body += f"- [[{d}]]\n"
                else:
                    dep_back_body += f"- {d}\n"
        else:
            dep_back_body += "_(없음)_\n"

        # AC 목록
        ac_body = "## Acceptance Criteria\n\n"
        if ac_list:
            for ac in ac_list:
                ac_body += f"- {ac}\n"
        else:
            ac_body += "_(없음)_\n"

        # frontmatter (멱등성 — F014: created 보존, updated 분리)
        node_path = features_dir / f"{fid}.md"
        now = _now_iso()
        existing_created = _extract_created(node_path.read_text(encoding="utf-8")) if node_path.exists() else None
        ts_created = existing_created or now

        related_yaml = json.dumps(related_refs) if related_refs else "[]"
        tags_yaml = json.dumps(tags)
        node_status = "active" if passes else "draft"
        frontmatter = (
            "---\n"
            f"type: feature\n"
            f"id: {fid}\n"
            f"created: {ts_created}\n"
            f"updated: {now}\n"
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

        new_content = frontmatter + "\n" + body
        # 내용 동일 시 파일을 쓰지 않아 완전 멱등 (timestamp 제외 비교)
        if node_path.exists() and _content_equal_ignoring_timestamps(node_path.read_text(encoding="utf-8"), new_content):
            continue
        _atomic_write(node_path, new_content)
        created += 1

    if enrich_llm:
        print("  INFO: --enrich-llm 옵트인 감지.")
        print("        LLM 보강은 designer 에이전트 (opus-4-7) 위임 패턴을 사용합니다.")
        print("        이 기능은 후속 phase 구현 예정 — 현재는 결정론적 매핑만 실행됨.")

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

def _ingest_adrs(
    vault_dir: Path,
    enrich_llm: bool = False,
    known_ids: Optional[set] = None,
) -> tuple[int, int]:
    """docs/adr/*.md 를 wiki/adrs/<ADR-NNN>.md 노드로 변환.

    ADR-007 결정 3: 본문의 FXXX 참조 추출 → related frontmatter 엣지.
    MUST 1 (dead-link 분리): related frontmatter 는 전체 참조 기록,
    본문 [[wikilink]] 는 known_ids 에 실제 존재하는 노드만 작성.

    Args:
        vault_dir: vault 루트 경로
        enrich_llm: LLM 보강 모드 플래그
        known_ids: vault 에 이미 존재하는 노드 ID 집합 (None 이면 vault 직접 조회)

    Returns:
        tuple: (생성된 노드 수, 건너뛴 수)
    """
    adrs_dir = vault_dir / "adrs"
    adrs_dir.mkdir(parents=True, exist_ok=True)

    if known_ids is None:
        known_ids = _collect_known_node_ids(vault_dir)

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

        # frontmatter: related 는 전체 참조 기록 (끊겨도 메타데이터로 유효)
        # 멱등성 — F014: created 보존, updated 분리
        node_path = adrs_dir / f"{node_id}.md"
        now = _now_iso()
        existing_created = _extract_created(node_path.read_text(encoding="utf-8")) if node_path.exists() else None
        ts_created = existing_created or now

        related_yaml = json.dumps(feature_refs)
        tags_yaml = json.dumps(["adr", f"adr-{adr_num}"])
        node_wiki_status = "active" if adr_status == "accepted" else "draft"
        frontmatter = (
            "---\n"
            f"type: adr\n"
            f"id: {node_id}\n"
            f"created: {ts_created}\n"
            f"updated: {now}\n"
            f"source_ref: docs/adr/{adr_path.name}\n"
            f"tags: {tags_yaml}\n"
            f"related: {related_yaml}\n"
            f"status: {node_wiki_status}\n"
            "---\n"
        )

        # 역방향 wikilink: vault 에 실제 존재하는 노드만 [[wikilink]],
        # 나머지는 평문 텍스트로 (dead-link 방지 — MUST 1)
        feat_links = ""
        if feature_refs:
            feat_links = "## 관련 Features\n\n"
            for ref in feature_refs:
                if ref in known_ids:
                    feat_links += f"- [[{ref}]]\n"
                else:
                    feat_links += f"- {ref}\n"
            feat_links += "\n"

        body = (
            f"# {node_id} — {title}\n\n"
            f"**원본**: `docs/adr/{adr_path.name}`\n\n"
            f"{feat_links}"
            f"## 발췌\n\n"
            f"{excerpt}\n"
        )

        new_content = frontmatter + "\n" + body
        # 내용 동일 시 파일을 쓰지 않아 완전 멱등 (timestamp 제외 비교)
        if node_path.exists() and _content_equal_ignoring_timestamps(node_path.read_text(encoding="utf-8"), new_content):
            continue
        _atomic_write(node_path, new_content)
        created += 1

    if enrich_llm:
        print("  INFO: --enrich-llm 옵트인 감지 (ADRs). 후속 phase 구현 예정.")

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

def _ingest_learnings(
    vault_dir: Path,
    enrich_llm: bool = False,
    known_ids: Optional[set] = None,
) -> tuple[int, int]:
    """learnings.jsonl 각 엔트리를 wiki/learnings/ 노드로 변환.

    ADR-007 결정 3: feature_id → related frontmatter 엣지.
    MUST 1 (dead-link 분리): related frontmatter 는 전체 참조 기록,
    본문 [[wikilink]] 는 known_ids 에 실제 존재하는 노드만 작성.

    Args:
        vault_dir: vault 루트 경로
        enrich_llm: LLM 보강 모드 플래그
        known_ids: vault 에 이미 존재하는 노드 ID 집합 (None 이면 vault 직접 조회)

    Returns:
        tuple: (생성된 노드 수, 건너뛴 수)
    """
    learnings_dir = vault_dir / "learnings"
    learnings_dir.mkdir(parents=True, exist_ok=True)

    if known_ids is None:
        known_ids = _collect_known_node_ids(vault_dir)

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

        # related: feature_id + note 에서 FXXX 추출 (frontmatter — 전체 참조 기록)
        related: list[str] = []
        if feature_id:
            related.append(feature_id)
        note_feats = re.findall(r"\b(F\d{3,})\b", note)
        for nf in note_feats:
            if nf not in related:
                related.append(nf)

        tags = [category] + (tags_raw if isinstance(tags_raw, list) else [])

        # frontmatter: related 는 전체 참조 기록 (끊겨도 메타데이터로 유효)
        # 멱등성 — F014: created 보존, updated 분리
        node_path = learnings_dir / f"{node_id}.md"
        now = _now_iso()
        existing_created = _extract_created(node_path.read_text(encoding="utf-8")) if node_path.exists() else None
        ts_created = existing_created or now

        related_yaml = json.dumps(related)
        tags_yaml = json.dumps(tags)
        frontmatter = (
            "---\n"
            f"type: learning\n"
            f"id: {node_id}\n"
            f"created: {ts_created}\n"
            f"updated: {now}\n"
            f"source_ref: .claude/state/learnings.jsonl\n"
            f"tags: {tags_yaml}\n"
            f"related: {related_yaml}\n"
            f"status: active\n"
            "---\n"
        )

        # 본문 wikilink: vault 에 실제 존재하는 노드만 [[wikilink]],
        # 나머지는 평문 텍스트로 (dead-link 방지 — MUST 1)
        feat_links = ""
        if related:
            feat_links = "## 관련 Features\n\n"
            for ref in related:
                if ref in known_ids:
                    feat_links += f"- [[{ref}]]\n"
                else:
                    feat_links += f"- {ref}\n"
            feat_links += "\n"

        body = (
            f"# Learning: {category}\n\n"
            f"**기록 시각**: {ts}\n\n"
            f"{feat_links}"
            f"## 내용\n\n"
            f"{note}\n"
        )

        new_content = frontmatter + "\n" + body
        # 내용 동일 시 파일을 쓰지 않아 완전 멱등 (timestamp 제외 비교)
        if node_path.exists() and _content_equal_ignoring_timestamps(node_path.read_text(encoding="utf-8"), new_content):
            continue
        _atomic_write(node_path, new_content)
        created += 1

    if enrich_llm:
        print("  INFO: --enrich-llm 옵트인 감지 (learnings). 후속 phase 구현 예정.")

    return created, 0


# ─── 서브커맨드 핸들러 ─────────────────────────────────────────────────────────

def _ingest_source_file(vault_dir: Path, source_file: Path) -> tuple[int, int]:
    """외부 .md 파일을 wiki/sources/<slug>.md 노드로 ingest.

    MUST 2: --source-file 옵션 구현.

    Args:
        vault_dir: vault 루트 경로
        source_file: 외부 .md 파일 경로

    Returns:
        tuple: (생성된 노드 수, 건너뛴 수)
    """
    sources_dir = vault_dir / "sources"
    sources_dir.mkdir(parents=True, exist_ok=True)

    if not source_file.exists():
        print(f"  CONCERN: 파일 없음 ({source_file})")
        return 0, 1

    raw = source_file.read_text(encoding="utf-8")

    # 제목 추출 (첫 번째 # 헤딩 또는 파일명)
    title_m = re.search(r"^#\s+(.+)$", raw, re.MULTILINE)
    title = title_m.group(1).strip() if title_m else source_file.stem

    slug = _slug_from_text(title, 40) or _slug_from_text(source_file.stem, 40)
    node_id = slug

    # 멱등성 — F014: created 보존, updated 분리
    node_path = sources_dir / f"{node_id}.md"
    now = _now_iso()
    existing_created = _extract_created(node_path.read_text(encoding="utf-8")) if node_path.exists() else None
    ts_created = existing_created or now

    tags_yaml = json.dumps(["source"])
    frontmatter = (
        "---\n"
        f"type: source\n"
        f"id: {node_id}\n"
        f"created: {ts_created}\n"
        f"updated: {now}\n"
        f"source_ref: {source_file}\n"
        f"tags: {tags_yaml}\n"
        f"related: []\n"
        f"status: active\n"
        "---\n"
    )

    body = (
        f"# {title}\n\n"
        f"> **원본 경로**: `{source_file}`\n\n"
        "---\n\n"
        f"{raw.strip()}\n"
    )

    new_content = frontmatter + "\n" + body
    # 내용 동일 시 파일을 쓰지 않아 완전 멱등 (timestamp 제외 비교)
    if node_path.exists() and _content_equal_ignoring_timestamps(node_path.read_text(encoding="utf-8"), new_content):
        print(f"  {INFO}: sources/{node_id}.md 변경 없음 (skip)")
        return 0, 1
    _atomic_write(node_path, new_content)
    print(f"  {PASS_LABEL}: sources/{node_id}.md 생성 (원본: {source_file})")
    return 1, 0


def cmd_ingest(args: argparse.Namespace) -> int:
    """ingest 서브커맨드 — 산출물을 vault 노드로 결정론적 변환.

    MUST 1 (dead-link 분리): 2-pass 처리.
    1st pass: features 노드 생성 (기준 노드 집합 확립)
    2nd pass: adrs/learnings 노드 생성 + known_ids 로 wikilink 필터링

    Args:
        args: argparse 파싱 결과

    Returns:
        int: exit code (0: 성공, 1: --strict + BLOCK)
    """
    vault_dir = Path(args.vault) if args.vault else _VAULT_DIR_DEFAULT
    source = getattr(args, "source", "all") or "all"
    enrich_llm = getattr(args, "enrich_llm", False)
    source_file_arg = getattr(args, "source_file", None)

    # --source-file 처리 (MUST 2)
    if source_file_arg:
        sf = Path(source_file_arg)
        print(f"[wiki.py ingest] --source-file 모드: {sf}")
        created, skipped = _ingest_source_file(vault_dir, sf)
        if created:
            print("\n[index] wiki/index.md 갱신 중...")
            _atomic_write(vault_dir / "index.md", _build_index_content(vault_dir))
            print(f"  {PASS_LABEL}: index.md 갱신 완료")
            _append_log(vault_dir, "ingest", f"source-file {sf.name} — {created}개 노드 생성")
            print(f"\n[완료] {created}개 노드 생성 | vault: {vault_dir}")
        return 0

    print(f"[wiki.py ingest] vault: {vault_dir}")
    print(f"  source: {source}")

    total_created = 0

    # ── 1st pass: features 노드 생성 ───────────────────────────────────────────
    # features 먼저 생성하여 adrs/learnings 의 wikilink 기준 집합 확립
    if source in ("features", "all"):
        print("\n[1/3] feature_list.json → features/")
        created, _ = _ingest_features(vault_dir, enrich_llm)
        total_created += created
        print(f"  {PASS_LABEL}: features 노드 {created}개 생성")

    # ── known_ids 수집 (1st pass 완료 후) ─────────────────────────────────────
    # adrs/learnings 의 [[wikilink]] 는 vault 에 실제 존재하는 노드만 (MUST 1)
    known_ids = _collect_known_node_ids(vault_dir)

    # ── 2nd pass: adrs/learnings 노드 생성 + wikilink 필터링 ──────────────────
    if source in ("adrs", "all"):
        print("\n[2/3] docs/adr/*.md → adrs/")
        created, _ = _ingest_adrs(vault_dir, enrich_llm, known_ids=known_ids)
        total_created += created
        print(f"  {PASS_LABEL}: adrs 노드 {created}개 생성")

    if source in ("learnings", "all"):
        print("\n[3/3] learnings.jsonl → learnings/")
        created, _ = _ingest_learnings(vault_dir, enrich_llm, known_ids=known_ids)
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


def _detect_tool(tool_name: str) -> bool:
    """외부 도구 설치 여부를 감지한다 (단일 도구 버전).

    Args:
        tool_name: 감지할 도구 이름 (예: "qmd", "marp")

    Returns:
        bool: 도구가 PATH 에 있으면 True
    """
    return shutil.which(tool_name) is not None


def _grep_vault(vault_dir: Path, query_text: str, limit: int, node_type: Optional[str]) -> list[dict]:
    """stdlib re 로 vault 노드를 검색한다 (qmd 없을 때 fallback).

    제목 매칭 우선, 본문 매칭 후순. 결과: 매칭 노드 목록.

    Args:
        vault_dir: vault 루트 경로
        query_text: 검색어
        limit: 최대 결과 수
        node_type: 노드 타입 필터 (features/adrs/learnings/pages/sources)

    Returns:
        list: [{node_id, path, match_type, context_line}] 형식 결과 목록
    """
    pattern = re.compile(re.escape(query_text), re.IGNORECASE)
    results: list[dict] = []

    # 검색 대상 디렉토리 결정
    search_dirs: list[Path] = []
    node_dirs = ["features", "adrs", "learnings", "pages", "sources"]
    if node_type and node_type in node_dirs:
        d = vault_dir / node_type
        if d.exists():
            search_dirs.append(d)
    else:
        for nd in node_dirs:
            d = vault_dir / nd
            if d.exists():
                search_dirs.append(d)

    seen_ids: set[str] = set()

    for search_dir in search_dirs:
        for md_file in sorted(search_dir.glob("*.md")):
            node_id = md_file.stem
            if node_id in seen_ids:
                continue
            try:
                content = md_file.read_text(encoding="utf-8")
            except OSError:
                continue

            lines = content.splitlines()

            # 제목 라인 (# 로 시작) 우선 매칭
            title_match = None
            for line in lines:
                if line.startswith("#") and pattern.search(line):
                    title_match = line.strip()
                    break

            if title_match:
                seen_ids.add(node_id)
                results.append({
                    "node_id": node_id,
                    "path": str(md_file.relative_to(vault_dir)),
                    "match_type": "title",
                    "context_line": title_match[:120],
                })
                continue

            # 본문 매칭 (frontmatter 포함)
            body_match = None
            for line in lines:
                if pattern.search(line):
                    body_match = line.strip()
                    break

            if body_match:
                seen_ids.add(node_id)
                results.append({
                    "node_id": node_id,
                    "path": str(md_file.relative_to(vault_dir)),
                    "match_type": "body",
                    "context_line": body_match[:120],
                })

            if len(results) >= limit * 3:
                break

    # 제목 매칭 우선 정렬 후 limit 적용
    results.sort(key=lambda r: (0 if r["match_type"] == "title" else 1, r["node_id"]))
    return results[:limit]


def cmd_query(args: argparse.Namespace) -> int:
    """query 서브커맨드 — vault 검색 (qmd 있으면 BM25, 없으면 grep fallback).

    ADR-007 결정 5: graceful degrade. qmd 미설치 시 stdlib grep 으로 fallback.
    결과: 매칭 노드 ID + 한 줄 컨텍스트 + wikilink 경로.

    Args:
        args: argparse 파싱 결과

    Returns:
        int: exit code (0: 성공)
    """
    vault_dir = Path(args.vault) if args.vault else _VAULT_DIR_DEFAULT
    query_text = getattr(args, "query_text", "") or ""
    limit = getattr(args, "limit", 10)
    node_type = getattr(args, "node_type", None)

    if not query_text:
        print("[wiki.py query] 검색어를 입력하세요.")
        print("  사용법: wiki.py query <검색어> [--limit N] [--type feature|adr|learning]")
        return 0

    if not vault_dir.exists():
        print(f"[wiki.py query] vault 없음: {vault_dir}")
        print("  먼저 wiki.py ingest 를 실행하세요.")
        return 0

    qmd_available = _detect_tool("qmd")

    print(f"[wiki.py query] 검색어: '{query_text}'")
    print(f"  vault: {vault_dir}")

    if qmd_available:
        # qmd BM25/vector 검색
        print(f"  모드: qmd (BM25/vector 검색)")
        try:
            result = subprocess.run(
                ["qmd", "search", query_text, "--path", str(vault_dir), "--limit", str(limit)],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                print(result.stdout)
                _append_log(vault_dir, "query", f"qmd | '{query_text}' | limit={limit}")
                return 0
            else:
                print(f"  WARN: qmd 실행 실패 ({result.returncode}) — grep fallback")
                print(f"  stderr: {result.stderr[:200]}")
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
            print(f"  WARN: qmd 실행 오류 ({e}) — grep fallback")

    # grep fallback (qmd 없거나 실패 시)
    if not qmd_available:
        print(f"  모드: stdlib grep (qmd 미설치 — fallback)")
        print(f"  더 나은 검색을 원하면: bash .claude/bin/wiki-setup.sh")
    else:
        print(f"  모드: stdlib grep (fallback)")

    results = _grep_vault(vault_dir, query_text, limit, node_type)

    if not results:
        print(f"\n  결과 없음: '{query_text}'")
        print("  vault 노드가 없거나 매칭되는 내용이 없습니다.")
        _append_log(vault_dir, "query", f"grep | '{query_text}' | 결과 없음")
        return 0

    print(f"\n  결과 {len(results)}건:")
    print(f"  {'노드 ID':<20} {'타입':<8} {'컨텍스트'}")
    print(f"  {'-'*20} {'-'*8} {'-'*60}")
    for r in results:
        node_id = r["node_id"]
        match_type = r["match_type"]
        context = r["context_line"]
        wiki_path = r["path"]
        print(f"  [[{node_id}]]{'':<{max(0, 18 - len(node_id))}} {match_type:<8} {context}")

    print(f"\n  wikilink: [[<노드ID>]] — vault 경로 wiki/<하위폴더>/<노드ID>.md")

    _append_log(vault_dir, "query", f"grep | '{query_text}' | {len(results)}건")
    return 0


# ─── lint: vault 정합성 점검 ───────────────────────────────────────────────────

def _parse_frontmatter(content: str) -> dict:
    """markdown 파일의 YAML frontmatter 를 파싱한다 (간단한 키=값 파서).

    외부 YAML 라이브러리 없이 stdlib 로 처리. 복잡한 YAML (중첩/멀티라인) 은
    부분 파싱 — 단순 key: value 만 추출.

    Args:
        content: markdown 파일 전체 텍스트

    Returns:
        dict: frontmatter 키-값. frontmatter 없으면 빈 dict.
    """
    if not content.startswith("---"):
        return {}
    end_idx = content.find("\n---\n", 4)
    if end_idx == -1:
        return {}
    fm_text = content[4:end_idx]
    result: dict = {}
    for line in fm_text.splitlines():
        m = re.match(r"^(\w[\w_-]*):\s*(.*)$", line.strip())
        if m:
            key, val = m.group(1), m.group(2).strip()
            # JSON 배열 파싱 시도
            if val.startswith("["):
                try:
                    result[key] = json.loads(val)
                except json.JSONDecodeError:
                    result[key] = val
            else:
                result[key] = val
    return result


def _extract_wikilinks(content: str) -> list[str]:
    """markdown 본문에서 [[wikilink]] 패턴을 모두 추출한다.

    Args:
        content: markdown 파일 전체 텍스트

    Returns:
        list: wikilink 대상 이름 목록 (중복 제거)
    """
    return list(set(re.findall(r"\[\[([^\]]+)\]\]", content)))


def _collect_all_nodes(vault_dir: Path) -> dict[str, Path]:
    """vault 전체 노드를 수집한다 (node_id → 파일 경로).

    Args:
        vault_dir: vault 루트 경로

    Returns:
        dict: {node_id: 파일 경로}
    """
    nodes: dict[str, Path] = {}
    node_dirs = ["features", "adrs", "learnings", "pages", "sources"]
    for nd in node_dirs:
        d = vault_dir / nd
        if not d.exists():
            continue
        for md_file in d.glob("*.md"):
            nodes[md_file.stem] = md_file
    return nodes


def cmd_lint(args: argparse.Namespace) -> int:
    """lint 서브커맨드 — vault 정합성 점검 (ADR-007 결정 7).

    F009 lint.py 와 독립 (wiki 변형 전용). 4 가지 검사:
    - WIKI-ORPHAN: 인바운드 wikilink 0 인 노드 (index.md 제외)
    - WIKI-DEAD-LINK: [[X]] 가 존재하지 않는 노드 가리킴
    - WIKI-STALE: source_ref 원본이 노드보다 최신 (ingest 재실행 필요)
    - WIKI-FRONTMATTER: 필수 frontmatter 필드 (type/id/created) 누락

    BLOCK: WIKI-DEAD-LINK (끊긴 그래프 — 명확한 오류)
    CONCERN: WIKI-ORPHAN / WIKI-STALE (권고)
    INFO: WIKI-FRONTMATTER (메타데이터 누락)

    Args:
        args: argparse 파싱 결과

    Returns:
        int: exit code (0: 성공, 1: --strict + BLOCK)
    """
    vault_dir = Path(args.vault) if args.vault else _VAULT_DIR_DEFAULT
    strict = getattr(args, "strict", False)

    print("[wiki.py lint] vault 정합성 점검")
    print(f"  vault: {vault_dir}")

    if not vault_dir.exists():
        print(f"  CONCERN: vault 없음 ({vault_dir}) — ingest 를 먼저 실행하세요.")
        return 0

    # 전체 노드 수집
    all_nodes = _collect_all_nodes(vault_dir)
    if not all_nodes:
        print("  INFO: vault 에 노드 없음 — 점검 스킵.")
        return 0

    print(f"  대상 노드: {len(all_nodes)}개")
    print("")

    issues: list[tuple[str, str, str]] = []  # (label, node_id, 설명)

    # ── 1. WIKI-FRONTMATTER: 필수 필드 누락 ────────────────────────────────────
    required_fields = {"type", "id", "created"}
    print("[1/4] WIKI-FRONTMATTER 점검...")
    for node_id, node_path in all_nodes.items():
        try:
            content = node_path.read_text(encoding="utf-8")
        except OSError:
            continue
        fm = _parse_frontmatter(content)
        missing = required_fields - set(fm.keys())
        if missing:
            issues.append((
                "WIKI-FRONTMATTER",
                node_id,
                f"필수 frontmatter 누락: {sorted(missing)}",
            ))

    # ── 2. 인바운드 링크 맵 구성 (WIKI-ORPHAN 준비) ────────────────────────────
    # node_id → 이 노드를 가리키는 다른 노드들
    inbound: dict[str, list[str]] = {nid: [] for nid in all_nodes}

    # wikilink 파싱 (모든 노드 본문 + index.md 제외)
    outbound_links: dict[str, list[str]] = {}  # node_id → [링크 대상 node_id]
    dead_links: list[tuple[str, str]] = []  # (from_node_id, dead_target)

    print("[2/4] WIKI-DEAD-LINK 점검...")
    for node_id, node_path in all_nodes.items():
        try:
            content = node_path.read_text(encoding="utf-8")
        except OSError:
            continue
        links = _extract_wikilinks(content)
        outbound_links[node_id] = links
        for target in links:
            if target in all_nodes:
                inbound[target].append(node_id)
            else:
                # index.md 의 [[X]] 는 카탈로그이므로 dead link 제외
                dead_links.append((node_id, target))

    for from_id, dead_target in dead_links:
        issues.append((
            "WIKI-DEAD-LINK",
            from_id,
            f"[[{dead_target}]] → 존재하지 않는 노드",
        ))

    # ── 3. WIKI-ORPHAN: 인바운드 0 노드 ────────────────────────────────────────
    print("[3/4] WIKI-ORPHAN 점검...")
    for node_id in all_nodes:
        # index.md 및 최상위 파일은 제외
        if inbound.get(node_id) is not None and len(inbound[node_id]) == 0:
            issues.append((
                "WIKI-ORPHAN",
                node_id,
                "인바운드 wikilink 0 — 다른 노드에서 참조되지 않음",
            ))

    # ── 4. WIKI-STALE: source_ref 원본이 노드보다 최신 ──────────────────────────
    print("[4/4] WIKI-STALE 점검...")
    for node_id, node_path in all_nodes.items():
        try:
            content = node_path.read_text(encoding="utf-8")
        except OSError:
            continue
        fm = _parse_frontmatter(content)
        source_ref = fm.get("source_ref", "")
        if not source_ref:
            continue

        # source_ref 경로 해석: feature_list.json#F001 → feature_list.json
        src_path_str = source_ref.split("#")[0]
        src_path = _PROJECT_ROOT / src_path_str
        if not src_path.exists():
            continue

        try:
            src_mtime = src_path.stat().st_mtime
            node_mtime = node_path.stat().st_mtime
            if src_mtime > node_mtime:
                issues.append((
                    "WIKI-STALE",
                    node_id,
                    f"원본 '{src_path_str}' 이 노드보다 최신 — ingest 재실행 권장",
                ))
        except OSError:
            continue

    # ── 결과 출력 ───────────────────────────────────────────────────────────────
    print("")

    blocks = [(lbl, nid, desc) for lbl, nid, desc in issues if lbl == "WIKI-DEAD-LINK"]
    concerns = [(lbl, nid, desc) for lbl, nid, desc in issues if lbl in ("WIKI-ORPHAN", "WIKI-STALE")]
    infos = [(lbl, nid, desc) for lbl, nid, desc in issues if lbl == "WIKI-FRONTMATTER"]
    pass_count = len(all_nodes) - len({nid for _, nid, _ in issues})

    if not issues:
        print(f"  {PASS_LABEL}: 정합성 이슈 없음 ({len(all_nodes)}개 노드 모두 통과)")
    else:
        for lbl, nid, desc in blocks:
            print(f"  [{BLOCK}] {lbl} | {nid}: {desc}")
        for lbl, nid, desc in concerns:
            print(f"  [{CONCERN}] {lbl} | {nid}: {desc}")
        for lbl, nid, desc in infos:
            print(f"  [{INFO}] {lbl} | {nid}: {desc}")

    print("")
    print(f"요약: PASS ~{pass_count} / BLOCK {len(blocks)} / CONCERN {len(concerns)} / INFO {len(infos)}")

    _append_log(
        vault_dir,
        "lint",
        f"BLOCK {len(blocks)} / CONCERN {len(concerns)} / INFO {len(infos)} ({len(all_nodes)}개 노드)",
    )

    if blocks and strict:
        return 1

    return 0


# ─── graph: vault 노드/엣지 → mermaid / DOT 텍스트 ───────────────────────────

def _build_node_label(node_id: str, node_path: Path) -> str:
    """노드 레이블을 생성한다 (mermaid/DOT 용 짧은 이름).

    Args:
        node_id: 노드 ID
        node_path: 노드 파일 경로

    Returns:
        str: 레이블 문자열
    """
    try:
        content = node_path.read_text(encoding="utf-8")
    except OSError:
        return node_id
    # 첫 번째 # 헤딩 추출
    m = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
    if m:
        title = m.group(1).strip()
        # 너무 길면 잘라냄
        if len(title) > 40:
            title = title[:37] + "..."
        return title
    return node_id


def _get_node_type_from_frontmatter(content: str, node_path: Path) -> str:
    """노드 타입을 frontmatter 또는 경로로부터 추출한다.

    Args:
        content: 노드 파일 전체 텍스트
        node_path: 노드 파일 경로

    Returns:
        str: 노드 타입 (feature/adr/learning/page/source)
    """
    fm = _parse_frontmatter(content)
    if "type" in fm:
        return str(fm["type"])
    # 경로 기반 추론
    parent = node_path.parent.name
    type_map = {
        "features": "feature",
        "adrs": "adr",
        "learnings": "learning",
        "pages": "page",
        "sources": "source",
    }
    return type_map.get(parent, "unknown")


def cmd_graph(args: argparse.Namespace) -> int:
    """graph 서브커맨드 — vault 노드/엣지를 mermaid 또는 DOT 텍스트로 출력.

    Obsidian graph view 의 텍스트 대체 (외부 도구 없이도 그래프 구조 확인).
    외부 도구 0 — 순수 stdlib (텍스트 출력).

    frontmatter `related` + 본문 `[[wikilink]]` 모두 엣지로 사용.
    --output 지정 시 mermaid 코드블록으로 파일 저장.

    Args:
        args: argparse 파싱 결과

    Returns:
        int: exit code (0: 성공)
    """
    vault_dir = Path(args.vault) if args.vault else _VAULT_DIR_DEFAULT
    graph_format = getattr(args, "graph_format", "mermaid")
    node_type_filter = getattr(args, "node_type_filter", None)
    output_path_str = getattr(args, "output", None)

    print(f"[wiki.py graph] vault: {vault_dir}")
    print(f"  format: {graph_format}")

    if not vault_dir.exists():
        print(f"  CONCERN: vault 없음 ({vault_dir}) — ingest 를 먼저 실행하세요.")
        return 0

    all_nodes = _collect_all_nodes(vault_dir)
    if not all_nodes:
        print("  INFO: vault 에 노드 없음 — 그래프 출력 스킵.")
        return 0

    # 노드 타입별 그룹핑 맵
    type_nodes: dict[str, list[str]] = {}
    node_labels: dict[str, str] = {}
    edges: list[tuple[str, str]] = []  # (from_id, to_id)

    for node_id, node_path in all_nodes.items():
        try:
            content = node_path.read_text(encoding="utf-8")
        except OSError:
            continue

        node_type = _get_node_type_from_frontmatter(content, node_path)

        # 타입 필터
        if node_type_filter and node_type != node_type_filter:
            continue

        type_nodes.setdefault(node_type, []).append(node_id)

        # 레이블 (mermaid 는 짧은 텍스트 사용)
        node_labels[node_id] = node_id  # 기본: ID 사용 (레이블 너무 길면 그래프 복잡)

        # 엣지: frontmatter related + 본문 wikilink
        fm = _parse_frontmatter(content)
        related = fm.get("related", [])
        if isinstance(related, list):
            for target in related:
                if target in all_nodes:
                    edges.append((node_id, target))

        wikilinks = _extract_wikilinks(content)
        for target in wikilinks:
            if target in all_nodes and (node_id, target) not in edges:
                edges.append((node_id, target))

    # 타입 필터 적용 시 필터된 노드만 포함
    if node_type_filter:
        filtered_ids = set(type_nodes.get(node_type_filter, []))
        edges = [(f, t) for f, t in edges if f in filtered_ids or t in filtered_ids]

    all_used_ids = {nid for ids in type_nodes.values() for nid in ids}

    # ── mermaid 출력 ────────────────────────────────────────────────────────────
    if graph_format == "mermaid":
        lines = ["graph LR"]

        # subgraph 로 타입 그룹핑
        type_order = ["feature", "adr", "learning", "page", "source", "unknown"]
        for node_type in type_order:
            ids = type_nodes.get(node_type, [])
            if not ids:
                continue
            # mermaid subgraph: 특수문자 이스케이프
            safe_type = node_type.replace("-", "_")
            lines.append(f'  subgraph {safe_type}["{node_type}"]')
            for nid in sorted(ids):
                safe_id = re.sub(r"[^A-Za-z0-9_-]", "_", nid)
                lines.append(f'    {safe_id}["{nid}"]')
            lines.append("  end")

        # 엣지
        for from_id, to_id in edges:
            safe_from = re.sub(r"[^A-Za-z0-9_-]", "_", from_id)
            safe_to = re.sub(r"[^A-Za-z0-9_-]", "_", to_id)
            lines.append(f"  {safe_from} --> {safe_to}")

        graph_text = "\n".join(lines)

        if output_path_str:
            out_path = Path(output_path_str)
            md_content = f"# Wiki 지식 그래프\n\n```mermaid\n{graph_text}\n```\n"
            _atomic_write(out_path, md_content)
            print(f"\n  저장: {out_path}")
            print(f"  노드 {sum(len(v) for v in type_nodes.values())}개 / 엣지 {len(edges)}개")
        else:
            print("")
            print(graph_text)
            print("")
            print(f"  노드 {sum(len(v) for v in type_nodes.values())}개 / 엣지 {len(edges)}개")
            print("  위 mermaid 코드를 https://mermaid.live 또는 Obsidian 에 붙여넣기 가능.")

    # ── DOT 출력 ────────────────────────────────────────────────────────────────
    elif graph_format == "dot":
        type_colors = {
            "feature": "#4A90D9",
            "adr": "#E8A838",
            "learning": "#7BC67E",
            "page": "#B39DDB",
            "source": "#EF9A9A",
            "unknown": "#CFD8DC",
        }

        dot_lines = ['digraph wiki {', '  rankdir=LR;', '  node [shape=box, style=filled];']

        for node_type in ["feature", "adr", "learning", "page", "source", "unknown"]:
            ids = type_nodes.get(node_type, [])
            if not ids:
                continue
            color = type_colors.get(node_type, "#CFD8DC")
            dot_lines.append(f'  // {node_type}')
            dot_lines.append(f'  {{ node [fillcolor="{color}"]')
            for nid in sorted(ids):
                safe_id = re.sub(r"[^A-Za-z0-9_]", "_", nid)
                dot_lines.append(f'    {safe_id} [label="{nid}"];')
            dot_lines.append("  }")

        dot_lines.append("")
        for from_id, to_id in edges:
            safe_from = re.sub(r"[^A-Za-z0-9_]", "_", from_id)
            safe_to = re.sub(r"[^A-Za-z0-9_]", "_", to_id)
            dot_lines.append(f"  {safe_from} -> {safe_to};")

        dot_lines.append("}")
        graph_text = "\n".join(dot_lines)

        if output_path_str:
            out_path = Path(output_path_str)
            _atomic_write(out_path, graph_text)
            print(f"\n  저장: {out_path}")
        else:
            print("")
            print(graph_text)
            print("")

        print(f"  노드 {sum(len(v) for v in type_nodes.values())}개 / 엣지 {len(edges)}개")
        print("  DOT → PNG: dot -Tpng output.dot -o graph.png (graphviz 필요)")

    # ── JSON 출력 ────────────────────────────────────────────────────────────────
    elif graph_format == "json":
        nodes_list = []
        for node_type, ids in type_nodes.items():
            for nid in ids:
                nodes_list.append({"id": nid, "type": node_type})
        edges_list = [{"from": f, "to": t} for f, t in edges]
        graph_data = {"nodes": nodes_list, "edges": edges_list}
        graph_text = json.dumps(graph_data, ensure_ascii=False, indent=2)

        if output_path_str:
            out_path = Path(output_path_str)
            _atomic_write(out_path, graph_text)
            print(f"\n  저장: {out_path}")
        else:
            print(graph_text)

        print(f"  노드 {len(nodes_list)}개 / 엣지 {len(edges_list)}개")

    _append_log(
        vault_dir,
        "graph",
        f"{graph_format} | 노드 {sum(len(v) for v in type_nodes.values())}개 / 엣지 {len(edges)}개",
    )
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

    # --- 외부 도구 --- (vault_dir 전달: --vault override 존중 — SHOULD 2)
    tools = _detect_external_tools(vault_dir)
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
    ingest_p.add_argument(
        "--source-file",
        dest="source_file",
        default=None,
        help="외부 .md 파일을 wiki/sources/ 노드로 ingest",
    )

    # query
    query_p = sub.add_parser("query", help="vault 검색 (qmd BM25 / stdlib grep fallback)")
    query_p.add_argument("query_text", nargs="?", help="검색어")
    query_p.add_argument("--limit", type=int, default=10, help="결과 수 제한")
    query_p.add_argument("--type", dest="node_type", help="노드 타입 필터")

    # lint
    lint_p = sub.add_parser("lint", help="vault 정합성 점검 (ORPHAN/DEAD-LINK/STALE/FRONTMATTER)")

    # graph
    graph_p = sub.add_parser("graph", help="vault 그래프 출력 (mermaid/DOT/JSON)")
    graph_p.add_argument(
        "--format",
        dest="graph_format",
        choices=["mermaid", "dot", "json"],
        default="mermaid",
        help="그래프 출력 형식",
    )
    graph_p.add_argument("--node-type", dest="node_type_filter", help="노드 타입 필터")
    graph_p.add_argument(
        "--output",
        dest="output",
        default=None,
        help="출력 파일 경로 (지정 시 파일 저장, 기본: stdout)",
    )

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
