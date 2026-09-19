#!/usr/bin/env python3
"""수신 봉투의 필드가 inbox 밖으로 파일을 쓰지 못하는지 검증한다 (stdlib unittest).

왜 이 테스트가 있는가 (F019 리뷰 MUST-2):
  Teams·openclaw 수신 경로는 원격 봉투의 `ts` 를 파일명 **선두 성분**으로 썼다.
  당시 위생 처리는 `:` 와 `-` 만 지웠고 `/`·`..` 는 남겨, 실증으로 다음이 가능했다:

      ts="/etc/ABSOLUTE"    → /etc/ABSOLUTE__from-x.json   (inbox 완전 이탈)
      ts="../../../ESCAPED" → inbox 4단계 상위에 파일 생성

  채널에 글을 쓸 수 있는 누구나 폴링 프로세스의 권한으로 임의 위치에 파일을 쓸 수 있었고,
  rc=0 으로 조용히 성공했다. 수정(`_safe_component` 화이트리스트) 이 되돌아가지 않도록 잠근다.

실행:
    python3 tests/test_consortium_paths.py
"""
import importlib.util
import sys
import io
import os
import tempfile
import contextlib
import unittest
from pathlib import Path

_BIN = Path(__file__).resolve().parent.parent / ".claude" / "bin" / "consortium.py"
_spec = importlib.util.spec_from_file_location("consortium", _BIN)
_mod = importlib.util.module_from_spec(_spec)
sys.modules["consortium"] = _mod
_spec.loader.exec_module(_mod)


class SafeComponentTest(unittest.TestCase):
    """`_safe_component` 가 파일명 한 성분으로 안전한 값만 남기는지."""

    def _write_target(self, raw: str, fallback: str = "fb") -> Path:
        """실제 코드와 같은 방식으로 경로를 만든다."""
        inbox = Path("/tmp/consortium-test-inbox")
        return inbox / f"{_mod._safe_component(raw, fallback)}__from-x.json"

    def test_정상_타임스탬프는_보존된다(self):
        """ISO 타임스탬프의 의미 있는 문자(숫자·T·+)는 살아남아야 한다."""
        got = _mod._safe_component("2026-09-16T00:19:53+00:00", "fb")
        self.assertEqual(got, "20260916T001953+0000")   # `-`·`:` 제거, 숫자·T·+ 보존
        self.assertNotIn("/", got)

    def test_절대경로는_inbox를_벗어나지_못한다(self):
        """pathlib 은 절대경로 세그먼트를 만나면 base 를 버린다 — 가장 위험한 경로."""
        out = self._write_target("/etc/ABSOLUTE")
        self.assertEqual(out.parent, Path("/tmp/consortium-test-inbox"))
        self.assertNotIn("etc", out.parts[:-1])

    def test_상대경로_탈출은_차단된다(self):
        """`..` 가 남으면 상위 디렉토리로 올라간다."""
        out = self._write_target("../../../ESCAPED")
        self.assertNotIn("..", str(out))
        self.assertEqual(out.parent, Path("/tmp/consortium-test-inbox"))

    def test_구분자가_모두_제거된다(self):
        """제거 목록이 아니라 허용 목록이므로 새 구분자에도 안전하다."""
        for raw in ("a/b", "a\\b", "a:b", "a\x00b", "a b", "a..b"):
            with self.subTest(raw=raw):
                got = _mod._safe_component(raw, "fb")
                self.assertTrue(got.isalnum() or got == "fb", f"{raw!r} → {got!r}")

    def test_빈값이면_fallback(self):
        """전부 걸러지면 호출부가 준 fallback 을 쓴다 (빈 파일명 방지)."""
        self.assertEqual(_mod._safe_component("", "fb"), "fb")
        self.assertEqual(_mod._safe_component("../", "fb"), "fb")

    def test_from_team_도_위생처리된다(self):
        """봉투의 from_team 역시 원격 입력이다."""
        got = _mod._safe_component("../../evil", "unknown")
        self.assertNotIn("/", got)
        self.assertNotIn("..", got)


class CliSmokeTest(unittest.TestCase):
    """모든 CLI 하위명령이 **적어도 실행은 되는지** (리뷰 MUST-1).

    `roster` 가 `NameError` 로 죽은 채 커밋됐다. 원인은 문서 문구를 고치려고 돌린
    정규식이 소스의 `len(teams)` 까지 친 것인데, **`roster` 에 테스트가 0건이라**
    아무도 잡지 못했다. 정교한 단언보다 "죽지 않는다" 를 거는 것이 먼저다.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        os.environ["CLAUDE_PROJECT_DIR"] = str(self.root)

    def tearDown(self):
        os.environ.pop("CLAUDE_PROJECT_DIR", None)
        self.tmp.cleanup()

    def _run(self, *argv) -> int:
        spec = importlib.util.spec_from_file_location("consortium_cli", _BIN)
        mod = importlib.util.module_from_spec(spec)
        sys.modules["consortium_cli"] = mod
        spec.loader.exec_module(mod)
        old = sys.argv
        sys.argv = ["consortium.py", *argv]
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                mod.main()
            return 0
        except SystemExit as exc:
            return int(exc.code or 0)
        finally:
            sys.argv = old

    def test_모든_하위명령이_예외없이_실행된다(self):
        self.assertEqual(self._run("init", "team-a", "--agents", "developer"), 0)
        for argv in (["roster"],
                     ["send", "--to", "team-b", "--role", "developer",
                      "--cycle", "C1", "--msg", "스모크"],
                     ["inbox"],
                     ["self"],
                     ["gateway", "slack"],
                     ["gateway", "teams"],
                     ["gateway", "telegram"]):
            with self.subTest(cmd=" ".join(argv)):
                self.assertEqual(self._run(*argv), 0, f"`{' '.join(argv)}` 가 실패했다")


if __name__ == "__main__":
    unittest.main(verbosity=2)
