#!/usr/bin/env python3
"""Teams 게이트웨이 완전 왕복 E2E — mock 서버로 발신·수신을 실제로 태운다 (stdlib only).

왜 이 테스트가 있는가 (F019 AC2 / 리뷰 MUST-1):
  인수 기준 AC2 는 "Teams 게이트웨이 발신(webhook)+수신(Graph 폴링) 실구현 —
  **mock 완전 왕복 E2E**" 였다. 코드는 실재했지만 **그 왕복을 태워 본 적이 없었다**.
  그럼에도 `ADR-013` 과 `docs/consortium-gateway-setup.md §10-3` 은 "모킹으로 왕복
  검증함"이라고 적고 있었다 — 존재하지 않는 검증을 주장한 것이다.

  이 테스트가 그 주장을 사실로 만든다. 없으면 AC2 는 다시 미입증이 된다.

무엇을 태우는가:
  node-a 의 outbox → (mock webhook POST) → 채널 저장소 →
  (mock Graph GET) → node-b 의 inbox

  네트워크 경계만 mock 이고, 봉투 포장·base64 복원·seen 멱등·수신자 필터는 **실제 코드**다.

실행:
    python3 tests/test_consortium_gateway.py
"""
import base64
import importlib.util
import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.parse
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
        """`_safe_component` 단위 테스트와 별개 — **호출을 빼먹는 회귀**를 잡는다.

        `ts` 는 계약 필수 필드가 아니라 검증이 걸리지 않는다. 그래서 위생 처리
        (`_safe_component`)가 유일한 방어이고, 이 경로가 살아 있는지 여기서 본다.
        """
        mod, root = self._node("node-escape")
        state = root / ".claude/state/consortium"
        inbound = state / "openclaw-inbound"
        inbound.mkdir(parents=True, exist_ok=True)
        (inbound / "00-escape.json").write_text(json.dumps({"consortium_msg": {
            "from_team": "team-a", "to_team": "team-b", "role": "developer",
            "cycle_id": "C3", "msg": "탈출 시도", "ts": "../../../../ESCAPED",
        }}, ensure_ascii=False), encoding="utf-8")

        self.assertEqual(mod._receive_openclaw(), 0)
        written = list((state / "inbox").glob("*.json"))
        self.assertEqual(len(written), 1, "적재되지 않았다")
        self.assertEqual(written[0].parent.resolve(), (state / "inbox").resolve(),
                         "inbox 밖에 파일이 쓰였다 — 경로 탈출")
        self.assertNotIn("..", written[0].name)

    def test_계약을_위반한_원격_레코드는_거부된다(self):
        """수신에도 계약 검증이 걸리는지 (ADR-012 결정 3 수정).

        `_safe_component` 는 파일명만 지킨다. `role`·`cycle_id` 는 downstream
        product-cycle 라우팅 키로 흘러가므로, 계약 검증이 없으면 원격이
        `to_team` 만 맞추고 나머지 필드에 무엇이든 넣을 수 있다.
        """
        violations = {
            "team-id 형식 위반": {"from_team": "../../../etc", "to_team": "team-b",
                              "role": "developer", "cycle_id": "C1", "msg": "x"},
            "필수 필드 누락(role)": {"from_team": "team-a", "to_team": "team-b",
                                "role": "", "cycle_id": "C1", "msg": "x"},
            "stage 값 오류": {"from_team": "team-a", "to_team": "team-b", "role": "developer",
                          "cycle_id": "C1", "msg": "x", "stage": "배포해줘"},
            # 비문자열은 `str(m.get(f,""))` 비교에서 전부 "존재" 로 통과했다 —
            # str(None)="None", str([])="[]", str(False)="False".
            # send 는 argparse 가 문자열만 주므로 **수신 전용** 구멍이었고,
            # 하필 ADR-012 정정문이 "계약 검증이 지킨다" 고 적은 라우팅 키였다.
            "role=null": {"from_team": "team-a", "to_team": "team-b", "role": None,
                          "cycle_id": "C1", "msg": "x"},
            "role=[]": {"from_team": "team-a", "to_team": "team-b", "role": [],
                        "cycle_id": "C1", "msg": "x"},
            "cycle_id=false": {"from_team": "team-a", "to_team": "team-b", "role": "developer",
                               "cycle_id": False, "msg": "x"},
        }
        for label, contract in violations.items():
            with self.subTest(violation=label):
                mod, root = self._node(f"node-v{abs(hash(label))}")
                state = root / ".claude/state/consortium"
                inbound = state / "openclaw-inbound"
                inbound.mkdir(parents=True, exist_ok=True)
                (inbound / "00-bad.json").write_text(
                    json.dumps({"consortium_msg": contract}, ensure_ascii=False), encoding="utf-8")
                (inbound / "01-good.json").write_text(_GOOD_DROP, encoding="utf-8")

                self.assertEqual(mod._receive_openclaw(), 0)
                self.assertEqual(len(list((state / "inbox").glob("*.json"))), 1,
                                 f"{label} 이 적재됐거나 정상분이 막혔다")
                self.assertEqual(len(list((inbound / "quarantine").glob("*.json"))), 1,
                                 f"{label} 이 격리되지 않았다")


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

    def test_같은_초에_보낸_메시지가_openclaw_큐에서도_모두_남는다(self):
        """QA 가 잡은 결함 — `_write_unique` 가 outbox·inbox 에만 적용됐었다.

        courier 가 비동기로 가져가는 `openclaw-outbound/` 도 큐인데 `write_text` +
        `Path.rename` 이라 같은 이름이 조용히 교체됐다. 실측: `--send` 3회 →
        outbound 1건·sent 1건, **2건이 rc=0 인 채 소멸**.

        3차 MUST-B 의 수정이 "갈 곳에 다 가지 않은" 네 번째 사례다. 그래서 이
        테스트는 발신 경로를 **send 쪽과 별도로** 건다 — 한쪽만 고쳐도 통과하면
        같은 일이 또 난다.
        """
        root = Path(self.tmp.name) / "oc-send-node"
        root.mkdir(parents=True, exist_ok=True)
        mod = _load_consortium(root)
        self._run(mod, "init", "team-a")
        for idx in (1, 2, 3):
            self._run(mod, "send", "--to", "team-b", "--role", "developer",
                      "--cycle", f"C{idx}", "--msg", f"MSG-{idx}")
            self.assertEqual(mod._send_openclaw("teams"), 0)

        state = root / ".claude/state/consortium"
        outbound = sorted(json.loads(f.read_text(encoding="utf-8"))["consortium_msg"]["msg"]
                          for f in (state / "openclaw-outbound").glob("*.json"))
        sent = sorted(json.loads(f.read_text(encoding="utf-8"))["msg"]
                      for f in (state / "outbox" / "sent").glob("*.json"))
        self.assertEqual(outbound, ["MSG-1", "MSG-2", "MSG-3"], f"큐에서 소멸: {outbound}")
        self.assertEqual(sent, ["MSG-1", "MSG-2", "MSG-3"], f"발신 기록 소멸: {sent}")

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


