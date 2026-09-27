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


class VerifyLoopReReviewTest(unittest.TestCase):
    """재리뷰(F020 2차)가 실측으로 찾은 MUST 4건 + SHOULD 2건.

    1차 수정이 남긴 것들이다. 공통점은 **방어가 한쪽에만 걸렸다**는 것 —
    `_safe_name` 은 feature 에만, 형태 검증은 `attempts` 에만, 격리는 파싱 오류에만.
    이 리포가 아홉 번 겪은 그 결함 클래스가 수정 자신에게도 일어났다.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / ".claude" / "rubrics").mkdir(parents=True)
        (self.root / ".claude" / "rubrics" / "code-review.md").write_text("# rubric", encoding="utf-8")
        (self.root / "LEAK.md").write_text("비밀", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    @property
    def _state(self) -> Path:
        return self.root / ".claude" / "state" / "verify-loop"

    def _write(self, name: str, body: str) -> None:
        self._state.mkdir(parents=True, exist_ok=True)
        (self._state / name).write_text(body, encoding="utf-8")

    def test_rubric_이름도_경로_성분_검증을_받는다(self):
        """커밋 1731d3e 는 "rubric 이름도 같은 검증" 이라 적었지만 feature 에만 걸려 있었다."""
        for bad in ("../../LEAK", "..", "a/b", "x" * 100):
            with self.subTest(rubric=bad):
                res = _run(self.root, _BIN, "start", "F001", "--rubric", bad)
                self.assertNotEqual(res.returncode, 0, f"{bad!r} 가 통과했다")
        # `rubric` 하위명령도 같은 경로로 읽는다 — 한쪽만 막으면 의미가 없다
        res = _run(self.root, _BIN, "rubric", "../../LEAK")
        self.assertNotEqual(res.returncode, 0)
        self.assertNotIn("비밀", res.stdout, "rubrics 디렉토리 밖 파일이 출력됐다")

    def test_미등록_grader_는_judge_로_승격되지_않고_거부된다(self):
        """`--grader Lint` 오타 하나로 judge pass 가 되어 루프를 통과했다 (fail-open)."""
        for typo in ("Lint", "lnt", "qa_browser", "reviewer2"):
            with self.subTest(grader=typo):
                res = _run(self.root, _BIN, "record", "F010", "--grader", typo, "--verdict", "pass")
                self.assertNotEqual(res.returncode, 0, f"{typo!r} 가 기록됐다")
        self.assertFalse((self._state / "F010.json").exists(),
                         "거부했는데 상태 파일이 만들어졌다 — 부작용이 검증보다 앞섰다")

    def test_feature_키가_파일명과_다르면_파일명을_따른다(self):
        """내용의 `feature` 를 믿으면 락은 F001 인데 쓰기는 F002 로 간다 (교차 lost update)."""
        self._write("F001.json", json.dumps({"feature": "F002", "attempts": [], "revision_count": 0}))
        res = _run(self.root, _BIN, "record", "F001", "--grader", "reviewer", "--verdict", "revision")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertFalse((self._state / "F002.json").exists(), "다른 feature 파일로 기록이 샜다")
        loop = json.loads((self._state / "F001.json").read_text(encoding="utf-8"))
        self.assertEqual(len(loop["attempts"]), 1, "원본이 갱신되지 않았다")
        self.assertEqual(loop["feature"], "F001")

    def test_카운터_타입이_틀려도_영구_wedge_가_되지_않는다(self):
        """`revision_count: "3"` 이면 `+= 1` 이 매 record 마다 TypeError 로 죽었다."""
        poisons = {
            "count-str": {"attempts": [], "revision_count": "3"},
            "count-none": {"attempts": [], "revision_count": None},
            "count-bool": {"attempts": [], "revision_count": True},
            "thr-none": {"attempts": [], "escalation_threshold": None},
            "thr-zero": {"attempts": [], "escalation_threshold": 0},
            "status-bogus": {"attempts": [], "status": "완전히 이상한 값"},
            "rubric-int": {"attempts": [], "rubric": 7},
        }
        for label, body in poisons.items():
            with self.subTest(poison=label):
                fid = f"F{abs(hash(label)) % 900 + 100}"
                self._write(f"{fid}.json", json.dumps(body))
                for round_n in (1, 2):   # 2회차까지 봐야 "영구" wedge 가 드러난다
                    res = _run(self.root, _BIN, "record", fid,
                               "--grader", "reviewer", "--verdict", "revision")
                    self.assertEqual(res.returncode, 0,
                                     f"{label} {round_n}회차에서 죽었다: {res.stdout}{res.stderr}")

    def test_필수키가_없는_attempt_가_목록을_죽이지_않는다(self):
        """`_print_loop` 가 `a['n']` 을 직접 첨자해서, 원소 하나에 list 전체가 죽었다."""
        self._write("F020.json", json.dumps(
            {"attempts": [{}, {"n": 1}, {"n": 2, "grader": "reviewer", "kind": "judge",
                                         "verdict": "pass"}]}))
        self._write("F021.json", json.dumps({"attempts": [], "revision_count": 0}))
        res = _run(self.root, _BIN, "list")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertIn("F021", res.stdout, "정상 루프가 가려졌다")
        self.assertIn("F020", res.stdout)

    def test_형태_오류_파일도_덮어쓰지_않고_격리한다(self):
        """격리가 파싱 오류에만 걸려서, 파싱되는 비정형은 자동 start 가 **덮어썼다**."""
        self._write("F030.json", json.dumps({"attempts": "x", "precious": "지워지면 안 되는 이력"}))
        res = _run(self.root, _BIN, "record", "F030", "--grader", "reviewer", "--verdict", "revision")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        saved = list(self._state.glob("F030.json.corrupt-*"))
        self.assertEqual(len(saved), 1, f"형태 오류가 보존되지 않았다: {list(self._state.iterdir())}")
        self.assertIn("precious", saved[0].read_text(encoding="utf-8"), "보존본에 원본이 없다")

    def test_기존_루프를_start_가_조용히_리셋하지_않는다(self):
        """에스컬레이션 직전 카운터를 0 으로 되돌리는 판정 위조 경로였다."""
        _run(self.root, _BIN, "start", "F040")
        for _ in range(2):
            _run(self.root, _BIN, "record", "F040", "--grader", "reviewer", "--verdict", "revision")
        res = _run(self.root, _BIN, "start", "F040")
        self.assertNotEqual(res.returncode, 0, "기존 이력을 조용히 덮어썼다")
        loop = json.loads((self._state / "F040.json").read_text(encoding="utf-8"))
        self.assertEqual(loop["revision_count"], 2, "이력이 사라졌다")
        # --force 는 명시적 의사표시이므로 허용한다
        self.assertEqual(_run(self.root, _BIN, "start", "F040", "--force").returncode, 0)
        loop = json.loads((self._state / "F040.json").read_text(encoding="utf-8"))
        self.assertEqual(loop["revision_count"], 0, "--force 가 리셋하지 않았다")

    def test_결정론_grader_의_fail_은_설계거부가_아니다(self):
        """lint 실패를 `failed`(Planner·Architect 재설계)로 올리는 건 과하다.

        pass 는 judge 만 인정하면서 fail 은 결정론도 인정하던 비대칭을 없앤다.
        """
        _run(self.root, _BIN, "start", "F050")
        _run(self.root, _BIN, "record", "F050", "--grader", "lint", "--verdict", "fail")
        loop = json.loads((self._state / "F050.json").read_text(encoding="utf-8"))
        self.assertEqual(loop["status"], "in-loop",
                         "결정론 게이트 실패가 루프를 REJECTED 로 만들었다")
        # judge 의 fail 은 여전히 설계 거부다
        _run(self.root, _BIN, "record", "F050", "--grader", "reviewer", "--verdict", "fail")
        loop = json.loads((self._state / "F050.json").read_text(encoding="utf-8"))
        self.assertEqual(loop["status"], "failed")


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
