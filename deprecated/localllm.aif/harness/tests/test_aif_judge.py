#!/usr/bin/env python3
"""aif_judge 의 판정 계약을 잠근다 (stdlib unittest, 모델 호출 없음).

왜 이 파일이 있는가 (F028 리뷰 MUST-5):
  ADR-020 "결과" 절은 "증거 결함 검출·무효 판정 제외·동수 UNCERTAIN·과반 미달
  UNCERTAIN 이 모두 설계대로 동작" 이라고 적었는데 **테스트가 0건**이었다.
  `parse_items`/`validate`/`aggregate` 는 전부 순수 함수다 — 리뷰가 찾은 MUST
  여섯 중 넷이 10줄짜리 테스트로 잡혔을 것들이었다.

  이 리포의 `test_cycle_driver_gates.py` 헤더가 남긴 교훈("순수 함수 게이트에
  테스트 0건") 이 그대로 반복됐다.

사본:
  `aif_judge.py` 는 claude.aif / localllm.aif 두 벌이다. 사본별 테스트를 만들면
  한쪽에만 케이스를 추가하고 끝나므로, `AIF_JUDGE` 환경변수로 대상을 받는다.

실행:
    python3 tests/test_aif_judge.py
    AIF_JUDGE=../../localllm.aif/harness/.claude/bin/aif_judge.py python3 tests/...
"""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_DEFAULT = Path(__file__).resolve().parent.parent / ".claude" / "bin" / "aif_judge.py"
_TARGET = Path(os.environ.get("AIF_JUDGE", str(_DEFAULT))).resolve()

_RUBRIC = """\
### M1 | MUST | docstring 존재
요구: 모든 공개 함수에 docstring 이 있다
증거: 각 docstring 의 첫 줄을 `파일:행` 과 함께 인용

### M2 | MUST | 자격증명 부재
요구: 소스에 하드코딩된 토큰이 없다
증거유형: 부재
증거: 확인한 파일 범위와 검색어를 서술

### S1 | SHOULD | 함수 길이
요구: 함수가 40줄을 넘지 않는다
증거: 가장 긴 함수의 `파일:행` 과 줄 수
"""

_TARGET_FILE = '''\
def add(a, b):
    """두 수를 더한다."""
    return a + b
'''


def _install(root: Path) -> Path:
    """스크립트를 임시 트리에 복사하고 그 사본 경로를 돌려준다.

    `aif_judge` 는 `_ROOT` 를 `__file__` 에서 잡는다 (CLAUDE_PROJECT_DIR 미사용).
    그래서 원본을 그대로 부르면 **실제 리포의 rubric·상태 디렉토리**를 쓴다 —
    테스트가 리포를 오염시키고, 임시 트리에 심은 픽스처는 무시된다.
    사본을 쓰면 두 문제가 같이 없어진다.
    """
    dst = root / ".claude/bin/aif_judge.py"
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(_TARGET.read_text(encoding="utf-8"), encoding="utf-8")
    return dst


def _load(script: Path):
    """사본을 모듈로 적재한다."""
    spec = importlib.util.spec_from_file_location("aif_judge_under_test", script)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["aif_judge_under_test"] = mod
    spec.loader.exec_module(mod)
    return mod


class AifJudgeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / ".claude/rubrics").mkdir(parents=True)
        (self.root / ".claude/rubrics/code-review.items.md").write_text(_RUBRIC, encoding="utf-8")
        (self.root / "src").mkdir()
        (self.root / "src/calc.py").write_text(_TARGET_FILE, encoding="utf-8")
        (self.root / "SECRET.txt").write_text("비밀", encoding="utf-8")
        self.script = _install(self.root)
        self.mod = _load(self.script)
        self.items = self.mod.parse_items("code-review")
        self.context = self.mod._read_target("src/calc.py")

    def tearDown(self):
        self.tmp.cleanup()

    @property
    def _state(self) -> Path:
        return self.root / ".claude/state/aif"

    def _cli(self, *argv) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(self.script), *argv],
                              capture_output=True, text=True, timeout=60)

    # ── 이름이 경로 성분이 되는 지점 ────────────────────────────────────────
    def test_run_이름이_상태_디렉토리를_벗어나지_못한다(self):
        for bad in ("../../escaped", "..", "a/b", "/tmp/abs"):
            with self.subTest(run=bad):
                res = self._cli("record", "code-review", "--run", bad, "--file", "/dev/null")
                self.assertNotEqual(res.returncode, 0, f"{bad!r} 가 통과했다")
        self.assertEqual(list(self.root.glob("**/escaped")), [], "상태 디렉토리 밖에 생겼다")

    def test_rubric_이름도_같은_검증을_받는다(self):
        res = self._cli("plan", "../../evil")
        self.assertNotEqual(res.returncode, 0)

    def test_target_은_프로젝트_루트_밖을_읽지_않는다(self):
        """`--target /etc/hostname` 이 호스트명을 프롬프트에 실었다 (같은 클래스 3회차)."""
        body = self.mod._read_target("/etc/hostname,../../../etc/passwd")
        self.assertNotIn("root:", body)
        self.assertIn("읽지 않음", body)

    # ── 증거 강제 (MUST-4·6) ──────────────────────────────────────────────
    def test_없는_파일과_없는_인용은_증거로_인정되지_않는다(self):
        raw = ("M1: met | ghost_file_zzz.py:9999 에 docstring 있음\n"
               "M2: met | src/ 전체를 token|secret|key 로 검색해 하드코딩 없음 확인\n"
               'S1: met | "이 인용은 대상 어디에도 없다 정말로" 참조\n')
        res = self.mod.validate(self.items, raw, self.context)
        self.assertIn("없는 파일", res["items"]["M1"]["invalid"])
        self.assertIn("없는 인용", res["items"]["S1"]["invalid"])
        self.assertEqual(res["items"]["M2"]["invalid"], "", "부재 항목이 서술 증거로 통과해야 한다")

    def test_파일_끝을_넘는_행번호는_날조로_잡힌다(self):
        raw = ("M1: met | src/calc.py:9999 의 docstring\n"
               "M2: met | src/ 전체를 token|secret|key 로 검색해 하드코딩 없음 확인\n"
               "S1: met | src/calc.py:1 함수는 3줄\n")
        res = self.mod.validate(self.items, raw, self.context)
        self.assertIn("행 번호", res["items"]["M1"]["invalid"])

    def test_rubric_문구_에코는_접두어를_붙여도_잡힌다(self):
        """`startswith` 였을 때 `"확인: "`·`"- "` 한 조각으로 무력화됐다."""
        ev = self.items[0]["ev"]
        for prefix in ("", "확인: ", "- ", "  * "):
            with self.subTest(prefix=prefix):
                raw = (f"M1: met | {prefix}{ev}\n"
                       "M2: met | src/ 전체를 token|secret|key 로 검색해 하드코딩 없음 확인\n"
                       "S1: met | src/calc.py:1 함수는 3줄\n")
                res = self.mod.validate(self.items, raw, self.context)
                self.assertIn("에코", res["items"]["M1"]["invalid"], f"접두어 {prefix!r} 로 빠져나갔다")

    def test_증거_없는_unmet_은_유효표가_아니다(self):
        """빈 증거 unmet 이 cycle_driver 를 통해 '결정론 검출' 로 judge 에 주입됐다."""
        raw = "M1: unmet | \nM2: unmet\nS1: unmet | 짧음\n"
        res = self.mod.validate(self.items, raw, self.context)
        for iid in ("M1", "M2", "S1"):
            self.assertIn("근거 부재", res["items"][iid]["invalid"], f"{iid} 가 유효표로 인정됐다")
        agg = self.mod.aggregate(self.items, [res, res])
        self.assertEqual(agg["overall"], "uncertain", "근거 없는 unmet 이 revision 을 만들었다")

    def test_근거_있는_unmet_은_정상_인정된다(self):
        raw = ("M1: unmet | src/calc.py:1 의 add() 에는 있으나 다른 함수 확인 불가\n"
               "M2: met | src/ 전체를 token|secret|key 로 검색해 하드코딩 없음 확인\n"
               "S1: met | src/calc.py:1 함수는 3줄\n")
        res = self.mod.validate(self.items, raw, self.context)
        self.assertEqual(res["items"]["M1"]["invalid"], "")
        self.assertEqual(self.mod.aggregate(self.items, [res, res])["overall"], "revision")

    def test_항목_id_대소문자는_무시한다(self):
        """로컬 32B 가 소문자로 쓰면 '미정의 id' 로 판정 전체가 무효가 됐다."""
        raw = ("m1: met | src/calc.py:2 \"두 수를 더한다.\"\n"
               "m2: met | src/ 전체를 token|secret|key 로 검색해 하드코딩 없음 확인\n"
               "s1: met | src/calc.py:1 함수는 3줄\n")
        res = self.mod.validate(self.items, raw, self.context)
        self.assertTrue(res["valid"], f"소문자 id 로 무효가 됐다: {res['reason']}")

    # ── 앙상블 (UNCERTAIN 강제 기록 금지) ─────────────────────────────────
    def _judgment(self, verdicts: dict) -> dict:
        return {"valid": True, "rubric": "code-review",
                "items": {k: {"verdict": v, "evidence": "e", "invalid": ""}
                          for k, v in verdicts.items()}}

    def test_동수와_과반미달은_UNCERTAIN_이다(self):
        tie = [self._judgment({"M1": "met", "M2": "met", "S1": "met"}),
               self._judgment({"M1": "unmet", "M2": "met", "S1": "met"})]
        self.assertEqual(self.mod.aggregate(self.items, tie)["items"]["M1"]["decided"], "UNCERTAIN")
        short = [self._judgment({"M1": "met", "M2": "met", "S1": "met"}),
                 {"valid": False, "items": {}}, {"valid": False, "items": {}}]
        self.assertEqual(self.mod.aggregate(self.items, short)["items"]["M1"]["decided"], "UNCERTAIN")

    def test_uncertain_은_verify_loop_기록_명령을_찍지_않는다(self):
        """갈린 판정을 pass|revision 으로 강제 기록하면 불확실성이 기록에서 사라진다."""
        d = self._state / "r-tie"
        d.mkdir(parents=True)
        (d / "j1.json").write_text(json.dumps(self._judgment({"M1": "met", "M2": "met", "S1": "met"})), encoding="utf-8")
        (d / "j2.json").write_text(json.dumps(self._judgment({"M1": "unmet", "M2": "met", "S1": "met"})), encoding="utf-8")
        res = self._cli("aggregate", "r-tie")
        self.assertIn("억지로 정하지 않는다", res.stdout)
        self.assertNotIn("verify_loop.py record", res.stdout)

    # ── 기록 파일 (MUST-2·3 + SHOULD-5) ───────────────────────────────────
    def test_판정_번호는_단조증가하고_기존_기록을_덮지_않는다(self):
        d = self._state / "r-num"
        d.mkdir(parents=True)
        original = self._judgment({"M1": "unmet", "M2": "met", "S1": "met"})
        (d / "j1.json").write_text(json.dumps(original), encoding="utf-8")
        (d / "j3.json").write_text(json.dumps(original), encoding="utf-8")
        n = self.mod._write_judgment(d, self._judgment({"M1": "met", "M2": "met", "S1": "met"}))
        self.assertEqual(n, 4, f"번호가 {n} — 기존 j3 를 덮어썼다")
        kept = json.loads((d / "j3.json").read_text(encoding="utf-8"))
        self.assertEqual(kept["items"]["M1"]["verdict"], "unmet", "기존 판정이 덮어써졌다")

    def test_손상된_판정_1건이_run_전체를_죽이지_않는다(self):
        poisons = ("{ broken json", '{"valid": true}', '{"valid": true, "items": "문자열"}',
                   '{"valid": true, "items": {"M1": null}}', "[1,2,3]", "null")
        for i, body in enumerate(poisons):
            with self.subTest(poison=body[:20]):
                d = self._state / f"r-poison{i}"
                d.mkdir(parents=True)
                (d / "j1.json").write_text(body, encoding="utf-8")
                (d / "j2.json").write_text(
                    json.dumps(self._judgment({"M1": "met", "M2": "met", "S1": "met"})),
                    encoding="utf-8")
                res = self._cli("aggregate", f"r-poison{i}")
                self.assertEqual(res.returncode, 0,
                                 f"{body[:20]!r} 로 집계가 죽었다: {res.stdout}{res.stderr}")
                self.assertIn("제외", res.stdout, "무효 사유가 로그에 남지 않았다")

    def test_판정이_아닌_파일은_집계에_섞이지_않는다(self):
        d = self._state / "r-junk"
        d.mkdir(parents=True)
        (d / "junk.json").write_text('{"valid": true, "items": {}}', encoding="utf-8")
        (d / "j1.json").write_text(
            json.dumps(self._judgment({"M1": "met", "M2": "met", "S1": "met"})), encoding="utf-8")
        res = self._cli("aggregate", "r-junk")
        self.assertIn("판정 1회", res.stdout, f"junk.json 이 판정으로 세어졌다: {res.stdout}")

    def test_run_에_rubric_이_섞이면_알리고_무효_처리한다(self):
        d = self._state / "r-mixed"
        d.mkdir(parents=True)
        a = self._judgment({"M1": "met", "M2": "met", "S1": "met"})
        b = dict(a, rubric="qa-acceptance")
        (d / "j1.json").write_text(json.dumps(a), encoding="utf-8")
        (d / "j2.json").write_text(json.dumps(b), encoding="utf-8")
        res = self._cli("aggregate", "r-mixed")
        self.assertIn("rubric 이 섞여", res.stdout, "원인이 로그에 안 보인다")

    def test_없는_판정_파일에_traceback_대신_안내가_나온다(self):
        res = self._cli("record", "code-review", "--run", "r-x", "--file", "/nonexistent-zzz")
        self.assertEqual(res.returncode, 1)
        self.assertNotIn("Traceback", res.stderr)

    # ── "모델을 호출하지 않는다" 주장 ─────────────────────────────────────
    def test_auto_외에는_네트워크도_서브프로세스도_쓰지_않는다(self):
        src = _TARGET.read_text(encoding="utf-8")
        for banned in ("import requests", "import urllib", "import socket", "import http"):
            self.assertNotIn(banned, src, f"{banned} 가 들어왔다 — stdlib 판정 엔진 계약 위반")
        # subprocess 는 auto 모드의 cycle_driver 위임 한 곳뿐이어야 한다
        self.assertNotIn("subprocess", src, "직접 서브프로세스를 띄운다 — auto 는 cycle_driver 위임이다")


if __name__ == "__main__":
    print(f"대상: {_TARGET}")
    unittest.main(verbosity=2)