class ReceiveBoundaryParityTest(unittest.TestCase):
    """**같은** 악성 입력을 두 transport 에 태운다 (F019 에스컬레이션 산출).

    수신 경계가 2벌로 복제돼 있던 동안, 수정은 리뷰어가 찔러본 사본에만 갔다 —
    `except Exception` 이 openclaw 에만 적용되고 teams 는 열거형으로 남아 같은
    `RecursionError` 로 뚫렸다. 클래스를 닫으려던 수정조차 인스턴스만 닫은 것이다.

    그래서 이 테스트는 transport 별로 복제하지 않는다. 복제하면 테스트가 같은 병에
    걸린다 — 한쪽에만 케이스를 추가하고 끝난다. 악성 입력 목록은 **하나**이고,
    두 transport 가 그것을 공유한다.
    """

    POISONS = {
        "최상위가 배열": [1, 2, 3],
        "계약이 문자열": {"consortium_msg": "x"},
        "과다 중첩": None,          # 아래에서 raw 문자열로 특별 처리
        "과다 길이 ts": {"consortium_msg": {
            "from_team": "team-a", "to_team": "team-b", "role": "developer",
            "cycle_id": "C1", "msg": "x", "ts": "A" * 300}},
        "계약 위반(team-id)": {"consortium_msg": {
            "from_team": "../../etc", "to_team": "team-b", "role": "developer",
            "cycle_id": "C1", "msg": "x"}},
    }

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

    def test_openclaw_경계가_모든_악성입력을_견딘다(self):
        for label, payload in self.POISONS.items():
            with self.subTest(transport="openclaw", poison=label):
                mod, root = self._node(f"oc-{abs(hash(label))}")
                inbound = root / ".claude/state/consortium/openclaw-inbound"
                inbound.mkdir(parents=True, exist_ok=True)
                body = "[" * 100000 if payload is None else json.dumps(payload, ensure_ascii=False)
                (inbound / "00-bad.json").write_text(body, encoding="utf-8")
                (inbound / "01-good.json").write_text(_GOOD_DROP, encoding="utf-8")

                self.assertEqual(mod._receive_openclaw(), 0, f"{label} 으로 수신이 죽었다")
                # 악성분이 거부될지 위생 처리 후 적재될지는 입력마다 다르다.
                # 경계의 계약은 하나 — **정상분은 반드시 도착하고 큐는 비워진다**.
                arrived = [json.loads(f.read_text(encoding="utf-8"))["msg"]
                           for f in (root / ".claude/state/consortium/inbox").glob("*.json")]
                self.assertIn("정상 메시지", arrived, f"{label} 뒤의 정상분이 막혔다: {arrived}")
                self.assertEqual(list(inbound.glob("*.json")), [], "큐가 비워지지 않았다")

    def test_slack_경계가_같은_악성입력을_견딘다(self):
        """transport 가 늘 때마다 여기 등재한다 — 사본 테스트를 만들면 같은 병에 걸린다."""
        good = base64.b64encode(json.dumps({
            "from_team": "team-a", "to_team": "team-b", "role": "developer",
            "cycle_id": "C1", "msg": "정상", "ts": "2026-09-19T00:00:00+00:00",
        }, ensure_ascii=False).encode()).decode()

        for label, payload in self.POISONS.items():
            with self.subTest(transport="slack", poison=label):
                mod, root = self._node(f"sl-{abs(hash(label))}")
                raw = "[" * 100000 if payload is None else json.dumps(payload, ensure_ascii=False)
                evil = base64.b64encode(raw.encode()).decode()
                mod._slack_api = lambda tok, m, pl, get=False, _e=evil, _g=good: (True, {
                    "ok": True, "has_more": False, "messages": [
                        {"ts": "1700000002.000100", "text": mod._ENVELOPE_PREFIX + _g},
                        {"ts": "1700000001.000100", "text": mod._ENVELOPE_PREFIX + _e},
                    ]})
                os.environ.update({"CONSORTIUM_SLACK_TOKEN": "xoxb-x",
                                   "CONSORTIUM_SLACK_CHANNEL": "C0X"})
                try:
                    self.assertEqual(mod._receive_slack(), 0, f"{label} 으로 폴링이 죽었다")
                finally:
                    for key in ("CONSORTIUM_SLACK_TOKEN", "CONSORTIUM_SLACK_CHANNEL"):
                        os.environ.pop(key, None)
                arrived = [json.loads(f.read_text(encoding="utf-8"))["msg"]
                           for f in (root / ".claude/state/consortium/inbox").glob("*.json")]
                self.assertIn("정상", arrived, f"{label} 뒤의 정상분이 막혔다: {arrived}")

    def test_teams_경계가_같은_악성입력을_견딘다(self):
        good = base64.b64encode(json.dumps({
            "from_team": "team-a", "to_team": "team-b", "role": "developer",
            "cycle_id": "C1", "msg": "정상", "ts": "2026-09-17T00:00:00+00:00",
        }, ensure_ascii=False).encode()).decode()

        for label, payload in self.POISONS.items():
            with self.subTest(transport="teams", poison=label):
                mod, root = self._node(f"tm-{abs(hash(label))}")
                raw = "[" * 100000 if payload is None else json.dumps(payload, ensure_ascii=False)
                evil = base64.b64encode(raw.encode()).decode()
                mod._graph_get = lambda url, token, _e=evil, _g=good: (True, {"value": [
                    {"id": "gid-evil-01", "body": {"content": mod._ENVELOPE_PREFIX + _e}},
                    {"id": "gid-good-01", "body": {"content": mod._ENVELOPE_PREFIX + _g}},
                ]})
                os.environ.update({"CONSORTIUM_TEAMS_TOKEN": "tok",
                                   "CONSORTIUM_TEAMS_TEAM_ID": "t",
                                   "CONSORTIUM_TEAMS_CHANNEL_ID": "c"})
                try:
                    self.assertEqual(mod._receive_teams(), 0, f"{label} 으로 폴링이 죽었다")
                finally:
                    for key in ("CONSORTIUM_TEAMS_TOKEN", "CONSORTIUM_TEAMS_TEAM_ID",
                                "CONSORTIUM_TEAMS_CHANNEL_ID"):
                        os.environ.pop(key, None)
                arrived = [json.loads(f.read_text(encoding="utf-8"))["msg"]
                           for f in (root / ".claude/state/consortium/inbox").glob("*.json")]
                self.assertIn("정상", arrived, f"{label} 뒤의 정상분이 막혔다: {arrived}")


