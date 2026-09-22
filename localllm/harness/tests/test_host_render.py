#!/usr/bin/env python3
"""host.py 의 render-agents / render-commands 안전 계약을 잠근다 (stdlib unittest).

왜 이 파일이 있는가 (F023 리뷰 MUST-1·2·3):
  렌더러의 "stale 정리" 가 출력 디렉토리의 **모든** `.md` 를 지웠다. 실측으로
  `--agents-out docs/adr` 하나에 ADR 9건이, `--agents-out .` 에 `CLAUDE.md`·
  `README.md` 가 사라졌다. 출력 경로도 구속되지 않아 `../..` 로 트리를 벗어났고,
  둘을 합치면 **외부 디렉토리의 문서를 지울 수 있었다**.

  python 내부 `unlink` 라 `permissions.ask` 의 `rm` 패턴도 훅도 잡지 못한다 —
  CLAUDE.md 규칙 #1 이 경고한 "선언 규칙이 못 잡는 삭제 경로" 가 이것이다.
  그런데 ADR-017 은 "30 커맨드 변환 검증 완료" 라 적어 놓고 테스트가 0건이었다.

실행:
    python3 tests/test_host_render.py
"""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent


def _make_project(dst: Path) -> None:
    """렌더에 필요한 최소 트리를 만든다 (실제 리포를 건드리지 않는다)."""
    (dst / ".claude" / "bin" / "host_adapters").mkdir(parents=True)
    shutil.copy(_ROOT / ".claude" / "bin" / "host.py", dst / ".claude" / "bin")
    for f in (_ROOT / ".claude" / "bin" / "host_adapters").glob("*.py"):
        shutil.copy(f, dst / ".claude" / "bin" / "host_adapters")
    shutil.copytree(_ROOT / ".claude" / "agents", dst / ".claude" / "agents")
    shutil.copytree(_ROOT / ".claude" / "commands", dst / ".claude" / "commands")


def _render(root: Path, *argv) -> subprocess.CompletedProcess:
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(root), "HARNESS_AGENT_TYPE": "opencode"}
    return subprocess.run([sys.executable, str(root / ".claude" / "bin" / "host.py"), *argv],
                          capture_output=True, text=True, env=env, cwd=str(root), timeout=120)


class RenderSafetyTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "proj"
        self.root.mkdir()
        _make_project(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_출력_경로가_프로젝트_루트를_벗어나지_못한다(self):
        """`--agents-out ../..` 가 트리 밖에 파일을 만들었다 (실측).

        절대경로 케이스는 **실행마다 유일한 경로**를 쓴다 — 고정 경로로 두면 이전
        실행이 남긴 잔재와 충돌해, 코드가 아니라 환경 때문에 빨개진다(실제로 겪었다).
        """
        abs_target = Path(self.tmp.name) / "abs-escape"
        for cmd, flag in (("render-agents", "--agents-out"), ("render-commands", "--commands-out")):
            for bad in ("../escaped", str(abs_target), "../../deeper"):
                with self.subTest(cmd=cmd, out=bad):
                    res = _render(self.root, cmd, flag, bad)
                    self.assertNotEqual(res.returncode, 0, f"{bad} 가 통과했다")
                    self.assertIn("벗어", res.stdout + res.stderr)
        self.assertFalse((Path(self.tmp.name) / "escaped").exists(), "트리 밖에 디렉토리가 생겼다")
        self.assertFalse(abs_target.exists(), "절대경로로 트리를 벗어났다")

    def test_렌더_산출물이_아닌_파일은_지우지_않는다(self):
        """이 테스트가 잡는 회귀가 실제로 있었다 — ADR 9건이 사라졌다."""
        docs = self.root / "docs" / "adr"
        docs.mkdir(parents=True)
        for name in ("ADR-001-x.md", "ADR-002-y.md", "README.md"):
            (docs / name).write_text(f"# {name}\n소중한 내용", encoding="utf-8")

        res = _render(self.root, "render-agents", "--agents-out", "docs/adr")
        self.assertEqual(res.returncode, 0, res.stderr[:300])
        for name in ("ADR-001-x.md", "ADR-002-y.md", "README.md"):
            with self.subTest(file=name):
                self.assertTrue((docs / name).exists(), f"{name} 이 삭제됐다")
                self.assertIn("소중한 내용", (docs / name).read_text(encoding="utf-8"))
        self.assertIn("WARN", res.stdout, "비산출물이 있는데 경고가 없다")

    def test_렌더_산출물은_stale_정리_대상이다(self):
        """소스에서 사라진 에이전트의 산출물은 지워져야 한다 (정리 기능 자체)."""
        _render(self.root, "render-agents")
        out = self.root / ".opencode" / "agent"
        victim = out / "developer.md"
        self.assertTrue(victim.exists())
        (self.root / ".claude" / "agents" / "developer.md").unlink()
        _render(self.root, "render-agents")
        self.assertFalse(victim.exists(), "소스에서 사라진 산출물이 남았다")

    def test_두_번_렌더해도_결과가_같다(self):
        for cmd in ("render-agents", "render-commands"):
            with self.subTest(cmd=cmd):
                self.assertEqual(_render(self.root, cmd).returncode, 0)
                sub = "agent" if cmd == "render-agents" else "commands"
                first = {p.name: p.read_bytes() for p in (self.root / ".opencode" / sub).glob("*.md")}
                self.assertEqual(_render(self.root, cmd).returncode, 0)
                second = {p.name: p.read_bytes() for p in (self.root / ".opencode" / sub).glob("*.md")}
                self.assertEqual(first, second, f"{cmd} 가 멱등하지 않다")
                self.assertGreater(len(first), 0, "산출물이 없다")


class FrontmatterToleranceTest(unittest.TestCase):
    """frontmatter 가 이탈해도 **틀린 산출물을 조용히 내지 않는지** (MUST-4).

    `tools:` 가 YAML 리스트면 11 도구 전부 deny 로 변환돼 에이전트가 아무 도구도
    못 쓰는데 경고가 0건이었다 — 터지지 않고 **틀린 결과가 로드**되는 형태다.
    """

    CASES = {
        "리스트 tools": "---\ndescription: t\ntools:\n  - Bash\n  - Read\n---\n본문\n",
        "닫는 --- 없음": "---\ndescription: t\ntools: Bash\n본문\n",
        "빈 파일": "",
        "frontmatter 없음": "그냥 본문\n",
        "빈 description": "---\ndescription:\ntools: Bash\n---\n본문\n",
    }

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "proj"
        self.root.mkdir()
        _make_project(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_이탈한_frontmatter_는_경고와_함께_처리된다(self):
        agents = self.root / ".claude" / "agents"
        for f in agents.glob("*.md"):
            f.unlink()
        for label, body in self.CASES.items():
            with self.subTest(case=label):
                (agents / "probe.md").write_text(body, encoding="utf-8")
                res = _render(self.root, "render-agents")
                self.assertEqual(res.returncode, 0, f"{label} 에 렌더가 죽었다: {res.stderr[:200]}")
                self.assertNotIn("Traceback", res.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
