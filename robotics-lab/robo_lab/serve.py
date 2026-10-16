"""Local web UI for the robotics safety lab.

Runs the REAL lab engine behind a small stdlib HTTP server and serves a single-page UI where
you design an AMR safety stack, pick attacks, click Run, and see real measured results + charts.

    python -m robo_lab.serve           # then open the printed URL (default http://localhost:8109)

No third-party dependencies.
"""
from __future__ import annotations
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
from . import run as R

PORT = int(os.environ.get("ROBO_LAB_PORT", "8109"))
HERE = os.path.dirname(__file__)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json"):
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        # UI is served from this same origin; no cross-origin header needed. Bind is localhost-only.
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
        if u.path == "/api/profiles":
            return self._send(200, json.dumps(R.profiles_api()))
        if u.path == "/api/components":
            q = parse_qs(u.query)
            pid = q.get("profile", [None])[0]
            prof = R.get_profile(pid) if pid else None
            return self._send(200, json.dumps(R.component_catalog(prof)))
        if u.path == "/api/presets":
            return self._send(200, json.dumps(R.presets()))
        if u.path == "/api/run":
            q = parse_qs(u.query)
            key = q.get("attack", ["baseline"])[0]
            nh = max(1, min(int(q.get("hazards", q.get("hostile", ["4"]))[0]), 60))
            nb = max(0, min(int(q.get("cleared", q.get("benign", ["3"]))[0]), 60))
            pid = q.get("profile", [None])[0]
            prof = R.get_profile(pid) if pid else None
            try:
                return self._send(200, json.dumps(R.run_api(key, nh, nb, profile=prof)))
            except Exception as e:
                return self._send(400, json.dumps({"error": str(e)}))
        return self._send(404, json.dumps({"error": "not found"}))

    def do_POST(self):
        u = urlparse(self.path)
        if u.path == "/api/profile":
            # register a user-supplied robot profile ("Add your robot"); returns its id
            try:
                n = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(n) or "{}")
                pid = R.register_profile_api(body)
                return self._send(200, json.dumps({"id": pid, "profiles": R.profiles_api()}))
            except Exception as e:
                return self._send(400, json.dumps({"error": str(e)}))
        if u.path == "/api/run":
            try:
                n = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(n) or "{}")
                key = body.get("attack", "baseline")
                nh = max(1, min(int(body.get("hazards", body.get("hostile", 4))), 60))
                nb = max(0, min(int(body.get("cleared", body.get("benign", 3))), 60))
                design = body.get("design")
                # profile can be an id (string) or an inline profile dict
                prof = body.get("profile")
                if isinstance(prof, str):
                    prof = R.get_profile(prof)
                elif isinstance(prof, dict):
                    R.register_profile_api(prof)
                    prof = R.get_profile(prof.get("id") or prof.get("name"))
                return self._send(200, json.dumps(R.run_api(key, nh, nb, design, profile=prof)))
            except Exception as e:
                return self._send(400, json.dumps({"error": str(e)}))
        return self._send(404, json.dumps({"error": "not found"}))


def _find_free_port(preferred):
    import socket
    for p in range(preferred, preferred + 20):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind(("127.0.0.1", p))
                return p
            except OSError:
                continue
    return preferred


def main():
    port = _find_free_port(PORT)
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    bar = "=" * 48
    print("\n" + bar)
    print("  Robotics Safety Lab UI is running.")
    print("  Open:  http://localhost:%d" % port)
    if port != PORT:
        print("  (port %d was busy -> using %d instead)" % (PORT, port))
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
