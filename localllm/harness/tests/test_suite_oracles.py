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
  · `run_suite` 가 **기록하는 것**을 `cycle_driver` 가 실제로 **내는가** (교차 검증)
  · localllm / .aif / .nem **3 사본이 갈라지지 않았는가**

실행:
    python3 tests/test_suite_oracles.py
"""
import hashlib
import re
import unittest
from pathlib import Path

_SUITE = Path(__file__).resolve().parent / "suite" / "run_suite.py"
_DRIVER = Path(__file__).resolve().parents[1] / ".claude" / "bin" / "cycle_driver.py"


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


class SuiteDriverContractTest(unittest.TestCase):
    """`run_suite.py` 가 **기록하는 것**을 `cycle_driver.py` 가 실제로 **내는가**.

    왜 이 클래스가 있는가 (F029 4차 리뷰 SHOULD-4):
      위 `SuiteRecordSchemaTest` 는 `run_suite.py` **소스 문자열만** grep 한다. 그래서
      "레코드에 `claude_calls` 가 있다" 는 통과시키면서, 같은 사본의 드라이버가 `[cost]`
      줄을 **내지 않아 항상 0 이 기록되는** 상태를 놓쳤다 (localllm.nem). 같은 이유로
      "레코드에 `host` 가 있다" 가 통과하는데 드라이버엔 호스트 분기가 없어
      `HARNESS_DRIVER_HOST=claude-code` 를 줘도 **opencode 로 돌면서 claude-code 로
      기록**되는 상태도 놓쳤다 (localllm.aif).

      두 결함의 공통점: 스키마는 맞는데 **생산자와 소비자가 연결돼 있지 않다**.
      그래서 여기서는 한쪽 파일만 보지 않고 **두 파일을 맞대어** 본다.
    """

    def setUp(self):
        self.suite = _SUITE.read_text(encoding="utf-8")
        self.assertTrue(_DRIVER.is_file(), f"드라이버가 없다: {_DRIVER}")
        self.driver = _DRIVER.read_text(encoding="utf-8")

    def test_비용_줄을_내는_쪽과_읽는_쪽이_맞물린다(self):
        """드라이버의 `[cost]` 포맷을 run_suite 의 파서 정규식에 직접 먹여 본다.

        `assertIn("[cost]")` 만으로는 포맷이 어긋나도 통과한다 — 실제로 소비자는
        `claude_calls=(\\d+)` 를 찾는다. 양쪽을 소스에서 뽑아 맞물리는지 확인한다.
        """
        m = re.search(r'_log\(f"(\[cost\][^"]*)"\s*\n?\s*f?"([^"]*)"\)', self.driver)
        if not m:
            m = re.search(r'_log\(f"(\[cost\][^"]*)"', self.driver)
            self.assertIsNotNone(
                m, "드라이버가 `[cost]` 줄을 내지 않는다 — run_suite 의 claude_calls 가 항상 0 이 된다")
            template = m.group(1)
        else:
            template = m.group(1) + m.group(2)
        # f-string 자리표시자를 표본값으로 채워 **실제로 찍히는 한 줄**을 만든다.
        rendered = re.sub(r"\{[^}]*\}", "7", template)

        pm = re.search(r"_COST_LINE = re\.compile\(r\"([^\"]+)\"\)", self.suite)
        self.assertIsNotNone(pm, "run_suite 에 _COST_LINE 파서가 없다")
        self.assertRegex(rendered, pm.group(1),
                         f"드라이버가 내는 줄({rendered!r})을 run_suite 파서가 못 읽는다")

    def test_host_를_기록하면_드라이버가_host_를_제어한다(self):
        """제어 없는 기록은 **거짓 라벨**이다 — 실제로 돌린 호스트와 어긋난다."""
        if '"host"' not in self.suite:
            self.skipTest("이 사본은 레코드에 host 를 담지 않는다")
        self.assertIn("HARNESS_DRIVER_HOST", self.driver,
                      "레코드에 host 를 담는데 드라이버가 HARNESS_DRIVER_HOST 를 보지 않는다 "
                      "— 기록은 하되 제어는 못 하는 상태")
        self.assertIn("def _driver_host(", self.driver, "드라이버에 호스트 분기가 없다")
        self.assertIn("def _claude_exec(", self.driver, "claude-code 위임 경로가 없다")

    def test_lean_을_기록하면_드라이버가_lean_을_적용한다(self):
        if "HARNESS_LEAN_PROMPT" not in self.suite:
            self.skipTest("이 사본은 lean 구간을 기록하지 않는다")
        self.assertIn("HARNESS_LEAN_PROMPT", self.driver,
                      "레코드에 lean 을 담는데 드라이버가 프롬프트를 바꾸지 않는다")
        self.assertIn("def _lean(", self.driver)

    def test_claude_calls_를_기록하면_드라이버가_센다(self):
        if '"claude_calls"' not in self.suite:
            self.skipTest("이 사본은 claude_calls 를 기록하지 않는다")
        self.assertIn("claude_calls=", self.driver,
                      "레코드에 claude_calls 를 담는데 드라이버가 그 줄을 내지 않는다 "
                      "— AC6 비용 귀속이 조용히 0 을 기록한다")

    def test_비용_보고가_모든_종료_경로를_덮는다(self):
        """`cmd_run` 이 `finally` 로 감싸지 않으면 실패 경로에서 비용이 사라진다."""
        self.assertIn("def _cmd_run(", self.driver,
                      "cmd_run 이 비용 보고 래퍼로 감싸여 있지 않다")
        wrapper = self.driver[self.driver.index("def cmd_run("):self.driver.index("def _cmd_run(")]
        self.assertIn("finally:", wrapper, "비용 보고가 정상 종료 경로에만 있다")

    def test_transient_판정은_실패한_호출에만_적용된다(self):
        """"All 503 lines reviewed" 를 과부하로 오판해 성공을 rc=124 로 뒤집던 결함."""
        if "def _claude_exec(" not in self.driver:
            self.skipTest("이 사본엔 claude 위임 경로가 없다")
        self.assertRegex(self.driver, r"transient = rc == 124 or \(rc != 0 and any\(",
                         "성공한 호출의 출력에 '503' 이 있다는 이유로 transient 로 판정한다")

    def test_호스트별_실행_전제를_둘_다_확인한다(self):
        """opencode 쪽만 확인하고 claude 쪽은 traceback 으로 죽던 비대칭."""
        if "def _driver_host(" not in self.driver:
            self.skipTest("이 사본엔 호스트 분기가 없다")
        self.assertIn('shutil.which("opencode")', self.driver)
        self.assertIn('shutil.which("claude")', self.driver,
                      "claude-code 분기에 CLI 부재 확인이 없다")

    def test_숫자가_아닌_타임아웃_env_에_죽지_않는다(self):
        if "def _claude_exec(" not in self.driver:
            self.skipTest("이 사본엔 claude 위임 경로가 없다")
        self.assertIn("except ValueError:", self.driver[
            self.driver.index("def _claude_exec("):self.driver.index("def _opencode_run(")],
            "CYCLE_CLAUDE_TIMEOUT 이 숫자가 아니면 ValueError 로 죽는다")


class TriCopyParityTest(unittest.TestCase):
    """`localllm` · `localllm.aif` · `localllm.nem` 3 사본이 갈라지지 않았는가.

    이 리포의 반복 결함은 "수정이 갈 곳에 다 가지 않는다" 이다 — 측정 11 문서는
    nem 만 따로 자라 재현 불가 배너를 못 받았고, 드라이버 MUST 5건은 nem 에 1/5,
    aif 에 0/5 만 갔다. 사람이 기억으로 미러하는 대신 **테스트가 대조**한다.

    3 사본이 없는 배포본(다운스트림)에서는 조용히 skip 한다.
    """

    # 사본마다 정당하게 다른 부분이 있으므로(모델 축·aif 오버레이) 드라이버는
    # md5 가 아니라 **핵심 블록 존재**로 본다. 문서는 한 벌이어야 하므로 md5 로 본다.
    IDENTICAL_DOCS = ("docs/poc/measurements/11-host-comparison.md",)
    DRIVER_BLOCKS = (
        "def _driver_host(",        # 호스트 분기
        "def _claude_exec(",        # claude-code 위임
        "def _lean(",               # lean 구간 프롬프트
        "def _cmd_run(",            # 비용 보고 래퍼
        "[cost] host=",             # run_suite 가 파싱하는 줄
        "shutil.which(\"claude\")",  # claude CLI 부재 확인
        "rc != 0 and any(",         # transient 오판 가드
    )

    @classmethod
    def setUpClass(cls):
        cls.roots = []
        tpl = Path(__file__).resolve().parents[3]
        for name in ("localllm", "localllm.aif", "localllm.nem"):
            p = tpl / name / "harness"
            if p.is_dir():
                cls.roots.append(p)

    def setUp(self):
        if len(self.roots) < 3:
            self.skipTest("3 사본 레이아웃이 아니다 (배포본) — 대조 생략")

    def test_측정_문서가_3_사본에서_동일하다(self):
        for rel in self.IDENTICAL_DOCS:
            digests = {}
            for root in self.roots:
                f = root / rel
                self.assertTrue(f.is_file(), f"{f} 가 없다")
                digests[root.parent.name] = hashlib.md5(f.read_bytes()).hexdigest()
            self.assertEqual(len(set(digests.values())), 1,
                             f"{rel} 가 사본마다 다르다: {digests}")

    def test_드라이버_핵심_블록이_3_사본에_모두_있다(self):
        for root in self.roots:
            src = (root / ".claude/bin/cycle_driver.py").read_text(encoding="utf-8")
            for block in self.DRIVER_BLOCKS:
                with self.subTest(copy=root.parent.name, block=block):
                    self.assertIn(block, src,
                                  f"{root.parent.name} 의 드라이버에 {block!r} 가 없다 "
                                  "— 수정이 이 사본에 가지 않았다")

    def test_run_suite_가_동일하거나_모델_축만_다르다(self):
        """전송·기록 로직이 갈라지면 사본 간 결과를 비교할 수 없다.

        `localllm.nem` 은 모델 축 변형이라 `SUITE_DRIVER_TIMEOUT`(느린 모델용 예산)
        한 줄만 다르다 — 그 외 차이는 회귀로 본다.
        """
        srcs = {r.parent.name: (r / "tests/suite/run_suite.py").read_text(encoding="utf-8")
                for r in self.roots}
        base = srcs["localllm"].replace(
            'DRIVER_TIMEOUT = 1500  # 초 — 드라이버 자체가 내부 timeout/재시도를 가짐',
            'DRIVER_TIMEOUT = int(os.environ.get("SUITE_DRIVER_TIMEOUT", "1500"))')
        for name, src in srcs.items():
            with self.subTest(copy=name):
                self.assertIn(src, (srcs["localllm"], base),
                              f"{name} 의 run_suite 가 모델 축 외의 이유로 갈라졌다")


if __name__ == "__main__":
    unittest.main(verbosity=2)
