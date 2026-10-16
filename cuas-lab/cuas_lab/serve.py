"""Local web UI for the C-UAS lab.

Runs the REAL lab engine behind a small stdlib HTTP server and serves a single-page
UI where you pick attacks, click Run, and see real measured results + charts.

    python -m cuas_lab.serve           # then open http://localhost:8099

No third-party dependencies.
"""
from __future__ import annotations
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
from . import run as R

PORT = int(os.environ.get("CUAS_LAB_PORT", "8099"))
HERE = os.path.dirname(__file__)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):            # quiet
        pass

    def _send(self, code, body, ctype="application/json"):
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        # The UI is served from this SAME origin, so no cross-origin header is needed at all.
        # Dropping the previous wildcard "Access-Control-Allow-Origin: *" keeps this security
        # tool from advertising itself to any other local web page. Server also binds 127.0.0.1 only.
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        u = urlparse(self.path)
        if u.path in ("/", "/index.html"):
            with open(os.path.join(HERE, "ui.html"), "rb") as f:
                return self._send(200, f.read(), "text/html; charset=utf-8")
        if u.path == "/api/catalog":
            return self._send(200, json.dumps(R.attack_catalog()))
        if u.path == "/api/components":
            return self._send(200, json.dumps(R.component_catalog()))
        if u.path == "/api/presets":
            return self._send(200, json.dumps(R.presets()))
        if u.path == "/api/run":
            q = parse_qs(u.query)
            key = q.get("attack", ["baseline"])[0]
            nh = int(q.get("hostile", ["4"])[0])
            nb = int(q.get("benign", ["3"])[0])
            nh = max(1, min(nh, 40)); nb = max(0, min(nb, 40))   # sane bounds
            try:
                return self._send(200, json.dumps(R.run_api(key, nh, nb)))
            except Exception as e:
                return self._send(400, json.dumps({"error": str(e)}))
        return self._send(404, json.dumps({"error": "not found"}))

    def do_POST(self):
        u = urlparse(self.path)
        if u.path == "/api/run":
            try:
                n = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(n) or "{}")
                key = body.get("attack", "baseline")
                nh = max(1, min(int(body.get("hostile", 4)), 60))
                nb = max(0, min(int(body.get("benign", 3)), 60))
                design = body.get("design")
                return self._send(200, json.dumps(R.run_api(key, nh, nb, design)))
            except Exception as e:
                return self._send(400, json.dumps({"error": str(e)}))
        return self._send(404, json.dumps({"error": "not found"}))


def _find_free_port(preferred):
    """Try the preferred port; if it's taken (e.g. a leftover server), walk up until free.
    This guarantees the lab always starts for a live demo instead of silently colliding."""
    import socket
    for p in range(preferred, preferred + 20):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind(("127.0.0.1", p))
                return p
            except OSError:
                continue
    return preferred  # fall back; will error loudly if truly stuck


def main():
    port = _find_free_port(PORT)
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    bar = "=" * 48
    print("\n" + bar)
    print("  C-UAS Lab UI is running.")
    print("  Open:  http://localhost:%d" % port)
    if port != PORT:
        print("  (port %d was busy — using %d instead)" % (PORT, port))
    print("  Stop:  Ctrl+C in this window")
    print(bar + "\n")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n  stopped.\n")
    finally:
        srv.server_close()


if __name__ == "__main__":
    main()
