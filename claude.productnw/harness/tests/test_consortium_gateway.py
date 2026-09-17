#!/usr/bin/env python3
"""Teams 게이트웨이 완전 왕복 E2E — mock 서버로 발신·수신을 실제로 태운다 (stdlib only).

왜 이 테스트가 있는가 (F019 AC2 / 리뷰 MUST-1):
  인수 기준 AC2 는 "Teams 게이트웨이 발신(webhook)+수신(Graph 폴링) 실구현 —
  **mock 완전 왕복 E2E**" 였다. 코드는 실재했지만 **그 왕복을 태워 본 적이 없었다**.
  그럼에도 `ADR-013` 과 `docs/consortium-gateway-setup.md §9-3` 은 "모킹으로 왕복
  검증함"이라고 적고 있었다 — 존재하지 않는 검증을 주장한 것이다.

  이 테스트가 그 주장을 사실로 만든다. 없으면 AC2 는 다시 미입증이 된다.

무엇을 태우는가:
  node-a 의 outbox → (mock webhook POST) → 채널 저장소 →
  (mock Graph GET) → node-b 의 inbox

  네트워크 경계만 mock 이고, 봉투 포장·base64 복원·seen 멱등·수신자 필터는 **실제 코드**다.

실행:
    python3 tests/test_consortium_gateway.py
"""
import importlib.util
import json
import os
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

_BIN = Path(__file__).resolve().parent.parent / ".claude" / "bin" / "consortium.py"

# 채널 저장소 — mock webhook 이 받은 것을 mock Graph 가 그대로 돌려준다 (Teams 채널 역할)
_CHANNEL: list[dict] = []


class _MockTeams(BaseHTTPRequestHandler):
    """웹훅 수신(POST)과 Graph 메시지 조회(GET)를 한 서버에서 흉내 낸다."""

    def do_POST(self):
        """`/webhook` — Teams Incoming Webhook. 받은 카드를 채널에 적재한다."""
        body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        card = json.loads(body)
        # Graph 메시지 형태로 감싼다 — 실제 채널이 카드를 body.content 에 담는 것과 같게
        _CHANNEL.append({
            "id": f"msg{len(_CHANNEL) + 1}",
            "body": {"contentType": "html", "content": json.dumps(card, ensure_ascii=False)},
        })
        self.send_response(200)
        self.send_header("Content-Length", "2")
        self.end_headers()
        self.wfile.write(b"ok")

    def do_GET(self):
        """`/teams/{t}/channels/{c}/messages` — Graph 폴링 응답."""
        payload = json.dumps({"value": list(reversed(_CHANNEL))}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *a):
        """테스트 출력을 더럽히지 않는다."""


def _load_consortium(root: Path):
    """프로젝트 루트를 바꿔 모듈을 새로 적재한다 (모듈 상수가 경로를 잡으므로 재적재 필요)."""
    os.environ["CLAUDE_PROJECT_DIR"] = str(root)
    spec = importlib.util.spec_from_file_location("consortium", _BIN)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["consortium"] = mod
    spec.loader.exec_module(mod)
    return mod


