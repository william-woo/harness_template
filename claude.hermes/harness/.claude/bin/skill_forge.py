#!/usr/bin/env python3
"""
skill_forge.py — 스킬 자동 생성 + self-improve + agentskills.io 표준 검증
(claude.hermes 변형 전용, d-hermes)

Hermes Agent 의 "복잡 작업 후 재사용 스킬 자동 생성 + 사용 중 self-improve" 패턴을
하네스에 이식한다. 스킬은 agentskills.io 개방 표준(Anthropic 원작)에 맞춰 생성/검증한다.

핵심 설계 (stdlib only):
- 스킬 '내용' 작성은 에이전트가 한다 (LLM). 헬퍼는 **구조·메타데이터·표준 적합성·
  사용 추적**의 결정론적 부분을 담당한다 (Karpathy: 추측 자동화 금지).
- self-improve = SKILL.md metadata 에 uses/version/last_improved 추적 → `nudge` 가
  "자주 쓰였는데 개선 안 된" 스킬을 짚어 에이전트에 개선을 유도 (Hermes 의 nudge 패턴).

사용법:
  python3 .claude/bin/skill_forge.py new <name> --description "<무엇+언제>"
  python3 .claude/bin/skill_forge.py from-learning <learning-key>
  python3 .claude/bin/skill_forge.py validate [<skill-dir>]   # 미지정 시 전체
  python3 .claude/bin/skill_forge.py record-use <name>        # 사용 1회 기록
  python3 .claude/bin/skill_forge.py nudge [--threshold N]    # 개선 후보 표시
  python3 .claude/bin/skill_forge.py list                     # 스킬 목록 + 사용/버전
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import date as _date
from pathlib import Path


def _project_root() -> Path:
    """하네스 루트 ($CLAUDE_PROJECT_DIR > 스크립트 위치 기준 parent×3)."""
    env = os.environ.get("CLAUDE_PROJECT_DIR")
    if env and Path(env).is_dir():
        return Path(env)
    return Path(__file__).resolve().parent.parent.parent


_ROOT = _project_root()
_SKILLS = _ROOT / ".claude" / "skills"

_NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


# ---------------------------------------------------------------------------
# frontmatter 파싱/직렬화 (의존성 없는 최소 YAML — 우리 스킬 포맷에 한정)
# ---------------------------------------------------------------------------

def _split_frontmatter(text: str) -> tuple[str, str]:
    """SKILL.md 를 (frontmatter, body) 로 분리한다. 없으면 ('', text)."""
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", text, re.DOTALL)
    if not m:
        return "", text
    return m.group(1), m.group(2)


def _parse_frontmatter(fm: str) -> dict:
    """
    최소 YAML 파서: top-level `key: value`, `metadata:` 1단계 맵,
    그리고 `key: |`/`key: >` **블록 스칼라**(멀티라인 문자열)를 지원한다.
    (우리 SKILL.md 가 쓰는 부분집합만 — 외부 의존성 회피.)
    """
    data: dict = {}
    cur_map: str | None = None       # metadata 맵 수집 중인 키
    block_key: str | None = None     # 블록 스칼라 수집 중인 키
    block_lines: list[str] = []

    def _flush_block() -> None:
        nonlocal block_key, block_lines
        if block_key is not None:
            data[block_key] = " ".join(s.strip() for s in block_lines if s.strip())
            block_key, block_lines = None, []

    for line in fm.splitlines():
        # 블록 스칼라 수집: 들여쓰기된(또는 빈) 줄은 본문으로
        if block_key is not None:
            if line.strip() == "" or re.match(r"^\s+", line):
                block_lines.append(line)
                continue
            _flush_block()
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        # metadata 맵 자식
        if re.match(r"^\s+\S", line) and cur_map:
            k, sep, v = line.strip().partition(":")
            if sep:
                data[cur_map][k.strip()] = v.strip().strip('"')
            continue
        key, sep, val = line.partition(":")
        if not sep:
            continue
        key, val = key.strip(), val.strip()
        cur_map = None
        if val in ("|", ">", "|-", ">-"):
            block_key, block_lines = key, []           # 블록 스칼라 시작
        elif val == "":
            data[key] = {} if key == "metadata" else ""
            cur_map = key if key == "metadata" else None
        else:
            data[key] = val.strip('"')
    _flush_block()
    return data


# ---------------------------------------------------------------------------
# agentskills.io 표준 검증 (skills-ref validate 동등 — 핵심 규칙)
# ---------------------------------------------------------------------------

def _validate_skill(skill_dir: Path) -> list[str]:
    """
    스킬 디렉토리를 agentskills.io 표준으로 검증하고 위반 목록을 반환한다 (빈 = 통과).

    검증 규칙 (spec):
      - SKILL.md 존재
      - name: 1-64, [a-z0-9-], 선·후행/연속 하이픈 금지, **부모 디렉토리명과 일치**
      - description: 1-1024, 비어있지 않음
      - compatibility: 1-500 (선택)
    """
    errs: list[str] = []
    md = skill_dir / "SKILL.md"
    if not md.exists():
        return [f"{skill_dir.name}: SKILL.md 없음"]
    fm, _ = _split_frontmatter(md.read_text(encoding="utf-8"))
    if not fm:
        return [f"{skill_dir.name}: YAML frontmatter 없음"]
    data = _parse_frontmatter(fm)

    name = data.get("name", "")
    if not name:
        errs.append(f"{skill_dir.name}: name 필수 누락")
    else:
        if len(name) > 64:
            errs.append(f"{skill_dir.name}: name 64자 초과")
        if not _NAME_RE.match(name):
            errs.append(f"{skill_dir.name}: name 형식 위반 (소문자·숫자·하이픈, 선·후행/연속 하이픈 금지): '{name}'")
        if name != skill_dir.name:
            errs.append(f"{skill_dir.name}: name('{name}') 이 디렉토리명과 불일치")

    desc = data.get("description", "")
    if not desc or not str(desc).strip():
        errs.append(f"{skill_dir.name}: description 필수 누락/빈값")
    elif len(str(desc)) > 1024:
        errs.append(f"{skill_dir.name}: description 1024자 초과")

    compat = data.get("compatibility", "")
    if compat and len(str(compat)) > 500:
        errs.append(f"{skill_dir.name}: compatibility 500자 초과")
    return errs


def cmd_validate(args) -> int:
    """스킬 1개 또는 전체를 agentskills.io 표준으로 검증한다."""
    if args.path:
        targets = [Path(args.path) if Path(args.path).is_absolute()
                   else _ROOT / args.path]
    else:
        targets = [d for d in sorted(_SKILLS.iterdir()) if d.is_dir()] \
            if _SKILLS.is_dir() else []
    if not targets:
        print("[skill-forge] 검증 대상 스킬 없음")
        return 0
    total_errs: list[str] = []
    for d in targets:
        errs = _validate_skill(d)
        mark = "✅" if not errs else "❌"
        print(f"  {mark} {d.name}")
        for e in errs:
            print(f"      - {e}")
        total_errs += errs
    print(f"\n[skill-forge] {len(targets)}개 검증 / 위반 {len(total_errs)}건 "
          f"({'PASS' if not total_errs else 'FAIL'})")
    return 1 if total_errs else 0


# ---------------------------------------------------------------------------
# 스킬 생성 (scaffold) — agentskills.io 구조
# ---------------------------------------------------------------------------

_SKILL_TEMPLATE = """---
name: {name}
description: {description}
metadata:
  author: hermes-skill-forge
  version: "0.1"
  uses: "0"
  last_improved: "{date}"
