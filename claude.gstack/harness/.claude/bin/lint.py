#!/usr/bin/env python3
"""F009 — Lint helper for harness governance.

정합성 헬스체크 도구. 거버넌스 산출물(feature_list / ADR / learnings / mirror)을
JSON·마크다운 분석으로 검사한다.

서브커맨드:
  check                  — 검사기 실행, 결과를 stdout에 표로 출력
  check --strict         — BLOCK이 1건이라도 있으면 exit 1 (기본은 항상 0)
  check --only=LINT-FL   — 특정 검사기만 실행
  check --json           — 머신용 JSON 출력
  regenerate-index       — (세션 2에서 구현) docs/index.md 갱신
  report                 — (세션 2에서 구현) 캐시된 마지막 실행 결과 표시

검사기 (세션 1):
  LINT-FL     feature_list 정합성 (status×passes, 의존성 무결성)
  LINT-STALE  stale in-progress (>30일)
  LINT-AC     acceptance_criteria 누락·모호

검사기 (세션 2):
  LINT-ADR    ADR ↔ feature 연결성
  LINT-LEARN  learnings 모순
  LINT-MIRROR 미러링 diff (4변형)

외부 의존성: 없음 (Python stdlib only)
hook-failure-tolerance: 최상위 try/except → 예기치 못한 예외도 stderr + exit 0
"""

import argparse
import json
import re
import sys
import tempfile
import os
from pathlib import Path
from datetime import datetime, timezone, timedelta

# 프로젝트 루트: bin/lint.py → .claude/bin/lint.py → 프로젝트 루트
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_FEATURE_LIST = _PROJECT_ROOT / "feature_list.json"
_DOCS_ADR = _PROJECT_ROOT / "docs" / "adr"
_STATE_DIR = _PROJECT_ROOT / ".claude" / "state"
_CHECKPOINTS_DIR = _STATE_DIR / "checkpoints"
_LEARNINGS_FILE = _STATE_DIR / "learnings.jsonl"
_CACHE_FILE = _STATE_DIR / "lint-last.json"

# 라벨 (F007 design-review 일관)
BLOCK = "BLOCK"
CONCERN = "CONCERN"
INFO = "INFO"
PASS = "PASS"

