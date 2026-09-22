#!/usr/bin/env python3
"""cycle_driver 의 **순수 함수 게이트**를 잠근다 (stdlib unittest, Ollama 불요).

왜 이 파일이 있는가 (F025·F026 리뷰):
  게이트 함수들(`_is_echo_note`·`_artifact_problems`·`_contradicts`·`_grade`…)은
  전부 순수 함수인데 단위 테스트가 **0건**이었다. 리뷰가 찾아낸 MUST 중 셋은
  "10줄짜리 테스트로 잡혔을" 것이다:
    · 초기 judge 루프가 placeholder 노트를 수용 → passes:true
    · grader 타임아웃 미처리 → 드라이버 traceback, revision 기록도 없음
    · `_vl_state` 가 비정형 attempts 에서 AttributeError

  그리고 이 드라이버는 **3 변형에 복제**돼 있다. 사본별 테스트를 만들면 한쪽에만
  케이스를 추가하고 끝나므로, 이 파일은 `CYCLE_DRIVER` 환경변수로 대상을 받아
  세 사본에 같은 목록을 태울 수 있게 했다.

실행:
    python3 tests/test_cycle_driver_gates.py
    CYCLE_DRIVER=../../localllm.nem/harness/.claude/bin/cycle_driver.py python3 tests/...
"""
import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path

_DEFAULT = Path(__file__).resolve().parent.parent / ".claude" / "bin" / "cycle_driver.py"
_TARGET = Path(os.environ.get("CYCLE_DRIVER", str(_DEFAULT))).resolve()


def _load():
    spec = importlib.util.spec_from_file_location("cycle_driver_under_test", _TARGET)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["cycle_driver_under_test"] = mod
    spec.loader.exec_module(mod)
    return mod


class EchoNoteTest(unittest.TestCase):
    """판정 노트가 프롬프트의 placeholder 를 베낀 것인지 (MUST-1)."""

    ECHOES = (
        "<your concrete finding>",
        "<the unmet criterion>",
        "<name the criterion and the evidence>",
        "  <your concrete finding>  ",
    )
    REAL = (
        "fizzbuzz() lacks a docstring (fizzbuzz.py:1)",
        "AC2 미충족 — 15 에서 FizzBuzz 대신 Fizz 를 반환한다",
    )

    def setUp(self):
        self.mod = _load()

    def test_placeholder_는_메아리로_판정된다(self):
        for note in self.ECHOES:
            with self.subTest(note=note[:30]):
                self.assertTrue(self.mod._is_echo_note(note), f"메아리를 못 잡았다: {note!r}")

    def test_구체적_노트는_메아리가_아니다(self):
        for note in self.REAL:
            with self.subTest(note=note[:30]):
                self.assertFalse(self.mod._is_echo_note(note), f"정상 노트를 메아리로 봤다: {note!r}")


class GradeTest(unittest.TestCase):
    """결정론 grader 의 공허 통과 차단과 타임아웃 (MUST-5)."""

    def setUp(self):
        self.mod = _load()

    def test_exit0_이지만_기대_출력이_없으면_실패다(self):
        ok, _out = self.mod._grade("true", "ALL PASS")
        self.assertFalse(ok, "exit 0 만으로 통과시켰다 — 공허 통과")

    def test_exit0_에_기대_출력이_있으면_통과다(self):
        ok, _out = self.mod._grade("echo ALL PASS", "ALL PASS")
        self.assertTrue(ok)

    def test_exit_비0_는_실패다(self):
        ok, _out = self.mod._grade("echo ALL PASS; exit 1", "ALL PASS")
        self.assertFalse(ok)

    def test_무한_루프는_타임아웃으로_판정된다(self):
        """예전에는 드라이버가 traceback 으로 죽고 revision 기록도 없었다.

        타임아웃이 120초라 여기서는 호출 자체를 대신하지 않고, 짧은 타임아웃으로
        같은 경로를 태운다.
        """
        import subprocess
        real = subprocess.run

        def boom(*a, **k):
            raise subprocess.TimeoutExpired(cmd="sleep", timeout=120)

        subprocess.run = boom
        try:
            ok, out = self.mod._grade("sleep 999", None)
        finally:
            subprocess.run = real
        self.assertFalse(ok)
        self.assertIn("timeout", out.lower())


