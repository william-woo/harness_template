#!/usr/bin/env python3
"""스위트 oracle 의 **호스트 편향**을 잠근다 (F029, stdlib unittest — LLM 불요).

왜 이 파일이 있는가 (F029 리뷰 MUST-1):
  측정 11 결과 3 은 "측정 도구가 약한 호스트의 문체에 적합돼 있었다" 를 발견했다 —
  O7 이 Claude 의 **반박문을 결함 서술로 오판**했다. 그런데 AC2 는 "부정문 인식
  수정" 이라 적혀 있고, 실제로 일어난 일은 `ACCURACY → INFO` **강등**이었다.
  리뷰가 코드를 직접 돌려 4케이스 중 1건만 커버됨을 보였고, 더 나쁘게는 그 수정이
  **진짜 결함을 삼키는 거짓 부재**를 새로 만든 것을 찾았다:

      "the file does not contain a docstring"  → "does not contain" 이 반박 표지
      "docstring 이 존재하지 않음, 누락"        → "존재" 가 "존재하지 않음" 에 부분매칭

  거짓 부재는 오탐보다 나쁘다 — 오탐은 사람이 보고 넘기지만 거짓 부재는 보이지 않는다.

무엇을 고정하나:
  · 반박문·기대동작 서술을 결함으로 읽지 않는다 (호스트 편향)
  · **진짜 결함은 반드시 검출한다** (거짓 부재 금지)
  · 남는 한계를 `KNOWN_MISS` 로 **명시**한다 — 못 잡는 것을 잡는다고 적지 않는다

실행:
    python3 tests/test_suite_oracles.py
"""
import re
import unittest
from pathlib import Path

_SUITE = Path(__file__).resolve().parent / "suite" / "run_suite.py"


def _load_o7():
    """`run_suite.py` 에서 O7 판별 블록만 떼어 실행한다.

    모듈 전체를 import 하면 실행 전제(opencode·rsync·git) 검사에 걸린다.
    판별부는 순수 함수라 이렇게 분리해도 같은 코드를 태운다.
    """
    src = _SUITE.read_text(encoding="utf-8")
    m = re.search(r"    _DEFECT_WORDS = .*?return sorted\(set\(hits\)\)\n", src, re.S)
    assert m, "O7 판별 블록을 찾지 못했다 — run_suite.py 구조가 바뀌었다"
    ns = {"re": re}
    exec("\n".join(line[4:] for line in m.group(0).splitlines()), ns)  # noqa: S102
    return ns["_unresolved_defect_hits"]


class O7HostBiasTest(unittest.TestCase):
    """O7 = "pass 인데 노트가 미해소 결함을 서술" 판별."""

    # 결함이 **없다**는 주장 — 결함어가 들어 있어도 잡으면 안 된다 (호스트 편향)
    REFUTATIONS = (
        "the criterion flagged as missing is actually satisfied",
        "the criterion listed as missing is in fact present",
        "dividing by zero fails with valueerror as required",
        "the docstring is present; nothing is missing",
        "this does not violate the acceptance criteria",
        "모든 기준이 충족됨 — 누락 없음",
    )

    # 진짜 결함 — **반드시** 잡아야 한다. 놓치면 거짓 부재다
    REAL_DEFECTS = (
        "the file does not contain a docstring for divide",
        "docstring 이 존재하지 않음, 누락",
        "the import is incorrect",
        "test_x.py is missing",
        "the function returns the wrong value for n=0",
        "docstring 누락 — 결함",
    )

    # 못 잡는 것. **여기 적힌 만큼만 한계다** — 늘어나면 그때 고친다.
    KNOWN_MISS = (
        # judge 가 자기 이전 판정을 회고하는 문장. "was wrong" 이 문법적으로는
        # 결함 서술과 구별되지 않는다. O7 은 INFO(수동 확인 플래그)이므로
        # 이 오탐은 판정을 오염시키지 않고 잡음으로만 남는다.
        "my earlier needs revision was wrong; it is now correct",
    )

    def setUp(self):
        self.hits = _load_o7()

    def test_반박문을_결함으로_읽지_않는다(self):
        for text in self.REFUTATIONS:
            with self.subTest(note=text[:40]):
                self.assertEqual(self.hits(text.lower()), [],
                                 "결함이 없다는 주장을 결함으로 읽었다 — 호스트 편향")

    def test_진짜_결함은_반드시_검출한다(self):
        """거짓 부재 금지 — 반박 표지를 넓게 잡으면 진짜 결함이 지워진다."""
        for text in self.REAL_DEFECTS:
            with self.subTest(note=text[:40]):
                self.assertTrue(self.hits(text.lower()),
                                "진짜 결함을 삼켰다 (거짓 부재) — 반박 표지가 너무 넓다")

    def test_못_잡는_것을_잡는다고_적지_않는다(self):
        """`KNOWN_MISS` 가 실제로 여전히 못 잡히는지 확인한다.

        고쳐졌으면 이 테스트가 실패한다 — 그때 목록에서 빼고 한계 서술도 지운다.
        문서가 코드보다 비관적인 것도 부정확이다.
        """
        for text in self.KNOWN_MISS:
            with self.subTest(note=text[:40]):
                self.assertTrue(self.hits(text.lower()),
                                "이제 잡힌다 — KNOWN_MISS 와 측정 11 한계 서술을 갱신하라")

    def test_O7_은_판정에_관여하지_않는다(self):
        """정밀도가 낮으므로 ACCURACY 가 아니라 INFO 여야 한다 (신호는 보존, 판정은 불관여)."""
        src = _SUITE.read_text(encoding="utf-8")
        blk = re.search(r'findings\.append\(\{"o": "O7".*?\}\)', src, re.S)
        self.assertIsNotNone(blk, "O7 finding 생성부를 찾지 못했다")
        self.assertIn('"sev": "INFO"', blk.group(0),
                      "O7 이 판정에 관여한다 — 정밀도가 낮은 휴리스틱을 verdict 에 쓰면 안 된다")


class SuiteRecordSchemaTest(unittest.TestCase):
    """산출물이 **구간을 구분할 수 있는가** (F029 리뷰 MUST-2·6).

    결과 1·2 의 수치를 재현할 수 없던 이유의 절반은 산출물 부재였고,
    나머지 절반은 **레코드에 host/lean 필드가 없어** 있었어도 두 구간을
    나눌 수 없었다는 것이다.
    """

    def setUp(self):
        self.src = _SUITE.read_text(encoding="utf-8")

    def test_레코드에_구간_식별자가_있다(self):
        for field in ('"host"', '"lean"'):
            self.assertIn(field, self.src, f"레코드에 {field} 가 없다 — 구간 구분 불가")

    def test_레코드에_재작업_라운드와_비용이_있다(self):
        """AC4 지표 6종 중 둘이 빠져 있었다."""
        self.assertIn('"rework_rounds"', self.src)
        self.assertIn('"claude_calls"', self.src)

    def test_결과_파일이_구간별로_갈린다(self):
        """같은 파일에 두 구간을 섞으면 나중에 분리할 수 없다."""
        self.assertRegex(self.src, r'round\{rnd\}-\{_arm\}\.jsonl',
                         "결과 파일명에 구간이 없다")


if __name__ == "__main__":
    unittest.main(verbosity=2)