# 모호 키워드 패턴 (LINT-AC)
_VAGUE_PATTERNS = re.compile(
    r"\b(잘\s*동작|적절히|일반적으로|충분히|문제없이|정상적으로|대략|적당히|보통"
    r"|works\s+correctly|properly|reasonably|appropriately)\b",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# 공통 타입
# ---------------------------------------------------------------------------

def _issue(checker_id: str, label: str, target: str, message: str) -> dict:
    """단일 검사 결과 딕셔너리를 생성한다."""
    return {
        "id": checker_id,
        "label": label,
        "target": target,
        "message": message,
    }


# ---------------------------------------------------------------------------
# LINT-FL: feature_list 정합성
# ---------------------------------------------------------------------------

def check_fl() -> list:
    """
    feature_list.json 의 정합성을 검사한다.

    검사 항목:
    - passes/status 조합 BLOCK: passes=true & status!=done, 또는 status=done & passes=false
    - 의존성 참조 무결성: dependencies 에 존재하지 않는 ID 포함 시 BLOCK
    - 의존성 순서 CONCERN: 의존 feature 가 아직 passes=false 인데 본인이 in-progress 이상
    - INFO: priority 또는 estimated_sessions 누락

    Returns:
        list[dict]: 검사 결과 목록 (각 dict는 id/label/target/message 키 보유)
    """
    results = []
    checker = "LINT-FL"

    try:
        if not _FEATURE_LIST.exists():
            results.append(_issue(checker, BLOCK, "feature_list.json", "파일이 존재하지 않음"))
            return results

        with open(_FEATURE_LIST, encoding="utf-8") as f:
            features = json.load(f)

        all_ids = {feat.get("id") for feat in features if "id" in feat}
        status_order = ["todo", "in-progress", "review", "qa", "done"]

        for feat in features:
            fid = feat.get("id", "UNKNOWN")
            passes = feat.get("passes")
            status = feat.get("status")

            # 필수 필드 확인
            for field in ("passes", "status", "id"):
                if field not in feat:
                    results.append(_issue(checker, BLOCK, fid, f"필수 필드 누락: {field}"))

            if passes is None or status is None:
                continue

            # passes × status 정합성
            if passes is True and status != "done":
                results.append(_issue(
                    checker, BLOCK, fid,
                    f"passes=true 인데 status={status!r} (done 이어야 함)"
                ))
            elif passes is False and status == "done":
                results.append(_issue(
                    checker, BLOCK, fid,
                    f"status=done 인데 passes=false (passes=true 이어야 함)"
                ))
            else:
                # 정상 케이스도 명시적 PASS
                results.append(_issue(checker, PASS, fid, "passes×status 정합성 OK"))

            # 의존성 무결성
            deps = feat.get("dependencies", [])
            for dep_id in deps:
                if dep_id not in all_ids:
                    results.append(_issue(
                        checker, BLOCK, fid,
                        f"dependencies에 존재하지 않는 ID 참조: {dep_id}"
                    ))

            # 의존성 순서 CONCERN
            if status in ("in-progress", "review", "qa", "done"):
                for dep_id in deps:
                    dep_feat = next((d for d in features if d.get("id") == dep_id), None)
                    if dep_feat and not dep_feat.get("passes", True):
                        results.append(_issue(
                            checker, CONCERN, fid,
                            f"의존 feature {dep_id}가 아직 passes=false 인데 status={status!r}"
                        ))

            # INFO: priority / estimated_sessions 누락
            if not feat.get("priority"):
                results.append(_issue(checker, INFO, fid, "priority 필드 미설정"))
            if not feat.get("estimated_sessions"):
                results.append(_issue(checker, INFO, fid, "estimated_sessions 필드 미설정"))

    except Exception as exc:  # noqa: BLE001
        results.append(_issue(checker, INFO, "feature_list.json", f"검사 중 오류 — {exc}"))

    return results


# ---------------------------------------------------------------------------
# LINT-STALE: 오래된 in-progress
# ---------------------------------------------------------------------------

def _parse_checkpoint_date(filename: str):
    """
    체크포인트 파일명에서 날짜를 파싱한다.

    파일명 형식: YYYYMMDD-HHMMSS-*.md 또는 YYYYMMDD-*.md

    Returns:
        datetime | None
    """
    m = re.match(r"^(\d{4})(\d{2})(\d{2})", filename)
    if m:
        try:
            return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)),
                            tzinfo=timezone.utc)
        except ValueError:
            return None
    return None


def check_stale() -> list:
    """
    in-progress 상태인 feature 의 stale 여부를 검사한다.

    비교 방법:
    - .claude/state/checkpoints/ 파일명 YYYYMMDD prefix 파싱 → 가장 최근 일자 추출
    - in-progress feature 와 마지막 checkpoint 날짜 차이 계산

    라벨:
    - BLOCK: 60일 이상 경과
    - CONCERN: 30~60일 경과
    - INFO: 0~30일 또는 checkpoint 없음

    Returns:
        list[dict]: 검사 결과 목록
    """
    results = []
    checker = "LINT-STALE"

    try:
        if not _FEATURE_LIST.exists():
            results.append(_issue(checker, INFO, "feature_list.json", "파일 없음 — 검사 스킵"))
            return results

        with open(_FEATURE_LIST, encoding="utf-8") as f:
            features = json.load(f)

        in_progress = [f for f in features if f.get("status") == "in-progress"]

        if not in_progress:
            results.append(_issue(checker, INFO, "feature_list.json", "in-progress feature 없음 — 검사 대상 0건"))
            return results

        # 가장 최근 checkpoint 날짜 추출
        latest_checkpoint_dt = None
        if _CHECKPOINTS_DIR.exists():
            checkpoint_dates = []
            for cp_file in _CHECKPOINTS_DIR.glob("*.md"):
                dt = _parse_checkpoint_date(cp_file.name)
                if dt:
                    checkpoint_dates.append(dt)
            if checkpoint_dates:
                latest_checkpoint_dt = max(checkpoint_dates)

        now = datetime.now(tz=timezone.utc)

        for feat in in_progress:
            fid = feat.get("id", "UNKNOWN")

            if latest_checkpoint_dt is None:
                results.append(_issue(checker, INFO, fid, "checkpoint 파일 없음 — 경과일 추정 불가"))
                continue

            elapsed_days = (now - latest_checkpoint_dt).days

            if elapsed_days >= 60:
                results.append(_issue(
                    checker, BLOCK, fid,
                    f"in-progress 상태이며 최근 checkpoint로부터 {elapsed_days}일 경과 (60일 이상 — stale)"
                ))
            elif elapsed_days >= 30:
                results.append(_issue(
                    checker, CONCERN, fid,
                    f"in-progress 상태이며 최근 checkpoint로부터 {elapsed_days}일 경과 (30~60일)"
                ))
            else:
                results.append(_issue(
                    checker, INFO, fid,
                    f"in-progress 상태이며 최근 checkpoint로부터 {elapsed_days}일 경과 (30일 미만)"
                ))

    except Exception as exc:  # noqa: BLE001
        results.append(_issue(checker, INFO, "feature_list.json", f"검사 중 오류 — {exc}"))

    return results


