"""LINT-CO · LINT-FREEZE — 내용 오버레이와 동결 스냅샷의 가드 (F021 / ADR-015 결정 5·6).

이 묶음이 지켜야 하는 것은 **양방향**이다:

  - 사고 재현(M1·M2·M3)이 **잡히고**
  - 정당한 편집(N1)이 **안 잡힌다**

둘 중 하나라도 뒤집히면 설계가 틀린 것이다. 특히 **N1 을 빼면 안 된다** — N1 없는
테스트 묶음은 "무조건 BLOCK 내는 검사기" 와 구별되지 않는다.

fixture 규율 (F020 이 비싸게 배운 것, `docs/reviews/F020-disposition.md`):
  - 변이와 실행은 **같은 트리**에서. 다른 트리에서 돌리면 skip 되어 "생존" 으로 보인다.
  - fixture 가 **진짜로 만들어졌는지** 먼저 단언한다. 중첩이 어긋난 fixture 에서
    기준선이 거짓 BLOCK 18건을 낸 적이 있다 — 그대로 믿었으면 결론이 통째로 틀렸다.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_LINT = _ROOT / ".claude" / "bin" / "lint.py"

#: fixture 에 둘 변형 — 실제 이름이어야 `_CO_AXES` 멤버십이 성립한다
_FIXTURE_VARIANTS = ("claude", "claude.gstack", "claude.loope",
                     "claude.aif", "localllm", "localllm.nem")


def _load_lint():
    spec = importlib.util.spec_from_file_location("_lint_under_test", _LINT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class OverlayFixture(unittest.TestCase):
    """실제 `lint.py` 를 fixture 루트에 복사해 **그 사본을 돌린다**.

    `_PROJECT_ROOT` 가 `__file__` 에서 파생되므로, 사본을 두면 그 트리가 프로젝트 루트가
    된다. 환경변수로 바꿀 수 없어서 이 방식이다.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / ".claude" / "bin").mkdir(parents=True)
        self._copy_lint_with_fixture_axes()
        self.ht = self.root / "src" / "harness_template"
        for v in _FIXTURE_VARIANTS:
            (self.ht / v / "harness" / ".claude" / "agents").mkdir(parents=True)
            (self.ht / v / "harness" / ".claude" / "commands").mkdir(parents=True)
        (self.root / ".claude" / "agents").mkdir(parents=True)
        (self.root / ".claude" / "commands").mkdir(parents=True)
        self._write_reviewer()
        self._write_retro()
        self._write_freeze_manifest()
        # 양의 목록(`_SCOPE_REQUIRED`)을 만족시킨다 — 안 채우면 모든 케이스가
        # "경로류가 비었다" BLOCK 에 묻혀 fixture 가 아무것도 구별하지 못한다.
        for prefix in _load_lint()._SCOPE_REQUIRED:
            for v in _FIXTURE_VARIANTS:
                if v == "claude":
                    continue        # 동결 변형은 LINT-CO 참여 대상이 아니다
                self._put(v, f"{prefix}keep.md", "same\n")

    def tearDown(self):
        self.tmp.cleanup()

    def _copy_lint_with_fixture_axes(self):
        """`lint.py` 를 복사하되 **선언 목록을 fixture 가 가진 파일로** 바꾼다.

        여기서 검증하는 것은 *우리 리포의 선언이 맞는가* 가 아니라 **메커니즘**이다.
        실제 선언 22종을 그대로 쓰면 fixture 에 없는 20종이 "선언했는데 스캔에 없다" 로
        터진다 — 그건 fixture 의 사정이지 결함이 아니다. 실제 선언의 건전성은
        `RealTreeCoverageTest` 가 실트리에서 본다.
        """
        import re
        src = _LINT.read_text(encoding="utf-8")
        new = ('_CONTENT_OVERLAY_AXES = {\n'
               '    ".claude/agents/reviewer.md": {"loop", "aif"},\n'
               '    ".claude/commands/retro.md": {"loop"},\n'
               '}\n')
        patched, n = re.subn(r"_CONTENT_OVERLAY_AXES = \{.*?\n\}\n", new, src,
                             count=1, flags=re.S)
        assert n == 1, "선언 블록을 못 찾았다 — fixture 가 실제 선언을 쓰게 된다"
        (self.root / ".claude" / "bin" / "lint.py").write_text(patched, encoding="utf-8")

    # ── fixture 작성 ─────────────────────────────────────────────────
    def _put(self, variant: str | None, rel: str, text: str) -> Path:
        base = self.root if variant is None else self.ht / variant / "harness"
        p = base / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        return p

    def _write_reviewer(self):
        """축 {loop, aif} — 실제 `reviewer.md` 의 분할 모양 그대로."""
        base, loop, aif = "# reviewer\nbase\n", "# reviewer\nbase\nLoop 2\n", \
                          "# reviewer\nbase\nLoop 2\nADR-020\n"
        self._put(None, ".claude/agents/reviewer.md", loop)       # MAIN ≡ loope
        self._put("claude.gstack", ".claude/agents/reviewer.md", base)
        self._put("claude.loope", ".claude/agents/reviewer.md", loop)
        self._put("localllm", ".claude/agents/reviewer.md", loop)
        self._put("localllm.nem", ".claude/agents/reviewer.md", loop)
        self._put("claude.aif", ".claude/agents/reviewer.md", aif)
        self._put("claude", ".claude/agents/reviewer.md", "# reviewer\nphase0\n")   # 동결

    def _write_retro(self):
        """축 {loop} — 미선언 축 변이(N3)의 대상."""
        base, loop = "# retro\nbase\n", "# retro\nbase\nLoop 4\n"
        self._put(None, ".claude/commands/retro.md", loop)
        self._put("claude.gstack", ".claude/commands/retro.md", base)
        for v in ("claude.loope", "localllm", "localllm.nem", "claude.aif"):
            self._put(v, ".claude/commands/retro.md", loop)
        self._put("claude", ".claude/commands/retro.md", "# retro\nphase0\n")

    def _write_freeze_manifest(self):
        files = {}
        for q in sorted((self.ht / "claude").rglob("*")):
            if q.is_file():
                files[str(q.relative_to(self.root))] = {
                    "sha256": hashlib.sha256(q.read_bytes()).hexdigest(),
                    "reason": "phase0"}
        (self.root / ".claude" / "freeze-manifest.json").write_text(
            json.dumps({"files": files}, ensure_ascii=False, indent=2), encoding="utf-8")

    # ── 실행 ─────────────────────────────────────────────────────────
    def _run(self, checker: str) -> tuple:
        res = subprocess.run(
            [sys.executable, str(self.root / ".claude" / "bin" / "lint.py"),
             "check", "--only", checker],
            capture_output=True, text=True, cwd=str(self.root))
        out = res.stdout
        blocks = [ln for ln in out.splitlines() if "| BLOCK |" in ln]
        return blocks, out

    # ── 0. fixture 자체가 성립하는가 ─────────────────────────────────
    def test_fixture_가_올바르고_기준선이_깨끗하다(self):
        """이 단언이 **먼저** 와야 한다.

        중첩이 어긋난 fixture(`harness/.claude/.claude`)에서 기준선이 거짓 BLOCK 18건을
        낸 전례가 있다. 그 상태에서 변이를 걸면 "잡혔다" 가 전부 거짓이 된다.
        """
        self.assertFalse(list(self.root.rglob(".claude/.claude")),
                         "fixture 가 중첩됐다 — 기준선이 거짓 BLOCK 을 낸다")
        self.assertTrue((self.ht / "claude.loope" / "harness" / ".claude" /
                         "agents" / "reviewer.md").is_file())
        for checker in ("LINT-CO", "LINT-FREEZE"):
            blocks, out = self._run(checker)
            self.assertEqual(blocks, [], f"{checker} 기준선이 깨끗하지 않다:\n{out}")
        out = self._run("LINT-CO")[1]
        self.assertIn("공유 파일", out, "공유 파일을 하나도 못 찾았다 — 검사기가 공회전한다")
        # 이 fixture 는 git 리포가 **아니다** → 추적 목록을 못 얻으므로 디스크로 내려간다.
        # 그 강등이 **조용하면** 안 된다 — 로컬 산출물이 섞여 거짓 BLOCK 이 날 수 있는데
        # 아무도 모른다. CONCERN 이 뜨는지 고정한다 (그걸 지우는 변이가 생존했다).
        self.assertIn("git 추적 목록 없음", out,
                      "git 없이 디스크를 훑으면서 아무 말도 하지 않았다 — 조용한 강등이다")

    # ── M1·M3: 2026-10-19 사고 재현 ──────────────────────────────────
    def test_M1_일괄복사가_오버레이를_지우면_잡힌다(self):
        """사고 본체 — main 사본을 전 변형에 복사하면 세 프로필이 한 내용이 된다."""
        src = (self.root / ".claude" / "agents" / "reviewer.md").read_text(encoding="utf-8")
        for v in _FIXTURE_VARIANTS:
            self._put(v, ".claude/agents/reviewer.md", src)
        blocks, out = self._run("LINT-CO")
        self.assertTrue(blocks, f"일괄 복사가 잡히지 않았다:\n{out}")
        self.assertIn("오버레이 소실", "\n".join(blocks))
        self.assertIn("reviewer.md", "\n".join(blocks))

    def test_M3_aif_의_의도된_차이가_지워지면_잡힌다(self):
        """aif 2 사본만 loop 내용으로 되돌리는 — 미러 사고의 실제 모양."""
        loop = (self.ht / "claude.loope" / "harness" / ".claude" / "agents" /
                "reviewer.md").read_text(encoding="utf-8")
        self._put("claude.aif", ".claude/agents/reviewer.md", loop)
        blocks, out = self._run("LINT-CO")
        self.assertTrue(blocks, f"aif 차이 소실이 잡히지 않았다:\n{out}")
        self.assertIn("오버레이 소실", "\n".join(blocks))

    # ── M2: LINT-CO 가 **못 잡는다**는 사실을 고정한다 ───────────────
    def test_M2_baseline_덮어쓰기는_CO_가_아니라_FREEZE_가_잡는다(self):
        """역할 분담을 고정한다 — 둘을 한 검사기로 합치려는 다음 사람을 위해.

        동결을 축으로 모델링하면 "baseline 은 늘 달라야 한다" 가 되어 Karpathy 동기화가
        영구 금지된다. 그래서 별도 기전이고, 그 경계가 여기서 실측으로 남는다.
        """
        loop = (self.ht / "claude.loope" / "harness" / ".claude" / "agents" /
                "reviewer.md").read_text(encoding="utf-8")
        self._put("claude", ".claude/agents/reviewer.md", loop)
        co_blocks, _ = self._run("LINT-CO")
        self.assertEqual(co_blocks, [], "LINT-CO 가 동결 변형을 보고 있다 — 참여 제외여야 한다")
        fz_blocks, out = self._run("LINT-FREEZE")
        self.assertTrue(fz_blocks, f"동결 위반이 잡히지 않았다:\n{out}")
        self.assertIn("동결 파일이 바뀌었다", "\n".join(fz_blocks))

    # ── N1: 음성 대조 — 이것이 통과해야 설계가 성립한다 ──────────────
    def test_N1_모든_비동결_사본에_같은_수정은_통과한다(self):
        """**이 테스트를 빼면 안 된다.**

        기대 해시 표였다면 여기서 갈래 수만큼 틀어진다. 파생 분할을 고른 이유가
        정확히 이것이다 — `reviewer.md` 는 리뷰어 행동을 조정할 때마다 바뀐다.
        """
        for variant in (None, "claude.gstack", "claude.loope", "localllm",
                        "localllm.nem", "claude.aif"):
            base = self.root if variant is None else self.ht / variant / "harness"
            p = base / ".claude" / "agents" / "reviewer.md"
            p.write_text(p.read_text(encoding="utf-8") + "\n공통 규율 한 줄 추가\n",
                         encoding="utf-8")
        blocks, out = self._run("LINT-CO")
        self.assertEqual(blocks, [], f"정당한 편집이 BLOCK 됐다 — 검사기가 과하다:\n{out}")

    # ── N2·N3: 부분 미러와 미선언 축 ─────────────────────────────────
    def test_N2_부분_미러가_잡힌다(self):
        """같은 프로필(loop) 안에서 일부만 편집 — 수정이 갈 곳에 다 가지 않은 것."""
        for variant in (None, "claude.loope"):
            base = self.root if variant is None else self.ht / variant / "harness"
            p = base / ".claude" / "agents" / "reviewer.md"
            p.write_text(p.read_text(encoding="utf-8") + "\n여기만 고쳤다\n", encoding="utf-8")
        blocks, out = self._run("LINT-CO")
        self.assertTrue(blocks, f"부분 미러가 잡히지 않았다:\n{out}")
        self.assertIn("선언 안 된 분기", "\n".join(blocks))

    def test_선언되지_않은_파일은_축_공집합_기본값이다(self):
        """**검사기를 돌려서** 본다 — 전에는 테스트가 스스로 기본값을 계산했다.

        `self.assertEqual(_co_profile(v, _CONTENT_OVERLAY_AXES.get(rel, set())), frozenset())`
        는 동어반복이다. 테스트가 `.get(…, set())` 을 직접 넣으므로 **검사기의 기본값을
        보지 않는다**. 실제로 기본값을 fail-open(`set(_CO_AXES)`)으로 바꾸는 변이가 17건을
        전부 통과했다 (리뷰 MUST-4 / 변이 m8).

        선언 없는 파일은 축 ∅ 이어야 하므로 **모든 비동결 트리에서 같아야 한다**.
        fail-open 이면 프로필이 서로 달라져 갈려도 통과한다.
        """
        self._put("claude.gstack", ".claude/commands/handoff.md", "# handoff\nA\n")
        self._put("claude.loope", ".claude/commands/handoff.md", "# handoff\nB\n")
        blocks, out = self._run("LINT-CO")
        self.assertTrue(blocks, f"선언 없는 파일이 갈렸는데 통과했다 — 기본값이 "
                                f"fail-open 이다:\n{out}")
        self.assertIn("handoff.md", "\n".join(blocks))
        self.assertIn("선언 안 된 분기", "\n".join(blocks))

    def test_두_트리만_공유하는_파일도_검사한다(self):
        """공유 임계(`len(m) >= 2`)를 고정한다 — 임계를 올리는 변이가 생존했다.

        실트리에서 aif(2곳)·d2(3곳) 전용 파일이 정확히 그 구간이다. fixture 에 2 트리
        공유 파일이 없으면 임계가 아무것도 막지 않는다 (리뷰 SHOULD-7 / 변이 m7).
        """
        self._put("claude.aif", ".claude/commands/aif-judge.md", "# aif\nA\n")
        self._put("localllm.nem", ".claude/commands/aif-judge.md", "# aif\nB\n")
        blocks, out = self._run("LINT-CO")
        self.assertTrue(blocks, f"2 트리만 공유하는 파일이 검사에서 빠졌다:\n{out}")
        self.assertIn("aif-judge.md", "\n".join(blocks))

    def test_죽은_축_선언이_잡힌다(self):
        """축 안·밖 중 한쪽만 파일을 보유하면 그 선언은 아무것도 제약하지 않는다.

        검사기에서 이 검출(⓪)을 지워도 실트리 커버리지 테스트는 통과했다 — 그 테스트가
        검사기 대신 **데이터를 직접** 보기 때문이다 (재리뷰: 여섯 번째 공회전 형태).
        그래서 여기서 **검사기를 돌려** 고정한다.
        """
        # 이 fixture 에 **없는** 변형만 가진 축(`nw` = productnw)을 붙인다 → 이 파일을
        # 가진 변형 중 축 안이 비어 분할이 원리적으로 불가능해진다. 리뷰어가 실트리에서
        # `nw` 로 쓴 것과 같은 변이다.
        lintpy = self.root / ".claude" / "bin" / "lint.py"
        src = lintpy.read_text(encoding="utf-8")
        old_decl = '".claude/agents/reviewer.md": {"loop", "aif"},'
        self.assertEqual(src.count(old_decl), 1, "선언을 못 찾았다")
        lintpy.write_text(
            src.replace(old_decl, '".claude/agents/reviewer.md": {"loop", "aif", "nw"},', 1),
            encoding="utf-8")
        blocks, out = self._run("LINT-CO")
        self.assertTrue(blocks, f"죽은 축 선언이 잡히지 않았다:\n{out}")
        self.assertIn("죽은 축 선언", "\n".join(blocks))

    def test_읽지_못한_파일을_조용히_넘기지_않는다(self):
        """읽지 못한 파일은 그 트리에서 **사라져** 보유 수가 줄고 분할이 틀린 채 통과한다.

        F020 8차가 같은 모양(`UnicodeDecodeError ⊂ ValueError`)을 실측했다.
        """
        import os
        victim = self._put("claude.loope", ".claude/commands/locked.md", "x\n")
        self._put("claude.gstack", ".claude/commands/locked.md", "x\n")
        os.chmod(victim, 0o000)
        try:
            blocks, out = self._run("LINT-CO")
        finally:
            os.chmod(victim, 0o644)
        if os.geteuid() == 0:
            self.skipTest("root 는 권한을 무시해 읽기 실패를 만들 수 없다")
        self.assertTrue(blocks, f"읽지 못한 파일이 조용히 빠졌다:\n{out}")
        self.assertIn("읽지 못한 파일", "\n".join(blocks))

    def test_git_추적_밖_파일은_비교하지_않는다(self):
        """미러는 **추적되는 내용**에 대한 계약이다.

        디스크를 그대로 훑으면 로컬 산출물이 섞인다 — 실측: 메인의 gitignore 된
        `.opencode/` 가 d-2 변형들과 "갈린" 것으로 읽혀 거짓 BLOCK 8건을 냈다.
        """
        import subprocess
        env = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
               "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t", "PATH": os.environ["PATH"]}
        for cmd in (["git", "init", "-q"], ["git", "add", "-A"],
                    ["git", "-c", "commit.gpgsign=false", "commit", "-qm", "t"]):
            r = subprocess.run(cmd, cwd=str(self.root), capture_output=True, env=env)
            if r.returncode != 0:
                self.skipTest(f"git 사용 불가: {r.stderr[:120]}")
        # 커밋 **뒤에** 추적되지 않은 파일을 서로 다르게 둔다
        self._put("claude.gstack", ".claude/commands/scratch.md", "A\n")
        self._put("claude.loope", ".claude/commands/scratch.md", "B\n")
        blocks, out = self._run("LINT-CO")
        self.assertEqual(blocks, [],
                         f"git 추적 밖 파일을 비교했다 — 로컬 산출물이 섞인다:\n{out}")
        self.assertNotIn("git 추적 목록 없음", out,
                         "git 리포인데 추적 목록을 못 얻었다")

    def test_N3_선언되지_않은_축으로_갈리면_잡힌다(self):
        """`retro.md` 는 축 {loop} 로 선언돼 있다. loop 안에서 또 갈리면 미선언 축이다."""
        self._put("localllm.nem", ".claude/commands/retro.md",
                  "# retro\nbase\nLoop 4\nnem 전용 한 줄\n")
        blocks, out = self._run("LINT-CO")
        self.assertTrue(blocks, f"미선언 축이 잡히지 않았다:\n{out}")
        self.assertIn("retro.md", "\n".join(blocks))
        self.assertIn("선언 안 된 분기", "\n".join(blocks))


