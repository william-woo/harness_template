"""`opencode-setup.sh` 의 **추론 예산 등재·보정** (ADR-021 결정 3).

## 왜 이 테스트가 있나

추론 모델(`thinking` 선언 — gemma4·nemotron·muse-glimmer 등)은 도구를 호출하기 **전에**
추론 토큰을 쓴다. 전역 설정에 `limit: {context, output}` 이 없으면 추론 중간에서 잘려
도구 호출이 **0건**이 된다 (`finish=length`). ADR-021 측정 11 결과 10 이 찾아낸 원인이고,
그때 배치 2개를 그 함정 때문에 폐기했다.

이 등재·보정은 원래 `localllm.nem` 에만 있었다. 2026-10-23 에 nem 이 `deprecated/` 로
내려가면서 **활성 `localllm` 에는 남지 않았고**, 그 상태로 추론 모델을 물리면 "이 모델은
우리 하네스에서 안 된다" 는 틀린 결론이 난다. 이미 서버에 있는 `gemma4:26b` 가 바로
그 경우다. 2026-11-03 에 부모로 이식하면서 이 테스트를 함께 붙인다.

## 셸 스크립트를 **실제로 돌린다**

설정 파일을 직접 만들고 스크립트를 태운 뒤 결과 JSON 을 본다. 문자열 grep 으로는
"코드가 있다" 만 확인되고 "그 코드가 맞게 동작한다" 는 확인되지 않는다 — 이 리포가
F021 에서 열 번 센 공회전 형태들이 전부 그 모양이었다.
"""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_SETUP = _ROOT / ".claude" / "bin" / "opencode-setup.sh"

_GEN = "qwen2.5:14b-instruct-q8_0"
_JUDGE = "qwen2.5:32b-instruct-q4_K_M"


class FakeOllama:
    """스크립트가 실제로 말을 거는 Ollama 를 대신한다.

    실서버를 쓰면 테스트가 GPU 박스의 전원 상태에 좌우된다 — 2026-11-04 에 실제로
    서버가 내려가 "조회 실패" 로 빠졌다. 창 크기는 테스트가 정해야 측정이 된다.

    `declared` 에 넣은 모델은 Modelfile 에 `num_ctx` 가 박힌 것처럼 `/api/show` 로
    알려주고, `runtime` 에 넣은 모델은 그게 없어 `/api/ps` 로만 드러나는 서버
    기본값을 흉내 낸다. 두 경로가 스크립트에서 서로 다른 분기다.
    """

    def __init__(self, declared=None, runtime=None, thinking=()):
        self.declared = dict(declared or {})
        self.runtime = dict(runtime or {})
        self.thinking = set(thinking)
        self.loaded = set()
        self.generate_calls = []
        fake = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *args):
                pass

            def _send(self, obj):
                body = json.dumps(obj).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                if self.path == "/api/version":
                    return self._send({"version": "0.0.0-fake"})
                if self.path == "/api/ps":
                    return self._send({"models": [
                        {"name": m, "context_length": fake.runtime[m]}
                        for m in sorted(fake.loaded) if m in fake.runtime]})
                return self._send({})

            def do_POST(self):
                payload = json.loads(self.rfile.read(
                    int(self.headers.get("Content-Length", 0))) or b"{}")
                model = payload.get("model", "")
                if self.path == "/api/show":
                    if model not in fake.declared and model not in fake.runtime:
                        self.send_error(404)
                        return
                    params = ("temperature 1" if model not in fake.declared
                              else f"num_ctx                        {fake.declared[model]}\ntemperature 1")
                    caps = ["completion", "tools"] + (
                        ["thinking"] if model in fake.thinking else [])
                    return self._send({"parameters": params, "capabilities": caps})
                if self.path == "/api/generate":
                    fake.generate_calls.append(model)
                    fake.loaded.add(model)
                    return self._send({"response": "", "done": True})
                return self._send({})

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


