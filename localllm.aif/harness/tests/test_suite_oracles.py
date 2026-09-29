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
  · **고정 표본 안에서** 진짜 결함을 검출한다 (한국어 부정형 축)
  · 남는 한계를 **두 목록으로** 명시한다 — 못 잡는 것을 잡는다고 적지 않는다
      `KNOWN_MISS`           오탐 (결함이 아닌데 결함으로 읽는다)
      `KNOWN_FALSE_ABSENCE`  거짓 부재 (진짜 결함을 삼킨다) — 주로 **영어 축**
  · `run_suite` 가 **기록하는 것**을 `cycle_driver` 가 실제로 **내는가** (교차 검증)
  · localllm / .aif / .nem **3 사본이 갈라지지 않았는가**

실행:
    python3 tests/test_suite_oracles.py
"""
import contextlib
import hashlib
import io
import os
import re
import unittest
from pathlib import Path
from unittest import mock

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
        # QA 재판정: 반박 표지 `해소`·`충족` 이 자기 부정형에 부분매칭돼 삼켰던 것들.
        # `존재`→`존재한다` 와 같은 계열의 거짓 부재이고, `미충족` 은 이 프로젝트의
        # O6 메시지·AC 문구가 실제로 쓰는 말이라 흔하다.
        "결함이 해소되지 않음",
        "docstring 누락으로 ac 충족 실패",
        "docstring 미충족, 누락",
        "ac 미충족: docstring 누락",
        "결함 미해소, 누락 상태",
        # QA 2회차: 위 5건은 **좁혀진 표지만으로도** 통과한다 (`미충족` 에는 `충족함`
        # 이 없다). 그래서 `_NEGATED` 가드를 지워도 테스트가 초록이었다 — 안전장치가
        # 두 개인데 표본이 하나만 태우면 나머지는 검증되지 않은 채 남는다.
        # 아래 둘은 긍정형을 **부분문자열로 포함**해 가드가 없으면 반드시 삼켜진다.
        "결함 미해소됨, 누락 상태",
        "docstring 미충족됨, 누락",
        # 이건 반대로 **좁힌 표지**를 태운다 — 넓은 `충족` 을 되살리면 삼켜진다.
        "docstring 누락, 충족하지 않음",
        "충족됨을 확인하지 못함, 누락",
        # (H) 후행 부정 — 긍정형 표지 **뒤에** 부정이 붙는 형태 (QA 3회차)
        "충족됨이 확인되지 않음, docstring 누락",
        "docstring 이 존재한다고 볼 수 없음, 누락",
        "해소됨은 아님, 결함 잔존",
        "수정됨 아님, 결함",
    )

    # 못 잡는 **거짓 부재**. `KNOWN_MISS` 는 오탐 전용이라(assertTrue) 이걸 담지
    # 못한다 — 자리가 없어서 한동안 어디에도 적히지 않았다 (QA 2회차 지적).
    #
    # judge 프롬프트는 영어인데, 영어 반박 표지에 대응하는 부정 가드가 없다.
    # 한국어처럼 표지를 좁히는 방식이 통하지 않는다: `not missing`·`nothing is
    # missing` 자체가 정당한 반박이라 `not` 을 부정 표지로 넣으면 그것들이 깨진다.
    # O7 은 INFO(수동 확인 플래그)이고 측정 11 결과 3 이 이미 "정밀도 0, 키워드
    # 보강으로는 못 고친다" 고 결론냈으므로, 여기서는 **고치지 않고 고정**한다.
    # 고쳐지면 아래 테스트가 깨져서 이 서술을 갱신하게 만든다.
    # 축별로 적는다 — 2회차엔 "한국어 잔여 = 역접 하나" 라고 적었는데 사실이 아니었고,
    # 목록이 실제 한계보다 작으면 그 자체가 또 하나의 거짓 부재다 (QA 3회차).
    KNOWN_FALSE_ABSENCE = (
        # (1) 영어 부정 — 표지 앞에 부정이 붙는다. 한국어처럼 표지를 좁혀 막을 수 없다:
        #     `not missing`·`nothing is missing` 자체가 정당한 반박이라
        #     `"not "` 을 부정 표지에 넣으면 그것들이 깨진다 (QA 가 변이로 실증).
        "the function does not raise valueerror as required",
        "the criterion is not actually satisfied, docstring missing",
        # (2) 영어 표지의 의미 반전 — `is present` 는 "기준이 있다"(반박)와
        #     "버그가 있다"(결함)를 구별하지 못한다. 키워드로는 못 가른다.
        "the bug is present in divide",
        "the test no longer passes, wrong import",
        # (3) 영어 등위·양보 접속 — 절 분리자가 `[.;\n—]|but|however` 뿐이라,
        #     다른 기준의 반박과 이 기준의 결함이 **한 절에 공존**하면 삼킨다.
        #     and / although / while / yet / except 가 전부 여기 걸린다.
        "ac1 is in fact correct and the docstring is missing",
        "the docstring is present although the test file is missing",
        "no issues except the missing docstring",
        # (4) 한국어 역접 — `하지만`·`그러나` 가 절 분리자에 없다 (영어 but/however 는 있다)
        "수정됨, 하지만 테스트 누락",
    )

    # 못 잡는 것 (오탐 축). 이 목록은 **대표 표본**이지 전수가 아니다 — O7 의 정밀도는
    # 측정 11 결과 3 에서 이미 0 으로 측정됐고, 여기 적히지 않은 오탐도 있다
    # (`the bug was fixed`, `결함을 수정함` 등). 전수를 적는 것이 목적이 아니라
    # **고쳐졌을 때 알아차리는 것**이 목적이다.
    KNOWN_MISS = (
        # judge 가 자기 이전 판정을 회고하는 문장. "was wrong" 이 문법적으로는
        # 결함 서술과 구별되지 않는다. O7 은 INFO(수동 확인 플래그)이므로
        # 이 오탐은 판정을 오염시키지 않고 잡음으로만 남는다.
        "my earlier needs revision was wrong; it is now correct",
        # 후행 부정 표지(`아님`)를 넣은 대가 — `<표지> 아님`(결함)과 `<결함어> 아님`
        # (반박)은 키워드로 가를 수 없다. 거짓 부재를 막는 쪽을 택했고, 그 값으로
        # 이 오탐을 받는다. 트레이드오프를 숨기지 않으려고 적어 둔다 (QA 4회차).
        "모든 기준 충족됨, 결함 아님",
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

    def test_거짓_부재를_숨기지_않는다(self):
        """`KNOWN_FALSE_ABSENCE` 가 실제로 여전히 삼켜지는지 고정한다.

        거짓 부재는 오탐보다 나쁘다 — 오탐은 사람이 보고 넘기지만 거짓 부재는
        보이지 않는다. 고칠 수 없다면 최소한 **어디가 보이지 않는지**는 보여야 한다.
        고쳐지면 이 테스트가 깨져서 목록과 한계 서술을 갱신하게 만든다.
        """
        for text in self.KNOWN_FALSE_ABSENCE:
            with self.subTest(note=text[:40]):
                self.assertEqual(self.hits(text.lower()), [],
                                 "이제 잡힌다 — KNOWN_FALSE_ABSENCE 와 한계 서술을 갱신하라")

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


class _FakeProc:
    """`subprocess.run` 대역 — opencode 경로를 실제 실행 없이 끝낸다."""
    returncode = 0
    stdout = "ok"
    stderr = ""

class DriverBehaviourTest(unittest.TestCase):
    """드라이버를 **실제로 태워** 배선을 본다 (5차 리뷰 SHOULD-1·2).

    왜 필요한가: 위의 계약 테스트들은 소스 문자열 grep 이라 `def` 가 **있는지**만 본다.
    리뷰가 그 한계를 실증했다 — `_opencode_run` 안의 호스트 라우팅 3줄만 지우고
    `_claude_exec` 정의는 남겨두면, MUST-4 가 고친 바로 그 상태("host 를 기록하되
    제어는 못 한다")가 재생되는데도 grep 테스트는 전부 초록이었다.

    그래서 여기서는 모듈을 import 해 함수를 직접 호출한다. opencode·claude 가 깔려
    있지 않아도 돈다 — 실행 직전 갈림길만 확인하고 실제 프로세스는 띄우지 않는다.
    """

    @classmethod
    def setUpClass(cls):
        import importlib.util
        spec = importlib.util.spec_from_file_location("_cycle_driver_under_test", _DRIVER)
        cls.mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.mod)

    def _routed(self, host: str) -> bool:
        """`HARNESS_DRIVER_HOST=<host>` 에서 `_opencode_run` 이 claude 경로로 갔는가."""
        calls = []
        with mock.patch.dict(os.environ, {"HARNESS_DRIVER_HOST": host}), \
             mock.patch.object(self.mod, "_claude_exec",
                               lambda *a, **k: calls.append(a) or (0, "claude")), \
             mock.patch.object(self.mod.subprocess, "run",
                               lambda *a, **k: _FakeProc()), \
             contextlib.redirect_stdout(io.StringIO()):
            try:
                self.mod._opencode_run(None, "x", attempts=1)
            except Exception as exc:                       # noqa: BLE001
                # opencode 경로는 환경에 따라 다르게 죽을 수 있다. 우리가 보는 것은
                # **claude 로 갔는가** 하나뿐이므로, 안 갔다는 사실만 확정되면 충분하다.
                if not calls:
                    return False
                raise AssertionError(f"claude 로 갔는데 예외: {exc}") from exc
        return bool(calls)

    def test_host_가_claude_code_면_claude_실행으로_라우팅된다(self):
        """이 테스트가 리뷰의 변이 M1(라우팅 3줄 삭제)을 잡는다."""
        self.assertTrue(self._routed("claude-code"),
                        "HARNESS_DRIVER_HOST=claude-code 인데 claude 로 라우팅되지 않았다 — "
                        "스위트는 host 를 기록하는데 드라이버가 제어하지 않으면 "
                        "**틀린 호스트를 측정하고도 맞다고 기록한다**")

    def test_기본_호스트에서는_claude_로_라우팅하지_않는다(self):
        self.assertFalse(self._routed("opencode"),
                         "기본 호스트인데 claude 로 샜다")

    def test_알_수_없는_호스트값은_즉시_실패한다(self):
        with mock.patch.dict(os.environ, {"HARNESS_DRIVER_HOST": "Claude-Code"}), \
             contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(SystemExit) as ctx:
                self.mod._driver_host()
        self.assertEqual(ctx.exception.code, 2)

    def _cost_line(self, inner) -> str:
        buf = io.StringIO()
        with mock.patch.object(self.mod, "_cmd_run", inner), \
             contextlib.redirect_stdout(buf):
            try:
                self.mod.cmd_run(None)
            except RuntimeError:
                pass
        return buf.getvalue()

    def test_비용_줄이_정상_종료에서_나온다(self):
        self.assertIn("[cost]", self._cost_line(lambda args: 0))

    def test_비용_줄이_예외_경로에서도_나온다(self):
        """`finally` 가 아니라 반환 직전에 찍으면 여기서 사라진다."""
        def boom(args):
            raise RuntimeError("중간에 죽음")
        self.assertIn("[cost]", self._cost_line(boom))

    def test_비용_줄을_run_suite_정규식이_실제로_읽는다(self):
        """생산된 줄을 소비자 정규식에 그대로 먹인다 — 포맷이 갈라지면 여기서 깨진다."""
        line = next((l for l in self._cost_line(lambda args: 0).splitlines()
                     if "[cost]" in l), "")
        src = _SUITE.read_text(encoding="utf-8")
        m = re.search(r'_COST_LINE\s*=\s*re\.compile\(\s*r?["\'](.+?)["\']\s*\)', src)
        self.assertTrue(m, "run_suite 에서 _COST_LINE 정규식을 못 찾았다")
        self.assertRegex(line, m.group(1))


    def test_lean_값이_0_1_이_아니면_즉시_실패한다(self):
        """host 는 fail-fast 인데 lean 만 관대하면 거짓 라벨이 남는다 (QA 재판정).

        run_suite 가 이 값으로 `lean` 필드와 `-lean` 파일명을 정하므로, 드라이버가
        `"true"` 를 무시하고 원본으로 도는 동안 스위트는 lean 구간으로 기록한다.
        """
        for bad in ("true", "yes", "2", "on"):
            with self.subTest(value=bad):
                with mock.patch.dict(os.environ, {"HARNESS_LEAN_PROMPT": bad}), \
                     contextlib.redirect_stdout(io.StringIO()):
                    with self.assertRaises(SystemExit) as ctx:
                        self.mod._lean_enabled()
                self.assertEqual(ctx.exception.code, 2)

    def test_lean_술어가_스위트와_드라이버에서_일치한다(self):
        """두 술어가 갈라지면 라벨과 실행이 어긋난다 — 같은 입력에 같은 답이어야 한다."""
        suite_src = _SUITE.read_text(encoding="utf-8")
        ns: dict = {"os": os}
        start = suite_src.index("def _lean_arm(")
        end = suite_src.index("\ndef ", start + 1)
        exec(compile(suite_src[start:end], "<_lean_arm>", "exec"), ns)   # noqa: S102
        for raw in ("", "0", "1"):
            with self.subTest(value=raw), \
                 mock.patch.dict(os.environ, {"HARNESS_LEAN_PROMPT": raw}), \
                 contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(ns["_lean_arm"](), self.mod._lean_enabled())
        for bad in ("true", "2"):
            with self.subTest(value=bad), \
                 mock.patch.dict(os.environ, {"HARNESS_LEAN_PROMPT": bad}):
                with self.assertRaises(SystemExit):
                    ns["_lean_arm"]()

    def test_lean_구간이_호스트_교체보다_먼저_적용된다(self):
        """변이 M8 — `_lean` 호출이 호스트 교체 뒤로 밀리면 claude 구간은 원본을 받는다.

        그러면 `-lean` 파일에 비-lean 프롬프트로 돈 결과가 쌓인다. 실제로 받은
        프롬프트를 비교해야 잡힌다 (소스 grep 으로는 순서를 못 본다).
        """
        seen = []
        original = ("write it (a bare relative name: no leading slash, no directory, "
                    "no placeholder path) now")
        # 표본이 실제 우회책과 맞물리는지 먼저 확인한다 — 안 맞으면 이 테스트는
        # 순서를 검사하는 게 아니라 아무것도 검사하지 않는 것이 된다.
        with mock.patch.dict(os.environ, {"HARNESS_LEAN_PROMPT": "1"}), \
             contextlib.redirect_stdout(io.StringIO()):
            self.assertNotEqual(self.mod._lean(original), original,
                                "표본이 _WORKAROUNDS 와 더 이상 매칭되지 않는다 — 표본을 갱신하라")
        with mock.patch.dict(os.environ, {"HARNESS_DRIVER_HOST": "claude-code",
                                          "HARNESS_LEAN_PROMPT": "1"}), \
             mock.patch.object(self.mod, "_claude_exec",
                               lambda p, *a, **k: seen.append(p) or (0, "ok")), \
             contextlib.redirect_stdout(io.StringIO()):
            self.mod._opencode_run(None, original, attempts=1)
        self.assertTrue(seen, "claude 로 라우팅되지 않았다")
        self.assertNotEqual(seen[0], original,
                            "lean 구간인데 claude 가 원본 프롬프트를 받았다 — "
                            "우회책 제거가 호스트 교체 뒤로 밀렸다")

    @unittest.skipIf(".aif" not in _DRIVER.parents[3].name, "aif 변형이 아닌 사본")
    def test_aif_변형이면_오버레이가_반드시_있다(self):
        """존재 여부를 skip 조건으로 쓰면, 사라졌을 때 조용히 통과한다 (거짓 부재).

        변형 이름으로 기대치를 정하고 **없으면 실패**시킨다 — 드라이버를 재생성하다
        오버레이를 흘리면 여기서 걸린다.
        """
        self.assertTrue(hasattr(self.mod, "_aif_findings"),
                        f"{_DRIVER.parents[3].name} 는 aif 변형인데 _aif_findings 가 없다")

    @unittest.skipIf(".aif" not in _DRIVER.parents[3].name, "aif 변형이 아닌 사본")
    def test_aif_킬스위치가_모델을_부르지_않고_빈_결과를_준다(self):
        """드라이버를 통째로 재생성할 때 오버레이가 사라지면 여기서 잡힌다 (SHOULD-2).

        `CYCLE_AIF=0` 경로만 태운다 — 나머지 경로는 실제로 판정 모델을 호출하므로
        단위 테스트에 넣으면 환경에 따라 멈춘다 (실제로 한 번 멈춰서 알았다).
        """
        with mock.patch.dict(os.environ, {"CYCLE_AIF": "0"}), \
             mock.patch.object(self.mod.subprocess, "run",
                               lambda *a, **k: self.fail("킬스위치인데 외부를 호출했다")), \
             contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(self.mod._aif_findings("code-review", ["x"]), [])

if __name__ == "__main__":
    unittest.main(verbosity=2)
