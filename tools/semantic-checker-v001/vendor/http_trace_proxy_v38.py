#!/usr/bin/env python3
from __future__ import annotations

import argparse
import http.client
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HOP = {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
       "te", "trailers", "transfer-encoding", "upgrade"}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--listen-port", type=int, default=0,
                   help="Listener port; 0 asks the OS for a free port")
    p.add_argument("--target-port", type=int, required=True)
    p.add_argument("--trace", required=True)
    p.add_argument("--port-file", help="Write the actual listener port here once bound")
    a = p.parse_args()
    lock = threading.Lock()

    class Proxy(BaseHTTPRequestHandler):
        def do_GET(self): self.forward()
        def do_POST(self): self.forward()
        def do_PUT(self): self.forward()
        def do_PATCH(self): self.forward()
        def do_DELETE(self): self.forward()
        def do_HEAD(self): self.forward()
        def do_OPTIONS(self): self.forward()
        def log_message(self, *_): pass

        def forward(self):
            length = int(self.headers.get("Content-Length", "0") or 0)
            body = self.rfile.read(length) if length else b""
            headers = {k: v for k, v in self.headers.items()
                       if k.lower() not in HOP and k.lower() != "host"}
            conn = http.client.HTTPConnection("127.0.0.1", a.target_port, timeout=30)
            try:
                conn.request(self.command, self.path, body=body, headers=headers)
                response = conn.getresponse()
                response_body = response.read()
                self.send_response(response.status)
                for k, v in response.getheaders():
                    if k.lower() not in HOP and k.lower() != "content-length":
                        self.send_header(k, v)
                self.send_header("Content-Length", str(len(response_body)))
                self.end_headers()
                if self.command != "HEAD":
                    self.wfile.write(response_body)

                def decode(raw):
                    if not raw:
                        return None
                    try:
                        return json.loads(raw.decode("utf-8"))
                    except Exception:
                        return raw.decode("utf-8", errors="replace")

                event = {
                    "kind": "api_success" if response.status < 400 else "api_result",
                    "method": self.command,
                    "path": self.path.split("?", 1)[0],
                    "body": decode(body),
                    "status": response.status,
                    "response": decode(response_body),
                }
                with lock, open(a.trace, "a", encoding="utf-8") as f:
                    f.write("MODEL_EVENT " + json.dumps(event, sort_keys=True) + "\n")
                    f.flush()
            finally:
                conn.close()

    server = ThreadingHTTPServer(("127.0.0.1", a.listen_port), Proxy)
    actual_port = int(server.server_address[1])
    if a.port_file:
        path = Path(a.port_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(str(actual_port) + "\n", encoding="utf-8")
    print(f"PROXY_READY http://127.0.0.1:{actual_port} -> 127.0.0.1:{a.target_port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
