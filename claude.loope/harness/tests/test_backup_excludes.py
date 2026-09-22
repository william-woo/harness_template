#!/usr/bin/env python3
"""backup.py 의 제외·보안차단 판정을 잠근다 (stdlib unittest).

왜 이 테스트가 있는가 (F019 리뷰 MUST-4 중 발견):
  `_is_rsync_excluded` 의 디렉토리 패턴 처리가 **단일 세그먼트만** 다뤘다.
  `.claude/state/qa-browser/screenshots/` 같은 다중 세그먼트 패턴은
  `p in parts[:-1]` 비교에서 절대 참이 될 수 없었다 — `p` 는 여러 세그먼트를 담은
  한 문자열이고 `parts` 는 단일 세그먼트 목록이기 때문이다.

  결과: 제외한다고 적어 둔 5개 패턴이 전부 무효였고, 스크린샷·실행로그가 백업에 실렸다.
  "제외 목록에 적었다"와 "실제로 제외된다"는 다르다 — 그 간극을 이 테스트가 막는다.

실행:
    python3 tests/test_backup_excludes.py
"""
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

_BIN = Path(__file__).resolve().parent.parent / ".claude" / "bin" / "backup.py"
_spec = importlib.util.spec_from_file_location("backup", _BIN)
_mod = importlib.util.module_from_spec(_spec)
sys.modules["backup"] = _mod
_spec.loader.exec_module(_mod)


class RsyncExcludeTest(unittest.TestCase):
    """경로가 백업에서 빠지는지 — 패턴 형태별로."""

    def setUp(self):
        self.excludes = _mod.get_effective_excludes()

    def _excluded(self, rel: str) -> bool:
        return _mod._is_rsync_excluded(rel, self.excludes)

    def test_다중세그먼트_디렉토리_패턴이_동작한다(self):
        """이 테스트가 잡는 회귀가 실제로 있었다 (5개 패턴 전부 무효)."""
        for rel in (".claude/state/qa-browser/screenshots/shot.png",
                    ".claude/state/qa-browser/runs/run.jsonl",
                    ".claude/state/consortium/roster.json",
                    ".claude/state/atlassian/map.json",
                    "src/harness_template/claude.loope/harness/CLAUDE.md"):
            with self.subTest(rel=rel):
                self.assertTrue(self._excluded(rel), f"{rel} 이 제외되지 않는다")

    def test_단일세그먼트_디렉토리_패턴은_그대로(self):
        """깊이와 무관하게 매칭되던 기존 동작이 깨지지 않아야 한다."""
        self.assertTrue(self._excluded("node_modules/x/y.js"))
        self.assertTrue(self._excluded("a/b/node_modules/deep/z.js"))

    def test_자격증명_경로는_제외된다(self):
        """게이트웨이 토큰이 백업 리포로 새 나가지 않아야 한다."""
        self.assertTrue(self._excluded(".claude/state/consortium/.secrets/teams_token.txt"))

    def test_커밋대상_산출물은_통과한다(self):
        """제외가 과해지면 백업이 비어 버린다 — 반대 방향도 잠근다."""
        for rel in ("docs/adr/ADR-012-consortium-distribution.md",
                    ".claude/state/checkpoints/x.md",
                    ".claude/state/learnings.jsonl",
                    "CLAUDE.md"):
            with self.subTest(rel=rel):
                self.assertFalse(self._excluded(rel), f"{rel} 이 잘못 제외된다")


class SecurityBlockTest(unittest.TestCase):
    """자격증명으로 보이는 파일이 백업 전에 차단되는지."""

    def test_토큰_웹훅_시크릿디렉토리가_차단된다(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            for rel in (".secrets/teams_token.txt", "cfg/teams_webhook.txt", "x/app_secret.txt"):
                p = root / rel
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text("x", encoding="utf-8")
            hits = _mod.scan_security_blocks(root)
            self.assertEqual(len(hits), 3, f"차단 누락: {hits}")

    def test_디렉토리_패턴이_파일명과_무관하게_차단한다(self):
        """이 테스트가 없어서 `.secrets/` 패턴이 무효인 걸 놓쳤다 (재리뷰 신규 MUST).

        위 테스트는 `.secrets/teams_token.txt` 를 썼는데, 그건 `*token.txt` **글롭**이
        잡은 것이었다. `.secrets/` 디렉토리 패턴 자체는 `is_file()` 검사에 걸려
        아무것도 차단하지 않았다 — 통과하는 테스트가 결함을 가린 전형이다.
        그래서 여기선 **어떤 글롭에도 걸리지 않는 파일명**을 쓴다.
        """
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            for rel in (".secrets/foo.bin", "deep/.secrets/bar.json", ".aws/config"):
                p = root / rel
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text("x", encoding="utf-8")
            hits = set(_mod.scan_security_blocks(root))
            for rel in (".secrets/foo.bin", "deep/.secrets/bar.json", ".aws/config"):
                with self.subTest(rel=rel):
                    self.assertIn(rel, hits, f"{rel} 이 차단되지 않는다")

    def test_양식파일과_일반문서는_통과한다(self):
        """*.example 화이트리스트와 평범한 문서가 오탐으로 막히면 안 된다."""
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            for rel in ("docs/normal.md", "cfg/app.env.example", "README.md"):
                p = root / rel
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text("x", encoding="utf-8")
            self.assertEqual(_mod.scan_security_blocks(root), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