class TeamsGatewayRoundTripTest(unittest.TestCase):
    """발신 → 채널 → 수신 왕복에서 계약이 무손실로 도착하는지."""

    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), _MockTeams)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def setUp(self):
        _CHANNEL.clear()
        self.tmp = tempfile.TemporaryDirectory()
        self.base = f"http://127.0.0.1:{self.port}"
        # 환경변수는 프로세스 전역이다 — 복원하지 않으면 뒤에 도는 테스트가
        # mock 서버를 가리킨 채 실행되고, 그 순서 의존을 나중에 진단하기 어렵다.
        self._env_backup = {k: os.environ.get(k) for k in (
            "CONSORTIUM_GRAPH_BASE", "CONSORTIUM_TEAMS_WEBHOOK",
            "CONSORTIUM_TEAMS_TOKEN", "CONSORTIUM_TEAMS_TEAM_ID",
            "CONSORTIUM_TEAMS_CHANNEL_ID")}
        os.environ["CONSORTIUM_GRAPH_BASE"] = self.base
        os.environ["CONSORTIUM_TEAMS_WEBHOOK"] = f"{self.base}/webhook"
        os.environ["CONSORTIUM_TEAMS_TOKEN"] = "mock-token"
        os.environ["CONSORTIUM_TEAMS_TEAM_ID"] = "t1"
        os.environ["CONSORTIUM_TEAMS_CHANNEL_ID"] = "c1"

    def tearDown(self):
        for key, val in self._env_backup.items():
            if val is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = val
        self.tmp.cleanup()

    def _run(self, mod, argv: list[str]) -> int:
        """실제 CLI 경로(argparse)로 태운다 — 인자 객체를 손으로 흉내 내면
        시그니처가 바뀔 때 테스트만 조용히 어긋난다."""
        old = sys.argv
        sys.argv = ["consortium.py", *argv]
        try:
            mod.main()          # main() 은 sys.exit() 으로 끝난다
            return 0
        except SystemExit as exc:
            return int(exc.code or 0)
        finally:
            sys.argv = old

    def _node(self, name: str, team: str):
        """노드 하나를 만들고 팀을 등록한 뒤 모듈을 반환한다."""
        root = Path(self.tmp.name) / name
        root.mkdir(parents=True, exist_ok=True)
        mod = _load_consortium(root)
        self._run(mod, ["init", team, "--agents", "developer"])
        return mod, root

    def test_발신부터_수신까지_계약이_무손실로_도착한다(self):
        """AC2 의 '완전 왕복' — 이 테스트가 그 주장의 근거다."""
        # ── 보내는 쪽
        send_mod, _ = self._node("node-a", "team-a")
        self._run(send_mod, ["send", "--to", "team-b", "--role", "developer",
                             "--cycle", "C1", "--msg", "설계 완료, 구현 요청"])
        self.assertEqual(send_mod._send_teams(), 0, "발신이 실패했다")
        self.assertEqual(len(_CHANNEL), 1, "채널에 카드가 적재되지 않았다")

        # ── 받는 쪽 (별도 노드 = 별도 프로젝트 루트)
        recv_mod, recv_root = self._node("node-b", "team-b")
        self.assertEqual(recv_mod._receive_teams(), 0, "수신이 실패했다")

        inbox = list((recv_root / ".claude/state/consortium/inbox").glob("*.json"))
        self.assertEqual(len(inbox), 1, f"inbox 적재 실패: {inbox}")
        got = json.loads(inbox[0].read_text(encoding="utf-8"))

        self.assertEqual(got["from_team"], "team-a")
        self.assertEqual(got["to_team"], "team-b")
        self.assertEqual(got["cycle_id"], "C1")
        self.assertEqual(got["msg"], "설계 완료, 구현 요청")
        self.assertEqual(got["status"], "received")

    def test_재폴링해도_중복_적재되지_않는다(self):
        """seen 멱등 — 폴링은 반복 실행되므로 이것이 깨지면 inbox 가 불어난다."""
        send_mod, _ = self._node("node-a", "team-a")
        self._run(send_mod, ["send", "--to", "team-b", "--role", "qa",
                             "--cycle", "C2", "--msg", "검증 요청"])
        send_mod._send_teams()

        recv_mod, recv_root = self._node("node-b", "team-b")
        recv_mod._receive_teams()
        recv_mod._receive_teams()          # 같은 채널을 다시 폴링

        inbox = list((recv_root / ".claude/state/consortium/inbox").glob("*.json"))
        self.assertEqual(len(inbox), 1, f"재폴링에 중복 적재됨: {inbox}")

    def test_남의_메시지는_받지_않는다(self):
        """수신자 필터 — 채널은 공유되므로 to_team 이 내가 아니면 무시해야 한다."""
        send_mod, _ = self._node("node-a", "team-a")
        self._run(send_mod, ["send", "--to", "team-z", "--role", "developer",
                             "--cycle", "C3", "--msg", "제3자 앞 메시지"])
        send_mod._send_teams()

        recv_mod, recv_root = self._node("node-b", "team-b")
        recv_mod._receive_teams()

        inbox = list((recv_root / ".claude/state/consortium/inbox").glob("*.json"))
        self.assertEqual(inbox, [], f"남의 메시지를 받았다: {inbox}")