---

# {title}

> agentskills.io 표준 스킬. 에이전트가 활성화 시 이 본문을 컨텍스트로 읽는다.
> (progressive disclosure: 평소엔 name+description 만, 활성화 시 전체 로드)

## 언제 사용하나
{description}

## 단계별 지침
1. (에이전트가 작성) — 이 스킬이 수행하는 절차를 단계로 기술
2. ...

## 입력/출력 예시
- 입력: ...
- 출력: ...

## 엣지 케이스
- ...

<!-- self-improve: 이 스킬이 자주 쓰이면 `skill_forge.py nudge` 가 개선을 유도한다.
     개선 시 metadata.version 증가 + last_improved 갱신 + record-use 카운터 참고. -->
"""


def cmd_new(args) -> int:
    """agentskills.io 표준에 맞는 새 스킬 폴더를 scaffold 한다."""
    name = args.name.strip()
    if not _NAME_RE.match(name) or len(name) > 64:
        print(f"[skill-forge] ❌ 잘못된 name '{name}' — 소문자·숫자·하이픈만, "
              "선·후행/연속 하이픈 금지, 64자 이하")
        return 1
    skill_dir = _SKILLS / name
    if skill_dir.exists() and not args.force:
        print(f"[skill-forge] 이미 존재: {skill_dir.relative_to(_ROOT)} (--force 로 덮어쓰기)")
        return 1
    desc = (args.description or
            f"{name} 작업을 수행하는 스킬. {name} 관련 요청 시 사용한다.").strip()
    if len(desc) > 1024:
        desc = desc[:1021] + "..."
    (skill_dir / "scripts").mkdir(parents=True, exist_ok=True)
    (skill_dir / "references").mkdir(parents=True, exist_ok=True)
    title = name.replace("-", " ").title()
    # last_improved 기본값은 실행 시점 날짜 (Reviewer SHOULD — 고정값이면 개선 이력 추적 불가)
    content = _SKILL_TEMPLATE.format(
        name=name, description=desc, title=title,
        date=args.date or _date.today().isoformat())
    (skill_dir / "SKILL.md").write_text(content, encoding="utf-8")
    print(f"[skill-forge] 생성: {(skill_dir / 'SKILL.md').relative_to(_ROOT)}")
    print("  → 에이전트가 본문(단계별 지침/예시/엣지케이스)을 채우세요.")
    errs = _validate_skill(skill_dir)
    print(f"  표준 검증: {'PASS' if not errs else 'FAIL — ' + '; '.join(errs)}")
    return 0


def cmd_from_learning(args) -> int:
    """learnings.jsonl 의 항목(key)으로부터 스킬 초안을 생성한다."""
    jl = _ROOT / ".claude" / "state" / "learnings.jsonl"
    if not jl.exists():
        print(f"[skill-forge] learnings.jsonl 없음: {jl.relative_to(_ROOT)}")
        return 1
    found = None
    for line in jl.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if obj.get("key") == args.key:
            found = obj
    if not found:
        print(f"[skill-forge] 학습 키 '{args.key}' 없음")
        return 1
    # 학습 key(보통 kebab-ish) → 스킬 name 정규화
    name = re.sub(r"[^a-z0-9-]", "-", args.key.lower())
    name = re.sub(r"-+", "-", name).strip("-")[:64]
    desc = (found.get("insight", "")[:1024]).strip() or f"{name} 학습 기반 스킬"
    args.name, args.description = name, desc
    print(f"[skill-forge] 학습 '{args.key}' → 스킬 '{name}' 초안 생성")
    return cmd_new(args)


# ---------------------------------------------------------------------------
# self-improve 추적 (uses 카운터 + nudge)
# ---------------------------------------------------------------------------

def _bump_metadata(md: Path, key: str, value: str) -> None:
    """SKILL.md frontmatter 의 metadata.<key> 값을 교체/추가한다 (라인 단위 안전 편집)."""
    text = md.read_text(encoding="utf-8")
    fm, body = _split_frontmatter(text)
    if not fm:
        # 경계 방어 (Reviewer MUST): frontmatter 없는 파일은 건드리지 않는다
        # (빈 frontmatter 삽입으로 파일을 오염시키지 않도록 early-return).
        print(f"[skill-forge] 경고: {md.name} — frontmatter 없음, {key} 갱신 건너뜀")
        return
    lines = fm.splitlines()
    out, in_meta, replaced = [], False, False
    for ln in lines:
        if re.match(r"^metadata\s*:", ln):
            in_meta = True
            out.append(ln)
            continue
        if in_meta and re.match(rf"^\s+{re.escape(key)}\s*:", ln):
            indent = ln[:len(ln) - len(ln.lstrip())]
            out.append(f'{indent}{key}: "{value}"')
            replaced = True
            continue
        if in_meta and not re.match(r"^\s+\S", ln):
            if not replaced:
                out.append(f'  {key}: "{value}"')
                replaced = True
            in_meta = False
        out.append(ln)
    if in_meta and not replaced:
        out.append(f'  {key}: "{value}"')
    md.write_text(f"---\n" + "\n".join(out) + "\n---\n" + body, encoding="utf-8")


def cmd_record_use(args) -> int:
    """스킬 사용 1회를 metadata.uses 에 기록한다 (self-improve 추적)."""
    md = _SKILLS / args.name / "SKILL.md"
    if not md.exists():
        print(f"[skill-forge] 스킬 없음: {args.name}")
        return 1
    fm, _ = _split_frontmatter(md.read_text(encoding="utf-8"))
    data = _parse_frontmatter(fm)
    uses = int(str(data.get("metadata", {}).get("uses", "0")) or "0") + 1
    _bump_metadata(md, "uses", str(uses))
    print(f"[skill-forge] {args.name} 사용 기록 → uses={uses}")
    return 0


def cmd_nudge(args) -> int:
    """uses 가 임계치 이상인 스킬을 'self-improve 후보'로 표시한다 (Hermes nudge)."""
    if not _SKILLS.is_dir():
        print("[skill-forge] 스킬 디렉토리 없음")
        return 0
    flagged = []
    for d in sorted(_SKILLS.iterdir()):
        if not d.is_dir() or not (d / "SKILL.md").exists():
            continue
        fm, _ = _split_frontmatter((d / "SKILL.md").read_text(encoding="utf-8"))
        meta = _parse_frontmatter(fm).get("metadata", {})
        uses = int(str(meta.get("uses", "0")) or "0")
        if uses >= args.threshold:
            flagged.append((d.name, uses, meta.get("version", "?"),
                            meta.get("last_improved", "?")))
    if not flagged:
        print(f"[skill-forge] 개선 후보 없음 (임계치 uses>={args.threshold})")
        return 0
    print(f"[skill-forge] self-improve 후보 (uses>={args.threshold}):\n")
    for name, uses, ver, last in sorted(flagged, key=lambda x: -x[1]):
        print(f"  ● {name}: uses={uses} v{ver} (last_improved={last})")
    print("\n  → 에이전트가 본문을 개선 후 metadata.version 증가 + last_improved 갱신 권장.")
    return 0


def cmd_list(args) -> int:
    """스킬 목록 + 사용 횟수/버전을 표시한다."""
    if not _SKILLS.is_dir():
        print("[skill-forge] 스킬 디렉토리 없음")
        return 0
    print("[skill-forge] 스킬 목록:")
    for d in sorted(_SKILLS.iterdir()):
        if not d.is_dir() or not (d / "SKILL.md").exists():
            continue
        fm, _ = _split_frontmatter((d / "SKILL.md").read_text(encoding="utf-8"))
        data = _parse_frontmatter(fm)
        meta = data.get("metadata", {})
        print(f"  ● {d.name:22} uses={meta.get('uses','0'):>3} "
              f"v{meta.get('version','?'):4} — {str(data.get('description',''))[:60]}")
    return 0


def main() -> None:
    """CLI 진입점."""
    parser = argparse.ArgumentParser(description="스킬 자동생성+self-improve+agentskills.io 검증")
    sub = parser.add_subparsers(dest="command")

    p_new = sub.add_parser("new", help="새 스킬 scaffold (agentskills.io 표준)")
    p_new.add_argument("name", help="스킬 이름 (소문자·하이픈, 디렉토리명=name)")
    p_new.add_argument("--description", help="무엇+언제 (1-1024자)")
    p_new.add_argument("--force", action="store_true", help="기존 덮어쓰기")
    p_new.add_argument("--date", help="last_improved 날짜 (기본 2026-01-01)")

    p_fl = sub.add_parser("from-learning", help="learnings.jsonl 항목으로 스킬 초안 생성")
    p_fl.add_argument("key", help="learnings.jsonl 의 key")
    p_fl.add_argument("--force", action="store_true")
    p_fl.add_argument("--date")

    p_val = sub.add_parser("validate", help="agentskills.io 표준 검증 (미지정 시 전체)")
    p_val.add_argument("path", nargs="?", help="스킬 디렉토리 (생략 시 전체)")

    p_use = sub.add_parser("record-use", help="스킬 사용 1회 기록 (self-improve 추적)")
    p_use.add_argument("name")

    p_nudge = sub.add_parser("nudge", help="self-improve 후보 표시")
    p_nudge.add_argument("--threshold", type=int, default=5, help="uses 임계치 (기본 5)")

    sub.add_parser("list", help="스킬 목록 + 사용/버전")

    args = parser.parse_args()
    handlers = {
        "new": cmd_new, "from-learning": cmd_from_learning, "validate": cmd_validate,
        "record-use": cmd_record_use, "nudge": cmd_nudge, "list": cmd_list,
    }
    if args.command is None:
        parser.print_help()
        sys.exit(0)
    sys.exit(handlers[args.command](args))


if __name__ == "__main__":
    main()