class VlStateTest(unittest.TestCase):
    """비정형 루프 상태가 사이클을 중단시키지 않는지 (MUST-4)."""

    POISONS = ('{"attempts":[1,2]}', '{"attempts":"x"}', "[1,2]", "null",
               '{"attempts":[{"n":"1"}],"revision_count":"3"}')

    def setUp(self):
        self.mod = _load()

    def test_비정형_attempts_를_정규화한다(self):
        import json
        for poison in self.POISONS:
            with self.subTest(poison=poison[:20]):
                loop = self.mod._vl_norm(json.loads(poison))
                self.assertIsInstance(loop, dict)
                self.assertIsInstance(loop.get("attempts"), list)
                for a in loop["attempts"]:
                    self.assertIsInstance(a, dict, "비dict 원소가 남았다")
                self.assertIsInstance(loop.get("revision_count"), int)
                # 소비 패턴이 실제로 안전한지 — 드라이버가 매번 하는 연산이다
                max((a.get("n", 0) for a in loop["attempts"]), default=0)


class SafeRelTest(unittest.TestCase):
    """`--files` 경로가 프로젝트 루트를 벗어나지 못하는지 (SHOULD-1)."""

    def setUp(self):
        self.mod = _load()

    def test_루트_밖_경로는_거부된다(self):
        for bad in ("../outside.py", "../../etc/hostname", "/etc/hostname"):
            with self.subTest(path=bad):
                self.assertIsNone(self.mod._safe_rel(bad), f"{bad} 가 통과했다")

    def test_루트_안_경로는_허용된다(self):
        self.assertIsNotNone(self.mod._safe_rel("feature_list.json"))


class BookkeepTest(unittest.TestCase):
    """feature_list 갱신이 **다른 변경을 잃지 않는지** (MUST-2)."""

    def setUp(self):
        self.mod = _load()

    def test_사이_추가된_feature_가_사라지지_않는다(self):
        import json
        with tempfile.TemporaryDirectory() as d:
            fl = Path(d) / "feature_list.json"
            fl.write_text(json.dumps({"features": [
                {"id": "F001", "status": "review", "passes": False},
                {"id": "F999", "status": "todo", "passes": False},   # 사이에 추가된 것
            ]}, ensure_ascii=False), encoding="utf-8")
            self.assertTrue(self.mod._bookkeep_feature(fl, "F001"))
            data = json.loads(fl.read_text(encoding="utf-8"))
            ids = [f["id"] for f in data["features"]]
            self.assertIn("F999", ids, "사이에 추가된 feature 가 사라졌다")
            target = next(f for f in data["features"] if f["id"] == "F001")
            self.assertTrue(target["passes"])
            self.assertEqual(target["status"], "done")

    def test_없는_feature_는_False_를_돌려준다(self):
        import json
        with tempfile.TemporaryDirectory() as d:
            fl = Path(d) / "feature_list.json"
            fl.write_text(json.dumps({"features": []}), encoding="utf-8")
            self.assertFalse(self.mod._bookkeep_feature(fl, "F001"))

    def test_손상된_feature_list_에도_죽지_않는다(self):
        with tempfile.TemporaryDirectory() as d:
            fl = Path(d) / "feature_list.json"
            fl.write_text("{ torn", encoding="utf-8")
            self.assertFalse(self.mod._bookkeep_feature(fl, "F001"))


if __name__ == "__main__":
    print(f"대상: {_TARGET}")
    unittest.main(verbosity=2)
