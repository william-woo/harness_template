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
        shutil.copy2(_LINT, self.root / ".claude" / "bin" / "lint.py")
        self.ht = self.root / "src" / "harness_template"
        for v in _FIXTURE_VARIANTS:
            (self.ht / v / "harness" / ".claude" / "agents").mkdir(parents=True)
            (self.ht / v / "harness" / ".claude" / "commands").mkdir(parents=True)
        (self.root / ".claude" / "agents").mkdir(parents=True)
        (self.root / ".claude" / "commands").mkdir(parents=True)
        self._write_reviewer()
        self._write_retro()
        self._write_freeze_manifest()

    def tearDown(self):
        self.tmp.cleanup()

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
        self.assertIn("공유 파일", self._run("LINT-CO")[1],
                      "공유 파일을 하나도 못 찾았다 — 검사기가 공회전한다")

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
        files, _, unread, untracked = self.lint._co_collect()
        self.assertEqual(unread, [], "읽지 못한 파일이 있다 — 그만큼 분류에서 빠진다")
        self.assertEqual(untracked, [],
                         "git 추적 목록 없이 디스크를 훑었다 — 로컬 산출물이 섞인다")
        shared = {rel: m for rel, m in files.items() if len(m) >= 2}
        self.assertGreater(len(shared), 100, "공유 파일이 너무 적다 — 범위가 좁혀졌다")

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

    def test_C_부류는_사유_없이_늘지_않는다(self):
        """제외는 곧 *어떤 검사도 보지 않는 파일*을 만드는 일이다 (ADR-015 결정 2)."""
        for key, reason in self.lint._CO_VARIANT_LOCAL.items():
            self.assertTrue(isinstance(reason, str) and len(reason) >= 10,
                            f"'{key}' 의 제외 사유가 없거나 너무 짧다: {reason!r}")

    def test_선언된_축이_전부_살아_있다(self):
        """죽은 선언은 "여기는 갈려도 된다" 는 **거짓 신호**를 남긴다."""
        files, _, _, _ = self.lint._co_collect()
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

    def test_매니페스트가_비었으면_공회전하지_않는다(self):
        (self.root / ".claude" / "freeze-manifest.json").write_text(
            json.dumps({"files": {}}), encoding="utf-8")
        self.assertIn("공회전", "\n".join(self._blocks()))


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