class MoveResilienceTest(unittest.TestCase):
    """큐 파일 **이동**이 실패해도 큐가 멈추지 않는지 (QA 2차 FAIL).

    유일성을 `os.link` 배타 생성에 맡겼더니 `rename` 이 되던 것을 못 하게 됐다:
    디렉토리에 걸리지 않고, `fs.protected_hardlinks=1`(Ubuntu 기본)에서 타 계정 소유
    파일은 EPERM 이다. 게다가 격리 이동이 `except` 핸들러 **안**이라 거기서 터지면
    잡는 곳이 없었다 — 그 핸들러가 막으려던 wedge 가 핸들러 자신에서 났다.

    이 테스트는 "이동이 실패하는 두 환경"을 만들어 **정상분이 도착하는지**를 본다.
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

    def test_디렉토리_드롭이_큐를_멈추지_않는다(self):
        """`os.link` 는 디렉토리에 걸리지 않는다 — `rename` 폴백이 받아야 한다."""
        mod, root = self._node("dir-drop")
        inbound = root / ".claude/state/consortium/openclaw-inbound"
        inbound.mkdir(parents=True, exist_ok=True)
        (inbound / "0000-dir.json").mkdir()
        (inbound / "01-good.json").write_text(_GOOD_DROP, encoding="utf-8")

        for run in (1, 2):
            with self.subTest(run=run):
                self.assertEqual(mod._receive_openclaw(), 0, f"{run}회차에 수신이 죽었다")
        arrived = [json.loads(f.read_text(encoding="utf-8"))["msg"]
                   for f in (root / ".claude/state/consortium/inbox").glob("*.json")]
        self.assertEqual(arrived, ["정상 메시지"], f"정상분이 막히거나 중복됐다: {arrived}")

    def test_os_link_이_EPERM_인_환경에서도_수신이_계속된다(self):
        """courier 가 별도 계정이면 모든 드롭이 이 경로를 탄다."""
        mod, root = self._node("eperm")
        inbound = root / ".claude/state/consortium/openclaw-inbound"
        inbound.mkdir(parents=True, exist_ok=True)
        (inbound / "00-bad.json").write_text("{ 손상", encoding="utf-8")
        (inbound / "01-good.json").write_text(_GOOD_DROP, encoding="utf-8")

        real_link = os.link
        os.link = lambda *a, **k: (_ for _ in ()).throw(
            PermissionError(1, "Operation not permitted"))
        try:
            for run in (1, 2):
                with self.subTest(run=run):
                    self.assertEqual(mod._receive_openclaw(), 0, f"{run}회차에 수신이 죽었다")
        finally:
            os.link = real_link

        arrived = [json.loads(f.read_text(encoding="utf-8"))["msg"]
                   for f in (root / ".claude/state/consortium/inbox").glob("*.json")]
        self.assertEqual(arrived, ["정상 메시지"],
                         f"정상분이 막히거나 중복 적재됐다: {arrived}")
        self.assertEqual(list(inbound.glob("*.json")), [], "큐가 비워지지 않았다")

    def test_이동_불가여도_다른_메시지는_흐른다(self):
        """이동이 **모두** 실패하는 최악에서도 정상분 처리가 막히지 않아야 한다."""
        mod, root = self._node("immovable")
        inbound = root / ".claude/state/consortium/openclaw-inbound"
        inbound.mkdir(parents=True, exist_ok=True)
        (inbound / "00-bad.json").write_text("{ 손상", encoding="utf-8")
        (inbound / "01-good.json").write_text(_GOOD_DROP, encoding="utf-8")

        boom = lambda *a, **k: (_ for _ in ()).throw(OSError(5, "I/O error"))
        real_link, real_rename = os.link, os.rename
        os.link, os.rename = boom, boom
        try:
            self.assertEqual(mod._receive_openclaw(), 0, "이동 실패가 루프를 죽였다")
        finally:
            os.link, os.rename = real_link, real_rename
        # 이동이 전부 실패했으니 inbox 적재도 못 하지만, **예외 없이 rc=0** 이어야 한다.
        # 그것이 "한 항목이 다른 항목을 막지 않는다" 의 최소 형태다.

    def test_선재_이름_충돌이_있어도_기존_파일을_보존한다(self):
        mod, root = self._node("collide")
        state = root / ".claude/state/consortium"
        inbound = state / "openclaw-inbound"
        (inbound / "processed").mkdir(parents=True, exist_ok=True)
        (inbound / "processed" / "01-good.json").write_text("먼저 있던 것", encoding="utf-8")
        (inbound / "01-good.json").write_text(_GOOD_DROP, encoding="utf-8")

        self.assertEqual(mod._receive_openclaw(), 0)
        processed = sorted(p.name for p in (inbound / "processed").glob("*.json"))
        self.assertEqual(len(processed), 2, f"선재 파일이 덮어써졌다: {processed}")
        self.assertEqual((inbound / "processed" / "01-good.json").read_text(encoding="utf-8"),
                         "먼저 있던 것", "선재 파일 내용이 바뀌었다")


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


class _MockTelegram(BaseHTTPRequestHandler):
    """Bot API 흉내 — **플랫폼 규칙을 강제한다**.

    이전 mock 은 작성자와 무관하게 모든 update 를 돌려줬다. 그래서 "팀마다 봇을 만들어
    같은 그룹에 넣으면 서로의 메시지를 본다" 는 **틀린 전제**가 5건의 왕복 테스트를
    통과했다 — Telegram Bot FAQ 는 정반대를 말한다:

        "bots will not be able to see messages from other bots regardless of mode"

    봇은 자기가 보낸 것도 `getUpdates` 로 되받지 못한다. 그래서 이 mock 은 **봇이
    작성한 메시지를 getUpdates 결과에서 제외**한다. 그 규칙을 넣자마자 옛 왕복
    테스트는 성립하지 않게 되고, 그것이 정확한 신호다.
    """

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)))
        method = self.path.rsplit("/", 1)[-1]
        if method == "sendMessage":
            _TG_CHANNEL.append({"update_id": len(_TG_CHANNEL) + 1,
                                "by_bot": True,          # ← 봇이 쓴 글
                                "message": {"message_id": len(_TG_CHANNEL) + 1,
                                            "from": {"is_bot": True},
                                            "chat": {"id": body["chat_id"]},
                                            "text": body["text"]}})
            payload = {"ok": True, "result": {"message_id": len(_TG_CHANNEL)}}
        elif method == "getUpdates":
            off = int(body.get("offset") or 0)
            payload = {"ok": True,
                       "result": [{k: v for k, v in u.items() if k != "by_bot"}
                                  for u in _TG_CHANNEL
                                  if u["update_id"] >= off and not u.get("by_bot")]}
        else:
            payload = {"ok": False, "description": f"unknown method {method}"}
        raw = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, *a):
        """테스트 출력을 더럽히지 않는다."""


_TG_CHANNEL: list[dict] = []
_TG_CHAT = "-1001234567890"


def _tg_human_post(contract: dict, chat_id: str = _TG_CHAT) -> None:
    """사람이 그룹에 봉투를 붙여 넣은 상황 (봇이 아니므로 getUpdates 에 잡힌다)."""
    envelope = "[[consortium-msg]]" + base64.b64encode(
        json.dumps(contract, ensure_ascii=False).encode()).decode()
    _TG_CHANNEL.append({"update_id": len(_TG_CHANNEL) + 1,
                        "message": {"message_id": len(_TG_CHANNEL) + 1,
                                    "from": {"is_bot": False},
                                    "chat": {"id": chat_id},
                                    "text": f"확인 바랍니다\n\n{envelope}"}})


class TelegramHumanLoopTest(unittest.TestCase):
    """Telegram 은 **사람이 끼는 흐름** 전용이다 (ADR-013 결정 5 정정).

    봇↔봇은 플랫폼이 막으므로 컨소시엄 팀 노드끼리의 자동 왕복에는 쓸 수 없다.
    남는 용도는 "에이전트가 사람에게 알리고, 사람이 지시를 준다" 이고,
    이 클래스가 그 범위만 검증한다 — 할 수 없는 것을 할 수 있다고 적지 않는다.
    """

    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), _MockTelegram)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def setUp(self):
        _TG_CHANNEL.clear()
        self.tmp = tempfile.TemporaryDirectory()
        self._env_backup = {k: os.environ.get(k) for k in (
            "CONSORTIUM_TELEGRAM_BASE", "CONSORTIUM_TELEGRAM_TOKEN", "CONSORTIUM_TELEGRAM_CHAT_ID")}
        os.environ["CONSORTIUM_TELEGRAM_BASE"] = f"http://127.0.0.1:{self.port}"
        os.environ["CONSORTIUM_TELEGRAM_TOKEN"] = "123:mock-token"
        os.environ["CONSORTIUM_TELEGRAM_CHAT_ID"] = _TG_CHAT

    def tearDown(self):
        for key, val in self._env_backup.items():
            if val is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = val
        self.tmp.cleanup()

    def _run(self, mod, argv):
        old = sys.argv
        sys.argv = ["consortium.py", *argv]
        try:
            mod.main()
            return 0
        except SystemExit as exc:
            return int(exc.code or 0)
        finally:
            sys.argv = old

    def _node(self, name: str, team: str):
        root = Path(self.tmp.name) / name
        root.mkdir(parents=True, exist_ok=True)
        mod = _load_consortium(root)
        self._run(mod, ["init", team, "--agents", "developer"])
        return mod, root

    def test_봇이_보낸_메시지는_다른_봇이_받지_못한다(self):
        """**이 테스트가 없어서 틀린 전제가 5건을 통과했다** (리뷰 MUST-1).

        Bot FAQ 의 규칙을 mock 이 강제하므로, 봇↔봇 왕복을 주장하는 코드·문서가
        생기면 여기서 걸린다.
        """
        send_mod, _ = self._node("tg-a", "team-a")
        self._run(send_mod, ["send", "--to", "team-b", "--role", "developer",
                             "--cycle", "TG1", "--msg", "봇이 보낸 것"])
        self.assertEqual(send_mod._send_telegram(), 0, "발신 자체는 된다")
        self.assertEqual(len(_TG_CHANNEL), 1, "채널에 적재되지 않았다")

        recv_mod, recv_root = self._node("tg-b", "team-b")
        self.assertEqual(recv_mod._receive_telegram(), 0)
        self.assertEqual(list((recv_root / ".claude/state/consortium/inbox").glob("*.json")), [],
                         "봇이 쓴 글이 다른 봇에게 전달됐다 — 플랫폼 규칙 위반 모델")

    def test_사람이_보낸_봉투는_수신된다(self):
        recv_mod, recv_root = self._node("tg-b", "team-b")
        _tg_human_post({"from_team": "team-a", "to_team": "team-b", "role": "developer",
                        "cycle_id": "TG2", "msg": "사람이 준 지시", "ts": "2026-09-19T00:00:00+00:00"})
        self.assertEqual(recv_mod._receive_telegram(), 0)
        inbox = list((recv_root / ".claude/state/consortium/inbox").glob("*.json"))
        self.assertEqual(len(inbox), 1, "사람이 쓴 봉투가 적재되지 않았다")
        self.assertEqual(json.loads(inbox[0].read_text(encoding="utf-8"))["msg"], "사람이 준 지시")

    def test_다른_채팅에서_온_봉투는_거부된다(self):
        """봇은 **누구에게나 DM 을 받는다** — chat 필터가 없으면 주입구가 된다 (MUST-2)."""
        recv_mod, recv_root = self._node("tg-b", "team-b")
        _tg_human_post({"from_team": "team-a", "to_team": "team-b", "role": "developer",
                        "cycle_id": "EVIL", "msg": "낯선 사람의 DM", "ts": "2026-09-19T00:00:00+00:00"},
                       chat_id="55555")          # 설정된 그룹이 아닌 DM
        self.assertEqual(recv_mod._receive_telegram(), 0)
        self.assertEqual(list((recv_root / ".claude/state/consortium/inbox").glob("*.json")), [],
                         "설정되지 않은 채팅에서 온 메시지가 적재됐다")

    def test_재폴링해도_중복_적재되지_않는다(self):
        recv_mod, recv_root = self._node("tg-b", "team-b")
        _tg_human_post({"from_team": "team-a", "to_team": "team-b", "role": "qa",
                        "cycle_id": "TG3", "msg": "검증 요청", "ts": "2026-09-19T00:00:00+00:00"})
        recv_mod._receive_telegram()
        recv_mod._receive_telegram()
        self.assertEqual(len(list((recv_root / ".claude/state/consortium/inbox").glob("*.json"))), 1)

    def test_본문이_상한을_넘으면_잘라_보내지_않고_거부한다(self):
        send_mod, send_root = self._node("tg-a", "team-a")
        self._run(send_mod, ["send", "--to", "team-b", "--role", "developer",
                             "--cycle", "TG4", "--msg", "가" * 4000])
        self.assertEqual(send_mod._send_telegram(), 1, "상한 초과인데 성공으로 보고했다")
        self.assertEqual(len(_TG_CHANNEL), 0, "잘린 메시지가 전송됐다")
        self.assertEqual(
            len(list((send_root / ".claude/state/consortium/outbox").glob("*.json"))), 1,
            "거부된 메시지가 outbox 에서 사라졌다")


class _MockSlack(BaseHTTPRequestHandler):
    """Slack Web API 흉내 — `conversations.history` 는 **봇 글도 돌려준다**.

    이것이 Telegram 과 갈리는 지점이자 Slack 을 권장하는 이유다. history 는
    이벤트 구독이 아니라 **채널 로그 읽기**라 `bot_id` 가 붙은 메시지가 그대로 들어온다.
    """

    def _reply(self, payload: dict):
        raw = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)))
        if self.path.rsplit("/", 1)[-1] == "chat.postMessage":
            ts = f"{1700000000 + len(_SL_CHANNEL)}.000100"
            _SL_CHANNEL.append({"type": "message", "bot_id": "B01", "subtype": "bot_message",
                                "ts": ts, "channel": body["channel"], "text": body["text"]})
            return self._reply({"ok": True, "ts": ts})
        self._reply({"ok": False, "error": "unknown_method"})

    def do_GET(self):
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        oldest = qs.get("oldest", ["0"])[0]
        msgs = [m for m in _SL_CHANNEL if float(m["ts"]) > float(oldest or 0)]
        self._reply({"ok": True, "messages": list(reversed(msgs)), "has_more": False})

    def log_message(self, *a):
        """테스트 출력을 더럽히지 않는다."""


_SL_CHANNEL: list[dict] = []


class SlackGatewayRoundTripTest(unittest.TestCase):
    """Slack 완전 왕복 — **권장 transport** 의 근거 (ADR-013 결정 5).

    Telegram 이 탈락한 이유(봇↔봇 비가시)가 여기서는 성립하지 않는다는 것을
    보이는 것이 이 클래스의 목적이다. 네트워크만 mock 이고 봉투 포장·복원·
    cursor 멱등·수신자 필터는 실코드다.
    """

    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), _MockSlack)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def setUp(self):
        _SL_CHANNEL.clear()
        self.tmp = tempfile.TemporaryDirectory()
        self._env_backup = {k: os.environ.get(k) for k in (
            "CONSORTIUM_SLACK_BASE", "CONSORTIUM_SLACK_TOKEN", "CONSORTIUM_SLACK_CHANNEL")}
        os.environ["CONSORTIUM_SLACK_BASE"] = f"http://127.0.0.1:{self.port}"
        os.environ["CONSORTIUM_SLACK_TOKEN"] = "xoxb-mock"
        os.environ["CONSORTIUM_SLACK_CHANNEL"] = "C0CONSORTIUM"

    def tearDown(self):
        for key, val in self._env_backup.items():
            if val is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = val
        self.tmp.cleanup()

    def _run(self, mod, argv):
        old = sys.argv
        sys.argv = ["consortium.py", *argv]
        try:
            mod.main()
            return 0
        except SystemExit as exc:
            return int(exc.code or 0)
        finally:
            sys.argv = old

    def _node(self, name: str, team: str):
        root = Path(self.tmp.name) / name
        root.mkdir(parents=True, exist_ok=True)
        mod = _load_consortium(root)
        self._run(mod, ["init", team, "--agents", "developer"])
        return mod, root

    def test_봇이_보낸_메시지를_다른_팀_노드가_받는다(self):
        """Telegram 과 갈리는 지점 — 이게 되기 때문에 Slack 이 권장이다."""
        send_mod, _ = self._node("sl-a", "team-a")
        self._run(send_mod, ["send", "--to", "team-b", "--role", "developer",
                             "--cycle", "SL1", "--msg", "슬랙 왕복 — 한글도"])
        self.assertEqual(send_mod._send_slack(), 0, "발신 실패")
        self.assertEqual(len(_SL_CHANNEL), 1, "채널에 적재되지 않았다")

        recv_mod, recv_root = self._node("sl-b", "team-b")
        self.assertEqual(recv_mod._receive_slack(), 0, "수신 실패")
        inbox = list((recv_root / ".claude/state/consortium/inbox").glob("*.json"))
        self.assertEqual(len(inbox), 1, f"inbox 적재 실패: {inbox}")
        got = json.loads(inbox[0].read_text(encoding="utf-8"))
        self.assertEqual(got["from_team"], "team-a")
        self.assertEqual(got["cycle_id"], "SL1")
        self.assertEqual(got["msg"], "슬랙 왕복 — 한글도")
        self.assertEqual(got["status"], "received")

    def test_재폴링해도_중복_적재되지_않는다(self):
        send_mod, _ = self._node("sl-a", "team-a")
        self._run(send_mod, ["send", "--to", "team-b", "--role", "qa",
                             "--cycle", "SL2", "--msg", "검증 요청"])
        send_mod._send_slack()
        recv_mod, recv_root = self._node("sl-b", "team-b")
        recv_mod._receive_slack()
        recv_mod._receive_slack()
        self.assertEqual(len(list((recv_root / ".claude/state/consortium/inbox").glob("*.json"))), 1)

    def test_남의_메시지는_받지_않는다(self):
        send_mod, _ = self._node("sl-a", "team-a")
        self._run(send_mod, ["send", "--to", "team-z", "--role", "developer",
                             "--cycle", "SL3", "--msg", "제3자 앞"])
        send_mod._send_slack()
        recv_mod, recv_root = self._node("sl-b", "team-b")
        recv_mod._receive_slack()
        self.assertEqual(list((recv_root / ".claude/state/consortium/inbox").glob("*.json")), [])

    def test_처리_실패분은_원본을_보존하고_cursor_를_멈춘다(self):
        """cursor 전진은 '보존 또는 처리된 접두' 까지만 — 안 그러면 소실된다 (MUST-3)."""
        send_mod, _ = self._node("sl-a", "team-a")
        self._run(send_mod, ["send", "--to", "team-b", "--role", "developer",
                             "--cycle", "SL4", "--msg", "보존 대상"])
        send_mod._send_slack()

        recv_mod, recv_root = self._node("sl-b", "team-b")
        real = recv_mod._write_unique
        recv_mod._write_unique = lambda p, t: (_ for _ in ()).throw(OSError(28, "No space left"))
        try:
            self.assertEqual(recv_mod._receive_slack(), 0, "실패가 루프를 죽였다")
        finally:
            recv_mod._write_unique = real
        state = recv_root / ".claude/state/consortium"
        # 보존도 실패했으므로 cursor 가 전진하면 안 된다 (다음 폴링이 다시 받아야 한다)
        self.assertFalse((state / "slack-cursor.json").exists(),
                         "보존 실패인데 cursor 가 전진했다 — 다음 폴링이 건너뛴다")

if __name__ == "__main__":
    unittest.main(verbosity=2)
