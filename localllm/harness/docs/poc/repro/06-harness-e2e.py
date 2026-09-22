#!/usr/bin/env python3
"""
06-harness-e2e.py — 측정 06(통합 테스트 01)의 **재현 스크립트**.

측정 06 은 2026-08-05 에 사람이 상위 호스트에서 수동으로 돌린 하이브리드 세션이었고,
그 세션의 샌드박스·프롬프트·verify-loop 상태가 **하나도 보존되지 않았다**. 문서만 남아
"풀사이클 완주"를 주장했다 (F024 리뷰 MUST). 이 스크립트는 같은 시나리오(F001 fizzbuzz)를
`cycle_driver` 로 무인 재현하고, 산출물을 `docs/poc/artifacts/06/` 에 **보존**한다.

원본과의 차이는 정직하게 적는다:
  - 원본: 사람이 핸드오프·grader 정의·북키핑을 담당한 하이브리드
  - 재현: `cycle_driver`(F025) 가 그 supervisor 역할을 결정론으로 수행
  즉 재현은 원본을 복제하지 않는다. 원본이 주장한 **결론**(로컬 티어가 SDLC 사이클을
  완주할 수 있다)이 재현 가능한지를 확인할 뿐이다.

사용법:
  python3 docs/poc/repro/06-harness-e2e.py            # 재현 + artifact 보존
  REPRO_SANDBOX=/tmp/x python3 docs/poc/repro/06-harness-e2e.py
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPRO_DIR = Path(__file__).resolve().parent
# 하네스 루트 = docs/poc/repro/06-harness-e2e.py → <harness>
HARNESS = REPRO_DIR.parent.parent.parent
ARTIFACTS = HARNESS / "docs/poc/artifacts/06"
DRIVER_TIMEOUT = int(os.environ.get("REPRO_TIMEOUT", "1800"))

# 측정 06 의 시나리오: F001 fizzbuzz CLI.
# AC 3번이 **호출까지** 요구하는 것이 핵심이다 — 원본에서 14B 가 테스트를 정의만 하고
# 호출하지 않아 "공허 통과(vacuous pass)"가 났고, 그게 규율 1(기대 출력 확인)의 근거였다.
FEATURE = {
    "id": "F001",
    "title": "fizzbuzz — fizzbuzz.py",
    "priority": "high",
    "status": "todo",
    "passes": False,
    "dependencies": [],
    "acceptance_criteria": [
        "fizzbuzz.py 에 fizzbuzz(n) 함수: 3 배수 'Fizz', 5 배수 'Buzz', 15 배수 'FizzBuzz', "
        "나머지는 str(n) 을 반환, docstring 포함",
        "test_fizzbuzz.py: fizzbuzz(3)=='Fizz', fizzbuzz(5)=='Buzz', fizzbuzz(15)=='FizzBuzz', "
        "fizzbuzz(7)=='7' assert 후 print('PASS'); 파일 끝에 if __name__ == '__main__': 로 테스트 함수 호출",
        "python3 test_fizzbuzz.py 가 exit 0 + PASS 출력",
    ],
}
TEST_CMD = "python3 test_fizzbuzz.py"
EXPECT = "PASS"
FILES = "fizzbuzz.py,test_fizzbuzz.py"


def _preflight() -> None:
    """스위트와 같은 전제를 확인한다 — 없으면 조용한 INFRA 대신 안내하고 멈춘다."""
    missing = [t for t in ("opencode", "rsync", "git") if shutil.which(t) is None]
    if missing:
        raise SystemExit(
            "재현 전제가 없습니다: " + ", ".join(missing) + "\n"
            "  opencode: bash .claude/bin/opencode-setup.sh\n"
            "  rsync·git: 배포판 패키지 매니저\n"
            "  (이 스크립트는 로컬 LLM 을 실제로 호출합니다 — Ollama 도 떠 있어야 합니다)"
        )


def _sandbox() -> Path:
    """샌드박스를 초기화한다. 템플릿 내부면 rsync 가 자기 자신을 재귀 복사한다."""
    root = Path(os.environ.get(
        "REPRO_SANDBOX", Path(tempfile.gettempdir()) / "harness-repro-06")).resolve()
    tpl = HARNESS.resolve()
    if tpl == root or tpl in root.parents:
        raise SystemExit(
            f"REPRO_SANDBOX 가 하네스 내부입니다 — 재귀 복사 방지\n"
            f"  harness={tpl}\n  sandbox={root}"
        )
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)
    subprocess.run([
        "rsync", "-a", "--exclude=__pycache__", "--exclude=.claude/state/sessions.db",
        "--exclude=.claude/state/lint-last.json", "--exclude=.claude/state/verify-loop/",
        f"{HARNESS}/", f"{root}/",
    ], check=True, capture_output=True)
    (root / ".claude/state/verify-loop").mkdir(parents=True, exist_ok=True)
    fl = {"project": "repro-06", "features": [FEATURE]}
    (root / "feature_list.json").write_text(
        json.dumps(fl, ensure_ascii=False, indent=2), encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=root, capture_output=True)
    subprocess.run(["git", "add", "-A"], cwd=root, capture_output=True)
    subprocess.run(["git", "commit", "-qm", "chore: repro-06 seed"], cwd=root, capture_output=True)
    return root


def _drive(sb: Path) -> tuple[int, str, float]:
    """cycle_driver 를 무인 실행하고 (exit, 로그, 소요초) 를 반환한다."""
    cmd = [
        sys.executable, ".claude/bin/cycle_driver.py", "run", "F001",
        "--test-cmd", TEST_CMD, "--expect", EXPECT, "--files", FILES,
    ]
    t0 = time.time()
    try:
        r = subprocess.run(cmd, cwd=sb, capture_output=True, text=True, timeout=DRIVER_TIMEOUT)
        return r.returncode, (r.stdout or "") + (r.stderr or ""), time.time() - t0
    except subprocess.TimeoutExpired as exc:
        out = exc.stdout or b""
        if isinstance(out, bytes):
            out = out.decode(errors="replace")
        return 124, f"REPRO-TIMEOUT {DRIVER_TIMEOUT}s\n{out}", time.time() - t0


def _ground_truth(sb: Path) -> tuple[bool, str]:
    """드라이버 주장을 믿지 않고 테스트를 독립 실행한다 (스위트 oracle O2 와 같은 규율)."""
    try:
        r = subprocess.run(TEST_CMD, shell=True, cwd=sb, capture_output=True,
                           text=True, timeout=120)
        out = (r.stdout or "") + (r.stderr or "")
        return r.returncode == 0 and EXPECT in out, out.strip()[-400:]
    except subprocess.TimeoutExpired:
        return False, "ground-truth timeout"


def _preserve(sb: Path, rc: int, log: str, elapsed: float) -> dict:
    """산출물을 리포 안에 보존한다 — 이게 이 스크립트의 존재 이유다."""
    if ARTIFACTS.exists():
        shutil.rmtree(ARTIFACTS)
    ARTIFACTS.mkdir(parents=True)
    (ARTIFACTS / "driver.log").write_text(log, encoding="utf-8")

    vl_src = sb / ".claude/state/verify-loop/F001.json"
    vl: dict = {}
    if vl_src.is_file():
        shutil.copy2(vl_src, ARTIFACTS / "verify-loop-F001.json")
        try:
            vl = json.loads(vl_src.read_text(encoding="utf-8"))
        except ValueError:
            vl = {}

    produced = ARTIFACTS / "produced"
    produced.mkdir()
    for rel in FILES.split(","):
        src = sb / rel.strip()
        if src.is_file():
            shutil.copy2(src, produced / src.name)

    fl_path = sb / "feature_list.json"
    passes = None
    if fl_path.is_file():
        shutil.copy2(fl_path, ARTIFACTS / "feature_list.json")
        try:
            feats = json.loads(fl_path.read_text(encoding="utf-8")).get("features", [])
            passes = next((f.get("passes") for f in feats if f.get("id") == "F001"), None)
        except ValueError:
            pass

    truth, truth_out = _ground_truth(sb)
    judges = [a for a in vl.get("attempts", []) if a.get("kind") == "judge"]
    summary = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "scenario": "측정 06 재현 — F001 fizzbuzz",
        "driver_exit": rc,
        "elapsed_sec": round(elapsed, 1),
        "verify_loop_status": vl.get("status"),
        "verify_loop_attempts": len(vl.get("attempts", [])),
        "judge_verdicts": [a.get("verdict") for a in judges],
        "revision_count": vl.get("revision_count"),
        "ground_truth_pass": truth,
        "ground_truth_output": truth_out,
        "feature_passes": passes,
        # 거짓 결과: judge 가 pass 를 기록했는데 독립 실행은 실패 (스위트 oracle O3)
        "false_pass": bool(judges) and judges[-1].get("verdict") == "pass" and not truth,
        "sandbox": str(sb),
    }
    (ARTIFACTS / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return summary


def main() -> int:
    _preflight()
    sb = _sandbox()
    print(f"[repro-06] 샌드박스: {sb}")
    rc, log, elapsed = _drive(sb)
    summary = _preserve(sb, rc, log, elapsed)
    print(f"[repro-06] 드라이버 exit={rc} ({elapsed:.0f}s)")
    print(f"[repro-06] verify-loop status={summary['verify_loop_status']} "
          f"judge={summary['judge_verdicts']}")
    print(f"[repro-06] ground truth={'PASS' if summary['ground_truth_pass'] else 'FAIL'} "
          f"passes={summary['feature_passes']}")
    if summary["false_pass"]:
        print("[repro-06] ❌ 거짓 결과 — judge pass 인데 독립 실행은 실패")
    print(f"[repro-06] artifact: {ARTIFACTS}")
    # 재현이 실패해도 artifact 는 남는다. 실패를 성공으로 만들지 않는 것이 이 스크립트의 요점이다.
    return 0 if (rc == 0 and summary["ground_truth_pass"] and not summary["false_pass"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