class RealTreeCoverageTest(unittest.TestCase):
    """AC3 의 **"미분류 0건"** 을 실트리에서 직접 단언한다.

    fixture 테스트는 "이 모양이 잡히는가" 를 본다. 그것만으로는 **범위를 좁혀** 통과하는
    것을 막지 못한다 — 실제로 처음 판은 `.claude/`·`docs/adr/` 만 훑어서, 바깥의 진짜
    drift(`docs/poc/measurements/06-harness-e2e.md`)와 미가드 내용 오버레이(`.opencode/`
    렌더 산출물 등 9종)를 못 봤다 (리뷰 MUST-2).

    그래서 여기서는 **실트리의 git 추적 공유 파일 전부**가 A(축 ∅ — 어디서나 동일) /
    B(`_CONTENT_OVERLAY_AXES`) / C(`_CO_VARIANT_LOCAL`) 중 하나로 설명되는지 본다.
    설명되지 않는 파일이 곧 "53번째 파일" 이다.
    """

    def setUp(self):
        self.lint = _load_lint()
        if not (_ROOT / "src" / "harness_template").is_dir():
            self.skipTest("템플릿 트리가 없는 변형 사본 — 실트리 검사 대상 아님")

    def test_공유_파일이_전부_A_B_C_중_하나로_분류된다(self):
        files, _, unread, untracked, links = self.lint._co_collect()
        self.assertEqual(unread, [], "읽지 못한 파일이 있다 — 그만큼 분류에서 빠진다")
        self.assertEqual(links, [], "미러에 심볼릭 링크가 있다 — 사본이 늘 같아 보인다")
        self.assertEqual(untracked, [],
                         "git 추적 목록 없이 디스크를 훑었다 — 로컬 산출물이 섞인다")
        shared = {rel: m for rel, m in files.items() if len(m) >= 2}
        # 하한을 적지 않는다 — 옛 범위(110)도 통과하던 숫자였다. 범위 축소는 아래
        # "선언했는데 스캔에 없다" 와 검사기의 같은 BLOCK 이 잡는다 (재리뷰 SHOULD-7).
        self.assertEqual(sorted(set(self.lint._CONTENT_OVERLAY_AXES) - set(files)), [],
                         "선언한 파일이 스캔에 없다 — 범위가 좁혀졌다")

        declared = set(self.lint._CONTENT_OVERLAY_AXES)
        unexplained = []
        for rel, obs in shared.items():
            if len(set(obs.values())) == 1:
                continue                      # (A) 어디서나 동일
            if rel in declared:
                continue                      # (B) 축 선언됨
            unexplained.append(rel)           # (C) 는 `_co_collect` 가 이미 제외한다
        self.assertEqual(sorted(unexplained), [],
                         "내용이 갈렸는데 A·B·C 어디에도 없다 — AC3 의 '미분류 0건' 위반. "
                         "의도된 오버레이면 `_CONTENT_OVERLAY_AXES` 에, 변형 로컬이면 "
                         "`_CO_VARIANT_LOCAL` 에 **사유와 함께** 등재하라")

    def test_제외가_사유와_가드_없이_늘지_않는다(self):
        """제외는 곧 *어떤 검사도 보지 않는 파일*을 만드는 일이다 (ADR-015 결정 2).

        구조는 `ScopeRuleTableTest` 가 보고, 여기서는 **실트리에서 실제로 쓰이는**
        규칙만 추려 사유·가드를 다시 본다 — 죽은 행은 아래 테스트가 따로 잡는다.
        """
        for rule in self.lint._SCOPE_RULES:
            with self.subTest(pattern=rule["pattern"]):
                self.assertGreaterEqual(len(rule["reason"]), 10)
                self.assertGreaterEqual(len(rule["guard"]), 5)

    def test_선언된_축이_전부_살아_있다(self):
        """죽은 선언은 "여기는 갈려도 된다" 는 **거짓 신호**를 남긴다."""
        files, *_ = self.lint._co_collect()
        dead = []
        for rel, axes in self.lint._CONTENT_OVERLAY_AXES.items():
            obs = files.get(rel)
            if not obs:
                dead.append(f"{rel}: 파일이 없다")
                continue
            members = {("claude.loope" if v == "MAIN" else v) for v in obs}
            for axis in axes:
                inside = members & set(self.lint._CO_AXES[axis])
                if not inside or inside == members:
                    dead.append(f"{rel}: 축 '{axis}'")
        self.assertEqual(dead, [], f"죽은 축 선언: {dead}")