# ---------------------------------------------------------------------------
# LINT-AC: acceptance_criteria 누락·모호
# ---------------------------------------------------------------------------

def check_ac() -> list:
    """
    feature_list.json 각 feature 의 acceptance_criteria 를 검사한다.

    검사 항목:
    - BLOCK: acceptance_criteria 배열 자체 없거나 비어있음
    - CONCERN: 모호 키워드 포함 항목 존재 (정규식: _VAGUE_PATTERNS)
    - INFO: 단일 항목 (분해 부족 가능성)

    Returns:
        list[dict]: 검사 결과 목록
    """
    results = []
    checker = "LINT-AC"

    try:
        if not _FEATURE_LIST.exists():
            results.append(_issue(checker, INFO, "feature_list.json", "파일 없음 — 검사 스킵"))
            return results

        with open(_FEATURE_LIST, encoding="utf-8") as f:
            features = json.load(f)

        for feat in features:
            fid = feat.get("id", "UNKNOWN")
            ac = feat.get("acceptance_criteria")

            if ac is None or (isinstance(ac, list) and len(ac) == 0):
                results.append(_issue(
                    checker, BLOCK, fid,
                    "acceptance_criteria 배열이 없거나 비어있음"
                ))
                continue

            if not isinstance(ac, list):
                results.append(_issue(
                    checker, BLOCK, fid,
                    f"acceptance_criteria 타입 오류: {type(ac).__name__} (list 이어야 함)"
                ))
                continue

            # 모호 키워드 검사
            vague_found = []
            for item in ac:
                if isinstance(item, str) and _VAGUE_PATTERNS.search(item):
                    vague_found.append(item[:60] + ("..." if len(item) > 60 else ""))

            if vague_found:
                for vague in vague_found:
                    results.append(_issue(
                        checker, CONCERN, fid,
                        f"모호 키워드 포함: {vague!r}"
                    ))
            else:
                results.append(_issue(checker, PASS, fid, f"acceptance_criteria {len(ac)}건 — 모호 키워드 없음"))

            # 단일 항목 INFO
            if len(ac) == 1:
                results.append(_issue(
                    checker, INFO, fid,
                    "acceptance_criteria가 1건 — 분해 부족 가능성 (INFO)"
                ))

    except Exception as exc:  # noqa: BLE001
        results.append(_issue(checker, INFO, "feature_list.json", f"검사 중 오류 — {exc}"))

    return results


# ---------------------------------------------------------------------------
# 검사기 레지스트리
# ---------------------------------------------------------------------------

_CHECKERS = {
    "LINT-FL": ("feature_list 정합성", check_fl),
    "LINT-STALE": ("오래된 in-progress", check_stale),
    "LINT-AC": ("acceptance_criteria 누락·모호", check_ac),
    # 세션 2에서 추가:
    # "LINT-ADR": ("ADR ↔ feature 연결성", check_adr),
    # "LINT-LEARN": ("learnings 모순", check_learn),
    # "LINT-MIRROR": ("미러링 diff (4변형)", check_mirror),
}


# ---------------------------------------------------------------------------
# 출력 포매터
# ---------------------------------------------------------------------------

