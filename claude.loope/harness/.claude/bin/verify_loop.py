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
import contextlib
import fcntl
import json
import os
import re
import sys
import tempfile
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
_JUDGE = {"reviewer", "qa"}
# 에스컬레이션 처리자 — judge 로 세지만 **루프를 닫지는 못한다** (MUST-2).
_ESCALATION_HANDLER = {"architect"}

_VERDICTS = ("pass", "revision", "fail")
_STATUSES = ("in-loop", "passed", "failed", "escalated")
# `_print_loop` 가 직접 첨자하는 키들 — 없으면 목록 전체가 죽는다.
_REQUIRED_ATTEMPT_KEYS = {"n", "grader", "kind", "verdict"}


def _now() -> str:
    """UTC ISO 타임스탬프."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _grader_kind(grader: str) -> str:
    """grader 이름 → 종류(deterministic|judge).

    미등록 이름은 여기 오지 않는다 — `cmd_record` 가 먼저 거부한다 (MUST-2).
    예전엔 미등록을 **judge 로 승격**시켰고, judge 의 pass 는 루프를 통과시키므로
    `--grader Lint` 오타 하나가 게이트를 통째로 건너뛰었다. 권한이 큰 쪽을 기본값으로
    두는 것이 fail-open 이다.
    """
    return "deterministic" if grader in _DETERMINISTIC else "judge"
    # NOTE: _ESCALATION_HANDLER(architect)도 judge 로 센다 — 판단하는 쪽이다.
    #       다만 루프를 **닫지는 못한다** (cmd_record 가 따로 가른다).


# feature id·rubric 이름은 **파일 경로 성분**이 된다. 검증 없이 쓰면 상태 디렉토리를
# 벗어난다 (실측: `start ../../pwn` → `.claude/pwn.json` 생성).
_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


def _safe_name(value: str, what: str) -> str:
    """경로 성분으로 쓸 이름을 검증한다. 위반이면 SystemExit(2).

    화이트리스트로 거르고 `..` 를 따로 막는다 — `.` 가 허용 문자라 `..` 만으로도
    상위로 갈 수 있기 때문이다.
    """
    name = (value or "").strip()
    if not _NAME_RE.match(name) or ".." in name:
        print(f"[verify-loop] ❌ 잘못된 {what}: {value!r}")
        print("  영숫자로 시작하고 영숫자·`.`·`_`·`-` 만, 64자 이내 (`..` 불가)")
        raise SystemExit(2)
    return name


def _loop_path(feature: str) -> Path:
    """feature 의 루프 상태 파일 경로."""
    return _STATE / f"{_safe_name(feature, 'feature id')}.json"


def _quarantine(path: Path, why: str) -> None:
    """손상·비정형 상태 파일을 `*.corrupt-<ts>` 로 치우고 None 을 돌려준다.

    삭제하지 않는 이유: 원인을 남겨야 다음 사람이 무슨 일이 있었는지 안다.
    파싱 오류와 형태 오류가 **같은 주소**를 쓰게 모아 둔다 — 갈라 두면 한쪽만 고친다.
    """
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    quarantined = path.with_suffix(f".json.corrupt-{stamp}")
    try:
        os.replace(path, quarantined)
    except OSError:
        pass
    print(f"[verify-loop] ⚠️ 상태 파일 {why} — {quarantined.name} 로 보존하고 새로 시작")
    return None


def _read_loop(path: Path) -> dict | None:
    """상태 파일 하나를 **안전하게** 읽는다. 손상이면 옆으로 치우고 None.

    한 파일이 깨졌다고 `list` 가 정상 파일까지 못 보여주거나 `record` 가 영구히
    실패하면, 그 feature 의 루프는 되살릴 수 없다 (실측: torn JSON 1건에 세 명령 모두
    traceback). 삭제하지 않고 `*.corrupt-<ts>` 로 보존해 원인을 남긴다.
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, UnicodeDecodeError, RecursionError, OSError) as exc:
        # 디렉토리·권한 오류까지 "손상" 으로 보고 **rename** 하면 안 된다 — 예전엔
        # `IsADirectoryError` 에 디렉토리를 통째로 옆으로 치웠다. 읽기 실패 종류를 좁힌다.
        if isinstance(exc, OSError) and not isinstance(exc, (IsADirectoryError, PermissionError)):
            raise
        if isinstance(exc, (IsADirectoryError, PermissionError)):
            print(f"[verify-loop] ⚠️ 상태 파일을 읽을 수 없음(건너뜀): {path.name} — "
                  f"{type(exc).__name__}")
            return None
        return _quarantine(path, f"손상 ({type(exc).__name__}: {str(exc)[:60]})")
    # 형태까지 본다 — 파싱만 통과한 비정형은 소비 지점에서 KeyError/AttributeError 가 된다.
    if not isinstance(data, dict) or not isinstance(data.get("attempts"), list):
        # 예전엔 여기서 None 만 돌려줬고, 그러면 자동 start 가 그 파일을 **덮어썼다**.
        # "손상은 삭제하지 않고 보존한다" 는 약속이 파싱 오류에만 적용됐던 것이다.
        return _quarantine(path, "형태 오류(최상위 dict + attempts list 아님)")

    # `feature` 키는 **파일명이 SSOT** 다. 예전엔 `setdefault` 라 키가 있으면 그대로
    # 믿었고, 내용이 다른 feature 를 가리키면 `_save` 가 **다른 파일에 써서** 원본은
    # 영영 갱신되지 않았다 (락은 F001, 쓰기는 F002 — 교차 lost update).
    data["feature"] = path.stem
    data["revision_count"] = _as_count(data.get("revision_count"), 0)
    data["escalation_threshold"] = _as_count(
        data.get("escalation_threshold"), _ESCALATION_THRESHOLD, minimum=1)
    if data.get("status") not in _STATUSES:
        data["status"] = "in-loop"
    if not isinstance(data.get("rubric"), str) or not data["rubric"].strip():
        data["rubric"] = "code-review"
    # attempt 원소도 소비 지점(`_print_loop` 의 `a['n']`)이 직접 첨자한다 — 필수 키가
    # 없는 원소 하나에 `list` 가 통째로 죽었다. dict 여부만으로는 부족하다.
    data["attempts"] = [a for a in data["attempts"]
                        if isinstance(a, dict) and _REQUIRED_ATTEMPT_KEYS <= a.keys()]
    return data


