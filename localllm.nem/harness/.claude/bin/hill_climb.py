#!/usr/bin/env python3
"""
hill_climb.py — Loop 4 (Hill-Climbing Loop) 정형화 (claude.loope 전용)

LangChain "loop engineering" 의 **Loop 4** = "production 트레이스 → 분석 → harness 개선".
retro/learn/brain 이 이미 부분 구현하지만, ① 루프가 자동으로 안 닫히고 ② F020 의 verify-loop
트레이스(Loop 2 산출)가 미활용이었다. 이 헬퍼가 **3개 트레이스 소스를 결정론으로 집계**하고
**구체 개선 후보(candidate)** 를 플래그해, 분석 에이전트가 harness-config 개선안을 내도록 한다.

설계 (Karpathy · 하네스 패턴): **헬퍼 = 결정론 집계·신호 추출** / **에이전트 = 개선안 판단**.
이 스크립트는 신호와 후보만 낸다 — 실제 config 변경 제안·반영은 분석 에이전트+사람 몫(루프 닫힘).

트레이스 소스:
  ① .claude/state/verify-loop/*.json  — Loop 2 판정/재시도/에스컬레이션 (F020)
  ② .claude/state/analytics.jsonl      — handoff/session_end/review_iteration 이벤트
  ③ .claude/state/learnings.jsonl      — pitfall/pattern/architecture (있으면)

사용법:
  python3 .claude/bin/hill_climb.py analyze            # 신호 리포트 + 개선 후보
  python3 .claude/bin/hill_climb.py analyze --json     # 기계 판독용 JSON
  python3 .claude/bin/hill_climb.py self               # 소스 감지
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path


def _project_root() -> Path:
    """하네스 루트 ($CLAUDE_PROJECT_DIR > 스크립트 위치 기준 parent×3)."""
    env = os.environ.get("CLAUDE_PROJECT_DIR")
    if env and Path(env).is_dir():
        return Path(env)
    return Path(__file__).resolve().parent.parent.parent


_ROOT = _project_root()
_STATE = _ROOT / ".claude" / "state"
_VERIFY_LOOP = _STATE / "verify-loop"
_ANALYTICS = _STATE / "analytics.jsonl"
_LEARNINGS = _STATE / "learnings.jsonl"

# 개선 후보 판정 임계 (heuristic — 결정론)
_HIGH_FILES_CHANGED = 30    # handoff 1건당 변경 파일 이 이상이면 Surgical 위반 후보
_HIGH_REVISION_RATE = 0.5   # grader 판정 중 revision 비율 이 이상이면 rubric 재점검 후보


def _read_jsonl(path: Path) -> list[dict]:
    """JSONL 을 관대하게 파싱한다 — **dict 인 줄만** 돌려준다.

    파싱만 방어하고 소비 지점은 dict 를 가정하면, `42` 나 `[1,2]` 한 줄이
    `l.get(...)` 에서 AttributeError 로 집계 전체를 죽인다. 방어와 소비가 다른
    주소에 있으면 반드시 어긋난다 — 여기서 타입까지 걸러 한 주소로 모은다.
    `analytics.jsonl` 은 handoff 가 `>>` 로 append 하는 파일이라 실제로 이런 줄이 생긴다.
    """
    rows: list[dict] = []
    if not path.exists():
        return rows
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return rows
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _collect_verify_loops() -> list[dict]:
    """verify-loop 상태 파일을 읽는다 — **형태가 맞는 것만** (Loop 2 트레이스).

    `attempts` 가 list 가 아니거나 최상위가 dict 가 아니면 소비 지점에서 터진다.
    깨진 소스는 조용히 빠지지 않고 `skipped` 로 셈해 `self`/`analyze` 에 노출한다.
    """
    if not _VERIFY_LOOP.exists():
        return []
    loops: list[dict] = []
    skipped = 0
    for p in sorted(_VERIFY_LOOP.glob("*.json")):
        try:
            loop = json.loads(p.read_text(encoding="utf-8", errors="replace"))
        except (json.JSONDecodeError, OSError, ValueError):
            skipped += 1
            continue
        if not isinstance(loop, dict) or not isinstance(loop.get("attempts"), list):
            skipped += 1
            continue
        loop["attempts"] = [a for a in loop["attempts"] if isinstance(a, dict)]
        loops.append(loop)
    if skipped:
        print(f"[hill-climb] ⚠️ 읽을 수 없는 루프 파일 {skipped}건 건너뜀", file=sys.stderr)
    return loops


def _as_int(value: object) -> int | None:
    """정수로 쓸 수 있으면 정수를, 아니면 None. `bool` 은 제외한다.

    `isinstance(x, int)` 만 쓰면 `True` 가 통과해 `files_changed: true` 가
    평균 1.0 으로 집계된다 (실측).
    """
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _signals() -> dict:
    """3개 트레이스 소스를 집계해 Loop 4 신호를 낸다 (결정론)."""
    loops = _collect_verify_loops()
    analytics = _read_jsonl(_ANALYTICS)
    learnings = _read_jsonl(_LEARNINGS)

    # ── verify-loop (Loop 2) 신호 ──
    status_counts = Counter(str(l.get("status", "?")) for l in loops)
    revisions = [n for n in (_as_int(l.get("revision_count", 0)) for l in loops) if n is not None]
    escalated = [str(l.get("feature", "?")) for l in loops if l.get("status") == "escalated"]
    grader_verdicts: Counter = Counter()   # (grader, verdict) → n
    for l in loops:
        for a in l.get("attempts", []):
            grader_verdicts[(str(a.get("grader", "?")), str(a.get("verdict", "?")))] += 1
    # grader 별 revision 비율
    grader_rev_rate = {}
    graders = {g for (g, _v) in grader_verdicts}
    for g in graders:
        total = sum(n for (gg, _v), n in grader_verdicts.items() if gg == g)
        rev = sum(n for (gg, v), n in grader_verdicts.items() if gg == g and v == "revision")
        grader_rev_rate[g] = (rev / total) if total else 0.0

    # ── analytics 신호 ──
    ev_counts = Counter(str(e.get("event", "?")) for e in analytics)
    handoffs = [e for e in analytics if e.get("event") == "handoff"]
    features_touched = Counter(str(e.get("feature_id", "?")) for e in handoffs if e.get("feature_id"))
    files_changed = [n for n in (_as_int(e.get("files_changed")) for e in handoffs) if n is not None]
    big_handoffs = [(str(e.get("feature_id", "?")), _as_int(e.get("files_changed")))
                    for e in handoffs
                    if (_as_int(e.get("files_changed")) or 0) >= _HIGH_FILES_CHANGED]

    # ── learnings 신호 ──
    learn_by_type = Counter(str(l.get("type", "?")) for l in learnings)

    return {
        "verify_loop": {
            "total": len(loops),
            "status": dict(status_counts),
            "avg_revisions": round(sum(revisions) / len(revisions), 2) if revisions else 0,
            "escalated_features": escalated,
            "grader_revision_rate": {g: round(r, 2) for g, r in sorted(grader_rev_rate.items())},
        },
        "analytics": {
            "events": dict(ev_counts),
            "handoffs": len(handoffs),
            "features_touched": dict(features_touched.most_common(8)),
            "avg_files_changed": round(sum(files_changed) / len(files_changed), 1) if files_changed else 0,
            "big_handoffs": big_handoffs,
        },
        "learnings": {"total": len(learnings), "by_type": dict(learn_by_type)},
    }


def _candidates(sig: dict) -> list[str]:
    """신호에서 결정론 heuristic 으로 harness 개선 후보를 플래그한다."""
    out = []
    vl = sig["verify_loop"]
    if vl["escalated_features"]:
        out.append(f"에스컬레이션 feature {vl['escalated_features']} → Architect 선행 검토/Feature 분해 후보")
    for g, rate in vl["grader_revision_rate"].items():
        if rate >= _HIGH_REVISION_RATE:
            out.append(f"grader '{g}' revision율 {rate:.0%} (≥{_HIGH_REVISION_RATE:.0%}) → 해당 rubric 항목·Developer 가이드 재점검 후보")
    for feat, n in sig["analytics"]["big_handoffs"]:
        out.append(f"{feat} handoff 변경파일 {n}건 (≥{_HIGH_FILES_CHANGED}) → Surgical Changes 위반 후보, 리뷰 강화")
    reappear = [f for f, n in sig["analytics"]["features_touched"].items() if n >= 3]
    if reappear:
        out.append(f"handoff 3회+ feature {reappear} → 반복 재작업, learn(pitfall) 등록 + 설계 재검토 후보")
    if sig["learnings"]["total"] == 0 and vl["total"] > 0:
        out.append("검증 루프는 도는데 learnings 0건 → /project:learn add 로 pitfall 축적 습관 후보")
    if not out:
        out.append("(임계 초과 신호 없음 — 현재 harness config 유지 가능)")
    return out


def cmd_analyze(args) -> int:
    """3 트레이스 소스를 집계해 신호 + 개선 후보를 출력한다."""
    sig = _signals()
    cands = _candidates(sig)
    if args.json:
        print(json.dumps({"signals": sig, "candidates": cands}, ensure_ascii=False, indent=2))
        return 0

    vl, an, le = sig["verify_loop"], sig["analytics"], sig["learnings"]
    print("[hill-climb] ── Loop 4 신호 리포트 (결정론 집계) ──\n")
    print("① verify-loop (Loop 2 트레이스)")
    print(f"   루프 {vl['total']}개 · 상태 {vl['status']} · 평균 revision {vl['avg_revisions']}")
    if vl["grader_revision_rate"]:
        print(f"   grader revision율: {vl['grader_revision_rate']}")
    if vl["escalated_features"]:
        print(f"   에스컬레이션: {vl['escalated_features']}")
    print("\n② analytics")
    print(f"   이벤트 {an['events']} · handoff {an['handoffs']}회 · 평균 변경파일 {an['avg_files_changed']}")
    if an["features_touched"]:
        print(f"   feature 접촉 빈도: {an['features_touched']}")
    print("\n③ learnings")
    print(f"   총 {le['total']}건 · 유형 {le['by_type']}")
    print("\n── 개선 후보 (harness-config candidate) ──")
    for c in cands:
        print(f"   • {c}")
    print("\n※ 헬퍼는 신호·후보만 낸다 (결정론). 이를 구체 config 변경안으로 바꾸는 것은")
    print("  분석 에이전트(retro/architect)+사람 몫 — 그때 Loop 4 가 닫힌다.")
    print("  예: reviewer/architect 에게 '위 후보로 harness 개선안을 제시하라' 위임.")
    return 0


def cmd_self(args) -> int:
    """트레이스 소스 감지."""
    print("[hill-climb] ── self check ──")
    print(f"  Python: {sys.version.split()[0]} (stdlib only)")
    print(f"  프로젝트 루트: {_ROOT}")
    n_loops = len(list(_VERIFY_LOOP.glob("*.json"))) if _VERIFY_LOOP.exists() else 0
    print(f"  ① verify-loop: {n_loops}개 상태 파일")
    print(f"  ② analytics.jsonl: {'존재' if _ANALYTICS.exists() else '없음'} ({len(_read_jsonl(_ANALYTICS))} 이벤트)")
    print(f"  ③ learnings.jsonl: {'존재' if _LEARNINGS.exists() else '없음'} ({len(_read_jsonl(_LEARNINGS))} 건)")
    print(f"  임계: files_changed≥{_HIGH_FILES_CHANGED} / revision율≥{_HIGH_REVISION_RATE:.0%}")
    return 0


def main() -> None:
    """CLI 진입점."""
    parser = argparse.ArgumentParser(description="Loop 4 Hill-Climbing 신호 집계 (claude.loope 전용)")
    sub = parser.add_subparsers(dest="command")
    p_an = sub.add_parser("analyze", help="트레이스 집계 → 신호 + 개선 후보")
    p_an.add_argument("--json", action="store_true", help="기계 판독용 JSON 출력")
    sub.add_parser("self", help="트레이스 소스 감지")

    args = parser.parse_args()
    handlers = {"analyze": cmd_analyze, "self": cmd_self}
    if args.command is None:
        parser.print_help()
        sys.exit(0)
    sys.exit(handlers[args.command](args))


if __name__ == "__main__":
    main()
