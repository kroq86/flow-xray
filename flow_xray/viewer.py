"""Local HTTP viewer: serves embedded DOT and a WASM Graphviz page (with DOT fallback)."""

from __future__ import annotations

import argparse
import http.server
import socketserver
import sys
import webbrowser
from pathlib import Path


def _static_html() -> bytes:
    p = Path(__file__).resolve().parent / "static" / "viewer.html"
    return p.read_bytes()


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    p = argparse.ArgumentParser(
        prog="flow-xray-viewer",
        description="Serve graph.dot + viewer on localhost (Ctrl+C to stop)",
    )
    p.add_argument("dotfile", type=Path, help="path to .dot file")
    p.add_argument("-p", "--port", type=int, default=0, help="port (0 = auto)")
    p.add_argument("--no-browser", action="store_true", help="do not open a browser tab")
    args = p.parse_args(argv)
    dot_path = args.dotfile
    if not dot_path.is_file():
        print(f"not a file: {dot_path}", file=sys.stderr)
        return 2
    dot_body = dot_path.read_text(encoding="utf-8")
    index = _static_html()

    class H(http.server.BaseHTTPRequestHandler):
        def log_message(self, *_args: object) -> None:
            return

        def do_GET(self) -> None:
            path = self.path.split("?", 1)[0]
            if path in ("/", "/viewer.html"):
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(index)
            elif path == "/graph.dot":
                self.send_response(200)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.end_headers()
                self.wfile.write(dot_body.encode("utf-8"))
            else:
                self.send_error(404)

    with socketserver.TCPServer(("127.0.0.1", args.port), H) as httpd:
        _, port = httpd.server_address
        url = f"http://127.0.0.1:{port}/viewer.html"
        print(url, file=sys.stderr)
        if not args.no_browser:
            webbrowser.open(url)
        print("Serving… Ctrl+C to stop", file=sys.stderr)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("stopped", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