def _as_count(value: object, default: int, minimum: int = 0) -> int:
    """정수 카운터를 안전하게 읽는다 (bool 은 정수가 아니다).

    `revision_count` 가 문자열 `"3"` 이면 `+= 1` 이 TypeError 를 내고 **매 record 마다**
    같은 자리에서 죽었다 — 영구 wedge. `escalation_threshold` 가 None 이면 `>=` 비교가
    터진다. 값을 못 믿으면 기본값으로 갈아끼운다.
    """
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        return default
    return value


def _load(feature: str) -> dict | None:
    """루프 상태를 읽는다 (없거나 손상이면 None)."""
    p = _loop_path(feature)
    return _read_loop(p) if p.exists() else None


def _save(loop: dict) -> None:
    """루프 상태를 **원자적으로** 저장한다 (락으로 read-modify-write 보호).

    `write_text` 는 truncate 후 쓰므로 중단되면 **직전까지의 판정 이력이 사라진다**
    (실측: 쓰기 중단 → 파일이 `{"feature": "F100` 만 남음). 동시 `record` 두 건이
    서로를 덮어쓰는 것도 실측됐다 (20건 동시 → 11건만 기록).
    """
    _STATE.mkdir(parents=True, exist_ok=True)
    feature = loop.get("feature")
    if not isinstance(feature, str) or not feature.strip():
        raise ValueError("루프 상태에 feature 이름이 없습니다 — 저장 대상을 알 수 없습니다")
    target = _loop_path(feature)
    fd, tmp = tempfile.mkstemp(dir=str(_STATE), prefix=".tmp-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(loop, fh, ensure_ascii=False, indent=2)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, target)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


@contextlib.contextmanager
def _loop_lock(feature: str):
    """read-modify-write 를 직렬화한다 (stdlib `fcntl`, Linux 전제).

    reviewer·qa sub-agent 가 병렬로 돌 수 있고 `reviewer.md` 는 결정론 grader 를
    먼저 기록하라고 권한다 — 그 조합이 실제로 lost update 를 만들었다.
    """
    _STATE.mkdir(parents=True, exist_ok=True)
    lock_path = _STATE / f".{_safe_name(feature, 'feature id')}.lock"
    with open(lock_path, "w", encoding="utf-8") as fh:
        try:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        except OSError:
            pass          # 락을 못 걸어도 진행한다 — 없는 것보다 낫고, 막지는 않는다
        yield


def cmd_start(args) -> int:
    """feature 의 검증 루프를 개시한다 (rubric 바인딩).

    이미 루프가 있으면 **거부**한다 (`--force` 로만 리셋). 예전엔 조용히 덮어써서
    에스컬레이션 직전의 revision 카운터를 0 으로 되돌릴 수 있었다 — 판정 위조 경로다.
    """
    feature = _safe_name(args.feature, "feature id")
    # rubric 도 `_RUBRICS / f"{rubric}.md"` 로 **경로 성분**이 된다. 커밋 1731d3e 는
    # "rubric 이름도 같은 검증" 이라 적었지만 실제로는 feature 에만 걸려 있었다.
    rubric = _safe_name(args.rubric or "code-review", "rubric 이름")
    existing = _load(feature)
    if existing is not None and not getattr(args, "force", False):
        print(f"[verify-loop] ❌ {feature} 루프가 이미 있습니다 "
              f"(시도 {len(existing['attempts'])}회, revision {existing['revision_count']}).")
        print("  이력을 지우고 다시 시작하려면 `--force`. 이어서 기록하려면 `record` 를 쓰십시오.")
        return 1
    rubric_file = _RUBRICS / f"{rubric}.md"
    if not rubric_file.exists():
        avail = ", ".join(p.stem for p in _RUBRICS.glob("*.md")) or "(없음)"
        print(f"[verify-loop] ⚠️ rubric '{rubric}' 없음 — 사용 가능: {avail}")
        print(f"  계속 진행하나 rubric 없이 기록됩니다 (.claude/rubrics/{rubric}.md 권장).")
    with _loop_lock(feature):
        _start_locked(feature, rubric)
    print(f"[verify-loop] 개시: {feature} (rubric={rubric}, 에스컬레이션 임계 {_ESCALATION_THRESHOLD}회)")
    print(f"  다음: grader 가 채점 후 `record {feature} --grader <name> --verdict pass|revision|fail`")
    return 0


def cmd_record(args) -> int:
    """grader 의 판정을 루프에 기록하고 에스컬레이션을 판정한다."""
    feature = args.feature
    # 입력 검증을 **부작용 앞**에 둔다 — 예전에는 `--verdict bogus` 여도 자동 start 가
    # 먼저 돌아 빈 상태 파일이 생긴 뒤 exit 1 이었다.
    if args.verdict not in _VERDICTS:
        print(f"[verify-loop] ❌ verdict 오류: {args.verdict} (pass|revision|fail)")
        return 1
    for label, val in (("--must", args.must), ("--should", args.should)):
        if val is not None and val < 0:
            print(f"[verify-loop] ❌ {label} 는 0 이상이어야 합니다: {val}")
            return 1
    if args.grader not in _DETERMINISTIC | _JUDGE | _ESCALATION_HANDLER:
        # 예전엔 경고만 하고 **judge 로 기록**했다. judge 의 pass 는 루프를 통과시키므로
        # `--grader Lint`(대소문자)·`lnt`(오타) 하나로 게이트를 건너뛸 수 있었다.
        # 등록부가 곧 계약이다 — 새 grader 가 필요하면 등록부에 추가한다.
        print(f"[verify-loop] ❌ 미등록 grader: {args.grader!r}")
        print(f"  결정론: {', '.join(sorted(_DETERMINISTIC))}")
        print(f"  judge:  {', '.join(sorted(_JUDGE))}")
        return 1
    # read-modify-write 를 **락 안**에서 한다. reviewer·qa sub-agent 가 병렬로 돌면
    # 서로의 기록을 덮어썼다 (실측: 동시 20건 → 3건만 남음).
    with _loop_lock(feature):
        return _record_locked(args, feature)


def _start_locked(feature: str, rubric: str) -> dict:
    """락을 쥔 상태에서 새 루프를 만든다 (자동 개시 경로가 공유한다)."""
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
    return loop


def _record_locked(args, feature: str) -> int:
    """락을 쥔 상태에서 판정 1건을 기록한다 (cmd_record 의 본체)."""
    loop = _load(feature)
    if loop is None:
        print(f"[verify-loop] ⚠️ {feature} 루프 없음 — 자동 개시합니다 (start 생략 허용).")
        # `cmd_start` 를 부르면 같은 락을 다시 잡는다 (flock 은 같은 프로세스에선
        # 재진입되지만 의존하지 않는다). 락 안에서 쓰는 경로를 따로 둔다.
        loop = _start_locked(feature, _safe_name(args.rubric or "code-review", "rubric 이름"))
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
        # 제어문자를 지우고 길이를 자른다 — `status` 출력이 터미널에 그대로 렌더돼
        # ANSI escape 주입이 가능했고, 100KB notes 가 그대로 저장됐다.
        # 개행·탭도 공백으로 — notes 는 한 줄 요약이고, `status` 출력이 여러 줄로
        # 번지면 다른 판정 항목과 구분이 안 된다.
        clean = re.sub(r"[\x00-\x1f\x7f]", " ", args.notes)
        attempt["notes"] = clean[:2000] + ("…(절단)" if len(clean) > 2000 else "")
    loop["attempts"].append(attempt)

    if args.verdict == "revision":
        loop["revision_count"] += 1

    # 상태 전이 — **judge 의 pass 만** 루프를 통과시킨다.
    # 결정론 grader(lint/design-review/qa-browser)의 pass 는 게이트 하나를 통과한
    # 것이지 판정이 아니다. 예전에는 `record F002 --grader lint --verdict pass` 한 번에
    # `passed` 가 됐는데, 그게 하필 verify-loop.md·reviewer.md 가 권하는 **첫 단계**였다.
    if kind == "deterministic":
        # 결정론 grader 는 **게이트**다 — 통과도 실패도 판정이 아니다.
        # pass: 게이트 하나를 통과한 것이지 루프를 통과한 게 아니다.
        # fail: lint 가 깨진 것을 `failed`(REJECTED — Planner·Architect 재설계)로
        #       올리는 건 과하다. 재작업 신호이므로 revision 과 같은 층에 둔다.
        if args.verdict == "pass":
            gates = loop.setdefault("gates_passed", [])
            if args.grader not in gates:
                gates.append(args.grader)
            # **status 를 건드리지 않는다.** 예전엔 이 재계산이 if 문 밖에 있어서
            # 결정론 pass 가 judge 의 판정을 지웠다 — `reviewer pass → passed` 다음
            # `lint pass` 한 번에 `in-loop` 로 떨어졌고, `failed`(설계 거부)조차
            # lint 한 번으로 풀렸다. 하필 문서가 권하는 운용(승인 후 게이트 기록)을
            # 따를수록 상태가 깨졌다 (F019·F020·F030 실측).
        else:
            # fail/revision 은 재작업 신호다 — 종결됐던 루프도 다시 연다.
            loop["status"] = ("escalated"
                              if loop["revision_count"] >= loop["escalation_threshold"]
                              else "in-loop")
    elif args.grader in _ESCALATION_HANDLER:
        # architect 는 루프를 **닫지 않는다**. 에스컬레이션을 받아 재무장할 뿐이다.
        # 예전엔 `_JUDGE` 에 있어서 `--grader architect --verdict pass` 한 번으로
        # 코드 리뷰 루프가 reviewer 없이 종결됐다 — 두 번째 fail-open 경로였다.
        if loop["status"] != "escalated":
            print(f"[verify-loop] ❌ {args.grader} 는 에스컬레이션 처리자다 — "
                  f"현재 상태 {loop['status']!r} 에서는 기록하지 않는다.", file=sys.stderr)
            print("   루프를 닫으려면 reviewer/qa 판정을 기록하십시오.", file=sys.stderr)
            return 1
        loop["escalation_acked"] = {"by": args.grader, "at": _now(),
                                    "note": attempt.get("notes", "")}
        loop["status"] = "in-loop"
    elif args.verdict in ("pass", "fail"):
        # 에스컬레이션 상태에서 판정을 닫으려면 **누가 왜 재검토했는지**를 받는다.
        # 예전엔 3회 revision → escalated → 다음 pass 로 그냥 통과했다. 배너만
        # 찍히고 아무것도 막지 않아, ADR-014 가 선언한 "유계" 에 대응물이 없었다
        # (F019 는 escalated 직후 pass, 재검토 기록 0건).
        if loop["status"] == "escalated" and not getattr(args, "ack_escalation", None):
            print(f"[verify-loop] ❌ {feature} 는 에스컬레이션 상태다 "
                  f"(revision {loop['revision_count']}/{loop['escalation_threshold']}).",
                  file=sys.stderr)
            print("   Planner+Architect 재검토 없이 닫지 않는다. 재검토를 마쳤으면:",
                  file=sys.stderr)
            print(f"   --ack-escalation \"<누가/무엇을 결정했는지>\"", file=sys.stderr)
            return 1
        if getattr(args, "ack_escalation", None):
            loop["escalation_acked"] = {"by": args.grader, "at": _now(),
                                        "note": args.ack_escalation[:500]}
        loop["status"] = "passed" if args.verdict == "pass" else "failed"
    elif loop["revision_count"] >= loop["escalation_threshold"]:
        if loop["status"] != "escalated":
            loop["escalated_at"] = _now()   # 언제 넘었는지 — 없으면 "재검토 대기" 인지 알 수 없다
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
        since = loop.get("escalated_at", "?")
        print(f"  🚨 ESCALATION — NEEDS REVISION {loop['revision_count']}회 도달 "
              f"(임계 {loop['escalation_threshold']}, {since} 부터).")
        print("     Planner+Architect 재검토 필요 · Feature 분해 검토 · /project:learn add (pitfall).")
        print("     재검토를 마쳤으면 판정에 --ack-escalation \"<누가/무엇을>\" 을 붙이십시오.")
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
    gates = loop.get("gates_passed")
    if gates:
        print(f"    통과한 결정론 게이트: {', '.join(gates)}")
    for a in loop["attempts"]:
        extra = ""
        if "must" in a:
            extra = f" (MUST {a['must']}, SHOULD {a.get('should','?')})"
        if a.get("notes"):
            extra += f" — {a['notes']}"
        print(f"    #{a.get('n','?')} {a.get('grader','?')}({a.get('kind','?')}) "
              f"→ {a.get('verdict','?')}{extra}")


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
    # `_read_loop` 를 쓴다 — 손상 파일 1건에 목록 전체가 죽으면 정상 루프까지 못 본다.
    # 방어가 두 주소에 흩어지면 하나만 고치게 된다 (이 리포가 일곱 번 겪은 일).
    loops = [lp for lp in (_read_loop(p) for p in sorted(_STATE.glob("*.json"))) if lp]
    print(f"[verify-loop] 루프 {len(loops)}개")
    for loop in loops:
        _print_loop(loop)
    return 0


def cmd_rubric(args) -> int:
    """rubric 을 표시하거나 목록을 나열한다."""
    if args.name:
        rf = _RUBRICS / f"{_safe_name(args.name, 'rubric 이름')}.md"
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
    p_start.add_argument("--force", action="store_true",
                         help="기존 루프가 있어도 이력을 지우고 새로 개시")

    p_rec = sub.add_parser("record", help="grader 판정 기록")
    p_rec.add_argument("feature", help="Feature ID")
    p_rec.add_argument("--grader", required=True, help="grader 이름 (lint|design-review|qa-browser|reviewer|qa …)")
    p_rec.add_argument("--verdict", required=True, help="pass|revision|fail")
    p_rec.add_argument("--must", type=int, help="MUST 미해결 건수 (judge grader)")
    p_rec.add_argument("--should", type=int, help="SHOULD 건수 (judge grader)")
    p_rec.add_argument("--notes", help="판정 메모")
    p_rec.add_argument("--rubric", help="루프 미개시 시 자동 개시할 rubric")
    p_rec.add_argument("--ack-escalation", metavar="WHO/WHAT",
                       help="에스컬레이션 재검토 완료 표시 (escalated 상태에서 pass|fail 에 필요)")

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