class FreezeManifestTest(unittest.TestCase):
    """`LINT-FREEZE` 의 사유 검증 — 해시만으로는 사유 날조를 못 본다."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / ".claude" / "bin").mkdir(parents=True)
        shutil.copy2(_LINT, self.root / ".claude" / "bin" / "lint.py")
        self.target = (self.root / "src" / "harness_template" / "claude" /
                       "harness" / ".claude" / "agents" / "developer.md")
        self.target.parent.mkdir(parents=True)
        self.target.write_text("# developer\n## Simplicity First\n본문\n", encoding="utf-8")
        self._manifest("karpathy")

    def tearDown(self):
        self.tmp.cleanup()

    def _manifest(self, reason: str, sha: str | None = None):
        (self.root / ".claude" / "freeze-manifest.json").write_text(json.dumps({
            "files": {str(self.target.relative_to(self.root)): {
                "sha256": sha or hashlib.sha256(self.target.read_bytes()).hexdigest(),
                "reason": reason}}}, ensure_ascii=False), encoding="utf-8")

    def _blocks(self) -> list:
        res = subprocess.run(
            [sys.executable, str(self.root / ".claude" / "bin" / "lint.py"),
             "check", "--only", "LINT-FREEZE"],
            capture_output=True, text=True, cwd=str(self.root))
        return [ln for ln in res.stdout.splitlines() if "| BLOCK |" in ln]

    def test_기준선은_통과한다(self):
        self.assertEqual(self._blocks(), [])

    def test_허용되지_않은_사유는_거부된다(self):
        self._manifest("because-i-said-so")
        self.assertIn("사유가 허용값이 아니다", "\n".join(self._blocks()))

    def test_karpathy_사유인데_4원칙이_없으면_거부된다(self):
        """사유가 거짓인 경우 — 해시만 보면 통과한다.

        `must_contain` 앵커라 리워딩되면 **시끄럽게** 실패한다. `must_not_contain`
        이었다면 조용히 vacuous 가 됐을 것이다.
        """
        self.target.write_text("# developer\n아무 원칙도 없다\n", encoding="utf-8")
        self._manifest("karpathy")
        self.assertIn("4원칙 제목이 하나도 없다", "\n".join(self._blocks()))

    def test_매니페스트에_없는_동결_파일이_있으면_거부된다(self):
        """새로 들어온 파일은 동결 밖이라 아무 가드도 보지 않는다."""
        (self.target.parent / "slipped-in.md").write_text("몰래", encoding="utf-8")
        self.assertIn("매니페스트에 없는 파일", "\n".join(self._blocks()))

    def test_동결_밀반입은_중간_디렉토리_이름으로_숨을_수_없다(self):
        """같은 bare-name 구멍이 `LINT-SSOT`·`LINT-CO`·`LINT-FREEZE` 에 **각각** 났다.

        각자 손으로 적었기 때문이고, 그래서 하나의 표로 모았다. 실측: 전에는
        `agents/evil.md` 는 BLOCK 인데 그 아래 `state/`·`node_modules/`·
        `.pytest_cache/` 를 한 겹 끼우면 전부 **0 BLOCK** 이었다.
        """
        base = self.target.parent
        for mid in ("", "state/", "node_modules/", ".pytest_cache/"):
            with self.subTest(mid=mid or "(루트)"):
                d = base / mid if mid else base
                d.mkdir(parents=True, exist_ok=True)
                (d / "slipped.md").write_text("몰래", encoding="utf-8")
                try:
                    self.assertIn("매니페스트에 없는 파일", "\n".join(self._blocks()),
                                  f"'{mid}' 를 끼우니 밀반입이 숨었다")
                finally:
                    (d / "slipped.md").unlink()

    def test_매니페스트가_비었으면_공회전하지_않는다(self):
        (self.root / ".claude" / "freeze-manifest.json").write_text(
            json.dumps({"files": {}}), encoding="utf-8")
        self.assertIn("공회전", "\n".join(self._blocks()))


class ScopeRuleTableTest(unittest.TestCase):
    """제외 **규칙 표**를 순회한다 — F021 AC6 의 본체.

    세 라운드 연속 같은 모양의 결함이 난 원인은 테스트를 덜 써서가 아니라, **규칙이
    흩어진 상수·조건문으로만 존재해서** 테스트가 언제나 "직전에 고친 그 규칙 하나" 만
    겨냥할 수 있었던 것이다. 그래서 다음 규칙이 추가되면 또 구멍이 났다
    (mC·mD·mH·mT2 가 전부 그 모양).

    여기서는 **규칙이 자기 증인을 들고** 있고 테스트가 표를 순회한다 — 행을 추가하면
    테스트가 **자동으로 따라온다**. 그것이 "제외 규칙이 하나 늘 때 테스트가 따라오는가"
    라는 판단 기준에 대한 답이다.
    """

    def setUp(self):
        self.lint = _load_lint()

    def test_모든_제외규칙이_증인과_가드를_갖는다(self):
        """증인 없는 행은 그 자체로 결함이다 — 아무것도 고정하지 않으면서 범위만 줄인다."""
        for rule in self.lint._SCOPE_RULES:
            with self.subTest(pattern=rule.get("pattern")):
                for field in ("kind", "pattern", "scope", "reason", "guard",
                              "inside", "outside"):
                    self.assertIn(field, rule, f"필수 필드 누락: {field}")
                self.assertIn(rule["kind"], ("exact", "prefix", "anydir"))
                self.assertTrue(rule["scope"] <= {"ssot", "co", "freeze"},
                                f"알 수 없는 scope: {rule['scope']}")
                self.assertTrue(rule["scope"], "scope 가 비었다 — 아무 데도 적용되지 않는다")
                self.assertGreaterEqual(len(rule["reason"]), 10, "사유가 너무 짧다")
                self.assertGreaterEqual(len(rule["guard"]), 5, "가드 서술이 없다")
                self.assertTrue(rule["inside"], "inside 증인이 없다")
                self.assertTrue(rule["outside"], "outside 증인이 없다")

    def test_증인이_의도한_행에_걸린다(self):
        """**부울이 아니라 매칭된 행의 정체**를 단언한다.

        부울만 보면 다른 행에 흡수된 **죽은 행**이 조용히 통과한다.
        """
        for rule in self.lint._SCOPE_RULES:
            for scope in sorted(rule["scope"]):
                for path in rule["inside"]:
                    with self.subTest(scope=scope, rule=rule["pattern"], inside=path):
                        hit = self.lint._scope_match(path, scope)
                        self.assertIsNotNone(hit, "이 행이 제외해야 하는데 안 한다")
                        self.assertEqual(hit["pattern"], rule["pattern"],
                                         f"다른 행({hit['pattern']})이 흡수했다 — "
                                         "이 행은 죽은 행이다")
                for path in rule["outside"]:
                    with self.subTest(scope=scope, rule=rule["pattern"], outside=path):
                        hit = self.lint._scope_match(path, scope)
                        self.assertIsNone(
                            hit, f"이웃 경로가 제외됐다 — 통로가 한 칸 넓다 "
                                 f"(걸린 행: {hit['pattern'] if hit else None})")

    def test_anydir_는_캐시와_VCS_에만_쓴다(self):
        """내용 디렉토리를 `anydir` 로 두면 전혀 다른 경로가 함께 사라진다.

        `docs/design/` 이 `design` 이라는 이름 하나로 통째로 빠진 것이 그 사고였고,
        같은 결함이 `LINT-SSOT`·`LINT-CO`·`LINT-FREEZE` 에 **각각** 났다.
        """
        allowed = {"__pycache__", ".git", "node_modules", ".pytest_cache",
                   ".venv", ".mypy_cache"}
        for rule in self.lint._SCOPE_RULES:
            if rule["kind"] == "anydir":
                self.assertIn(rule["pattern"], allowed,
                              f"'{rule['pattern']}' 는 캐시·VCS 가 아니다 — "
                              "루트 상대 `prefix` 로 쓰라")

    def test_필수_경로류가_제외와_겹치지_않는다(self):
        """양의 목록과 음의 목록이 모순이면 둘 중 하나는 거짓이다."""
        for prefix in self.lint._SCOPE_REQUIRED:
            with self.subTest(prefix=prefix):
                hit = self.lint._scope_match(prefix + "sample.md", "co")
                self.assertIsNone(hit, f"필수 경로류가 제외된다 (행: "
                                       f"{hit['pattern'] if hit else None})")


class ScopeWitnessFixtureTest(unittest.TestCase):
    """증인 경로를 **실제 검사기**에 태운다 — 데이터 순회만으로는 동작을 못 본다."""

    #: 두 변형이면 분할 비교가 성립한다
    _V = ("claude.gstack", "claude.loope")

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / ".claude" / "bin").mkdir(parents=True)
        shutil.copy2(_LINT, self.root / ".claude" / "bin" / "lint.py")
        self.lint = _load_lint()
        self.ht = self.root / "src" / "harness_template"
        for v in self._V:
            (self.ht / v / "harness").mkdir(parents=True)
        # 양의 목록을 만족시킨다 — 안 그러면 모든 케이스가 그 BLOCK 에 묻힌다
        for prefix in self.lint._SCOPE_REQUIRED:
            self._put_all(f"{prefix}keep.md", "same\n", "same\n")

    def tearDown(self):
        self.tmp.cleanup()

    def _put_all(self, rel: str, a: str, b: str):
        for v, body in zip(self._V, (a, b)):
            q = self.ht / v / "harness" / rel
            q.parent.mkdir(parents=True, exist_ok=True)
            q.write_text(body, encoding="utf-8")

    def _blocks(self) -> str:
        res = subprocess.run(
            [sys.executable, str(self.root / ".claude" / "bin" / "lint.py"),
             "check", "--only", "LINT-CO"],
            capture_output=True, text=True, cwd=str(self.root))
        return "\n".join(l for l in res.stdout.splitlines() if "| BLOCK |" in l)

    def test_증인_경계가_실제_검사에서_지켜진다(self):
        """`inside` 는 제외되고 `outside` 는 **갈리면 BLOCK** 이어야 한다.

        규칙마다 돌린다 — 행을 추가하면 이 테스트가 자동으로 그 행을 태운다.
        """
        for rule in self.lint._SCOPE_RULES:
            if "co" not in rule["scope"]:
                continue
            if rule["pattern"] == ".git":
                continue        # fixture 에 가짜 .git 을 만들면 git 경계가 흔들린다
            for path in rule["inside"]:
                with self.subTest(rule=rule["pattern"], inside=path):
                    self._put_all(path, "A\n", "B\n")
                    self.assertNotIn(path, self._blocks(),
                                     "제외되어야 할 경로가 BLOCK 됐다")
            for path in rule["outside"]:
                with self.subTest(rule=rule["pattern"], outside=path):
                    self._put_all(path, "A\n", "B\n")
                    self.assertIn(path, self._blocks(),
                                  "제외하면 안 되는 이웃인데 BLOCK 이 안 났다 — "
                                  "통로가 한 칸 넓다")

    def test_범위_필수_경로류가_전부_살아_있다(self):
        """제외가 넓어져 경로류가 통째로 비면 `lint --strict` 가 막아야 한다.

        실측(mH): 파생으로 `hooks/` 가 빠졌을 때 37 테스트와 `lint --strict` 가
        **전부 통과**했다. 테스트만으로는 못 막는다.
        """
        out = self._blocks()
        for prefix in self.lint._SCOPE_REQUIRED:
            self.assertNotIn(f"| {prefix} |", out, f"{prefix} 가 비었다")
        # 경로류 하나를 지우면(=파일을 다른 데로 옮기면) BLOCK 이 나야 한다
        victim = ".claude/hooks/"
        for v in self._V:
            (self.ht / v / "harness" / victim / "keep.md").unlink()
        self.assertIn(victim, self._blocks(),
                      "경로류가 비었는데 BLOCK 이 안 났다")

    def _patch_axes(self, body: str):
        """fixture 의 `lint.py` 선언을 갈아끼운다 — 메커니즘 검증이다."""
        import re
        q = self.root / ".claude" / "bin" / "lint.py"
        src = q.read_text(encoding="utf-8")
        patched, n = re.subn(r"^_CONTENT_OVERLAY_AXES = \{.*?\n\}\n", body, src,
                             count=1, flags=re.S | re.M)
        self.assertEqual(n, 1, "선언 블록을 못 찾았다")
        q.write_text(patched, encoding="utf-8")

    def test_선언했는데_스캔에_없으면_BLOCK_이다(self):
        """범위가 좁아지면 `lint --strict` **단독**으로 막혀야 한다.

        전에는 테스트에서만 잡히고 게이트는 열려 있었다 (재리뷰 SHOULD-5).
        """
        self._patch_axes('_CONTENT_OVERLAY_AXES = {\n'
                         '    ".claude/commands/nowhere.md": {"loop"},\n'
                         '}\n')
        out = self._blocks()
        self.assertIn("nowhere.md", out, "선언한 파일이 없는데 통과했다")
        self.assertIn("스캔에 없다", out)

    def test_사본이_하나뿐인_파일은_내용_오버레이가_아니다(self):
        """보유 1 은 `shared`(≥2)·`missing`(0) 어디에도 없어 **둘 다에서 빠졌다**.

        그래서 테스트는 빨간데 `lint --strict` 는 exit 0 이었다 — 여섯 번째 공회전
        형태의 역상(검사기가 테스트보다 덜 안다). 내용 오버레이는 사본이 둘 이상일
        때만 성립하는 개념이므로 **정의상** BLOCK 이다.
        """
        only = self.ht / self._V[0] / "harness" / ".claude" / "commands" / "solo.md"
        only.parent.mkdir(parents=True, exist_ok=True)
        only.write_text("only here\n", encoding="utf-8")
        self._patch_axes('_CONTENT_OVERLAY_AXES = {\n'
                         '    ".claude/commands/solo.md": {"loop"},\n'
                         '}\n')
        out = self._blocks()
        self.assertIn("solo.md", out, "단일 보유 선언이 통과했다")
        self.assertIn("사본이 하나뿐", out)

    def test_symlink_은_스캔에서_조용히_빠지지_않는다(self):
        """실측 mS3: 변형 사본을 main 으로 링크하면 부분 미러가 BLOCK 1 → **0** 이었다."""
        self._put_all(".claude/commands/x.md", "A\n", "B\n")
        self.assertIn("x.md", self._blocks(), "전제가 깨졌다")
        tgt = self.ht / self._V[1] / "harness" / ".claude" / "commands" / "x.md"
        tgt.unlink()
        tgt.symlink_to(self.ht / self._V[0] / "harness" / ".claude" / "commands" / "x.md")
        out = self._blocks()
        self.assertIn("symlink", out,
                      "링크가 조용히 빠졌다 — 사본이 늘 같아 보여 부분 미러가 사라진다")


class GateFailureTest(unittest.TestCase):
    """**검사기가 죽으면 어떻게 되는가** — 다섯 번째 공회전 형태 (재리뷰 MUST-3).

    runner 는 예외를 INFO 로 강등했고 `--strict` 는 INFO 를 세지 않았다. 그래서 검사기를
    죽이는 입력 하나가 게이트를 통째로 여는 통로였다. 동작은 고쳤는데 **테스트가 0건**
    이어서 그 수정 자체가 회귀에 무방비였다.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / ".claude" / "bin").mkdir(parents=True)
        self.lint = self.root / ".claude" / "bin" / "lint.py"
        shutil.copy2(_LINT, self.lint)

    def tearDown(self):
        self.tmp.cleanup()

    def _inject_raise(self, func: str):
        src = self.lint.read_text(encoding="utf-8")
        marker = f"def {func}() -> list:\n"
        self.assertEqual(src.count(marker), 1, f"{func} 를 못 찾았다")
        self.lint.write_text(
            src.replace(marker, marker + '    raise RuntimeError("죽었다")\n', 1),
            encoding="utf-8")

    def _run(self, checker: str) -> tuple:
        res = subprocess.run([sys.executable, str(self.lint), "check",
                              "--only", checker, "--strict"],
                             capture_output=True, text=True, cwd=str(self.root))
        return res.returncode, res.stdout

    def test_게이트_검사기가_죽으면_BLOCK_이고_strict_가_막는다(self):
        self._inject_raise("check_content_overlay")
        code, out = self._run("LINT-CO")
        self.assertEqual(code, 1, f"게이트 검사기가 죽었는데 통과했다:\n{out}")
        self.assertIn("| BLOCK |", out)
        self.assertIn("검사기 실행 실패", out)

    def test_비게이트_검사기는_죽어도_INFO_다(self):
        """훅의 관용은 훅의 것이지 게이트 검사기의 것이 아니다 — 경계를 고정한다."""
        self._inject_raise("check_learn")
        code, out = self._run("LINT-LEARN")
        self.assertEqual(code, 0, f"비게이트 검사기가 게이트처럼 막았다:\n{out}")
        self.assertIn("| INFO |", out)


