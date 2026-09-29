#!/usr/bin/env python3
"""`atlassian_map.py` 의 **종료코드 계약**을 잠근다 (F032 AC5).

왜 이 파일이 있는가:
  AC5 는 "종료코드 0/2/3 분기" 를 주장하는데, 그것을 고정하는 테스트가 없었다.
  QA 2회차가 변이로 실증했다 — `cmd_check` 의 `return 3` 을 `return 0` 으로 바꿔도
  **66 테스트가 전부 통과**했다. 갱신이 필요한 대상을 "최신" 으로 읽는 변경이
  아무 저항 없이 들어갈 수 있었다는 뜻이다.

  이 스크립트가 하는 일은 하나다 — **판단을 모델에게 맡기지 않는 것**. 발행할지
  말지를 셸이 `case $?` 로 가른다. 그 숫자가 계약이므로 숫자를 잠근다.

  ADR-023 의 설계에서 코드가 필요한 곳은 멱등성 하나뿐이었다. 그 하나가
  검증되지 않으면 "API 래퍼를 만들지 않는다" 는 결정의 근거도 같이 약해진다.

실행:
    python3 tests/test_atlassian_map.py
"""
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

_SRC = Path(__file__).resolve().parents[1] / ".claude" / "bin" / "atlassian_map.py"


class AtlassianMapExitCodeTest(unittest.TestCase):
    """`_MAP` 이 `__file__` 기준이라, 스크립트를 임시 트리에 **설치**해서 태운다.

    실제 리포의 매핑 파일을 건드리지 않기 위해서다 — 테스트가 작업 상태를
    바꾸면 그 테스트는 한 번만 맞는다.
    """

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        (root / ".claude" / "bin").mkdir(parents=True)
        self.script = root / ".claude" / "bin" / "atlassian_map.py"
        shutil.copy2(_SRC, self.script)
        self.map_file = root / ".claude" / "state" / "atlassian" / "map.json"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def run_map(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(["python3", str(self.script), *args],
                              capture_output=True, text=True)

    # ── check 의 0/2/3 — 이것이 계약이다 ──────────────────────────────────
    def test_미기록이면_신규_발행_2(self):
        r = self.run_map("check", "adr", "ADR-001", "--digest", "abc")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)

    def test_digest_가_같으면_발행_불필요_0(self):
        self.run_map("put", "adr", "ADR-001", "--url", "https://x/1", "--digest", "abc")
        r = self.run_map("check", "adr", "ADR-001", "--digest", "abc")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_digest_가_다르면_갱신_발행_3(self):
        """QA 변이 M10 이 살아남은 자리 — `return 3` 을 0 으로 바꿔도 아무도 몰랐다."""
        self.run_map("put", "adr", "ADR-001", "--url", "https://x/1", "--digest", "abc")
        r = self.run_map("check", "adr", "ADR-001", "--digest", "zzz")
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)

    def test_세_경우가_서로_다른_값이다(self):
        """0/2/3 이 **구별**되어야 셸이 가를 수 있다 — 셋이 같으면 분기가 죽는다."""
        new = self.run_map("check", "adr", "A", "--digest", "d1").returncode
        self.run_map("put", "adr", "A", "--url", "https://x/1", "--digest", "d1")
        same = self.run_map("check", "adr", "A", "--digest", "d1").returncode
        changed = self.run_map("check", "adr", "A", "--digest", "d2").returncode
        self.assertEqual(len({new, same, changed}), 3,
                         f"신규={new} 동일={same} 변경={changed} — 구별되지 않는다")

    # ── 기록이 실제로 남는가 ──────────────────────────────────────────────
    def test_put_이_url_digest_revision_을_기록한다(self):
        self.run_map("put", "adr", "ADR-007", "--url", "https://x/7",
                     "--id", "777", "--digest", "d1")
        entry = json.loads(self.map_file.read_text(encoding="utf-8"))["entries"]["adr:ADR-007"]
        self.assertEqual(entry["url"], "https://x/7")
        self.assertEqual(entry["digest"], "d1")
        self.assertEqual(entry.get("remote_id"), "777")
        self.assertEqual(entry.get("revision"), 1)

    def test_같은_대상을_다시_발행하면_revision_이_오른다(self):
        self.run_map("put", "adr", "ADR-007", "--url", "https://x/7", "--digest", "d1")
        self.run_map("put", "adr", "ADR-007", "--url", "https://x/7", "--digest", "d2")
        entry = json.loads(self.map_file.read_text(encoding="utf-8"))["entries"]["adr:ADR-007"]
        self.assertEqual(entry.get("revision"), 2)
        self.assertEqual(entry["digest"], "d2")

    # ── forget 은 되돌릴 수 없는 일을 한다 ────────────────────────────────
    def test_forget_은_yes_없이는_거부한다(self):
        """기록을 지우면 다음 발행이 **새 페이지를 만든다** — 확인 없이 하면 안 된다."""
        self.run_map("put", "adr", "ADR-007", "--url", "https://x/7", "--digest", "d1")
        r = self.run_map("forget", "adr", "ADR-007")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("adr:ADR-007", self.map_file.read_text(encoding="utf-8"))

    def test_forget_은_yes_가_있으면_지운다(self):
        self.run_map("put", "adr", "ADR-007", "--url", "https://x/7", "--digest", "d1")
        r = self.run_map("forget", "adr", "ADR-007", "--yes")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("adr:ADR-007", self.map_file.read_text(encoding="utf-8"))

    # ── 없는 것을 있다고 하지 않는다 ──────────────────────────────────────
    def test_get_은_미발행이면_1_이다(self):
        self.assertEqual(self.run_map("get", "adr", "ADR-999").returncode, 1)

    def test_digest_는_같은_내용에_같은_값을_준다(self):
        f = Path(self._tmp.name) / "a.md"
        f.write_text("hello", encoding="utf-8")
        a = self.run_map("digest", str(f)).stdout.strip()
        b = self.run_map("digest", str(f)).stdout.strip()
        self.assertTrue(a, "digest 가 아무것도 출력하지 않았다")
        self.assertEqual(a, b)
        f.write_text("hello!", encoding="utf-8")
        self.assertNotEqual(a, self.run_map("digest", str(f)).stdout.strip())


class AtlassianMapIsolationTest(unittest.TestCase):
    """멱등성 코드가 **네트워크를 건드리지 않는다** — ADR-023 의 설계 전제다.

    "자체 MCP 서버도 API 래퍼도 만들지 않는다. 코드가 필요한 곳은 멱등성 하나뿐"
    이라고 적었다. 그 코드가 슬그머니 HTTP 를 부르기 시작하면 그 결정이 무너진다.
    """

    FORBIDDEN = ("requests", "urllib.request", "http.client", "httpx", "socket", "mcp")

    def test_외부_통신_모듈을_import_하지_않는다(self):
        src = _SRC.read_text(encoding="utf-8")
        found = [m for m in self.FORBIDDEN
                 if f"import {m}" in src or f"from {m}" in src]
        self.assertEqual(found, [], f"멱등성 층이 외부 통신을 끌어들였다: {found}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
