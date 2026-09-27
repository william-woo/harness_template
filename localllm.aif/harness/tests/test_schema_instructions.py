#!/usr/bin/env python3
"""스키마 파생 지시 + VERDICT 폴백 + 검사기를 잠근다 (F031, stdlib unittest).

왜 이 파일이 있는가 (F031 리뷰 MUST-7):
  F031 의 명제는 "모델의 선의에 기대지 않는다 — 문자 그대로 따라도 성립하는 지시만
  쓴다" 인데, 그 명제를 지키는 코드에 테스트가 **0건**이었다. 리뷰가 찾은 것들:

    · `_record_from_prose` 가 **초기 판정 루프에 배선되지 않았다** — 재판정 경로에만
      있어서, 첫 라운드에 judge 가 VERDICT 줄을 정확히 내도 기회조차 없었다.
      측정 11 의 "폴백 발동 0회" 는 그 배선 결함 위에서 나온 수치다.
    · **첫** VERDICT 매치를 취해서, 모델이 스스로 고친 판정(`pass` → `revision`)이
      버려졌다.
    · 스냅샷이 손상되면 파생기가 성립 불가능한 지시를 스스로 만들었다.
    · 검사기의 "0건" 이 **무엇을 봤는지 세지 않았다** — 대상 0개와 결함 0개가 같은 출력.

실행:
    python3 tests/test_schema_instructions.py
    CYCLE_DRIVER=<경로> SCHEMA_CHECK=<경로> python3 tests/...
"""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_HARNESS = Path(__file__).resolve().parent.parent
_DRIVER = Path(os.environ.get("CYCLE_DRIVER", _HARNESS / ".claude/bin/cycle_driver.py")).resolve()
_CHECK = Path(os.environ.get("SCHEMA_CHECK", _HARNESS / ".claude/bin/schema_check.py")).resolve()


def _load(script: Path):
    spec = importlib.util.spec_from_file_location("driver_under_test", script)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["driver_under_test"] = mod
    spec.loader.exec_module(mod)
    return mod


class VerdictFallbackTest(unittest.TestCase):
    """`_record_from_prose` — judge 가 기록 도구를 안 불렀을 때의 결정론 회수."""

    def setUp(self):
        self.mod = _load(_DRIVER)
        self.recorded = []
        self.mod._vl = lambda args, strict=False: self.recorded.append(args) or (0, "")
        # 기록 여부 판정은 스텁 — 여기서 보는 것은 "무엇을 기록하기로 했는가" 다
        self.mod._judge_recorded = lambda feature, role, before: (
            self.recorded[-1][self.recorded[-1].index("--verdict") + 1]
            if self.recorded else None)

    def _call(self, out: str):
        self.recorded.clear()
        return self.mod._record_from_prose("reviewer", "F001", out, 0)

    def test_마지막_VERDICT_줄을_채택한다(self):
        """모델이 스스로 고친 판정을 버리면 안 된다 (첫 매치를 취하던 결함)."""
        got = self._call("VERDICT: pass — tests pass\n"
                         "Actually wait, let me re-check.\n"
                         "VERDICT: revision — add() lacks a docstring (calc.py:1)")
        self.assertEqual(got, "revision", f"첫 매치를 취했다: {self.recorded}")

    def test_프롬프트_인용_뒤의_실판정을_살린다(self):
        """첫 매치가 에코라 실판정까지 통째로 버려졌다."""
        got = self._call("The format is: VERDICT: pass — <your concrete finding>\n"
                         "VERDICT: revision — calc.py:1 의 add() 에 docstring 이 없다")
        self.assertEqual(got, "revision")

    def test_VERDICT_줄이_응답_끝이_아니면_기록하지_않는다(self):
        """judge 가 `cat` 한 파일 안의 VERDICT 문자열이 기록되면 안 된다."""
        self.assertIsNone(self._call(
            "VERDICT: pass — calc.py:1 확인함\n(위는 파일 내용이고 아래가 내 분석이다)\n분석 …"))

    def test_근거가_placeholder_거나_비면_기록하지_않는다(self):
        for note in ("", "<your concrete finding>", "<the unmet criterion>"):
            with self.subTest(note=note):
                self.assertIsNone(self._call(f"VERDICT: pass — {note}"))

    def test_pass_인데_본문이_미충족을_말하면_기록하지_않는다(self):
        """초기 경로엔 있던 모순 게이트가 이 경로엔 없었다."""
        self.assertIsNone(self._call(
            "VERDICT: pass — criterion 2 not met: docstring missing in calc.py:1"))

    def test_초기_판정_루프에_폴백이_배선돼_있다(self):
        """`_judge_with_retry` 에만 있으면 첫 라운드는 기회조차 없다 (MUST-1)."""
        src = _DRIVER.read_text(encoding="utf-8")
        wired = src.count("_record_from_prose(")
        self.assertGreaterEqual(
            wired, 3,      # 정의 1 + 재판정 경로 1 + 초기 루프 1
            f"_record_from_prose 호출 지점이 {wired}곳 — 초기 판정 루프 배선을 확인하라")