class _SetupFixture(unittest.TestCase):
    """픽스처만 — 케이스는 아래 두 클래스가 따로 가진다.

    케이스를 가진 클래스를 상속하면 부모의 케이스가 자식 이름으로 **한 번 더** 돈다.
    같은 실수를 `test_lint_overlay.py` 에서 한 번 했고, 그때도 테스트 수만 늘고
    검증력은 그대로였다.
    """

    #: 창이 충분한 서버 — 등재·보정 경로를 보는 테스트는 [4/5] 게이트에 걸리면 안 된다.
    FAKE = dict(declared={_GEN: 32768, _JUDGE: 32768})

    def setUp(self):
        if not _SETUP.is_file():
            self.skipTest("opencode-setup.sh 없음 (d-2 오버레이 변형에서만 존재)")
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        self.cfg = self.home / "opencode" / "opencode.jsonc"
        self.cfg.parent.mkdir(parents=True)
        self.ollama = FakeOllama(**self.FAKE)

    def tearDown(self):
        self.ollama.close()
        self.tmp.cleanup()

    def _run(self, **env_over) -> subprocess.CompletedProcess:
        env = dict(os.environ)
        env.update({"XDG_CONFIG_HOME": str(self.home), "OLLAMA_HOST": self.ollama.url,
                    "OLLAMA_MODEL": _GEN, "OLLAMA_JUDGE_MODEL": _JUDGE})
        env.update(env_over)
        return subprocess.run(["bash", str(_SETUP)], capture_output=True, text=True,
                              env=env, timeout=180)

    def _models(self) -> dict:
        return json.loads(self.cfg.read_text(encoding="utf-8"))["provider"]["ollama"]["models"]

    def _write(self, models: dict, *, jsonc_noise: bool = False):
        body = json.dumps({"provider": {"ollama": {"models": models}}},
                          ensure_ascii=False, indent=2)
        if jsonc_noise:
            # 흔한 JSONC: 행끝 주석 + trailing comma. 전 판은 행 **시작** 주석만 벗겨서
            # 여기서 JSONDecodeError 가 났고, 그러고도 "설정 완료" 를 찍었다.
            body = body.replace('"models": {', '"models": {   // 역할별 모델', 1)
            body = body.replace("\n  }\n}", ",\n  }\n}")
            body = "// 전역 OpenCode 설정\n" + body
        self.cfg.write_text(body, encoding="utf-8")


