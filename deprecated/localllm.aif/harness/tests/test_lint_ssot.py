#!/usr/bin/env python3
"""LINT-SSOT (main ≡ claude.loope invariant) 을 잠근다 (stdlib unittest).

왜 이 파일이 있는가 (F021 재리뷰 MUST-1·2 / SHOULD-2):
  F021 은 "ADR-015 의 invariant 를 **코드로** 강제한다" 며 `check_ssot` 를 만들었는데
  그 검사기 자신에 테스트가 0건이었다. 검증 근거는 커밋 메시지의 수동 실험 한 줄
  ("loope 에 한 줄 넣으면 BLOCK 1건") 뿐이었다.

  그 공백에서 두 결함이 살아남았다 — 둘 다 **검사를 통째로 우회**하는 것이었다:
    · 제외 목록이 경로 성분 전역 매칭이라, `state`/`design` 이라는 이름의 디렉토리를
      어디에 만들든 그 아래가 전부 검사에서 빠졌다 (`.claude/agents/design/evil.md`)
    · CLAUDE.md 섹션 비교가 단방향이라 loope 에만 섹션을 더하면 0 BLOCK 이었다
      (파일 수준은 양방향인데 섹션 수준만 아니었다 — 층마다 정책이 달랐다)

  "검사기를 만들었다" 와 "그 검사기가 실제로 잡는다" 는 다른 주장이다.
  이 파일이 뒤쪽을 맡는다.

실행:
    python3 tests/test_lint_ssot.py
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
_LINT_REL = ".claude/bin/lint.py"


def _run(root: Path) -> subprocess.CompletedProcess:
    """LINT-SSOT 만 실제 CLI 로 태운다."""
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(root)}
    return subprocess.run(
        [sys.executable, str(root / _LINT_REL), "check", "--only=LINT-SSOT"],
        capture_output=True, text=True, env=env, cwd=str(root), timeout=120)


def _blocks(res: subprocess.CompletedProcess) -> list[str]:
    return [ln for ln in res.stdout.splitlines() if "| BLOCK |" in ln]


class LintSsotTest(unittest.TestCase):
    """최소 미러 쌍을 만들어 drift 검출을 확인한다."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        # main 쪽: lint.py 는 실물을 쓴다 (검사기 자신이 대상이 아니라 도구다)
        (self.root / ".claude/bin").mkdir(parents=True)
        shutil.copy2(_REPO / _LINT_REL, self.root / _LINT_REL)
        (self.root / ".claude/agents").mkdir(parents=True)
        (self.root / ".claude/agents/dev.md").write_text("# dev", encoding="utf-8")
        (self.root / "docs/adr").mkdir(parents=True)
        (self.root / "docs/adr/ADR-001-x.md").write_text("# ADR", encoding="utf-8")
        (self.root / "CLAUDE.md").write_text(
            "# 가이드\n\n## 🅰 첫 섹션\n본문 A\n\n## 🅱 둘째 섹션\n본문 B\n", encoding="utf-8")
        # loope 쪽: 1:1 복사
        self.loope = self.root / "src/harness_template/claude.loope/harness"
        self.loope.mkdir(parents=True)
        for rel in (".claude", "docs", "CLAUDE.md"):
            src = self.root / rel
            dst = self.loope / rel
            shutil.copytree(src, dst) if src.is_dir() else shutil.copy2(src, dst)

    def tearDown(self):
        self.tmp.cleanup()

    def test_기준선은_정합이다(self):
        res = _run(self.root)
        self.assertEqual(_blocks(res), [], res.stdout)

    def test_내용_drift_를_잡는다(self):
        (self.loope / ".claude/agents/dev.md").write_text("# dev (변조)", encoding="utf-8")
        self.assertTrue(_blocks(_run(self.root)), "한 줄 drift 를 놓쳤다")

    def test_한쪽에만_있는_파일을_양방향으로_잡는다(self):
        (self.root / ".claude/agents/only-main.md").write_text("m", encoding="utf-8")
        self.assertTrue(any("only-main" in b for b in _blocks(_run(self.root))),
                        "main-only 파일을 놓쳤다")
        (self.loope / ".claude/agents/only-loope.md").write_text("l", encoding="utf-8")
        blocks = _blocks(_run(self.root))
        self.assertTrue(any("only-loope" in b for b in blocks), "loope-only 파일을 놓쳤다")

    def test_제외_이름을_디렉토리로_써서_밀반입할_수_없다(self):
        """제외 목록이 경로 성분 전역 매칭이던 동안, 이 5건이 전부 0 BLOCK 이었다."""
        smuggle = {
            ".claude/agents/design/evil.md": "제외 이름을 중간 디렉토리로",
            ".claude/skills/state/SKILL.md": "state 를 하위 디렉토리로",
            ".claude/commands/host.json": "제외 파일명을 다른 위치에",
            "docs/adr/design/ADR-099-rogue.md": "adr 아래 design 디렉토리",
        }
        for rel, why in smuggle.items():
            with self.subTest(경로=rel):
                target = self.loope / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("rogue", encoding="utf-8")
                blocks = _blocks(_run(self.root))
                self.assertTrue(any(Path(rel).name in b for b in blocks),
                                f"{why} — 밀반입이 통과했다: {rel}")
                target.unlink()

    def test_CLAUDE_md_섹션_drift_를_양방향으로_잡는다(self):
        """파일 수준은 양방향인데 섹션 수준만 main-only 였다 — 층마다 정책이 달랐다."""
        md = self.loope / "CLAUDE.md"
        original = md.read_text(encoding="utf-8")

        md.write_text(original + "\n## 🧨 loope 전용 섹션\n몰래 추가\n", encoding="utf-8")
        self.assertTrue(any("loope 전용 섹션" in b for b in _blocks(_run(self.root))),
                        "loope 에만 있는 섹션을 놓쳤다")

        md.write_text(original.replace("본문 B", "본문 B 변조"), encoding="utf-8")
        self.assertTrue(any("둘째 섹션" in b for b in _blocks(_run(self.root))),
                        "섹션 본문 drift 를 놓쳤다")

        md.write_text(original, encoding="utf-8")
        (self.root / "CLAUDE.md").write_text(
            original + "\n## 🆕 main 전용 섹션\n본문\n", encoding="utf-8")
        self.assertTrue(any("main 전용 섹션" in b for b in _blocks(_run(self.root))),
                        "main 에만 있는 섹션을 놓쳤다")

    def test_symlink_으로_해시를_맞춰_drift_를_가릴_수_없다(self):
        """loope 쪽에 main 을 가리키는 링크를 두면 내용 해시가 같아진다."""
        link = self.loope / ".claude/agents/dev.md"
        link.unlink()
        link.symlink_to(self.root / ".claude/agents/dev.md")
        self.assertTrue(_blocks(_run(self.root)), "심볼릭 링크가 검사를 통과했다")

    def test_변형이_없으면_BLOCK_대신_INFO_로_물러난다(self):
        """다운스트림(변형 디렉토리 부재)에서 이 검사가 게이트를 막으면 안 된다."""
        solo = Path(self.tmp.name) / "solo"
        (solo / ".claude/bin").mkdir(parents=True)
        shutil.copy2(_REPO / _LINT_REL, solo / _LINT_REL)
        res = _run(solo)
        self.assertEqual(_blocks(res), [], res.stdout)
        self.assertIn("검사 생략", res.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
