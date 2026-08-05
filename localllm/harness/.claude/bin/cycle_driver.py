#!/usr/bin/env python3
"""
cycle_driver.py — 로컬 결정론 supervisor: SDLC 사이클 상태 기계 (localllm 전용, d-2)

측정 05/06 의 결론을 코드화한다 (ADR-018):
  - LLM 이 문맥으로 흐름을 조율(G5)하는 것은 32B 도 실패 → **흐름은 코드가 소유**
  - 로컬 LLM 은 역할 단위로만 호출: developer(생성, 14B) / reviewer·qa(판정, 32B)
  - 값 전달은 전부 드라이버가 파일·인자로 주입 (LLM 문맥 전달 배제)
  - grader 는 결정론 (테스트 실행 + 기대 출력 확인 — 공허 통과 차단)
  - 재작업 지시는 전체 파일 재작성 + 실패 출력 + 현재 파일 내용 주입 (AGENTS.md 규칙 6)
  - 판정 역할은 bash-only 파일 접근 (AGENTS.md 규칙 7) + 기록 여부를 드라이버가 검증
  - verify-loop 상태로 유계 재시도 — 에스컬레이션 도달 시 상위 호스트로 인계 (exit 2)

이로써 supervisor(핸드오프·grader·북키핑)가 **로컬 머신에서 무인 실행**된다.
상위 호스트(Claude Code/사람)는 에스컬레이션 시에만 개입한다.

사용법:
  python3 .claude/bin/cycle_driver.py run F001 \
      --test-cmd "python3 test_fizzbuzz.py" --expect PASS \
      --files fizzbuzz.py,test_fizzbuzz.py
  python3 .claude/bin/cycle_driver.py self       # 의존성 점검 (opencode/모델/verify_loop)

외부 의존성: OpenCode CLI (d-2 실행 환경) — 미설치 시 안내 후 exit 0 (graceful degrade).
드라이버 자체는 Python stdlib only.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


def _project_root() -> Path:
    """하네스 루트를 반환한다 (스크립트 위치 기준 — session_search.py 와 동일 규약)."""
    env = os.environ.get("CLAUDE_PROJECT_DIR")
    if env and Path(env).is_dir():
        return Path(env)
    return Path(__file__).resolve().parent.parent.parent


_ROOT = _project_root()
_VL = _ROOT / ".claude" / "bin" / "verify_loop.py"
_STATE_DIR = _ROOT / ".claude" / "state" / "verify-loop"
_OC_TIMEOUT = int(os.environ.get("CYCLE_OC_TIMEOUT", "420"))


def _log(msg: str) -> None:
    """드라이버 진행 로그를 출력한다 (단계 prefix 규약)."""
    print(f"[cycle-driver] {msg}", flush=True)


def _opencode_run(agent: str | None, prompt: str, model: str | None = None) -> tuple[int, str]:
    """
    opencode run 을 실행한다. 부트스트랩 간헐 행(측정 06) 대응으로 timeout + 1회 재시도.

    Returns:
        (returncode, 표준출력+표준에러 결합 텍스트). 두 번 모두 timeout 이면 (124, "").
    """
    cmd = ["opencode", "run"]
    # --pure: 외부 플러그인 해석(네트워크) 생략 — 부트스트랩 간헐 행의 원인 구간 제거 (측정 07).
    # 하네스는 OpenCode 플러그인을 사용하지 않으므로 밀폐 실행이 안전 기본값.
    if os.environ.get("CYCLE_OC_PURE", "1") != "0":
        cmd.append("--pure")
    if agent:
        cmd += ["--agent", agent]
    if model:
        cmd += ["-m", model]
    cmd.append(prompt)
    for attempt in (1, 2):
        try:
            r = subprocess.run(
                cmd, cwd=_ROOT, capture_output=True, text=True, timeout=_OC_TIMEOUT
            )
            return r.returncode, (r.stdout or "") + (r.stderr or "")
        except subprocess.TimeoutExpired:
            _log(f"  ⚠️ opencode timeout ({_OC_TIMEOUT}s) — {'10초 후 재시도' if attempt == 1 else '포기'}")
            if attempt == 1:
                import time
                time.sleep(10)
    return 124, ""


def _vl(args: list[str]) -> str:
    """verify_loop.py 서브커맨드를 실행하고 출력을 반환한다."""
    r = subprocess.run(
        [sys.executable, str(_VL)] + args, cwd=_ROOT, capture_output=True, text=True
    )
    return (r.stdout or "") + (r.stderr or "")


def _vl_state(feature: str) -> dict:
    """verify-loop 상태 JSON 을 읽는다 (없으면 빈 dict)."""
    p = _STATE_DIR / f"{feature}.json"
    if not p.is_file():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except ValueError:
        return {}


def _judge_recorded(feature: str, grader: str, before_n: int) -> str | None:
    """judge 가 새 판정을 기록했는지 검증한다. 기록됐으면 verdict, 아니면 None."""
    for a in _vl_state(feature).get("attempts", []):
        if a.get("n", 0) > before_n and a.get("grader") == grader:
            return a.get("verdict")
    return None


def _grade(test_cmd: str, expect: str | None) -> tuple[bool, str]:
    """결정론 grader: 테스트 명령 실행 — exit 0 + 기대 출력 확인 (공허 통과 차단)."""
    r = subprocess.run(
        test_cmd, shell=True, cwd=_ROOT, capture_output=True, text=True, timeout=120
    )
    out = (r.stdout or "") + (r.stderr or "")
    ok = r.returncode == 0 and (expect is None or expect in out)
    return ok, out.strip()[-800:]


def _files_context(files: list[str]) -> str:
    """재작업 프롬프트에 주입할 현재 파일 내용을 구성한다 (드라이버가 값 주입 — LLM 문맥 전달 배제)."""
    chunks = []
    for f in files:
        p = _ROOT / f
        body = p.read_text(encoding="utf-8") if p.is_file() else "(파일 없음)"
        chunks.append(f"--- current content of {f} ---\n{body}")
    return "\n".join(chunks)


def cmd_run(args) -> int:
    """SDLC 사이클 상태 기계: develop → grade(재시도) → review → qa → bookkeep."""
    feature = args.feature
    files = [f.strip() for f in args.files.split(",")] if args.files else []

    # 대상 feature 로드
    fl_path = _ROOT / "feature_list.json"
    fl = json.loads(fl_path.read_text(encoding="utf-8"))
    feats = fl["features"] if isinstance(fl, dict) else fl
    feat = next((f for f in feats if f.get("id") == feature), None)
    if feat is None:
        _log(f"❌ {feature} 가 feature_list.json 에 없음")
        return 1
    criteria = "\n".join(f"- {c}" for c in feat.get("acceptance_criteria", []))

    # verify-loop 개시 (이미 있으면 이어감)
    if not _vl_state(feature):
        _vl(["start", feature, "--rubric", "code-review"])
    _log(f"▶ {feature} {feat.get('title', '')} — 사이클 시작 (grader: `{args.test_cmd}`)")

    # ── GRADE-FIRST (멱등 재개) ────────────────────────────────
    # 결정론 게이트가 이미 통과하면 생성 모델을 호출하지 않는다 (측정 07 교훈:
    # 재개 시 무조건 구현부터 부르면 14B 가 멀쩡한 산출물을 다시 망가뜨린다).
    ok, _out = _grade(args.test_cmd, args.expect)
    if ok:
        _log("① grader 선통과 — 구현 단계 생략 (재개/멱등)")
    else:
        # ── DEVELOP ────────────────────────────────────────────
        dev_prompt = (
            f"Implement feature {feature}: {feat.get('title', '')}.\n"
            f"Acceptance criteria:\n{criteria}\n"
            "Create the files in the current directory with exact relative filenames "
            "(no leading slash, no directories). Reply DONE when all files exist."
        )
        _log("① developer(생성형) 구현 호출")
        rc, _ = _opencode_run("developer", dev_prompt)
        if rc == 124:
            _log("❌ developer 호출 실패 (연속 timeout) — 중단")
            return 1

    # ── GRADE + REVISE 루프 (verify-loop 가 유계·에스컬레이션 관리) ──
    while True:
        ok, out = _grade(args.test_cmd, args.expect)
        if ok:
            _vl(["record", feature, "--grader", "test", "--verdict", "pass",
                 "--notes", "결정론 grader 통과 (exit 0 + 기대 출력)"])
            _log("② grader PASS")
            break
        _vl(["record", feature, "--grader", "test", "--verdict", "revision",
             "--notes", f"grader 실패: {out[:120]}"])
        state = _vl_state(feature)
        revisions = sum(1 for a in state.get("attempts", []) if a.get("verdict") == "revision")
        _log(f"② grader FAIL (revision {revisions}) — 출력: {out[:100]}")
        if state.get("escalated") or revisions >= args.max_revisions:
            _log(f"🚨 에스컬레이션 — 상위 호스트(사람/Claude Code) 인계 필요. "
                 f"상태: python3 .claude/bin/verify_loop.py status {feature}")
            return 2
        # 재작업 = 전체 파일 재작성 (규칙 6) — 실패 출력 + 현재 내용을 드라이버가 주입
        revise_prompt = (
            f"The implementation of {feature} fails its test.\n"
            f"Test command: {args.test_cmd}\nTest output:\n{out}\n\n"
            f"{_files_context(files)}\n\n"
            "Identify the buggy file and REWRITE that file COMPLETELY with corrected "
            "content (do not use partial edits). Use the exact relative filename. Reply DONE."
        )
        _log("  ↻ developer 재작업 (전체 파일 재작성 지시)")
        rc, _ = _opencode_run("developer", revise_prompt)
        if rc == 124:
            _log("❌ developer 재작업 호출 실패 — 중단")
            return 1

    # ── REVIEW / QA (판정은 로컬 32B judge — bash-only, 기록 여부는 드라이버가 검증) ──
    for role, ask in (
        ("reviewer", "judge code quality, correctness and test coverage"),
        ("qa", "verify every acceptance criterion is met"),
    ):
        before_n = max((a.get("n", 0) for a in _vl_state(feature).get("attempts", [])), default=0)
        judge_prompt = (
            f"You must {ask} for feature {feature} using ONLY the bash tool "
            f"(never the read tool).\n"
            f"Step 1: run bash: cat {' '.join(files)}\n"
            f"Step 2: run bash: {args.test_cmd}\n"
            f"Acceptance criteria:\n{criteria}\n"
            f"Step 3: record your verdict via bash (fill notes with a concrete finding):\n"
            f"python3 .claude/bin/verify_loop.py record {feature} --grader {role} "
            f"--verdict pass --notes '<your concrete finding>'\n"
            f"(use --verdict revision instead if you found a must-fix issue)\n"
            f"Reply PASS or NEEDS REVISION with one sentence."
        )
        _log(f"③ {role}(judge, 32B) 판정 호출")
        for attempt in (1, 2):
            _opencode_run(role, judge_prompt)
            verdict = _judge_recorded(feature, role, before_n)
            if verdict:
                break
            _log(f"  ⚠️ {role} 판정 미기록 — {'재시도' if attempt == 1 else '중단'}")
        if not verdict:
            _log(f"❌ {role} 가 판정을 기록하지 않음 — 상위 호스트 인계 (exit 2)")
            return 2
        _log(f"  {role} verdict: {verdict}")
        if verdict != "pass":
            _log(f"🔄 {role} NEEDS REVISION — 재작업 루프는 상위 호스트/재실행으로 (exit 3)")
            return 3

    # ── BOOKKEEP (supervisor 북키핑 — QA pass 근거로 상태 반영) ──
    feat["passes"] = True
    feat["status"] = "done"
    fl_path.write_text(json.dumps(fl, ensure_ascii=False, indent=2), encoding="utf-8")
    prog = _ROOT / "claude-progress.txt"
    with prog.open("a", encoding="utf-8") as fh:
        fh.write(f"\n## cycle-driver | {feature} PASSED — dev(14B)+judge(32B) 로컬 무인 사이클, "
                 f"verify-loop {len(_vl_state(feature).get('attempts', []))}기록\n")
    if (_ROOT / ".git").exists():
        subprocess.run(["git", "add", "-A"], cwd=_ROOT, capture_output=True)
        subprocess.run(["git", "commit", "-m",
                        f"feat({feature}): 로컬 무인 사이클 완료 (cycle_driver — dev 14B + judge 32B)"],
                       cwd=_ROOT, capture_output=True)
    _log(f"✅ {feature} 완료 — passes:true, status:done, 커밋 기록")
    return 0


def cmd_self(args) -> int:
    """의존성 점검: opencode CLI / verify_loop / feature_list / 모델 설정."""
    print("[cycle-driver] ── self check ──")
    oc = shutil.which("opencode")
    print(f"  opencode CLI: {'PASS — ' + oc if oc else 'FAIL (미설치 — opencode-setup.sh 참조)'}")
    print(f"  verify_loop.py: {'PASS' if _VL.is_file() else 'FAIL'}")
    print(f"  feature_list.json: {'PASS' if (_ROOT / 'feature_list.json').is_file() else 'FAIL'}")
    ocj = _ROOT / "opencode.json"
    print(f"  opencode.json (역할별 모델): {'PASS' if ocj.is_file() else 'CONCERN (전역 설정만 사용)'}")
    return 0


def main() -> None:
    """CLI 엔트리포인트."""
    parser = argparse.ArgumentParser(description="로컬 결정론 supervisor — SDLC 사이클 드라이버 (localllm 전용)")
    sub = parser.add_subparsers(dest="command")
    p_run = sub.add_parser("run", help="feature 하나를 사이클로 실행")
    p_run.add_argument("feature", help="feature ID (예: F001)")
    p_run.add_argument("--test-cmd", required=True, help="결정론 grader 명령 (예: 'python3 test_x.py')")
    p_run.add_argument("--expect", default=None, help="grader 기대 출력 문자열 (공허 통과 차단)")
    p_run.add_argument("--files", default="", help="대상 파일 목록 (쉼표 구분 — 재작업 주입·judge cat 용)")
    p_run.add_argument("--max-revisions", type=int, default=3, help="에스컬레이션 임계 (기본 3)")
    sub.add_parser("self", help="의존성 점검")
    args = parser.parse_args()
    if args.command == "run":
        sys.exit(cmd_run(args))
    cmd_self(args)


if __name__ == "__main__":
    main()
