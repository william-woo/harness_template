"""OpenCode → Ollama 사이 로깅 프록시 (stdlib). 실제 전송 페이로드를 캡처한다.

모순 조사(측정 11 결과 8): 원시 /v1 에서는 gemma 가 도구 호출을 하고 qwen 은 무반응인데
하네스에서는 정반대다. OpenCode 가 무엇을 보내는지 봐야 원인이 확정된다.
"""
import json, sys, urllib.request, urllib.error
from http.server import BaseHTTPRequestHandler, HTTPServer

UPSTREAM = "http://172.16.10.217:11434"
LOG = sys.argv[2] if len(sys.argv) > 2 else "/tmp/proxy.jsonl"


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
        try:
            with urllib.request.urlopen(req, timeout=600) as up:
                data = up.read()
                self.send_response(up.status)
                for k, v in up.headers.items():
                    if k.lower() not in ("transfer-encoding", "content-length", "connection"):
                        self.send_header(k, v)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                self._log({"dir": "res", "status": up.status,
                           "body": data[:20000].decode(errors="replace")})
        except urllib.error.HTTPError as e:
            payload = e.read()
            self._log({"dir": "res", "status": e.code, "body": payload[:4000].decode(errors="replace")})
            self.send_response(e.code); self.send_header("Content-Length", str(len(payload)))
            self.end_headers(); self.wfile.write(payload)

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


HTTPServer(("127.0.0.1", int(sys.argv[1])), H).serve_forever()
