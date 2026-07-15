#!/usr/bin/env python3
"""Serve the prototype on localhost without exposing private-data directories."""

from __future__ import annotations

import argparse
import functools
import json
import posixpath
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlsplit

from runtime_paths import NORMALIZED_DIR, ROOT, ensure_private_dirs

BLOCKED_PREFIXES = ("/private-data/", "/sources/raw/", "/.git/")
BLOCKED_DIRECTORIES = {"/private-data", "/sources/raw", "/.git"}
BLOCKED_LEGACY_FILES = {
    "/data/properties.json",
    "/data/nbf-properties.json",
    "/data/jre-properties.json",
    "/data/glp-properties.json",
    "/data/import-report.json",
    "/data/all-import-report.json",
    "/data/geocode-cache.json",
}


def normalized_request_path(raw_path: str) -> str:
    decoded = unquote(urlsplit(raw_path).path)
    return "/" + posixpath.normpath(decoded).lstrip("/")


def is_blocked_path(request_path: str) -> bool:
    return (
        request_path in BLOCKED_DIRECTORIES
        or request_path.startswith(BLOCKED_PREFIXES)
        or request_path in BLOCKED_LEGACY_FILES
        or request_path == "/.env"
        or request_path.startswith("/.env.")
    )


class LocalHandler(SimpleHTTPRequestHandler):
    def copyfile(self, source, outputfile) -> None:
        try:
            super().copyfile(source, outputfile)
        except BrokenPipeError:
            # A browser can cancel a large JSON response after reading headers.
            pass

    def send_head(self):
        request_path = normalized_request_path(self.path)
        if request_path == "/runtime-data/properties.json":
            target = NORMALIZED_DIR / "properties.json"
            if not target.is_file():
                self.send_error(404, "Local normalized data not found")
                return None
            stream = target.open("rb")
            size = target.stat().st_size
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(size))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            return stream
        if is_blocked_path(request_path):
            self.send_error(404, "Private runtime path is not publicly served")
            return None
        return super().send_head()

    def log_message(self, format_string: str, *args) -> None:
        super().log_message(format_string, *args)


class LocalServer(ThreadingHTTPServer):
    allow_reuse_address = True


def main() -> int:
    parser = argparse.ArgumentParser(description="J-REIT Intelligence local-only web server")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--bind", default="127.0.0.1", choices=["127.0.0.1", "::1"])
    args = parser.parse_args()
    ensure_private_dirs()
    handler = functools.partial(LocalHandler, directory=str(ROOT))
    server = LocalServer((args.bind, args.port), handler)
    print(json.dumps({
        "url": f"http://127.0.0.1:{args.port}",
        "bind": args.bind,
        "private_data": str(NORMALIZED_DIR.parent),
        "note": "Control+C で終了",
    }, ensure_ascii=False, indent=2))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n停止しました。")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
