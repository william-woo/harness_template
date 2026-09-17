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
        os.environ["CONSORTIUM_GRAPH_BASE"] = self.base
        os.environ["CONSORTIUM_TEAMS_WEBHOOK"] = f"{self.base}/webhook"
        os.environ["CONSORTIUM_TEAMS_TOKEN"] = "mock-token"
        os.environ["CONSORTIUM_TEAMS_TEAM_ID"] = "t1"
        os.environ["CONSORTIUM_TEAMS_CHANNEL_ID"] = "c1"

    def tearDown(self):
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


class PoisonPillTest(unittest.TestCase):
    """손상된 드롭 하나가 수신 큐 전체를 멈추지 않는지 (리뷰 MUST-3).

    수정 전에는 `json.loads` 가 무방어라 손상 1건이 traceback 으로 루프를 끝냈고,
    그 파일이 processed/ 로 가지 못해 **매 실행 같은 지점에서 다시 죽었다** —
    뒤에 있던 정상 메시지는 영원히 도착하지 않는다.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def test_손상된_드롭은_격리되고_정상분은_처리된다(self):
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

        inbound = root / ".claude/state/consortium/openclaw-inbound"
        inbound.mkdir(parents=True, exist_ok=True)
        (inbound / "00-bad.json").write_text("{ 손상된 JSON", encoding="utf-8")
        (inbound / "01-good.json").write_text(json.dumps({"consortium_msg": {
            "from_team": "team-a", "to_team": "team-b", "role": "developer",
            "cycle_id": "C1", "msg": "정상 메시지", "ts": "2026-09-17T00:00:00+00:00",
            "stage": "", "status": "queued",
        }}, ensure_ascii=False), encoding="utf-8")

        self.assertEqual(mod._receive_openclaw(), 0, "손상분 때문에 수신이 실패했다")

        state = root / ".claude/state/consortium"
        self.assertEqual(len(list((state / "inbox").glob("*.json"))), 1,
                         "손상분 뒤의 정상 메시지가 처리되지 않았다")
        self.assertEqual(len(list((inbound / "quarantine").glob("*.json"))), 1,
                         "손상분이 격리되지 않았다")
        self.assertEqual(list(inbound.glob("*.json")), [],
                         "큐가 비워지지 않았다 — 재실행 시 같은 지점에서 또 죽는다")


if __name__ == "__main__":
    unittest.main(verbosity=2)
