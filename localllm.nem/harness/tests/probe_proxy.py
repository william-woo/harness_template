"""OpenCode → Ollama 사이 로깅 프록시 (stdlib). 실제 전송 페이로드를 캡처한다.

모순 조사(측정 11 결과 8): 원시 /v1 에서는 gemma 가 도구 호출을 하고 qwen 은 무반응인데
하네스에서는 정반대다. OpenCode 가 무엇을 보내는지 봐야 원인이 확정된다.
"""
import json, sys, urllib.request, urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

UPSTREAM = "http://172.16.10.217:11434"
LOG = sys.argv[2] if len(sys.argv) > 2 else "/tmp/proxy.jsonl"


def _summarize(text: str) -> dict:
    """SSE 스트림에서 델타 분포·길이·도구호출·종료사유를 집계한다.

    본문이 잘려도 살아남도록 로그 시점에 계산한다 — 이 요약이 판정의 근거다.
    """
    keys, reasoning, content, tool_calls, finish = {}, [], [], 0, None
    for line in text.split("\n"):
        if not line.startswith("data: "):
            continue
        payload = line[6:].strip()
        if payload == "[DONE]":
            continue
        try:
            chunk = json.loads(payload)
        except ValueError:
            continue
        for ch in chunk.get("choices") or []:
            delta = ch.get("delta") or {}
            for k in delta:
                keys[k] = keys.get(k, 0) + 1
            if delta.get("reasoning"):
                reasoning.append(delta["reasoning"])
            if delta.get("content"):
                content.append(delta["content"])
            if delta.get("tool_calls"):
                tool_calls += 1
            if ch.get("finish_reason"):
                finish = ch["finish_reason"]
    return {"delta_keys": keys, "reasoning_chars": len("".join(reasoning)),
            "content_chars": len("".join(content)), "tool_call_deltas": tool_calls,
            "finish_reason": finish, "reasoning_tail": "".join(reasoning)[-300:]}


class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _log(self, rec):
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False)[:200000] + "\n")

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(n)
        try:
            parsed = json.loads(body)
        except ValueError:
            parsed = {"_raw": body[:2000].decode(errors="replace")}
        self._log({"dir": "req", "path": self.path, "body": parsed})

        req = urllib.request.Request(UPSTREAM + self.path, data=body,
                                     headers={k: v for k, v in self.headers.items()
                                              if k.lower() not in ("host", "content-length")},
                                     method="POST")
        buf = []
        try:
            with urllib.request.urlopen(req, timeout=600) as up:
                self.send_response(up.status)
                for k, v in up.headers.items():
                    if k.lower() not in ("transfer-encoding", "content-length", "connection"):
                        self.send_header(k, v)
                self.send_header("Transfer-Encoding", "chunked")
                self.end_headers()
                # 청크 단위로 **즉시 전달**한다. up.read() 로 통째로 받으면 SSE 스트리밍이
                # 프록시에서 멈춰, 클라이언트는 빈 응답을 받고 응답 로깅에도 도달하지 못한다
                # (측정 11 결과 13 — 버퍼링 프록시가 관측 대상을 스스로 망가뜨렸다).
                while True:
                    chunk = up.read(4096)
                    if not chunk:
                        break
                    buf.append(chunk)
                    self.wfile.write(b"%x\r\n%s\r\n" % (len(chunk), chunk))
                    self.wfile.flush()
                self.wfile.write(b"0\r\n\r\n")
                self.wfile.flush()
                status = up.status
        except urllib.error.HTTPError as e:
            payload = e.read()
            self._log({"dir": "res", "status": e.code, "body": payload[:4000].decode(errors="replace")})
            self.send_response(e.code); self.send_header("Content-Length", str(len(payload)))
            self.end_headers(); self.wfile.write(payload)
            return
        except Exception as e:                      # 클라이언트 조기 종료 등 — 받은 만큼은 남긴다
            status = f"interrupted: {type(e).__name__}: {str(e)[:120]}"
        text = b"".join(buf).decode(errors="replace")
        # 요약은 **로그 시점에** 계산한다. body 만 남기면 절단 상한이 finish_reason 과
        # tool_calls 를 통째로 숨겨, 모델이 안 한 일을 안 했다고 오판하게 된다
        # (측정 11 결과 13 — 20000자 상한이 정확히 그 오판을 만들었다).
        self._log({"dir": "res", "status": status, "summary": _summarize(text),
                   "body": text[:400000]})

    def do_GET(self):
        req = urllib.request.Request(UPSTREAM + self.path, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=120) as up:
                data = up.read()
                self.send_response(up.status)
                self.send_header("Content-Length", str(len(data))); self.end_headers()
                self.wfile.write(data)
                self._log({"dir": "get", "path": self.path, "status": up.status})
        except Exception as e:
            self.send_response(502); self.end_headers()
            self._log({"dir": "get", "path": self.path, "error": str(e)[:200]})

    def log_message(self, *a):
        pass


# 단일 스레드 서버는 동시 요청을 직렬화해 지연을 스스로 만들어낸다 (측정 11 결과 13).
ThreadingHTTPServer(("127.0.0.1", int(sys.argv[1])), H).serve_forever()
