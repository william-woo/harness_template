#!/usr/bin/env python3
"""verify_loop.py / hill_climb.py 의 계약을 잠근다 (stdlib unittest).

왜 이 파일이 있는가 (F020 리뷰 MUST-1):
  ADR-014 와 체크포인트가 "mock E2E 로 검증함" 이라고 적었는데 **테스트가 0건**이었다.
  F019 1차 MUST 와 정확히 같은 결함 — 문서가 존재하지 않는 검증을 주장한 것이다.

  그 상태에서 리뷰가 실측으로 찾아낸 것들이 여기 전부 들어 있다:
  경로 탈출, 손상 파일 wedge, lost update, 결정론 grader 의 pass 가 루프를 통과시키던 것.

실행:
    python3 tests/test_verify_loop.py
"""
import contextlib
import importlib.util
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_BIN = Path(__file__).resolve().parent.parent / ".claude" / "bin" / "verify_loop.py"
_HILL = Path(__file__).resolve().parent.parent / ".claude" / "bin" / "hill_climb.py"


def _run(root: Path, script: Path, *argv) -> subprocess.CompletedProcess:
    """실제 CLI 경로로 태운다 — 내부 함수를 직접 부르면 argparse 변화를 놓친다."""
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(root)}
    return subprocess.run([sys.executable, str(script), *argv],
                          capture_output=True, text=True, env=env, timeout=60)


class VerifyLoopContractTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / ".claude" / "rubrics").mkdir(parents=True)
        (self.root / ".claude" / "rubrics" / "code-review.md").write_text("# rubric", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    @property
    def _state(self) -> Path:
        return self.root / ".claude" / "state" / "verify-loop"

    def test_feature_id_가_상태_디렉토리를_벗어나지_못한다(self):
        """`start ../../pwn` 이 `.claude/pwn.json` 을 만들었다 (실측).

        F019 의 "원격 ts 가 파일명 선두" 와 같은 클래스다 — 경로 성분이 될 값은
        화이트리스트로 거른다.
        """
        for bad in ("../../pwn", "..", "", "a/b", "x" * 100):
            with self.subTest(feature=bad):
                res = _run(self.root, _BIN, "start", bad)
                self.assertNotEqual(res.returncode, 0, f"{bad!r} 가 통과했다")
        self.assertEqual(list(self.root.glob("**/pwn.json")), [], "상태 디렉토리 밖에 파일이 생겼다")

    def test_결정론_grader_의_pass_는_루프를_통과시키지_않는다(self):
        """`record --grader lint --verdict pass` 한 번에 `passed` 가 됐다 (실측).

        그게 하필 verify-loop.md·reviewer.md 가 권하는 **첫 단계**였다 —
        결정론 게이트 하나를 통과한 것과 판정이 끝난 것은 다르다.
        """
        _run(self.root, _BIN, "start", "F002")
        _run(self.root, _BIN, "record", "F002", "--grader", "lint", "--verdict", "pass")
        loop = json.loads((self._state / "F002.json").read_text(encoding="utf-8"))
        self.assertEqual(loop["status"], "in-loop", "결정론 pass 가 루프를 통과시켰다")
        self.assertIn("lint", loop.get("gates_passed", []))

        _run(self.root, _BIN, "record", "F002", "--grader", "reviewer", "--verdict", "pass")
        loop = json.loads((self._state / "F002.json").read_text(encoding="utf-8"))
        self.assertEqual(loop["status"], "passed", "judge pass 인데 통과하지 않았다")

    def test_손상된_상태_파일이_다른_루프를_막지_않는다(self):
        """손상 1건에 `status`·`record`·`list` 가 전부 죽었다 (실측)."""
        _run(self.root, _BIN, "start", "F001")
        for poison in ('{"feature":"F005","attempts":[{"n":1,', "[1,2]", "null", "", "[" * 100000):
            with self.subTest(poison=poison[:14]):
                (self._state / "F0BAD.json").write_text(poison, encoding="utf-8")
                res = _run(self.root, _BIN, "list")
                self.assertEqual(res.returncode, 0, f"list 가 죽었다: {res.stderr[:200]}")
                self.assertIn("F001", res.stdout, "정상 루프가 목록에서 사라졌다")
                self.assertNotIn("Traceback", res.stderr)

    def test_feature_키가_없는_상태_파일도_record_가_된다(self):
        """`_read_loop` 가 `feature` 를 채우지 않아 `_save` 가 KeyError 로 죽었다.

        내가 F020 에서 손상 방어를 넣을 때 만든 회귀다 — 형태 검증은 했는데
        **저장에 필요한 키**를 빠뜨렸다. 그 루프는 매 `record` 마다 죽어 영구 wedge 였다.
        """
        self._state.mkdir(parents=True, exist_ok=True)
        (self._state / "F009.json").write_text(
            json.dumps({"attempts": [], "revision_count": 0, "status": "in-loop"}),
            encoding="utf-8")
        for run in (1, 2):
            with self.subTest(run=run):
                res = _run(self.root, _BIN, "record", "F009",
                           "--grader", "reviewer", "--verdict", "revision")
                self.assertEqual(res.returncode, 0, f"{run}회차에 죽었다: {res.stderr[:200]}")
                self.assertNotIn("KeyError", res.stderr)
        loop = json.loads((self._state / "F009.json").read_text(encoding="utf-8"))
        self.assertEqual(len(loop["attempts"]), 2)
        self.assertEqual(loop["feature"], "F009", "파일명으로 feature 를 채우지 않았다")

    def test_revision_3회에_에스컬레이션한다(self):
        _run(self.root, _BIN, "start", "F003")
        for _ in range(3):
            _run(self.root, _BIN, "record", "F003", "--grader", "reviewer", "--verdict", "revision")
        loop = json.loads((self._state / "F003.json").read_text(encoding="utf-8"))
        self.assertEqual(loop["status"], "escalated")
        self.assertEqual(loop["revision_count"], 3)

    def test_동시_record_가_서로를_덮어쓰지_않는다(self):
        """reviewer·qa sub-agent 병렬 실행에서 20건 중 3건만 남았다 (실측)."""
        import concurrent.futures
        _run(self.root, _BIN, "start", "F100")
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
            list(pool.map(
                lambda i: _run(self.root, _BIN, "record", "F100", "--grader", "reviewer",
                               "--verdict", "revision", "--notes", f"c{i}"),
                range(20)))
        loop = json.loads((self._state / "F100.json").read_text(encoding="utf-8"))
        self.assertEqual(len(loop["attempts"]), 20, "lost update — 동시 기록이 유실됐다")
        self.assertEqual(sorted(a["n"] for a in loop["attempts"]), list(range(1, 21)))

    def test_잘못된_verdict_는_부작용_없이_거부된다(self):
        """검증 전에 자동 start 가 먼저 돌아 빈 상태 파일이 생겼다 (실측)."""
        res = _run(self.root, _BIN, "record", "F004", "--grader", "reviewer", "--verdict", "bogus")
        self.assertNotEqual(res.returncode, 0)
        self.assertFalse((self._state / "F004.json").exists(), "거부됐는데 상태 파일이 생겼다")

    def test_notes_의_제어문자가_출력에_그대로_나가지_않는다(self):
        _run(self.root, _BIN, "start", "F006")
        # 널바이트는 subprocess 가 거부하므로 CLI 로는 도달 불가 — 실제로 올 수 있는
        # 것(ANSI escape·개행·탭)만 건다. `status` 출력이 터미널에 그대로 렌더됐다.
        _run(self.root, _BIN, "record", "F006", "--grader", "reviewer", "--verdict", "revision",
             "--notes", "위험\x1b[31m빨강\n둘째줄\t탭")
        loop = json.loads((self._state / "F006.json").read_text(encoding="utf-8"))
        notes = loop["attempts"][0]["notes"]
        self.assertNotIn("\x1b", notes, "ANSI escape 가 그대로 저장됐다")
        self.assertNotIn("\n", notes, "개행이 그대로 저장됐다")

    def test_긴_notes_가_절단된다(self):
        _run(self.root, _BIN, "start", "F007")
        _run(self.root, _BIN, "record", "F007", "--grader", "reviewer", "--verdict", "revision",
             "--notes", "가" * 5000)
        loop = json.loads((self._state / "F007.json").read_text(encoding="utf-8"))
        self.assertLessEqual(len(loop["attempts"][0]["notes"]), 2100)


class VerifyLoopReReviewTest(unittest.TestCase):
    """재리뷰(F020 2차)가 실측으로 찾은 MUST 4건 + SHOULD 2건.

    1차 수정이 남긴 것들이다. 공통점은 **방어가 한쪽에만 걸렸다**는 것 —
    `_safe_name` 은 feature 에만, 형태 검증은 `attempts` 에만, 격리는 파싱 오류에만.
    이 리포가 아홉 번 겪은 그 결함 클래스가 수정 자신에게도 일어났다.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / ".claude" / "rubrics").mkdir(parents=True)
        (self.root / ".claude" / "rubrics" / "code-review.md").write_text("# rubric", encoding="utf-8")
        (self.root / "LEAK.md").write_text("비밀", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    @property
    def _state(self) -> Path:
        return self.root / ".claude" / "state" / "verify-loop"

    def _write(self, name: str, body: str) -> None:
        self._state.mkdir(parents=True, exist_ok=True)
        (self._state / name).write_text(body, encoding="utf-8")

    def test_rubric_이름도_경로_성분_검증을_받는다(self):
        """커밋 1731d3e 는 "rubric 이름도 같은 검증" 이라 적었지만 feature 에만 걸려 있었다."""
        for bad in ("../../LEAK", "..", "a/b", "x" * 100):
            with self.subTest(rubric=bad):
                res = _run(self.root, _BIN, "start", "F001", "--rubric", bad)
                self.assertNotEqual(res.returncode, 0, f"{bad!r} 가 통과했다")
        # `rubric` 하위명령도 같은 경로로 읽는다 — 한쪽만 막으면 의미가 없다
        res = _run(self.root, _BIN, "rubric", "../../LEAK")
        self.assertNotEqual(res.returncode, 0)
        self.assertNotIn("비밀", res.stdout, "rubrics 디렉토리 밖 파일이 출력됐다")

    def test_미등록_grader_는_judge_로_승격되지_않고_거부된다(self):
        """`--grader Lint` 오타 하나로 judge pass 가 되어 루프를 통과했다 (fail-open)."""
        for typo in ("Lint", "lnt", "qa_browser", "reviewer2"):
            with self.subTest(grader=typo):
                res = _run(self.root, _BIN, "record", "F010", "--grader", typo, "--verdict", "pass")
                self.assertNotEqual(res.returncode, 0, f"{typo!r} 가 기록됐다")
        self.assertFalse((self._state / "F010.json").exists(),
                         "거부했는데 상태 파일이 만들어졌다 — 부작용이 검증보다 앞섰다")

    def test_feature_키가_파일명과_다르면_파일명을_따른다(self):
        """내용의 `feature` 를 믿으면 락은 F001 인데 쓰기는 F002 로 간다 (교차 lost update)."""
        self._write("F001.json", json.dumps({"feature": "F002", "attempts": [], "revision_count": 0}))
        res = _run(self.root, _BIN, "record", "F001", "--grader", "reviewer", "--verdict", "revision")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertFalse((self._state / "F002.json").exists(), "다른 feature 파일로 기록이 샜다")
        loop = json.loads((self._state / "F001.json").read_text(encoding="utf-8"))
        self.assertEqual(len(loop["attempts"]), 1, "원본이 갱신되지 않았다")
        self.assertEqual(loop["feature"], "F001")

    def test_카운터_타입이_틀려도_영구_wedge_가_되지_않는다(self):
        """`revision_count: "3"` 이면 `+= 1` 이 매 record 마다 TypeError 로 죽었다."""
        poisons = {
            "count-str": {"attempts": [], "revision_count": "3"},
            "count-none": {"attempts": [], "revision_count": None},
            "count-bool": {"attempts": [], "revision_count": True},
            "thr-none": {"attempts": [], "escalation_threshold": None},
            "thr-zero": {"attempts": [], "escalation_threshold": 0},
            "status-bogus": {"attempts": [], "status": "완전히 이상한 값"},
            "rubric-int": {"attempts": [], "rubric": 7},
        }
        for label, body in poisons.items():
            with self.subTest(poison=label):
                fid = f"F{abs(hash(label)) % 900 + 100}"
                self._write(f"{fid}.json", json.dumps(body))
                for round_n in (1, 2):   # 2회차까지 봐야 "영구" wedge 가 드러난다
                    res = _run(self.root, _BIN, "record", fid,
                               "--grader", "reviewer", "--verdict", "revision")
                    self.assertEqual(res.returncode, 0,
                                     f"{label} {round_n}회차에서 죽었다: {res.stdout}{res.stderr}")

    def test_필수키가_없는_attempt_가_목록을_죽이지_않는다(self):
        """`_print_loop` 가 `a['n']` 을 직접 첨자해서, 원소 하나에 list 전체가 죽었다."""
        self._write("F020.json", json.dumps(
            {"attempts": [{}, {"n": 1}, {"n": 2, "grader": "reviewer", "kind": "judge",
                                         "verdict": "pass"}]}))
        self._write("F021.json", json.dumps({"attempts": [], "revision_count": 0}))
        res = _run(self.root, _BIN, "list")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertIn("F021", res.stdout, "정상 루프가 가려졌다")
        self.assertIn("F020", res.stdout)

    def test_형태_오류_파일도_덮어쓰지_않고_격리한다(self):
        """격리가 파싱 오류에만 걸려서, 파싱되는 비정형은 자동 start 가 **덮어썼다**."""
        self._write("F030.json", json.dumps({"attempts": "x", "precious": "지워지면 안 되는 이력"}))
        res = _run(self.root, _BIN, "record", "F030", "--grader", "reviewer", "--verdict", "revision")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        saved = list(self._state.glob("F030.json.corrupt-*"))
        self.assertEqual(len(saved), 1, f"형태 오류가 보존되지 않았다: {list(self._state.iterdir())}")
        self.assertIn("precious", saved[0].read_text(encoding="utf-8"), "보존본에 원본이 없다")

    def test_기존_루프를_start_가_조용히_리셋하지_않는다(self):
        """에스컬레이션 직전 카운터를 0 으로 되돌리는 판정 위조 경로였다."""
        _run(self.root, _BIN, "start", "F040")
        for _ in range(2):
            _run(self.root, _BIN, "record", "F040", "--grader", "reviewer", "--verdict", "revision")
        res = _run(self.root, _BIN, "start", "F040")
        self.assertNotEqual(res.returncode, 0, "기존 이력을 조용히 덮어썼다")
        loop = json.loads((self._state / "F040.json").read_text(encoding="utf-8"))
        self.assertEqual(loop["revision_count"], 2, "이력이 사라졌다")
        # --force 는 명시적 의사표시이므로 허용한다
        self.assertEqual(_run(self.root, _BIN, "start", "F040", "--force").returncode, 0)
        loop = json.loads((self._state / "F040.json").read_text(encoding="utf-8"))
        self.assertEqual(loop["revision_count"], 0, "--force 가 리셋하지 않았다")

    def test_결정론_grader_의_fail_은_설계거부가_아니다(self):
        """lint 실패를 `failed`(Planner·Architect 재설계)로 올리는 건 과하다.

        pass 는 judge 만 인정하면서 fail 은 결정론도 인정하던 비대칭을 없앤다.
        """
        _run(self.root, _BIN, "start", "F050")
        _run(self.root, _BIN, "record", "F050", "--grader", "lint", "--verdict", "fail")
        loop = json.loads((self._state / "F050.json").read_text(encoding="utf-8"))
        self.assertEqual(loop["status"], "in-loop",
                         "결정론 게이트 실패가 루프를 REJECTED 로 만들었다")
        # judge 의 fail 은 여전히 설계 거부다
        _run(self.root, _BIN, "record", "F050", "--grader", "reviewer", "--verdict", "fail")
        loop = json.loads((self._state / "F050.json").read_text(encoding="utf-8"))
        self.assertEqual(loop["status"], "failed")


class VerifyLoopTerminalStateTest(unittest.TestCase):
    """F020 3차 리뷰 MUST-1·2 — 종결 상태와 에스컬레이션.

    MUST-1: 결정론 grader 의 `pass` 가 judge 의 판정을 **지웠다**. 09-28 수정이
      "결정론 pass 가 `passed` 를 만들던 것" 을 고치면서, 만들지 *못하게* 가 아니라
      **지우게** 됐다. `reviewer pass → passed` 다음 `lint pass` 한 번에 `in-loop`
      로 떨어지고, `failed`(설계 거부)조차 lint 한 번으로 풀렸다.
      하필 문서가 권하는 운용(판정 후 게이트 기록)을 따를수록 깨졌다 — 실제로
      F019·F020·F030 세 루프가 그렇게 강등된 채 남아 있었다.

    MUST-2: 에스컬레이션이 배너만 찍고 **아무것도 막지 않았다**. 3회 revision 뒤
      다음 pass 가 그냥 통과했고(F019 는 escalated 직후 pass, 재검토 기록 0건),
      언제 넘었는지도 안 남았다. `architect` 는 `_JUDGE` 에 있어서 reviewer 없이
      루프를 종결시킬 수 있었다 — 두 번째 fail-open 경로였다.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / ".claude" / "rubrics").mkdir(parents=True)
        (self.root / ".claude" / "rubrics" / "code-review.md").write_text("# rubric", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    @property
    def _state(self) -> Path:
        return self.root / ".claude" / "state" / "verify-loop"

    def rec(self, feature: str, grader: str, verdict: str, *extra):
        return _run(self.root, _BIN, "record", feature, "--grader", grader,
                    "--verdict", verdict, "--rubric", "code-review", *extra)

    def loop(self, feature: str) -> dict:
        return json.loads((self._state / f"{feature}.json").read_text(encoding="utf-8"))

    # ── MUST-1 ───────────────────────────────────────────────────────────
    def test_결정론_pass_가_passed_를_지우지_않는다(self):
        self.rec("F001", "reviewer", "pass")
        self.assertEqual(self.loop("F001")["status"], "passed")
        self.rec("F001", "lint", "pass")
        self.assertEqual(self.loop("F001")["status"], "passed",
                         "판정 뒤 게이트를 기록했더니 통과가 취소됐다")

    def test_결정론_pass_가_failed_를_풀지_않는다(self):
        """설계 거부(REJECTED)가 lint 한 번으로 풀리면 거부가 거부가 아니다."""
        self.rec("F002", "reviewer", "fail")
        self.assertEqual(self.loop("F002")["status"], "failed")
        self.rec("F002", "lint", "pass")
        self.assertEqual(self.loop("F002")["status"], "failed")

    def test_결정론_fail_은_종결된_루프를_다시_연다(self):
        """게이트가 깨졌으면 재작업 신호다 — 통과를 유지하면 그게 거짓이다."""
        self.rec("F003", "reviewer", "pass")
        self.rec("F003", "lint", "fail")
        self.assertEqual(self.loop("F003")["status"], "in-loop")

    def test_결정론_pass_는_게이트_목록에_남는다(self):
        self.rec("F004", "lint", "pass")
        self.assertIn("lint", self.loop("F004").get("gates_passed", []))

    # ── MUST-2 ───────────────────────────────────────────────────────────
    def _escalate(self, feature: str) -> None:
        for _ in range(3):
            self.rec(feature, "reviewer", "revision")

    def test_에스컬레이션_진입_시각이_남는다(self):
        self._escalate("F010")
        d = self.loop("F010")
        self.assertEqual(d["status"], "escalated")
        self.assertTrue(d.get("escalated_at"),
                        "언제 넘었는지 없으면 '재검토 대기' 인지 '끝나고 계속' 인지 모른다")

    def test_에스컬레이션_상태에서_ack_없는_pass_는_거부된다(self):
        self._escalate("F011")
        res = self.rec("F011", "reviewer", "pass")
        self.assertNotEqual(res.returncode, 0, "에스컬레이션이 아무것도 막지 않았다")
        self.assertEqual(self.loop("F011")["status"], "escalated", "거부됐는데 상태가 바뀌었다")

    def test_판정한_역할은_자기_에스컬레이션을_승인할_수_없다(self):
        """이 테스트는 **뒤집힌 것**이다 (ADR-024 결정 3 / 실측 2).

        원래 이름은 `test_ack_를_붙이면_통과하고_누가_왜가_남는다` 였고,
        `reviewer pass --ack-escalation "architect: 범위 축소"` 가 rc=0 으로 `passed` 가
        되는 것을 **정상 경로로 고정**하고 있었다. 그런데 그 플래그는 검증되지 않는 자유
        문자열이라, 실제로 기록된 것은 `acked_by=reviewer` 였다 — 판정을 낸 당사자가 자기
        에스컬레이션을 자기 주장 한 줄로 닫은 것이다. 통과하는 테스트가 그 구멍을 계약으로
        만들고 있었다.

        ack 는 ① 재검토를 **수행한** 역할이어야 하고 ② 판정을 낸 역할과 **달라야** 한다.
        reviewer·qa 는 둘 다 위반한다. 그래서 플래그를 삭제하고, 유일한 ack 를
        `--grader architect` 기록으로 뒀다 (아래 `test_architect_재검토가_예산을_갱신한다`).
        """
        for grader in ("reviewer", "qa"):
            with self.subTest(grader=grader):
                f = f"F012{grader}"
                for _ in range(3):
                    self.rec(f, grader, "revision")
                # 플래그 자체가 없어졌다 — argparse 가 거부한다 (rc=2)
                res = self.rec(f, grader, "pass", "--ack-escalation", "architect: 범위 축소")
                self.assertNotEqual(res.returncode, 0, "self-ack 플래그가 아직 살아 있다")
                # 플래그 없이도 당연히 닫히지 않는다
                self.assertNotEqual(self.rec(f, grader, "pass").returncode, 0)
                self.assertEqual(self.loop(f)["status"], "escalated",
                                 f"{grader} 가 자기 에스컬레이션을 닫았다")

    def test_에스컬레이션_아닐_때는_ack_가_필요없다(self):
        """경계 — revision 2회면 아직 유계 안이다."""
        for _ in range(2):
            self.rec("F013", "reviewer", "revision")
        self.assertEqual(self.rec("F013", "reviewer", "pass").returncode, 0)
        self.assertEqual(self.loop("F013")["status"], "passed")

    # ── architect ────────────────────────────────────────────────────────
    def test_architect_단독으로는_루프가_통과되지_않는다(self):
        """architect 는 예산을 갱신할 뿐 **판정을 내지 않는다**.

        rc 기대가 바뀌었다 (ADR-024 결정 3 / 실측 5): 예전엔 `escalated` 가 아닌 상태의
        architect 기록을 **전부 거부**해서 rc=1 이었고, 그 바람에 설계자가 설계 거부를
        낼 수단이 이 도구에 없었다. 지금은 기록은 받되 `passed` 가 되지 않는 것으로
        같은 불변식을 지킨다 — 막아야 하는 것은 기록이 아니라 **종결**이다.
        """
        res = self.rec("F020", "architect", "pass")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        d = self.loop("F020")
        self.assertEqual(d["status"], "in-loop",
                         "architect 가 reviewer 없이 루프를 종결시켰다")
        self.assertNotIn("escalation_acked", d,
                         "에스컬레이션이 없었는데 해제 기록이 생겼다")

    def test_architect_는_에스컬레이션을_받아_재무장한다(self):
        self._escalate("F021")
        res = self.rec("F021", "architect", "pass", "--notes", "feature 분해 결정")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        d = self.loop("F021")
        self.assertEqual(d["status"], "in-loop", "재검토 뒤에는 루프를 다시 돌아야 한다")
        self.assertEqual(d.get("escalation_acked", {}).get("by"), "architect")

    def test_architect_도_등록부에_있어_미등록으로_거부되지_않는다(self):
        """`_JUDGE` 에서 빼면서 등록부 검사에 안 넣으면 '미등록' 으로 막힌다 (실제로 그랬다)."""
        self._escalate("F022")
        res = self.rec("F022", "architect", "pass")
        self.assertNotIn("미등록", res.stdout + res.stderr)

    def test_오타_grader_는_여전히_거부된다(self):
        """등록부를 넓히면서 fail-closed 가 풀리지 않았는지 — 09-28 수정의 회귀 검사."""
        for bad in ("Lint", "lnt", "Architect", "reviewr"):
            with self.subTest(grader=bad):
                self.assertNotEqual(self.rec("F023", bad, "pass").returncode, 0)

class VerifyLoopDerivedStateTest(unittest.TestCase):
    """ADR-024 — `status` 를 전이시키지 않고 이력에서 파생한다.

    3 라운드(09-28 ×2, 10-05)의 결함이 전부 상태 전이 주변에서 났다. 원인은 개별 분기가
    아니라 모델이었다: `status` 하나가 서로 독립인 네 사실(판정·게이트·예산·종결)을 4값
    enum 에 접고 있어서, 모든 규칙이 "둘이 어긋나면 누가 이기나" 로만 표현됐다. 게다가
    결론이 **직전 1건**으로 재계산돼 순서에 의존했다.

    여기 있는 것은 그 모델이 낳은 실측 결함(ADR-024 실측 1·2·4·5·7·9)의 회귀 가드다.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / ".claude" / "rubrics").mkdir(parents=True)
        (self.root / ".claude" / "rubrics" / "code-review.md").write_text("# rubric", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    @property
    def _state(self) -> Path:
        return self.root / ".claude" / "state" / "verify-loop"

    def rec(self, feature: str, grader: str, verdict: str, *extra):
        return _run(self.root, _BIN, "record", feature, "--grader", grader,
                    "--verdict", verdict, "--rubric", "code-review", *extra)

    def loop(self, feature: str) -> dict:
        return json.loads((self._state / f"{feature}.json").read_text(encoding="utf-8"))

    def play(self, feature: str, history) -> None:
        """`[(grader, verdict), ...]` 를 순서대로 기록한다."""
        for grader, verdict in history:
            self.rec(feature, grader, verdict)

    # ── 실측 1: 같은 두 사실이 순서에 따라 다른 결론을 냈다 ──────────────────
    def test_게이트_결과는_기록_순서에_의존하지_않는다(self):
        """`lint fail → reviewer pass` 는 **passed**, 반대 순서는 `in-loop` 였다 (실측).

        전이 모델에서는 결론이 직전 1건으로 정해지므로 같은 두 사실이 순서에 따라 갈렸다.
        파생은 전체 이력을 집계하므로 두 순서가 같은 답을 낸다 — 분기를 더해 맞춘 게 아니다.
        """
        self.play("F101", [("lint", "fail"), ("reviewer", "pass")])
        self.play("F102", [("reviewer", "pass"), ("lint", "fail")])
        self.assertEqual(self.loop("F101")["status"], self.loop("F102")["status"])
        self.assertEqual(self.loop("F101")["status"], "in-loop",
                         "깨진 게이트를 둔 채 통과했다")
        self.assertIn("lint", self.loop("F101")["gates_broken"])

    def test_게이트는_그_grader_의_마지막_verdict_만_본다(self):
        """고쳐서 다시 통과시킨 게이트가 영원히 루프를 막으면 아무도 못 닫는다."""
        self.play("F103", [("lint", "fail"), ("lint", "pass"), ("reviewer", "pass")])
        self.assertEqual(self.loop("F103")["status"], "passed")
        self.assertEqual(self.loop("F103")["gates_broken"], [])

    def test_기록이_없는_게이트는_제약하지_않는다(self):
        """실측: 14 루프 중 7건이 결정론 기록 0건이다. 필수화하면 실무를 깬다."""
        self.play("F104", [("reviewer", "pass")])
        self.assertEqual(self.loop("F104")["status"], "passed")

    # ── 실측 9: 결정론 revision 이 judge 예산을 잠식해 무인 드라이버가 멈췄다 ──
    def test_결정론_revision_은_judge_예산을_쓰지_않는다(self):
        """cycle_driver 는 `--grader test` 로 재작업을 돈다. 그 revision 이 judge 예산을
        3회 잠식해 `escalated` 를 만들었고, 이어지는 `reviewer pass` 가 exit 1 로 막혔다.
        드라이버는 ack 수단이 없으므로 무인 사이클이 **닫히지 않았다** (실측 9).
        """
        for _ in range(5):
            self.rec("F110", "test", "revision")
        d = self.loop("F110")
        self.assertEqual(d["revision_count"], 0, "결정론 재작업이 judge 예산을 먹었다")
        self.assertEqual(d["status"], "in-loop")
        # 드라이버의 실제 흐름: 결정론 게이트가 끝내 통과한 뒤 judge 가 판정한다
        self.rec("F110", "test", "pass")
        res = self.rec("F110", "reviewer", "pass")
        self.assertEqual(res.returncode, 0, f"무인 사이클이 막혔다: {res.stdout}{res.stderr}")
        self.assertEqual(self.loop("F110")["status"], "passed")

    def test_결정론_revision_도_게이트를_깬_것으로_본다(self):
        """`fail` 만 broken 으로 보면 **드라이버가 포기한 루프가 통과로 읽힌다**.

        `cycle_driver` 는 재작업을 `--grader test --verdict revision` 으로 돈다.
        한도까지 고치고도 못 고치면 마지막 기록이 `revision` 인 채 끝난다 — 그 상태가
        `passed` 로 읽히면 "테스트가 깨진 채 통과" 가 된다.

        이 규칙은 ADR-024 가 적은 "마지막 verdict 이 fail 일 때" 보다 한 칸 넓다.
        넓힌 근거가 코드 주석에만 있고 **테스트가 없어서**, `v != "pass"` 를
        `v == "fail"` 로 좁히는 변이가 41건 전부를 통과했다 (Planner 실측).
        """
        self.rec("F120", "test", "revision")
        self.rec("F120", "reviewer", "pass")
        d = self.loop("F120")
        self.assertIn("test", d.get("gates_broken", []),
                      "결정론 revision 이 broken 으로 안 잡혔다")
        self.assertNotEqual(d["status"], "passed",
                            "마지막 테스트 기록이 revision 인데 통과로 읽혔다")

    def test_게이트가_다시_통과하면_broken_에서_빠진다(self):
        """broken 이 누적이면 한 번 깨진 게이트가 영영 통과를 막는다 — 마지막 결과만 유효하다."""
        self.rec("F121", "test", "revision")
        self.rec("F121", "test", "pass")
        self.rec("F121", "reviewer", "pass")
        d = self.loop("F121")
        self.assertEqual(d.get("gates_broken"), [])
        self.assertEqual(d["status"], "passed")

    def test_에스컬레이션_중에도_증거_기록은_막히지_않는다(self):
        """막아야 하는 것은 **종결**이지 기록이 아니다. 증거 기록을 막은 것이 실측 9 의 원인."""
        for _ in range(3):
            self.rec("F111", "reviewer", "revision")
        for grader, verdict in (("test", "revision"), ("test", "pass"),
                                ("reviewer", "revision"), ("qa", "fail")):
            with self.subTest(grader=grader, verdict=verdict):
                res = self.rec("F111", grader, verdict)
                self.assertEqual(res.returncode, 0, f"{grader}:{verdict} 기록이 막혔다")

    # ── 실측 4: ack 뒤 예산이 1회뿐이었다 ───────────────────────────────────
    def test_architect_재검토가_예산을_갱신한다(self):
        """예전엔 `revision_count` 를 아무도 되돌리지 않아 ack 직후 revision 1건에 즉시
        재에스컬레이션했다 — rev 8 짜리 feature 가 architect 왕복 6회를 요구했다 (실측 4).
        예산 파생식이 "마지막 architect 이후" 이므로 갱신이 공짜로 따라온다.
        """
        for _ in range(3):
            self.rec("F120", "reviewer", "revision")
        self.assertEqual(self.loop("F120")["status"], "escalated")
        self.rec("F120", "architect", "pass", "--notes", "범위 축소 결정")
        d = self.loop("F120")
        self.assertEqual(d["status"], "in-loop")
        self.assertEqual(d["revision_count"], 0, "ack 가 예산을 갱신하지 않았다")
        self.assertEqual(d.get("escalation_acked", {}).get("by"), "architect")
        self.assertNotIn("escalated_at", d, "해제됐는데 진입 시각이 남아 있다")
        # 갱신 뒤에도 유계다 — 3회째에 다시 멈춘다
        for n in (1, 2):
            self.rec("F120", "reviewer", "revision")
            self.assertEqual(self.loop("F120")["status"], "in-loop", f"{n}회차에 멈췄다")
        self.rec("F120", "reviewer", "revision")
        self.assertEqual(self.loop("F120")["status"], "escalated", "갱신이 유계를 없앴다")

    # ── 실측 5: architect 의 --verdict 가 무시됐다 ─────────────────────────
    def test_architect_의_verdict_에_의미가_있다(self):
        """`pass`/`revision`/`fail` 셋 다 결과가 같았다 — 필수 인자인데 의미가 없었다.
        반대로 `escalated` 가 아니면 architect 기록이 **전부 거부**돼, 설계자가 설계 거부를
        낼 수단이 이 도구에 없었다 (실측 5).
        """
        self.rec("F130", "architect", "fail", "--notes", "접근 자체가 틀렸다")
        self.assertEqual(self.loop("F130")["status"], "failed",
                         "설계자의 설계 거부가 반영되지 않았다")
        for verdict in ("pass", "revision"):
            with self.subTest(verdict=verdict):
                f = f"F131{verdict}"
                for _ in range(3):
                    self.rec(f, "reviewer", "revision")
                self.rec(f, "architect", verdict, "--notes", "재무장")
                self.assertEqual(self.loop(f)["status"], "in-loop")

    # ── 실측 7: 저장된 요약이 이력과 갈라져 사람이 손으로 고쳤다 ──────────────
    def test_요약_필드를_손으로_고쳐도_다음_record_가_바로잡는다(self):
        """실측 7: 상태 파일에 사람이 직접 넣은 `status_restored` 키가 있었다. 저장된
        `status` 가 이력과 어긋났기 때문이다(`--force` 는 이력을 지우므로 쓸 수 없었다).
        파생이면 그 교정 자체가 불필요해진다 — 저장값은 캐시일 뿐이다.
        """
        self._state.mkdir(parents=True, exist_ok=True)
        (self._state / "F140.json").write_text(json.dumps({
            "attempts": [{"n": 1, "grader": "reviewer", "kind": "judge", "verdict": "revision"},
                         {"n": 2, "grader": "reviewer", "kind": "judge", "verdict": "revision"}],
            "status": "passed",          # 위조: 이력은 revision 2회뿐이다
            "revision_count": 0,
            "gates_passed": ["lint", "qa-browser"],   # 위조: 결정론 기록이 없다
        }), encoding="utf-8")
        res = _run(self.root, _BIN, "status", "F140")
        self.assertIn("IN-LOOP", res.stdout, f"위조된 status 를 그대로 믿었다: {res.stdout}")
        self.rec("F140", "reviewer", "revision")
        d = self.loop("F140")
        self.assertEqual(d["status"], "escalated")
        self.assertEqual(d["revision_count"], 3, "위조된 카운터가 살아남았다")
        self.assertEqual(d["gates_passed"], [], "기록에 없는 게이트가 통과로 남았다")

    def test_저장된_kind_라벨로는_분류를_바꿀_수_없다(self):
        """`kind` 를 믿으면 손으로 고친 라벨 하나가 판정 주체를 바꾼다 — 파생은 grader 이름으로 센다."""
        self._state.mkdir(parents=True, exist_ok=True)
        (self._state / "F141.json").write_text(json.dumps({
            "attempts": [{"n": 1, "grader": "lint", "kind": "judge", "verdict": "pass"}],
        }), encoding="utf-8")
        res = _run(self.root, _BIN, "status", "F141")
        self.assertIn("IN-LOOP", res.stdout, "결정론 grader 가 kind 라벨만으로 판정을 냈다")

    # ── 문서 ↔ 코드 (F020 AC5) ──────────────────────────────────────────────
    def test_문서의_파생_예시가_실제_실행과_일치한다(self):
        """`verify-loop.md` 의 "이력 → 상태" 표 각 행을 CLI 로 실제 실행해 대조한다.

        문서만 고치면 다시 어긋난다 — 3차 리뷰가 지적한 전이표가 정확히 그랬다
        (코드가 바뀌는 동안 표는 `pass → passed` 에 머물렀다). 표가 코드와 1:1 임을
        테스트가 고정한다.
        """
        doc = (Path(__file__).resolve().parent.parent
               / ".claude" / "commands" / "verify-loop.md")
        rows = _parse_history_table(doc.read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(rows), 10,
                                f"문서의 '이력 → 상태' 표를 찾지 못했다 ({len(rows)}행) — "
                                "표가 사라졌거나 형식이 바뀌었다면 이 테스트부터 고쳐라")
        # 행이 맞는지만 보면 표가 **줄어드는** 것은 못 잡는다. 표가 설명해야 할 것을 건다.
        histories = [h for h, _, _ in rows]
        self.assertEqual({e for _, e, _ in rows},
                         {"in-loop", "passed", "failed", "escalated"},
                         "표가 네 상태를 모두 예시하지 않는다")
        order_pair = [("lint", "fail"), ("reviewer", "pass")]
        for h in (order_pair, list(reversed(order_pair))):
            self.assertIn(h, histories,
                          "순서 독립성(ADR-024 결정 2)을 보이는 두 행이 표에 모두 있어야 한다")
        for i, (history, expected, source) in enumerate(rows):
            with self.subTest(row=source):
                feature = f"F2{i:02d}"
                self.play(feature, history)
                self.assertEqual(self.loop(feature)["status"], expected,
                                 f"문서와 코드가 어긋난다: {source}")


# 표 셀 안의 `grader:verdict` (뒤에 `×N` 반복이 붙을 수 있다)
_HISTORY_STEP = re.compile(r"`([a-z][a-z-]*):(pass|revision|fail)`(?:\s*×(\d+))?")


def _parse_history_table(markdown: str):
    """`verify-loop.md` 의 "이력 → 상태" 표를 `(history, expected, 원문)` 목록으로 읽는다.

    표 형식에 의존하므로, 못 찾으면 호출부가 **행 수로 실패**한다 (조용한 통과 금지).
    """
    rows = []
    for line in markdown.splitlines():
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 2:
            continue
        steps = _HISTORY_STEP.findall(cells[0])
        expected = cells[1].strip("`")
        if not steps or expected not in ("in-loop", "passed", "failed", "escalated"):
            continue
        history = []
        for grader, verdict, repeat in steps:
            history.extend([(grader, verdict)] * int(repeat or 1))
        rows.append((history, expected, cells[0]))
    return rows


class CycleDriverEscalationSignalTest(unittest.TestCase):
    """ADR-024 결정 6 — 무인 드라이버가 **존재한 적 없는 키**를 읽고 있었다 (실측 8).

    `cycle_driver.py` 는 `state.get("escalated")` 로 에스컬레이션을 감지했는데, 상태
    파일에 그런 키는 한 번도 없었다 (`status == "escalated"` 가 실제 표현이다). 즉
    에스컬레이션 신호가 드라이버에 **닿은 적이 없다**. 정적으로 고정한다 — 실제 구동은
    OpenCode·로컬 모델을 요구하므로 단위 테스트가 태울 수 없다.
    """

    def test_드라이버가_실존하는_키로_에스컬레이션을_읽는다(self):
        driver = (Path(__file__).resolve().parent.parent
                  / ".claude" / "bin" / "cycle_driver.py")
        if not driver.exists():
            self.skipTest("cycle_driver 는 localllm 계열 변형에만 있다 (d-2 오버레이)")
        # 주석은 떼고 본다 — 수정 자리의 주석이 "예전엔 이 키를 읽었다" 며 옛 키를 **인용**한다.
        # 그 인용을 결함으로 잡으면 설명을 지우게 되고, 다음 사람은 왜 고쳤는지 모른다.
        src = driver.read_text(encoding="utf-8")
        code = "\n".join(line.split("#", 1)[0] for line in src.splitlines())
        self.assertNotIn('state.get("escalated")', code,
                         "상태 파일에 없는 키를 읽는다 — 신호가 영영 닿지 않는다")
        self.assertIn('state.get("status") == "escalated"', code,
                      "에스컬레이션 감지 자체가 사라졌다")


class HillClimbResilienceTest(unittest.TestCase):
    """비정형 트레이스 소스가 Loop 4 집계를 죽이지 않는지 (F020 MUST-5)."""

    POISON_LOOPS = ("[1,2]", "null", '"str"', '{"attempts":"x"}',
                    '{"attempts":[1,2],"revision_count":"3"}')
    POISON_ROWS = ("42", "null", "[1,2]", '{"event":"handoff","files_changed":true}')

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / ".claude" / "state" / "verify-loop").mkdir(parents=True)

    def tearDown(self):
        self.tmp.cleanup()

    def test_비정형_소스에도_집계가_죽지_않는다(self):
        state = self.root / ".claude" / "state"
        for loop_poison in self.POISON_LOOPS:
            for row_poison in self.POISON_ROWS:
                with self.subTest(loop=loop_poison[:14], row=row_poison[:14]):
                    (state / "verify-loop" / "F0BAD.json").write_text(loop_poison, encoding="utf-8")
                    (state / "analytics.jsonl").write_text(row_poison + "\n", encoding="utf-8")
                    res = _run(self.root, _HILL, "analyze")
                    self.assertEqual(res.returncode, 0,
                                     f"analyze 가 죽었다: {res.stderr[:200]}")
                    self.assertNotIn("Traceback", res.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
