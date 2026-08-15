#!/usr/bin/env python3
"""
verify_loop.py — Loop 2 (검증 루프) 정형화 (claude.loope 전용)

LangChain "loop engineering" 의 Loop 2(Verification Loop)를 하네스에 이식한 것.
하네스는 이미 Reviewer→NEEDS REVISION→재시도 + QA 게이트 + 3회 에스컬레이션 규칙을
갖고 있으나, **rubric 이 암묵적이고 재시도 상태가 코드화돼 있지 않다**. 이 헬퍼가:

  ① 명시적 rubric 로드 (.claude/rubrics/<name>.md — MUST/SHOULD 체크리스트)
  ② grader 판정을 상태로 추적 (.claude/state/verify-loop/<feature>.json)
  ③ 재시도 횟수 집계 + 에스컬레이션 자동 판정 (기본 3회)
  ④ grader 종류 구분 — 결정론(lint/design-review/qa-browser) vs LLM-judge(reviewer/qa)

즉 "이미 도는 루프를 명시적·유계(bounded)로 만든다" (프레임워크를 짓지 않음 — Karpathy).

사용법:
  python3 .claude/bin/verify_loop.py start F001 --rubric code-review
  python3 .claude/bin/verify_loop.py record F001 --grader lint --verdict pass
  python3 .claude/bin/verify_loop.py record F001 --grader reviewer --verdict revision --must 1 --should 2 --notes "docstring 누락"
  python3 .claude/bin/verify_loop.py record F001 --grader reviewer --verdict pass
  python3 .claude/bin/verify_loop.py status F001
  python3 .claude/bin/verify_loop.py rubric code-review     # rubric 표시
  python3 .claude/bin/verify_loop.py list                   # 진행중 루프
  python3 .claude/bin/verify_loop.py self                   # 점검

상태 위치: .claude/state/verify-loop/<feature>.json (런타임 gitignore)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path


def _project_root() -> Path:
    """하네스 루트 ($CLAUDE_PROJECT_DIR > 스크립트 위치 기준 parent×3)."""
    env = os.environ.get("CLAUDE_PROJECT_DIR")
    if env and Path(env).is_dir():
        return Path(env)
    return Path(__file__).resolve().parent.parent.parent


_ROOT = _project_root()
_STATE = _ROOT / ".claude" / "state" / "verify-loop"
_RUBRICS = _ROOT / ".claude" / "rubrics"

_ESCALATION_THRESHOLD = 3  # NEEDS REVISION N회 → 에스컬레이션 (reviewer.md 규칙과 일치)

# grader 종류 (LangChain: 결정론 grader vs LLM-judge grader).
# 결정론 = 프로그램이 pass/fail 판정 / judge = 에이전트가 판단.
_DETERMINISTIC = {"lint", "design-review", "qa-browser", "test"}
_JUDGE = {"reviewer", "qa", "architect"}

_VERDICTS = ("pass", "revision", "fail")


def _now() -> str:
    """UTC ISO 타임스탬프."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _grader_kind(grader: str) -> str:
    """grader 이름 → 종류(deterministic|judge). 미등록은 judge 로 간주."""
    if grader in _DETERMINISTIC:
        return "deterministic"
    return "judge"


def _loop_path(feature: str) -> Path:
    """feature 의 루프 상태 파일 경로."""
    return _STATE / f"{feature}.json"


def _load(feature: str) -> dict | None:
    """루프 상태를 읽는다 (없으면 None)."""
    p = _loop_path(feature)
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return None


def _save(loop: dict) -> None:
    """루프 상태를 저장한다."""
    _STATE.mkdir(parents=True, exist_ok=True)
    _loop_path(loop["feature"]).write_text(
        json.dumps(loop, ensure_ascii=False, indent=2), encoding="utf-8")