class FreezeManifestShapeTest(unittest.TestCase):
    """매니페스트 **손상 3종** — 문법이 맞아도 모양이 틀리면 전면 거부다 (ADR-015 결정 6).

    `[]` 는 전에 `.get()` 에서 AttributeError 를 냈고, 그것이 INFO 로 강등돼 `--strict`
    가 **exit 0** 이었다. 두 수정(형태 검사 · 게이트 예외 BLOCK)이 서로를 가리므로
    **메시지 수준**으로 각각 고정한다.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / ".claude" / "bin").mkdir(parents=True)
        shutil.copy2(_LINT, self.root / ".claude" / "bin" / "lint.py")
        (self.root / "src" / "harness_template" / "claude" / "harness").mkdir(parents=True)

    def tearDown(self):
        self.tmp.cleanup()

    def _run(self, body: str) -> tuple:
        (self.root / ".claude" / "freeze-manifest.json").write_text(body, encoding="utf-8")
        res = subprocess.run([sys.executable, str(self.root / ".claude" / "bin" / "lint.py"),
                              "check", "--only", "LINT-FREEZE", "--strict"],
                             capture_output=True, text=True, cwd=str(self.root))
        return res.returncode, res.stdout

    def test_최상위가_dict_가_아니면_모양_오류로_거부된다(self):
        code, out = self._run("[]")
        self.assertEqual(code, 1, f"`[]` 손상이 통과했다:\n{out}")
        self.assertIn("매니페스트 모양이 틀렸다", out)

    def test_files_가_dict_가_아니면_거부된다(self):
        code, out = self._run('{"files": []}')
        self.assertEqual(code, 1)
        self.assertIn("매니페스트 모양이 틀렸다", out)

    def test_깨진_JSON_은_읽기_실패로_거부된다(self):
        code, out = self._run("{broken")
        self.assertEqual(code, 1)
        self.assertIn("읽지 못했다", out)

    def test_비었으면_공회전하지_않는다(self):
        code, out = self._run('{"files": {}}')
        self.assertEqual(code, 1)
        self.assertIn("공회전", out)


class DocSymbolTest(unittest.TestCase):
    """`LINT-DOC` — 문서가 코드를 인용하되 복제하지 않는가 (ADR-015 결정 8).

    숫자·심볼 인용이 낡은 것이 **네 번째**였고, "세는 명령을 적는다" 는 규율은 사람의
    기억에 의존해 네 번 다 실패했다. 기계가 볼 수 있는 만큼만 기계에 맡긴다.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / ".claude" / "bin").mkdir(parents=True)
        shutil.copy2(_LINT, self.root / ".claude" / "bin" / "lint.py")
        (self.root / "docs" / "adr").mkdir(parents=True)
        (self.root / "CLAUDE.md").write_text("# h\n", encoding="utf-8")
        self.adr = self.root / "docs" / "adr" / "ADR-001-x.md"

    def tearDown(self):
        self.tmp.cleanup()

    def _run(self, body: str) -> tuple:
        self.adr.write_text(body, encoding="utf-8")
        res = subprocess.run([sys.executable, str(self.root / ".claude" / "bin" / "lint.py"),
                              "check", "--only", "LINT-DOC", "--strict"],
                             capture_output=True, text=True, cwd=str(self.root))
        return res.returncode, res.stdout

    def test_실재하는_심볼_인용은_통과한다(self):
        code, out = self._run("`_SCOPE_RULES` 가 SSOT 다.\n")
        self.assertEqual(code, 0, f"실재 심볼인데 막혔다:\n{out}")

    def test_없는_심볼을_인용하면_BLOCK_이다(self):
        """개명 리팩터가 문서를 끌고 가게 하는 장치다 — `_CO_SKIP_DIRS` 가 그렇게 남았다."""
        code, out = self._run("`_CO_SKIP_DIRS` 와 아래 둘뿐이다.\n")
        self.assertEqual(code, 1, f"유령 심볼이 통과했다:\n{out}")
        self.assertIn("_CO_SKIP_DIRS", out)

    def test_숫자는_출처를_달면_기계가_맞춘다(self):
        code, _ = self._run("규칙 <!-- lint:len _SCOPE_RULES -->99<!-- /lint --> 행.\n")
        self.assertEqual(code, 1, "틀린 숫자가 통과했다")
        import importlib.util
        spec = importlib.util.spec_from_file_location("_l", _LINT)
        mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
        n = len(mod._SCOPE_RULES)
        code, out = self._run(f"규칙 <!-- lint:len _SCOPE_RULES -->{n}<!-- /lint --> 행.\n")
        self.assertEqual(code, 0, f"맞는 숫자가 막혔다:\n{out}")

    def test_환경변수_같은_비코드_심볼은_허용된다(self):
        code, out = self._run("`CLAUDE_PROJECT_DIR` 아래에서 돈다.\n")
        self.assertEqual(code, 0, f"허용 목록이 동작하지 않는다:\n{out}")