class SchemaDerivationTest(unittest.TestCase):
    """`_tool_schema` / `_write_instruction` — 스냅샷이 이상해도 쓰레기를 만들지 않는다."""

    POISONS = {
        "잘린 JSON": "{ torn",
        "최상위가 배열": "[]",
        "tools 가 문자열": '{"tools": "oops"}',
        "spec 이 문자열": '{"tools": {"write": "oops"}}',
        "required 가 문자열": '{"tools": {"write": {"required": "filePath"}}}',
        "required 가 비원소": '{"tools": {"write": {"required": [1, null]}}}',
        "required 가 빈 목록": '{"tools": {"write": {"required": []}}}',
        "required 키 부재": '{"tools": {"write": {}}}',
    }

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / ".claude/bin").mkdir(parents=True)
        (self.root / ".claude/schema").mkdir(parents=True)
        self.script = self.root / ".claude/bin/cycle_driver.py"
        self.script.write_text(_DRIVER.read_text(encoding="utf-8"), encoding="utf-8")
        self.snap = self.root / ".claude/schema/opencode-tools.json"

    def tearDown(self):
        self.tmp.cleanup()

    def test_손상된_스냅샷에도_성립하는_지시를_낸다(self):
        for label, body in self.POISONS.items():
            with self.subTest(snapshot=label):
                self.snap.write_text(body, encoding="utf-8")
                mod = _load(self.script)
                try:
                    text = mod._write_instruction("calc.py")
                except Exception as exc:  # noqa: BLE001
                    self.fail(f"{label} 에 죽었다: {type(exc).__name__}: {exc}")
                self.assertIn("filePath", text, f"{label}: 필수 인자가 빠진 지시")
                self.assertIn("content", text, f"{label}: 필수 인자가 빠진 지시")
                self.assertNotIn("set appropriately", text,
                                 f"{label}: 의미 없는 인자 지시를 만들어 냈다")

    def test_정상_스냅샷이면_그것에서_파생한다(self):
        self.snap.write_text(json.dumps({"tools": {
            "write": {"required": ["filePath", "content"]},
            "edit": {"required": ["filePath", "oldString", "newString"]},
        }}), encoding="utf-8")
        text = _load(self.script)._write_instruction("calc.py")
        self.assertIn("calc.py", text)
        self.assertIn("oldString", text, "edit 금지 근거가 스냅샷에서 파생되지 않았다")


class SchemaCheckerTest(unittest.TestCase):
    """검사기의 "0건" 이 **무엇을 봤는지** 말하는가 (MUST-4)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "h"
        shutil.copytree(_HARNESS, self.root, symlinks=True,
                        ignore=shutil.ignore_patterns("__pycache__", "state", ".git", "sandboxes*"))
        self.check = self.root / ".claude/bin/schema_check.py"
        self.snap = self.root / ".claude/schema/opencode-tools.json"
        # 결함을 심을 자리. `.claude/policy/<role>.md` 는 변형마다 있을 수도 없을 수도
        # 있다 (nem 만 judge 정책 오버레이를 가진다) — 없으면 만든다. 검사 대상은
        # `_TARGETS` 의 `.claude/policy` 디렉토리이므로 파일명은 무엇이든 된다.
        self.policy = self.root / ".claude/policy/reviewer.md"
        self.policy.parent.mkdir(parents=True, exist_ok=True)
        if not self.policy.is_file():
            self.policy.write_text("# 테스트용 정책 자리\n", encoding="utf-8")
        self.base = self.policy.read_text(encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def _run(self) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(self.check)],
                              capture_output=True, text=True, timeout=60)

    def test_기준선은_검사한_건수를_밝히며_통과한다(self):
        res = self._run()
        self.assertEqual(res.returncode, 0, res.stdout)
        self.assertIn("리터럴 지시", res.stdout, "무엇을 봤는지 세지 않는다")
        self.assertNotIn("리터럴 지시 0건", res.stdout,
                         "검사 대상이 0건인데 통과를 주장한다 — vacuous PASS")

    def test_빈_tools_는_통과가_아니라_BLOCK_이다(self):
        self.snap.write_text(json.dumps({"tools": {}}), encoding="utf-8")
        self.assertEqual(self._run().returncode, 1, "기준이 없는데 '결함 0건' 을 냈다")

    def test_손상된_스냅샷은_traceback_이_아니라_BLOCK_이다(self):
        self.snap.write_text("{ torn", encoding="utf-8")
        res = self._run()
        self.assertEqual(res.returncode, 1)
        self.assertNotIn("Traceback", res.stderr)

    def test_심은_결함_4종을_검출한다(self):
        defects = {
            "edit 에 content": "Call the edit tool with content set to the text.",
            "bash 인자 누락": "The bash tool needs both arguments: command.",
            "write 인자 누락": "Use the write tool to save it.",
            "없는 도구": "Call the frobnicate tool with x.",
        }
        for label, line in defects.items():
            with self.subTest(defect=label):
                self.policy.write_text(self.base + "\n" + line + "\n", encoding="utf-8")
                self.assertEqual(self._run().returncode, 1, f"{label} 를 놓쳤다")
        self.policy.write_text(self.base, encoding="utf-8")
        self.assertEqual(self._run().returncode, 0, "복원 후에도 BLOCK 이 남았다")

    def test_여러_줄로_쪼개진_지시를_거짓_BLOCK_하지_않는다(self):
        """모델이 보는 것은 이어붙인 한 문장이다 — 소스 줄 단위로 끊으면 오탐이다."""
        self.policy.write_text(
            self.base + '\n"Use the write tool to create a file "\n'
                        '"(filePath as a relative path and content as the text)."\n',
            encoding="utf-8")
        self.assertEqual(self._run().returncode, 0, "연결된 리터럴을 끊어 읽었다")


if __name__ == "__main__":
    print(f"드라이버: {_DRIVER}\n검사기:   {_CHECK}")
    unittest.main(verbosity=2)
