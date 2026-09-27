#!/usr/bin/env python3
"""autoresearch 의 **불변·승인 게이트**를 잠근다 (stdlib unittest, LLM 호출 없음).

왜 이 파일이 있는가 (F027 리뷰 MUST-5):
  이 기능의 존재 이유는 "자동 채택은 실험 원장까지, 하네스 반영은 사람 승인" 이다.
  그 계약을 지키는 코드에 **테스트가 0건**이었고, 실측된 것은 KEEP/DISCARD 두
  분류뿐이었다 — INVALID·DISQUALIFIED·promote 게이트·매니페스트 검사는 어디서도
  실행된 기록이 없었다.

  리뷰어의 스텁 드라이버 80줄이 MUST 넷을 찍어냈다. 그 케이스를 여기 옮긴다.

무엇을 스텁으로 갈아끼우나:
  `_suite_arm`(로컬 LLM 스위트 2회 실행)과 `_propose`(LLM 제안) 둘뿐이다.
  판정·불변검사·원장·승격은 **실제 코드**가 돈다 — 거기가 잠글 대상이다.

사본:
  `autoresearch.py` 는 localllm / localllm.aif / localllm.nem 세 벌이다.
  `AUTORESEARCH` 환경변수로 대상을 받아 한 목록을 세 사본에 태운다.

실행:
    python3 tests/test_autoresearch_gates.py
    AUTORESEARCH=../../localllm.nem/harness/.claude/bin/autoresearch.py python3 tests/...
"""
import importlib.util
import json
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path

_DEFAULT = Path(__file__).resolve().parent.parent / ".claude" / "bin" / "autoresearch.py"
_TARGET = Path(os.environ.get("AUTORESEARCH", str(_DEFAULT))).resolve()


def _load(ar_dir: Path, root: Path):
    """실험 공간과 프로젝트 루트를 임시 경로로 돌린 모듈을 적재한다."""
    os.environ["AUTORESEARCH_DIR"] = str(ar_dir)
    spec = importlib.util.spec_from_file_location("autoresearch_under_test", _TARGET)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["autoresearch_under_test"] = mod
    spec.loader.exec_module(mod)
    # `_ROOT` 는 `__file__` 기준이라 임시 트리를 가리키게 갈아끼운다.
    mod._ROOT = root
    mod._PROMOTED = root / ".claude" / "policy"
    return mod


def _args(**kw):
    base = dict(experiments=1, scenarios="S01", repeats=1, timeout=60, budget_min=0)
    base.update(kw)
    return types.SimpleNamespace(**base)


class AutoresearchGateTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "repo"
        self.ar = Path(self.tmp.name) / "ar"
        for rel in (".claude/bin", ".claude/policy", "tests/suite"):
            (self.root / rel).mkdir(parents=True)
        # 불변 대상 3종을 실재하게 만든다
        for rel in (".claude/bin/cycle_driver.py", ".claude/bin/autoresearch.py",
                    "tests/suite/run_suite.py"):
            (self.root / rel).write_text("# 원본\n", encoding="utf-8")
        (self.root / ".claude/policy/developer.md").write_text("본체 정책\n", encoding="utf-8")
        self.mod = _load(self.ar, self.root)
        self.mod._BEST.mkdir(parents=True, exist_ok=True)
        (self.mod._BEST / "developer.md").write_text("챔피언 정책\n", encoding="utf-8")
        self.mod._PROGRAM.parent.mkdir(parents=True, exist_ok=True)
        self.mod._PROGRAM.write_text("# program\n", encoding="utf-8")

    def tearDown(self):
        os.environ.pop("AUTORESEARCH_DIR", None)
        self.tmp.cleanup()

    def _stub(self, base: dict, cand: dict, proposal=("developer", "새 지시")):
        """스위트와 제안을 스텁으로 갈아끼운다 (판정 이후는 실제 코드)."""
        def fake_arm(exp_dir, arm, policy_dir, scenarios, repeats, timeout):
            d = dict(base if arm == "base" else cand)
            d.setdefault("records", [])
            d.setdefault("accuracy", 0)
            d.setdefault("bug", 0)
            return d
        self.mod._suite_arm = fake_arm
        self.mod._propose = lambda *a, **k: proposal

    def _ledger(self) -> list[dict]:
        return self.mod._read_ledger()

    # ── 기본 경로 (M1) ────────────────────────────────────────────────────
    def test_기본_실험공간은_리포_밖이다(self):
        """리포 안이면 run_suite 재귀가드에 걸려 모든 실험이 0 records 가 된다."""
        os.environ.pop("AUTORESEARCH_DIR", None)
        spec = importlib.util.spec_from_file_location("ar_default", _TARGET)
        fresh = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(fresh)
        self.assertFalse(
            str(fresh._AR.resolve()).startswith(str(fresh._ROOT.resolve())),
            f"기본 실험 공간이 리포 내부다: {fresh._AR}")

    # ── 불변 강제 (M2) ────────────────────────────────────────────────────
    def test_불변_파일이_바뀌면_무효로_기록하고_루프를_멈춘다(self):
        self._stub({"pass": 1, "total": 2}, {"pass": 2, "total": 2})
        original = self.mod._suite_arm

        def tamper(exp_dir, arm, policy_dir, scenarios, repeats, timeout):
            if arm == "cand":
                (self.root / "tests/suite/run_suite.py").write_text("# 변조\n", encoding="utf-8")
            return original(exp_dir, arm, policy_dir, scenarios, repeats, timeout)
        self.mod._suite_arm = tamper

        rc = self.mod.cmd_run(_args(experiments=3))
        self.assertEqual(rc, 1, "위반인데 루프가 계속됐다")
        led = self._ledger()
        self.assertEqual(len(led), 1, f"중단하지 않고 실험을 이어갔다: {led}")
        self.assertEqual(led[0]["outcome"], "INVALID")
        self.assertEqual(led[0]["reason"], "immutable-changed")

    def test_기준_매니페스트는_한_번_고정되고_재계산되지_않는다(self):
        """매 실험마다 다시 잡으면 변조 상태가 다음 실험의 정상 기준선이 된다."""
        first = self.mod._baseline_manifest()
        (self.root / "tests/suite/run_suite.py").write_text("# 변조\n", encoding="utf-8")
        second = self.mod._baseline_manifest()
        self.assertEqual(first, second, "기준선이 변조본으로 갱신됐다")
        self.assertNotEqual(second, self.mod._manifest(), "변조를 검출하지 못한다")

    def test_실행_전에_이미_변조돼_있어도_검출한다(self):
        """이게 고정 기준선의 존재 이유다.

        `before = _manifest()` 로 매번 다시 잡으면, **이번 실행 전에 이미 바뀐**
        게이트는 그 실행의 정상 기준선이 되어 영영 검출되지 않는다. 한 실험이
        변조하고 INVALID 를 받은 뒤, 그 다음 실행이 변조본 위에서 시작하던 경로다.
        """
        self.mod._baseline_manifest()                    # init 시점 고정
        (self.root / "tests/suite/run_suite.py").write_text("# 사전 변조\n", encoding="utf-8")
        self._stub({"pass": 1, "total": 2}, {"pass": 2, "total": 2})
        rc = self.mod.cmd_run(_args())
        self.assertEqual(rc, 1, "실행 전 변조를 통과시켰다")
        self.assertEqual(self._ledger()[-1]["reason"], "immutable-changed")

    def test_불변_파일_삭제도_검출된다(self):
        """`is_file()` 인 것만 담으면 **지우는 것**이 검사를 통과한다."""
        before = self.mod._baseline_manifest()
        (self.root / "tests/suite/run_suite.py").unlink()
        self.assertNotEqual(self.mod._manifest(), before)

    # ── 하네스 본체 보호 (M3) ─────────────────────────────────────────────
    def test_실험이_하네스_본체_정책을_고치면_무효다(self):
        """후보 구간 에이전트는 bash 를 가진다 — promote 없이 본체를 쓸 수 있었다."""
        self._stub({"pass": 1, "total": 2}, {"pass": 2, "total": 2})
        original = self.mod._suite_arm

        def inject(exp_dir, arm, policy_dir, scenarios, repeats, timeout):
            if arm == "cand":
                (self.root / ".claude/policy/developer.md").write_text(
                    "후보 구간이 몰래 쓴 지시\n", encoding="utf-8")
            return original(exp_dir, arm, policy_dir, scenarios, repeats, timeout)
        self.mod._suite_arm = inject

        rc = self.mod.cmd_run(_args())
        self.assertEqual(rc, 1)
        led = self._ledger()
        self.assertEqual(led[-1]["outcome"], "INVALID")
        self.assertEqual(led[-1]["reason"], "harness-body-changed")

    def test_정상_실험은_하네스_본체를_건드리지_않는다(self):
        self._stub({"pass": 1, "total": 2}, {"pass": 2, "total": 2})
        self.mod.cmd_run(_args())
        self.assertEqual(
            (self.root / ".claude/policy/developer.md").read_text(encoding="utf-8"),
            "본체 정책\n", "KEEP 이 본체를 바꿨다")
        self.assertEqual(self._ledger()[-1]["outcome"], "KEEP")

    # ── 판정 우선순위 ─────────────────────────────────────────────────────
    def test_후보_거짓결과는_점수와_무관하게_실격이다(self):
        self._stub({"pass": 0, "total": 4}, {"pass": 3, "total": 4, "accuracy": 1})
        self.mod.cmd_run(_args())
        self.assertEqual(self._ledger()[-1]["outcome"], "DISQUALIFIED")

    def test_베이스라인_거짓결과도_무효다(self):
        """챔피언이 오염되면 기준선이 깎여 어떤 후보든 유리해진다."""
        self._stub({"pass": 0, "total": 4, "accuracy": 3}, {"pass": 1, "total": 4})
        self.mod.cmd_run(_args())
        rec = self._ledger()[-1]
        self.assertEqual(rec["outcome"], "INVALID")
        self.assertEqual(rec["base_accuracy"], 3, "베이스라인 거짓결과가 기록되지 않았다")

    def test_구간_실행수가_다르면_비교하지_않는다(self):
        """base 1/2 vs cand 2/4 는 delta 0.0 인데 예전엔 KEEP 이었다."""
        self._stub({"pass": 1, "total": 2}, {"pass": 2, "total": 4})
        self.mod.cmd_run(_args())
        rec = self._ledger()[-1]
        self.assertEqual(rec["outcome"], "INVALID")
        self.assertIn("unpaired", rec["reason"])

    def test_개선이_없으면_DISCARD_이고_챔피언은_그대로다(self):
        self._stub({"pass": 2, "total": 4}, {"pass": 2, "total": 4})
        self.mod.cmd_run(_args())
        self.assertEqual(self._ledger()[-1]["outcome"], "DISCARD")
        self.assertEqual((self.mod._BEST / "developer.md").read_text(encoding="utf-8"),
                         "챔피언 정책\n", "DISCARD 인데 챔피언이 갱신됐다")

    # ── 원장 (M4 · S1) ────────────────────────────────────────────────────
    def test_원장의_비객체_행이_세_서브커맨드를_죽이지_않는다(self):
        self.mod._append_ledger({"exp": "exp-001", "outcome": "KEEP"})
        with self.mod._LEDGER.open("a", encoding="utf-8") as fh:
            fh.write("5\n[1,2]\n\"문자열\"\nnull\n{ torn\n")
        self.assertEqual(self.mod.cmd_status(_args()), 0)
        self.assertEqual(self.mod.cmd_promote(_args(exp="exp-999", yes=False)), 1)
        self._stub({"pass": 1, "total": 2}, {"pass": 2, "total": 2})
        self.assertEqual(self.mod.cmd_run(_args()), 0)

    def test_실험_id_는_최대번호_기준으로_매겨진다(self):
        """고유 id 개수로 매기면 원장이 [001, 003] 일 때 003 이 다시 나온다."""
        self.mod._append_ledger({"exp": "exp-001", "outcome": "DISCARD"})
        self.mod._append_ledger({"exp": "exp-003", "outcome": "DISCARD"})
        self._stub({"pass": 1, "total": 2}, {"pass": 1, "total": 2})
        self.mod.cmd_run(_args())
        self.assertEqual(self._ledger()[-1]["exp"], "exp-004")

    # ── 승인 게이트 (기능의 존재 이유) ────────────────────────────────────
    def test_promote_는_yes_없이_본체를_바꾸지_않는다(self):
        self._stub({"pass": 1, "total": 2}, {"pass": 2, "total": 2})
        self.mod.cmd_run(_args())
        exp = self._ledger()[-1]["exp"]
        body = self.root / ".claude/policy/developer.md"
        self.mod.cmd_promote(_args(exp=exp, yes=False))
        self.assertEqual(body.read_text(encoding="utf-8"), "본체 정책\n", "dry-run 이 본체를 썼다")
        self.assertNotIn("PROMOTED", [r.get("outcome") for r in self._ledger()])
        self.mod.cmd_promote(_args(exp=exp, yes=True))
        self.assertEqual(body.read_text(encoding="utf-8").strip(), "새 지시")

    def test_KEEP_이_아닌_실험은_승격할_수_없다(self):
        self._stub({"pass": 2, "total": 4}, {"pass": 2, "total": 4})
        self.mod.cmd_run(_args())
        exp = self._ledger()[-1]["exp"]
        self.assertEqual(self.mod.cmd_promote(_args(exp=exp, yes=True)), 1)

    def test_정책_파일이_없는_실험은_승격을_거부한다(self):
        """예전엔 아무것도 복사하지 않고 PROMOTED 를 기록했다 — 원장이 거짓말한다."""
        self.mod._append_ledger({"exp": "exp-900", "outcome": "KEEP", "role": "developer",
                                 "base": "1/2", "cand": "2/2", "delta": 0.5,
                                 "cand_accuracy": 0, "scenarios": ["S01"], "repeats": 1})
        (self.ar / "exp-900" / "policy").mkdir(parents=True)
        self.assertEqual(self.mod.cmd_promote(_args(exp="exp-900", yes=True)), 1)
        self.assertNotIn("PROMOTED", [r.get("outcome") for r in self._ledger()])


if __name__ == "__main__":
    print(f"대상: {_TARGET}")
    unittest.main(verbosity=2)