class OverlayDeclarationTest(unittest.TestCase):
    """선언 자체의 규율 — 표가 낡는 경로를 막는다."""

    def setUp(self):
        self.lint = _load_lint()

    def test_CO_AXES_는_기존_상수를_재나열하지_않고_참조한다(self):
        """재나열하면 두 목록이 갈라지고, 그것이 지금 고치는 결함 그 자체다."""
        expected = {
            "design": "_VARIANTS_WITH_DESIGN", "wiki": "_VARIANTS_WITH_WIKI",
            "orch": "_VARIANTS_WITH_ORCH", "d2": "_VARIANTS_WITH_D2",
            "hermes": "_VARIANTS_WITH_HERMES", "pm": "_VARIANTS_WITH_PM",
            "nw": "_VARIANTS_WITH_NW", "loop": "_VARIANTS_WITH_LOOP",
            "aif": "_VARIANTS_WITH_AIF", "atl": "_VARIANTS_WITH_ATLASSIAN",
            "model_nem": "_VARIANTS_WITH_MODEL_NEM",
        }
        self.assertEqual(set(self.lint._CO_AXES), set(expected))
        for axis, const in expected.items():
            self.assertIs(self.lint._CO_AXES[axis], getattr(self.lint, const),
                          f"축 '{axis}' 가 {const} 를 **참조**하지 않고 재나열했다")


    def test_MAIN_은_loope_프로필로_환산된다(self):
        """ADR-015: main ≡ loope. 환산하지 않으면 main 이 늘 '(base)' 로 읽힌다."""
        self.assertEqual(self.lint._co_profile("MAIN", {"loop", "aif"}), frozenset({"loop"}))
        self.assertEqual(self.lint._co_profile("claude.aif", {"loop", "aif"}),
                         frozenset({"loop", "aif"}))

    def test_동결_변형은_CO_에_참여하지_않는다(self):
        self.assertEqual(set(self.lint._CO_FROZEN), {"claude", "openai"})

    def test_선언된_축은_전부_CO_AXES_에_있다(self):
        used = {a for ax in self.lint._CONTENT_OVERLAY_AXES.values() for a in ax}
        self.assertEqual(used - set(self.lint._CO_AXES), set())


if __name__ == "__main__":
    unittest.main()