def _format_human(ts: str, all_results: dict, summary: dict) -> str:
    """
    검사 결과를 사람이 읽기 좋은 마크다운 표 형식으로 포매팅한다.

    Args:
        ts: 실행 시각 문자열
        all_results: {checker_id: [issue, ...]} 딕셔너리
        summary: {"BLOCK": n, "CONCERN": n, "INFO": n, "PASS": n}

    Returns:
        str: 포매팅된 출력 문자열
    """
    lines = []
    lines.append(f"=== F009 Lint Report — {ts} ===")
    lines.append("")

    for checker_id, (checker_desc, _) in _CHECKERS.items():
        if checker_id not in all_results:
            continue
        issues = all_results[checker_id]
        lines.append(f"{checker_id} ({checker_desc})")
        lines.append("| # | 라벨 | 항목 | 메시지 |")
        lines.append("|---|---|---|---|")
        for i, issue in enumerate(issues, 1):
            label = issue["label"]
            target = issue["target"]
            message = issue["message"]
            lines.append(f"| {i} | {label} | {target} | {message} |")
        lines.append("")

    block_n = summary["BLOCK"]
    concern_n = summary["CONCERN"]
    info_n = summary["INFO"]
    pass_n = summary["PASS"]
    lines.append(f"요약: {block_n} BLOCK, {concern_n} CONCERN, {info_n} INFO, {pass_n} PASS")

    if block_n > 0:
        lines.append("")
        lines.append("BLOCK 항목이 있습니다. 즉시 수정이 필요합니다.")
        lines.append("--strict 플래그를 사용하면 BLOCK 발견 시 exit 1 (CI gate 용도)")

    return "\n".join(lines)