def cmd_start(args) -> int:
    """feature 의 검증 루프를 개시한다 (rubric 바인딩)."""
    feature = args.feature
    rubric = args.rubric or "code-review"
    rubric_file = _RUBRICS / f"{rubric}.md"
    if not rubric_file.exists():
        avail = ", ".join(p.stem for p in _RUBRICS.glob("*.md")) or "(없음)"
        print(f"[verify-loop] ⚠️ rubric '{rubric}' 없음 — 사용 가능: {avail}")
        print(f"  계속 진행하나 rubric 없이 기록됩니다 (.claude/rubrics/{rubric}.md 권장).")
    loop = {
        "feature": feature,
        "rubric": rubric,
        "attempts": [],
        "revision_count": 0,
        "status": "in-loop",
        "escalation_threshold": _ESCALATION_THRESHOLD,
        "started": _now(),
    }
    _save(loop)
    print(f"[verify-loop] 개시: {feature} (rubric={rubric}, 에스컬레이션 임계 {_ESCALATION_THRESHOLD}회)")
    print(f"  다음: grader 가 채점 후 `record {feature} --grader <name> --verdict pass|revision|fail`")
    return 0


def cmd_record(args) -> int:
    """grader 의 판정을 루프에 기록하고 에스컬레이션을 판정한다."""
    feature = args.feature
    loop = _load(feature)
    if loop is None:
        print(f"[verify-loop] ⚠️ {feature} 루프 없음 — 자동 개시합니다 (start 생략 허용).")
        cmd_start(argparse.Namespace(feature=feature, rubric=args.rubric or "code-review"))
        loop = _load(feature)
    if args.verdict not in _VERDICTS:
        print(f"[verify-loop] ❌ verdict 오류: {args.verdict} (pass|revision|fail)")
        return 1

    kind = _grader_kind(args.grader)
    attempt = {
        "n": len(loop["attempts"]) + 1,
        "grader": args.grader,
        "kind": kind,
        "verdict": args.verdict,
        "ts": _now(),
    }
    if args.must is not None:
        attempt["must"] = args.must
    if args.should is not None:
        attempt["should"] = args.should
    if args.notes:
        attempt["notes"] = args.notes
    loop["attempts"].append(attempt)

    if args.verdict == "revision":
        loop["revision_count"] += 1

    # 상태 전이
    if args.verdict == "pass":
        loop["status"] = "passed"
    elif args.verdict == "fail":
        loop["status"] = "failed"
    elif loop["revision_count"] >= loop["escalation_threshold"]:
        loop["status"] = "escalated"
    else:
        loop["status"] = "in-loop"
    _save(loop)

    grade_note = ""
    if args.must is not None:
        grade_note = f" (MUST {args.must}" + (f", SHOULD {args.should}" if args.should is not None else "") + ")"
    icon = {"pass": "✅", "revision": "🔄", "fail": "❌"}[args.verdict]
    print(f"[verify-loop] {icon} {feature} #{attempt['n']} — {args.grader}({kind}) → {args.verdict}{grade_note}")
    if loop["status"] == "escalated":
        print(f"  🚨 ESCALATION — NEEDS REVISION {loop['revision_count']}회 도달 (임계 {loop['escalation_threshold']}).")
        print("     Planner+Architect 재검토 권장 · Feature 분해 검토 · /project:learn add (pitfall).")
    elif loop["status"] == "passed":
        print(f"  통과 — 총 {attempt['n']}회 시도, revision {loop['revision_count']}회.")
    elif loop["status"] == "failed":
        print("  REJECTED — 재작업 필요.")
    else:
        print(f"  진행중 — revision {loop['revision_count']}/{loop['escalation_threshold']}.")
    return 0


def _print_loop(loop: dict) -> None:
    """루프 상태를 사람이 읽게 출력한다."""
    st = loop["status"]
    badge = {"passed": "✅ PASSED", "failed": "❌ FAILED",
             "escalated": "🚨 ESCALATED", "in-loop": "🔄 IN-LOOP"}.get(st, st)
    print(f"  {loop['feature']}  [{badge}]  rubric={loop['rubric']}  "
          f"revision {loop['revision_count']}/{loop['escalation_threshold']}")
    for a in loop["attempts"]:
        extra = ""
        if "must" in a:
            extra = f" (MUST {a['must']}, SHOULD {a.get('should','?')})"
        if a.get("notes"):
            extra += f" — {a['notes']}"
        print(f"    #{a['n']} {a['grader']}({a['kind']}) → {a['verdict']}{extra}")


