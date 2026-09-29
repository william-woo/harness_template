#!/usr/bin/env python3
"""pre-bash-check.sh 의 main/master 커밋 차단이 **어느 저장소를 보는가**.

훅은 원래 자기 cwd 에서 `git branch --show-current` 를 읽었다. 그러나 명령은
`cd src/harness_template && git commit …` 처럼 다른 저장소로 옮겨가서 커밋할 수
있고, 이 리포에는 실제로 중첩 저장소가 있다. 그래서 두 방향으로 틀렸다:

  · 미탐 — 바깥이 feature 브랜치면 안쪽 `main` 직접 커밋이 통과한다
  · 오탐 — 바깥이 `main` 이면 안쪽 feature 브랜치 커밋이 막힌다

이 테스트는 중첩 저장소를 실제로 만들어 훅을 태운다. 훅의 판정 대상을 cwd 로
되돌리면 `미탐`·`오탐` 테스트가 **실패해야** 한다 — 그것이 이 테스트가 결함을
잡는다는 증거다.
"""
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_HOOK = _ROOT / ".claude" / "hooks" / "pre-bash-check.sh"

_GIT_ENV = {
    "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@e",
    "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@e",
}


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True,
                   capture_output=True, env={**os.environ, **_GIT_ENV})


def _make_repo(path: Path, branch: str, commit: bool = True) -> None:
    """`branch` 위에 있는 저장소를 만든다. commit=False 면 HEAD 가 없다(초기 커밋 상태)."""
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-b", branch, str(path)], check=True, capture_output=True)
    if commit:
        (path / "f.txt").write_text("x", encoding="utf-8")
        _git(path, "add", "f.txt")
        _git(path, "commit", "-m", "init")


def _run(cwd: Path, command: str) -> int:
    """훅을 실제 명령 payload 로 태운다. 0=허용, 2=차단."""
    payload = json.dumps({"hook_event_name": "PreToolUse", "tool_name": "Bash",
                          "tool_input": {"command": command}})
    proc = subprocess.run(["bash", str(_HOOK)], input=payload, text=True,
                          capture_output=True, cwd=str(cwd))
    return proc.returncode


