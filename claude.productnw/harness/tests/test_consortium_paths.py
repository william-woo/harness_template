#!/usr/bin/env python3
"""수신 봉투의 필드가 inbox 밖으로 파일을 쓰지 못하는지 검증한다 (stdlib unittest).

왜 이 테스트가 있는가 (F019 리뷰 MUST-2):
  Teams·openclaw 수신 경로는 원격 봉투의 `ts` 를 파일명 **선두 성분**으로 썼다.
  당시 위생 처리는 `:` 와 `-` 만 지웠고 `/`·`..` 는 남겨, 실증으로 다음이 가능했다:

      ts="/etc/ABSOLUTE"    → /etc/ABSOLUTE__from-x.json   (inbox 완전 이탈)
      ts="../../../ESCAPED" → inbox 4단계 상위에 파일 생성

  채널에 글을 쓸 수 있는 누구나 폴링 프로세스의 권한으로 임의 위치에 파일을 쓸 수 있었고,
  rc=0 으로 조용히 성공했다. 수정(`_safe_component` 화이트리스트) 이 되돌아가지 않도록 잠근다.

실행:
    python3 tests/test_consortium_paths.py
"""
import importlib.util
import sys
import io
import json
import os
import tempfile
import contextlib
import unittest
from pathlib import Path

_BIN = Path(__file__).resolve().parent.parent / ".claude" / "bin" / "consortium.py"
_spec = importlib.util.spec_from_file_location("consortium", _BIN)
_mod = importlib.util.module_from_spec(_spec)
sys.modules["consortium"] = _mod
_spec.loader.exec_module(_mod)


class SafeComponentTest(unittest.TestCase):
    """`_safe_component` 가 파일명 한 성분으로 안전한 값만 남기는지."""

    def _write_target(self, raw: str, fallback: str = "fb") -> Path:
        """실제 코드와 같은 방식으로 경로를 만든다."""
        inbox = Path("/tmp/consortium-test-inbox")
        return inbox / f"{_mod._safe_component(raw, fallback)}__from-x.json"

    def test_정상_타임스탬프는_보존된다(self):
        """ISO 타임스탬프의 의미 있는 문자(숫자·T·+)는 살아남아야 한다."""
        got = _mod._safe_component("2026-09-16T00:19:53+00:00", "fb")
        self.assertEqual(got, "20260916T001953+0000")   # `-`·`:` 제거, 숫자·T·+ 보존
        self.assertNotIn("/", got)

    def test_절대경로는_inbox를_벗어나지_못한다(self):
        """pathlib 은 절대경로 세그먼트를 만나면 base 를 버린다 — 가장 위험한 경로."""
        out = self._write_target("/etc/ABSOLUTE")
        self.assertEqual(out.parent, Path("/tmp/consortium-test-inbox"))
        self.assertNotIn("etc", out.parts[:-1])

    def test_상대경로_탈출은_차단된다(self):
        """`..` 가 남으면 상위 디렉토리로 올라간다."""
        out = self._write_target("../../../ESCAPED")
        self.assertNotIn("..", str(out))
        self.assertEqual(out.parent, Path("/tmp/consortium-test-inbox"))

    def test_구분자가_모두_제거된다(self):
        """제거 목록이 아니라 허용 목록이므로 새 구분자에도 안전하다."""
        for raw in ("a/b", "a\\b", "a:b", "a\x00b", "a b", "a..b"):
            with self.subTest(raw=raw):
                got = _mod._safe_component(raw, "fb")
                self.assertTrue(got.isalnum() or got == "fb", f"{raw!r} → {got!r}")

    def test_빈값이면_fallback(self):
        """전부 걸러지면 호출부가 준 fallback 을 쓴다 (빈 파일명 방지)."""
        self.assertEqual(_mod._safe_component("", "fb"), "fb")
        self.assertEqual(_mod._safe_component("../", "fb"), "fb")

    def test_from_team_도_위생처리된다(self):
        """봉투의 from_team 역시 원격 입력이다."""
        got = _mod._safe_component("../../evil", "unknown")
        self.assertNotIn("/", got)
        self.assertNotIn("..", got)