class OpencodeSetupLimitTest(_SetupFixture):
    """`limit` 등재·보정 — 설정 파일 안에서 끝나는 동작."""

    # ── 등재 ─────────────────────────────────────────────────────────
    def test_새_모델은_limit_과_함께_등재된다(self):
        """`limit` 없이 등재하면 추론 모델에서 도구 호출이 0건이 된다."""
        self._write({})
        self._run()
        for key in (_GEN, _JUDGE):
            with self.subTest(model=key):
                self.assertIn(key, self._models(), "모델이 등재되지 않았다")
                self.assertEqual(self._models()[key].get("limit"),
                                 {"context": 32768, "output": 4096},
                                 "limit 없이 등재됐다 — 추론 모델이 도구를 못 부른다")

    def test_예산은_환경변수로_조정된다(self):
        self._write({})
        self._run(OLLAMA_CONTEXT="65536", OLLAMA_OUTPUT="8192")
        self.assertEqual(self._models()[_GEN]["limit"],
                         {"context": 65536, "output": 8192})

    # ── 보정 ─────────────────────────────────────────────────────────
    def test_limit_이_없는_기존_항목을_보정한다(self):
        """이미 등재된 항목도 고쳐야 한다 — 전 판으로 깔린 설정이 그 상태다."""
        self._write({_GEN: {"name": _GEN}, _JUDGE: {"name": _JUDGE}})
        self._run()
        for key in (_GEN, _JUDGE):
            with self.subTest(model=key):
                self.assertEqual(self._models()[key].get("limit"),
                                 {"context": 32768, "output": 4096},
                                 "limit 누락이 보정되지 않았다")

    def test_반쪽_limit_도_보정하고_기존_값은_살린다(self):
        """`limit` 은 **두 필드를 모두** 요구한다 — 하나만 있으면 OpenCode 가
        `Configuration is invalid` 로 전 실행을 거부한다.

        그런데 보정이 "`limit` 키가 통째로 없을 때만" 돌면 반쪽 상태가 그대로
        "모두 등재됨" 으로 통과한다. 사용자가 적어 둔 값은 살려야 한다.
        """
        self._write({_GEN: {"name": _GEN, "limit": {"context": 131072}},
                     _JUDGE: {"name": _JUDGE, "limit": None}})
        self._run()
        self.assertEqual(self._models()[_GEN]["limit"],
                         {"context": 131072, "output": 4096},
                         "기존 context 를 뭉갰거나 output 을 안 채웠다")
        self.assertEqual(self._models()[_JUDGE]["limit"],
                         {"context": 32768, "output": 4096},
                         "`limit: null` 반쪽 상태가 보정되지 않았다")

    def test_이미_온전하면_건드리지_않는다(self):
        """음성 대조 — 멱등이어야 한다. 매번 고치면 '보정' 이 아니라 덮어쓰기다.

        **바이트 비교로 쓰면 안 된다.** 검증 단계의 `opencode models` 가 실행되면
        OpenCode 가 자기 전역 설정을 스스로 정규화해서 파일이 바뀐다 (실측: 448→496,
        OpenCode 1.16.2). 그건 이 스크립트의 쓰기가 아니다. 그래서 ① 백업이
        안 생겼고(= 스크립트가 쓰지 않았다) ② 값이 그대로인지를 본다.
        """
        full = {"context": 16384, "output": 2048}
        self._write({_GEN: {"name": _GEN, "limit": dict(full)},
                     _JUDGE: {"name": _JUDGE, "limit": dict(full)}})
        r = self._run()
        self.assertFalse((self.cfg.parent / "opencode.jsonc.bak-harness").exists(),
                         "온전한 설정인데 스크립트가 백업을 떴다 — 덮어썼다는 뜻이다")
        for key in (_GEN, _JUDGE):
            with self.subTest(model=key):
                self.assertEqual(self._models()[key]["limit"], full,
                                 "온전한 값을 기본값으로 덮어썼다")
        self.assertIn("모두 등재됨", r.stdout)

    # ── 입력 방어 ────────────────────────────────────────────────────
    def test_JSONC_주석과_trailing_comma_를_견딘다(self):
        """전 판은 행 **시작** 주석만 벗겨서 흔한 JSONC 에 파싱 실패했고,
        그러고도 '설정 완료' 를 찍었다 — 조용한 실패다."""
        self._write({_GEN: {"name": _GEN}}, jsonc_noise=True)
        r = self._run()
        self.assertNotIn("Traceback", r.stdout + r.stderr,
                         "JSONC 를 파싱하지 못했다")
        self.assertEqual(self._models()[_GEN].get("limit"),
                         {"context": 32768, "output": 4096})

    def test_정수가_아닌_예산은_설정을_망가뜨리기_전에_멈춘다(self):
        """`OLLAMA_OUTPUT=abc` 가 JSON 에 들어가면 OpenCode 가 설정을 읽지 못해
        **모든 실행이 거부**된다. 쓰기 전에 거른다."""
        self._write({})
        r = self._run(OLLAMA_OUTPUT="abc")
        self.assertIn("정수여야", r.stdout)
        self.assertEqual(json.loads(self.cfg.read_text(encoding="utf-8")
                                    )["provider"]["ollama"]["models"], {},
                         "잘못된 값으로 설정을 건드렸다")

    # ── 신규 생성 경로 ───────────────────────────────────────────────
    def test_설정이_없으면_생성본에도_limit_이_있다(self):
        """병합 경로만 고치고 생성 경로를 빠뜨리면, 새로 까는 사람은 그대로 당한다."""
        self.assertFalse(self.cfg.exists())
        self._run()
        self.assertTrue(self.cfg.exists(), "설정이 생성되지 않았다")
        for key in (_GEN, _JUDGE):
            with self.subTest(model=key):
                self.assertEqual(self._models()[key].get("limit"),
                                 {"context": 32768, "output": 4096})


