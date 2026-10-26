"""P3.5 screenshot receiver: accepts one PNG per POST and saves it in screenshots/.

Run it isolated, bound to loopback only:
    python -I receiver.py [port]

- Binds to 127.0.0.1 only (default port 8766; never 8765, the preview server).
- One fixed path: POST /shot?name=<name>.png with the PNG bytes as the body.
- Names must match [a-z0-9-]+\\.png, so no path can be given.
- Bodies over 20 MB, or that don't start with the PNG signature, are refused.
- CORS allows only the mockup's origin, http://127.0.0.1:8765.
No packages: the standard library only.
"""

import http.server
import os
import re
import sys
import urllib.parse

HOST = "127.0.0.1"
ALLOWED_ORIGIN = "http://127.0.0.1:8765"
PATH = "/shot"
MAX_BYTES = 20 * 1024 * 1024
NAME_RE = re.compile(r"[a-z0-9-]+\.png")
PNG_SIG = b"\x89PNG\r\n\x1a\n"
OUT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # screenshots/


class Handler(http.server.BaseHTTPRequestHandler):
    server_version = "ShelfSyncShotReceiver/1"

    def _cors(self):
        if self.headers.get("Origin") == ALLOWED_ORIGIN:
            self.send_header("Access-Control-Allow-Origin", ALLOWED_ORIGIN)
            self.send_header("Access-Control-Allow-Methods", "POST")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.send_header("Vary", "Origin")

    def _reply(self, code, text):
        body = text.encode("utf-8")
        self.send_response(code)
        self._cors()
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        if urllib.parse.urlsplit(self.path).path != PATH or self.headers.get("Origin") != ALLOWED_ORIGIN:
            return self._reply(403, "refused")
        self.send_response(204)
        self._cors()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        self._reply(405, "POST only")

    def do_POST(self):
        parts = urllib.parse.urlsplit(self.path)
        if parts.path != PATH:
            return self._reply(404, "unknown path")
        origin = self.headers.get("Origin")
        if origin is not None and origin != ALLOWED_ORIGIN:
            return self._reply(403, "origin refused")
        names = urllib.parse.parse_qs(parts.query).get("name", [])
        if len(names) != 1 or not NAME_RE.fullmatch(names[0]):
            return self._reply(400, "name must match [a-z0-9-]+.png")
        try:
            length = int(self.headers.get("Content-Length", ""))
        except ValueError:
            return self._reply(411, "Content-Length required")
        if length <= len(PNG_SIG) or length > MAX_BYTES:
            return self._reply(413, "size must be under 20 MB")
        data = self.rfile.read(length)
        if len(data) != length or not data.startswith(PNG_SIG):
            return self._reply(400, "not a PNG")
        target = os.path.join(OUT_DIR, names[0])
        tmp = target + ".part"
        with open(tmp, "wb") as f:
            f.write(data)
        os.replace(tmp, target)
        self._reply(200, f"saved {names[0]} ({length} bytes)")

    def log_message(self, fmt, *args):
        sys.stdout.write("%s %s\n" % (self.log_date_time_string(), fmt % args))
        sys.stdout.flush()


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8766
    if port == 8765:
        raise SystemExit("8765 is the preview server's port")
    srv = http.server.HTTPServer((HOST, port), Handler)
    print(f"receiver on http://{HOST}:{port}{PATH}, writing to {OUT_DIR}", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()


if __name__ == "__main__":
    main()