class OpenClawBridgeRoundTripTest(unittest.TestCase):
    """openclaw 호스트의 핸드오프 브리지 왕복 (ADR-013).

    ADR-013 은 "모킹으로 왕복 검증함"이라 적었지만 그 모킹은 리포에 없었다.
    여기가 그 주장의 근거다. Teams 와 달리 네트워크가 아니라 **디렉토리 핸드오프**라
    courier(채널 I/O 담당)를 파일 이동으로 흉내 내면 왕복이 완성된다.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def _node(self, name: str, team: str):
        root = Path(self.tmp.name) / name
        root.mkdir(parents=True, exist_ok=True)
        mod = _load_consortium(root)
        old = sys.argv
        sys.argv = ["consortium.py", "init", team, "--agents", "developer"]
        try:
            mod.main()
        except SystemExit:
            pass
        finally:
            sys.argv = old
        return mod, root

    def test_핸드오프_디렉토리로_왕복한다(self):
        """outbox → openclaw-outbound → (courier) → openclaw-inbound → inbox."""
        send_mod, send_root = self._node("oc-a", "team-a")
        old = sys.argv
        sys.argv = ["consortium.py", "send", "--to", "team-b", "--role", "developer",
                    "--cycle", "C9", "--msg", "브리지 왕복"]
        try:
            send_mod.main()
        except SystemExit:
            pass
        finally:
            sys.argv = old

        self.assertEqual(send_mod._send_openclaw("teams"), 0, "브리지 발신 실패")
        outbound = list((send_root / ".claude/state/consortium/openclaw-outbound").glob("*.json"))
        self.assertEqual(len(outbound), 1, f"openclaw-outbound 적재 실패: {outbound}")

        # ── courier 흉내: 발신측 outbound 를 수신측 inbound 로 옮긴다 (실제로는 채널 경유)
        recv_mod, recv_root = self._node("oc-b", "team-b")
        inbound = recv_root / ".claude/state/consortium/openclaw-inbound"
        inbound.mkdir(parents=True, exist_ok=True)
        (inbound / outbound[0].name).write_text(
            outbound[0].read_text(encoding="utf-8"), encoding="utf-8")

        self.assertEqual(recv_mod._receive_openclaw(), 0, "브리지 수신 실패")
        inbox = list((recv_root / ".claude/state/consortium/inbox").glob("*.json"))
        self.assertEqual(len(inbox), 1, f"inbox 적재 실패: {inbox}")
        got = json.loads(inbox[0].read_text(encoding="utf-8"))
        self.assertEqual(got["from_team"], "team-a")
        self.assertEqual(got["cycle_id"], "C9")
        self.assertEqual(got["msg"], "브리지 왕복")


_GOOD_DROP = json.dumps({"consortium_msg": {
    "from_team": "team-a", "to_team": "team-b", "role": "developer",
    "cycle_id": "C1", "msg": "정상 메시지", "ts": "2026-09-17T00:00:00+00:00",
    "stage": "", "status": "queued",
}}, ensure_ascii=False)


class PoisonPillTest(unittest.TestCase):
    """드롭 하나가 수신 큐 전체를 멈추지 않는지 (리뷰 MUST-3 + 재리뷰 연장).

    1차 수정은 `json.loads` 만 감쌌다. 재리뷰가 **유효한 JSON** 세 종류로 같은
    영구 wedge 를 재현했다 — 파싱을 통과해도 그 뒤 단계가 무방어였기 때문이다:
      · 최상위가 객체가 아님 (`[1,2,3]`) → `record.get` 에서 AttributeError
      · 계약이 객체가 아님 (`"consortium_msg": "x"`) → 같은 자리
      · 과다 길이 ts → 파일명이 255바이트를 넘어 OSError

    어느 경우든 그 파일이 processed/ 로 가지 못해 **매 실행 같은 지점에서 다시
    죽고**, 뒤에 있던 정상 메시지는 영원히 도착하지 않는다. 그래서 이 테스트는
    "손상 JSON" 한 종류가 아니라 **처리 단계별 실패**를 모두 건다.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def _node(self, name: str):
        root = Path(self.tmp.name) / name
        root.mkdir(parents=True, exist_ok=True)
        mod = _load_consortium(root)
        old = sys.argv
        sys.argv = ["consortium.py", "init", "team-b", "--agents", "developer"]
        try:
            mod.main()
        except SystemExit:
            pass
        finally:
            sys.argv = old
        return mod, root

    def test_처리불가_드롭은_격리되고_정상분은_처리된다(self):
        poisons = {
            "손상 JSON": "{ 손상된 JSON",
            "최상위가 배열": "[1, 2, 3]",
            "계약이 문자열": json.dumps({"consortium_msg": "x"}),
            "계약이 배열": json.dumps({"consortium_msg": [1]}),
            # RecursionError 는 열거형 except 튜플을 뚫었다 — 예외를 세려 들면
            # 반드시 빠뜨린다는 증거라서 목록에 남긴다 (3차 리뷰 MUST-A).
            "깊은 중첩": "[" * 100000,
        }
        for label, body in poisons.items():
            with self.subTest(poison=label):
                mod, root = self._node(f"node-{abs(hash(label))}")
                inbound = root / ".claude/state/consortium/openclaw-inbound"
                inbound.mkdir(parents=True, exist_ok=True)
                (inbound / "00-bad.json").write_text(body, encoding="utf-8")
                (inbound / "01-good.json").write_text(_GOOD_DROP, encoding="utf-8")

                self.assertEqual(mod._receive_openclaw(), 0, f"{label} 때문에 수신이 실패했다")
                state = root / ".claude/state/consortium"
                self.assertEqual(len(list((state / "inbox").glob("*.json"))), 1,
                                 f"{label} 뒤의 정상 메시지가 처리되지 않았다")
                self.assertEqual(len(list((inbound / "quarantine").glob("*.json"))), 1,
                                 f"{label} 이 격리되지 않았다")
                self.assertEqual(list(inbound.glob("*.json")), [],
                                 "큐가 비워지지 않았다 — 재실행 시 같은 지점에서 또 죽는다")

    def test_과다_길이_ts_는_잘려서_적재된다(self):
        """계약 자체는 유효하므로 격리가 아니라 **적재**되어야 한다 — 파일명만 잘린다."""
        mod, root = self._node("node-longts")
        inbound = root / ".claude/state/consortium/openclaw-inbound"
        inbound.mkdir(parents=True, exist_ok=True)
        (inbound / "00-long.json").write_text(json.dumps({"consortium_msg": {
            "from_team": "team-a", "to_team": "team-b", "role": "developer",
            "cycle_id": "C2", "msg": "긴 ts", "ts": "A" * 300,
        }}, ensure_ascii=False), encoding="utf-8")

        self.assertEqual(mod._receive_openclaw(), 0, "긴 ts 때문에 수신이 실패했다")
        inbox = list((root / ".claude/state/consortium/inbox").glob("*.json"))
        self.assertEqual(len(inbox), 1, "유효한 계약이 적재되지 않았다")
        self.assertLessEqual(len(inbox[0].name.encode()), 255, "파일명이 여전히 상한을 넘는다")
        self.assertEqual(list(inbound.glob("*.json")), [], "큐가 비워지지 않았다")

    def test_오염된_ts_는_inbox_경로를_벗어나지_못한다(self):
        """`_safe_component` 단위 테스트와 별개 — **호출을 빼먹는 회귀**를 잡는다."""
        mod, root = self._node("node-escape")
        state = root / ".claude/state/consortium"
        inbound = state / "openclaw-inbound"
        inbound.mkdir(parents=True, exist_ok=True)
        (inbound / "00-escape.json").write_text(json.dumps({"consortium_msg": {
            "from_team": "../../../etc", "to_team": "team-b", "role": "developer",
            "cycle_id": "C3", "msg": "탈출 시도", "ts": "../../../../ESCAPED",
        }}, ensure_ascii=False), encoding="utf-8")

        self.assertEqual(mod._receive_openclaw(), 0)
        written = list((state / "inbox").glob("*.json"))
        self.assertEqual(len(written), 1, "적재되지 않았다")
        self.assertEqual(written[0].parent.resolve(), (state / "inbox").resolve(),
                         "inbox 밖에 파일이 쓰였다 — 경로 탈출")
        self.assertNotIn("..", written[0].name)