def cmd_status(args) -> int:
    """특정 feature 의 루프 상태를 표시한다."""
    loop = _load(args.feature)
    if loop is None:
        print(f"[verify-loop] {args.feature} 루프 없음")
        return 0
    print(f"[verify-loop] 상태 — {args.feature}")
    _print_loop(loop)
    return 0


def cmd_list(args) -> int:
    """모든 진행중/완료 루프를 나열한다."""
    if not _STATE.exists() or not any(_STATE.glob("*.json")):
        print("[verify-loop] 루프 없음 — `start <feature>` 로 개시")
        return 0
    loops = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(_STATE.glob("*.json"))]
    print(f"[verify-loop] 루프 {len(loops)}개")
    for loop in loops:
        _print_loop(loop)
    return 0


def cmd_rubric(args) -> int:
    """rubric 을 표시하거나 목록을 나열한다."""
    if args.name:
        rf = _RUBRICS / f"{args.name}.md"
        if not rf.exists():
            print(f"[verify-loop] rubric '{args.name}' 없음")
            return 1
        print(rf.read_text(encoding="utf-8"))
        return 0
    rubrics = sorted(p.stem for p in _RUBRICS.glob("*.md")) if _RUBRICS.exists() else []
    print(f"[verify-loop] rubric 목록: {', '.join(rubrics) or '(없음)'}")
    return 0


def cmd_self(args) -> int:
    """환경·상태 점검."""
    print("[verify-loop] ── self check ──")
    print(f"  Python: {sys.version.split()[0]} (stdlib only)")
    print(f"  프로젝트 루트: {_ROOT}")
    rubrics = sorted(p.stem for p in _RUBRICS.glob("*.md")) if _RUBRICS.exists() else []
    print(f"  rubrics: {', '.join(rubrics) or '(없음 — .claude/rubrics/ 생성 권장)'}")
    n = len(list(_STATE.glob("*.json"))) if _STATE.exists() else 0
    print(f"  진행/완료 루프: {n}개")
    print(f"  grader 종류: 결정론={sorted(_DETERMINISTIC)} / judge={sorted(_JUDGE)}")
    print(f"  에스컬레이션 임계: {_ESCALATION_THRESHOLD}회")
    return 0


def main() -> None:
    """CLI 진입점."""
    parser = argparse.ArgumentParser(description="Loop 2 검증 루프 정형화 (claude.loope 전용)")
    sub = parser.add_subparsers(dest="command")

    p_start = sub.add_parser("start", help="검증 루프 개시")
    p_start.add_argument("feature", help="Feature ID (예: F001)")
    p_start.add_argument("--rubric", help="rubric 이름 (기본 code-review)")

    p_rec = sub.add_parser("record", help="grader 판정 기록")
    p_rec.add_argument("feature", help="Feature ID")
    p_rec.add_argument("--grader", required=True, help="grader 이름 (lint|design-review|qa-browser|reviewer|qa …)")
    p_rec.add_argument("--verdict", required=True, help="pass|revision|fail")
    p_rec.add_argument("--must", type=int, help="MUST 미해결 건수 (judge grader)")
    p_rec.add_argument("--should", type=int, help="SHOULD 건수 (judge grader)")
    p_rec.add_argument("--notes", help="판정 메모")
    p_rec.add_argument("--rubric", help="루프 미개시 시 자동 개시할 rubric")

    p_st = sub.add_parser("status", help="특정 feature 루프 상태")
    p_st.add_argument("feature", help="Feature ID")

    sub.add_parser("list", help="모든 루프 나열")

    p_ru = sub.add_parser("rubric", help="rubric 표시/목록")
    p_ru.add_argument("name", nargs="?", help="rubric 이름 (생략 시 목록)")

    sub.add_parser("self", help="환경 점검")

    args = parser.parse_args()
    handlers = {
        "start": cmd_start, "record": cmd_record, "status": cmd_status,
        "list": cmd_list, "rubric": cmd_rubric, "self": cmd_self,
    }
    if args.command is None:
        parser.print_help()
        sys.exit(0)
    sys.exit(handlers[args.command](args))


if __name__ == "__main__":
    main()
