#!/usr/bin/env python3
"""verify_loop.py / hill_climb.py 의 계약을 잠근다 (stdlib unittest).

왜 이 파일이 있는가 (F020 리뷰 MUST-1):
  ADR-014 와 체크포인트가 "mock E2E 로 검증함" 이라고 적었는데 **테스트가 0건**이었다.
  F019 1차 MUST 와 정확히 같은 결함 — 문서가 존재하지 않는 검증을 주장한 것이다.

  그 상태에서 리뷰가 실측으로 찾아낸 것들이 여기 전부 들어 있다:
  경로 탈출, 손상 파일 wedge, lost update, 결정론 grader 의 pass 가 루프를 통과시키던 것.

실행:
    python3 tests/test_verify_loop.py
"""
import contextlib
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_BIN = Path(__file__).resolve().parent.parent / ".claude" / "bin" / "verify_loop.py"
_HILL = Path(__file__).resolve().parent.parent / ".claude" / "bin" / "hill_climb.py"


def _run(root: Path, script: Path, *argv) -> subprocess.CompletedProcess:
    """실제 CLI 경로로 태운다 — 내부 함수를 직접 부르면 argparse 변화를 놓친다."""
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(root)}
    return subprocess.run([sys.executable, str(script), *argv],
                          capture_output=True, text=True, env=env, timeout=60)


class VerifyLoopContractTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / ".claude" / "rubrics").mkdir(parents=True)
        (self.root / ".claude" / "rubrics" / "code-review.md").write_text("# rubric", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    @property
    def _state(self) -> Path:
        return self.root / ".claude" / "state" / "verify-loop"

    def test_feature_id_가_상태_디렉토리를_벗어나지_못한다(self):
        """`start ../../pwn` 이 `.claude/pwn.json` 을 만들었다 (실측).

        F019 의 "원격 ts 가 파일명 선두" 와 같은 클래스다 — 경로 성분이 될 값은
        화이트리스트로 거른다.
        """
        for bad in ("../../pwn", "..", "", "a/b", "x" * 100):
            with self.subTest(feature=bad):
                res = _run(self.root, _BIN, "start", bad)
                self.assertNotEqual(res.returncode, 0, f"{bad!r} 가 통과했다")
        self.assertEqual(list(self.root.glob("**/pwn.json")), [], "상태 디렉토리 밖에 파일이 생겼다")

    def test_결정론_grader_의_pass_는_루프를_통과시키지_않는다(self):
        """`record --grader lint --verdict pass` 한 번에 `passed` 가 됐다 (실측).

        그게 하필 verify-loop.md·reviewer.md 가 권하는 **첫 단계**였다 —
        결정론 게이트 하나를 통과한 것과 판정이 끝난 것은 다르다.
        """
        _run(self.root, _BIN, "start", "F002")
        _run(self.root, _BIN, "record", "F002", "--grader", "lint", "--verdict", "pass")
        loop = json.loads((self._state / "F002.json").read_text(encoding="utf-8"))
        self.assertEqual(loop["status"], "in-loop", "결정론 pass 가 루프를 통과시켰다")
        self.assertIn("lint", loop.get("gates_passed", []))

        _run(self.root, _BIN, "record", "F002", "--grader", "reviewer", "--verdict", "pass")
        loop = json.loads((self._state / "F002.json").read_text(encoding="utf-8"))
        self.assertEqual(loop["status"], "passed", "judge pass 인데 통과하지 않았다")

    def test_손상된_상태_파일이_다른_루프를_막지_않는다(self):
        """손상 1건에 `status`·`record`·`list` 가 전부 죽었다 (실측)."""
        _run(self.root, _BIN, "start", "F001")
        for poison in ('{"feature":"F005","attempts":[{"n":1,', "[1,2]", "null", "", "[" * 100000):
            with self.subTest(poison=poison[:14]):
                (self._state / "F0BAD.json").write_text(poison, encoding="utf-8")
                res = _run(self.root, _BIN, "list")
                self.assertEqual(res.returncode, 0, f"list 가 죽었다: {res.stderr[:200]}")
                self.assertIn("F001", res.stdout, "정상 루프가 목록에서 사라졌다")
                self.assertNotIn("Traceback", res.stderr)

    def test_feature_키가_없는_상태_파일도_record_가_된다(self):
        """`_read_loop` 가 `feature` 를 채우지 않아 `_save` 가 KeyError 로 죽었다.

        내가 F020 에서 손상 방어를 넣을 때 만든 회귀다 — 형태 검증은 했는데
        **저장에 필요한 키**를 빠뜨렸다. 그 루프는 매 `record` 마다 죽어 영구 wedge 였다.
        """
        self._state.mkdir(parents=True, exist_ok=True)
        (self._state / "F009.json").write_text(
            json.dumps({"attempts": [], "revision_count": 0, "status": "in-loop"}),
            encoding="utf-8")
        for run in (1, 2):
            with self.subTest(run=run):
                res = _run(self.root, _BIN, "record", "F009",
                           "--grader", "reviewer", "--verdict", "revision")
                self.assertEqual(res.returncode, 0, f"{run}회차에 죽었다: {res.stderr[:200]}")
                self.assertNotIn("KeyError", res.stderr)
        loop = json.loads((self._state / "F009.json").read_text(encoding="utf-8"))
        self.assertEqual(len(loop["attempts"]), 2)
        self.assertEqual(loop["feature"], "F009", "파일명으로 feature 를 채우지 않았다")

    def test_revision_3회에_에스컬레이션한다(self):
        _run(self.root, _BIN, "start", "F003")
        for _ in range(3):
            _run(self.root, _BIN, "record", "F003", "--grader", "reviewer", "--verdict", "revision")
        loop = json.loads((self._state / "F003.json").read_text(encoding="utf-8"))
        self.assertEqual(loop["status"], "escalated")
        self.assertEqual(loop["revision_count"], 3)

    def test_동시_record_가_서로를_덮어쓰지_않는다(self):
        """reviewer·qa sub-agent 병렬 실행에서 20건 중 3건만 남았다 (실측)."""
        import concurrent.futures
        _run(self.root, _BIN, "start", "F100")
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
            list(pool.map(
                lambda i: _run(self.root, _BIN, "record", "F100", "--grader", "reviewer",
                               "--verdict", "revision", "--notes", f"c{i}"),
                range(20)))
        loop = json.loads((self._state / "F100.json").read_text(encoding="utf-8"))
        self.assertEqual(len(loop["attempts"]), 20, "lost update — 동시 기록이 유실됐다")
        self.assertEqual(sorted(a["n"] for a in loop["attempts"]), list(range(1, 21)))

    def test_잘못된_verdict_는_부작용_없이_거부된다(self):
        """검증 전에 자동 start 가 먼저 돌아 빈 상태 파일이 생겼다 (실측)."""
        res = _run(self.root, _BIN, "record", "F004", "--grader", "reviewer", "--verdict", "bogus")
        self.assertNotEqual(res.returncode, 0)
        self.assertFalse((self._state / "F004.json").exists(), "거부됐는데 상태 파일이 생겼다")

    def test_notes_의_제어문자가_출력에_그대로_나가지_않는다(self):
        _run(self.root, _BIN, "start", "F006")
        # 널바이트는 subprocess 가 거부하므로 CLI 로는 도달 불가 — 실제로 올 수 있는
        # 것(ANSI escape·개행·탭)만 건다. `status` 출력이 터미널에 그대로 렌더됐다.
        _run(self.root, _BIN, "record", "F006", "--grader", "reviewer", "--verdict", "revision",
             "--notes", "위험\x1b[31m빨강\n둘째줄\t탭")
        loop = json.loads((self._state / "F006.json").read_text(encoding="utf-8"))
        notes = loop["attempts"][0]["notes"]
        self.assertNotIn("\x1b", notes, "ANSI escape 가 그대로 저장됐다")
        self.assertNotIn("\n", notes, "개행이 그대로 저장됐다")

    def test_긴_notes_가_절단된다(self):
        _run(self.root, _BIN, "start", "F007")
        _run(self.root, _BIN, "record", "F007", "--grader", "reviewer", "--verdict", "revision",
             "--notes", "가" * 5000)
        loop = json.loads((self._state / "F007.json").read_text(encoding="utf-8"))
        self.assertLessEqual(len(loop["attempts"][0]["notes"]), 2100)


class HillClimbResilienceTest(unittest.TestCase):
    """비정형 트레이스 소스가 Loop 4 집계를 죽이지 않는지 (F020 MUST-5)."""

    POISON_LOOPS = ("[1,2]", "null", '"str"', '{"attempts":"x"}',
                    '{"attempts":[1,2],"revision_count":"3"}')
    POISON_ROWS = ("42", "null", "[1,2]", '{"event":"handoff","files_changed":true}')

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / ".claude" / "state" / "verify-loop").mkdir(parents=True)

    def tearDown(self):
        self.tmp.cleanup()

    def test_비정형_소스에도_집계가_죽지_않는다(self):
        state = self.root / ".claude" / "state"
        for loop_poison in self.POISON_LOOPS:
            for row_poison in self.POISON_ROWS:
                with self.subTest(loop=loop_poison[:14], row=row_poison[:14]):
                    (state / "verify-loop" / "F0BAD.json").write_text(loop_poison, encoding="utf-8")
                    (state / "analytics.jsonl").write_text(row_poison + "\n", encoding="utf-8")
                    res = _run(self.root, _HILL, "analyze")
                    self.assertEqual(res.returncode, 0,
                                     f"analyze 가 죽었다: {res.stderr[:200]}")
                    self.assertNotIn("Traceback", res.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