class RepoScopeTest(unittest.TestCase):
    """중첩 저장소에서 훅이 **커밋이 실제로 일어날 저장소**를 보는가."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    # ── 미탐 방향: 바깥 feature / 안쪽 main ────────────────────────────────
    def _outer_feature_inner_main(self) -> Path:
        outer = self.base / "outer"
        _make_repo(outer, "feat/x")
        _make_repo(outer / "inner", "main")
        return outer

    def test_cd_로_들어간_안쪽_main_커밋을_차단한다(self):
        outer = self._outer_feature_inner_main()
        self.assertEqual(_run(outer, "cd inner && git commit -m x"), 2)

    def test_git_C_로_지정한_안쪽_main_커밋을_차단한다(self):
        outer = self._outer_feature_inner_main()
        self.assertEqual(_run(outer, "git -C inner commit -m x"), 2)

    def test_cd_절대경로도_따라간다(self):
        outer = self._outer_feature_inner_main()
        self.assertEqual(_run(outer, f"cd {outer / 'inner'} && git commit -m x"), 2)

    def test_cd_체인을_누적해_따라간다(self):
        outer = self.base / "outer"
        _make_repo(outer, "feat/x")
        _make_repo(outer / "a" / "b", "main")
        self.assertEqual(_run(outer, "cd a && cd b && git commit -m x"), 2)

    def test_바깥에서_그냥_커밋하면_바깥_브랜치를_본다(self):
        outer = self._outer_feature_inner_main()
        self.assertEqual(_run(outer, "git commit -m x"), 0)

    # ── 오탐 방향: 바깥 main / 안쪽 feature ────────────────────────────────
    def _outer_main_inner_feature(self) -> Path:
        outer = self.base / "outer"
        _make_repo(outer, "main")
        _make_repo(outer / "inner", "feat/y")
        return outer

    def test_바깥이_main_이어도_안쪽_feature_커밋은_허용한다(self):
        outer = self._outer_main_inner_feature()
        self.assertEqual(_run(outer, "cd inner && git commit -m x"), 0)

    def test_바깥이_main_이면_바깥_커밋은_차단한다(self):
        outer = self._outer_main_inner_feature()
        self.assertEqual(_run(outer, "git commit -m x"), 2)

    # ── 경계 ──────────────────────────────────────────────────────────────
    def test_초기_커밋은_main_이어도_허용한다(self):
        """HEAD 가 없으면 저장소 셋업 중이다 — 판정 대상 저장소에서 확인해야 한다."""
        outer = self.base / "outer"
        _make_repo(outer, "feat/x")
        _make_repo(outer / "inner", "main", commit=False)
        self.assertEqual(_run(outer, "cd inner && git commit -m x"), 0)

    def test_존재하지_않는_경로로_cd_하면_막지_않는다(self):
        """브랜치를 못 읽으면 판정하지 않는다 — 없는 저장소를 main 으로 단정하지 않는다."""
        outer = self.base / "outer"
        _make_repo(outer, "main")
        self.assertEqual(_run(outer, "cd nope && git commit -m x"), 0)

    def test_따옴표_있는_경로도_한_경로로_읽는다(self):
        outer = self.base / "outer"
        _make_repo(outer, "feat/x")
        _make_repo(outer / "a b", "main")
        self.assertEqual(_run(outer, 'cd "a b" && git commit -m x'), 2)

    def test_master_도_같이_막는다(self):
        outer = self.base / "outer"
        _make_repo(outer, "feat/x")
        _make_repo(outer / "inner", "master")
        self.assertEqual(_run(outer, "cd inner && git commit -m x"), 2)


class MirrorTest(unittest.TestCase):
    """수정이 **갈 곳에 다 갔는가** — 이 리포의 반복 결함이 정확히 이것이다.

    `claude/`(baseline)은 Phase 0 스냅샷이라 의도적으로 동결돼 있고(CLAUDE.md), 같은
    결함을 **가진 채로** 남는다. 그것을 여기서 조용히 건너뛰면 "고쳐졌다"는 인상만
    남으므로, 제외를 목록으로 못박고 그 목록이 늘어나면 실패하게 둔다.
    """

    FROZEN = {"claude"}   # baseline — 동결, 같은 결함 잔존 (의도된 제외)
    MARKER = 'git -C "$COMMIT_REPO" branch'

    def _copies(self):
        tpl = _ROOT / "src" / "harness_template"
        if not tpl.exists():
            self.skipTest("harness_template 없음")
        # 고정 깊이 glob — `state/` 안의 런타임 사본(git 미추적)은 잡지 않는다
        return tpl, sorted(tpl.glob("*/harness/.claude/hooks/pre-bash-check.sh"))

    def test_활성_변형은_모두_저장소를_해석한다(self):
        tpl, copies = self._copies()
        self.assertTrue(copies, "변형 사본을 하나도 못 찾았다 — 경로 패턴을 확인하라")
        stale = [p.relative_to(tpl).parts[0] for p in copies
                 if p.relative_to(tpl).parts[0] not in self.FROZEN
                 and self.MARKER not in p.read_text(encoding="utf-8")]
        self.assertEqual(stale, [], f"cwd 기준 판정이 남은 변형: {stale}")

    def test_메인과_활성_변형이_바이트_동일하다(self):
        tpl, copies = self._copies()
        want = _HOOK.read_bytes()
        diff = [p.relative_to(tpl).parts[0] for p in copies
                if p.relative_to(tpl).parts[0] not in self.FROZEN
                and p.read_bytes() != want]
        self.assertEqual(diff, [], f"메인과 내용이 다른 변형: {diff}")

    def test_동결_제외_목록이_늘어나지_않았다(self):
        """제외가 슬그머니 늘어나면 '고쳤다'는 말이 거짓이 된다."""
        self.assertEqual(self.FROZEN, {"claude"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
