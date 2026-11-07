"""Serve the static site/ folder for local viewing with caching switched off (so a reload always fetches the current files).

  python3 scripts/serve_site.py [--port 8010] [--host 127.0.0.1]

Standard library only; serves nothing outside site/. Use --host 0.0.0.0 to open it from a phone on the same network.
"""
import argparse
import functools
import http.server
import sys
from pathlib import Path

SITE = Path(__file__).resolve().parent.parent / "site"


class NoCacheHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-store, max-age=0")
        super().end_headers()


def make_server(host: str, port: int, directory: Path = SITE) -> http.server.ThreadingHTTPServer:
    handler = functools.partial(NoCacheHandler, directory=str(directory))
    return http.server.ThreadingHTTPServer((host, port), handler)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8010)
    a = ap.parse_args(argv)
    srv = make_server(a.host, a.port)
    print(f"serving {SITE} on http://{a.host}:{a.port}/ (no caching); Ctrl-C to stop")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
