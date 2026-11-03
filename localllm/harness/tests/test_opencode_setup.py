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
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_SETUP = _ROOT / ".claude" / "bin" / "opencode-setup.sh"

_GEN = "qwen2.5:14b-instruct-q8_0"
_JUDGE = "qwen2.5:32b-instruct-q4_K_M"


class OpencodeSetupLimitTest(unittest.TestCase):
    """기존 설정이 **있을 때**의 병합 경로 — 보정이 여기서 일어난다."""

    def setUp(self):
        if not _SETUP.is_file():
            self.skipTest("opencode-setup.sh 없음 (d-2 오버레이 변형에서만 존재)")
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        self.cfg = self.home / "opencode" / "opencode.jsonc"
        self.cfg.parent.mkdir(parents=True)

    def tearDown(self):
        self.tmp.cleanup()

    def _run(self, **env_over) -> subprocess.CompletedProcess:
        env = dict(os.environ)
        env.update({"XDG_CONFIG_HOME": str(self.home),
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


if __name__ == "__main__":
    unittest.main()