def _format_json(ts: str, all_results: dict, summary: dict) -> str:
    """
    검사 결과를 머신 파싱용 JSON 형식으로 포매팅한다.

    Args:
        ts: ISO 8601 타임스탬프 문자열
        all_results: {checker_id: [issue, ...]} 딕셔너리
        summary: {"BLOCK": n, "CONCERN": n, "INFO": n, "PASS": n}

    Returns:
        str: JSON 문자열
    """
    flat_results = []
    for checker_id, issues in all_results.items():
        for issue in issues:
            flat_results.append(issue)

    output = {
        "ts": ts,
        "results": flat_results,
        "summary": summary,
    }
    return json.dumps(output, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# 캐시 저장 (atomic write)
# ---------------------------------------------------------------------------

def _save_cache(ts: str, all_results: dict, summary: dict) -> None:
    """
    검사 결과를 .claude/state/lint-last.json 에 원자적으로 저장한다.

    atomic write: tempfile + os.rename 패턴으로 부분 쓰기 방지.

    Args:
        ts: ISO 8601 타임스탬프
        all_results: 검사 결과 딕셔너리
        summary: 요약 딕셔너리
    """
    try:
        _STATE_DIR.mkdir(parents=True, exist_ok=True)
        flat_results = []
        for issues in all_results.values():
            flat_results.extend(issues)
        payload = {"ts": ts, "results": flat_results, "summary": summary}
        # tempfile을 같은 디렉토리에 생성해야 atomic rename 가능
        fd, tmp_path = tempfile.mkstemp(dir=_STATE_DIR, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            os.rename(tmp_path, _CACHE_FILE)
        except Exception:
            # 임시 파일 정리
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
    except Exception as exc:  # noqa: BLE001
        print(f"[lint] 캐시 저장 실패 (무시): {exc}", file=sys.stderr)


# ---------------------------------------------------------------------------
# 서브커맨드 핸들러
# ---------------------------------------------------------------------------

def cmd_check(args) -> int:
    """
    'check' 서브커맨드 핸들러 — 검사기 실행 후 결과 출력.

    Args:
        args: argparse Namespace (strict, only, json 필드 포함)

    Returns:
        int: exit code (--strict 시 BLOCK 존재하면 1, 그 외 0)
    """
    now = datetime.now(tz=timezone(timedelta(hours=9)))  # KST
    ts_display = now.strftime("%Y-%m-%d %H:%M")
    ts_iso = now.isoformat()

    # 실행할 검사기 결정
    only = getattr(args, "only", None)
    if only:
        # --only=LINT-FL,LINT-AC 형태 지원
        only_ids = [x.strip() for x in only.split(",")]
        checkers_to_run = {k: v for k, v in _CHECKERS.items() if k in only_ids}
        unknown = [x for x in only_ids if x not in _CHECKERS]
        if unknown:
            print(f"[lint] 알 수 없는 검사기 ID: {unknown}", file=sys.stderr)
            print(f"[lint] 사용 가능: {list(_CHECKERS.keys())}", file=sys.stderr)
    else:
        checkers_to_run = _CHECKERS

    # 검사기 실행
    all_results = {}
    for checker_id, (_, fn) in checkers_to_run.items():
        try:
            all_results[checker_id] = fn()
        except Exception as exc:  # noqa: BLE001
            all_results[checker_id] = [
                _issue(checker_id, INFO, checker_id, f"검사기 실행 실패 — {exc}")
            ]

    # 요약 계산
    summary = {BLOCK: 0, CONCERN: 0, INFO: 0, PASS: 0}
    for issues in all_results.values():
        for issue in issues:
            label = issue.get("label", INFO)
            if label in summary:
                summary[label] += 1

    # 캐시 저장
    _save_cache(ts_iso, all_results, summary)

    # 출력
    use_json = getattr(args, "json", False)
    if use_json:
        print(_format_json(ts_iso, all_results, summary))
    else:
        print(_format_human(ts_display, all_results, summary))

    # exit code
    strict = getattr(args, "strict", False)
    if strict and summary[BLOCK] > 0:
        return 1
    return 0


def cmd_regenerate_index(args) -> int:  # noqa: ARG001
    """
    'regenerate-index' 서브커맨드 핸들러.

    세션 2에서 구현 예정. 현재는 안내 메시지만 출력.

    Args:
        args: argparse Namespace (미사용)

    Returns:
        int: exit code (항상 0)
    """
    print("[lint] regenerate-index는 세션 2에서 구현됩니다.")
    print("[lint] docs/index.md 자동 생성 기능은 다음 세션에서 추가될 예정입니다.")
    return 0


def cmd_report(args) -> int:  # noqa: ARG001
    """
    'report' 서브커맨드 핸들러 — 캐시된 마지막 실행 결과 표시.

    세션 2에서 완전 구현 예정. 현재는 캐시 파일이 있으면 읽어 출력.

    Args:
        args: argparse Namespace (미사용)

    Returns:
        int: exit code (항상 0)
    """
    if not _CACHE_FILE.exists():
        print("[lint] 캐시 파일 없음. 먼저 'check'를 실행하세요.")
        print(f"[lint] 예상 경로: {_CACHE_FILE}")
        return 0

    try:
        with open(_CACHE_FILE, encoding="utf-8") as f:
            cached = json.load(f)
        ts = cached.get("ts", "unknown")
        summary = cached.get("summary", {})
        block_n = summary.get(BLOCK, 0)
        concern_n = summary.get(CONCERN, 0)
        info_n = summary.get(INFO, 0)
        pass_n = summary.get(PASS, 0)
        print(f"[lint] 마지막 실행: {ts}")
        print(f"[lint] 요약: {block_n} BLOCK, {concern_n} CONCERN, {info_n} INFO, {pass_n} PASS")
        print("[lint] 상세 결과는 'check --json'으로 재실행하거나 세션 2의 report 명령을 사용하세요.")
    except Exception as exc:  # noqa: BLE001
        print(f"[lint] 캐시 읽기 실패: {exc}", file=sys.stderr)

    return 0


# ---------------------------------------------------------------------------
# 진입점
# ---------------------------------------------------------------------------

def main() -> int:
    """
    lint.py 메인 진입점.

    서브커맨드를 파싱하고 적절한 핸들러를 호출한다.
    최상위 try/except로 예기치 못한 예외도 stderr 로그 + exit 0 보장.

    Returns:
        int: exit code
    """
    parser = argparse.ArgumentParser(
        description="F009 — Lint helper for harness governance",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command")

    # check
    check_parser = subparsers.add_parser("check", help="검사기 실행")
    check_parser.add_argument(
        "--strict",
        action="store_true",
        default=False,
        help="BLOCK이 1건이라도 있으면 exit 1 (CI gate용)",
    )
    check_parser.add_argument(
        "--only",
        metavar="CHECKER_ID",
        default=None,
        help="특정 검사기만 실행 (예: LINT-FL, 콤마 구분 복수 지정 가능)",
    )
    check_parser.add_argument(
        "--json",
        action="store_true",
        default=False,
        help="머신용 JSON 출력",
    )

    # regenerate-index
    subparsers.add_parser("regenerate-index", help="docs/index.md 갱신 (세션 2 구현 예정)")

    # report
    subparsers.add_parser("report", help="캐시된 마지막 실행 결과 표시")

    args = parser.parse_args()

    if args.command == "check":
        return cmd_check(args)
    elif args.command == "regenerate-index":
        return cmd_regenerate_index(args)
    elif args.command == "report":
        return cmd_report(args)
    else:
        parser.print_help()
        return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001
        # hook-failure-tolerance: 예기치 못한 예외도 exit 0
        print(f"[lint] 예기치 못한 오류 (무시): {exc}", file=sys.stderr)
        sys.exit(0)