class CliSmokeTest(unittest.TestCase):
    """모든 CLI 하위명령이 **적어도 실행은 되는지** (리뷰 MUST-1).

    `roster` 가 `NameError` 로 죽은 채 커밋됐다. 원인은 문서 문구를 고치려고 돌린
    정규식이 소스의 `len(teams)` 까지 친 것인데, **`roster` 에 테스트가 0건이라**
    아무도 잡지 못했다. 정교한 단언보다 "죽지 않는다" 를 거는 것이 먼저다.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        os.environ["CLAUDE_PROJECT_DIR"] = str(self.root)

    def tearDown(self):
        os.environ.pop("CLAUDE_PROJECT_DIR", None)
        self.tmp.cleanup()

    def _run(self, *argv) -> int:
        spec = importlib.util.spec_from_file_location("consortium_cli", _BIN)
        mod = importlib.util.module_from_spec(spec)
        sys.modules["consortium_cli"] = mod
        spec.loader.exec_module(mod)
        old = sys.argv
        sys.argv = ["consortium.py", *argv]
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                mod.main()
            return 0
        except SystemExit as exc:
            return int(exc.code or 0)
        finally:
            sys.argv = old

    def test_모든_하위명령이_예외없이_실행된다(self):
        self.assertEqual(self._run("init", "team-a", "--agents", "developer"), 0)
        for argv in (["roster"],
                     ["send", "--to", "team-b", "--role", "developer",
                      "--cycle", "C1", "--msg", "스모크"],
                     ["inbox"],
                     ["self"],
                     ["gateway", "slack"],
                     ["gateway", "teams"],
                     ["gateway", "telegram"]):
            with self.subTest(cmd=" ".join(argv)):
                self.assertEqual(self._run(*argv), 0, f"`{' '.join(argv)}` 가 실패했다")


class OutboxPoisonTest(unittest.TestCase):
    """찢어지거나 타입이 다른 outbox 파일 1건이 **발신 큐를 멈추지 않는지**.

    QA 가 `_send_openclaw` 만 방어가 빠진 것을 잡았다(형제 3경로엔 있었다).
    고치고 보니 네 경로 **전부** 같은 구멍이 더 있었다 — `json.loads` 는 성공해도
    `[1,2]` 같은 비객체면 바로 뒤의 `.get()` 이 try **밖**에서 터진다.
    "읽기를 감쌌다" 와 "한 건이 큐를 멈추지 않는다" 는 다르다.

    그래서 이 테스트는 발신 경로를 **한 목록으로 묶어** 돈다 — 경로별 사본을
    만들면 하나에만 케이스를 추가하고 끝난다 (이 파일이 여섯 번 겪은 일이다).
    """

    POISONS = ("{ torn", "[1, 2]", '"just a string"', "null", "123")

    # 자격증명이 없으면 각 발신기가 루프 **전에** 반환하므로, 읽기 경계에 닿지 않는다.
    _CREDS = {
        "CONSORTIUM_TEAMS_WEBHOOK": "https://example.invalid/webhook",
        "CONSORTIUM_SLACK_TOKEN": "xoxb-x", "CONSORTIUM_SLACK_CHANNEL": "C0",
        "CONSORTIUM_TELEGRAM_TOKEN": "1:x", "CONSORTIUM_TELEGRAM_CHAT_ID": "-100",
    }

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self._env = {k: os.environ.get(k) for k in
                     ("CLAUDE_PROJECT_DIR", *self._CREDS)}
        os.environ["CLAUDE_PROJECT_DIR"] = str(Path(self.tmp.name))
        os.environ.update(self._CREDS)

    def tearDown(self):
        for key, val in self._env.items():
            if val is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = val
        self.tmp.cleanup()

    def _fresh(self, poison: str):
        """팀 등록 + 정상 메시지 1건 + 오염 파일 1건을 둔 모듈을 만든다."""
        spec = importlib.util.spec_from_file_location("consortium_poison", _BIN)
        mod = importlib.util.module_from_spec(spec)
        sys.modules["consortium_poison"] = mod
        spec.loader.exec_module(mod)
        old = sys.argv
        for argv in (["consortium.py", "init", "team-c", "--agents", "qa"],
                     ["consortium.py", "send", "--to", "team-d", "--role", "qa",
                      "--cycle", "GOOD", "--msg", "정상"]):
            sys.argv = argv
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    mod.main()
            except SystemExit:
                pass
        sys.argv = old
        (mod._OUTBOX / "0000-bad.json").write_text(poison, encoding="utf-8")
        # 네트워크는 태우지 않는다 — 이 테스트가 보는 것은 **읽기 경계**다.
        mod._post_teams = lambda *a, **k: (False, "mock: 전송 안 함")
        mod._slack_api = lambda *a, **k: (False, "mock: 전송 안 함")
        mod._telegram_api = lambda *a, **k: (False, "mock: 전송 안 함")
        return mod

    def test_발신_경로가_오염된_outbox_파일에_멈추지_않는다(self):
        senders = ("_send_openclaw", "_send_teams", "_send_slack", "_send_telegram")
        for poison in self.POISONS:
            for name in senders:
                with self.subTest(poison=poison, sender=name):
                    mod = self._fresh(poison)
                    fn = getattr(mod, name)
                    buf = io.StringIO()
                    try:
                        with contextlib.redirect_stdout(buf):
                            fn("teams") if name == "_send_openclaw" else fn()
                    except Exception as exc:  # noqa: BLE001
                        self.fail(f"{name} 이 {poison!r} 에 죽었다: {type(exc).__name__}: {exc}")
                    self.assertIn("읽기 실패", buf.getvalue(),
                                  f"{name} 이 {poison!r} 를 건너뛰었다고 보고하지 않았다")


class StateFilePoisonTest(unittest.TestCase):
    """상태 파일 5종 × 오염 5종을 **한 목록으로** 돈다 (F019 9차 MUST-2).

    `OutboxPoisonTest` 와 같은 설계다. 여섯 지점이 제각각 방어하던 것을
    `_load_state` 하나로 모았고, 이 테스트가 그 단일 주소를 지킨다.

    실측으로 확인됐던 것들: `slack-seen.json` 이 `[1,2]` 면 `sorted(seen)` 이
    TypeError 로 죽고 그 crash 가 영속 **전**이라 매 폴링 재적재됐다.
    `received-seen.json`·`telegram-offset.json` 은 열거형 except 라 깊은 중첩의
    `RecursionError` 를 놓쳤다 — 이 파일이 세 라운드에 걸쳐 배운 바로 그 교훈이다.
    """

    POISONS = ("{ torn", "[1, 2]", '"just a string"', "null", "[" * 100000)
    STATE_FILES = ("slack-seen.json", "received-seen.json", "telegram-offset.json",
                   "slack-cursor.json", "roster.json")

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self._env = {k: os.environ.get(k) for k in
                     ("CLAUDE_PROJECT_DIR", "CONSORTIUM_SLACK_TOKEN", "CONSORTIUM_SLACK_CHANNEL",
                      "CONSORTIUM_TELEGRAM_TOKEN", "CONSORTIUM_TELEGRAM_CHAT_ID",
                      "CONSORTIUM_TEAMS_TOKEN", "CONSORTIUM_TEAMS_TEAM_ID",
                      "CONSORTIUM_TEAMS_CHANNEL_ID")}
        os.environ.update({
            "CLAUDE_PROJECT_DIR": str(Path(self.tmp.name)),
            "CONSORTIUM_SLACK_TOKEN": "x", "CONSORTIUM_SLACK_CHANNEL": "C0",
            "CONSORTIUM_TELEGRAM_TOKEN": "1:x", "CONSORTIUM_TELEGRAM_CHAT_ID": "-100",
            "CONSORTIUM_TEAMS_TOKEN": "t", "CONSORTIUM_TEAMS_TEAM_ID": "t",
            "CONSORTIUM_TEAMS_CHANNEL_ID": "c"})

    def tearDown(self):
        for key, val in self._env.items():
            if val is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = val
        self.tmp.cleanup()

    def test_상태파일이_오염돼도_수신이_죽지_않는다(self):
        for fname in self.STATE_FILES:
            for poison in self.POISONS:
                with self.subTest(file=fname, poison=poison[:12]):
                    spec = importlib.util.spec_from_file_location("consortium_state", _BIN)
                    mod = importlib.util.module_from_spec(spec)
                    sys.modules["consortium_state"] = mod
                    spec.loader.exec_module(mod)
                    mod._STATE.mkdir(parents=True, exist_ok=True)
                    if fname != "roster.json":
                        mod._ROSTER.write_text(
                            json.dumps({"self": "team-b", "teams": {"team-b": {}}}),
                            encoding="utf-8")
                    (mod._STATE / fname).write_text(poison, encoding="utf-8")
                    # 네트워크는 태우지 않는다 — 이 테스트가 보는 것은 상태 파일이다.
                    mod._slack_api = lambda *a, **k: (True, {"ok": True, "messages": [],
                                                             "has_more": False})
                    mod._graph_get = lambda *a, **k: (True, {"value": []})
                    mod._telegram_api = lambda *a, **k: (True, [])
                    for fn in (mod._receive_slack, mod._receive_teams, mod._receive_telegram):
                        try:
                            with contextlib.redirect_stdout(io.StringIO()):
                                fn()
                        except Exception as exc:  # noqa: BLE001
                            self.fail(f"{fn.__name__} 이 {fname}={poison[:12]!r} 에 죽었다: "
                                      f"{type(exc).__name__}: {exc}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