class MessageDurabilityTest(unittest.TestCase):
    """넣은 메시지가 사라지지 않는지 — 큐의 최소 계약 (3차 리뷰 MUST-B).

    파일명은 ts + 팀 id 로 만드는데 둘 다 유일하지 않다. `_now()` 는 **초 단위**라
    같은 초에 send 2회면 outbox 가 1건이 되고 첫 메시지가 rc=0 인 채 사라졌다
    (CLI 기동이 ~50ms 이므로 스크립트 fan-out 에서 자연 발생한다).
    수신 경로는 ts·from_team 을 원격이 정하므로 더 쉽게 겹친다 — 드롭 파일명
    꼬리를 접미사로 붙여도 courier 명명 규약에 따라 상수가 될 수 있다.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def _run(self, mod, *argv):
        old = sys.argv
        sys.argv = ["consortium.py", *argv]
        try:
            return mod.main()
        except SystemExit as exc:
            return exc.code
        finally:
            sys.argv = old

    def test_같은_초에_보낸_두_메시지가_모두_남는다(self):
        root = Path(self.tmp.name) / "send-node"
        root.mkdir(parents=True, exist_ok=True)
        mod = _load_consortium(root)
        self._run(mod, "init", "team-a")
        self._run(mod, "send", "--to", "team-b", "--role", "developer", "--cycle", "C1", "--msg", "첫번째")
        self._run(mod, "send", "--to", "team-b", "--role", "developer", "--cycle", "C2", "--msg", "두번째")

        outbox = list((root / ".claude/state/consortium/outbox").glob("*.json"))
        got = sorted(json.loads(f.read_text(encoding="utf-8"))["msg"] for f in outbox)
        self.assertEqual(got, ["두번째", "첫번째"], f"메시지가 덮어써졌다: {got}")

    def test_팀id_앞뒤_공백은_정규화된다(self):
        """검증만 strip 하면 `' team-b'` 가 통과해 수신측이 조용히 버린다."""
        root = Path(self.tmp.name) / "strip-node"
        root.mkdir(parents=True, exist_ok=True)
        mod = _load_consortium(root)
        self._run(mod, "init", "team-a")
        self._run(mod, "send", "--to", " team-b ", "--role", "developer", "--cycle", "C1", "--msg", "공백")

        outbox = list((root / ".claude/state/consortium/outbox").glob("*.json"))
        self.assertEqual(len(outbox), 1)
        self.assertEqual(json.loads(outbox[0].read_text(encoding="utf-8"))["to_team"], "team-b")
        self.assertNotIn(" ", outbox[0].name)

    def test_잘못된_팀id_는_거부된다(self):
        root = Path(self.tmp.name) / "reject-node"
        root.mkdir(parents=True, exist_ok=True)
        mod = _load_consortium(root)
        self._run(mod, "init", "team-a")
        rc = self._run(mod, "send", "--to", "Team_B", "--role", "developer", "--cycle", "C1", "--msg", "x")
        self.assertEqual(rc, 1, "형식 위반 team-id 가 통과했다")
        self.assertEqual(list((root / ".claude/state/consortium/outbox").glob("*.json")), [])

    def test_동일한_ts_와_from_team_드롭이_겹쳐도_둘_다_남는다(self):
        root = Path(self.tmp.name) / "recv-node"
        root.mkdir(parents=True, exist_ok=True)
        mod = _load_consortium(root)
        self._run(mod, "init", "team-b")

        inbound = root / ".claude/state/consortium/openclaw-inbound"
        inbound.mkdir(parents=True, exist_ok=True)
        for idx, label in enumerate(("FIRST", "SECOND")):
            # 꼬리가 상수가 되는 courier 명명 규약 — 프로젝트 자체 왕복 테스트가 쓰는 형태다
            (inbound / f"{idx}__to-team-b.json").write_text(json.dumps({"consortium_msg": {
                "from_team": "team-a", "to_team": "team-b", "role": "developer",
                "cycle_id": "C1", "msg": label, "ts": "2026-09-17T00:00:00+00:00",
            }}, ensure_ascii=False), encoding="utf-8")

        self.assertEqual(mod._receive_openclaw(), 0)
        inbox = list((root / ".claude/state/consortium/inbox").glob("*.json"))
        got = sorted(json.loads(f.read_text(encoding="utf-8"))["msg"] for f in inbox)
        self.assertEqual(got, ["FIRST", "SECOND"], f"수신 메시지가 덮어써졌다: {got}")


class SeenPersistenceTest(unittest.TestCase):
    """`received-seen.json` 이 깨져도 Teams 수신이 계속되는지 (재리뷰 신규 MUST).

    MUST-3 수정이 "seen 은 반드시 영속" 을 도입하면서 그 파일이 단일 장애점이 됐다.
    읽기가 무방어면 torn write(디스크 풀·프로세스 kill) 한 번에 수신이 **영구 정지**한다.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env_backup = {k: os.environ.get(k) for k in
                           ("CONSORTIUM_TEAMS_TOKEN", "CONSORTIUM_TEAMS_TEAM_ID",
                            "CONSORTIUM_TEAMS_CHANNEL_ID")}
        os.environ.update({"CONSORTIUM_TEAMS_TOKEN": "tok",
                           "CONSORTIUM_TEAMS_TEAM_ID": "t",
                           "CONSORTIUM_TEAMS_CHANNEL_ID": "c"})

    def tearDown(self):
        for key, val in self.env_backup.items():
            if val is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = val
        self.tmp.cleanup()

    def test_깨진_seen_기록에서_복구한다(self):
        root = Path(self.tmp.name) / "node"
        root.mkdir(parents=True, exist_ok=True)
        mod = _load_consortium(root)
        old = sys.argv
        sys.argv = ["consortium.py", "init", "team-b", "--agents", "developer"]
        try:
            mod.main()
        except SystemExit:
            pass
        finally:
            sys.argv = old

        mod._graph_get = lambda url, token: (True, {"value": [{"id": "gid-1", "body": {"content": "noise"}}]})
        state = root / ".claude/state/consortium"
        seen_file = state / "received-seen.json"
        seen_file.write_text('["m1", "m2', encoding="utf-8")  # torn write 재현

        self.assertEqual(mod._receive_teams(), 0, "깨진 seen 때문에 수신이 죽었다")
        self.assertEqual(mod._receive_teams(), 0, "재실행에서도 죽었다 — 영구 정지")
        self.assertEqual(json.loads(seen_file.read_text(encoding="utf-8")), ["gid-1"],
                         "seen 이 복구되지 않았다")
        self.assertEqual(list(state.glob("*.tmp")), [], "원자적 교체의 임시 파일이 남았다")


if __name__ == "__main__":
    unittest.main(verbosity=2)