class ServerContextGateTest(_SetupFixture):
    """`limit` 만으로는 부족하다 — 창을 정하는 건 서버다 (측정 12, 2026-11-04).

    `limit.context` 는 **와이어에 나가지 않는다**. 실측에서 OpenCode 가 보낸 요청에는
    `max_tokens`(=limit.output) 만 있었고, 서버 창 4096 에 도구 프리앰블 ~12.7k 가
    들어가면서 `prompt_tokens=4095 / completion_tokens=1 / finish=length` 로
    도구 호출이 **0건**이 됐다. 설정 파일만 보면 멀쩡해 보이는 상태다.
    """

    def test_창이_모자라면_설정_완료를_찍지_않는다(self):
        """이 배너가 유일한 신호다 — 여기서 '완료' 가 나오면 다음 사람은 도구 호출
        0건의 원인을 모델 탓으로 돌린다."""
        self.ollama.declared = {_GEN: 4096, _JUDGE: 4096}
        self._write({})
        r = self._run()
        self.assertIn("설정 미완료", r.stdout, "창이 4096 인데 완료로 보고했다")
        self.assertNotIn("=== 설정 완료 ===", r.stdout)

    def test_부족하면_고치는_명령을_알려준다(self):
        """진단만 하고 처방이 없으면 읽는 사람이 서버 설정을 뒤져야 한다."""
        self.ollama.declared = {_GEN: 4096, _JUDGE: 32768}
        self._write({})
        r = self._run()
        self.assertIn("/api/create", r.stdout, "고치는 명령이 없다")
        self.assertIn("num_ctx", r.stdout)
        self.assertIn(_GEN, r.stdout.split("/api/create")[1][:300],
                      "모자란 모델이 처방에 들어 있지 않다")

    def test_충분하면_통과한다(self):
        """음성 대조 — 항상 막으면 게이트가 아니라 벽이다."""
        self._write({})
        r = self._run()
        self.assertIn("=== 설정 완료 ===", r.stdout)
        self.assertNotIn("설정 미완료", r.stdout)

    def test_num_ctx_가_없으면_적재해서_실제_창을_잰다(self):
        """모델에 `num_ctx` 가 없으면 서버 기본값을 따른다. 그 값은 `/api/show` 에
        없고 적재된 모델의 `/api/ps` 에만 나온다 — 안 재면 4096 을 못 본다."""
        self.ollama.declared = {}
        self.ollama.runtime = {_GEN: 4096, _JUDGE: 4096}
        self._write({})
        r = self._run()
        self.assertIn(_GEN, self.ollama.generate_calls, "적재 측정을 하지 않았다")
        self.assertIn("서버 기본값", r.stdout)
        self.assertIn("설정 미완료", r.stdout)

    def test_서버에_닿지_못하면_완료로_적지_않는다(self):
        """서버가 꺼져 있을 때 통과하는 점검은 점검이 아니다. 2026-11-04 에
        실제로 GPU 서버가 내려갔고, 그때 이 스크립트는 '설정 완료' 를 찍었다."""
        self.ollama.close()
        self._write({})
        r = self._run()
        self.assertIn("미확인", r.stdout, "확인하지 못한 것을 완료로 보고했다")
        self.assertNotIn("=== 설정 완료 ===", r.stdout)

    def test_추론_모델은_그_모델_줄에_표시된다(self):
        """`thinking` 선언 여부는 ADR-021 의 예산 함정과 직결된다 — 눈에 보여야 한다.

        **stdout 전체에서 '추론 모델' 을 찾으면 안 된다.** 마지막 배너에도 같은 낱말이
        있어서, 표시를 빼는 변이가 살아남았다. 해당 모델의 **점검 줄**을 봐야 한다.
        """
        self.ollama.thinking = {_GEN}
        self._write({})
        r = self._run()
        lines = {m: ln for ln in r.stdout.splitlines()
                 for m in (_GEN, _JUDGE) if ln.lstrip().startswith(("✅ " + m, "❌ " + m))}
        self.assertIn(_GEN, lines, "점검 줄 자체가 없다")
        self.assertIn("(추론 모델)", lines[_GEN], "추론 모델인데 표시가 없다")
        self.assertNotIn("(추론 모델)", lines.get(_JUDGE, ""),
                         "추론 모델이 아닌데 표시가 붙었다")


if __name__ == "__main__":
    unittest.main()
